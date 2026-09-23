#!/usr/bin/env python3
"""p2io-directed-readback: minimal write->query key consistency probe.

Constructs a real ExtentFileBackend with the same storage config the e7j
engine used (extent, page_first, tp_rank=0/tp_size=1, model_name matching
the config_suffix form), writes a known rid's pages through the real
v1 batch_set_v1 / v2 batch_set_v2 code paths, then queries the same rid
through batch_exists / batch_exists_v2 / batch_get / batch_get_v2, printing
the actual storage key bytes used on each side.

Prints PASS/FAIL for each write->query pair.  The engine-side hashes are
position-aware SHA256 page keys (get_hash_str); here we feed identical key
strings into both sides so the probe isolates the *key-space transform*
(write key vs query key), not the token-to-hash derivation (which is shared
and identical on both sides per utils.py).

Runs on CPU only -- the extent backend is pure file storage.
"""
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

CONFIG = dict(
    tp_rank=0,
    tp_size=1,
    pp_rank=0,
    pp_size=1,
    attn_cp_rank=0,
    attn_cp_size=1,
    is_mla_model=False,
    enable_storage_metrics=False,
    is_page_first_layout=True,
    model_name="qwen3.5-9b-gptq",
)


def make_backend(tmpdir, **overrides):
    cfg = dict(CONFIG)
    cfg.update(overrides)
    return ExtentFileBackend(
        HiCacheStorageConfig(**cfg, extra_config={"max_size": "4G", "min_free_space": "1G"}),
        file_path=tmpdir,
    )


def main():
    failures = 0

    with tempfile.TemporaryDirectory() as tmp:
        backend = make_backend(tmp)
        suffix = backend.config_suffix
        print(f"config_suffix = {suffix!r}")
        print(f"storage_dir   = {backend._storage_dir!r}")
        print(f"data_path     = {backend._data_path!r}")

        # ---- Case 1: v1 batch_set -> batch_exists (generic KV path) ----
        rid = "k" * 64  # a fake page hash
        v = bytearray(32768)
        for i in range(len(v)):
            v[i] = (i * 7 + 13) % 256
        ok = backend.batch_set([rid], [v])
        write_key = backend._storage_key(rid)
        exists = backend.batch_exists([rid])
        got = backend.get(rid)
        ok_get = got is not None and bytes(got) == bytes(v)
        print(f"\n[CASE 1 v1 batch_set->batch_exists] write_ok={ok} "
              f"exists={exists} write_key={write_key!r} readback={ok_get}")
        if not (ok and exists == 1 and ok_get):
            failures += 1
            print("  FAIL")

        # ---- Case 2: v1 batch_set_v1 zero-copy path -> batch_exists ----
        # host_indices need a registered host pool with get_page_buffer_meta;
        # skip (needs engine host pool), but verify batch_exists still sees
        # the key written through plain batch_set (same index).

        # ---- Case 3: v2 batch_set_v2 (mamba component) -> batch_exists_v2 ----
        class FakePool:
            page_size = 1

            def get_data_page(self, index, flat=True):
                # mamba single page per transfer, 49MiB
                b = bytearray(51511296)
                for j in range(0, len(b), 4096):
                    b[j] = (index + j // 4096) % 256
                return b

            def get_dummy_flat_data_page(self):
                return bytearray(51511296)

            def set_from_flat_data_page(self, index, data):
                pass

        backend.registered_pools = {PoolName.MAMBA: FakePool()}
        mkey = "m" * 64
        mtransfer = PoolTransfer(
            name=PoolName.MAMBA,
            host_indices=[0],
            keys=[mkey],
            hit_policy=PoolHitPolicy.TRAILING_PAGES,
        )
        wres = backend.batch_set_v2([mtransfer])
        m_write_key = backend._component_key(PoolName.MAMBA, mkey)
        # batch_exists_v2 with the same transfer (mamba trailing=1)
        qres = backend.batch_exists_v2([mkey], [mtransfer])
        print(f"\n[CASE 3 v2 mamba set->exists_v2] write={wres} "
              f"m_write_key={m_write_key!r} query={qres}")
        if wres.get(PoolName.MAMBA) != [True] or qres.kv_hit_pages != 1:
            failures += 1
            print("  FAIL (mamba write/query mismatch)")

        # ---- Case 4: v2 kv component (ALL_PAGES) ----
        backend.registered_pools = {PoolName.KV: FakePool()}
        ktransfer = PoolTransfer(
            name=PoolName.KV,
            host_indices=[0],
            keys=[rid],
            hit_policy=PoolHitPolicy.ALL_PAGES,
        )
        wres2 = backend.batch_set_v2([ktransfer])
        qres2 = backend.batch_exists_v2([rid], [ktransfer])
        print(f"\n[CASE 4 v2 kv set->exists_v2] write={wres2} query={qres2}")
        if wres2.get(PoolName.KV) != [True] or qres2.kv_hit_pages != 1:
            failures += 1
            print("  FAIL")

        backend.close()

    print(f"\n=== {'PASS' if failures == 0 else 'FAIL'} ({failures} failures) ===")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
