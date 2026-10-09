# CODER3060-RH-MATCH-PREP-CLOSE-20260909

status: done
task_id: T3060-RH-MATCH-PREP-CLOSE-20260909
orchestration_epoch: 20260909-rh-ab50
role: coder
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
commit: c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a
commit_message: "fix(hicache): close RH current-match gate"

## Artifacts

- Commit `c4ad01ef5d7578bb542fe3e514a71cdbccb6c07a`.
- This report.

## Changed files and symbols

- `python/sglang/srt/managers/scheduler.py`: pass-local prepared-match
  capability; RH candidate reason/disposition; valid-ticket consumption and
  one fallback rematch through `_prefetch_kvcache_impl`; fail-closed anchor
  validation; no-COW observation; and `rh_match_prepare.v1` telemetry.
  Changed symbols include `_ReadyHorizonPreparedMatch`, `_prefetch_kvcache`,
  `_prefetch_kvcache_impl`, `_rh_match_candidate`,
  `_rh_match_candidate_reason`, `_rh_mamba_snapshot`,
  `_rh_match_observation`, `_emit_rh_match_prepare`,
  `_prepare_ready_horizon_match`, `_rh_prepared_match_valid`,
  `_ready_horizon_pass`, and `_ready_horizon_views`.
- `python/sglang/srt/mem_cache/unified_radix_cache.py`:
  `UnifiedRadixCache.has_restore_potential` adds only the authorized
  L3-durable parity disjunct.
- `3090-dev/test_rh_contract_dependency_free.py`: real-path focused RH
  consumption, fallback, fail-closed anchor, lifecycle, telemetry, and
  no-COW allocator/eviction-state oracles.
- `3090-dev/test_ready_horizon_unit.py` and
  `3090-dev/test_prefetch_gate_skip_regression.py`: prepared-match-compatible
  focused fixtures.

Telemetry now emits the required `restore_state_before`,
`match_duration_us`, Mamba change flags/counters, `buffer_device_fallback`
anchor classification, explicit nullable fields, and bounded zero-match
skipped/ineligible records. Emission and telemetry-side anchor inspection are
observational and fail closed without affecting control decisions.

## Evidence

- `python3 3090-dev/test_rh_contract_dependency_free.py`: 15 passed.
- `python3 3090-dev/test_prefetch_gate_skip_regression.py`: 2 passed.
- `python3 -m py_compile` for both product files and three focused tests: passed.
- `python3 -m compileall -q` for the same files: passed.
- `git diff --check`: passed before commit.
- Final committed file scope was exactly the five authorized tracked files
  listed above. Existing untracked gate/memory artifacts were not staged.
- No deployment or live load was run.

## Followups

- Independent tester/reviewer should collect package-backed evidence at this
  immutable commit when dependencies are available.
- A separate runtime task is still needed for paired RH-OFF/RH-ON evidence;
  this coder task did not run live load.

## Open issues

- `PYTHONPATH=python python3 3090-dev/test_ready_horizon_unit.py` could not
  collect because the environment lacks `orjson` (`ModuleNotFoundError`).
  The dependency-free production-method harness was used instead; it does not
  substitute for package-backed runtime acceptance.
- Formatter/type-check tools (`ruff`, `black`, `mypy`, `pyright`, and
  `pre-commit`) are unavailable in the environment. Compile and diff checks
  passed.
- No package-backed or live proof is claimed for runtime telemetry joins,
  allocator/eviction counters in actual cache components, RH-OFF/RH-ON
  paired behavior, performance, or deployment.
