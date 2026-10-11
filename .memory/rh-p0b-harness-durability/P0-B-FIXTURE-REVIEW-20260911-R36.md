status: done

artifacts:
- Reviewed artifact set:
  - `test/registered/unit/managers/test_hicache_host_allocability.py`
  - `3090-dev/test_drain_reentry.py`
  - `3090-dev/test_storage_regression.py`
- Input reports:
  - `.memory/phase2-hicache-design/work/P0-B-FAILURE-TRIAGE-20260911-R33.md`
  - `.memory/phase2-hicache-design/work/P0-B-FIXTURES-20260911-R35.md`
- This report: `.memory/phase2-hicache-design/work/P0-B-FIXTURE-REVIEW-20260911-R36.md`

evidence:
- Repository guidance read: `/home/dev-codex/AGENTS.md`. No unauthorized auditing,
  tracing, or instrumentation was introduced or requested by this review.
- Review was read-only for the three fixture files and the R33/R35 reports. No
  remote access and no product-file edits were performed.
- `git diff --stat -- <three files>` reports exactly 6 insertions and 0 deletions:
  2 in `3090-dev/test_drain_reentry.py`, 3 in
  `3090-dev/test_storage_regression.py`, and 1 in the registered HOST_ALLOC
  fixture. `git diff --name-only -- <three files>` contains only those three
  paths.
- `git diff --check -- <three files>` passed with no whitespace errors.
- Independent syntax verification passed:
  `python3 -m py_compile test/registered/unit/managers/test_hicache_host_allocability.py
  3090-dev/test_drain_reentry.py 3090-dev/test_storage_regression.py`.
- The six changes are additive object-new/test-double state initialization only:
  `hicache_restore_state_ts`, `speculative_release_epoch`, `components`,
  `_t38c_residency_lock`, and `_host_allocability_telemetry_seq`. They match the
  missing fixture/API-shape gaps identified in R33 and the R35 report.
- The FIFO assertion at `test_hicache_host_allocability.py:111` remains
  unchanged. No production arbiter or other product file appears in the scoped
  diff. This preserves the required FIFO assertion rather than masking the open
  rotate-and-choose contract question.
- R35 reports `test_drain_reentry.py` as 31 passed and
  `test_storage_regression.py` as 126 passed / 21 skipped (torch-backed
  real-tree cases). Those results were not independently rerun here because the
  local environment has no `pytest` module (`python3 -m pytest ...` fails with
  `No module named pytest`). The registered HOST_ALLOC suite is therefore still
  dependency-blocked locally; R35 records the prior `orjson` blocker.

summary:
- verdict: APPROVE
- The R35 patch is limited to the authorized test-only fixture repairs, is
  syntactically valid, passes scoped diff hygiene, and does not alter the FIFO
  assertion or production behavior.
- A focused dependency-complete rerun may proceed, subject to its separately
  authorized execution scope and environment gates.
- This approval is only a fixture-review disposition. It does not verify the
  HOST_ALLOC liveness hard gate; P0-B remains NOT_VERIFIED.

followups:
- Run the registered HOST_ALLOC suite and any authorized related focused suites
  on the dependency-complete 3060 environment.
- Keep the FIFO assertion unchanged unless a separate evidence-backed contract
  decision authorizes changing it; do not change the production arbiter as part
  of the rerun.
- Continue requiring correlated `not allocable -> park -> real allocability
  change -> wake -> successful restore` evidence before P0-B closure.

open_issues:
- Local absence of `pytest` (and the R35-recorded `orjson` dependency gap)
  prevents a complete local focused-suite rerun.
- FIFO rotate-and-choose semantics remain an explicit contract question, not a
  defect established by this fixture review.
- No complete correlated live HOST_ALLOC-to-READY chain is established by this
  review.
