"""Test the bare-key-mamba-check hypothesis: if the live-time batch_exists_v2
checked the mamba boundary with the BARE storage key (not the .MAMBA-suffixed
_component_key) while the write side stored .MAMBA-suffixed keys, every hybrid
query's mamba boundary is 0 -> kv_hit=0 with sidecar {'kv':N} only -- the exact
live signature. Reproduce this in-process and show the contrast with the
correct _component_key check."""
import hashlib
import os
import shutil
import struct
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import torch

from sglang.srt.mem_cache.pool_host import base
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool
from sglang.srt.mem_cache.hicache_storage import (
    HiCacheStorageConfig,
    PoolName,
    PoolTransfer,
    PoolHitPolicy,
)
from sglang.srt.mem_cache.storage.extent.extent_file_backend import (
    ExtentFileBackend,
)

PAGE_SIZE = 1
LAYER_NUM = 1
HEAD_NUM = 2
HEAD_DIM = 8


def chain_hash(tokens, page_size=PAGE_SIZE):
    prior = None
    out = []
    data = b"".join(struct.pack("<I", t & 0xFFFFFFFF) for t in tokens)
    for start in range(0, len(tokens), page_size):
        ctx = hashlib.sha256()
        if prior is not None:
            ctx.update(prior)
        ctx.update(data[start * 4 : (start + page_size) * 4])
        d = ctx.digest()
        prior = d
        out.append(d.hex())
    return out


def main():
    tmpdir = tempfile.mkdtemp(prefix="p2io_e28_barekey_")
    budget_patch = mock.patch.object(
        base.psutil,
        "virtual_memory",
        return_value=mock.Mock(
            available=base.HICACHE_HOST_MEMORY_RESERVE_BYTES + 64 * (1024**3)
        ),
    )
    budget_patch.start()
    backend = None
    try:
        N = 9  # the live HEAD9 shape: kv_pages=9, node19=3 pages, node22=6 pages
        device_pool = MHATokenToKVPool(
            size=N * PAGE_SIZE,
            page_size=PAGE_SIZE,
            dtype=torch.float16,
            head_num=HEAD_NUM,
            head_dim=HEAD_DIM,
            layer_num=LAYER_NUM,
            device="cpu",
            enable_memory_saver=False,
        )
        host_pool = MHATokenToKVPoolHost(
            device_pool=device_pool,
            host_to_device_ratio=2.0,
            host_size=0,
            page_size=PAGE_SIZE,
            layout="page_first",
            pin_memory=False,
            device="cpu",
            allocator_type="default",
        )
        mamba_pool = MHATokenToKVPoolHost(
            device_pool=device_pool,
            host_to_device_ratio=2.0,
            host_size=0,
            page_size=PAGE_SIZE,
            layout="page_first",
            pin_memory=False,
            device="cpu",
            allocator_type="default",
        )
        storage_config = HiCacheStorageConfig(
            extra_config={
                "storage_dir": tmpdir,
                "extent_size": "64Mi",
                "file_size": "512Mi",
            },
            tp_rank=0, tp_size=1, pp_rank=0, pp_size=1,
            attn_cp_rank=0, attn_cp_size=1,
            is_mla_model=False, enable_storage_metrics=False,
            is_page_first_layout=True, model_name="testmodel",
        )
        backend = ExtentFileBackend(storage_config)
        backend.register_mem_pool_host(host_pool)
        backend.register_mem_host_pool_v2(host_pool, PoolName.KV)
        backend.register_mem_host_pool_v2(mamba_pool, PoolName.MAMBA)

        for p in range(N):
            host_pool.kv_buffer[0, p] = float(p + 1)
            host_pool.kv_buffer[1, p] = float(p + 100)
            mamba_pool.kv_buffer[0, p] = float(p + 1000)
            mamba_pool.kv_buffer[1, p] = float(p + 2000)

        # Live node sizes: node19=3 pages, node22=6 pages (seed=node19.last)
        node_sizes = [3, 6]
        tokens = [(i * 104729 + 7) % 100003 for i in range(N)]
        chain = chain_hash(tokens)
        cursor = 0
        for ns in node_sizes:
            slice_keys = chain[cursor : cursor + ns]
            hidx = torch.arange(cursor, cursor + len(slice_keys), dtype=torch.int64)
            backend.batch_set_v1(slice_keys, hidx)  # KV commit
            # MAMBA write: node-last page, .MAMBA-suffixed via batch_set_v2
            node_last = chain[cursor + ns - 1]
            mamba_hidx = torch.arange(cursor + ns - 1, cursor + ns, dtype=torch.int64)
            backend.batch_set_v2(
                [
                    PoolTransfer(
                        name=PoolName.MAMBA,
                        host_indices=mamba_hidx,
                        keys=[node_last],
                        hit_policy=PoolHitPolicy.TRAILING_PAGES,
                    )
                ]
            )
            cursor += ns

        print(f"chain len={len(chain)}")
        print(f"node19 last (chain[2])={chain[2][:8]} written as mamba: "
              f"{backend._allocator.lookup(backend._component_key(PoolName.MAMBA, chain[2])) is not None}")
        print(f"node22 last (chain[8])={chain[8][:8]} written as mamba: "
              f"{backend._allocator.lookup(backend._component_key(PoolName.MAMBA, chain[8])) is not None}")

        # ---- HYPOTHESIS: live backend checked the mamba boundary with BARE key ----
        def barekey_exists(keys, pool_transfers, extra_info=None):
            """Clone of batch_exists_v2 but the mamba check uses _storage_key
            (bare) instead of _component_key (MAMBA-suffixed)."""
            with backend._lock:
                def present(key):
                    return backend._allocator.lookup(key) is not None
                kv_pages = next(
                    (i for i in range(len(keys)) if not present(backend._storage_key(keys[i]))),
                    len(keys),
                )
                hit_count = {PoolName.KV: kv_pages} if kv_pages else {}
                final_pages = kv_pages
                for transfer in pool_transfers or []:
                    if final_pages == 0:
                        break
                    name = transfer.name
                    if transfer.hit_policy == PoolHitPolicy.ALL_PAGES:
                        boundary = next(
                            (i for i in range(kv_pages)
                             if not present(backend._storage_key(keys[i]))),
                            kv_pages,
                        )
                    else:
                        trailing = max(1, len(transfer.keys) if transfer.keys else 1)
                        boundary = 0
                        for prefix_len in range(kv_pages, 0, -1):
                            if all(
                                present(backend._storage_key(keys[i]))
                                for i in range(max(0, prefix_len - trailing), prefix_len)
                            ):
                                boundary = prefix_len
                                break
                    if boundary:
                        hit_count[name] = boundary
                    final_pages = min(final_pages, boundary)
            return PoolTransferResultProxy(final_pages, hit_count)

        class PoolTransferResultProxy:
            def __init__(self, kv, extra):
                self.kv_hit_pages = kv
                self.extra_pool_hit_pages = extra

        mamba_xfer = [
            PoolTransfer(
                name=PoolName.MAMBA,
                host_indices=None,
                keys=["__placeholder__"],
                hit_policy=PoolHitPolicy.TRAILING_PAGES,
            )
        ]
        r_bare = barekey_exists(chain, mamba_xfer)
        mamba_v = r_bare.extra_pool_hit_pages.get(PoolName.MAMBA, 0)
        print(
            f"\nHYPOTHESIS (bare-key mamba check, TRAILING placeholder): "
            f"kv_hit={r_bare.kv_hit_pages} extra="
            f"{{'kv':{r_bare.extra_pool_hit_pages.get(PoolName.KV, 0)}, "
            f"'mamba':{mamba_v}}}"
        )

        # ---- CORRECT behavior (current code): _component_key mamba check ----
        r_correct = backend.batch_exists_v2(chain, mamba_xfer)
        print(f"CORRECT (_component_key mamba check, TRAILING placeholder): "
              f"kv_hit={r_correct.kv_hit_pages} extra={ {getattr(k,'value',k):v for k,v in r_correct.extra_pool_hit_pages.items()} }")

        # ---- live log signature ----
        print(f"\nLIVE LOG signature: kv_hit=0, sidecar={{'kv':9}} (mamba absent)")
        print(f"BARE-KEY hypothesis matches live: {r_bare.kv_hit_pages == 0 and PoolName.MAMBA not in r_bare.extra_pool_hit_pages and r_bare.extra_pool_hit_pages.get(PoolName.KV) == 9}")

    finally:
        if backend is not None:
            backend.close()
        budget_patch.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
