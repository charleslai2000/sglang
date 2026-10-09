status: done
artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py
evidence:
- Read implementation report CODER-RH-RELEASE-EPOCH-FIX-20260910.md and review report REVIEW-RH-RELEASE-EPOCH-20260910.md before editing.
- Added source-backed scheduler regression coverage: the unsampled ABA test constructs a real UnifiedRadixCache object and calls its production reserve_prefetch/release_prefetch helper for the initial reservation and a replacement reservation, producing a complete 0 -> N -> 0 cycle with speculative_release_epoch advancing to 2.
- The same scheduler test performs a second pass after the wake with no new release and asserts no second issue; the candidate remains in the queue and the release epoch remains 2.
- Extended reservation tests to assert speculative release epoch starts unchanged, increments exactly once on first SPECULATIVE release, remains unchanged on duplicate/no-reservation release, and remains unchanged for DEMAND reservation/release (including a nonzero baseline cursor).
- `python3 -m py_compile /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py` passed.
- `git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt diff --check` passed.
- Dependency-light focused unittest invocation for the four reservation tests passed: 4 tests, OK.
- Attempted focused Ready Horizon scheduler unittest import; it was blocked by the existing missing `orjson` dependency while importing the real scheduler (`ModuleNotFoundError: No module named 'orjson'`). No installation was performed.
- A direct full prefetch test-file run was attempted earlier and showed unrelated pre-existing harness/dependency failures outside these focused assertions; no production code was changed.
summary:
Addressed only the review's concrete test-scope gaps. Tests now exercise the real release-event helper rather than manually incrementing the epoch, verify duplicate release and DEMAND release semantics, and explicitly prove one release event cannot cause a second Ready Horizon issue on the next pass.
exact_diff:
- `3090-dev/test_prefetch_budget_split_unit.py`: add `speculative_release_epoch` to the controller fixture; add exact epoch assertions to roundtrip, duplicate, missing-reservation, and DEMAND reservation tests.
- `3090-dev/test_ready_horizon_unit.py`: extend epoch fixtures for release events; preserve strict zero-cursor assertions; convert the post-issue scheduler test to production reserve/release calls; add a production-helper unsampled ABA scheduler test with a no-new-release second-pass assertion.
test_output:
- `python3 -m py_compile ...test_ready_horizon_unit.py ...test_prefetch_budget_split_unit.py`: passed (no output).
- `git diff --check`: passed (no output).
- Focused unittest: `Ran 4 tests in 0.026s` / `OK`.
- Ready Horizon focused import: failed before test execution because local interpreter lacks `orjson`; this is an environment limitation and no package installation was performed.
followups:
- Run the two Ready Horizon scheduler tests in an existing dependency-complete environment containing `orjson`, `msgspec`, torch, pytest, and local sglang.
- Independent review should inspect the final test diff and rerun the dependency-backed tests.
open_issues:
- Full dependency-backed Ready Horizon scheduler test execution remains pending.
- Live 3060 runtime acceptance remains a downstream gate and was not run.
- No commit, remote operation, package installation, cleanup, reset, merge, rebase, push, deployment, or production-source change was performed.
