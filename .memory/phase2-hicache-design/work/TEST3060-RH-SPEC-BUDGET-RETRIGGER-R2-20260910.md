# TEST3060-RH-SPEC-BUDGET-RETRIGGER-R2

status: done
task_id: TASK-3060-RH-SPEC-BUDGET-RETRIGGER
invocation_id: ROOT-FALLBACK-TEST-20260910
role: test-runner fallback
workspace: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
remote: `root@i-1.gpushare.com:27460`, `/root/sglang-3060-12g-hicache`
service impact: no restart; live service remained available during testing

## Focused verification

The two changed files were copied to the remote checkout after saving the previous
remote copies under `/hy-tmp/scheduler.before-rh-spec-budget.py` and
`/hy-tmp/test_ready_horizon.before-rh-spec-budget.py`.

Command:

```bash
PYTHONPATH=python /root/sglang-env-3060-4b/bin/python -m pytest -q \
  3090-dev/test_ready_horizon_unit.py \
  -k "spec_budget_park_uses_post_issue_cursor_and_wakes_on_release or physical_only_limiter_does_not_create_spec_budget_park"
```

Result: **2 passed, 70 deselected, 2 warnings, exit 0**.

The two new tests exercised both the post-issue cursor wake and the physical-only
limiter separation.

## Full file sanity

Command:

```bash
PYTHONPATH=python /root/sglang-env-3060-4b/bin/python -m pytest -q 3090-dev/test_ready_horizon_unit.py
```

Result: **66 passed, 6 failed, 2 warnings**.

The six failures are existing fixture/API or telemetry-token mismatches:

- legacy enum identity vs typed `PrefetchIssueResult`;
- legacy `evt=ready_stage.v2` token vs current `evt=ready_stage schema=rh_stage.v2`;
- four deterministic miss fixtures whose `charge()` does not accept the current
  required `origin=` keyword.

They are outside the two new tests and were present in the pre-fix test contract;
they remain open and prevent claiming the broad file suite green.

## Environment

The remote venv has `orjson=3.12.0`, `torch=2.6.0+cu124`, and `pytest=9.1.1`.
