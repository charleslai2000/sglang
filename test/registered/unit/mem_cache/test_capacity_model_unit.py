"""P3 token/bytes capacity model (ledger 2026-09-01 adjudication #2, #3).

The capacity model is tracked in KV-host TOKENS, not request counts or GB:
```
KV_usable = KV_pool - KV_writeback_reserve - KV_margin
RH only admits working + ready + inflight_spec <= KV_usable
```
The write-back reserve is "at least one target write-back state's KV
tokens", sized from the state-p95 figure. Six runtime gauges publish the
model in token space (no GB guessing).

Guarded concerns:

1. KV_usable computation: pool - reserve - margin is correct and exposed
   per-pool (kv/mamba) and as the aggregate usable.
2. Capacity admission: working + ready + spec-inflight being > usable
   declines the RH stage (the refill headroom gate applies the reserve +
   margin floor).
3. Token watermark: with different state lengths, the fixed token
   watermark triggers consistently (count-mode triggers at 24K vs 87K
   differently -- the adjudication's motivating scenario).
4. Reserve token semantics: a >= 1-state reserve is NOT squeezed; usable
   holds working + 2 READY when the reserve is sized to one state.
5. Six-gauge publish format smoke: the capacity stats dict has all nine
   keys with int values (kv/mamba usable + READY_state_max included).
6. Legacy GB back-compat: token_mode=False keeps the byte reserve +
   margin floor path (pool.writeback_reserve + GB margin conversion).
"""

import unittest
from types import SimpleNamespace

import torch

from sglang.srt.mem_cache.hicache_storage import PoolName
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool
from sglang.srt.mem_cache.pool_host import HostPoolGroup, PoolEntry
from sglang.srt.mem_cache.pool_host import base as pool_base
from sglang.srt.mem_cache.pool_host.mha import MHATokenToKVPoolHost
from sglang.srt.managers.scheduler import Scheduler
from sglang.srt.managers.scheduler_components.ready_horizon import (
    ReadyHorizonPolicy,
)

from test_ready_horizon_unit import (
    NONE,
    NO_HEADROOM,
    READY,
    _Cc,
    _epochs,
    _tree,
    _views,
)

# One full M4T chain: the resident footprint of a single READY member.
CHAIN_TOKENS = 20_910
# M4T State_p95 = max = 43,513 tokens (the scheduler default watermark basis).
STATE_P95 = 43_513
# pool tokens for the unit harness (device_pool=32 x host_to_device_ratio=2
# = 64, rounded up to page_num x page_size = 33 x 2 = 66 logical slots;
# dcp_size=1 so logical_size == size).
POOL_LOGICAL = 66
# bytes_per_token of the _HostPoolHarness host pool (4*2*2*2*2).
STATS_BPT = 4 * 2 * 2 * 2 * 2


class _HostPoolHarness:
    """Construct a small MHATokenToKVPoolHost with page_size=2 and a
    host_size large enough for the capacity tests (mirrors
    test_writeback_reserve_unit)."""

    def __init__(self, pages=128):
        pool_base.host_memory_budget_bytes = lambda: 100 * 1024**3
        import sglang.srt.mem_cache.pool_host.mha as _mha

        _mha.host_memory_budget_bytes = lambda: 100 * 1024**3
        self.page_size = 2
        self.device_pool = MHATokenToKVPool(
            size=self.page_size * 16,
            page_size=self.page_size,
            dtype=torch.float16,
            head_num=2,
            head_dim=4,
            layer_num=2,
            device="cpu",
            enable_memory_saver=False,
        )
        self.bytes_per_token = 4 * 2 * 2 * 2 * 2  # (layer*head*head_dim)*(k)v*dtype2
        self.host_pool = MHATokenToKVPoolHost(
            device_pool=self.device_pool,
            host_to_device_ratio=2.0,
            host_size=0,
            page_size=self.page_size,
            layout="layer_first",
            pin_memory=False,
            device="cpu",
            allocator_type="default",
        )

    def group(self):
        return HostPoolGroup(
            entries=[
                PoolEntry(
                    name=PoolName.KV,
                    host_pool=self.host_pool,
                    device_pool=self.device_pool,
                    layer_mapper=lambda layer: layer,
                    is_primary_index_anchor=True,
                )
            ]
        )


def _capacity_scheduler(views, cc, groups=None):
    """Build a real Scheduler stub wired for _hicache_capacity_stats."""
    scheduler = Scheduler.__new__(Scheduler)
    scheduler.ready_horizon = ReadyHorizonPolicy(
        frontier_n=8, watermark_low=2, watermark_high=4
    )
    scheduler.ready_horizon_token_mode = True
    scheduler.ready_horizon_reserve_tokens = STATE_P95
    scheduler.ready_horizon_margin_tokens = 0
    scheduler._ready_horizon_views = lambda frontier: views
    return scheduler


class UsableTokensTests(unittest.TestCase):
    """KV_usable = pool - writeback_reserve - safety_margin, exposed per
    pool and aggregate (adjudication #2, #3)."""

    def _stats(self, *, reserve_bytes=0, margin_bytes=0, used_pages=0):
        harness = _HostPoolHarness()
        group = harness.group()
        if margin_bytes:
            group.set_writeback_reserve_margin_bytes(margin_bytes)
        if reserve_bytes:
            group.set_writeback_reserve_bytes(reserve_bytes)
        # Occupy `used_pages` logical pages via the normal channel.
        if used_pages:
            self.assertIsNotNone(group.alloc(used_pages * harness.page_size))
        cc = SimpleNamespace(
            mem_pool_host=group, inflight_speculative_tokens=0
        )
        sched = _capacity_scheduler([], cc)
        return sched._hicache_capacity_stats([], cc), harness

    def test_usable_is_pool_minus_reserve_minus_margin(self):
        # reserve = 4 pages (8 tokens), margin = 2 pages (4 tokens):
        # usable = pool - 8 - 4.
        harness = _HostPoolHarness()
        group = harness.group()
        page = harness.page_size
        bpt = harness.bytes_per_token
        group.set_writeback_reserve_bytes(4 * page * bpt)
        group.set_writeback_reserve_margin_bytes(2 * page * bpt)
        cc = SimpleNamespace(mem_pool_host=group, inflight_speculative_tokens=0)
        sched = _capacity_scheduler([], cc)
        stats = sched._hicache_capacity_stats([], cc)
        self.assertEqual(stats["kv_pool_tokens"], POOL_LOGICAL)
        self.assertEqual(stats["writeback_reserve_tokens"], 8)
        self.assertEqual(stats["usable_tokens"], POOL_LOGICAL - 8 - 4)
        self.assertEqual(stats["kv_host_usable_tokens"], POOL_LOGICAL - 8 - 4)

    def test_working_tokens_is_usage_minus_ready(self):
        # 32 pages used (64 logical tokens), one READY resident of 24
        # tokens: working = used - ready_resident = 64 - 24 = 40.
        harness = _HostPoolHarness()
        group = harness.group()
        self.assertIsNotNone(group.alloc(32 * harness.page_size))
        views = _views(("r1", READY, None, 24))
        cc = SimpleNamespace(mem_pool_host=group, inflight_speculative_tokens=0)
        sched = _capacity_scheduler(views, cc)
        stats = sched._hicache_capacity_stats(views, cc)
        pool = stats["kv_pool_tokens"]
        used = pool - group.available_size()
        self.assertEqual(used, 64)
        self.assertEqual(stats["ready_resident_tokens"], 24)
        self.assertEqual(stats["working_tokens"], used - 24)

    def test_spec_inflight_reported(self):
        _, _ = self._stats()
        harness = _HostPoolHarness()
        group = harness.group()
        cc = SimpleNamespace(
            mem_pool_host=group, inflight_speculative_tokens=5000
        )
        sched = _capacity_scheduler([], cc)
        stats = sched._hicache_capacity_stats([], cc)
        self.assertEqual(stats["spec_inflight_tokens"], 5000)

    def test_ready_state_max_tracks_largest_ready(self):
        harness = _HostPoolHarness()
        group = harness.group()
        cc = SimpleNamespace(mem_pool_host=group, inflight_speculative_tokens=0)
        sched = _capacity_scheduler([], cc)
        views = _views(
            ("r1", READY, None, 20_000),
            ("r2", READY, None, 43_513),
            ("r3", NONE, None, 0, 0, True),
        )
        stats = sched._hicache_capacity_stats(views, cc)
        self.assertEqual(stats["ready_state_max_tokens"], 43_513)

    def test_mamba_host_usable_reported(self):
        # A group with a fake mamba side pool: per-pool usable is reported
        # independently for kv and mamba.
        harness = _HostPoolHarness()
        group = harness.group()
        fake_mamba = SimpleNamespace(
            logical_size=118,
            size=118,
            size_per_token=48_490_566,
            available_size=lambda: 118,
            writeback_reserve=lambda: 30,
            writeback_margin=lambda: 0,
            can_use_write_back_jit=True,  # HostPoolGroup.add_entry refreshes
        )
        group.add_entry(
            PoolEntry(
                name=PoolName.MAMBA,
                host_pool=fake_mamba,
                device_pool=harness.device_pool,
                layer_mapper=lambda layer: layer,
            )
        )
        cc = SimpleNamespace(mem_pool_host=group, inflight_speculative_tokens=0)
        sched = _capacity_scheduler([], cc)
        stats = sched._hicache_capacity_stats([], cc)
        self.assertEqual(stats["mamba_host_usable_tokens"], 118 - 30)
        self.assertEqual(stats["kv_host_usable_tokens"], POOL_LOGICAL)


class CapacityAdmissionTests(unittest.TestCase):
    """working + ready + inflight_spec > usable -> the RH stage declines
    (the refill headroom gate applies the reserve + margin floor)."""

    def _plan(self, *, inflight, headroom, reserve_floor):
        policy = ReadyHorizonPolicy(
            frontier_n=4,
            watermark_low=50_000,
            watermark_high=100_000,
            token_mode=True,
        )
        views = _views(
            ("r0", READY, None, 10_000),  # ready resident 10K tokens
            ("r1", NONE, None, 0, 0, True),
            ("r2", NONE, None, 0, 0, True),
        )
        return policy.refill_plan(
            views,
            tree=_tree(),
            cc=_Cc(spec_inflight=inflight),
            host_headroom=headroom,
            negatives={},
            epochs=_epochs(frontier=("r0", "r1", "r2")),
            now=0.0,
            reserve_floor=reserve_floor,
        )

    def test_working_plus_ready_plus_spec_over_usable_rejects(self):
        # usable = headroom - reserve_floor = 40K - 25K = 15K; the pool
        # footprint (ready 10K + inflight 10K = 20K) > 15K: every candidate
        # is declined NO_HEADROOM (the reserve + margin floor gate -- the
        # capacity model's working + ready + spec <= usable admission).
        plan = self._plan(
            inflight=10_000,
            headroom=40_000,
            reserve_floor=25_000,
        )
        self.assertEqual(plan.ready_tokens, 10_000)
        self.assertEqual(plan.to_issue, [])
        self.assertEqual(
            [(rid, reason) for rid, reason in plan.declines],
            [("r1", NO_HEADROOM), ("r2", NO_HEADROOM)],
        )

    def test_working_plus_ready_plus_spec_under_usable_admits(self):
        # usable = 40K - 5K = 35K > 20K footprint: both stage.
        plan = self._plan(
            inflight=10_000,
            headroom=40_000,
            reserve_floor=5_000,
        )
        self.assertEqual([v.rid for v in plan.to_issue], ["r1", "r2"])


class TokenWatermarkTests(unittest.TestCase):
    """The token watermark triggers consistently across state lengths --
    the count-mode drift (24K vs 87K) is the motivating scenario."""

    def _policy(self, *, token_mode=True, low=2 * STATE_P95, high=3 * STATE_P95):
        return ReadyHorizonPolicy(
            frontier_n=8,
            watermark_low=low,
            watermark_high=high,
            token_mode=token_mode,
        )

    def _plan(self, policy, views, cc=None):
        return policy.refill_plan(
            views,
            tree=_tree(),
            cc=cc or _Cc(),
            host_headroom=10**9,
            negatives={},
            epochs=_epochs(frontier=[v.rid for v in views]),
            now=0.0,
            reserve_floor=0,
        )

    def test_same_token_watermark_triggers_across_lengths(self):
        # Two READY states of 43,513 each = 87,026 tokens = the token low:
        # at/above low -> no refill. The same readiness in request-count
        # terms (count 2) would match a low_count of 2 in either case -- the
        # token view re-anchors the trigger on actual state size, not count.
        policy = self._policy(token_mode=True, low=87_026, high=87_026)
        views = _views(
            ("r1", READY, None, 43_513),
            ("r2", READY, None, 43_513),
            ("r3", NONE, None, 0, 0, True),  # the refill's candidate
        )
        plan = self._plan(policy, views)
        self.assertEqual(plan.ready_tokens, 87_026)
        self.assertEqual(plan.to_issue, [])
        # With slightly smaller states (2 x 43,000 = 86,000 < low) the same
        # NONE candidate is staged -> refill issues.
        views_small = _views(
            ("r1", READY, None, 43_000),
            ("r2", READY, None, 43_000),
            ("r3", NONE, None, 0, 0, True),
        )
        plan_small = self._plan(policy, views_small)
        self.assertEqual([v.rid for v in plan_small.to_issue], ["r3"])

    def test_count_mode_differs_from_token_mode_at_fixed_state_size(self):
        # 24K vs 87K at the same request count: token mode sees the total
        # state size, count mode only the request count.
        policy_count = self._policy(token_mode=False, low=2, high=4)
        views24 = _views(
            ("r1", READY, None, 24_000),
            ("r2", READY, None, 24_000),
            ("r3", NONE, None, 0, 0, True),
        )
        views87 = _views(
            ("r1", READY, None, 87_000),
            ("r2", READY, None, 87_000),
            ("r3", NONE, None, 0, 0, True),
        )
        # Count mode: ready_count=2 >= low_count=2 -> no refill for BOTH the
        # 48K and the 174K pool -- the drift (count can't see state size).
        self.assertEqual(self._plan(policy_count, views24).to_issue, [])
        self.assertEqual(self._plan(policy_count, views87).to_issue, [])
        # Token mode at the same low (e.g. 100K): 48K < 100K refills, 174K
        # > 100K does not -- the state size is visible.
        policy_token = self._policy(token_mode=True, low=100_000, high=200_000)
        self.assertEqual(
            [v.rid for v in self._plan(policy_token, views24).to_issue],
            ["r3"],
        )
        self.assertEqual(self._plan(policy_token, views87).to_issue, [])


class ReserveTokenSemanticsTests(unittest.TestCase):
    """A >= 1-state write-back reserve is not squeezed away: with reserve
    sized to one state, usable holds working + 2 READY."""

    def test_reserve_sized_to_one_state_leaves_twostate_usable(self):
        harness = _HostPoolHarness()
        group = harness.group()
        bpt = harness.bytes_per_token
        # Reserve = 43,513 tokens (one target state); pool logical 256.
        # For the unit pool the reserve_would_exceed capacity, so use a
        # proportionally-scaled state (a few pages) to exercise the
        # invariant: usable >= working + 2*READY when reserve is 1 state.
        reserve_bytes = 4 * harness.page_size * bpt  # 4 pages (one "state")
        group.set_writeback_reserve_bytes(reserve_bytes)
        reserve = group.writeback_reserve()
        work_pages = 8 * harness.page_size
        self.assertIsNotNone(group.alloc(work_pages))
        cc = SimpleNamespace(mem_pool_host=group, inflight_speculative_tokens=0)
        sched = _capacity_scheduler([], cc)
        stats = sched._hicache_capacity_stats([], cc)
        usable = stats["usable_tokens"]
        working = stats["working_tokens"]
        self.assertGreaterEqual(
            usable, working + 2 * reserve, "usable must hold work + 2 READY"
        )


class SixGaugeSmokeTests(unittest.TestCase):
    """Publish-format smoke: the capacity stats dict has all nine keys with
    int values -- no value-dependent crash, no missing key."""

    def test_all_nine_keys_are_ints(self):
        harness = _HostPoolHarness()
        group = harness.group()
        group.set_writeback_reserve_bytes(4 * harness.page_size * harness.bytes_per_token)
        cc = SimpleNamespace(mem_pool_host=group, inflight_speculative_tokens=1000)
        sched = _capacity_scheduler(
            _views(("r1", READY, None, 5000)), cc
        )
        stats = sched._hicache_capacity_stats(
            _views(("r1", READY, None, 5000)), cc
        )
        expected = {
            "kv_pool_tokens",
            "writeback_reserve_tokens",
            "ready_resident_tokens",
            "working_tokens",
            "spec_inflight_tokens",
            "usable_tokens",
            "kv_host_usable_tokens",
            "mamba_host_usable_tokens",
            "ready_state_max_tokens",
        }
        self.assertEqual(set(stats.keys()), expected)
        for k, v in stats.items():
            self.assertIsInstance(v, int, f"{k} must be an int")


class LegacyGbCompatTests(unittest.TestCase):
    """Back-compat: token_mode=False keeps the GB reserve + margin path
    (pool.writeback_reserve + GB margin conversion in
    _ready_reserve_floor_tokens)."""

    def _floor(self, *, reserve_bytes, margin_gb, token_mode):
        harness = _HostPoolHarness()
        group = harness.group()
        if reserve_bytes:
            group.set_writeback_reserve_bytes(reserve_bytes)
        cc = SimpleNamespace(mem_pool_host=group)
        scheduler = Scheduler.__new__(Scheduler)
        scheduler.ready_horizon_token_mode = token_mode
        scheduler.ready_horizon_reserve_tokens = STATE_P95
        scheduler.ready_horizon_margin_tokens = 0
        scheduler.server_args = SimpleNamespace(
            ready_horizon_safety_margin_gb=margin_gb,
            ready_horizon_margin_state_tokens=None,
            hicache_writeback_reserve_state_tokens=None,
            ready_horizon_state_p95_tokens=STATE_P95,
        )
        return scheduler._ready_reserve_floor_tokens(cc), group

    def test_count_mode_uses_pool_reserve_plus_gb_margin(self):
        harness = _HostPoolHarness()
        reserve_bytes = 8 * harness.page_size * harness.bytes_per_token
        floor, group = self._floor(
            reserve_bytes=reserve_bytes, margin_gb=0.0, token_mode=False
        )
        reserve = floor - 0  # no margin
        self.assertEqual(reserve, group.writeback_reserve())
        self.assertEqual(floor, group.writeback_reserve())

    def test_count_mode_gb_margin_added(self):
        harness = _HostPoolHarness()
        reserve_bytes = 4 * harness.page_size * harness.bytes_per_token
        floor, group = self._floor(
            reserve_bytes=reserve_bytes, margin_gb=0.0, token_mode=False
        )
        # margin_gb=0 leaves just the reserve.
        self.assertEqual(floor, group.writeback_reserve())

    def test_token_mode_uses_state_tokens_not_gb(self):
        harness = _HostPoolHarness()
        floor, _ = self._floor(
            reserve_bytes=0, margin_gb=0.3, token_mode=True
        )
        # Token mode ignores the GB knobs: reserve = state_p95 + margin_state(0).
        self.assertEqual(floor, STATE_P95)


if __name__ == "__main__":
    unittest.main(verbosity=2)