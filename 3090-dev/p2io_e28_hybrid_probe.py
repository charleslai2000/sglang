"""e28-focused probe: reproduce the LIVE hybrid (KV+MAMBA) batch_exists_v2
write/query key pattern to test whether the MAMBA trailing-pages boundary
clamps kv_hit_pages to 0 even when all KV keys are present.

Live write (BACKUP_STORAGE, mamba_component.py:752-763):
  MAMBA transfer keys = [node.hash_value[-1]]  (ONE key per node)
  batch_set_v2 stores _component_key(MAMBA, node.hash_value[-1])

Live query (PREFETCH, mamba_component.py:765-774):
  MAMBA transfer keys = ["__placeholder__"] (later None from kv_xfer)
  batch_exists_v2: kv_pages from KV-only lookups, then
    trailing = len(transfer.keys) or 1
    boundary over _component_key(MAMBA, keys[prefix_len-1])
    final = min(kv_pages, boundary)
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


def chain_hash(tokens, page_size=PAGE_SIZE):
    """Position-sensitive SHA256 chain (oracle)."""
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
    tmpdir = tempfile.mkdtemp(prefix="p2io_e28_hybrid_")
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
        N = 20910
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

        # ---- build the full 20910-page KV chain ----
        tokens = [(i * 104729 + 7) % 100003 for i in range(N)]
        chain = chain_hash(tokens)
        print(f"chain len={len(chain)}")

        # ---- WRITE the KV chain in 1024-batches (live _page_backup) ----
        # Simulates node writes tiling the document. Each node's KV is a slice
        # of the chain. Live nodes have n_pages in {3, 61, 2039, 2048, ...}.
        node_sizes = [3, 61, 6, 2039] + [2048] * 9  # tiles ~20910 pages
        written_kv = 0
        written_mamba_keys = set()
        kv_keys_all = []
        cursor = 0
        node_hashes = []
        for ns in node_sizes:
            if cursor + ns > N:
                ns = N - cursor
            slice_keys = chain[cursor : cursor + ns]
            # KV write in 1024-batches (live batch_set_v1 split)
            for s in range(0, len(slice_keys), 1024):
                batch = slice_keys[s : s + 1024]
                hidx = torch.arange(
                    (cursor + s) * ps,
                    (cursor + s + len(batch)) * ps,
                    dtype=torch.int64,
                )
                backend.batch_set_v1(batch, hidx)
                kv_keys_all.extend(batch)
                written_kv += len(batch)
            # MAMBA write: ONE key per node = node's last page hash
            node_last = chain[cursor + ns - 1]
            node_hashes.append((cursor, cursor + ns, node_last))
            mamba_hidx = torch.arange(
                (cursor + ns - 1) * ps, (cursor + ns) * ps, dtype=torch.int64
            )
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
            written_mamba_keys.add(node_last)
            cursor += ns
            if cursor >= N:
                break
        print(f"written KV keys: {written_kv}, MAMBA keys: {len(written_mamba_keys)}")
        for c0, c1, last in node_hashes:
            print(f"  node pages [{c0},{c1}) last8={last[:8]}")

        # ---- QUERY: the full 20910-page chain from root (live batch_exists_v2) ----
        # Live query MAMBA transfer: keys=["__placeholder__"] -> trailing=1
        def kv_only_hits():
            with backend._lock:
                present = [
                    backend._allocator.lookup(backend._storage_key(k)) is not None
                    for k in chain
                ]
            return next(
                (i for i, p in enumerate(present) if not p), len(chain)
            )

        kv_pages = kv_only_hits()
        print(f"\nKV-only first-missing index: {kv_pages}/{len(chain)}")

        # Reproduce batch_exists_v2 MAMBA trailing boundary (trailing=1):
        boundary = 0
        for prefix_len in range(kv_pages, 0, -1):
            if backend._allocator.lookup(
                backend._component_key(PoolName.MAMBA, chain[prefix_len - 1])
            ) is not None:
                boundary = prefix_len
                break
        print(f"MAMBA trailing boundary (trailing=1): {boundary}")
        print(f"batch_exists_v2 final kv_hit_pages = min({kv_pages},{boundary}) = {min(kv_pages, boundary)}")

        # Also reproduce exactly as live calls it:
        res = backend.batch_exists_v2(
            chain,
            [
                PoolTransfer(
                    name=PoolName.MAMBA,
                    host_indices=None,
                    keys=["__placeholder__"],
                    hit_policy=PoolHitPolicy.TRAILING_PAGES,
                )
            ],
        )
        print(f"\nLIVE batch_exists_v2 result: kv_hit_pages={res.kv_hit_pages} "
              f"extra={ {getattr(k,'value',k):v for k,v in res.extra_pool_hit_pages.items()} }")

        # Diagnostic: at which query boundary does the written MAMBA key sit?
        # The query checks chain[prefix_len-1]; written MAMBA keys are at node
        # last pages. Show the largest prefix_len where chain[prefix_len-1]
        # is a written MAMBA key.
        max_aligned = 0
        for prefix_len in range(kv_pages, 0, -1):
            if chain[prefix_len - 1] in written_mamba_keys:
                max_aligned = prefix_len
                break
        print(f"\nLargest query prefix whose last page is a written MAMBA key: {max_aligned} "
              f"(= last written node boundary page index + 1)")
        print(f"VERDICT: {'MAMBA TRAILING BOUNDARY CLAMPS HIT TO 0' if boundary == 0 else 'MAMBA boundary aligns; KV-only path is the issue'}")

        # ---- Control: batch_exists (KV-only, no v2 clamp) ----
        kv_ctrl = backend.batch_exists(chain)
        print(f"\nControl batch_exists (KV-only): {kv_ctrl}")

    finally:
        if backend is not None:
            backend.close()
        budget_patch.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
