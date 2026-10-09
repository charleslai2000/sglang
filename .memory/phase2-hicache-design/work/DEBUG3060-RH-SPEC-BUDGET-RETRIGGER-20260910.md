# DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910

status: done

## Invocation binding

- task_id: `D3060-RH-SPEC-BUDGET-RETRIGGER-20260910`
- invocation_id: `INV-20260910-DEBUG-RH-SPEC-BUDGET-R1`
- epoch: `20260910-rh`
- role/capability: `debugger-deep` / L2 (hard causal debugging)
- workdir: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- observed workspace root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` (matched before task reads)
- memory_root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design`
- memory_inputs: [`OPS3060-HICACHE-RESTORE-R3-20260910.md`](./OPS3060-HICACHE-RESTORE-R3-20260910.md)
- memory_report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`
- parent_thread_id: `01a07bea-d668-75b2-8280-6a2cf0870c1e`
- native event channel: available and successful; terminal `done` event sent to the bound parent after this report was verified.

## Summary

The `SPEC_BUDGET` negative-cache entry for B captures the **pre-issue**
`spec_budget` snapshot (zero), rather than the actual speculative-inflight
value at the time A's issue exhausts the budget (54,999).  The release rule is
correctly strict: it clears only when `current_spec_budget < epoch_cursor`.
Consequently the real `54,999 -> 0` release evaluates as `0 < 0`, false, and
B remains parked.  When ordinary scheduling later admits B, its RH stage was
never performed, which explains the observed `cached_tokens=0` path.

## Causal chain

| Time | Observed / code state | Consequence |
|---|---|---|
| t0 | `_ready_horizon_pass` snapshots `epochs.spec_budget=0` before issuing any `plan.to_issue` candidate. | The snapshot is saved as the prior epoch at `scheduler.py:4661-4666`. |
| t1 | A's 55K speculative issue reserves 54,999 tokens. The storage reservation increments `cc.inflight_speculative_tokens` (`unified_radix_cache.py:5118-5121`). | The speculative limiter becomes true. |
| t1 | The post-issue tail branch parks B as `SPEC_BUDGET` (`scheduler.py:4876-4887`) but passes the old `epochs` object to `_park_ready_decline`. | `_park_ready_decline` calls `policy_epoch_value(..., epochs, SPEC_BUDGET)` (`scheduler.py:4899-4923`), saving cursor **0**, not 54,999. This exactly matches the supplied `negative_cursor=0` observation. |
| t2 | A finishes staging/READY and exactly-once release reduces inflight speculative tokens to zero (`unified_radix_cache.py:5123-5143`). | `epoch_event` correctly recognizes a release because `0 < 54,999` at the pass-snapshot level (`ready_horizon.py:546-564`). |
| t2 | B's entry is checked with its stored cursor 0. `entry_cleared` requires `cur < entry.epoch_cursor` for `SPEC_BUDGET` (`ready_horizon.py:361-366`). | `0 < 0` is false; B remains `negative_cache`, so RH never stages it. |

## Root cause and hypotheses tested

Confirmed root cause:

- The epoch is a directional level (`inflight_speculative_tokens`), not a
  monotonic release sequence. It must be recorded at the **decline/exhaustion
  instant**. The issue loop creates the B decline after A mutated the level,
  but records the pass-start value instead.

Rejected alternatives:

- Changing `<` to `<=` is unsafe. A cursor of 0 would clear while current
  inflight remains 0, including later safety reconciliations with no release;
  that breaks the no-spin/one-probe semantics.
- A reaching `READY` is intentionally not a `SPEC_BUDGET` clearing event.
  `staging_candidates` consults the per-rid park before the state funnel
  (`ready_horizon.py:434-467`); READY membership must not itself re-arm B.
- Prefix/generation changes would clear an entry (`ready_horizon.py:377-381`),
  but the supplied sessions have fixed 55K prompts and no identity-change
  evidence.
- Fuse expiry is not the cause: it only permits an otherwise causal retry;
  it does not make `0 < 0` true (`ready_horizon.py:336-382`).

## Minimal safe fix shape (return owner: coder)

Change only the `SPEC_BUDGET` cursor capture in
`Scheduler._park_ready_decline` (`python/sglang/srt/managers/scheduler.py`).
When `reason is DeclineReason.SPEC_BUDGET`, read the current
`self.tree_cache.cache_controller.inflight_speculative_tokens` immediately
before constructing `NegativeCacheEntry`; keep the snapshot-based cursor for
`NO_L3` and `NO_HEADROOM` unchanged. The direct post-issue tail and a
synchronous budget decline both use this helper, so one bounded change covers
both stale-snapshot paths.

The implementation must only overwrite the cursor when the speculative
sub-budget is the limiter. The existing `SPEC_BUDGET` call sites also include
the physical prefetch limiter; that distinct physical-only case has no
matching causal cursor under the current enum/subscription contract and is
outside this narrowly authorized fix.

Expected invariant for this incident: if a speculative issue leaves
`inflight_speculative_tokens=N>0` and parks another rid, that entry records
`N`; after the reservation releases to `M<N`, it becomes eligible for exactly
one new attempt in the release event pass.

## Required regression tests

Add these to `3090-dev/test_ready_horizon_unit.py` (or its successor RH unit
suite) using the existing `_pass_scheduler` stubs.

1. Preserve the policy-level strictness guard: a `SPEC_BUDGET` entry with
   cursor 0 and current budget 0 is not cleared; a cursor 54,999 with current
   budget 0 is cleared. This rejects an unsafe `<=` workaround.
2. End-to-end two-candidate pass: start A and B with 55,000-token identities
   and current speculative use 0. Make A's fake issue set use to 54,999 and
   hit the speculative limit. Assert B is parked as `SPEC_BUDGET` with cursor
   54,999, not 0.
3. Simulate A terminal/READY plus reservation release to 0, run the next RH
   pass, and assert B receives exactly one RH issue. A repeat pass with no new
   release must not issue B again.
4. Existing regression behavior must remain: `NO_L3` and `NO_HEADROOM` retain
   their respective cursor sources, and a physical-only prefetch limit is not
   silently claimed to be a speculative-budget release.

## Evidence

- Design/live input read: `OPS3060-HICACHE-RESTORE-R3-20260910.md`. It
  confirms the 55K prompt shape and declares multi-session RH-ON staging an
  open area; the prompt supplied the incident-specific trace facts.
- Target checkout: `a96dc148c208d31d6c4b291370ee4e233063c60a` (`fix(hicache):
  avoid tensor truth test in RH telemetry`). Target product files and tests
  were unchanged by this diagnosis.
- Source reconstruction: `scheduler.py:4637-4666`, `4764-4887`,
  `4899-4923`; `ready_horizon.py:309-382`, `434-467`, `546-564`; and
  `unified_radix_cache.py:5106-5143`.
- Isolated execution of the exact parsed `entry_cleared` source (with only
  dependency stubs) produced:
  - `cursor=0, current_spec=0 -> False`
  - `cursor=54999, current_spec=0 -> True`
- `python3 -m compileall -q` passed for both target source files.
- Full project test execution was unavailable in this shell: `python3` has no
  `pytest`, and importing the runtime fails before tests because `orjson` is
  absent. No production code was run and no SSH was used.

## Prohibited broader changes

- Do not change the `SPEC_BUDGET` clear comparison from strict `<` to `<=`.
- Do not clear a negative entry on READY-pool changes, ordinary scheduler
  passes, or fuse expiry alone.
- Do not replace the per-rid negative cache with polling/cooldown behavior.
- Do not alter NO_L3 per-anchor or NO_HEADROOM host-release semantics.
- Do not widen this patch into physical-prefetch-budget redesign, admission
  policy, storage restore, or telemetry redesign; create a fresh diagnosis if
  physical-only exhaustion needs a causal wake contract.

## Followups

- Coder: implement the bounded cursor-capture change and the four regression
  assertions above.
- Tester: run the RH unit suite in the repository's dependency-complete test
  environment, then reproduce the two-55K-session scenario with telemetry
  asserting `negative_cursor=54999` and a B RH reissue after A's release.

## Open issues

- The raw RH telemetry/log artifact for the stated live incident was not among
  the designated memory inputs, so its timestamps/attempt IDs could not be
  independently cross-correlated. The supplied values are nevertheless
  sufficient to prove the source-level causal chain.
- Physical-only `prefetch_rate_limited()` calls currently share the
  `SPEC_BUDGET` reason but are not guaranteed a positive speculative cursor.
  This is not needed to explain this incident and must be separately scoped.
