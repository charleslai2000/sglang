"""P3 Ready Horizon v0 (3.2): the READY_HOST pool maintenance policy.

Pure, torch-free collaborator of the scheduler (large-class-style: the
domain logic lives here, scheduler.py only delegates). The scheduler feeds
the policy a frontier of frozen request views plus read-only tree /
controller references; every method returns a value or a plan and mutates
nothing (including the negatives dict -- it is a frozen input; the
scheduler owns its lifecycle).

Design (phase2-hicache-design/ledger.md 2026-09-01 user adjudication, M3
rework): the M3 gate is per-rid causal negative-cache eligibility, NOT an
epoch_sig + cooldown patch.

- M6 strict membership: a pool member is READY and its required prefix is
  physically resident in the host tree (staged_tokens > 0 -- the marker
  the prefetch finalize writes and admission consumes via
  pop_prefetch_loaded_tokens). Under the v0 conservative staging rule the
  resident span must be the FULL requested prefix.
- M1/M2 headroom: the READY pool plus inflight speculative staging fit the
  host headroom; a shortfall declines silently -- speculative staging never
  evicts.
- M3 event-driven refill: a check may run only on a causal-epoch event
  plus a low-frequency periodic safety reconciliation (seconds), never a
  per-pass poll. The events are the five causal epochs:
    l3_publish       -- L3 durable/publish advance (monotonic),
    host_headroom    -- host available pages (level signal; up = release),
    host_release     -- MONOTONIC host-capacity release counter (genuine
                        releasing events: host residency freed, ready
                        eviction, working-state release) -- Fix A: the
                        NO_HEADROOM waiter subscribes to THIS, not the
                        transient available level, which flips on every
                        alloc/free and can never sustain past the decline
                        cursor under a full working set (the B-run
                        permanent freeze),
    spec_budget      -- speculative budget in flight (release = down),
    waiting_frontier -- the frontier composition (a candidate entered/left).
  Each decline reason subscribes to exactly the epoch that can change its
  outcome:
    NO_L3       -> l3_publish
    NO_HEADROOM -> host_release
    SPEC_BUDGET -> spec_budget
  Identity events (request prefix changed, request generation changed) are
  causal for every park: they change what the rid is asking for, so the
  old negative judgment no longer applies.
- Negative cache (per-rid, causal): a staged request that declines records
  a per-rid negative-cache entry carrying the subscribed epoch's cursor at
  the decline. The rid is not re-eligible until the subscribed epoch
  advanced past that cursor -- NOT on the next pass, NOT on a READY pool
  change, NOT on running-batch change (e7: the non-directional signature
  ran the refill at ~141/s and self-sustained a miss issue->revoke->
  re-issue spin, 1289 issues / 9.04s for one rid). Deterministic L3 misses
  are not transient: the revoke releases the budget and would re-arm the
  next pass without the park.
- Safety fuse: a time-based per-rid issue-rate cap for anomalous retry
  storms; the correct-path retry cadence is causal (the subscribed epoch
  advanced), not time. The fuse only bounds pathological behavior.
- One probe per causal epoch: a rid whose park cleared on a causal event
  is eligible for exactly one fresh attempt in that epoch; the next
  attempt (declined -> fresh entry, issued -> no entry, finalize -> READY)
  records the cursor it happened at, so the "at most one attempt per
  causal epoch" semantic is inherent to the cursor comparison, not a
  counted gate.
- M2 no-evict staging: the plan declines silently (empty to_issue) when
  the host-headroom gate fails or the inflight budgets are exhausted;
  nothing here ever evicts host pages.
- M4 READY-first admission order: partition_ready_first reorders the
  calc_priority output between sorting and PrefillAdder -- stable, scoped
  to each maximal run of equal explicit priority (explicit priority >
  READY > base policy), READY members (M6) first. Off = the scheduler
  never calls it and the calc_priority order stands.
"""

from enum import Enum, auto
from typing import Optional

import msgspec

from sglang.srt.managers.scheduler_components.hicache_restore import (
    RestoreState,
    RestoreWaitReason,
)

#: Periodic safety reconciliation cadence (M3): the fallback that catches
#: lost resource events; seconds, never the per-pass path.
SAFETY_RECONCILE_INTERVAL_S = 5.0

#: Safety-fuse window (M3, user adjudication): a time-based issue-rate cap
#: for anomalous retry storms only. The correct-path retry cadence is
#: causal (the subscribed epoch advanced), never time -- a deterministic
#: L3 miss stays a miss no matter how long you wait. The fuse bounds only
#: a pathological repeat-fail loop. It is ALSO the no-headroom re-probe
#: debounce (Fix A requirement: repeated wakeup must be debounced): a
#: NO_HEADROOM park that clears on a release epoch still holds for the
#: fuse window after the decline, so a structurally-exhausted headroom
#: (working set at full, release after release) re-probes at most once per
#: fuse window instead of on every tiny release (one probe per release
#: epoch, at most one per fuse window).
SAFETY_FUSE_S = 1.0


class DeclineReason(Enum):
    """Why a staging attempt declined (the per-rid negative-cache reason).

    Each reason subscribes to exactly one causal epoch (the one that can
    change its outcome); the epoch-clear logic resolves that subscription.
    """

    NO_L3 = auto()  # deterministic miss: the full requested prefix is not in L3
    NO_HEADROOM = auto()  # host headroom gate failed
    SPEC_BUDGET = auto()  # speculative inflight budget exhausted


class NegativeCacheEntry(msgspec.Struct):
    """The per-rid causal park: the subscribed epoch's cursor at the
    decline, the request identity fingerprint (a prefix/generation change
    is causal for every park), and the safety-fuse expiry bounding an
    anomalous repeat-fail loop."""

    reason: DeclineReason
    epoch_cursor: int
    fuse_expiry: float
    prefix_len: int
    generation: Optional[int] = None


class ReadyHorizonView(msgspec.Struct):
    """Frozen per-request frontier view the scheduler builds for the
    policy (a pure input; the policy never touches the Req itself)."""

    req: object  # the scheduler Req (identity only; the pass issues on it)
    rid: str
    state: Optional[RestoreState]
    wait_reason: Optional[RestoreWaitReason]
    staged_tokens: int  # physically resident host-tree prefix (M6 marker)
    # full_prefix: resident material present (staged marker > 0) AND the
    # resident span is the FULL requested prefix (v0 conservative staging).
    full_prefix: bool
    host_hit_length: int
    staging_eligible: bool  # restore potential; NONE-state candidates only
    prefix_len: int  # request identity fingerprint (total prompt length)
    generation: Optional[int] = None  # session generation (identity fingerprint)


class RefillPlan(msgspec.Struct):
    """One refill decision: the M6 pool snapshot, the ordered issue list
    (frontier order, capped at watermark_high - ready_count) and the
    decline attributions -- the causal-eligible candidates that WOULD have
    been issued but for the headroom gate. The scheduler records each
    attribution as a per-rid negative-cache entry; SPEC_BUDGET attributions
    are recorded by the pass from the synchronous issue outcomes (only the
    pass observes the budget state after an actual issue)."""

    ready_count: int
    ready_tokens: int
    to_issue: list  # of ReadyHorizonView
    declines: list  # of (rid, DeclineReason) attributions (NO_HEADROOM)
    candidates: list  # the full causal-eligible candidate list (for the
    # pass's post-issue SPEC_BUDGET attribution of the un-tried tail)


class CausalEpochs(msgspec.Struct):
    """The five causal-epoch snapshot values the policy subscribes to.
    Built each pass by the scheduler; epoch_event compares it
    directionally against the previous pass's snapshot. Only the
    subscribed-epoch deltas are events; the refill's own traffic (issues
    raise inflight, consume headroom) is not."""

    l3_publish: int  # monotonic L3 durable/publish counter (up = event)
    host_headroom: int  # host available pages (up = event; level signal)
    host_release: int  # monotonic host-capacity release counter (up = event;
    # genuine capacity-releasing events -- host residency freed, ready
    # eviction, working-state release -- NOT the available level, which
    # flips on every alloc/free and can never sustain past the decline
    # cursor under a full working set (Fix A: the NO_HEADROOM waiter
    # subscribes to the release epoch, not the transient level).)
    spec_budget: int  # speculative inflight tokens (down = event)
    waiting_frontier: tuple  # frontier rids, any change = event


class ReadyHorizonPolicy:
    """The ready-pool maintenance policy (3.2): who is a pool member
    (M6), who may be staged (candidates), when a refill may run (M3), and
    how much the pool may occupy (M1/M2 headroom)."""

    def __init__(
        self,
        *,
        frontier_n: int = 8,
        watermark_low: int = 2,
        watermark_high: int = 4,
        safety_fuse_s: float = SAFETY_FUSE_S,
        safety_interval_s: float = SAFETY_RECONCILE_INTERVAL_S,
        token_mode: bool = False,
    ):
        assert watermark_high >= watermark_low, (
            "ready_host_watermark_high must be >= ready_host_watermark_low"
        )
        self.frontier_n = frontier_n
        self.watermark_low = watermark_low
        self.watermark_high = watermark_high
        # Token capacity watermarks (ledger 2026-09-01 adjudication #1): a
        # fixed request count is not a stable resource target when state
        # length varies (p50 11.9K / p90 34.8K / max 43.5K on the 3090 rig);
        # the refill trigger and cap are TOKENS. The class default is the
        # legacy count fallback; the scheduler engages token semantics via
        # the new token server_args (init_ready_horizon passes token_mode
        # explicitly), so direct policy construction stays on count.
        self.token_mode = token_mode
        self.safety_fuse_s = safety_fuse_s
        self.safety_interval_s = safety_interval_s

    def _watermark_tokens(self, view) -> int:
        """The refill-charge for one request: the tokens its staging would
        add to the READY pool. The requested-prefix length is the accurate
        estimate of the full state a full-prefix restore stages; the M6
        staged marker is what the pool already holds. Token mode weights
        each staging decision by actual state size rather than a flat
        request count."""
        return max(view.prefix_len, view.staged_tokens)

    def _below_low(self, ready_count: int, ready_tokens: int) -> bool:
        """Whether the pool is below the configured watermark: token
        comparison in token mode (the stable resource target), request-
        count comparison in legacy count mode."""
        if self.token_mode:
            return ready_tokens < self.watermark_low
        return ready_count < self.watermark_low

    def _issue_budget(self, ready_count: int, ready_tokens: int) -> int:
        """The per-pass issuance budget: enough staging to reach the HIGH
        token watermark (token mode) or the HIGH count watermark (count
        mode, high - ready_count -- the pre-token-semantics cap). Expressed
        in the same unit the issue loop accumulates (tokens in token mode,
        requests in count mode)."""
        if self.token_mode:
            return max(0, self.watermark_high - ready_tokens)
        return max(0, self.watermark_high - ready_count)

    def describe_watermarks(self) -> str:
        """A human-readable watermark description for [P3] logs: the low/
        high pair, in the mode's unit (tokens in token mode) or the legacy
        request-count pair -- the magnitude distinguishes them (a 43K/87K
        token pair vs a 2/4 request-count pair)."""
        return f"{self.watermark_low}/{self.watermark_high}"


    def frontier(self, waiting_queue, n: Optional[int] = None) -> list:
        """The staging input: the first N requests in current queue order
        (the scheduler has no per-agent lookahead; the queue order is the
        admission order this pass would see)."""
        return waiting_queue[: (self.frontier_n if n is None else n)]

    @staticmethod
    def _is_ready_resident(view) -> bool:
        # M6: the finalize writes the staged marker (the loaded span is
        # physically in the host tree) and admission pops it; a READY
        # without resident material (dropped insert, consumed, foreign
        # path) is not pool material. The full_prefix gate (v0 conservative
        # staging) keeps a partial restore out of the READY pool.
        return (
            view.state is RestoreState.READY
            and view.staged_tokens > 0
            and view.full_prefix
        )

    def ready_count(self, views) -> int:
        """M6 strict pool size: READY members with a physically resident
        full prefix that is not consumed/inflight."""
        return sum(1 for view in views if self._is_ready_resident(view))

    def ready_resident_tokens(self, views) -> int:
        """Host-tree tokens held by the M6 pool members."""
        return sum(
            view.staged_tokens for view in views if self._is_ready_resident(view)
        )

    # ---- M3 causal epochs ----

    @staticmethod
    def subscribed_epoch(reason: DeclineReason) -> str:
        """The single causal epoch whose advance can change this decline
        reason's outcome (user adjudication subscription table):
        NO_L3 -> l3_publish, NO_HEADROOM -> host_release (the MONOTONIC
        release counter -- Fix A: a park that is declined because host
        headroom could not fit the stage clears only on a genuine
        capacity-releasing event, not on the transient available level,
        which flips on every alloc/free and can never sustain past the
        decline cursor under a full working set),
        SPEC_BUDGET -> spec_budget."""
        if reason is DeclineReason.NO_L3:
            return "l3_publish"
        if reason is DeclineReason.NO_HEADROOM:
            return "host_release"
        return "spec_budget"

    @staticmethod
    def _epoch_value(epochs: CausalEpochs, name: str) -> int:
        return getattr(epochs, name)

    @staticmethod
    def entry_cleared(
        entry: NegativeCacheEntry,
        view: ReadyHorizonView,
        epochs: CausalEpochs,
        now: float,
    ) -> bool:
        """Whether a parked rid may be re-considered: the subscribed
        causal epoch advanced past the decline cursor, OR the request
        identity changed (prefix/generation -- a new question deserves a
        new probe), OR the safety fuse expired (the anomalous repeat-fail
        bound). A deterministic L3 miss is not transient: it stays parked
        until exactly one of these causal events occurs."""
        if now < entry.fuse_expiry:
            return False
        name = ReadyHorizonPolicy.subscribed_epoch(entry.reason)
        cur = ReadyHorizonPolicy._epoch_value(epochs, name)
        if name == "spec_budget":
            # Budget released: inflight dropped below the decline cursor.
            if cur < entry.epoch_cursor:
                return True
        elif name == "l3_publish":
            # L3 durable/publish advanced past the decline cursor.
            if cur > entry.epoch_cursor:
                return True
        else:  # host_release (Fix A)
            # A genuine host-capacity-releasing event advanced the release
            # counter past the decline cursor. The counter is MONOTONIC --
            # it never recedes when the working set re-consumes the freed
            # pages (unlike the available level, which flips 0->100->0 and
            # can never sustain past the cursor under a full working set).
            # A park therefore clears exactly once per release-epoch
            # advance; the headroom debounce fuse bounds the re-probe rate.
            if cur > entry.epoch_cursor:
                return True
        # Identity events are causal for every park.
        if view.prefix_len != entry.prefix_len:
            return True
        if view.generation != entry.generation:
            return True
        return False

    @staticmethod
    def subscribe_decline(
        entry: Optional[NegativeCacheEntry],
        view: ReadyHorizonView,
        epochs: CausalEpochs,
        now: float,
    ) -> bool:
        """Whether a candidate whose last attempt declined (parked) may be
        staged now. No entry = never attempted = eligible for its one
        fresh probe. The park clears only on its subscribed epoch's
        advance or an identity change; the READY pool / running batch /
        plain scheduler pass never clears it."""
        if entry is None:
            return True
        return ReadyHorizonPolicy.entry_cleared(entry, view, epochs, now)

    def _state_funnel(self, view) -> bool:
        """The WAIT/NONE state funnel: NONE with restore potential, or
        WAIT_CAPACITY with a capacity reason the horizon resolves --
        PREFETCH_BUDGET, and DEVICE_QUOTA with no host material yet (T6
        sources whose next step is the unrestricted L3->H prefetch).
        FRONTIER / BACKUP_PENDING are ACK-event-driven wakes (re-issuing
        them duplicates the T11/T12 wake re-issue) and REVALIDATE /
        HOST_ALLOC are not testable by the horizon; the paced retry and
        T13 own them.

        P1: a MISS_RECOMPUTE request (proven L3-missing) is treated like
        NONE here -- the ready horizon's OWN NO_L3 negative cache (keyed on
        the l3_publish cursor) is the authoritative retry gate, clearing
        only on an l3_publish advance / identity change / fuse expiry. That
        cleared re-probe is the legitimate re-arm, so the sticky miss state
        alone must not block the horizon's staging once its park clears."""
        if view.state in (RestoreState.NONE, RestoreState.MISS_RECOMPUTE):
            return bool(view.staging_eligible)
        if view.state is not RestoreState.WAIT_CAPACITY:
            return False
        reason = view.wait_reason
        if reason is RestoreWaitReason.PREFETCH_BUDGET:
            return True
        return reason is RestoreWaitReason.DEVICE_QUOTA and view.host_hit_length == 0

    def staging_candidates(
        self, views, *, tree, cc, negatives, epochs, now
    ) -> list:
        """The frontier requests a refill may stage right now: the first N
        whose negative-cache (if any) cleared on a causal event and whose
        state funnel passes. Candidates with an active park are excluded
        (the retry cadence is causal, not the next pass -- a cached
        decline is a deterministic current judgment). In-flight fetches are
        excluded. With either inflight budget exhausted every speculative
        issue declines identically, so the refill parks until a
        budget-release epoch (M3) instead of attempting it."""
        if cc is not None and (
            cc.prefetch_rate_limited() or cc.prefetch_speculative_rate_limited()
        ):
            return []
        out = []
        for view in views:
            if view.rid in tree.ongoing_prefetch:
                continue
            entry = negatives.get(view.rid)
            if not self.subscribe_decline(entry, view, epochs, now):
                continue
            if self._state_funnel(view):
                out.append(view)
        return out

    def headroom_fits(
        self, ready_tokens: int, inflight_tokens: int, host_headroom: int
    ) -> bool:
        """M1/M2 gate: the READY pool plus in-flight speculative staging
        must fit the host headroom (pool capacity minus the active/warm
        working set). The cap is the physical headroom, NOT the inflight
        prefetch budget: 2-4 READY chains (2 x ~21K tokens) are reachable
        only under the headroom model."""
        return ready_tokens + inflight_tokens <= host_headroom

    def refill_plan(
        self,
        views,
        *,
        tree,
        cc,
        host_headroom,
        negatives,
        epochs,
        now,
        reserve_floor: int = 0,
    ) -> RefillPlan:
        """The full refill decision: the M6 pool snapshot, the low-
        watermark trigger, the headroom gate, and the causal-eligible
        candidate list (parked rids excluded) capped at the HIGH watermark
        budget -- by TOKENS in token mode (each candidate charges its state
        size), by request count in legacy count mode. When the headroom
        gate fails every causal-eligible candidate is attributed
        NO_HEADROOM (none can stage); the pass records those as per-rid
        parks so they are not re-attempted until host pages free. The full
        candidate list is returned for the pass's post-issue SPEC_BUDGET
        attribution of the un-tried tail (only the pass observes the budget
        state after an actual issue)."""
        ready = self.ready_count(views)
        tokens = self.ready_resident_tokens(views)
        to_issue: list = []
        declines: list = []
        candidates: list = []
        issued_tokens = 0
        if self._below_low(ready, tokens):
            candidates = self.staging_candidates(
                views, tree=tree, cc=cc, negatives=negatives, epochs=epochs, now=now
            )
            # P3 write-back isolation: a stage is admitted only when the
            # host keeps writeback_reserve + safety_margin free after the
            # stage (free_host_after_stage >= reserve + margin). The floor
            # is a harder constraint than the headroom model: 2-4 READY
            # chains are reachable only when they do not encroach on the
            # write-back reserve.
            if self.headroom_fits(
                tokens,
                cc.inflight_speculative_tokens,
                host_headroom - reserve_floor,
            ):
                budget = self._issue_budget(ready, tokens)
                for view in candidates:
                    charge = self._watermark_tokens(view)
                    if self.token_mode:
                        if issued_tokens + charge > budget:
                            # Cap reached: not a decline, just deferred.
                            continue
                        issued_tokens += charge
                    else:
                        if len(to_issue) >= budget:
                            # Cap reached: not a decline, just deferred.
                            continue
                    to_issue.append(view)
            else:
                declines = [(v.rid, DeclineReason.NO_HEADROOM) for v in candidates]
        return RefillPlan(
            ready_count=ready,
            ready_tokens=tokens,
            to_issue=to_issue,
            declines=declines,
            candidates=candidates,
        )

    def epoch_event(self, prev: Optional[CausalEpochs], cur: CausalEpochs) -> bool:
        """M3 event gate: whether a causal-epoch change since the last
        pass warrants reconsidering the pool. Only availability-improving
        deltas fire it -- L3 published (counter up), host pages released
        (available up OR the monotonic release counter advanced: genuine
        capacity-releasing events -- host residency freed, ready eviction,
        working-state release -- Fix A), budget released (inflight down), a
        new request entered the frontier (composition changed). The
        refill's own traffic (issues raise inflight and lower free pages)
        never fires it (the e7 spin root cause)."""
        if prev is None:
            return True
        return (
            cur.l3_publish > prev.l3_publish
            or cur.host_headroom > prev.host_headroom
            or cur.host_release > prev.host_release
            or cur.spec_budget < prev.spec_budget
            or cur.waiting_frontier != prev.waiting_frontier
        )

    def should_refill(
        self,
        *,
        event: bool,
        last_refill_ts: float,
        now: float,
        safety_interval_s: Optional[float] = None,
    ) -> bool:
        """M3: run the refill check only when a causal-epoch event
        arrived, or the periodic safety reconciliation is due (the
        lost-event fallback, seconds -- never a per-pass poll)."""
        interval = self.safety_interval_s if safety_interval_s is None else safety_interval_s
        return event or now - last_refill_ts >= interval

    @staticmethod
    def _req_is_ready_resident(req, tree, buffer_mode: bool) -> bool:
        """M6 membership for a live queue Req: READY state plus the
        physically resident staged marker -- the same finalize-written,
        admission-consumed count the views read (buffer mode surfaces it
        from the pipeline)."""
        if req.hicache_restore_state is not RestoreState.READY:
            return False
        lookup = (
            tree.staged_prefetch_tokens
            if buffer_mode
            else tree.peek_prefetch_loaded_tokens
        )
        return lookup(req.rid) > 0

    def partition_ready_first(
        self,
        waiting_queue,
        *,
        tree,
        buffer_mode: bool = False,
        priority: bool = False,
    ) -> list:
        """M4: stable READY-first partition of the calc_priority output,
        called by the scheduler between calc_priority and PrefillAdder.

        Explicit priority > READY > base policy. With priority scheduling
        enabled the reorder is scoped to each maximal run of equal
        req.priority -- the exact key calc_priority sorts by up to the
        constant sign (schedule_low_priority_values_first flips it for
        the whole pass, so grouping is unaffected) -- and a READY request
        never overtakes one with a different explicit priority, in either
        direction. Without priority scheduling the whole queue is one
        run: READY beats the base policy order freely. Within a run the
        partition is stable: READY members move to the front, both sides
        keep their original order.

        Returns a new list; the input is untouched, so off (the
        scheduler gate) or an idle horizon (no M6 member) leaves the
        calc_priority order exactly as it was."""
        out = []
        run_ready = []
        run_rest = []
        last_level = object()  # unique sentinel: the first req opens a run
        for req in waiting_queue:
            level = req.priority if priority else None
            if level != last_level:
                out.extend(run_ready)
                out.extend(run_rest)
                run_ready = []
                run_rest = []
                last_level = level
            if self._req_is_ready_resident(req, tree, buffer_mode):
                run_ready.append(req)
            else:
                run_rest.append(req)
        out.extend(run_ready)
        out.extend(run_rest)
        return out