ENTRY: ACCEPT

status: done
task_id: CODE3060-RH-READY-HOST-AUX-20260909
orchestration_epoch: 20260909-rh-ab27
role: coder
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
base_commit: 7831d45dd469857b34b9b5d15d99b85751aa1121
commit: 6881529acbb55c9dc55745d08fca62b585ecdbad

## Artifacts

- Product/test commit `6881529acbb55c9dc55745d08fca62b585ecdbad`.
- This report is the only artifact written outside the authorized source
  repository.
- Changed files are limited to:
  - `python/sglang/srt/managers/scheduler.py`
  - `python/sglang/srt/mem_cache/unified_radix_cache.py`
  - `3090-dev/test_rh_contract_dependency_free.py`

## Data source and implementation

- `UnifiedRadixCache._handle_prefetch_result` remains the authority for the
  existing hybrid all-or-nothing check and already derives sidecar completion
  from `operation.pool_transfers` and
  `operation.pool_storage_result.extra_pool_hit_pages` through
  `_host_alloc_hybrid_sidecar_counts`.
- The finalizer now records a one-shot completion handoff containing the
  authoritative `completed_kv_tokens`, sorted actual auxiliary pool names,
  actual fetched auxiliary counts, and the finalizer result (`accepted` or
  `discarded`). It carries the existing prefetch attempt ID alongside the
  terminal handoff and does not alter Mamba, allocator, restore, or
  all-or-nothing authority.
- Scheduler `ready_host` emission consumes that completion handoff after the
  existing attempt-correlated terminal check, so a completed Mamba/hybrid
  finalization emits actual `required_aux_pools` and `completed_aux_units`
  rather than unconditional nulls. Legacy doubles without the optional
  handoff remain compatible.
- Abort/reset cleanup removes the one-shot completion record.

## Evidence

Passed:

- `python3 3090-dev/test_rh_contract_dependency_free.py` — 3 tests OK,
  including actual Mamba pool/count completion fields.
- `python3 3090-dev/test_prefetch_gate_skip_regression.py` — 2 tests OK.
- `python3 3090-dev/test_storage_regression.py RestoreDurabilityMarkingTests`
  — 4 tests OK, including accepted and discarded hybrid finalization.
- `python3 3090-dev/test_storage_regression.py
  FrontierWaiterRegistryTests.test_release_aborted_request_cleans_waiter_and_terminal`
  — abort cleanup test OK.
- `python3 -m py_compile` and `python3 -m compileall -q` for all three changed
  files — PASS.
- Independent `ast.parse` checks for all three changed files — PASS.
- `git diff --check` and post-commit `git diff HEAD^ HEAD --check` — PASS.
- Commit scope audit — exactly the three listed authorized files; pre-existing
  untracked `.memory/`, `review/gates/`, and `storage/` artifacts were not
  staged or modified.

Unavailable or unrelated:

- `ruff format --check`, `black --check`, and `mypy` could not run because the
  tools are not installed.
- Full `python3 3090-dev/test_storage_regression.py` ran 126 tests with 21
  skips and 5 errors in pre-existing host-allocation telemetry/component test
  fixtures missing `_host_allocability_telemetry_seq` or `components`; the
  changed finalizer/cleanup tests pass independently. No packages were
  installed and no unrelated failures were changed.

## Summary

Done. Ready-host telemetry now joins the authoritative hybrid finalizer's
actual auxiliary pool names and completion counts, while preserving existing
claim, terminal, scheduler, and all-or-nothing hybrid behavior.

## Followups

- Fresh tester/reviewer dispatch should independently verify the event join and
  runtime hybrid fixture when the dependency-backed environment is available.

## Open issues

- Formatter/typecheck tooling is unavailable in this environment.
- The broader storage regression retains the five unrelated fixture errors
  listed above.
- Remote runtime, gate acceptance, deployment, and other follow-on work require
  a fresh Task ID.
