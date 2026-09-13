# Independent gate review — RH SPEC_BUDGET re-trigger fix (3060 Ready Horizon)

```yaml
status: done
entry: ACCEPT
task_id: R3060-RH-SPEC-BUDGET-RETRIGGER-20260910
invocation_id: INV-20260910-REVIEW-RH-SPEC-BUDGET-R3
orchestration_epoch: 20260910-rh-spec-budget-review-r3
role: reviewer
capability_level: L3
workdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
memory_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design
memory_inputs:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/HANDOFF-2026-09-10-RH-SPEC-BUDGET.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/escalations/ESC-20260910-RH-SPEC-BUDGET-RETRIGGER.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-HORIZON-COMPARE-R2-20260910.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260910-RH-TENSOR-BOOL-FIX-R3.md
memory_report: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260910-RH-SPEC-BUDGET-RETRIGGER.md
observed_workspace_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
reviewed_revision: HEAD 4f41f5bab562b99562f30c67540eb05344d13637 (working-tree diff is EMPTY; see Scope finding)
verdict: REQUEST_CHANGES
code_gate: PASS
runtime_normal_event: UNPROVEN
deployment_acceptance: NOT_READY
```

## Scope and decision

**The two product-file changes are correct, bounded, and match the accepted
DEBUG3060 root cause. The overall gate is nevertheless REQUEST_CHANGES**
because the reviewed change is not present as the dispatched "uncommitted
working-tree diff": the working tree is clean and the fix is already committed
at `4f41f5bab5`, made before this independent review, and that commit carries a
third tracked file (a gate artifact asserting PASS from sources this review
could not verify). See the Blocking finding for the exact remediation.

## Independent evidence

### Binding and observed git state

- `pwd` = `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`; branch
  `3060-12g-qwen35-4b`.
- `git rev-parse HEAD` = `4f41f5bab562b99562f30c67540eb05344d13637`
  (`charles <charles@lorestack.dev>`, 2026-09-10 05:37:43 +0800, "[3060]
  retrigger ready horizon after speculative budget release").
- `git status --porcelain=v1`: only untracked entries (`?? .memory/`,
  `?? review/gates/...`, `?? storage/`); **no tracked-file modification or
  staged change**. The dispatched "uncommitted working-tree diff" does not
  exist.
- `git diff --name-only HEAD` = empty (working tree == HEAD).
- `git show --name-only --format="" HEAD` =
  - `python/sglang/srt/managers/scheduler.py`
  - `3090-dev/test_ready_horizon_unit.py`
  - `review/gates/REVIEW-20260910-RH-SPEC-BUDGET-RETRIGGER-R3.md`
  So the fix commit touches exactly the two authorized product files **plus one
  committed review artifact**.
- `git diff --check HEAD~1 HEAD` = clean (exit 0). `git diff --check HEAD` =
  clean (exit 0).
- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile
  python/sglang/srt/managers/scheduler.py 3090-dev/test_ready_horizon_unit.py`
  = passed. (Syntax-only; no dependency import.)
- `python/sglang/srt/managers/scheduler_components/ready_horizon.py` is not in
  the diff (unchanged): the strict `<` guard, `entry_cleared`,
  `epoch_event`, `subscribe_decline`, and the five `CausalEpochs` fields are
  all byte-identical to HEAD~1.

## Fix-shape verification (matches DEBUG3060 root cause)

Root cause accepted by DEBUG3060: the `SPEC_BUDGET` park captured the pre-issue
pass-start snapshot (`spec_budget=0`) instead of the speculative-inflight level
at the decline/exhaustion instant, so the strict wake (`cur < cursor`) could
never fire after the real `54999 -> 0` release (`0 < 0` false).

Verified in the committed scheduler change:

1. `post_issue_epochs = CausalEpochs(l3_publish=epochs.l3_publish,
   host_headroom=epochs.host_headroom, host_release=epochs.host_release,
   spec_budget=cc.inflight_speculative_tokens,
   waiting_frontier=epochs.waiting_frontier)` is built **after**
   `_prefetch_kvcache` returns and `issued` is computed
   (`python/sglang/srt/managers/scheduler.py:4799-4805`), i.e. at the
   post-issue instant.
2. The reservation that raises the speculative level happens synchronously in
   the issue path before the scheduler resumes: `reserve_prefetch` increments
   `cc.inflight_speculative_tokens` in `unified_radix_cache.py:5119-5121`
   (SPECULATIVE kind, cache mode), and `prefetch_from_storage` returns
   `"issued"` only after that reservation. So the post-issue read sees the
   just-issued candidate's charge (the live 54,999-level), not the pass-start
   zero.
3. Both `SPEC_BUDGET` park sites in the pass now pass `post_issue_epochs`
   instead of the pre-issue `epochs` snapshot:
   - synchronous decline of the just-tried rid (`scheduler.py:4879-4886`);
   - post-issue un-tried-tail park (`scheduler.py:4887-4902`).
   There are no other `SPEC_BUDGET` `_park_ready_decline` call sites; the only
   other call site (`scheduler.py:4769`) records `plan.declines` which are
   exclusively `NO_HEADROOM` attributions from `refill_plan` and keeps the
   `epochs` snapshot.
4. `_park_ready_decline` is unchanged: it reads the cursor via
   `policy_epoch_value(..., SPEC_BUDGET)` -> `epochs.spec_budget`
   (`scheduler.py:4919-4943`, `512-518`), so passing `post_issue_epochs` yields
   the post-issue inflight value for SPEC_BUDGET parks. NO_L3's per-anchor
   override (`_anchor_version_or_zero`) and NO_HEADROOM's epoch cursor are
   untouched.
5. `ready_horizon.py` `entry_cleared` (strict `<`, line 365), `epoch_event`
   (`cur.spec_budget < prev.spec_budget`, line 562), and the M3 event gating
   are unchanged; a cursor `N` recorded post-issue clears when the release
   returns the counter to `M < N`, giving exactly one re-issue.

## Boundedness verification

- **No `<=` widening**: `entry_cleared` for `spec_budget` remains strict `<`
  (`ready_horizon.py:363-366`, not in the diff). No other clear rule changed.
- **No NO_L3 / NO_HEADROOM semantic change**: their parks still use the
  pre-issue `epochs` snapshot (`scheduler.py:4769`) and `_park_ready_decline`
  still applies the per-anchor override for NO_L3. `subscribed_epoch` mapping
  unchanged.
- **Physical-only limiter is not claimed as a speculative-budget release**:
  `prefetch_speculative_rate_limited()` (`cache_controller.py:1283-1289`,
  `inflight_speculative_tokens >= prefetch_speculative_capacity_limit`) is now
  the sole gate for SPEC_BUDGET parks; the physical-only
  `prefetch_rate_limited()` (`cache_controller.py:1263-1281`, host
  memory/storage load) path takes a bare `break`/no-park and assigns **no**
  speculative cursor (`scheduler.py:4879-4907`). This complies with the
  dispatch boundedness check ("does not assign a speculative cursor in the
  physical-only case").
- The physical-only behavior change (previously parked SPEC_BUDGET with the
  stale snapshot cursor, which could not be cleared by the spec counter and
  only self-released on the 1s safety fuse / identity change; now not parked)
  is the necessary consequence of the boundedness requirement: pre-fix, a
  physical-only decline *was* mis-attributed as a speculative-budget negative
  cache. Under M3 event gating, an un-parked physical-only candidate is only
  re-attempted on a causal event / safety reconciliation, not per-pass; when
  the physical pressure frees, the host_headroom epoch fires and re-checks it.
  This is consistent with the pre-existing first-loop handling of physical-only
  candidates ("hold"/physical_budget, no park, `scheduler.py:4730-4731`).

## Regression tests

Added to `3090-dev/test_ready_horizon_unit.py` (real `Scheduler._ready_horizon_pass`
and `_park_ready_decline` source against the file's stub collaborators; policy
`ready_horizon.py` is the real module):

- `test_spec_budget_park_uses_post_issue_cursor_and_wakes_on_release`
  (line 1035): r1's fake issue raises `cc.inflight_speculative_tokens` to
  `CHAIN_TOKENS`; asserts r2 is parked `SPEC_BUDGET` with `epoch_cursor ==
  CHAIN_TOKENS` (not the pre-issue 0); then releases the budget to 0, advances
  the clock past the safety interval, and asserts r2 is issued exactly once on
  the next pass. Covers dispatch requirement (a) and DEBUG regression #2/#3's
  wake half.
- `test_physical_only_limiter_does_not_create_spec_budget_park`
  (line 1073): r1's fake issue raises `prefetch_tokens_occupied` to the
  physical limit only; asserts r2 is neither issued nor parked. Covers dispatch
  requirement (b) and DEBUG regression #4.
- Strict-`<` guard: `ready_horizon.py` is untouched, and the existing policy
  test `test_spec_budget_cleared_only_by_budget_release`
  (line 507, cursor 20 / current 20 not cleared; cursor 20 / current 0
  cleared; current 25 not cleared) still rejects a `<=` widening. The new
  end-to-end test adds the "cursor N with current 0 cleared" case.

These tests exercise the real pass and park source (the monkeypatched
`_prefetch_kvcache` mirrors the reservation increment); they are not
policy-stub-only. Static tracing of both new tests against the real pass logic
shows they should pass (first-pass park, second-pass wake via the >= 5s
safety reconciliation after the 10s clock advance; physical test parks
nothing). They could not be executed in this shell (no `orjson`; importing the
runtime package fails before tests). Local execution is the test-runner's
separate gate and was not counted as a PASS input.

## Prohibited-change check (DEBUG3060 list)

- No per-pass retry/spin semantics added; no `<=`; no clearing on READY-pool
  changes / ordinary passes / fuse expiry alone (all unchanged).
- No storage/restore semantic change; no telemetry redesign; no admission
  policy change.
- No physical-prefetch-budget limiter redesign (the limiter constants and
  functions are untouched; only the RH negative-cache attribution of a
  physical-only decline was removed, which is the boundedness requirement).
- No new decline reason / enum / subscription change.

## Findings

### Blocking findings

1. **[HIGH | VERIFIED] Scope / commit-shape deviation — the reviewed object is
   not the dispatched "uncommitted working-tree diff"; the fix is already
   committed with a third tracked gate artifact.**
   - evidence: `git status --porcelain` shows no tracked-file changes;
     `git log -1` shows HEAD `4f41f5bab5` "[3060] retrigger ready horizon
     after speculative budget release" (charles, 2026-09-10 05:37);
     `git show --name-only HEAD` lists the two product files **plus**
     `review/gates/REVIEW-20260910-RH-SPEC-BUDGET-RETRIGGER-R3.md`; that
     committed artifact asserts "Verdict: PASS" and cites a "tool-free"
     reviewer invocation (`...-RH-R4`) and remote test results. The handoff
     explicitly instructed "Do not commit or deploy until independent review
     and focused verification pass" and warns that stopped-child reports are
     not evidence.
   - problem: the change was committed before this independent gate, and the
     commit embeds a review-artifact in product git history (the
     `review/gates/` artifacts are untracked by convention in this repo — the
     analogous tensor-bool gate file is untracked). The embedded gate's PASS
     claim is not verifiable from this review's designated inputs.
   - impact: the branch is not in the exact two-file review shape required for
     PASS; deployment of HEAD would carry an unverified, pre-gate PASS into
     history and could mislead subsequent automated gates.
   - recommended_correction: after this review, re-cut the branch commit so it
     contains **only** the two product files (remove the committed
     `review/gates/REVIEW-20260910-RH-SPEC-BUDGET-RETRIGGER-R3.md` from the
     commit; keep gate artifacts untracked under `review/gates/` as
     convention), preserving the reviewed code content, then proceed to the
     test-runner's focused gate and the live re-trace.
   - confidence: high (directly observed).

### Non-blocking findings

2. **[MEDIUM | VERIFIED] Explicit "cursor 0 / current 0 not cleared"
   regression (DEBUG3060 required-list #1) is not added.**
   - problem: the DEBUG required a policy-level guard test that a SPEC_BUDGET
     entry with cursor 0 and current 0 is not cleared (the exact `<=` hazard).
     The new tests cover cursor-N-with-current-0 cleared end-to-end, and the
     existing policy test covers the equal-cursor guard at 20/20 (which also
     rejects `<=`), so the strict-`<` semantic is protected in source and by
     suite; only the literal 0/0 case is unasserted.
   - recommended_correction: add one assertion
     `assertFalse(self._cleared(_neg(reason=SPEC_BUDGET, cursor=0), epochs=_epochs(spec=0)))`
     next to `test_spec_budget_cleared_only_by_budget_release`.
   - impact: none on current code (guard verified unchanged); closes a
     specified regression gap.

3. **[LOW | VERIFIED] Pre-existing no-op membership test in the tail-park
   loop.** `if rest.rid in plan.to_issue or ...` compares a `str` rid against a
   list of `ReadyHorizonView` objects and is always False, so the tail-park
   covers every un-tried candidate (to_issue members included). Identical in
   HEAD~1 (not introduced by this fix); the conservative effect is consistent
   with the design (no further speculative attempt after budget exhaustion in
   the same pass) and does not affect this fix's correctness. Flagged for
   awareness only; out of scope to change here.

4. **[LOW | VERIFIED] Diagnostics note for the test-runner gate.** The stage
   event's `speculative_budget_used_tokens` and the decision emission's
   `speculative_used` are read pre-issue (`scheduler.py:4708`) and will still
   show the pre-issue value on the pass that parks B. The field that proves the
   fix is the negative entry's `negative_cursor` (telemetry field
   `negative_cursor`, `scheduler.py:4221`), which now carries the post-issue
   level (54,999 in the incident). The remote focused/live assertions should
   key on `negative_cursor`, not on that stage event's speculative_used field.
   Pre-existing behavior; no code change requested.

## Summary

The product-code fix (the two authorized files) is correct, minimal, and
faithful to the accepted DEBUG3060 root cause: the SPEC_BUDGET decline cursor
is captured at the post-issue instant from the live speculative-inflight
counter, the strict `<` wake is preserved, NO_L3/NO_HEADROOM semantics are
untouched, and a physical-only limiter no longer receives a speculative
negative-cache cursor. The two added unit regressions are meaningful and
exercise the real pass/park source. No blocking correctness, security,
compatibility, storage, or restore finding was established in the code content.

The overall gate is **REQUEST_CHANGES** solely on scope/governance: the change
is already committed (HEAD) ahead of this independent review and the commit
contains a third, unauthorized review-artifact file that asserts an
unverifiable PASS. The branch must be re-cut to the two product files before
deployment acceptance.

## Followups

- Re-cut commit `4f41f5bab5` to contain only `python/sglang/srt/managers/scheduler.py`
  and `3090-dev/test_ready_horizon_unit.py` (drop the committed
  `review/gates/...-R3.md` artifact); keep the reviewed code content unchanged.
- Add the literal cursor-0/current-0 strict-`<` regression assertion (Finding 2).
- Run the focused `3090-dev/test_ready_horizon_unit.py` suite in the
  dependency-complete environment (remote venv with `orjson 3.12.0`); the local
  shell cannot import the runtime (no `orjson`) — this is the tester's separate
  gate and is not part of this review's PASS inputs.
- Re-run the identical live RH-ON blocker+A/B 55K trace; acceptance requires B
  to wake after the speculative-budget release with a completed RH stage /
  Host-ready state before admission, `negative_cursor=54999` in the park, no
  `cached=0`, and no full-history recompute.

## Open issues

- Runtime normal event (`rh_stage.v2` for B after release) is UNPROVEN until
  the remote focused test and live re-trace run.
- The committed R3 gate artifact cites review/test reports
  (`work/REVIEW3060-RH-SPEC-BUDGET-RETRIGGER-R3-20260910.md`,
  `work/TEST3060-RH-SPEC-BUDGET-RETRIGGER-R2-20260910.md`) that exist on disk
  but were not among this review's designated must-read inputs and, per the
  handoff, derive from paused child invocations; their claims were not treated
  as evidence here.
- No product file, deployment state, remote host, or unrelated process was
  modified by this review. Only the two assigned report files were written.

## Communication

- This report is written to both assigned paths:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260910-RH-SPEC-BUDGET-RETRIGGER.md`
  and
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/REVIEW3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`.
- No lifecycle event was dispatched by this review invocation.
