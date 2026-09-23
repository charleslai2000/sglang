"""Trace batch_exists_v2's MAMBA trailing boundary computation for the exact
live query chain (node19 3 pages + node22 6 pages) with the live transfer.
Determines the exact prefix_len that passes / fails.
"""
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


def chain_hash(tokens, page_size=1, prior_hex=None):
    prior = bytes.fromhex(prior_hex) if prior_hex else None
    has_prior = prior is not None
    data = b"".join(struct.pack("<I", t & 0xFFFFFFFF) for t in tokens)
    out = []
    for start in range(0, len(tokens), page_size):
        ctx = hashlib.sha256()
        if has_prior:
            ctx.update(prior)
        ctx.update(data[start * 4 : (start + page_size) * 4])
        d = ctx.digest()
        prior = d
        has_prior = True
        out.append(d.hex())
    return out


def main():
    tmpdir = tempfile.mkdtemp(prefix="p2io_e28_boundary_")
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
        N = 512
        device_pool = MHATokenToKVPool(
            size=N, page_size=1, dtype=torch.float16,
            head_num=2, head_dim=8, layer_num=1, device="cpu",
            enable_memory_saver=False,
        )
        host_pool = MHATokenToKVPoolHost(
            device_pool=device_pool, host_to_device_ratio=2.0, host_size=0,
            page_size=1, layout="page_first", pin_memory=False, device="cpu",
            allocator_type="default",
        )
        storage_config = HiCacheStorageConfig(
            extra_config={
                "storage_dir": tmpdir, "extent_size": "64Mi", "file_size": "512Mi",
                "max_size": "20G", "min_free_space": "10G",
            },
            tp_rank=0, tp_size=1, pp_rank=0, pp_size=1,
            attn_cp_rank=0, attn_cp_size=1, is_mla_model=False,
            enable_storage_metrics=False, is_page_first_layout=True,
            model_name="testmodel",
        )
        backend = ExtentFileBackend(storage_config)
        backend.register_mem_pool_host(host_pool)
        backend.register_mem_host_pool_v2(host_pool, PoolName.KV)
        backend.register_mem_host_pool_v2(host_pool, PoolName.MAMBA)
        for p in range(N):
            host_pool.kv_buffer[0, p] = float(p + 1)
            host_pool.kv_buffer[1, p] = float(p + 100)

        # live chain: node19 (3) + node22 (6)
        tok19 = [(i * 104729 + 7) % 100003 for i in range(3)]
        chain19 = chain_hash(tok19)
        last19 = chain19[-1]
        tok22 = [((100000 - i) * 613 + 11) % 100003 for i in range(6)]
        chain22 = chain_hash(tok22, prior_hex=last19)
        query_chain = chain19 + chain22

        # write KV + MAMBA for node19 and node22
        allkv = chain19 + chain22
        for s in range(0, len(allkv), 1024):
            batch = allkv[s : s + 1024]
            backend.batch_set_v1(batch, torch.arange(s, s + len(batch), dtype=torch.int64))
        for last_hash, idx in ((last19, 300), (chain22[-1], 301)):
            backend.batch_set_v2(
                [PoolTransfer(name=PoolName.MAMBA, host_indices=torch.tensor([idx], dtype=torch.int64),
                              keys=[last_hash], hit_policy=PoolHitPolicy.TRAILING_PAGES)]
            )

        # Now instrument the EXACT boundary computation with the live transfer
        transfer = PoolTransfer(
            name=PoolName.MAMBA,
            host_indices=None,
            keys=["__placeholder__"],
            hit_policy=PoolHitPolicy.TRAILING_PAGES,
        )
        kv_pages = 9
        trailing = max(1, len(transfer.keys) if transfer.keys else 1)
        print(f"trailing = {trailing} (len(keys)={len(transfer.keys) if transfer.keys else None})")
        for prefix_len in range(kv_pages, 0, -1):
            i = prefix_len - 1
            sk = backend._component_key(PoolName.MAMBA, query_chain[i])
            present = backend._allocator.lookup(sk) is not None
            if present:
                print(f"  prefix_len={prefix_len} chain[{i}]={query_chain[i][:16]} -> PRESENT -> boundary={prefix_len}")
                break
            print(f"  prefix_len={prefix_len} chain[{i}]={query_chain[i][:16]} -> absent")
        else:
            print("  boundary=0 (no present chain page)")

        # Now the LIVE result
        res = backend.batch_exists_v2(query_chain, [transfer])
        print(f"\nLIVE batch_exists_v2: kv_hit_pages={res.kv_hit_pages} extra={ {getattr(k,'value',k):v for k,v in res.extra_pool_hit_pages.items()} }")

        # CRITICAL: what if hit_policy were ALL_PAGES?
        transfer2 = PoolTransfer(
            name=PoolName.MAMBA,
            host_indices=None,
            keys=["__placeholder__"],
            hit_policy=PoolHitPolicy.ALL_PAGES,
        )
        res2 = backend.batch_exists_v2(query_chain, [transfer2])
        print(f"ALL_PAGES transfer: kv_hit_pages={res2.kv_hit_pages} extra={ {getattr(k,'value',k):v for k,v in res2.extra_pool_hit_pages.items()} }")

    finally:
        if backend is not None:
            backend.close()
        budget_patch.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
