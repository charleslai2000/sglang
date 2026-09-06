"""P2-1 M1b: restore retry state machine for HiCache storage restores.

Pure, torch-free logic implementing the design's transition table
(p2-1-design.md §2.2, M1 restore retry state). The scheduler feeds events
recorded at the prefetch / admission / drain call sites into next_restore()
and executes the returned RestoreDecision; no I/O and no scheduler state is
touched here.

Invariant the transitions encode: a capacity denial (quota / budget / host
staging / frontier wait) is transient and retryable (WAIT_CAPACITY), while a
true L3 miss is terminal (ADMIT_RECOMPUTE) -- miss decisions and capacity
decisions are separate (design §0.1). P1 (restore re-arm churn): a definitive
miss parks the request in the sticky MISS_RECOMPUTE state (instead of
collapsing back to NONE) so the negative evidence -- "this prefix was just
proven L3-missing at this episode's L3 publish epoch" -- survives, and the
admission re-arm refuses to re-enter WAIT until that epoch advances or the
identity (generation) changes.
"""

from enum import Enum, auto
from typing import Optional, Tuple


class RestoreState(Enum):
    """Per-request restore lifecycle state (Req.hicache_restore_state)."""

    NONE = auto()  # no restore intent
    WAIT_CAPACITY = auto()  # denied for capacity; woken by T11/T12, bounded by T13
    RESTORING = auto()  # prefetch issued (or re-issued), in flight
    READY = auto()  # prefetch finalized; admission consumes the loaded tokens
    MISS_RECOMPUTE = auto()  # P1 sticky-miss: proven L3-missing this episode;
    # NOT re-armed until the L3 publish epoch advances or the identity
    # (generation) changes -- the request recomputes forward meanwhile


class RestoreWaitReason(Enum):
    """Why a request sits in WAIT_CAPACITY (design §2.2 wait_reason set)."""

    DEVICE_QUOTA = auto()
    PREFETCH_BUDGET = auto()
    HOST_ALLOC = auto()
    FRONTIER = auto()
    REVALIDATE = auto()
    BACKUP_PENDING = auto()  # chain's L3 write in flight; wait for the ack drain


class RestoreEvent(Enum):
    """Events the scheduler feeds into the state machine (design §2.2)."""

    PREFETCH_ISSUED = auto()  # T1
    DENIED_RATE = auto()  # T2
    DENIED_ALLOC = auto()  # T3
    DENIED_SHORT = auto()  # T4
    GATE_SKIP_FRONTIER = auto()  # T5
    ADMISSION_DENY = auto()  # T6
    LOAD_BACK_FAIL = auto()  # T7
    FINALIZED = auto()  # T8
    REVOKED_MISS = auto()  # T9
    REVOKED_TERMINATED = auto()  # T10
    CAPACITY_FITS = auto()  # T11
    FRONTIER_READY = auto()  # T12
    TIMEOUT = auto()  # T13
    ABORT = auto()  # T14
    BACKUP_PENDING = auto()  # T15: lookup found the chain mid-backup


class RestoreDecision(Enum):
    """What the scheduler must do after the transition."""

    NONE = auto()
    RETRY_PREFETCH = auto()  # re-issue _prefetch_kvcache(req)
    ADMIT_RECOMPUTE = auto()  # clear the state; admit as a normal request
    FORCE_REVOKE = auto()  # reserved; no transition currently emits it
    WAIT = auto()  # keep the request queued in WAIT_CAPACITY


def next_restore(
    state: Optional[RestoreState],
    event: RestoreEvent,
    *,
    capacity_fits: bool = False,
    genuine_miss: bool = False,
    rearm_allowed: bool = True,
) -> Tuple[RestoreState, RestoreDecision]:
    """Pure transition-table lookup for the design §2.2 state machine.

    - Issue-side events land the request in RESTORING (T1, and the T11/T12
      re-issue completion).
    - Capacity-type events (T2-T7, T10, T15) land it in WAIT_CAPACITY.
      T15 is the backup-completion wait (P2-IO): the lookup found the
      chain mid-backup, so the request waits for the ack drain instead of
      restoring the partial span and re-issuing the lookup per pass.
    - T4 too-short declines only start a WAIT[REVALIDATE] from a fresh
      NONE (the device-match-decay bet, re-issuable by the paced retry);
      on a re-issue leg (T11/T12 wake) the too-short re-judgment is
      definitive and clears the state with ADMIT_RECOMPUTE, exactly like a
      genuine miss -- re-waiting would only idle out the old T13 clock.
    - T8 finalize lands RESTORING in READY.
    - T9 genuine miss parks the request in MISS_RECOMPUTE (P1 sticky miss:
      the negative evidence survives), with the ADMIT_RECOMPUTE decision
      (degrade to recompute; never wait). It leaves MISS_RECOMPUTE only when
      the L3 publish epoch advances or the identity/generation changes (the
      re-arm epoch gate) or a later restore_success (T8) lands -- never by
      re-arm alone, so the same-probe churn cannot recur.
    - T13 timeout clears WAIT_CAPACITY to NONE with the ADMIT_RECOMPUTE
      decision (degrade to recompute; never wait).
    - T14 abort is a no-op here: the request object is destroyed by the
      scheduler and the tree-side registries are cleared by
      release_aborted_request.
    Events applied to an unexpected state are no-ops: the scheduler feeds at
    most one event per cause, and the real admission gates stay authoritative.
    """
    if state is None:
        state = RestoreState.NONE

    if event is RestoreEvent.PREFETCH_ISSUED:  # T1
        return RestoreState.RESTORING, RestoreDecision.NONE

    if event is RestoreEvent.DENIED_RATE:  # T2
        return RestoreState.WAIT_CAPACITY, RestoreDecision.WAIT
    if event is RestoreEvent.DENIED_ALLOC:  # T3
        return RestoreState.WAIT_CAPACITY, RestoreDecision.WAIT
    if event is RestoreEvent.DENIED_SHORT:  # T4
        if state is RestoreState.RESTORING:
            # A too-short decline on a re-issue leg (T11/T12 wake) is the
            # definitive judgment: the wake condition is resolved, so
            # re-entering WAIT[REVALIDATE] would only idle out the old T13
            # clock. Fresh declines (NONE) and re-declines (WAIT) keep the
            # REVALIDATE wait and its paced-retry loop.
            return RestoreState.NONE, RestoreDecision.ADMIT_RECOMPUTE
        return RestoreState.WAIT_CAPACITY, RestoreDecision.WAIT
    if event is RestoreEvent.GATE_SKIP_FRONTIER:  # T5
        return RestoreState.WAIT_CAPACITY, RestoreDecision.WAIT
    if event is RestoreEvent.ADMISSION_DENY:  # T6
        if state is RestoreState.MISS_RECOMPUTE and not rearm_allowed:
            # P1 sticky miss: a definitive miss proves this prefix
            # L3-missing at the episode's L3 publish epoch; re-arming into
            # WAIT[DEVICE_QUOTA] would re-probe the same missing prefix and
            # miss again (the ~13ms churn). The scheduler passes
            # rearm_allowed=False while the epoch is unchanged and the
            # generation matches -- the request stays sticky and recomputes
            # forward instead of re-arming. An epoch/generation advance
            # (rearm_allowed=True) lets it leave MISS and re-arm.
            return state, RestoreDecision.NONE
        return RestoreState.WAIT_CAPACITY, RestoreDecision.WAIT
    if event is RestoreEvent.LOAD_BACK_FAIL:  # T7
        return RestoreState.WAIT_CAPACITY, RestoreDecision.WAIT
    if event is RestoreEvent.REVOKED_TERMINATED:  # T10
        return RestoreState.WAIT_CAPACITY, RestoreDecision.WAIT

    if event is RestoreEvent.FINALIZED:  # T8
        if state is RestoreState.RESTORING:
            return RestoreState.READY, RestoreDecision.NONE
        return state, RestoreDecision.NONE

    if event is RestoreEvent.REVOKED_MISS:  # T9
        if genuine_miss:
            # P1 sticky miss: park in MISS_RECOMPUTE (degrade to recompute,
            # never wait). Unlike the pre-P1 collapse to NONE, the sticky
            # state carries the negative evidence so the admission re-arm
            # cannot re-enter WAIT at the same L3 publish epoch (the churn).
            # It leaves only on an epoch/generation advance (the re-arm
            # gate) or a later restore_success (T8 -> READY).
            return RestoreState.MISS_RECOMPUTE, RestoreDecision.ADMIT_RECOMPUTE
        # Capacity-type revoke (e.g. host staging shortfall): retryable.
        return RestoreState.WAIT_CAPACITY, RestoreDecision.WAIT

    if event is RestoreEvent.CAPACITY_FITS:  # T11
        if state is RestoreState.WAIT_CAPACITY and capacity_fits:
            return RestoreState.RESTORING, RestoreDecision.RETRY_PREFETCH
        return state, RestoreDecision.NONE

    if event is RestoreEvent.FRONTIER_READY:  # T12
        if state is RestoreState.WAIT_CAPACITY:
            return RestoreState.RESTORING, RestoreDecision.RETRY_PREFETCH
        return state, RestoreDecision.NONE

    if event is RestoreEvent.TIMEOUT:  # T13
        if state is RestoreState.WAIT_CAPACITY:
            # Bounded wait exceeded: clear and admit as a normal request.
            return RestoreState.NONE, RestoreDecision.ADMIT_RECOMPUTE
        # RESTORING is never timed out: wait_complete keeps the in-flight
        # prefetch running (design §2.5-3).
        return state, RestoreDecision.NONE

    if event is RestoreEvent.ABORT:  # T14
        return RestoreState.NONE, RestoreDecision.NONE

    if event is RestoreEvent.BACKUP_PENDING:  # T15
        # The lookup revealed the chain only partially in L3 while its L3
        # write is still in flight: park on the backup-completion wait
        # (the scheduler registers the M2 frontier waiter) instead of
        # restoring the partial span -- the per-pass re-issue cycle that
        # followed each partial restore was the backup-in-flight retry
        # loop (e13 profiling: 1.7 attempts/rid, retry waits up to 33.5s).
        # Capacity-type wait: bounded by T13, woken by the ack drain.
        return RestoreState.WAIT_CAPACITY, RestoreDecision.WAIT

    return state, RestoreDecision.NONE


def wait_reason_for(
    event: RestoreEvent, *, genuine_miss: bool = False
) -> Optional[RestoreWaitReason]:
    """Map an event that lands the request in WAIT_CAPACITY to its reason.

    REVOKED_MISS maps only when it is not a genuine miss (capacity-type
    revoke); a genuine-miss revoke never enters WAIT_CAPACITY.
    """
    if event in (RestoreEvent.DENIED_RATE, RestoreEvent.REVOKED_TERMINATED):
        return RestoreWaitReason.PREFETCH_BUDGET
    if event is RestoreEvent.DENIED_ALLOC:
        return RestoreWaitReason.HOST_ALLOC
    if event is RestoreEvent.DENIED_SHORT:
        return RestoreWaitReason.REVALIDATE
    if event is RestoreEvent.GATE_SKIP_FRONTIER:
        return RestoreWaitReason.FRONTIER
    if event in (RestoreEvent.ADMISSION_DENY, RestoreEvent.LOAD_BACK_FAIL):
        return RestoreWaitReason.DEVICE_QUOTA
    if event is RestoreEvent.REVOKED_MISS and not genuine_miss:
        return RestoreWaitReason.HOST_ALLOC
    if event is RestoreEvent.BACKUP_PENDING:
        return RestoreWaitReason.BACKUP_PENDING
    return None


def miss_rearm_allowed(
    miss_epoch: Optional[int],
    current_epoch: int,
    miss_generation: Optional[int],
    current_generation: Optional[int],
) -> bool:
    """P1: whether a request parked in MISS_RECOMPUTE may be re-armed at
    admission (the restore re-arm churn gate).

    A definitive miss proves the request's prefix L3-missing at the L3
    publish epoch it was probed; re-probing the same prefix at the same
    epoch is guaranteed to miss again (the ~13ms churn). Re-arm is therefore
    allowed only when the L3 publish epoch has advanced (the cache coverage
    genuinely changed) or the identity (session generation) changed -- either
    invalidates the old miss evidence. A request with no recorded miss epoch
    (defensive; the state should not be MISS then) is treated as re-armable.
    """
    if miss_epoch is None:
        return True
    if current_epoch > miss_epoch:
        return True
    if current_generation is not None and current_generation != miss_generation:
        return True
    return False


def wait_clock_next(
    prev_state: Optional[RestoreState],
    next_state: Optional[RestoreState],
    state_ts: float,
    now: float,
) -> float:
    """Next value of the WAIT clock (Req.hicache_restore_state_ts, the T13
    timeout base).

    The clock is armed at the first WAIT_CAPACITY entry of a restore episode
    and kept across every later WAIT re-entry (T2-T7/T10 re-declines) and
    across a WAIT -> RESTORING re-issue leg: re-arming on re-entry is what
    turned the capacity loop into an unbounded one (each re-issued prefetch
    that was declined reset the clock, so T13 never fired). The clock is
    cleared when the episode ends (READY / NONE); a fresh NONE -> RESTORING
    was never armed (state_ts == 0.0).
    """
    if prev_state is None:
        prev_state = RestoreState.NONE
    if next_state is None:
        next_state = RestoreState.NONE
    if next_state is RestoreState.WAIT_CAPACITY:
        return now if state_ts <= 0.0 else state_ts
    if next_state is RestoreState.RESTORING and prev_state is RestoreState.WAIT_CAPACITY:
        return state_ts
    return 0.0


def too_short_wait_armed(poll_interval: int) -> bool:
    """Whether a first-time too-short decline may enter WAIT[REVALIDATE].

    REVALIDATE is the device-match-decay bet (T4): its only re-issue source
    is the paced retry (the scheduler's _reconcile_restore_states step 2,
    gated on hicache_storage_prefetch_retry_poll_interval > 0), and the
    capacity predicate cannot validate it. With the poll disabled (the M2
    default 0) the wait has no wake path and idles out the full T13 clock
    (the e13 K=1 t5 60s). The scheduler gates the DENIED_SHORT event on
    this; an unarmed first decline is terminal (recompute immediately).
    """
    return poll_interval > 0


def promotion_budget_fits(
    locked: int,
    reserved: int,
    new_restore: int,
    capacity: int,
    margin: int,
) -> bool:
    """P2-1c device promotion budget (p2-promotion-admission.md §3.1):
    `locked + reserved + new_restore <= capacity - margin`.

    locked is the derived device locked token count (capacity - available -
    evictable); reserved is the in-flight promotion reservation not yet
    transferred to lock ownership; new_restore is the H->D transfer being
    admitted. The margin keeps a walker-reclaimable floor (one chunk at the
    default 2048): margin=0 would let two 16K chains lock the whole 32K pool
    (the e11 crash shape). Negative inputs are clamped to 0 -- derived
    values must never go negative, and a negative margin must not widen the
    budget.
    """
    locked = max(0, locked)
    reserved = max(0, reserved)
    new_restore = max(0, new_restore)
    capacity = max(0, capacity)
    margin = max(0, margin)
    return locked + reserved + new_restore <= capacity - margin


def promotion_wait_blocked(
    reason: Optional[RestoreWaitReason],
    host_hit_length: int,
    budget_fits: bool,
) -> bool:
    """Whether the per-pass T11 predicate must keep a WAIT request blocked
    by the P2-1c promotion budget (design §3.4).

    Only DEVICE_QUOTA waiters whose host material is ready (host_hit_length
    > 0) are budgeted: their next step is the H->D promotion, so waking them
    while the budget cannot hold the transfer would re-issue prefetch ->
    finalize -> admission -> re-deny, burning a full prefetch cycle per
    wake. T6 sources with host_hit_length == 0 are not blocked: their next
    step is the unrestricted L3->H prefetch. The predicate re-reads every
    pass, so a reservation release is visible the same pass.
    """
    return (
        reason is RestoreWaitReason.DEVICE_QUOTA
        and host_hit_length > 0
        and not budget_fits
    )


# Concurrent DEMAND_RESTORE re-issues (the T15 wake path) allowed past the
# speculative PREFETCH_BUDGET at once. The bound smooths the thundering
# herd of backup-complete wakes (e4: 57 denied_rate_limit after wakes);
# the prefetch IO pipeline stays serialized per thread regardless.
DEMAND_RESTORE_MAX_INFLIGHT = 4


def backup_wait_applies(
    storage_hit_pages: int,
    requested_pages: int,
    *,
    durable_frontier: int,
    backup_target_frontier: int,
) -> bool:
    """Whether a partial prefetch lookup outcome should park the request on
    the backup-completion wait (T15) instead of restoring the partial span.

    The park is for the backup-in-flight race (e13 profiling), framed by
    the chain's frontiers: the query saw only the already-written batches,
    and the park is useful exactly when the backup pipeline is targeted to
    cover the request's end -- then the wake (durable >= requested) yields
    one re-lookup, one full hit, one restore. A pipeline that stops short
    of the request's end (chain growth, a dropped-without-backup tail, a
    sibling chain's write) would wake into the same partial and is not
    parked: the current restore-or-recompute behavior applies. The
    zero-hit guard stays: a fresh span may simply never have been written.
    """
    if not (0 < storage_hit_pages < requested_pages):
        return False
    return (
        durable_frontier < requested_pages
        and backup_target_frontier >= requested_pages
    )


def backup_wake_applies(durable_frontier: int, requested_pages: int) -> bool:
    """Whether the backup-completion wait (T15) may wake: the chain's
    durable frontier has crossed the request's end, so the re-lookup
    serves the full hit (one lookup, one restore). The frontier is
    re-read every scheduler pass (the ACK drain advances it), which is
    the event-driven wake -- not a poll of the storage backend."""
    return durable_frontier >= requested_pages


def demand_restore_available(inflight: int) -> bool:
    """Whether a DEMAND_RESTORE ticket can be granted: the wake re-issue
    bypasses the speculative PREFETCH_BUDGET but is bounded by its own
    concurrency (a backup-complete wake batch must not stampede the host
    staging / IO pipeline)."""
    return inflight < DEMAND_RESTORE_MAX_INFLIGHT


def capacity_wake_applies(reason: Optional[RestoreWaitReason]) -> bool:
    """Whether the per-pass T11 capacity predicate can validate this WAIT
    reason (design §2.3 predicates: device charge, host prefetch budget,
    frontier anchor fallback).

    DEVICE_QUOTA / PREFETCH_BUDGET / FRONTIER / BACKUP_PENDING are
    testable: the predicate re-checks the exact denial cause (for
    BACKUP_PENDING: whether the chain's durable frontier has crossed the
    request end and a DEMAND_RESTORE ticket is grantable -- the ack drain
    flips the frontier, so the wake is ACK-driven, not a poll). REVALIDATE
    (the suffix is still below the prefetch threshold) and HOST_ALLOC (the
    host staging alloc is still failing) are not: waking them re-issues a
    prefetch that is declined identically every pass. Those waits leave
    only via the paced retry (poll interval > 0) or the T13 timeout.
    """
    return reason in (
        RestoreWaitReason.DEVICE_QUOTA,
        RestoreWaitReason.PREFETCH_BUDGET,
        RestoreWaitReason.FRONTIER,
        RestoreWaitReason.BACKUP_PENDING,
    )
