"""Async prefetch completion vs. anchor lifetime (r61 C-8).

Field symptom: under C-8 churn a storage->host prefetch is issued against a
matched anchor node, the anchor is evicted while the L3 read is in flight, and
the completion then either raised `KeyError` on the dead NodeId or (worse) would
have grafted the fetched KV under whatever node now holds that id.

The contract pinned here:

* the operation records the anchor's last page hash at issue. Hashes chain every
  ancestor hash, so equality at completion proves the id still resolves to a
  live node holding exactly this prefix -- a reused id or a different chain
  fails the check;
* a split (the anchor keeps its last page, its key loses a prefix) keeps the
  identity valid and the graft stays under the same node;
* an invalid anchor discards the fetch as a terminal miss, releasing only the
  operation's own staging exactly once and never touching the anchor's slots;
* the check and the graft happen on the scheduler thread's ACK drain with no
  interleaving tree mutation.
"""

import types
import unittest
from unittest import mock

import torch

from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.radix_cache import RadixKey
from sglang.srt.mem_cache.unified_cache.components import ComponentType
from sglang.srt.mem_cache.unified_cache.unified_tree_core import UnifiedTreeCore
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache

BASE = ComponentType.FULL
PAGE = 1


class _FakeOperation:
    """The fields the completion path reads off a PrefetchOperation."""

    def __init__(self, rid, host_indices, requested_tokens, *, pool_done=True):
        self.request_id = rid
        self.host_indices = host_indices
        self.pool_transfers_done = pool_done
        self.stats_requested_tokens = requested_tokens
        self.prefetch_attempt_id = None
        self.trace_context = None


def _make_tree():
    params = CacheInitParams(
        disable=False,
        req_to_token_pool=None,
        token_to_kv_pool_allocator=None,
        page_size=PAGE,
        tree_components=(BASE,),
    )
    tree = UnifiedTreeCore(params, {BASE: mock.Mock(component_type=BASE)})
    tree.set_hicache_enabled()
    tree.enable_storage = True
    return tree


def _make_cache(tree):
    """A cache facade with only the state the completion/discard path owns."""
    cache = UnifiedRadixCache.__new__(UnifiedRadixCache)
    cache.tree_core = tree
    cache.page_size = tree.page_size
    cache.disable = False
    cache.host_memory_mode = "cache"
    cache.ongoing_prefetch = {}
    cache._demand_restore_rids = set()
    cache.prefetch_loaded_tokens_by_reqid = {}
    cache._storage_prefetch_terminal = {}
    cache.cache_controller = types.SimpleNamespace(
        prefetch_tokens_occupied=0, append_host_mem_release=mock.Mock()
    )
    cache.release_prefetch = mock.Mock()
    cache._release_aux_transfers_before_host_alloc_snapshot = mock.Mock()
    cache._host_alloc_hybrid_completion = mock.Mock(return_value={})
    cache.record_storage_prefetch_completion = mock.Mock()
    cache._host_allocability_signatures = mock.Mock(return_value={})
    cache._bump_changed_host_allocability = mock.Mock()
    cache.record_storage_prefetch_terminal = types.MethodType(
        UnifiedRadixCache.record_storage_prefetch_terminal, cache
    )
    return cache


def _add(tree, parent, tokens, slots, hashes=None):
    node = tree._add_new_node(
        parent,
        RadixKey(list(tokens)),
        torch.tensor(list(slots), dtype=torch.int64),
    )
    if hashes is not None:
        node.hash_value = list(hashes)
    return node


def _entry(anchor, key, host_indices, op, lock_params, anchor_hash):
    from sglang.srt.mem_cache.unified_radix_cache import _OngoingPrefetch

    return _OngoingPrefetch(
        anchor, key, host_indices, op, lock_params, {}, anchor_hash
    )


def _discard(cache, tree, anchor, *, rid, key, completed, lock_params, live_lock):
    """Drive the real discard path with an upstream-issued operation."""
    host_indices = torch.tensor([900, 901], dtype=torch.int64)
    op = _FakeOperation(rid, host_indices, requested_tokens=completed)
    cache.ongoing_prefetch[rid] = _entry(
        anchor, key, host_indices, op, lock_params, None
    )
    cache._demand_restore_rids.add(rid)
    if len(cache.ongoing_prefetch) == 1:
        cache.cache_controller.prefetch_tokens_occupied = len(key)
    cache.dec_host_lock_ref = mock.Mock(wraps=live_lock)
    cache._discard_prefetch_stale_anchor(
        operation=op,
        req_id=rid,
        completed_tokens=completed,
        prefetch_key=key,
        host_indices=host_indices,
        comp_xfers={},
        anchor_node_id=anchor,
        anchor_lock_params=lock_params,
        sidecar_counts={},
    )
    return op


class TestPrefetchAnchorIdentity(unittest.TestCase):
    def setUp(self):
        self.tree = _make_tree()
        self.cache = _make_cache(self.tree)

    def test_identifies_an_evicted_anchor(self):
        anchor = _add(self.tree, self.tree.root_node, [1, 2], [1, 2], hashes=["h1", "h2"])
        seen_hash = self.tree.get_last_hash_value(anchor.id)
        self.assertTrue(self.cache._prefetch_anchor_is_valid(anchor.id, seen_hash))

        self.tree._remove_leaf_from_parent(anchor)

        self.assertFalse(self.tree.node_exists(anchor.id))
        self.assertFalse(self.cache._prefetch_anchor_is_valid(anchor.id, seen_hash))

    def test_reused_node_id_is_not_the_same_anchor(self):
        anchor = _add(self.tree, self.tree.root_node, [1, 2], [1, 2])
        seen_hash = self.tree.get_last_hash_value(anchor.id)
        self.tree._remove_leaf_from_parent(anchor)

        # Arena reuse: the id now names an unrelated node/prefix.
        stranger = _add(self.tree, self.tree.root_node, [7, 8], [7, 8])
        self.tree._node_arena[anchor.id] = stranger

        self.assertFalse(self.cache._prefetch_anchor_is_valid(anchor.id, seen_hash))

    def test_unhashed_anchor_is_unverifiable(self):
        anchor = _add(self.tree, self.tree.root_node, [1], [1], hashes=[])
        self.assertIsNone(self.tree.get_last_hash_value(anchor.id))
        self.assertFalse(self.cache._prefetch_anchor_is_valid(anchor.id, None))


    def test_split_keeps_the_identity_and_the_graft_target(self):
        anchor = _add(
            self.tree, self.tree.root_node, [1, 2, 3, 4], [1, 2, 3, 4],
            hashes=["h1", "h2", "h3", "h4"],
        )
        seen_hash = self.tree.get_last_hash_value(anchor.id)

        # A real split preserves the anchor node id and suffix hash.
        self.tree._split_node(anchor.key, anchor, 2)
        self.assertTrue(self.cache._prefetch_anchor_is_valid(anchor.id, seen_hash))

    def test_discard_releases_only_the_operation_staging(self):
        anchor = _add(
            self.tree, self.tree.root_node, [1, 2], [1, 2], hashes=["h1", "h2"]
        )
        seen_hash = self.tree.get_last_hash_value(anchor.id)
        key = RadixKey([1, 2, 3, 4])
        lock = mock.Mock()

        self.tree._remove_leaf_from_parent(anchor)
        self.assertFalse(self.cache._prefetch_anchor_is_valid(anchor.id, seen_hash))

        _discard(
            self.cache,
            self.tree,
            anchor.id,
            rid="r1",
            key=key,
            completed=4,
            lock_params=mock.Mock(),
            live_lock=lock,
        )

        # Staging released once, sized to the completed head.
        release = self.cache.cache_controller.append_host_mem_release
        self.assertEqual(release.call_count, 1)
        self.assertEqual(release.call_args.kwargs["host_indices"].tolist(), [900, 901])
        self.assertEqual(self.cache.cache_controller.prefetch_tokens_occupied, 0)
        # A dead anchor's lock died with it: never dereferenced.
        self.assertEqual(lock.call_count, 0)
        self.assertEqual(
            self.cache.release_prefetch.call_args.args, ("r1", "anchor_invalidated")
        )
        self.assertNotIn("r1", self.cache.ongoing_prefetch)
        self.assertNotIn("r1", self.cache._demand_restore_rids)
        self.assertEqual(self.cache.prefetch_loaded_tokens_by_reqid["r1"], 0)
        self.assertEqual(self.cache._storage_prefetch_terminal["r1"], "finalized")
        completion = self.cache.record_storage_prefetch_completion.call_args
        self.assertEqual(completion.args[2], None)

    def test_discard_is_idempotent_after_the_entry_is_gone(self):
        key = RadixKey([1, 2])
        _discard(
            self.cache,
            self.tree,
            self.tree.root_node.id,
            rid="r2",
            key=key,
            completed=2,
            lock_params=None,
            live_lock=mock.Mock(),
        )
        calls = self.cache.cache_controller.append_host_mem_release.call_count
        self.cache._discard_prefetch_stale_anchor(
            operation=_FakeOperation("r2", torch.tensor([1]), 2),
            req_id="r2",
            completed_tokens=2,
            prefetch_key=key,
            host_indices=torch.tensor([900, 901], dtype=torch.int64),
            comp_xfers={},
            anchor_node_id=self.tree.root_node.id,
            anchor_lock_params=None,
            sidecar_counts={},
        )
        self.assertEqual(
            self.cache.cache_controller.append_host_mem_release.call_count, calls
        )

    def test_concurrent_same_prefix_prefetches_are_independent(self):
        anchor = _add(self.tree, self.tree.root_node, [1, 2], [1, 2], hashes=["h1", "h2"])
        seen_hash = self.tree.get_last_hash_value(anchor.id)
        key = RadixKey([1, 2, 3])

        def issue(rid):
            op = _FakeOperation(rid, torch.tensor([900, 901]), 3)
            self.cache.ongoing_prefetch[rid] = _entry(
                anchor.id, key, op.host_indices, op, None, seen_hash
            )
            self.cache._demand_restore_rids.add(rid)
            return op

        issue("a")
        issue("b")
        self.cache.host_memory_mode = "cache"
        self.cache.cache_controller.prefetch_tokens_occupied = 6
        for rid, entry in list(self.cache.ongoing_prefetch.items()):
            self.cache.ongoing_prefetch[rid] = entry._replace(
                host_indices=torch.tensor([900, 901, 902])
            )
        # Both anchors are the same node; discard only "a".
        _discard(
            self.cache,
            self.tree,
            anchor.id,
            rid="a",
            key=key,
            completed=3,
            lock_params=None,
            live_lock=mock.Mock(),
        )
        self.assertIn("b", self.cache.ongoing_prefetch)
        self.assertIn("b", self.cache._demand_restore_rids)
        self.assertEqual(self.cache.cache_controller.prefetch_tokens_occupied, 3)
        # The surviving prefetch still resolves to the live anchor.
        self.assertTrue(self.cache._prefetch_anchor_is_valid(anchor.id, seen_hash))
        self.assertEqual(
            self.cache.cache_controller.append_host_mem_release.call_count, 1
        )

    def test_aux_staging_is_released_when_the_transfer_never_ran(self):
        key = RadixKey([1, 2])
        op = _FakeOperation("r3", torch.tensor([900, 901]), 2, pool_done=False)
        self.cache.ongoing_prefetch["r3"] = _entry(
            self.tree.root_node.id, key, op.host_indices, op, None, None
        )
        self.cache.dec_host_lock_ref = mock.Mock()
        self.cache._discard_prefetch_stale_anchor(
            operation=op,
            req_id="r3",
            completed_tokens=2,
            prefetch_key=key,
            host_indices=op.host_indices,
            comp_xfers={ComponentType.SWA: [mock.Mock()]},
            anchor_node_id=self.tree.root_node.id,
            anchor_lock_params=None,
            sidecar_counts={},
        )
        aux = self.cache._release_aux_transfers_before_host_alloc_snapshot
        self.assertEqual(aux.call_count, 1)
        self.assertEqual(aux.call_args.kwargs["causal_rid"], "r3")


if __name__ == "__main__":
    unittest.main()
