"""Empirically test the user's three narrow TRAILING_PAGES cases against the
current on-disk batch_exists_v2.

User spec:
  KV pages 0..31 all exist; Mamba checkpoints at page 15 and 31
  query 0..20 -> kv_hit=21 -> boundary=16 -> final_hit=16
  query 0..31 -> final_hit=32
  query 0..10 -> no checkpoint <= 10 -> final_hit=0

This probe drives the REAL ExtentFileBackend (bytearray pages) exactly like the
unit-test base, to determine the actual current behavior before any code change.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "python")
)

from sglang.srt.mem_cache.hicache_storage import (
    HiCacheStorageConfig,
    PoolHitPolicy,
    PoolName,
    PoolTransfer,
)
from sglang.srt.mem_cache.storage.extent.extent_file_backend import (
    ExtentFileBackend,
)


class _PagePool:
    """Minimal host pool: bytearray pages, page_size=1 (torch-free)."""

    def __init__(self, page_bytes, slots=1024):
        self.page_size = 1
        self._page_bytes = page_bytes
        self._pages = [bytearray(page_bytes) for _ in range(slots)]

    def get_data_page(self, index, flat=True):
        return self._pages[index]

    def get_dummy_flat_data_page(self):
        return bytearray(self._page_bytes)

    def set_from_flat_data_page(self, index, data_page):
        self._pages[index][:] = data_page


def _make_config(tmpdir):
    return HiCacheStorageConfig(
        extra_config={
            "storage_dir": tmpdir,
            "extent_size": "16Ki",
            "file_size": "64Ki",
        },
        tp_rank=0,
        tp_size=1,
        pp_rank=0,
        pp_size=1,
        attn_cp_rank=0,
        attn_cp_size=1,
        is_mla_model=False,
        enable_storage_metrics=False,
        is_page_first_layout=True,
        model_name="testmodel",
    )


def _transfer(name, keys, indices=None, hit_policy=None):
    return PoolTransfer(
        name=name,
        host_indices=indices if indices is not None else list(range(len(keys))),
        keys=list(keys),
        hit_policy=hit_policy,
    )


def page_bytes(i, page_bytes=1000):
    return bytearray(bytes([i % 251]) * page_bytes)


def main():
    tmpdir = tempfile.mkdtemp(prefix="p2io_e25_")
    backend = ExtentFileBackend(_make_config(tmpdir))
    try:
        kv = _PagePool(1000)
        mamba = _PagePool(1000)
        backend.register_mem_host_pool_v2(kv, PoolName.KV)
        backend.register_mem_host_pool_v2(mamba, PoolName.MAMBA)

        keys = [f"k{i:04d}" for i in range(32)]
        # KV pages 0..31 all present.
        for i in range(32):
            kv._pages[i][:] = page_bytes(i)
        r = backend.batch_set_v2([_transfer(PoolName.KV, keys)])
        assert r[PoolName.KV] == [True] * 32, r
        # Mamba checkpoints at page 15 and 31.
        for i in (15, 31):
            mamba._pages[i][:] = page_bytes(i)
        r = backend.batch_set_v2(
            [_transfer(PoolName.MAMBA, [keys[15], keys[31]])]
        )
        assert r[PoolName.MAMBA] == [True] * 2, r

        def query(hi):
            res = backend.batch_exists_v2(
                keys[:hi],
                [
                    _transfer(
                        PoolName.MAMBA,
                        ["__placeholder__"],
                        hit_policy=PoolHitPolicy.TRAILING_PAGES,
                    )
                ],
            )
            return res.kv_hit_pages, dict(res.extra_pool_hit_pages)

        q20 = query(21)
        q31 = query(32)
        q10 = query(11)
        print("query 0..20 ->", q20, "(expect kv_hit=16, mamba=16)")
        print("query 0..31 ->", q31, "(expect kv_hit=32, mamba=32)")
        print("query 0..10 ->", q10, "(expect kv_hit=0, no mamba)")
    finally:
        backend.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
