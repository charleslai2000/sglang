#!/usr/bin/env python3
"""e27 deterministic chain-compare probe: write chain vs query chain on a
2048-page node.

User/coordinator e27 ruling (background fixed): extent backend is innocent
(2048 set->exists->get byte-identical hard contract, proven e26).  The only
remaining layer is `UnifiedRadix logical prefix -> storage hash-chain`.

This probe constructs a REAL UnifiedRadixCache (CPU, page_size=1, storage
enabled) and a real 2048-page node, then compares:

  write_chain[i]  = node.hash_value[i]           (what build_storage_backup_spec
                                                  submits to L3)
  query_chain[i]  = query-side rebuilt hash[i]   (what _storage_hit_query /
                                                  get_hash_str recomputes)

page by page i = 0..2047, and prints batch-2 seed provenance:
  page 1023: write_hash, query_hash
  page 1024: write_seed, query_seed, write_hash, query_hash
  node_id / node.key range / parent_id / split offset

The hash source is the e7k oracle (p2io_refhash), verified equivalent to the
native hash_binding.cpp (20/20 random trials on this machine).  The oracle is
also what the CI test will use, so the probe and the permanent unit test agree.
"""
import os
import sys
from array import array

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

import torch

from sglang.srt.mem_cache.base_prefix_cache import (
    InsertParams,
    MatchPrefixParams,
)
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool, ReqToTokenPool
from sglang.srt.mem_cache.radix_cache import RadixKey
from sglang.srt.mem_cache.unified_cache.components import ComponentType
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache

# --- e7k oracle (p2io_refhash.py); native-equivalent (verified 20/20) ---
import hashlib
import struct


def _hash_page(data, prior_digest, has_prior):
    ctx = hashlib.sha256()
    if has_prior:
        ctx.update(prior_digest)
    if len(data) > 0:
        ctx.update(data)
    return ctx.digest()


def ref_hash(tokens, prior_hex=None, page_size=1):
    """Same entrypoint shape as get_native_hash(array, logical_len, 1, False,
    prior_bytes, page_size) but over a plain list; returns list[str]."""
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


def oracle_get_native_hash(token_ids, prior_digest, page_size=None):
    """Drop-in for utils.get_native_hash using the e7k oracle (native-
    equivalent, verified 20/20 random trials on this machine).

    token_ids may be a RadixKey (raw_token_ids) or an array; prior_digest is
    bytes or None; page_size None -> single hash over all tokens.
    """
    if hasattr(token_ids, "raw_token_ids"):
        raw = token_ids.raw_token_ids()
    elif hasattr(token_ids, "token_ids"):
        raw = token_ids.token_ids
    else:
        raw = token_ids
    tokens = list(raw)
    prior_hex = prior_digest.hex() if prior_digest else None
    if page_size is None:
        return ref_hash(tokens, prior_hex, page_size=len(tokens))[-1]
    return ref_hash(tokens, prior_hex, page_size=page_size)


# Patch the production hash entrypoint with the oracle so the REAL tree logic
# (compute_node_hash_values / get_hash_str) runs end-to-end without needing
# the C++ extension (Python.h / openssl headers absent on this machine).
import sglang.srt.mem_cache.utils as _utils

_utils.get_native_hash = oracle_get_native_hash



N = 2048
PAGE_SIZE = 1
_POOL_CAP = 4 * 2048 + 64  # enough for two 2048-token nodes + split slack


def _make_cache():
    dtype = torch.float16
    kv_pool = MHATokenToKVPool(
        size=_POOL_CAP,
        page_size=PAGE_SIZE,
        dtype=dtype,
        head_num=2,
        head_dim=8,
        layer_num=1,
        device="cpu",
        enable_memory_saver=False,
    )
    from sglang.srt.mem_cache.allocator import TokenToKVPoolAllocator

    allocator = TokenToKVPoolAllocator(
        size=_POOL_CAP,
        dtype=dtype,
        device="cpu",
        kvcache=kv_pool,
        need_sort=False,
    )
    req_pool = ReqToTokenPool(
        size=8,
        max_context_len=N + 64,
        device="cpu",
        enable_memory_saver=False,
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
    # Enable storage so _add_new_node computes hash_value.
    cache.enable_storage = True
    cache.hicache_storage_pass_prefix_keys = True
    return cache, allocator


def _insert(cache, allocator, token_ids):
    indices = allocator.alloc(len(token_ids))
    node_id = cache.insert(
        InsertParams(
            key=RadixKey(array("q", token_ids)),
            value=indices.to(torch.int64),
        )
    ).last_device_node
    return cache.tree_core.node_by_id(node_id)


def _match(cache, token_ids):
    return cache.match_prefix(
        MatchPrefixParams(key=RadixKey(array("q", token_ids)))
    )


def main():
    cache, allocator = _make_cache()
    # Deterministic 2048-token prefix (page_size=1 -> 2048 pages).
    toks = [(i * 7919 + 13) % 100003 for i in range(N)]
    node = _insert(cache, allocator, toks)
    assert node.key is not None and len(node.key) == N, (len(node.key), N)
    write_chain = node.hash_value
    assert write_chain is not None and len(write_chain) == N, (
        len(write_chain) if write_chain is not None else None,
        N,
    )

    # Live path: a node is backuped when its FULL host_value is populated
    # (D->H DMA ack).  Simulate that so build_storage_backup_spec (the exact
    # write-side chain source) returns the node's spec.
    node.component_data[ComponentType.FULL].host_value = (
        node.component_data[ComponentType.FULL].value.clone()
    )
    spec = cache.tree_core.build_storage_backup_spec(node.id, True)
    assert spec is not None
    spec_chain = spec.hash_value
    assert spec_chain == write_chain, "spec.hash_value != node.hash_value"

    # --- query side, exactly as the live path does it ---
    # live: last_hash = tree_cache.get_last_hash_value(last_host_node)
    #       prefix_keys = get_prefix_hash_values(last_host_node)
    #       new_input_tokens = unmatched suffix
    #       query keys = get_hash_str(new_input_tokens, last_hash, page_size)
    #         (then batch_exists batches of 1024, prefix_keys prefixed)
    parent_last_hash = node.get_prefix_hash_values(
        node.parent
    )  # anchor prefix hashes
    anchor_hash = parent_last_hash[-1] if parent_last_hash else None

    # 1. the pure query chain (fresh reconstruction over the full suffix):
    query_chain_fresh = ref_hash(toks, anchor_hash, page_size=1)
    # 2. the batched query chain (what _storage_hit_query effectively builds:
    #    prefix_keys + per-1024 get_hash_str, prefix carried across batches).
    #    NOTE: _storage_hit_query calls get_hash_str once over all tokens with
    #    the anchor last_hash; batching only affects the storage backend scan,
    #    not the hash values. So query_chain_batched == query_chain_fresh.

    # --- page-by-page compare + seed provenance ---
    first_div = None
    div_at_1024 = None
    for i in range(N):
        if write_chain[i] != query_chain_fresh[i]:
            first_div = i
            break

    print("=== chain compare ===")
    print(f"node_id={node.id} parent_id={node.parent.id if node.parent else None}")
    print(
        f"node.key range={toks[0]}..{toks[-1]} len={len(toks)} pages={N}"
    )
    print(f"anchor_hash({'none' if anchor_hash is None else anchor_hash[:16]})")
    print(f"write_chain len={len(write_chain)}")
    print(f"query_chain len={len(query_chain_fresh)}")
    print(f"FIRST DIVERGENCE page={first_div}")

    # provenance rows
    print("\n=== seed provenance ===")
    for p in (1023, 1024, 1025):
        if p >= N:
            continue
        print(
            f"page {p}: "
            f"write_hash={write_chain[p][:16]} query_hash={query_chain_fresh[p][:16]} "
            f"equal={write_chain[p] == query_chain_fresh[p]}"
        )
    # batch-2 seed: page 1024 hashes are seeded by page 1023's hash on the
    # chained scheme. print both the stored page-1023 hash and the seed used
    # to build page 1024.
    if N > 1024:
        print(
            f"page1023 write_hash={write_chain[1023][:16]} "
            f"query_hash={query_chain_fresh[1023][:16]}"
        )
        print(
            f"page1024 write_hash={write_chain[1024][:16]} "
            f"query_hash={query_chain_fresh[1024][:16]}"
        )
        # reproduce page1024 from page1023 hash under the oracle
        seed_write = write_chain[1023]
        seed_query = query_chain_fresh[1023]
        p1024_from_write = ref_hash([toks[1024]], seed_write, 1)[0]
        p1024_from_query = ref_hash([toks[1024]], seed_query, 1)[0]
        print(
            f"recomputed page1024 from write seed: {p1024_from_write[:16]}"
        )
        print(
            f"recomputed page1024 from query seed: {p1024_from_query[:16]}"
        )

    # --- verdict (the four cases the coordinator listed) ---
    print("\n=== verdict ===")
    if first_div is None:
        print("ALL 2048 EQUAL: write chain == query chain -> backend would hit;")
        print("storage_hit=0 must then come from a DIFFERENT query/prefix")
    elif first_div == 1024:
        print("DIVERGENCE AT PAGE 1024: batch-2 seed reset")
        print("  => 0..1023 equal, 1024+ all wrong: second batch seeded from")
        print("     a stale parent hash, not the just-written page 1023 hash")
    elif first_div < 1024:
        print(f"DIVERGENCE BEFORE 1024 (page {first_div}):")
        print("  => not a batch boundary; split/prefix issue")
    else:
        print(f"DIVERGENCE AT PAGE {first_div} (not at 1024):")
        print("  => batch_exists's final 1024 is not from a batch-2 seed reset")

    # --- what would the live query actually see? ---
    # live scheduler: match_prefix over the full 2048 gives the anchor node;
    # new_input_tokens = the unmatched suffix (0 here); prefix_keys = anchor
    # prefix. The backend then scans prefix_keys + query chain. If the anchor
    # is the node ITSELF (all 2048 matched), new_input_tokens is empty and the
    # query is just prefix_keys = node.get_prefix_hash_values(parent) -- which
    # may be SHORTER than node.hash_value.
    print("\n=== live-shape note ===")
    print("prefix_keys(anchor=node) len:", len(parent_last_hash))
    print("node.hash_value len:", len(write_chain))
    if len(parent_last_hash) < N:
        print(
            "query via prefix_keys covers",
            len(parent_last_hash),
            "pages, not",
            N,
            "-- the storage scan only sees the ANCHOR PREFIX, not the node's",
        )
        print("full 2048 chain, so storage_hit is capped at the anchor length")

    # --- split scenario (the coordinator's prime suspect) ---
    print("\n=== split scenario ===")
    # Insert a different sequence sharing a prefix: forces a radix split.
    share = 500
    alt = toks[:share] + [((i * 104729 + 3) % 100003) for i in range(N)]
    cache2, allocator2 = _make_cache()  # fresh cache + fresh allocator
    _ = _insert(cache2, allocator2, toks)  # original 2048 node
    _ = _insert(cache2, allocator2, alt)  # forces split at `share`
    for frag in _walk_fragments(cache2):
        k = frag.key.token_ids if frag.key is not None else []
        print(
            f"fragment node_id={frag.id} parent={frag.parent.id if frag.parent else None} "
            f"pages={len(frag.hash_value) if frag.hash_value else 0} "
            f"keyrange={k[0] if len(k) else '-'}..{k[-1] if len(k) else '-'}"
        )
    # The original 2048-token prefix: match it, then compare write chain vs
    # the fresh reconstruction over its full token span.
    res = cache2.match_prefix(
        MatchPrefixParams(key=RadixKey(array("q", toks)))
    )
    matched = res.device_indices.numel() if res.device_indices is not None else 0
    print("match of original 2048-prefix len:", matched)
    anchor_id = res.last_device_node
    anchor_hash_chain = cache2.tree_core.get_prefix_hash_values(anchor_id)
    print("anchor prefix hashes len:", len(anchor_hash_chain))
    path_hashes = _path_chain(cache2, anchor_id)
    print("path chain len:", len(path_hashes))
    fresh = ref_hash(toks, None, page_size=1)
    div = next(
        (
            i
            for i in range(min(len(path_hashes), len(fresh)))
            if path_hashes[i] != fresh[i]
        ),
        None,
    )
    print("split path chain vs fresh query: FIRST DIVERGENCE =", div)
    if div is not None:
        print(f"  page {div}: path={path_hashes[div][:16]} fresh={fresh[div][:16]}")
    else:
        print("  split does NOT diverge the hash chain: all equal")

    # --- growth scenario (the actual live node65/node29 shape) ---
    print("\n=== growth scenario (node 1024 -> 2048 -> query) ===")
    cache3, allocator3 = _make_cache()
    # Live writes a node in two 1024 batches; storage turn-on backfills hash.
    g_toks = [(i * 104729 + 7) % 100003 for i in range(N)]
    g_node = _insert(cache3, allocator3, g_toks[:1024])
    print(f"after 1024 insert: node_id={g_node.id} pages={len(g_node.hash_value)}")
    # grow to 2048 via a longer insert sharing the full prefix
    g_full = _insert(cache3, allocator3, g_toks)
    print(f"after 2048 insert: node_id={g_full.id} pages={len(g_full.hash_value)}")
    # the write chain (what would be persisted) is the FULL path chain:
    # anchor prefix (parent hashes) + leaf node hash_value (the suffix pages).
    # build_storage_backup_spec persists node35.hash_value; write_backup also
    # persists the unbacked ancestor gap (node34) whose prefix_keys carry the
    # first 1024 pages.  The recoverable write chain is the concatenation.
    w = _path_chain(cache3, g_full.id)
    # the query chain: anchor is the matched node; prefix_keys covers it;
    # fresh query reconstructs over the full 2048 from the anchor last_hash
    res3 = cache3.match_prefix(
        MatchPrefixParams(key=RadixKey(array("q", g_toks)))
    )
    anchor3_id = res3.last_device_node
    anchor3 = cache3.tree_core.node_by_id(anchor3_id)
    pref3 = cache3.tree_core.get_prefix_hash_values(anchor3_id)
    print(f"growth: anchor_id={anchor3_id} anchor_pages={len(anchor3.hash_value)} "
          f"anchor_prefix_len={len(pref3)}")
    last3 = anchor3.get_last_hash_value()
    print(f"growth: anchor_last_hash={'none' if last3 is None else last3[:16]}")
    # query keys = get_hash_str(unmatched suffix, anchor last_hash)
    unmatched = g_toks[len(pref3):]
    q3 = ref_hash(unmatched, last3, page_size=1)
    full_query = pref3 + q3
    div3 = next(
        (i for i in range(min(len(w), len(full_query))) if w[i] != full_query[i]),
        None,
    )
    print("growth write_chain len:", len(w))
    print("growth query_chain len:", len(full_query))
    print("growth FIRST DIVERGENCE =", div3)
    if div3 is not None:
        print(f"  page {div3}: write={w[div3][:16]} query={full_query[div3][:16]}")
        for p in (1023, 1024, 1025):
            if p < len(w) and p < len(full_query):
                print(
                    f"  page {p}: write={w[p][:16]} query={full_query[p][:16]} "
                    f"equal={w[p] == full_query[p]}"
                )
    else:
        print("  growth does NOT diverge: write chain == query chain")

    # --- LIVE-FAITHFUL query: what the backend actually scans ---
    # The live scheduler passes new_input_tokens = unmatched suffix ONLY, and
    # last_hash = anchor.last_hash.  The backend batch_exists scans ONLY the
    # reconstructed suffix hashes (prefix_keys is metadata, not scanned by
    # either HiCacheFile or ExtentFileBackend.batch_exists).  So the live KV
    # hit is capped at what get_hash_str(suffix, anchor_last_hash) can find in
    # storage.  The write side persisted the FULL path chain (anchor prefix +
    # suffix), but only the suffix hashes match storage keys; the query never
    # looks up the prefix hashes against storage.
    print("\n=== live-faithful query (backend scans suffix only) ===")
    suffix_start = len(pref3)  # 1024 in the growth case
    suffix_tokens = g_toks[suffix_start:]
    suffix_query = ref_hash(suffix_tokens, last3, page_size=1)
    # write side: node35.hash_value IS the suffix chain (1024 pages); anchor
    # prefix chain (pref3) is written by node34's backup.
    write_suffix = w[suffix_start:]  # path chain suffix = node35.hash_value
    print(f"suffix_start={suffix_start} suffix_len={len(suffix_tokens)}")
    print(f"write_suffix len={len(write_suffix)} suffix_query len={len(suffix_query)}")
    div_s = next(
        (
            i
            for i in range(min(len(write_suffix), len(suffix_query)))
            if write_suffix[i] != suffix_query[i]
        ),
        None,
    )
    print("suffix query vs write suffix: FIRST DIVERGENCE =", div_s)
    if div_s is not None:
        print(
            f"  page {suffix_start + div_s}: "
            f"write={write_suffix[div_s][:16]} query={suffix_query[div_s][:16]}"
        )
    else:
        print("  suffix query == write suffix: backend WOULD hit the suffix")
        print(
            "  => the live storage_hit should be >= suffix hit; the 1024/1027"
        )
        print("     cap must come from the query being issued over a SHORTER")
        print("     suffix or a different anchor last_hash")


def _walk_fragments(cache):
    """Yield every node reachable from the root, pre-order."""
    out = []
    stack = [cache.tree_core.node_by_id(cache.tree_core.root_node_handle())]
    while stack:
        n = stack.pop()
        out.append(n)
        stack.extend(n.children.values())
    return out


def _path_chain(cache, node_id):
    """Concatenate parent-prefix hashes down to node_id (the anchor path)."""
    node = cache.tree_core.node_by_id(node_id)
    return node.get_prefix_hash_values(node.parent) + (
        node.hash_value or []
    )


if __name__ == "__main__":
    main()
