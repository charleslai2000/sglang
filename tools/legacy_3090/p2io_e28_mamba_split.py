"""Reproduce the EXACT live split shape that kv_hit=0 with sidecar={'kv': 9}.

Live tree (t38c writes):
  node19: root child, 3 pages  -> KV written, MAMBA key = node19.hash_value[-1]
  node18: child of node19, seed=node19.last, 61 pages, page0=e4af379a
  node22: child of node19, seed=node19.last, 6 pages,  page0=3b1261d4
  Query follows node19(3) + node22(6) = chain[0..8]; KV scan finds 9 present.

Question: does the MAMBA trailing-pages boundary (written at node19.last and
node22.last) clamp final to 0, or align to 9?
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

PAGE_SIZE = 1
LAYER_NUM = 1
HEAD_NUM = 2
HEAD_DIM = 8
PAGE_BYTES = LAYER_NUM * PAGE_SIZE * HEAD_NUM * HEAD_DIM * 2  # fp16


def chain_hash(tokens, page_size=PAGE_SIZE, prior_hex=None):
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
    tmpdir = tempfile.mkdtemp(prefix="p2io_e28_mamba_split_")
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
        N = 1000
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
                "max_size": "20G",
                "min_free_space": "10G",
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
        backend = ExtentFileBackend(storage_config)
        backend.register_mem_pool_host(host_pool)
        backend.register_mem_host_pool_v2(host_pool, PoolName.KV)
        backend.register_mem_host_pool_v2(mamba_pool, PoolName.MAMBA)

        ps = PAGE_SIZE
        for p in range(N):
            host_pool.kv_buffer[0, p * ps : (p + 1) * ps] = float(p + 1)
            host_pool.kv_buffer[1, p * ps : (p + 1) * ps] = float(p + 100)
            mamba_pool.kv_buffer[0, p * ps : (p + 1) * ps] = float(p + 1000)
            mamba_pool.kv_buffer[1, p * ps : (p + 1) * ps] = float(p + 2000)

        # ---- Build the real split chain ----
        # node19: root child, 3 pages
        tok19 = [(i * 104729 + 7) % 100003 for i in range(3)]
        chain19 = chain_hash(tok19)
        last19 = chain19[-1]
        # node18: child of node19, 61 pages seeded from last19
        tok18 = [((3 + i) * 7919 + 5) % 100003 for i in range(61)]
        chain18 = chain_hash(tok18, prior_hex=last19)
        # node22: child of node19, 6 pages seeded from last19 (DIFFERENT continuation)
        tok22 = [((100000 - i) * 613 + 11) % 100003 for i in range(6)]
        chain22 = chain_hash(tok22, prior_hex=last19)

        print(f"node19 (3): last={last19[:16]}")
        print(f"node18 (61): page0={chain18[0][:16]} last={chain18[-1][:16]}")
        print(f"node22 (6):  page0={chain22[0][:16]} last={chain22[-1][:16]}")

        # Query chain = node19(3) + node22(6) = 9 pages, same as live kv_pages=9
        query_chain = chain19 + chain22
        print(f"query_chain len={len(query_chain)}")

        # ---- WRITE KV for all three nodes (live _page_backup) ----
        def kv_write(node_name, keys, base_idx):
            for s in range(0, len(keys), 1024):
                batch = keys[s : s + 1024]
                hidx = torch.arange(
                    (base_idx + s) * ps,
                    (base_idx + s + len(batch)) * ps,
                    dtype=torch.int64,
                )
                ok = backend.batch_set_v1(batch, hidx)
                assert all(ok), f"{node_name} kv write failed"

        kv_write("node19", chain19, 0)
        kv_write("node18", chain18, 10)
        kv_write("node22", chain22, 100)

        # ---- WRITE MAMBA exactly as live mamba_component (1 key = node last) ----
        def mamba_write(node_name, last_hash, base_idx):
            hidx = torch.arange(base_idx * ps, (base_idx + 1) * ps, dtype=torch.int64)
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
            assert all(res[PoolName.MAMBA]), f"{node_name} mamba write failed"

        mamba_write("node19", last19, 200)
        mamba_write("node18", chain18[-1], 201)
        mamba_write("node22", chain22[-1], 202)

        # ---- QUERY: batch_exists_v2 with live MAMBA transfer (placeholder) ----
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
        print(f"\nLIVE batch_exists_v2: kv_hit_pages={res.kv_hit_pages} "
              f"extra={ {getattr(k,'value',k):v for k,v in res.extra_pool_hit_pages.items()} }")

        # ---- Manual MAMBA trailing boundary (trailing=1) ----
        kv_pages = 9
        boundary = 0
        for prefix_len in range(kv_pages, 0, -1):
            if backend._allocator.lookup(
                backend._component_key(PoolName.MAMBA, query_chain[prefix_len - 1])
            ) is not None:
                boundary = prefix_len
                break
        print(f"manual MAMBA boundary (trailing=1): {boundary}")

        # which query chain positions are written MAMBA keys?
        print("\nwritten MAMBA keys present in query_chain:")
        for wm in (last19, chain18[-1], chain22[-1]):
            hits = [i for i, k in enumerate(query_chain) if k == wm]
            print(f"  {wm[:16]} at positions {hits}")

        # Control: batch_exists (KV-only)
        print(f"\nControl batch_exists (KV-only): {backend.batch_exists(query_chain)}")

    finally:
        if backend is not None:
            backend.close()
        budget_patch.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
