# Handoff — 3060 RH SPEC_BUDGET follow-up, session 2

Date: 2026-09-10  
Audience: **new Claude session** continuing the 3060 Ready Horizon work.  
Status: **PAUSED_FOR_SESSION_HANDOFF**

- Live RH blocker+A/B acceptance: **NOT VERIFIED**.
- Cleanup: **SAFE-NOOP**; no cleanup operation was executed by this session.
- Code content gate: **VERIFIED** by the independent R3 review, but the overall governance gate is **REQUEST_CHANGES**.
- Remote exact commit identity: **UNKNOWN** because the remote checkout is not Git.
- Do not treat reports from prior stopped child invocations as evidence. The facts below are reconciled only from the designated reports and the final RH ledger entries.

## 1. Goal and acceptance criteria

Goal: preserve the exact state after the 3060 Qwen3.5-4B AWQ/Marlin + FP8 KV + hierarchical file-backed HiCache Ready Horizon `SPEC_BUDGET` re-trigger follow-up and cleanup attempt, so a new session can continue without repeating work or trusting stale claims.

The code change addresses the accepted causal defect: request B captured a pre-issue speculative-budget cursor of `0`; after request A's speculative reservation released, the strict wake rule evaluated `0 < 0` and did not re-trigger B. The product fix records the post-issue speculative level for `SPEC_BUDGET` parks and keeps physical-only limiter behavior separate.

A clean live acceptance run must prove, for the specifically identified request B:

1. B has the expected post-issue park cursor, specifically `negative_cursor=54999` in the 55K scenario.
2. B wakes after speculative budget release.
3. B completes the RH stage / Host-ready state **before** admission.
4. B does not show `cached=0`.
5. B does not enter full-history recompute.
6. HTTP health and request correctness gates pass, and the cleanup gate is satisfied without deleting retained evidence.

The broad unit file is not green and must not be represented as green merely because the two new focused tests pass.

## 2. Confirmed baselines and evidence

### Product workspace and branch

- Product workspace: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- Branch: `3060-12g-qwen35-4b`
- Current HEAD: `4f41f5bab562b99562f30c67540eb05344d13637`
- HEAD subject: `[3060] retrigger ready horizon after speculative budget release`
- No 3090 production-candidate state machine changes were made.

### Commit shape and governance deviation

**VERIFIED:** HEAD contains these two product/test files:

- `python/sglang/srt/managers/scheduler.py`
- `3090-dev/test_ready_horizon_unit.py`

It also contains the committed review gate artifact:

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260910-RH-SPEC-BUDGET-RETRIGGER-R3.md`

This is a governance deviation. Do not silently rewrite published or deployed history. The independent R3 review reports:

- `code_gate: PASS` — the two product-file changes are bounded and match the accepted root cause.
- overall verdict: `REQUEST_CHANGES` — HEAD was already committed before that independent gate and includes the third tracked review artifact.
- runtime normal event: `UNPROVEN`.
- deployment acceptance: `NOT_READY`.

A prior concurrent logical gate claimed a narrow PASS, but it is **not** the R3 independent-review evidence and must not override the R3 governance finding. The R3 review also notes a non-blocking literal `cursor=0/current=0` assertion gap; the strict `<` policy itself remains unchanged.

### Test evidence

**VERIFIED:** The remote focused pytest selection ran against the two changed files in the dependency-complete remote venv:

```text
2 passed, 70 deselected, 2 warnings, exit 0
```

The two passing tests cover post-issue `SPEC_BUDGET` cursor wake and physical-only limiter separation.

**VERIFIED:** The full remote unittest file ran 72 tests:

```text
66 passed, 2 failures, 4 errors; 0 skipped; 0 not executed
```

The six failures are pre-existing fixture/API expectation mismatches, not a green full-file result:

- one legacy enum-identity expectation versus typed `PrefetchIssueResult`;
- one legacy `evt=ready_stage.v2` token expectation versus current `evt=ready_stage schema=rh_stage.v2` output;
- four deterministic-miss fixtures whose fake `charge()` does not accept the current required `origin=` keyword.

Therefore: **do not claim the full suite is green**. Local syntax checks (`py_compile`, `compileall`, and `git diff --check`) were reported passing. Remote test file copies were restored byte-identically after testing.

### Accepted code diagnosis

**VERIFIED:** The debugger's causal diagnosis and the R3 code review agree that the strict `<` wake condition is correct and must not be widened to `<=`. The patch captures post-issue speculative epochs for the two `SPEC_BUDGET` park paths, while preserving `NO_L3`, `NO_HEADROOM`, and physical-only limiter distinctions. No storage/restore, admission, telemetry redesign, or 3090 state-machine change is part of this handoff.

## 3. Remote current state and preserved paths

Remote target:

- SSH target: `root@i-1.gpushare.com:27460`
- Checkout: `/root/sglang-3060-12g-hicache`
- Venv: `/root/sglang-env-3060-4b`
- Model: `/hy-tmp/models/Qwen3.5-4B-AWQ`

**VERIFIED by the latest bounded audit:**

- service health: HTTP `200`;
- current SGLang master PID: `212252`;
- profile: RH-ON, c1;
- command uses hierarchical, file-backed HiCache and Ready Horizon, including `--enable-hierarchical-cache`, `--hicache-storage-backend file`, `--hicache-storage-prefetch-policy wait_complete`, `--enable-ready-horizon`, and `--ready-horizon-frontier-n 8`;
- `/` has approximately `14G` free;
- `/hy-tmp` has approximately `25G` free (`50G` total, about `51%` used).

The remote checkout is not a Git repository. Exact source-commit identity on the remote is therefore **UNKNOWN** and must not be inferred cryptographically from the deploy-log filename.

Preserve these paths and evidence:

- `/hy-tmp/models/Qwen3.5-4B-AWQ` — approximately `6.7G` model; **do not delete**.
- `/hy-tmp/hicache-restore-r3` — approximately `12G` historical HiCache restore evidence; **do not delete**.
- `/tmp` logs and historical evidence, including `/tmp/sglang3060-rh-fix-4f41f5.log`, `/tmp/t38c-probe.log`, and `/tmp/b15-probe.log`; preserve until explicitly authorized otherwise.
- Named old run directories `sglang3060-rh-horizon-r1`, `sglang3060-rh-queue-r1`, and `t38c-durable-trace` were absent in the bounded audit. The deletion list was empty.

The first cleanup audit was stopped for excessive scanning before mutation. The bounded R2 audit found no clearly safe deletion candidates and performed no deletion. The source of the reclaimed/free space is **UNKNOWN**; do not attribute it to this session.

### Concurrent trace and relaunch history

The prior concurrent run/relaunch involved:

- earlier service master PID `173342`, then replacement PID `176538`;
- a concurrent approximately 55K two-request trace;
- SIGTERM/relaunch during the trace.

This is not a clean acceptance run. Read-only evidence showed one RID progressing through `ready_host` to READY preadmission and then `admission.v2 ready_host_observed=true`; the other RID emitted `restore_recompute cause=timeout`. Readable artifacts did not establish A/B labels, the driver's join/output conclusion, or the required B-specific no-`cached=0` and no-full-history-recompute result. The latest service state is the bounded-audit PID `212252`, not an acceptance conclusion.

## 4. Open blockers and governance issue

1. **Live RH gate — NOT VERIFIED.** The concurrent run has partial evidence for one RID but is interrupted/non-clean and lacks readable A/B driver/join correlation. No clean B-specific acceptance has been established.
2. **Governance — REQUEST_CHANGES.** The fix is already in published HEAD together with the third tracked R3 gate artifact. Decide, with the authorized owner, whether governance is handled by a forward corrective commit or by preserving the historical commit as-is. Do not rewrite history without explicit authorization.
3. **Broad test file — NOT VERIFIED green.** Record exactly `66 passed, 2 failures, 4 errors`; the six mismatches remain open.
4. **Remote lineage — UNKNOWN.** The non-Git remote checkout prevents cryptographic HEAD verification.
5. **Concurrent actor — UNKNOWN until the next read-only liveness check.** The latest audit established the service PID and health, but does not establish that no actor is currently active.
6. **Cleanup — SAFE-NOOP.** There is no approved deletion list; retained model, current cache, historical restore evidence, and `/tmp` logs remain protected.

## 5. Strict prohibited actions

- No blind rerun of the live blocker+A/B trace.
- Do not delete the model, current service cache, `/hy-tmp/hicache-restore-r3`, or `/tmp` logs/history.
- Do not rewrite published/deployed Git history silently.
- Do not push without explicit authorization.
- Do not launch S=100, S=500, or S=1000 parked-fleet scale experiments.
- Do not start a new trace while concurrent actor liveness or service state is unknown.
- Do not use the interrupted concurrent trace as a clean acceptance result.
- Do not claim full-suite green, exact remote commit identity, or RH acceptance from partial telemetry.
- Do not perform cleanup merely because free space changed; the source of the change is unknown and the bounded deletion list is empty.

## 6. Exact recommended next DAG for the new session

Execute this DAG in order; do not skip the read-only and authorization gates:

**A.** Perform a read-only check of current service/process state and concurrent-actor liveness.

**B.** Obtain the concurrent driver's driver/join output if it is available; correlate request IDs to the intended A/B labels and preserve the output as evidence. If it is unavailable, retain live acceptance as NOT VERIFIED.

**C.** Decide whether the governance issue is handled by a forward corrective commit or by historical preservation. Do not rewrite published history without explicit authorization.

**D.** Only after A–C, obtain explicit authorization for any cleanup or live trace. No cleanup is implied by this handoff.

**E.** If a clean trace is explicitly authorized, use a fresh evidence namespace and require all of the following: B-specific `negative_cursor=54999`; wake after speculative release; RH stage/Host-ready before admission; no `cached=0`; no full-history recompute; HTTP/correctness gates; and cleanup gate. If any condition is absent, classify live RH acceptance as NOT VERIFIED.

## 7. Report paths and quick-start checklist

Designated source reports:

- `work/HANDOFF-2026-09-10-RH-SPEC-BUDGET.md`
- `work/DEBUG3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`
- `work/CODER3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`
- `work/REVIEW3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`
- `work/TEST3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md`
- `work/TEST3060-RH-SPEC-BUDGET-RETRIGGER-R2-20260910.md`
- `work/RECON3060-RH-LIVE-STATE-R2-20260910.md`
- `work/AUDIT3060-CLEANUP-20260910-R2.md` — **ABSENT**; bounded audit result is recorded above.
- `ledger.md` — final RH entries around the continuation/reconciliation records.

Quick start:

1. Read this handoff and the R3 review/test/recon reports; remember that older stopped-child reports are not evidence.
2. Run only DAG step A first: read-only service/process and actor-liveness check.
3. Seek the concurrent driver's join output (DAG step B); do not infer A/B mapping from the partial log alone.
4. Resolve the commit-shape governance choice with authorization before any history action, deploy, cleanup, or trace.
5. Preserve all retained paths and exact VERIFIED / NOT VERIFIED / UNKNOWN labels.

## Worker envelope

status: done
artifacts:
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/HANDOFF-2026-09-10-RH-SPEC-BUDGET-SESSION2.md`
evidence:
- Designated handoff, debugger, coder, review, test, recon, and final RH ledger entries were reconciled.
- Cleanup audit artifact was absent; its bounded result was preserved exactly as dispatched: health 200; PID 212252; `/` 14G free; `/hy-tmp` 25G free; model 6.7G and historical `hicache-restore-r3` 12G preserved; named old run directories absent; deletion list empty.
summary:
- Durable session-2 handoff written with the exact commit, review, test, live-state, cleanup, governance, prohibition, and next-DAG state. Live RH acceptance remains NOT VERIFIED and cleanup remains SAFE-NOOP.
followups:
- New session should begin with DAG step A read-only service/process and actor-liveness check, then obtain the concurrent driver's join output before considering any trace or cleanup authorization.
open_issues:
- Live B-specific acceptance is NOT VERIFIED.
- HEAD's committed review artifact remains a governance deviation requiring an authorized forward-correction-versus-historical-preservation decision.
- Broad unittest file remains 66 passed, 2 failures, 4 errors.
- Remote exact commit lineage and current concurrent-actor liveness are UNKNOWN.
