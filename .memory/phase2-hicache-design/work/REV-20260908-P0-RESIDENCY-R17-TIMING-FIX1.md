ENTRY: ACCEPT

# Independent review report

- Task ID: `REV-20260908-P0-RESIDENCY-R17-TIMING-FIX1`
- Orchestration epoch: `phase2-hicache-design/2026-09-08`
- Role: `reviewer`
- Status: `done`
- Verdict: **REJECT**
- Scope: read-only review of the authorized timing-fix source, focused fixture, implementation report, architecture contract, and relevant prior gates. No product/test repair, remote, or live execution.

## Evidence

Local verification from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- focused residency fixture: PASS;
- V4.3 fixture: PASS;
- `py_compile` for both authorized Python files: PASS;
- independent AST parse of both files: PASS;
- product `git diff --check`: PASS;
- untracked fixture diff-check: expected status 1 with no whitespace diagnostics.

The implementation report’s local evidence is reproducible. It is not sufficient for acceptance because the fixture extracts helpers and does not cover all production boundaries required by the authoritative contract.

## Blocking findings

1. **P0 — MAMBA detach is skipped in the production path.** At `unified_radix_cache.py:1157-1163`, `_t38c_residency_log` explicitly continues for `ComponentType.MAMBA`, so no MAMBA expected release token is admitted. MAMBA completion callbacks at `:3285-3349` cannot establish completion because `_t38c_note_completion` requires an entry already present in `_t38c_residency_detached` (`:533-549`). This allows the fold to prove only KV releases while the contract requires FULL/KV + MAMBA lifecycle evidence. The fixture’s direct MAMBA `_t38c_note_detach` calls (`test_p0_residency_barrier_emitter.py:852-867`) mask this integration defect.

2. **P0 — queue-drain readiness is still polling/checkpoint dependent.** Non-empty queues put identities into `_t38c_residency_reconcile_ready` (`unified_radix_cache.py:1015-1029`); `_t38c_poll_residency_barriers` is the consumer (`:1122-1149`), and the production drain invokes it at `:6270`. No affected-identity reconcile is attached directly to the owning drain-to-empty transaction. The fixture removes a queue item and then manually calls `poll` (`test_p0_residency_barrier_emitter.py:1067-1070`), so it does not prove the watchdog/poll-disabled requirement.

3. **P0 — detach sealing is inferred from a snapshot without an explicit completed-expectation boundary.** The fold sets `detach_sealed` as soon as current component values are absent (`unified_radix_cache.py:891-936`) after checking only a non-empty set and one device detach (`:866-887`). It does not prove that all applicable component/tier detach expectations were registered before entering `DETACH_SEALED`; B1 makes this partial-set path concrete.

4. **P1 — diagnostic attempt and terminal evidence do not meet the contract.** Duplicate `(identity, reason)` outcomes increment suppression only (`unified_radix_cache.py:623-637`), not reconcile or per-reason attempt counts. Terminal records from `:1080-1094` and `:440-452` lack the contract’s terminal aggregate fields, and `_t38c_durable_log` defaults schema v2 (`:265`) rather than the required P0.1 evidence schema. This prevents verification that bounded diagnostics preserve strict retry accounting and terminal causal identity.

5. **P1 — required focused coverage is incomplete.** The fixture does not test two final identities in one cache, all four FULL/MAMBA device/host blockers, production detach/free integration, polling-disabled queue drain, unsupported/missing component fail-closed behavior, logger-failure terminal retry, or the complete terminal diagnostic schema. Its two-cache isolation case is not the required two-identity gate.

## Non-blocking observations

- Final-node-only admission, typed lookup, six-field identity, handoff-lock queue sampling, and at-most-once publication key are present and locally exercised.
- The aggregate worktree is dirty with unrelated history and has no task-specific commit boundary; future acceptance must retain path-level attribution.

## Followups

- Remediate the blocking findings under fresh Task ID(s); do not modify product code as part of this review.
- Add deterministic one-/two-identity tests with watchdog disabled and production free/detach surfaces, then obtain a fresh independent gate review.
- No direct live recommendation follows from this report; a new ACCEPT gate is required first.

## Open issues

- Gate verdict remains REJECT.
- MAMBA release ownership/completion is unproven in production.
- Queue-drain event-driven reconciliation is unproven without polling.
- Detach sealing and terminal diagnostic accounting do not satisfy the architecture contract.
- Required focused coverage is incomplete.
- No remote/live evidence was collected.

## Status packet

- Status: `done`
- Artifacts: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-RESIDENCY-R17-TIMING-FIX1.md` and this report.
- Evidence: independent source/contract review and the local checks listed above.
- Summary: **REJECT**; the timing-fix is not eligible for subsequent 1–2 node live validation.
- Followups: fresh Task ID remediation, deterministic evidence, and fresh independent review.
- Open issues: listed above.
