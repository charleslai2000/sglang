status: done

artifacts:
- Reviewed target diff: `3090-dev/test_prefetch_budget_split_unit.py`
- Reviewed triage: `.memory/phase2-hicache-design/work/P0-A-RESIDENCY-TRIAGE-20260911-R20.md`
- Reviewed correction report: `.memory/phase2-hicache-design/work/P0-A-RESIDENCY-FIX-20260911-R21.md`
- This report: `.memory/phase2-hicache-design/work/P0-A-RESIDENCY-REVIEW-20260911-R22.md`

evidence:
- The reviewed correction is present at `3090-dev/test_prefetch_budget_split_unit.py:177`, immediately after `cache._t38c_residency_lock = threading.RLock()`: `cache._t38c_residency_queue_blocked = set()`.
- The target fixture is used by the budget tests, including all three R19 failures (`_make_budget_cache()` is called throughout the test classes; R20 identifies the three failing cases and their common drain path).
- R20 establishes the required invariant independently: constructor-created residency state is a per-cache mutable empty `set`; the failing fixture bypasses `UnifiedRadixCache.__init__`; and the production drain hook performs `difference_update` on that set. The correction mirrors the constructor and sibling fixture rather than weakening production behavior.
- The current target-file diff is whitespace-clean: `git diff --check -- 3090-dev/test_prefetch_budget_split_unit.py` passed. The R21 report records `py_compile` success and the same diff-check result.
- R21's targeted local run reached 19 passed and 1 skipped before four unrelated scheduler-fixture import errors (`ModuleNotFoundError: No module named 'sglang.srt.managers.scheduler'`). This is not evidence against the one-line residency initialization; it means local execution cannot authorize the remote result.
- R19's remote evidence records the exact authorized 3060 target, Python environment, command prefix, and that the full budget suite failed only at the missing attribute in three tests while the other seven commands passed. R20 correctly requires a same-environment full budget-suite rerun before P0-A can be verified.
- Independent worktree inspection shows unrelated dirty product/test files outside this correction. They are not included in this review's rerun authorization; the remote operator must transfer/select only the reviewed budget fixture correction and preserve the existing remote backup/boundary.

scope:
- Read-only review of the budget-test diff and the R20/R21 residency reports. No product files, remote systems, or reviewed artifacts were modified. This report is the sole new coordination artifact.

summary:
- Verdict: **APPROVE**.
- The one-line fixture correction is minimal, type-correct, localized to the constructor-bypassing budget harness, and directly addresses the R19 exception without changing production code or relaxing assertions.
- Final remote P0-A rerun is authorized, subject to the exact controls below. This approval does not claim P0-A verified or authorize any production change.

rerun_authorization:
- Authorized target: the same 3060 remote checkout and environment recorded by R19 (`root@i-1.gpushare.com:27460`, `/root/sglang-3060-12g-hicache`, `/root/sglang-env-3060-4b/bin/python`).
- Transfer/select only the reviewed `3090-dev/test_prefetch_budget_split_unit.py` correction, or otherwise prove the remote file matches the reviewed artifact before execution. Do not transfer the unrelated local product/test changes.
- Run the full `test_prefetch_budget_split_unit.py` suite with the exact R19 `PYTHONPATH` and pytest command prefix, not only the focused selector. Preserve complete output and exit status.
- Retain the previously passing R19 command set/regression boundary as required by the P0-A procedure. A final P0-A VERIFIED result requires the full budget suite and all required companion commands to pass; any failure leaves P0-A unverified.
- If the missing-attribute error persists, stop verification and report failure; do not alter production code or broaden the fixture patch under this authorization.

followups:
- Execute the authorized remote rerun under the R19 environment and compare the full budget result with the three prior failure IDs.
- Record remote file identity/checksum and complete command transcript in the next execution report.

open_issues:
- Local execution remains blocked by the torch-free/missing-scheduler harness import, so this review cannot substitute for remote verification.
- The broader local worktree is dirty beyond the reviewed budget fixture. Provenance isolation must be enforced by the rerun operator; this review does not approve or review those unrelated changes.
- P0-A remains **not verified** until the authorized remote rerun completes successfully.
