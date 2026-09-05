"""Live-shape regression probe: node65 wrote 2048 KV pages + a Mamba
checkpoint at its write-time last page (node.hash_value[-1]), then a query
for a longer chain (query_suffix_len=11427) asks: what is storage_hit?

This reproduces the exact live configuration so we can see whether the
current batch_exists_v2 delivers storage_hit > 0 (the user's live-shape
acceptance) or clamps to 0.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

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
    def __init__(self, page_bytes, slots=4096):
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
            "extent_size": "64Mi",
            "file_size": "512Mi",
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
    tmpdir = tempfile.mkdtemp(prefix="p2io_e25_live_")
    backend = ExtentFileBackend(_make_config(tmpdir))
    try:
        kv = _PagePool(1000)
        mamba = _PagePool(1000)
        backend.register_mem_host_pool_v2(kv, PoolName.KV)
        backend.register_mem_host_pool_v2(mamba, PoolName.MAMBA)

        n = 2048
        keys = [f"k{i:04d}" for i in range(n)]
        for i in range(n):
            kv._pages[i][:] = page_bytes(i)
        r = backend.batch_set_v2([_transfer(PoolName.KV, keys)])
        assert r[PoolName.KV] == [True] * n, "KV write failed"
        # Mamba checkpoint at the node's write-time last page (hash_value[-1]).
        mamba._pages[n - 1][:] = page_bytes(n - 1)
        r = backend.batch_set_v2(
            [_transfer(PoolName.MAMBA, [keys[n - 1]])]
        )
        assert r[PoolName.MAMBA] == [True], "mamba write failed"

        # Query chain of 11427 pages sharing the same 2048 prefix (live shape).
        qlen = 11427
        qkeys = [f"k{i % n:04d}" for i in range(qlen)]  # wraps: suffix differs
        # NOTE: to be faithful, the query prefix must be the written 2048 pages.
        qkeys = list(keys) + [f"q{i:04d}" for i in range(qlen - n)]

        res = backend.batch_exists_v2(
            qkeys,
            [
                _transfer(
                    PoolName.MAMBA,
                    ["__placeholder__"],
                    hit_policy=PoolHitPolicy.TRAILING_PAGES,
                )
            ],
        )
        print("kv_pages(prefix present)=", res.extra_pool_hit_pages.get(PoolName.KV, 0))
        print("storage_hit(final_pages)=", res.kv_hit_pages)
        print("mamba boundary=", res.extra_pool_hit_pages.get(PoolName.MAMBA, 0))
        print("=> live shape storage_hit > 0:", res.kv_hit_pages > 0)
    finally:
        backend.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
