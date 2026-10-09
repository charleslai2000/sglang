ENTRY: ACCEPT

status: done
task_id: CODE3060-RH-CONTRACT-CORRECTIONS-20260909
orchestration_epoch: 20260909-rh-ab25
role: coder
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
base_review_commit: 3785c99759d4026ebc4364ee46edb07987ed3b1a
commit: 7831d45dd4c9c3511666ff47f24f7bb5b2e50e7a

## Artifacts

- Commit `7831d45dd4c9c3511666ff47f24f7bb5b2e50e7a`.
- Product/test changes are limited to the seven files in that commit.
- This report is the only artifact written outside the authorized source
  repository.

## Changed files and semantics

- `python/sglang/srt/managers/scheduler.py`
  - Returns a frozen typed `PrefetchIssueResult` with status, attempt ID,
    origin, reason, and before/after restore states.
  - A storage outcome of `issued` returns `ISSUED` immediately after the
    restore transition, so the active claim remains held until terminal
    cleanup.
  - Claim release requires the expected attempt ID and terminal reason;
    mismatched releases are diagnosed and cannot clear a newer claim.
  - Terminal cleanup accepts attempt-correlated cache records and ignores
    stale completions before state transition. Existing resource cleanup and
    queued abort/retire ordering remain unchanged.
  - Adds bounded RH decision fingerprint suppression and complete
    `rh_preadmission.v1`, `rh_stage.v2`, `rh_ready_host.v1`, and
    `rh_admission.v2` joins. Missing observations are emitted as `null` where
    the value is unavailable; telemetry is observational.
- `python/sglang/srt/managers/schedule_batch.py`
  - Adds request-local decision ID/fingerprint and enqueue-sequence fields.
- `python/sglang/srt/managers/scheduler_components/hicache_restore.py`
  - Adds the accepted issue-status enum and frozen typed result, retaining
    compatibility aliases for existing scheduler fixtures.
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - Carries the scheduler attempt ID on storage prefetch operations and
    terminal records, while retaining RID cleanup and existing cache
    authority.
- `3090-dev/test_prefetch_gate_skip_regression.py`
  - Updates the dependency-free gate-skip/gate-pass regression to assert
    typed `HELD` and successful typed `ISSUED` with an attempt ID.
- `3090-dev/test_ready_horizon_unit.py`
  - Updates the focused claim-release fixture for attempt-correlated cleanup.
- `3090-dev/test_rh_contract_dependency_free.py`
  - Adds dependency-free tests for successful claim lifecycle, stale release
    fencing, and required telemetry join fields.

## Evidence

Passed:

- `python3 3090-dev/test_prefetch_gate_skip_regression.py` — 2 tests OK.
- `python3 3090-dev/test_rh_contract_dependency_free.py` — 2 tests OK.
- In-memory `compile(source)` for all seven changed source/test files — PASS.
- `git diff --check` — PASS.
- Commit scope audit — exactly the seven authorized product/test files;
  pre-existing `.memory/`, `review/gates/`, and `storage/` artifacts remained
  unstaged and unmodified.

Attempted but unavailable or environment-blocked:

- `ruff format --check ...` — `ruff` is not installed.
- Typecheck — `mypy` is not installed.
- `python3 3090-dev/test_ready_horizon_unit.py` — default environment lacks
  the `sglang` import path; dependency-backed execution was not retried or
  expanded.

## Summary

Done. Reviewer blockers for issued-result classification, active-attempt
retention, attempt-correlated stale cleanup, and the required bounded RH event
joins are corrected while preserving the prior gate-skip fix. The corrected
implementation is committed at `7831d45dd4c9c3511666ff47f24f7bb5b2e50e7a`.

## Followups

- Fresh tester/reviewer dispatch should run dependency-backed focused tests and
  independent gate acceptance when the project runtime environment is ready.
- Runtime deployment or remote validation requires a fresh Task ID.

## Open issues

- Formatter, typecheck, and dependency-backed unit evidence remain unavailable
  in this environment; this report is implementation evidence, not
  independent final acceptance.
- No remote service, seed/storage, gate document, or 3090 branch was modified.
