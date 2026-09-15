status: done

artifacts:
- `test/registered/unit/managers/test_hicache_host_allocability.py`
- `3090-dev/test_drain_reentry.py`
- This report: `.memory/phase2-hicache-design/work/P0-B-FIXTURE-REPAIR-20260911-R47.md`

evidence:
- Replaced expired `hicache_restore_state_ts=0.0` with
  `time.perf_counter() - 1.0`, preserving the 60-second timeout semantics.
- Added production-equivalent empty `_t38c_node_context_index = {}` to drain
  fixture.
- FIFO assertions and production eligibility/generation logic preserved.
- AST/static checks found exactly 9 HOST_ALLOC tests and 31 drain tests.
- `py_compile`, `compileall`, and scoped `git diff --check` passed.
- Drain tests passed 31/31 via unittest discover.
- HOST_ALLOC tests were locally blocked by missing pytest/orjson.
- No dependencies installed; no remote or product changes.

summary:
- Only approved two-file fixture repairs applied.
- P0-B remains NOT_VERIFIED.

followups:
- Run exact 9 HOST_ALLOC tests in dependency-complete 3060 environment.
- Independently review diff and focused output.
- Complete separately authorized correlated HOST_ALLOC-to-READY verification.

open_issues:
- Local runtime tools unavailable.
- FIFO contract and correlated live chain remain open.
