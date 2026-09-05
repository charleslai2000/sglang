"""e28 in-process live-path probe: three-way storage-keys comparison.

Reproduces the LIVE wiring (real UnifiedRadixCache -> CacheController
page_set_func=_page_set_zero_copy -> batch_set_v1, and page_get_func /
_storage_hit_query -> batch_exists) entirely in-process on CPU, then compares
three key sets page-by-page:

  A. spec.hash_value            -- what build_storage_backup_spec says we will write
  B. batch_set_v1 committed keys-- what batch_set_v1 actually committed
  C. query-side rebuilt keys    -- what batch_exists scans on the read side

Branch verdicts (coordinator e7n):
  - A != B -> spec/commit mismatch (spec chain not really committed)
  - B != C -> _v1_buffer_meta blocks-split construct (batch_set_v1 mis-keys)
  - A==B==C but batch_exists still misses -> allocator instance/state
    (e24/e26 proved backend passes in isolation; check live instance replace)
  - all pass -> upstream node/prefix construction is the only layer left

The tree inserts a 2048-page node (with a radix split / prefix-sharing shape
first so the chain spans a split), then the same 2048-page logical prefix is
backed up via CacheController._page_backup (write side) and queried via
CacheController._storage_hit_query (query side).
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
from sglang.srt.mem_cache.base_prefix_cache import InsertParams, MatchPrefixParams
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
    tmpdir = tempfile.mkdtemp(prefix="p2io_e28_live_")
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

    # Force the parallel context values so the real CacheController methods
    # (which call get_parallel().tp_rank etc. in _generate_storage_config) run
    # in-process without a distributed runtime.
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

    N = 2048
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
        tree_components=(ComponentType.FULL,),
    )
    cache = UnifiedRadixCache(params)
    cache.enable_storage = True
    cache.hicache_storage_pass_prefix_keys = True

    from sglang.srt.mem_cache.storage.backend_factory import StorageBackendFactory

    storage_config = HiCacheStorageConfig(
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
    # The controller creates its own backend in __init__ (attach_storage_backend);
    # we do not create a separate one, so the captured write/query go through
    # the single live backend instance.
    print(f"storage config tp_rank={storage_config.tp_rank} "
          f"tp_size={storage_config.tp_size}")

    # ---- INSERT: a 2048-page node with a split / prefix-sharing shape ----
    g_toks = [(i * 104729 + 7) % 100003 for i in range(N)]
    alt = g_toks[:300] + [((i * 7919 + 3) % 100003) for i in range(N)]
    inds = allocator.alloc(len(alt))
    cache.insert(
        InsertParams(key=RadixKey(array("q", alt)), value=inds.to(torch.int64))
    )
    inds = allocator.alloc(N)
    node_id = cache.insert(
        InsertParams(key=RadixKey(array("q", g_toks)), value=inds.to(torch.int64))
    ).last_device_node
    node = cache.tree_core.node_by_id(node_id)
    print(f"inserted node_id={node.id} pages={len(node.hash_value)}")

    # ---- WRITE SIDE: build_storage_backup_spec ----
    node.component_data[ComponentType.FULL].host_value = torch.zeros(
        (N, PAGE_BYTES), dtype=torch.float16
    )
    spec = cache.tree_core.build_storage_backup_spec(
        node_id, cache.hicache_storage_pass_prefix_keys
    )
    spec_hash = spec.hash_value
    spec_prefix = spec.prefix_keys
    print(f"spec.hash_value len={len(spec_hash)}")
    print(f"spec.prefix_keys len={len(spec_prefix) if spec_prefix else 0}")

    # Fill host pool distinct bytes per page so the v1 blocks carry content.
    for p in range(N):
        host_pool.kv_buffer[0, p * PAGE_SIZE : (p + 1) * PAGE_SIZE] = float(p + 1)
        host_pool.kv_buffer[1, p * PAGE_SIZE : (p + 1) * PAGE_SIZE] = float(p + 100)

    # ---- LIVE CacheController._page_backup (the write side) ----
    from sglang.srt.managers.cache_controller import HiCacheController, StorageOperation

    controller = HiCacheController(
        token_to_kv_pool_allocator=allocator,
        mem_pool_host=host_pool,
        page_size=PAGE_SIZE,
        tp_group=None,
        load_cache_event=threading.Event(),
        storage_backend="extent",
        model_name="testmodel",
        storage_backend_extra_config={
            "storage_dir": tmpdir,
            "extent_size": "64Mi",
            "file_size": "512Mi",
        },
        host_memory_mode="cache",
    )
    cache.cache_controller = controller

    # Capture what batch_set_v1 actually commits.
    committed_keys = []
    real_page_set = controller.page_set_func

    def capturing_set(hashes, host_inds, extra_info=None):
        result = real_page_set(hashes, host_inds, extra_info)
        committed_keys.extend(list(hashes))
        return result

    controller.page_set_func = capturing_set

    write_op = StorageOperation(
        host_indices=torch.arange(N * PAGE_SIZE, dtype=torch.int64),
        token_ids=g_toks,
        hash_value=spec_hash,
        prefix_keys=spec_prefix,
    )
    write_op.node_id = node_id
    try:
        controller._page_backup(write_op)
    except Exception as e:
        print(f"_page_backup raised: {e!r}")
        import traceback

        traceback.print_exc()
    finally:
        controller.page_set_func = real_page_set
    print(f"committed storage_keys count: {len(committed_keys)}")

    # ---- QUERY SIDE: CacheController._storage_hit_query ----
    # Faithful live shape (evicted-B / fresh-session re-query): the tree holds
    # the split parent A (g_toks[:300]) and child B (g_toks[300:], 1748 pages,
    # backed up above). A new request that matches only A continues with B's
    # key tokens; _storage_hit_query rebuilds B's chain from A's last hash:
    #   new_input_tokens = g_toks[300:]       (B's key)
    #   last_hash        = A.get_last_hash_value()
    # The rebuilt chain must equal B.hash_value == committed storage_keys.
    from sglang.srt.managers.cache_controller import PrefetchOperation

    anchor = node.parent  # the 300-page split parent of the backed-up leaf
    anchor_prefix = anchor.get_prefix_hash_values(anchor.parent)
    last_hash = anchor.get_last_hash_value()
    new_input = g_toks[300:]
    print(f"anchor pages={len(anchor.hash_value)} "
          f"anchor_prefix_pages={len(anchor_prefix)} "
          f"last_hash={last_hash[:16] if last_hash else None}")
    print(f"query new_input_tokens={len(new_input)}")

    scanned_keys = []
    live_backend = controller.storage_backend
    real_batch_exists = live_backend.batch_exists

    def capturing_exists(keys, extra_info=None):
        scanned_keys.extend(list(keys))
        return real_batch_exists(keys, extra_info)

    live_backend.batch_exists = capturing_exists

    prefetch_op = PrefetchOperation(
        request_id="probe-e28",
        token_ids=new_input,
        last_hash=last_hash,
        prefix_keys=anchor_prefix,
    )
    try:
        hash_value, storage_query_count = controller._storage_hit_query(prefetch_op)
    finally:
        live_backend.batch_exists = real_batch_exists
    print(f"storage_query_count={storage_query_count} "
          f"hash_value len={len(hash_value)}")

    # ---- THREE-WAY COMPARE ----
    print()
    print("=== THREE-WAY KEYS COMPARE ===")
    print(f"A. spec.hash_value len      = {len(spec_hash)}")
    print(f"B. batch_set_v1 committed   = {len(committed_keys)}")
    print(f"C. query-side rebuilt keys  = {len(scanned_keys)}")

    a_vs_b = spec_hash == committed_keys
    if not a_vs_b:
        first = next(
            i for i in range(min(len(spec_hash), len(committed_keys)))
            if spec_hash[i] != committed_keys[i]
        )
        print(f"  A vs B: FIRST MISS at key {first} "
              f"(A={spec_hash[first][:16]} B={committed_keys[first][:16]})")
    elif len(spec_hash) != len(committed_keys):
        print(f"  A vs B: LENGTH MISMATCH {len(spec_hash)} vs {len(committed_keys)}")
    else:
        print(f"  A vs B: EQUAL ({len(spec_hash)} keys)")

    # B vs C: the query chain over the continuation (B's key from A's last
    # hash) must byte-equal the committed storage_keys (which covered the same
    # B pages). In the faithful shape committed keys ARE B's chain, so B == C
    # is the invariant that makes the read side hit.
    b_vs_c = scanned_keys == committed_keys
    if not b_vs_c:
        n = min(len(scanned_keys), len(committed_keys))
        first = next(
            (i for i in range(n) if scanned_keys[i] != committed_keys[i]), None
        )
        if first is None:
            print(f"  B vs C: LENGTH MISMATCH {len(committed_keys)} vs "
                  f"{len(scanned_keys)}")
        else:
            print(f"  B vs C: FIRST MISS at key {first} "
                  f"(B={committed_keys[first][:16]} C={scanned_keys[first][:16]})")
    else:
        print(f"  B vs C: EQUAL ({len(committed_keys)} keys)")

    with live_backend._lock:
        bitmap = [
            live_backend._allocator.lookup(live_backend._storage_key(k)) is not None
            for k in scanned_keys
        ]
    present = sum(bitmap)
    print(f"index hit bitmap: {present}/{len(scanned_keys)} present")
    if present < len(scanned_keys):
        fm = next(i for i, b in enumerate(bitmap) if not b)
        print(f"  first missing index key={fm}")

    print()
    if not a_vs_b:
        verdict = "BRANCH A: spec.hash_value != committed storage_keys -> spec/commit layer"
    elif not b_vs_c:
        verdict = "BRANCH B: committed keys != query rebuilt keys -> _v1_buffer_meta blocks-split construct"
    elif present != len(scanned_keys):
        verdict = "BRANCH C: committed == rebuilt but allocator index missing -> allocator instance/state"
    elif storage_query_count != len(scanned_keys) * PAGE_SIZE:
        verdict = "BRANCH D: A==B==C, index full, but exists returned less -> backend scan"
    else:
        verdict = "BRANCH E: spec==commit==query, index full, exists full -> upstream node/prefix construction is the only layer left"
    print(f"VERDICT: {verdict}")

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
