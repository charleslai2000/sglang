#!/usr/bin/env python3
"""BOUND PROOF (executable): does the never-rewritten durability-anchor run grow
with the tree's logical prefix length?

Model: a session prefix grows by successive appends (toks[:1], toks[:2], ...,
toks[:N]).  Each append matches the existing chain and creates ONE new child
node (UnifiedTreeCore.insert splits/extends), exactly as a growing session does.
Normal traffic then backs up the new leaf via the real write path helpers
(collect_storage_gap -> build_storage_backup_spec -> advance_storage_persisted).
We record, for every backup, which pages its spec actually writes.

If the "run" were structurally bounded we would expect later backups to
re-enter the earlier nodes (refreshing them).  If it grows with the prefix we
expect every earlier node to be written exactly once and never re-entered.
"""
import ctypes
import hashlib
import json
import struct
import sys
import tempfile
from array import array
from unittest.mock import patch

import torch

from sglang.srt.mem_cache.allocator import TokenToKVPoolAllocator
from sglang.srt.mem_cache.base_prefix_cache import InsertParams
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool, ReqToTokenPool
from sglang.srt.mem_cache.radix_cache import RadixKey
from sglang.srt.mem_cache.unified_cache.components import ComponentType
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache
from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend

PAGE_BYTES = 5000


class _ZeroCopyPool:
    def __init__(self, page_bytes, slots):
        self.page_size = 1
        self._page_bytes = page_bytes
        self._pages = [bytearray(page_bytes) for _ in range(slots)]

    def get_page_buffer_meta(self, indices):
        idx = indices.tolist() if hasattr(indices, "tolist") else list(indices)
        ptrs = [ctypes.addressof(ctypes.c_char.from_buffer(self._pages[i])) for i in idx]
        return ptrs, [self._page_bytes] * len(ptrs)


def _oracle_get_native_hash(token_ids, prior_digest, page_size=None):
    raw = token_ids.raw_token_ids() if hasattr(token_ids, "raw_token_ids") else token_ids
    tokens = list(raw)
    prior = prior_digest if prior_digest else None
    data = b"".join(struct.pack("<I", t & 0xFFFFFFFF) for t in tokens)
    out, has = [], prior is not None
    step = page_size or len(tokens)
    for start in range(0, len(tokens), step):
        ctx = hashlib.sha256()
        if has:
            ctx.update(prior)
        ctx.update(data[start * 4 : (start + step) * 4])
        prior = ctx.digest()
        has = True
        out.append(prior.hex())
    return out[-1] if page_size is None else out


def _make_cache(cap_pages):
    kv_pool = MHATokenToKVPool(
        size=cap_pages, page_size=1, dtype=torch.float16, head_num=2, head_dim=8,
        layer_num=1, device="cpu", enable_memory_saver=False,
    )
    allocator = TokenToKVPoolAllocator(
        size=cap_pages, dtype=torch.float16, device="cpu", kvcache=kv_pool, need_sort=False,
    )
    req_pool = ReqToTokenPooL = ReqToTokenPool(
        size=8, max_context_len=cap_pages + 64, device="cpu", enable_memory_saver=False,
    )
    params = CacheInitParams(
        disable=False, req_to_token_pool=req_pool,
        token_to_kv_pool_allocator=allocator, page_size=1,
        eviction_policy="lru", tree_components=(ComponentType.FULL,),
    )
    cache = UnifiedRadixCache(params)
    cache.enable_storage = True
    return cache, allocator


def _insert(cache, allocator, token_ids):
    indices = allocator.alloc(len(token_ids))
    node_id = cache.insert(
        InsertParams(key=RadixKey(array("q", token_ids)), value=indices.to(torch.int64))
    ).last_device_node
    return cache.tree_core.node_by_id(node_id)


@patch("sglang.srt.mem_cache.utils.get_native_hash", _oracle_get_native_hash)
def run_n(n_nodes):
    tmp = tempfile.mkdtemp(prefix=f"f1_bound_{n_nodes}_")
    n_tokens = n_nodes  # one page per appended token -> one node per token
    toks = list(range(1000, 1000 + n_tokens))
    cache, alloc = _make_cache(n_tokens * (n_tokens + 1) // 2 + 16)

    written_specs = []          # list of sets of page hashes written by each backup
    nodes = []
    for k in range(1, n_tokens + 1):
        node = _insert(cache, alloc, toks[:k])
        node.component_data[ComponentType.FULL].host_value = torch.tensor(
            list(range(100 + k, 100 + k + len(node.hash_value))), dtype=torch.int64
        )
        nodes.append(node)
        # Real normal-traffic write path helpers (persisted parent -> gap is the
        # new node only): collect_storage_gap, build spec, advance persisted.
        gap = cache.tree_core.collect_storage_gap(node.id)
        for nid in gap:
            spec = cache.tree_core.build_storage_backup_spec(nid, False)
            if spec is not None and spec.hash_value:
                written_specs.append((nid, list(spec.hash_value)))
            cache.tree_core.advance_storage_persisted(nid)

    chain = [h for n in nodes for h in n.hash_value]
    # which pages were ever written, and how often
    from collections import Counter
    cnt = Counter(h for _nid, hs in written_specs for h in hs)
    once = [h for h in chain if cnt[h] == 1]
    # leading contiguous never-rewritten run from page 0
    run = 0
    while run < len(chain) and cnt[chain[run]] == 1:
        run += 1
    # real backend: seed the whole chain, recycle the oldest slots, query
    _slots = (n_tokens * PAGE_BYTES) // 16384 + 4
    backend = ExtentFileBackend(HiCacheStorageConfig(
        extra_config={"storage_dir": tmp, "extent_size": "16Ki", "file_size": f"{_slots * 16}Ki"},
        tp_rank=0, tp_size=1, pp_rank=0, pp_size=1, attn_cp_rank=0, attn_cp_size=1,
        is_mla_model=False, enable_storage_metrics=False, is_page_first_layout=True,
        model_name="f1bound",
    ))
    backend.register_mem_pool_host(_ZeroCopyPool(PAGE_BYTES, max(64, n_tokens)))
    backend.batch_set_v1(chain, torch.tensor(list(range(len(chain))), dtype=torch.int64))
    # recycle the slots holding the leading pages (allocator cursor wrap)
    slots = sorted({backend._allocator._index[backend._storage_key(chain[i])].extent_id
                    for i in range(run)})
    backend._append_drops([(s, backend._allocator._generations[s] + 1) for s in slots])
    backend._allocator.apply_drops([(s, backend._allocator._generations[s] + 1) for s in slots])
    for key in list(backend._components):
        if key not in backend._allocator._index:
            backend._components.pop(key, None)
    hits_from0 = backend.batch_exists(chain, None)
    backend.close()
    return {
        "n_nodes": n_nodes, "n_pages": len(chain),
        "n_ever_written_pages": len(cnt),
        "n_write_once_pages": len(once),
        "leading_never_rewritten_run": run,
        "run_fraction_of_chain": round(run / len(chain), 3),
        "batch_exists_from_page0_after_head_slot_recycle": hits_from0,
        "recycled_slots": slots,
    }


if __name__ == "__main__":
    out = []
    for n in (6, 12, 24, 48):
        r = run_n(n)
        out.append(r)
        print(json.dumps(r))
    json.dump(out, open("/tmp/opencode/f1-optionA-anchorrun-20260916/bound_demo.json", "w"), indent=2)
