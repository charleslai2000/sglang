"""e7p: Mamba contract three-case verification (Task 2).

Deterministic backend-level harness (extent backend + batch_exists/_v2),
replicating the REAL write shape (mamba_component BACKUP_STORAGE writes ONE
key = node.hash_value[-1]) and the REAL all-or-nothing prefetch rule
(unified_radix_cache.py:2917-2960: a sidecar shortfall discards the whole
prefetch -> final_pages clamped to 0 -> revoke as full miss).

Node model: a FULL-KV radix node of N pages; mamba state checkpointed once
per node at the node's LAST page hash (node.hash_value[-1]), written as a
MAMBA-component key (key + ".mamba" + config_suffix).

Three cases:
  Case A  exact node boundary restore: R2 queries the FULL N-prefix.
          Expected: KV present N, mamba TRAILING boundary = N
          (last query page == node last == the mamba key) -> final=N
          -> restore OK (usable = N).
  Case B  partial prefix restore: R2 queries P < N (P ends mid-node).
          Expected: KV present P, mamba TRAILING boundary = 0
          (query last page != node last) -> final=0 -> all-or-nothing
          -> restore NOT OK (usable = 0; recompute fallback).
  Case C  KV-only (mamba component disabled): same partial P, no mamba
          transfer (batch_exists path).
          Expected: KV present P -> final=P -> restore OK (usable = P)
          -> isolates KV layer as healthy.

Also a Case A' split-node variant: query covers node19(3)+node22(6)=9
ending exactly at node22's last page (multi-node exact restore, the shape
of a session-resume full-history query) -> mamba boundary = 9.
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
    tmpdir = tempfile.mkdtemp(prefix="p2io_e7p_")
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
        N = 4096  # host pool capacity
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

        # ---- Model node: 2048-page FULL-KV node (live node size) ----
        NODE_PAGES = 2048
        tok_node = [(i * 104729 + 7) % 100003 for i in range(NODE_PAGES)]
        chain = chain_hash(tok_node)
        node_last = chain[-1]  # mamba key position = 2047

        # ---- WRITE KV for the node (real _page_backup batch_set_v1 path) ----
        def kv_write(keys, base_idx):
            for s in range(0, len(keys), 1024):
                batch = keys[s : s + 1024]
                hidx = torch.arange(
                    (base_idx + s) * ps, (base_idx + s + len(batch)) * ps,
                    dtype=torch.int64,
                )
                ok = backend.batch_set_v1(batch, hidx)
                assert all(ok), "kv write failed"

        kv_write(chain, 0)

        # ---- WRITE MAMBA exactly as live mamba_component BACKUP_STORAGE ----
        # one key = node.hash_value[-1]
        hidx = torch.arange(3000 * ps, (3000 + 1) * ps, dtype=torch.int64)
        res = backend.batch_set_v2(
            [
                PoolTransfer(
                    name=PoolName.MAMBA,
                    host_indices=hidx,
                    keys=[node_last],
                    hit_policy=PoolHitPolicy.TRAILING_PAGES,
                )
            ]
        )
        assert all(res[PoolName.MAMBA]), "mamba write failed"
        print(f"node={NODE_PAGES} pages, mamba key at chain[{NODE_PAGES-1}] "
              f"= {node_last[:16]}")

        def run_exists(chain_prefix, with_mamba):
            """Real backend query; returns (kv_pages, extra, usable)."""
            if with_mamba:
                r = backend.batch_exists_v2(
                    chain_prefix,
                    [
                        PoolTransfer(
                            name=PoolName.MAMBA,
                            host_indices=None,
                            keys=["__placeholder__"],
                            hit_policy=PoolHitPolicy.TRAILING_PAGES,
                        )
                    ],
                )
                extra = {
                    getattr(k, "value", k): v
                    for k, v in r.extra_pool_hit_pages.items()
                }
                kv_pages = r.kv_hit_pages
            else:
                r = backend.batch_exists(chain_prefix)
                kv_pages = r
                extra = {}
            # all-or-nothing rule (unified_radix_cache.py:2917): a mamba
            # sidecar present + boundary < full -> usable 0; no sidecar ->
            # usable = kv_pages.
            mamba_b = extra.get("mamba", 0)
            if with_mamba and mamba_b < len(chain_prefix):
                usable = 0
            else:
                usable = kv_pages
            return kv_pages, extra, usable

        def present_at(chain_prefix, comp):
            with backend._lock:
                keyf = (
                    backend._storage_key
                    if comp == "kv"
                    else lambda k: backend._component_key(PoolName.MAMBA, k)
                )
                return [
                    i
                    for i, k in enumerate(chain_prefix)
                    if backend._allocator.lookup(keyf(k)) is not None
                ]

        print()
        print("=================== CASE A: exact node boundary ===================")
        kv_a, extra_a, usable_a = run_exists(chain, with_mamba=True)
        print(f"  query full {NODE_PAGES} prefix: kv_pages={kv_a} "
              f"extra={extra_a} usable={usable_a}")
        print(f"  mamba present at: {present_at(chain, 'mamba')}")

        print()
        print("=================== CASE B: partial prefix (1892) =================")
        P = 1892
        chain_p = chain[:P]
        kv_b, extra_b, usable_b = run_exists(chain_p, with_mamba=True)
        mamba_pos = present_at(chain_p, "mamba")
        print(f"  query partial {P} prefix: kv_pages={kv_b} extra={extra_b} "
              f"usable={usable_b}")
        print(f"  mamba present in span: {mamba_pos} "
              f"(node-last at chain[{NODE_PAGES-1}] NOT in span)")

        print()
        print("=================== CASE C: KV-only (mamba disabled) ==============")
        kv_c, extra_c, usable_c = run_exists(chain_p, with_mamba=False)
        print(f"  query partial {P} prefix, no mamba transfer: kv_pages={kv_c} "
              f"extra={extra_c} usable={usable_c}")

        print()
        print("=================== CASE A': split-node exact restore ============")
        # node19(3) -> node22(6), query = full node19+node22 = 9 pages ending
        # at node22's last page (session-resume full-history shape)
        tok19 = [(i * 104729 + 7) % 100003 for i in range(3)]
        chain19 = chain_hash(tok19)
        last19 = chain19[-1]
        tok22 = [((100000 - i) * 613 + 11) % 100003 for i in range(6)]
        chain22 = chain_hash(tok22, prior_hex=last19)
        split_chain = chain19 + chain22
        kv_write(split_chain, 200)
        for name, last, idx in (("node19", last19, 3100), ("node22", chain22[-1], 3101)):
            hidx = torch.arange(idx * ps, (idx + 1) * ps, dtype=torch.int64)
            res = backend.batch_set_v2(
                [
                    PoolTransfer(
                        name=PoolName.MAMBA,
                        host_indices=hidx,
                        keys=[last],
                        hit_policy=PoolHitPolicy.TRAILING_PAGES,
                    )
                ]
            )
            assert all(res[PoolName.MAMBA]), f"{name} mamba write failed"
        kv_a2, extra_a2, usable_a2 = run_exists(split_chain, with_mamba=True)
        print(f"  query full node19(3)+node22(6)={len(split_chain)} prefix: "
              f"kv_pages={kv_a2} extra={extra_a2} usable={usable_a2}")
        print(f"  mamba present at: {present_at(split_chain, 'mamba')}")

        print()
        print("=================== SUMMARY ===================")
        print(f"CASE A  exact node boundary ({NODE_PAGES}):  usable={usable_a}")
        print(f"CASE B  partial prefix ({P}):                usable={usable_b}")
        print(f"CASE C  KV-only partial ({P}):               usable={usable_c}")
        print(f"CASE A' split-node exact (9):                usable={usable_a2}")

    finally:
        if backend is not None:
            backend.close()
        budget_patch.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
