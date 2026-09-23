"""Trace the WRITE-side MAMBA key construction: does batch_set_v2 get
keys=[node.hash_value[-1]] with host_indices=cd.host_value where len==1*1?
And does _page_backup's MAMBA write actually reach batch_set_v2?

The critical question: node19 (3 pages) writes MAMBA key = node19.hash_value[-1]
= chain[2]. If that key is committed, boundary=9. Live says boundary=0.
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
from sglang.srt.mem_cache.pool_host.mamba import MambaPoolHost
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
    tmpdir = tempfile.mkdtemp(prefix="p2io_e28_mamba_writepath_")
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
        # A minimal fake mamba device pool is too complex; instead test the
        # KEY LOGIC directly: write a MAMBA key via batch_set_v2 and check it.
        from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool

        N = 512
        device_pool = MHATokenToKVPool(
            size=N, page_size=1, dtype=torch.float16,
            head_num=2, head_dim=8, layer_num=1, device="cpu",
            enable_memory_saver=False,
        )
        host_pool = __import__(
            "sglang.srt.mem_cache.pool_host.mha", fromlist=["MHATokenToKVPoolHost"]
        ).MHATokenToKVPoolHost(
            device_pool=device_pool, host_to_device_ratio=2.0, host_size=0,
            page_size=1, layout="page_first", pin_memory=False, device="cpu",
            allocator_type="default",
        )
        storage_config = HiCacheStorageConfig(
            extra_config={
                "storage_dir": tmpdir,
                "extent_size": "64Mi",
                "file_size": "512Mi",
                "max_size": "20G",
                "min_free_space": "10G",
            },
            tp_rank=0, tp_size=1, pp_rank=0, pp_size=1,
            attn_cp_rank=0, attn_cp_size=1, is_mla_model=False,
            enable_storage_metrics=False, is_page_first_layout=True,
            model_name="testmodel",
        )
        backend = ExtentFileBackend(storage_config)
        backend.register_mem_pool_host(host_pool)
        backend.register_mem_host_pool_v2(host_pool, PoolName.KV)
        # Use the same host pool as the MAMBA pool (size matches 1*1).
        backend.register_mem_host_pool_v2(host_pool, PoolName.MAMBA)

        for p in range(N):
            host_pool.kv_buffer[0, p] = float(p + 1)
            host_pool.kv_buffer[1, p] = float(p + 100)

        # Build the live chain: node19 (3), node22 (6) both children of node19
        tok19 = [(i * 104729 + 7) % 100003 for i in range(3)]
        chain19 = chain_hash(tok19)
        last19 = chain19[-1]
        tok22 = [((100000 - i) * 613 + 11) % 100003 for i in range(6)]
        chain22 = chain_hash(tok22, prior_hex=last19)
        query_chain = chain19 + chain22

        # WRITE KV (both nodes)
        allkv = chain19 + chain22
        for s in range(0, len(allkv), 1024):
            batch = allkv[s : s + 1024]
            hidx = torch.arange(s, s + len(batch), dtype=torch.int64)
            ok = backend.batch_set_v1(batch, hidx)
            assert all(ok)

        # WRITE MAMBA exactly as live (node19, then node22)
        for last_hash, idx in ((last19, 300), (chain22[-1], 301)):
            hidx = torch.tensor([idx], dtype=torch.int64)
            res = backend.batch_set_v2(
                [
                    PoolTransfer(
                        name=PoolName.MAMBA,
                        host_indices=hidx,
                        keys=[last_hash],
                        hit_policy=PoolHitPolicy.TRAILING_PAGES,
                    )
                ]
            )
            print(f"mamba write key={last_hash[:16]} host_indices={hidx.tolist()} "
                  f"-> ok={res[PoolName.MAMBA]}")
            sk = backend._component_key(PoolName.MAMBA, last_hash)
            with backend._lock:
                print(f"  _component_key={sk[:20]}... present={backend._allocator.lookup(sk) is not None}")

        # QUERY with live transfer
        res = backend.batch_exists_v2(
            query_chain,
            [
                PoolTransfer(
                    name=PoolName.MAMBA,
                    host_indices=None,
                    keys=["__placeholder__"],
                    hit_policy=PoolHitPolicy.TRAILING_PAGES,
                )
            ],
        )
        print(f"\nbatch_exists_v2: kv_hit_pages={res.kv_hit_pages} "
              f"extra={ {getattr(k,'value',k):v for k,v in res.extra_pool_hit_pages.items()} }")
        print(f"VERDICT: {'clamps to 0' if res.kv_hit_pages == 0 else 'aligns'}")

    finally:
        if backend is not None:
            backend.close()
        budget_patch.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
