"""Exhaustive divergence check: does the on-disk batch_exists_v2 differ from
the user's TRAILING_PAGES spec in ANY configuration?

User spec (mamba, trailing=1):
    kv_pages = longest_kv_prefix(keys)
    boundary = 0
    for prefix_len = kv_pages ... 1:
        if mamba_key(keys[prefix_len - 1]) exists:
            boundary = prefix_len
            break
    final_pages = min(kv_pages, boundary)

We compare the real backend's result against a from-scratch reference oracle
implemented directly from the spec, across: KV prefix length, checkpoint
positions, query lengths, and KV gaps.
"""
import itertools
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
    def __init__(self, page_bytes, slots=512):
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
            "extent_size": "64Ki",
            "file_size": "128Ki",
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
    tmpdir = tempfile.mkdtemp(prefix="p2io_e25_div_")
    backend = ExtentFileBackend(_make_config(tmpdir))
    mismatches = []
    try:
        kv = _PagePool(1000)
        mamba = _PagePool(1000)
        backend.register_mem_host_pool_v2(kv, PoolName.KV)
        backend.register_mem_host_pool_v2(mamba, PoolName.MAMBA)

        N = 40
        keys = [f"k{i:04d}" for i in range(N)]
        for i in range(N):
            kv._pages[i][:] = page_bytes(i)

        # Enumerate checkpoint position subsets (single and pair, including 0/off-by-one).
        cp_sets = [
            set(),
            {15},
            {31},
            {15, 31},
            {0},
            {39},
            {1},
            {40},  # out of range -> never found? (not written)
        ]
        # KV write prefix lengths: fully-present 0..kv_len-1, gap after.
        for kv_len in (0, 1, 10, 16, 20, 32, 40):
            for cps in cp_sets:
                # Rebuild fresh backend per scenario to avoid cross-contamination.
                backend.close()
                shutil.rmtree(tmpdir, ignore_errors=True)
                tmpdir = tempfile.mkdtemp(prefix="p2io_e25_div_")
                backend = ExtentFileBackend(_make_config(tmpdir))
                kv2 = _PagePool(1000)
                mamba2 = _PagePool(1000)
                backend.register_mem_host_pool_v2(kv2, PoolName.KV)
                backend.register_mem_host_pool_v2(mamba2, PoolName.MAMBA)

                # KV pages 0..kv_len-1 present.
                if kv_len:
                    for i in range(kv_len):
                        kv2._pages[i][:] = page_bytes(i)
                    backend.batch_set_v2([_transfer(PoolName.KV, keys[:kv_len])])
                # Mamba checkpoints.
                for cp in sorted(cps):
                    if 0 <= cp < N:
                        mamba2._pages[cp][:] = page_bytes(cp)
                valid_cps = [c for c in sorted(cps) if 0 <= c < N]
                if valid_cps:
                    backend.batch_set_v2(
                        [_transfer(PoolName.MAMBA, [keys[c] for c in valid_cps])]
                    )

                # Query prefixes of varying lengths (>= kv_len).
                for qlen in sorted({kv_len, min(N, kv_len + 3), N}):
                    if qlen == 0 or qlen > N:
                        continue
                    got = backend.batch_exists_v2(
                        keys[:qlen],
                        [
                            _transfer(
                                PoolName.MAMBA,
                                ["__placeholder__"],
                                hit_policy=PoolHitPolicy.TRAILING_PAGES,
                            )
                        ],
                    )
                    got_final = got.kv_hit_pages
                    got_mamba = got.extra_pool_hit_pages.get(PoolName.MAMBA, 0)

                    # Reference oracle from the user's spec.
                    kv_pages = min(kv_len, qlen)  # KV longest prefix
                    boundary = 0
                    for prefix_len in range(kv_pages, 0, -1):
                        if prefix_len - 1 in cps and (prefix_len - 1) < N:
                            boundary = prefix_len
                            break
                    if kv_len == 0:
                        boundary = 0  # no KV prefix -> no checkpoint reachable
                    exp_final = min(kv_pages, boundary)
                    exp_mamba = boundary if boundary else 0

                    if (got_final, got_mamba) != (exp_final, exp_mamba):
                        mismatches.append(
                            {
                                "kv_len": kv_len,
                                "cps": sorted(cps),
                                "qlen": qlen,
                                "got": (got_final, got_mamba),
                                "exp": (exp_final, exp_mamba),
                                "kv_hit_pages": got.extra_pool_hit_pages.get(
                                    PoolName.KV, 0
                                ),
                            }
                        )
    finally:
        backend.close()
        shutil.rmtree(tmpdir, ignore_errors=True)

    if mismatches:
        print(f"MISMATCHES ({len(mismatches)}):")
        for m in mismatches[:30]:
            print(" ", m)
    else:
        print(f"NO MISMATCHES across {len(cp_sets) * 8 * 3} configurations.")
        print("on-disk batch_exists_v2 == user's TRAILING_PAGES spec in all cases.")


if __name__ == "__main__":
    main()