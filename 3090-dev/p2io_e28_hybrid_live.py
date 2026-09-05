"""Definitive in-process live-path probe: REAL HybridCacheController with
MAMBA sidecar, reproducing the EXACT live shape:

  node19 (root child, 3 pages) -> node18 (61 pages) and node22 (6 pages),
  both children of node19 seeded from node19's last hash.

Three-way key comparison through the REAL _page_backup / _storage_hit_query:
  A. write-side MAMBA storage keys (batch_set_v2 _component_key)
  B. query-side MAMBA boundary check keys (_component_key(MAMBA, chain[i]))
  C. KV storage keys (_storage_key)

Then batch_exists_v2 with the live MAMBA PoolTransfer (TRAILING_PAGES,
keys=["__placeholder__"]) must NOT clamp the 9-page hit to 0.
"""
import hashlib
import os
import shutil
import struct
import sys
import tempfile
import threading
from array import array
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import torch

from sglang.srt.mem_cache.allocator import TokenToKVPoolAllocator
from sglang.srt.mem_cache.base_prefix_cache import InsertParams
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool, ReqToTokenPool
from sglang.srt.mem_cache.radix_cache import RadixKey
from sglang.srt.mem_cache.unified_cache.components import ComponentType
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache
from sglang.srt.mem_cache.pool_host import base
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
from sglang.srt.mem_cache.hicache_storage import (
    HiCacheStorageConfig,
    HiCacheStorageExtraInfo,
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


def _hash_page(data, prior_digest, has_prior):
    ctx = hashlib.sha256()
    if has_prior:
        ctx.update(prior_digest)
    if len(data) > 0:
        ctx.update(data)
    return ctx.digest()


def _oracle_ref_hash(tokens, prior_hex=None, page_size=PAGE_SIZE):
    data = b"".join(struct.pack("<I", t & 0xFFFFFFFF) for t in tokens)
    prior = bytes.fromhex(prior_hex) if prior_hex else None
    has_prior = prior is not None
    out = []
    for start in range(0, len(tokens), page_size):
        chunk = data[start * 4 : (start + page_size) * 4]
        d = _hash_page(chunk, prior, has_prior)
        prior = d
        has_prior = True
        out.append(d.hex())
    return out


def _oracle_get_native_hash(token_ids, prior_digest, page_size=None):
    if hasattr(token_ids, "raw_token_ids"):
        raw = token_ids.raw_token_ids()
    elif hasattr(token_ids, "token_ids"):
        raw = token_ids.token_ids
    else:
        raw = token_ids
    tokens = list(raw)
    prior_hex = prior_digest.hex() if prior_digest else None
    if page_size is None:
        return _oracle_ref_hash(tokens, prior_hex, page_size=len(tokens))[-1]
    return _oracle_ref_hash(tokens, prior_hex, page_size=page_size)


def main():
    tmpdir = tempfile.mkdtemp(prefix="p2io_e28_hybrid_live_")
    budget_patch = mock.patch.object(
        base.psutil,
        "virtual_memory",
        return_value=mock.Mock(
            available=base.HICACHE_HOST_MEMORY_RESERVE_BYTES + 64 * (1024**3)
        ),
    )
    budget_patch.start()

    import sglang.srt.mem_cache.utils as _utils

    _utils.get_native_hash = _oracle_get_native_hash

    from sglang.srt.runtime_context import get_parallel

    _override_cm = get_parallel().override(
        world_size=1,
        world_rank=0,
        tp_rank=0,
        tp_size=1,
        pp_rank=0,
        pp_size=1,
        tp_group=None,
    )
    _override_cm.__enter__()

    # --- tree with MAMBA component ---
    N = 1024
    cap = 4 * N + 64
    device_pool = MHATokenToKVPool(
        size=cap,
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

    req_pool = ReqToTokenPool(
        size=8, max_context_len=cap + 64, device="cpu", enable_memory_saver=False
    )
    allocator = TokenToKVPoolAllocator(
        size=cap, dtype=torch.float16, device="cpu", kvcache=device_pool, need_sort=False
    )
    params = CacheInitParams(
        disable=False,
        req_to_token_pool=req_pool,
        token_to_kv_pool_allocator=allocator,
        page_size=PAGE_SIZE,
        eviction_policy="lru",
        tree_components=(ComponentType.FULL, ComponentType.MAMBA),
    )
    cache = UnifiedRadixCache(params)
    cache.enable_storage = True
    cache.hicache_storage_pass_prefix_keys = True

    # Manually build the MAMBA controller (HybridCacheController) since the
    # pool assembler path is heavy. We exercise the same _storage_hit_query.
    from sglang.srt.mem_cache.hybrid_cache.hybrid_cache_controller import (
        HybridCacheController,
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
    controller = HybridCacheController(
        token_to_kv_pool_allocator=allocator,
        mem_pool_host=host_pool,
        page_size=PAGE_SIZE,
        tp_group=None,
        load_cache_event=threading.Event(),
        storage_backend=None,
        model_name="testmodel",
        storage_backend_extra_config={
            "storage_dir": tmpdir,
            "extent_size": "64Mi",
            "file_size": "512Mi",
            "max_size": "20G",
            "min_free_space": "10G",
        },
        host_memory_mode="cache",
    )
    # attach_storage_backend creates the backend; register MAMBA pool on it.
    controller.attach_storage_backend(
        "extent",
        HiCacheStorageConfig(
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
        ),
    )
    from sglang.srt.mem_cache.storage.backend_factory import StorageBackendFactory

    # Register the MAMBA host pool so batch_set_v2/batch_get_v2 can resolve it.
    controller.storage_backend.register_mem_host_pool_v2(mamba_pool, PoolName.MAMBA)
    cache.cache_controller = controller
    backend = controller.storage_backend

    # --- INSERT split shape (real radix tree) ---
    tok19 = [(i * 104729 + 7) % 100003 for i in range(3)]
    # node18 continuation (61 pages)
    tok18 = [((3 + i) * 7919 + 5) % 100003 for i in range(61)]
    # node22 continuation (6 pages) — DIFFERENT from node18
    tok22 = [((100000 - i) * 613 + 11) % 100003 for i in range(6)]

    def insert_tokens(toks):
        inds = allocator.alloc(len(toks))
        r = cache.insert(
            InsertParams(key=RadixKey(array("q", toks)), value=inds.to(torch.int64))
        )
        return r.last_device_node

    order = [tok19, tok22, tok18]
    node_ids = [insert_tokens(t) for t in order]
    n19, n22, n18 = node_ids
    node19 = cache.tree_core.node_by_id(n19)
    node22 = cache.tree_core.node_by_id(n22)
    node18 = cache.tree_core.node_by_id(n18)
    print(f"node19 pages={len(node19.hash_value)} last={node19.hash_value[-1][:16]}")
    print(f"node22 pages={len(node22.hash_value)} page0={node22.hash_value[0][:16]}")
    print(f"node18 pages={len(node18.hash_value)} page0={node18.hash_value[0][:16]}")

    # Fill host pools distinct so writes carry content
    for p in range(N * 2):
        if p < host_pool.kv_buffer.shape[1]:
            host_pool.kv_buffer[0, p] = float(p + 1)
            host_pool.kv_buffer[1, p] = float(p + 100)
        if p < mamba_pool.kv_buffer.shape[1]:
            mamba_pool.kv_buffer[0, p] = float(p + 1000)
            mamba_pool.kv_buffer[1, p] = float(p + 2000)

    # --- WRITE: _page_backup for all three nodes via real operation path ---
    from sglang.srt.managers.cache_controller import StorageOperation

    written_mamba = []
    written_kv = []

    def capturing_set_v2(transfers, extra_info=None):
        res = controller.storage_backend.batch_set_v2.__wrapped__(
            controller.storage_backend, transfers, extra_info
        ) if hasattr(controller.storage_backend.batch_set_v2, "__wrapped__") else None
        # capture via direct backend call
        for t in transfers:
            written_mamba.extend(
                [backend._component_key(t.name, k) for k in (t.keys or [])]
            )
        return res

    # We need to capture actual batch_set_v2. Since controller calls
    # storage_backend.batch_set_v2 directly, wrap it.
    real_set_v2 = backend.batch_set_v2

    def cap_set_v2(transfers, extra_info=None):
        res = real_set_v2(transfers, extra_info)
        for t in transfers:
            sk = [backend._component_key(t.name, k) for k in (t.keys or [])]
            if t.name == PoolName.MAMBA:
                written_mamba.extend(sk)
            elif t.name == PoolName.KV:
                written_kv.extend(sk)
        return res

    backend.batch_set_v2 = cap_set_v2

    def cap_set_v1(hashes, host_inds, extra_info=None):
        res = backend.batch_set_v1(hashes, host_inds, extra_info)
        written_kv.extend([backend._storage_key(k) for k in hashes])
        return res

    backend.batch_set_v1 = cap_set_v1

    real_page_set = controller.page_set_func
    def cap_page_set(hashes, host_inds, extra_info=None):
        r = real_page_set(hashes, host_inds, extra_info)
        return r
    controller.page_set_func = cap_page_set

    # Run the real _page_backup for each node with pool_transfers built the
    # live way (mamba_component BACKUP_STORAGE transfer).
    from sglang.srt.mem_cache.unified_cache.components.mamba_component import (
        MambaComponent,
    )

    for nid in (n19, n18, n22):
        node = cache.tree_core.node_by_id(nid)
        spec = cache.tree_core.build_storage_backup_spec(
            nid, cache.hicache_storage_pass_prefix_keys
        )
        # manifest the host_value like _execute_and_commit_kv_backup would
        node.component_data[ComponentType.MAMBA].host_value = torch.zeros(
            (1, PAGE_BYTES), dtype=torch.float16
        )
        spec2 = cache.tree_core.build_storage_backup_spec(
            nid, cache.hicache_storage_pass_prefix_keys
        )
        mamba_tf = spec2.comp_xfers[ComponentType.MAMBA]
        kv_xfer = PoolTransfer(
            name=PoolName.KV, host_indices=spec.host_value, keys=spec.hash_value
        )
        aux = [x for xs in spec2.comp_xfers.values() for x in xs] + \
            cache._build_sidecar_transfers(
                __import__("sglang.srt.mem_cache.hicache_storage", fromlist=["CacheTransferPhase"]).CacheTransferPhase.BACKUP_STORAGE,
                kv_xfer,
                spec2.comp_xfers,
            )
        op = StorageOperation(
            spec.host_value,
            spec.token_ids,
            hash_value=spec.hash_value,
            prefix_keys=spec.prefix_keys,
            pool_transfers=aux or None,
        )
        op.node_id = nid
        controller._page_backup(op)
        print(f"  wrote node {nid}: kv={len(spec.hash_value)} mamba_len={len(mamba_tf[0].keys or [])}")

    backend.batch_set_v2 = real_set_v2

    # --- QUERY: the live 9-page span through _storage_hit_query ---
    from sglang.srt.managers.cache_controller import PrefetchOperation

    # Query chain = node19(3) + node22(6), anchored after node19
    anchor = node22.parent  # node19
    anchor_prefix = anchor.get_prefix_hash_values(anchor.parent)
    last_hash = anchor.get_last_hash_value()
    new_input = tok22
    print(f"\nanchor last_hash={last_hash[:16]} new_input={len(new_input)}")

    mamba_tf = None
    # Build the query MAMBA transfer exactly as prefetch_from_storage does
    from sglang.srt.mem_cache.hicache_storage import CacheTransferPhase

    mamba_comp = cache.components[ComponentType.MAMBA]
    host_indices = torch.zeros((1, PAGE_SIZE), dtype=torch.int64)
    mamba_tf = mamba_comp.build_hicache_transfers(
        anchor, CacheTransferPhase.PREFETCH,
        host_indices=host_indices,
        prefetch_tokens=len(new_input),
        last_hash=last_hash,
        token_ids=new_input,
    )
    print(f"query mamba_tf keys={mamba_tf[0].keys} hit_policy={mamba_tf[0].hit_policy}")

    prefetch_op = PrefetchOperation(
        request_id="probe-hybrid-live",
        token_ids=new_input,
        last_hash=last_hash,
        prefix_keys=anchor_prefix,
        pool_transfers=mamba_tf,
    )
    hash_value, sqc = controller._storage_hit_query(prefetch_op)
    print(f"\n_storage_hit_query: hash_value={len(hash_value)} storage_query_count={sqc}")
    print(f"operation.pool_storage_result.kv_hit_pages={prefetch_op.pool_storage_result.kv_hit_pages}")

    # --- THREE-WAY KEYS COMPARE + MAMBA boundary ---
    print("\n=== KEYS COMPARE ===")
    kv_present = []
    with backend._lock:
        for k in hash_value:
            kv_present.append(backend._allocator.lookup(backend._storage_key(k)) is not None)
    print(f"KV present: {sum(kv_present)}/{len(hash_value)}")

    mamba_present = []
    with backend._lock:
        for k in hash_value:
            mamba_present.append(
                backend._allocator.lookup(backend._component_key(PoolName.MAMBA, k)) is not None
            )
    print(f"MAMBA present: {sum(mamba_present)}/{len(hash_value)}  positions={[i for i,b in enumerate(mamba_present) if b]}")

    print("\nVERDICT: kv_hit_pages>0 means hybrid MAMBA path does NOT clamp")

    try:
        controller._stop_storage_threads()
    except Exception:
        pass
    try:
        controller.storage_backend.close()
    except Exception:
        pass
    _override_cm.__exit__(None, None, None)
    budget_patch.stop()
    shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
