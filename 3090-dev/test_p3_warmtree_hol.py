"""P3 deterministic warm-tree HOL verification (tester independent harness).

Reproduces the l3ack-e2 §1.5 closed loop that produced the 60s T13 cliff on
the pre-P3 baseline, and verifies the P3 reconcile heals it:

  deferred node (acked && !persisted, parent anchor cleared)
    -> frontier_anchor_ready == False forever
    -> frontier waiter parks until the 60s T13 timeout -> restore_recompute

The harness drives the REAL UnifiedTreeCore + REAL UnifiedRadixCache flush
path and uses ONLY pre-P3 (baseline-present) APIs so it runs identically on
both code versions:

  * On the BASELINE: after the deferred state is set up, the flush pass does
    NOT promote the deferred node and does NOT wake the frontier waiter --
    the permanent-HOL precondition (frontier_anchor_ready stays False until
    the 60s T13 timeout -> restore_recompute).
  * With P3: the same flush pass's reconcile promotes the deferred node,
    wakes the frontier waiter, and resolves the frontier well under 60s with
    restore_recompute(timeout)=0.

Self-contained deterministic unit harness (no GPU).
"""
import unittest
import torch
from types import SimpleNamespace

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache
from sglang.srt.mem_cache.unified_cache.components import (
    ComponentType as _component_type,
)

from test_storage_regression import _make_cache, _RealTreeCore


def _build_real_chain(cache, depth):
    """root -> n1 -> ... -> n{depth} under a REAL tree core."""
    params = SimpleNamespace(
        page_size=1,
        is_eagle=False,
        enable_session_radix_cache=False,
        eviction_policy="lru",
        token_to_kv_pool_allocator=None,
        enable_kv_cache_events=False,
    )
    tree_core = _RealTreeCore(
        params,
        {
            _component_type.FULL: SimpleNamespace(tree_core=None),
            _component_type.MAMBA: SimpleNamespace(tree_core=None),
        },
    )
    tree_core.is_write_back = True
    tree_core.enable_storage = True  # cache.enable_storage proxies to it
    cache.tree_core = tree_core
    nodes = []
    parent = tree_core.root_node
    for i in range(depth):
        n = tree_core._new_node()
        n.parent = parent
        parent.children[f"n{i}"] = n
        nodes.append(n)
        parent = n
    return tree_core, nodes


# The T13 timeout the scheduler uses for restore_recompute.
T13_TIMEOUT_S = 60.0


class P3WarmTreeHOLTest(unittest.TestCase):
    """Deterministic reproduction of the durable-frontier HOL and its healing."""

    @unittest.skipIf(torch is None, "real UnifiedTreeCore needs torch")
    def test_deferred_node_heals_and_wakes_frontier_on_reconcile(self):
        cache = _make_cache()
        tree_core, (a, b) = _build_real_chain(cache, 2)

        # 1) a becomes a persisted anchor.
        self.assertEqual(tree_core.advance_storage_persisted(a.id), [a.id])
        self.assertTrue(tree_core.is_storage_persisted(a.id))
        self.assertTrue(cache.frontier_anchor_ready(a.id))

        # 2) a's durable belief is cleared (revoke-miss clear) while b is not
        #    yet acked -- the B guard allows this clear (no acked descendant).
        tree_core.clear_storage_durable(a.id)
        self.assertFalse(tree_core.is_storage_persisted(a.id))
        self.assertFalse(tree_core.is_l3_durable(a.id))

        # 3) b acks under the now-unpersisted a: b is DEFERRED
        #    (storage_acked && !storage_persisted) -- the permanent-HOL seed.
        tree_core.advance_storage_persisted(b.id)
        self.assertTrue(b.storage_acked)
        self.assertFalse(tree_core.is_storage_persisted(b.id))

        # 4) The scheduler parks a frontier waiter on b. On the PRE-P3 baseline
        #    the per-pass predicate is dead: frontier_anchor_ready(b) is False
        #    forever, so the waiter sits until the 60s T13 timeout.
        cache.register_frontier_waiter("r1", b.id)
        self.assertFalse(cache.frontier_anchor_ready(b.id))
        self.assertIn(b.id, cache._storage_frontier_waiters)
        self.assertNotIn("r1", cache._storage_frontier_ready)

        # 5) The ack-drain flush pass runs (the per-pass event-loop drain).
        #    With P3 this invokes the deferred-ACK reconcile; on the baseline
        #    there is no reconcile.
        cache._flush_pending_storage_writes()

        # THE P3 CONTRACT: the deferred node must be healed in this pass --
        # promoted, durable, its frontier waiter woken -- so the frontier
        # resolves well under the 60s T13 timeout with restore_recompute=0.
        # On the pre-P3 baseline this assertion FAILS: b stays unpersisted,
        # frontier_anchor_ready(b) stays False, and the waiter is never woken
        # (parked until the 60s timeout -> restore_recompute("timeout")).
        self.assertTrue(
            cache.frontier_anchor_ready(b.id),
            "deferred node must heal in the flush pass (P3 reconcile); on "
            "the pre-P3 baseline frontier_anchor_ready stays False forever "
            "-> parked until 60s T13 timeout -> restore_recompute(timeout)",
        )
        self.assertTrue(tree_core.is_storage_persisted(b.id))
        self.assertTrue(cache.pop_frontier_ready("r1"))

    @unittest.skipIf(torch is None, "real UnifiedTreeCore needs torch")
    def test_chain_of_deferred_nodes_heals_in_single_pass(self):
        """A 4-deep chain all acked under a cleared anchor heals in one
        reconcile pass, matching the frozen 37-node warm-tree shape."""
        cache = _make_cache()
        tree_core, (a, b, c, d) = _build_real_chain(cache, 4)

        # a is the original persisted anchor; clear it (revoke-miss) before
        # the descendants ack.
        tree_core.advance_storage_persisted(a.id)
        tree_core.clear_storage_durable(a.id)

        # Descendants ack bottom-up; all deferred under the unpersisted a.
        for n in (d, c, b):
            tree_core.advance_storage_persisted(n.id)
        self.assertFalse(cache.frontier_anchor_ready(d.id))

        # Park waiters on the deepest node (frontier HOL).
        cache.register_frontier_waiter("r1", d.id)
        self.assertNotIn("r1", cache._storage_frontier_ready)

        # Single flush pass (with P3 reconcile) heals the whole chain.
        cache._flush_pending_storage_writes()
        self.assertTrue(cache.frontier_anchor_ready(d.id))
        self.assertTrue(cache.pop_frontier_ready("r1"))
        for n in (a, b, c, d):
            self.assertTrue(tree_core.is_storage_persisted(n.id))


if __name__ == "__main__":
    unittest.main(verbosity=2)
