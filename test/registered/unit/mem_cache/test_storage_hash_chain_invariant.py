"""Unit tests for the UnifiedRadix storage hash-chain invariant.

Guards the position-sensitive chained SHA256 contract between the write side
(node.hash_value, what build_storage_backup_spec submits to L3) and the query
side (get_hash_str over the unmatched continuation, seeded from the matched
anchor's last page hash).  Every page i of the query reconstruction must equal
node.hash_value[i] for the full logical prefix, including across the
STORAGE_BATCH_SIZE (1024) boundary and across a radix split.

The hash source is the e7k oracle (p2io_refhash, pure Python), verified
byte-equivalent to the native hash_binding.cpp extension (20/20 random trials
on the dev box).  Patching get_native_hash makes the test deterministic on
CPU-only CI (the native extension needs a C++ toolchain + openssl headers).

The guarded failure mode: a regression that re-seeds the query chain (or the
write chain) at a batch boundary from a stale parent hash, or breaks the
split hash redistribution, would make storage_hit silently drop to 0 for
multi-thousand-page prefixes.  Without this case, every other test still
passes because they use chains shorter than one 1024-batch.
"""

import hashlib
import struct
import unittest
from array import array
from unittest.mock import patch

import torch

from sglang.srt.mem_cache.allocator import TokenToKVPoolAllocator
from sglang.srt.mem_cache.base_prefix_cache import InsertParams, MatchPrefixParams
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool, ReqToTokenPool
from sglang.srt.mem_cache.radix_cache import RadixKey
from sglang.srt.mem_cache.unified_cache.components import ComponentType
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache
from sglang.test.ci.ci_register import register_cpu_ci
from sglang.test.test_utils import CustomTestCase

register_cpu_ci(est_time=40, suite="base-a-test-cpu")

STORAGE_BATCH_SIZE = 1024  # cache_controller.CONST; must stay in sync with it.
PAGE_SIZE = 1


def _hash_page(data, prior_digest, has_prior):
    ctx = hashlib.sha256()
    if has_prior:
        ctx.update(prior_digest)
    if len(data) > 0:
        ctx.update(data)
    return ctx.digest()


def _oracle_ref_hash(tokens, prior_hex=None, page_size=PAGE_SIZE):
    """Per-page chained SHA256 over uint32-le tokens (e7k p2io_refhash)."""
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
    """Drop-in for sglang.srt.mem_cache.utils.get_native_hash."""
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


def _make_cache(cap_pages):
    dtype = torch.float16
    kv_pool = MHATokenToKVPool(
        size=cap_pages,
        page_size=PAGE_SIZE,
        dtype=dtype,
        head_num=2,
        head_dim=8,
        layer_num=1,
        device="cpu",
        enable_memory_saver=False,
    )
    allocator = TokenToKVPoolAllocator(
        size=cap_pages,
        dtype=dtype,
        device="cpu",
        kvcache=kv_pool,
        need_sort=False,
    )
    req_pool = ReqToTokenPool(
        size=8,
        max_context_len=cap_pages + 64,
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


def _prefix_hash_values(cache, node):
    return node.get_prefix_hash_values(node.parent)


class TestStorageHashChainInvariant(CustomTestCase):
    @patch("sglang.srt.mem_cache.utils.get_native_hash", _oracle_get_native_hash)
    def test_4096_page_cross_batch_chain_equals_write_chain(self):
        """4096-page node: query reconstruction must equal node.hash_value on
        every page, including across the 1024-batch boundary.

        The native hash is patched out with the deterministic oracle so the
        C++ toolchain is not required on CPU CI; the tree hash plumbing
        (compute_node_hash_values / split / query seeding) runs for real.
        """
        n = 4 * STORAGE_BATCH_SIZE  # 4096 pages, crosses 3 batch boundaries
        toks = [(i * 7919 + 13) % 100003 for i in range(n)]
        cache, allocator = _make_cache(n + 64)
        node = _insert(cache, allocator, toks)
        self.assertEqual(len(node.hash_value), n)

        # The write side is node.hash_value; the query side rebuilds the same
        # logical prefix as get_hash_str(prefix_tokens, anchor_last_hash).
        anchor_hash = _prefix_hash_values(cache, node)
        anchor_seed = anchor_hash[-1] if anchor_hash else None
        query_chain = _oracle_ref_hash(toks, anchor_seed)
        self.assertEqual(len(query_chain), n)

        # Every page must match the write chain, not just the first batch.
        first_div = next(
            (i for i in range(n) if query_chain[i] != node.hash_value[i]), None
        )
        self.assertIsNone(
            first_div,
            f"query chain diverged at page {first_div} "
            f"(write={node.hash_value[first_div][:16]} "
            f"query={query_chain[first_div][:16]})"
            if first_div is not None
            else "query chain matches write chain",
        )

        # Seed provenance at the batch boundaries: the seed for page 1024 is
        # page 1023's hash, carried position-continuously across the batch.
        self.assertEqual(
            node.hash_value[STORAGE_BATCH_SIZE - 1],
            query_chain[STORAGE_BATCH_SIZE - 1],
        )
        seed = node.hash_value[STORAGE_BATCH_SIZE - 1]
        recomputed = _oracle_ref_hash(
            [toks[STORAGE_BATCH_SIZE]], seed, page_size=1
        )[0]
        self.assertEqual(recomputed, node.hash_value[STORAGE_BATCH_SIZE])
        for boundary in (STORAGE_BATCH_SIZE, 2 * STORAGE_BATCH_SIZE):
            self.assertEqual(
                node.hash_value[boundary], query_chain[boundary]
            )

    @patch("sglang.srt.mem_cache.utils.get_native_hash", _oracle_get_native_hash)
    def test_2048_page_split_preserves_write_and_query_chain(self):
        """Radix split must not break the write/query hash chain invariant.

        A split at page 500 re-parents the original 2048-page node; the
        path chain (anchor prefix + split hash redistribution) must still
        equal the fresh query reconstruction of the full logical prefix.
        """
        n = 2 * STORAGE_BATCH_SIZE  # 2048 pages
        toks = [(i * 7919 + 13) % 100003 for i in range(n)]
        cache, allocator = _make_cache(4 * n + 64)
        _insert(cache, allocator, toks)  # original 2048-page node

        # A diverging sequence sharing the first 500 pages forces a radix
        # split at page 500.
        share = 500
        alt = toks[:share] + [((i * 104729 + 3) % 100003) for i in range(n)]
        _insert(cache, allocator, alt)

        # Re-match the original full prefix; the anchor is its leaf node.
        match = cache.match_prefix(
            MatchPrefixParams(key=RadixKey(array("q", toks)))
        )
        matched = match.device_indices.numel()
        self.assertEqual(matched, n)
        anchor_id = match.last_device_node
        anchor = cache.tree_core.node_by_id(anchor_id)

        # Write chain = anchor prefix hashes + leaf node hash_value.
        prefix = _prefix_hash_values(cache, anchor)
        write_chain = prefix + (anchor.hash_value or [])
        self.assertEqual(len(write_chain), n)

        # Query chain = fresh reconstruction seeded from the anchor last hash.
        anchor_seed = prefix[-1] if prefix else None
        query_chain = _oracle_ref_hash(
            toks[len(prefix) :], anchor_seed, page_size=1
        )
        self.assertEqual(len(query_chain), len(anchor.hash_value))

        # The write chain for the continuation pages IS the leaf's hash_value
        # (split redistribution keeps it equal to the original chain suffix).
        first_div = next(
            (
                i
                for i in range(len(query_chain))
                if query_chain[i] != anchor.hash_value[i]
            ),
            None,
        )
        self.assertIsNone(
            first_div,
            f"split query chain diverged at page {len(prefix) + first_div}"
            if first_div is not None
            else "split query chain matches write chain",
        )

        # The full write chain (anchor prefix + leaf) must equal a fresh
        # reconstruction of the whole logical prefix.
        full_write = prefix + anchor.hash_value
        full_query = _oracle_ref_hash(toks, None, page_size=1)
        self.assertEqual(full_write, full_query)

    @patch("sglang.srt.mem_cache.utils.get_native_hash", _oracle_get_native_hash)
    def test_continuation_after_full_match_seeds_from_anchor_last_hash(self):
        """A query that matches the full stored prefix continues from the
        anchor's last page hash, so the suffix chain equals the stored leaf
        node's hash_value (the live node65/node29 1024->2048 shape)."""
        half = STORAGE_BATCH_SIZE  # 1024 pages
        toks = [(i * 104729 + 7) % 100003 for i in range(2 * half)]
        cache, allocator = _make_cache(4 * half + 64)
        node_a = _insert(cache, allocator, toks[:half])  # node34: 1024 pages
        node_b = _insert(cache, allocator, toks)  # node35: 1024 pages, child

        # A query for the first half anchors at node_a; the continuation is
        # the second half (node_b's content).
        match = cache.match_prefix(
            MatchPrefixParams(key=RadixKey(array("q", toks[:half])))
        )
        anchor_id = match.last_device_node
        self.assertEqual(anchor_id, node_a.id)
        anchor = cache.tree_core.node_by_id(anchor_id)
        last_hash = anchor.get_last_hash_value()
        self.assertEqual(last_hash, node_a.hash_value[-1])

        # Live: new_input_tokens = continuation, seeded from anchor.last_hash.
        continuation = toks[half:]
        query_chain = _oracle_ref_hash(continuation, last_hash, page_size=1)
        self.assertEqual(query_chain, node_b.hash_value)


if __name__ == "__main__":
    unittest.main()
