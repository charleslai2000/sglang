ENTRY: ACCEPT

STATUS: done

# P0.1 readiness-to-residency timing-fix independent gate

- Task ID: `REV-20260908-P0-RESIDENCY-R17-TIMING-FIX1`
- Orchestration epoch: `phase2-hicache-design/2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Gate verdict: **REJECT**
- Live/remote decision: **not authorized by this gate; do not proceed to 1–2 node live validation**.

## Scope

Read-only review of:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `3090-dev/test_p0_residency_barrier_emitter.py`
- implementation report `COD-20260908-P0-RESIDENCY-R17-TIMING-FIX1.md`
- architecture contract `ARCH-20260908-P0-RESIDENCY-R17-TIMING-CONTRACT.md`
- prior FIX5/FIX6/node-sidecar/node-lookup gates for context

The aggregate `sglang-3090-24g-opt` worktree is dirty and has no task-specific commit boundary. Findings below are attributed only to the authorized source/test paths and the timing-fix behavior visible there. No product code, test, ledger, context, plan, remote host, live process, vehicle, or deployment was modified or executed.

## Evidence

Local checks independently run from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `python3 3090-dev/test_p0_residency_barrier_emitter.py` — PASS.
- `python3 3090-dev/test_p0_trace_context_v4.py` — PASS.
- `PYTHONPYCACHEPREFIX=/tmp/codex-p0-r17-review-pycache python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_residency_barrier_emitter.py` — PASS.
- Independent `ast.parse` of both authorized Python files — PASS.
- `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py` — PASS.
- `git diff --no-index --check /dev/null 3090-dev/test_p0_residency_barrier_emitter.py` — expected status 1 because the fixture is untracked; no whitespace diagnostics were produced.

The passing fixture is dependency-free and primarily extracts helper functions through AST. It is useful evidence for identity, queue-snapshot, and selected barrier predicates, but it does not establish the complete production timing contract.

## Blocking findings

### B1 — Production MAMBA detach admission is explicitly skipped

- Severity: **P0 / blocking**
- Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:1157-1180`, especially line 1162.
- Evidence: `_t38c_residency_log` iterates `result.device_frees` and `result.host_frees`, then executes `if not values or component_type == ComponentType.MAMBA: continue`. Therefore production MAMBA frees never call `_t38c_note_detach`. The completion paths at `:3285-3317` and `:3319-3349` can call `_t38c_note_completion` for MAMBA, but `_t38c_note_completion` only accepts tokens found in `_t38c_residency_detached` (`:533-549`); no production MAMBA expected token exists.
- Acceptance impact: the strict fold can prove only the admitted KV token set. It cannot prove the MAMBA detach/free completion required by the contract, despite checking MAMBA component presence. This violates the FULL/KV + MAMBA snapshot/token lifecycle and the preserved durability/at-most-once readiness invariants. The focused fixture does not catch it because it calls `_t38c_note_detach` directly for MAMBA (`test_p0_residency_barrier_emitter.py:852-867`, `:970-975`) instead of running `_t38c_residency_log` with production free results.
- Recommended action: under a fresh Task ID, make production detach admission cover every supported P0.1 component/tier that can be freed, including MAMBA, and add an integrated regression that runs `_t38c_residency_log` plus the corresponding free/completion path. Do not compensate by weakening the component or token predicates.

### B2 — Queue-drain readiness still depends on the polling/checkpoint path

- Severity: **P0 / blocking**
- Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:1015-1029`, `:1122-1149`, and `:6265-6270`.
- Evidence: on a non-empty queue, the barrier only adds the identity to `_t38c_residency_reconcile_ready` (`:1018-1019`). The only consumer is `_t38c_poll_residency_barriers` (`:1137-1149`), and the production storage-control implementation calls that poll at the end of the drain (`:6270`). There is no queue-owner drain-to-empty callback that directly reconciles the affected identities after the locked drain transaction. The focused fixture manually removes the queued item and then calls `poll(queued)` (`test_p0_residency_barrier_emitter.py:1067-1070`); it does not demonstrate publication with polling disabled or a queue-drain event callback.
- Acceptance impact: `release_queues_drained` is not independently event-driven as required by `R17-T4`/`R17-T7`; a queue becoming empty through another owner path can leave a fully ready identity pending indefinitely. Polling remains a correctness/liveness dependency, contrary to the authoritative contract and the timing-fix goal.
- Recommended action: under a fresh Task ID, have the owning drain transaction enqueue/invoke one idempotent exact-identity reconcile after it commits the empty transition, preserving cache-residency-lock outermost and handoff-lock inner ordering. Add a watchdog-disabled test that drains without invoking the poll helper.

### B3 — No explicit detach-seal/complete expectation boundary

- Severity: **P0 / blocking**
- Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:866-936`.
- Evidence: the fold requires only a non-empty expected set and one device entry (`:866-887`), then sets `lifecycle["detach_sealed"] = True` and advances to `DETACH_SEALED` immediately when the current snapshot reports no live values (`:891-936`). There is no separate event/fact proving that all detach expectations for the one-shot release have been registered. In combination with B1, a later MAMBA detach can be absent from the expected set when the fold seals and proceeds.
- Acceptance impact: the lifecycle can advance and publish from a partial expectation set. This does not satisfy the contract’s ordered `build registration -> detach/seal -> durability -> free completion -> queue drain -> retirement` lifecycle or its requirement that publication cover all exact release tokens.
- Recommended action: under a fresh Task ID, define and trigger an explicit exact-identity detach-seal boundary after all applicable component/tier detach expectations are registered and component absence is committed; reject or retire incomplete/unsupported manifests fail-closed.

### B4 — Diagnostic suppression violates the required attempt/terminal evidence contract

- Severity: **P1 / blocking for this gate**
- Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:623-637`, `:648-723`, and publication/retirement calls at `:1080-1094` and `:440-452`.
- Evidence: when `(identity, reason)` is already in `_t38c_residency_outcomes`, the function increments only `suppressed_diagnostic_count` and returns (`:625-631`). It does not increment `reconcile_attempt_count` or that reason’s `reason_attempt_counts`, although the contract requires repeated reconciles to increment those counters. Terminal records also contain neither `first_failure_event_id`, `observed_reasons`, `reason_attempt_counts` as terminal aggregates, `first_attempt_ts_mono_ns`, `last_attempt_ts_mono_ns`, nor the required publication/retirement causal field set. `_t38c_durable_log` defaults records to `schema_version: p0_durable.v2` at `:265`, while the authoritative timing contract requires the P0.1 evidence schema.
- Acceptance impact: bounded physical logging is present, but the required identity/reason/terminal constraints are not verifiable from the emitted records. Diagnostic accounting is therefore not merely a presentation issue; it fails the gate’s evidence contract and can conceal the number of strict retries.
- Recommended action: under a fresh Task ID, separate strict attempt accounting from physical record deduplication, emit the complete terminal aggregate schema, and preserve logger-failure behavior as pending/retryable.

### B5 — Focused fixture does not cover the required two-identity and production-boundary matrix

- Severity: **P1 / blocking evidence gap**
- Location: `3090-dev/test_p0_residency_barrier_emitter.py:17-112`, `:843-942`, `:956-1073`.
- Evidence: the loader extracts helper functions rather than invoking the production `_t38c_residency_log`/free integration. The tests use one logical identity per cache; the “two cache” isolation probe (`:1081-1097`) is not the contract’s one-cache/two-final-build-identity gate. Component coverage sets MAMBA device live only (`:881-914`), not each FULL/MAMBA device/host field. Queue drain publication explicitly calls `poll` (`:1067-1070`). There is no watchdog-disabled queue-drain callback test, no unknown/inactive component fail-closed matrix, no logger-failure terminal retry assertion, and no bounded terminal-schema assertion.
- Acceptance impact: criterion 6 and the contract’s required A/B deterministic gate are not met. Passing this fixture cannot authorize a live test because the missing cases are exactly the boundaries that determine whether readiness is safe.
- Recommended action: under fresh Task ID(s), extend or replace the fixture with production-boundary tests for two identities in one cache, all four component fields, unsupported/missing snapshots, exact MAMBA tokens, queue drain without polling, logger failure, terminal evidence, and retirement/reattachment.

## Non-blocking observations

- The focused fixture, V4.3 fixture, compile, AST, and whitespace checks pass locally.
- Final-node-only build admission, typed lookup, six-field identity construction, queue lock nesting, and at-most-once identity key are present in the reviewed source and prior accepted narrow gates. Those positives do not override the blocking timing/integration findings above.
- The worktree contains unrelated historical modifications and untracked files; no task-specific commit boundary exists. Preserve path-level attribution for any future re-review.

## Followups

- Fix B1–B5 only under fresh Task ID(s), then obtain a new independent review of the resulting diff and deterministic A/B evidence.
- Re-run focused, V4.3, py_compile, AST, and diff checks after the new implementation.
- Do not recommend or execute remote/live validation from this rejected gate. A later live task may be considered only after a new gate explicitly ACCEPTs the deterministic contract.

## Open issues

- P0.1 readiness-to-residency timing contract is not accepted.
- Production MAMBA detach/free ownership is not proven.
- Queue-drain event-driven liveness is not proven without polling.
- Terminal diagnostic evidence schema/accounting is incomplete.
- Required two-identity and production-boundary focused coverage is missing.
- No live/remote result exists; this is an intentional non-execution boundary, not evidence of runtime success.

## Status packet

- Status: `done`
- Artifacts: this gate report and the specialist report at `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-R17-TIMING-FIX1.md`.
- Evidence: direct source/contract/report review plus local focused, V4.3, py_compile, AST, and diff checks; no remote/live execution.
- Summary: **REJECT**. The implementation has useful narrow local coverage but fails the P0.1 timing contract at production MAMBA admission, queue-drain event triggering, detach sealing, diagnostic terminal accounting, and required A/B fixture coverage.
- Followups: fresh Task ID(s) for remediation and deterministic re-review; no direct live recommendation.
- Open issues: all items listed above remain unresolved.
