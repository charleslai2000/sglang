ENTRY: ACCEPT

status: blocked
task_id: TEST3060-RH-CONTRACT-CORRECTIONS-20260909
orchestration_epoch: 20260909-rh-ab26
role: tester
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
revision: 7831d45dd469857b34b9b5d15d99b85751aa1121
verdict: BLOCK

## Artifacts

- Independent report: this file.
- Verified commit: `7831d45dd469857b34b9b5d15d99b85751aa1121`.
- No source, gate, or remote-host files were modified.

## Evidence

Passed:

- `python3 3090-dev/test_prefetch_gate_skip_regression.py` — 2 tests OK.
- `python3 3090-dev/test_rh_contract_dependency_free.py` — 2 tests OK.
- In-memory `compile()` for all seven changed source/test files — PASS.
- `git diff --check 3785c99759..7831d45dd4` — PASS.
- Independent AST caller scan — all six `_prefetch_kvcache` callers provide explicit origins.
- Independent AST lifecycle harness — `LIFECYCLE_OK`: successful issue retains the active attempt; duplicate issue is `SKIPPED_ACTIVE`; stale release cannot clear it.
- Independent terminal harness — `STALE_TERMINAL_OK`: stale `(attempt_id, terminal)` completion leaves a newer active claim and restore state unchanged.
- Independent queue-order harness — `RH_ORDER_OK`: RH-OFF issues with `EAGER_RH_OFF` before queue append; RH-ON appends first and does not eagerly issue.
- Terminal attempt propagation is present at all four cache terminal-write sites.
- Commit scope is exactly the seven reported files; no allocator, Mamba, HOST_ALLOC generation, persistence, or unrelated authority diff was found.

Focused project attempts:

- Direct execution without `PYTHONPATH` fails at `ModuleNotFoundError: sglang`.
- With `PYTHONPATH=python`, RH unit/partition tests fail during package import on missing `orjson`.
- `3090-dev/test_prefetch_budget_split_unit.py` ran 24 tests: 11 pass, 12 errors, 1 skip; issue-path errors hit the test double's missing `_t38c_request_contexts`, and scheduler-wiring cases hit the unavailable package import. No packages were installed.
- `test/registered/unit/managers/test_hicache_restore_prefetch_budget.py` remains blocked by missing `orjson`.

## Findings

1. **Blocking gate admission remains unresolved.** `ARCH-20260909-RH-PREADMISSION.md` is `status: proposed`, `implementation_authority: none`, and `implementation_admission: BLOCKED_PATTERN_INTAKE_AND_NOVEL_DECLARATION`. The Novel Mechanism artifact is proposed/non-self-approving, and the Pattern Intake is conditional and pinned to revision `82ab235606...`, not the verified commit. No accepted authority decision is present.

2. **Readiness join evidence is incomplete.** At `python/sglang/srt/managers/scheduler.py:3839-3843`, every `rh_ready_host.v1` emission supplies `required_aux_pools=None` and `completed_aux_units=None`; no per-attempt auxiliary completion values are derived from the finalized operation. `completed_kv_tokens` is obtained, but the required hybrid material fields remain unavailable. Per the architecture contract, missing mandatory readiness fields make the join `not_computable`, so RH-G08/G09 and the required hybrid readiness join are not accepted by this revision.

## Summary

The former successful-issue classification, active-claim lifetime, stale-release fencing, typed result, origin wiring, and gate-skip regression are corrected and independently exercised within dependency-free scope. RH-OFF/RH-ON order and no allocator/Mamba authority leakage also pass static/direct checks. Overall acceptance is **BLOCKED** by the unaccepted architecture/pattern/Novel Mechanism gate chain and the incomplete `ready_host` material join.

## Followups

- Obtain accepted RH architecture, Pattern Intake, and Novel Mechanism decisions pinned to the implementation revision, then rerun this gate under a fresh Task ID.
- Provide an initialized dependency-backed test environment and a deterministic hybrid ready-host fixture that emits actual auxiliary pool fields.
- Run the required bounded RH-OFF/RH-ON runtime trace and independent telemetry join/performance evidence under a fresh Task ID.

## Open issues

- Dependency-backed tests, live runtime/E2E, and performance evidence were not computable in this environment; this is an environment/test-fixture limitation, not a pass.
- The report is blocked, not pending: the active invocation is complete and further implementation, gate, runtime, or review work requires a fresh Task ID.
