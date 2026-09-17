"""Spec-level probe for the F1 head-refresh fix (CPU-only).

Run with PYTHONPATH=<tree>/src/python to select the tree under test.
"""
import hashlib
import struct
import sys
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

PAGE = 1


def _hash_page(data, prior_digest, has_prior):
    ctx = hashlib.sha256()
    if has_prior:
        ctx.update(prior_digest)
    if len(data) > 0:
        ctx.update(data)
    return ctx.digest()


def _oracle_ref_hash(tokens, prior_hex=None, page_size=PAGE):
    data = b"".join(struct.pack("<I", t & 0xFFFFFFFF) for t in tokens)
    prior = bytes.fromhex(prior_hex) if prior_hex else None
    has_prior = prior is not None
    out = []
    for start in range(0, len(tokens), page_size):
        chunk = data[start * 4 : (start + page_size) * 4]
        digest = _hash_page(chunk, prior, has_prior)
        prior = digest
        has_prior = True
        out.append(digest.hex())
    return out


def _oracle_get_native_hash(token_ids, prior_digest, page_size=None):
    raw = token_ids.raw_token_ids() if hasattr(token_ids, "raw_token_ids") else token_ids
    tokens = list(raw)
    prior_hex = prior_digest.hex() if prior_digest else None
    if page_size is None:
        return _oracle_ref_hash(tokens, prior_hex, page_size=len(tokens))[-1]
    return _oracle_ref_hash(tokens, prior_hex, page_size=page_size)


def _make_cache(cap_pages):
    dtype = torch.float16
    kv_pool = MHATokenToKVPool(
        size=cap_pages, page_size=PAGE, dtype=dtype, head_num=2, head_dim=8,
        layer_num=1, device="cpu", enable_memory_saver=False,
    )
    allocator = TokenToKVPoolAllocator(
        size=cap_pages, dtype=dtype, device="cpu", kvcache=kv_pool, need_sort=False,
    )
    req_pool = ReqToTokenPool(
        size=8, max_context_len=cap_pages + 64, device="cpu", enable_memory_saver=False,
    )
    params = CacheInitParams(
        disable=False, req_to_token_pool=req_pool,
        token_to_kv_pool_allocator=allocator, page_size=PAGE,
        eviction_policy="lru", tree_components=(ComponentType.FULL,),
    )
    cache = UnifiedRadixCache(params)
    cache.enable_storage = True
    cache.hicache_storage_pass_prefix_keys = False
    return cache, allocator


def _insert(cache, allocator, token_ids):
    indices = allocator.alloc(len(token_ids))
    node_id = cache.insert(
        InsertParams(key=RadixKey(array("q", token_ids)), value=indices.to(torch.int64))
    ).last_device_node
    return cache.tree_core.node_by_id(node_id)


@patch("sglang.srt.mem_cache.utils.get_native_hash", _oracle_get_native_hash)
def main():
    toks = [11, 22, 33, 44, 55, 66, 77, 88]
    cache, allocator = _make_cache(64)
    head = _insert(cache, allocator, toks[:1])       # chain-head node A = [page0]
    desc = _insert(cache, allocator, toks)           # A split -> B = [page1..7]
    # Give both nodes a host copy so backuped is True (as after a D2H backup).
    head.component_data[ComponentType.FULL].host_value = torch.arange(
        len(head.hash_value) * PAGE, dtype=torch.int64
    )
    desc.component_data[ComponentType.FULL].host_value = torch.arange(
        100, 100 + len(desc.hash_value) * PAGE, dtype=torch.int64
    )
    head_id, desc_id = head.id, desc.id
    print("head hash[0] :", head.hash_value[0][:16])
    print("desc hash[0] :", desc.hash_value[0][:16])
    spec = cache.tree_core.build_storage_backup_spec(desc_id, False)
    print("spec n_hash  :", len(spec.hash_value), "desc n_hash", len(desc.hash_value))
    print("spec hash[0] :", spec.hash_value[0][:16])
    print("spec host len:", len(spec.host_value), "expected", (len(desc.hash_value) + 1) * PAGE)
    print("spec tok len :", len(spec.token_ids))
    head_prepended = spec.hash_value[0] == head.hash_value[0]
    print("HEAD_PREPENDED:", head_prepended)
    # empty-prefix path: the head node itself has no ancestor hash
    head_spec = cache.tree_core.build_storage_backup_spec(head_id, False)
    print("head spec n_hash:", len(head_spec.hash_value), "unchanged:", len(head_spec.hash_value) == len(head.hash_value))
    sys.exit(0 if head_prepended else 3)


if __name__ == "__main__":
    main()
