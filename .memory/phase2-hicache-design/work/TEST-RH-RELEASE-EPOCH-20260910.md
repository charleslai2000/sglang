status: blocked
artifacts:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST-RH-RELEASE-EPOCH-20260910.md
evidence:
  interpreter:
    command: "/usr/bin/python3 --version"
    output: "Python 3.12.3"
  environment_inspection:
    command: "find /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt -maxdepth 4 -type f ( -path '*/.venv/bin/python*' -o -path '*/venv/bin/python*' -o -path '*/bin/python*' ) -print"
    output: "no workspace-local interpreter/venv found"
    dependency_probe: "pytest MISSING (ModuleNotFoundError); torch MISSING (ModuleNotFoundError); sglang MISSING without PYTHONPATH; numpy OK 1.26.4"
  focused_test_targets:
    ready_horizon: "/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py"
    prefetch_budget: "/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py"
    matching_test_names: "RH spec-budget/release/ABA tests include test_spec_budget_cleared_only_by_budget_release, test_spec_budget_release_event_clears_unsampled_aba, test_spec_budget_park_uses_post_issue_cursor_and_wakes_on_release, test_spec_budget_park_wakes_after_unsampled_aba_release; prefetch release tests include reserve/release, double release, revoke, abort, finalize, hybrid-discard, detach"
  commands:
    - command: "PYTHONPATH=/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python:/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev /usr/bin/python3 /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py"
      exit_status: 1
      output: "ModuleNotFoundError: No module named 'orjson' (during sglang import)"
    - command: "PYTHONPATH=/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python:/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev /usr/bin/python3 /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py"
      exit_status: 1
      output: "Ran 24 tests in 0.170s; FAILED (errors=12, skipped=1). Dependency-light reservation tests passed, but issue-path tests errored because the local harness/source state lacks _t38c_request_contexts and scheduler wiring import failed with ModuleNotFoundError: No module named 'sglang.srt.managers.scheduler'."
    - command: "PYTHONPATH=/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python:/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev /usr/bin/python3 -m unittest -v test_prefetch_budget_split_unit.PrefetchReservationExactlyOnceTests.test_reserve_release_roundtrip test_prefetch_budget_split_unit.PrefetchReservationExactlyOnceTests.test_double_release_idempotent test_prefetch_budget_split_unit.PrefetchReservationExactlyOnceTests.test_release_without_reservation_noop test_prefetch_budget_split_unit.PrefetchReservationExactlyOnceTests.test_demand_reservation_does_not_touch_spec_counter test_prefetch_budget_split_unit.PrefetchReservationExactlyOnceTests.test_finalize_path_releases_speculative_reservation test_prefetch_budget_split_unit.PrefetchReservationExactlyOnceTests.test_hybrid_discard_path_releases_speculative_reservation"
      exit_status: 0
      output: "Ran 6 tests in 0.023s; OK"
    - command: "PYTHONPYCACHEPREFIX=/tmp/sglang-rh-pycache /usr/bin/python3 -m py_compile /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_budget_split_unit.py /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/cache_controller.py /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler_components/ready_horizon.py /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py"
      exit_status: 0
      output: "(no output)"
    - command: "git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt diff --check"
      exit_status: 0
      output: "(no output)"
summary:
executed: 2 focused unit files attempted; 6 dependency-light prefetch release tests; bounded py_compile; git diff --check
passed: 6 focused prefetch reservation tests; py_compile; diff --check
failed: ready_horizon_unit.py could not import due missing orjson; complete prefetch file ran 24 tests with 12 errors and 1 skip
skipped: 1 in complete prefetch file (detach path: real StorageAttachment requires torch)
not_executed: required RH spec_budget/release/ABA tests; complete dependency-valid prefetch issue-path verification; no package installation or environment creation attempted
followups:
  - Provide an already dependency-complete interpreter/environment containing orjson and the expected sglang test harness, then rerun the exact focused targets.
open_issues:
  - No dependency-complete local environment was available; no product or test files were modified by this invocation.
