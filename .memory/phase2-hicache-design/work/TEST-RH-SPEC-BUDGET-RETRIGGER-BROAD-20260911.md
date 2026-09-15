# TEST-RH-SPEC-BUDGET-RETRIGGER-BROAD-20260911

status: done
task_id: TEST-RH-SPEC-BUDGET-RETRIGGER-BROAD-20260911
invocation_id: test-runner-20260911-01
role: test-runner
workspace: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
scope: 3090-dev/test_ready_horizon_unit.py

## artifacts

- `3090-dev/test_ready_horizon_unit.py` inspected; AST contains 74 `test_*`
  methods.
- `test/pytest.ini` inspected; it only sets `asyncio_mode = auto`.
- This report is the only artifact written by this invocation.
- No product code, test code, git state, remote host, or live runtime was
  modified or invoked.

## evidence

Environment inspection:

```text
python -V
=> /bin/bash: python: command not found

python3 -V
=> Python 3.12.3

python3 -m pytest --version
=> /usr/bin/python3: No module named pytest
```

Attempt 1, exact command:

```bash
PYTHONPATH=python python3 -m pytest -q 3090-dev/test_ready_horizon_unit.py
```

Exit code: `1`.

Material error:

```text
/usr/bin/python3: No module named pytest
```

Attempt 2, exact command (stdlib fallback, not a substituted acceptance
method; used only to determine whether the file could collect):

```bash
PYTHONPATH=python python3 -m unittest 3090-dev/test_ready_horizon_unit.py
```

Exit code: `1`.

Material error:

```text
ModuleNotFoundError: No module named 'orjson'
```

The import chain fails while importing `sglang.srt.utils.common`, before any
test method executes. Therefore no broad test result, pass count, or current
worktree failure traceback was produced locally. No live 3060/3090 acceptance
was called.

The six failures requested for classification are documented by the prior
dependency-complete run recorded in
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-RH-SPEC-BUDGET-RETRIGGER-R2-20260910.md`:

1. One legacy enum-identity assertion mismatches the typed
   `PrefetchIssueResult` API.
2. One telemetry-token assertion expects legacy `evt=ready_stage.v2`, while
   the current output uses `evt=ready_stage schema=rh_stage.v2`.
3. Four deterministic-miss fixture failures occur because the fixture's
   `charge()` does not accept the current required `origin=` keyword.

These are six prior-run failures (one + one + four), not six failures freshly
reproduced in this local environment. The current worktree broad file run is
unavailable because pytest and the runtime dependency `orjson` are absent.

## summary

executed: 2 collection/execution attempts; 1 AST inventory; no test method execution
passed: 0 reported by the attempted broad test command (collection failed)
failed: 0 current test cases; 2 commands failed before collection; prior dependency-complete run had 6 failures (1 enum/API, 1 telemetry token, 4 fixture `origin=`)
skipped: 0
not_executed: full Ready Horizon unit suite in a dependency-complete environment; live 3060/3090 runtime acceptance

## followups

- Provide or activate the project dependency-complete environment containing
  pytest and `orjson`, then rerun exactly:
  `PYTHONPATH=python python3 -m pytest -q 3090-dev/test_ready_horizon_unit.py`.
- Preserve the six-failure classification above only as prior-run context;
  replace it with fresh tracebacks once the current worktree can collect.

## open_issues

- Broad current-worktree verification is not green or complete: local
  collection is blocked by missing tooling/dependencies.
- The six listed mismatches were not independently reproduced here.
