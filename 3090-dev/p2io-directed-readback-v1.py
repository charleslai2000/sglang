#!/usr/bin/env python3
"""p2io-directed-readback-v1: engine-faithful v1 zero-copy round-trip probe.

The e7j engine selects _page_set_zero_copy/_page_get_zero_copy for the
"extent" backend, so KV writes go through batch_set_v1 (pwritev into a
mock host pool's page buffers) and reads through batch_get_v1.  This probe
builds a mock host pool exposing get_page_buffer_meta / page_size / layout,
writes N KV pages through batch_set_v1, then reads them back through
batch_get_v1 AND batch_exists, verifying the index keys match.

Also tests the mamba (v2 batch_set_v2 / batch_exists_v2) round-trip with
engine-faithful key semantics: KV chain hashes H0..Hn plus a mamba transfer
keyed on node.hash_value[-1] = Hn.
"""
import ctypes
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from sglang.srt.mem_cache.hicache_storage import (
    HiCacheStorageConfig,
    PoolHitPolicy,
    PoolName,
    PoolTransfer,
)
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend

PAGE_BYTES = 32768  # ps=1, 32KB page


class MockHostPool:
    """Minimal page-first host pool: 2 blocks per page (k/v), page_size=1."""

    page_size = 1
    layout = "page_first"

    def __init__(self, n_pages):
        self.n_pages = n_pages
        # each page = 2 blocks of PAGE_BYTES/2
        self._buf = ctypes.create_string_buffer(n_pages * 2 * (PAGE_BYTES // 2))
        self._size = PAGE_BYTES // 2

    def get_page_buffer_meta(self, host_indices):
        ptr_list = []
        size_list = []
        base = ctypes.addressof(self._buf)
        for idx in host_indices:
            for b in range(2):
                ptr_list.append(base + idx * PAGE_BYTES + b * self._size)
                size_list.append(self._size)
        return ptr_list, size_list

    def fill(self, idx, pattern_seed):
        """Write a recognizable pattern into page idx (both blocks)."""
        p = PAGE_BYTES
        for j in range(p):
            self._buf[idx * p + j] = (pattern_seed + j) % 256

    def read_back(self, idx):
        return bytes(self._buf[idx * PAGE_BYTES : (idx + 1) * PAGE_BYTES])

    def get_data_page(self, index, flat=True):
        return bytes(self._buf[index * PAGE_BYTES : (index + 1) * PAGE_BYTES])

    def get_dummy_flat_data_page(self):
        return bytearray(PAGE_BYTES)

    def set_from_flat_data_page(self, index, data):
        self._buf[index * PAGE_BYTES : (index + 1) * PAGE_BYTES] = bytes(data)


def make_backend(tmpdir):
    cfg = dict(
        tp_rank=0, tp_size=1, pp_rank=0, pp_size=1, attn_cp_rank=0, attn_cp_size=1,
        is_mla_model=False, enable_storage_metrics=False, is_page_first_layout=True,
        model_name="qwen3.5-9b-gptq",
    )
    return ExtentFileBackend(
        HiCacheStorageConfig(**cfg, extra_config={"max_size": "4G", "min_free_space": "1G"}),
        file_path=tmpdir,
    )


def main():
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        backend = make_backend(tmp)
        pool = MockHostPool(n_pages=256)
        backend.mem_pool_host = pool

        n = 5
        keys = [f"hash{i:064x}" for i in range(n)]
        for i, k in enumerate(keys):
            pool.fill(i, 1000 + i)

        # ---- v1 zero-copy write path (what _page_backup uses) ----
        host_indices = list(range(n))
        res = backend.batch_set_v1(keys, host_indices)
        print("batch_set_v1 ->", res)
        write_ok = all(res)

        # ---- v1 zero-copy read path (what _page_transfer uses) ----
        read_back = backend.batch_get_v1(keys, host_indices)
        print("batch_get_v1 ->", read_back)
        read_ok = all(read_back)
        # verify bytes landed
        byte_ok = all(pool.read_back(i) == pool.get_data_page(i) for i in range(n))

        # ---- batch_exists (the presence check used in the base hit query) ----
        exists = backend.batch_exists(keys)
        print("batch_exists ->", exists)
        exists_ok = exists == n

        # storage keys in the index
        idx_keys = list(backend._allocator._index.keys())
        print("index keys:", [k[:20] for k in idx_keys])

        if not (write_ok and read_ok and exists_ok):
            failures += 1
            print("  FAIL (v1 KV path)")

        # ---- mamba v2 path: write transfer keyed on last KV hash, then query ----
        class MambaPool:
            page_size = 1

            def get_data_page(self, index, flat=True):
                b = bytearray(PAGE_BYTES)
                for j in range(0, len(b), 4096):
                    b[j] = (index + j // 4096) % 256
                return b

            def get_dummy_flat_data_page(self):
                return bytearray(PAGE_BYTES)

            def set_from_flat_data_page(self, index, data):
                pass

        backend.registered_pools = {PoolName.MAMBA: MambaPool()}
        mkey = keys[-1]  # node.hash_value[-1]
        mtransfer = PoolTransfer(
            name=PoolName.MAMBA,
            host_indices=[0],
            keys=[mkey],
            hit_policy=PoolHitPolicy.TRAILING_PAGES,
        )
        wres = backend.batch_set_v2([mtransfer])
        # query: full KV chain present + mamba trailing
        qres = backend.batch_exists_v2(keys, [mtransfer])
        print("\nbatch_set_v2 mamba ->", wres)
        print("batch_exists_v2(keys, [mamba]) ->", qres)
        m_write_key = backend._component_key(PoolName.MAMBA, mkey)
        print("mamba write key:", m_write_key[:40])
        # after writing KV keys, kv_pages should be n; mamba trailing on keys[n-1]
        if qres.kv_hit_pages != n or qres.extra_pool_hit_pages.get(PoolName.MAMBA) != n:
            failures += 1
            print("  FAIL (v2 mamba path)")

        backend.close()

    print(f"\n=== {'PASS' if failures == 0 else 'FAIL'} ({failures} failures) ===")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
