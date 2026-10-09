status: blocked
verdict: NOT_VERIFIED
artifacts:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST-P0-A-RH-FOCUSED-REGRESSION-20260910.md
  - /tmp/p0-a-ready-local.stdout (empty stdout from the only local test invocation)
  - /tmp/p0-a-ready-local.stderr (complete stderr from the only local test invocation)
evidence:
  dispatch_scope:
    task_id: P0-A-RH-FOCUSED-REGRESSION-20260910
    product_workspace: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
    approved_remote_checkout: /root/sglang-3060-12g-hicache
    approved_remote_interpreter: /root/sglang-env-3060-4b/bin/python
    report_inputs_read:
      - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/plan.md
      - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/context.md
      - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/REVIEW-RH-FINAL-TEST-GATE-20260910.md
      - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/REVIEW-RH-RELEASE-EPOCH-FINAL-20260910.md
      - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/REVIEW-RH-RELEASE-FINAL-GATE-20260910.md
      - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST-RH-RELEASE-EPOCH-20260910.md
      - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER-RH-RELEASE-EPOCH-FIX-20260910.md
      - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md
      - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/HANDOFF-2026-09-10-RH-SPEC-BUDGET-SESSION2.md
  selected_cases_from_designated_reports:
    ready_horizon:
      - test_spec_budget_cleared_only_by_budget_release
      - test_spec_budget_release_event_clears_unsampled_aba
      - test_spec_budget_park_uses_post_issue_cursor_and_wakes_on_release
      - test_spec_budget_park_wakes_after_unsampled_aba_release
      - test_physical_only_limiter_does_not_create_spec_budget_park
      - test_release_counter_monotonic_survives_reconsumption
      - test_active_prefetch_claim_blocks_duplicate_and_classifies_retry
      - test_no_event_epoch_no_refill
      - test_causal_epoch_change_triggers_new_refill
      - test_miss_recorded_and_held_across_ordinary_changes
      - test_anchor_version_advance_clears_and_reprobes_once
      - test_unrelated_chain_global_bump_never_clears_no_l3
      - test_after_reprobe_miss_reparks_at_new_cursor
    prefetch_budget_split:
      - test_reserve_release_roundtrip
      - test_double_release_idempotent
      - test_release_without_reservation_noop
      - test_demand_reservation_does_not_touch_spec_counter
      - test_revoke_path_releases_speculative_reservation
      - test_abort_path_releases_speculative_reservation
      - test_finalize_path_releases_speculative_reservation
      - test_hybrid_discard_path_releases_speculative_reservation
      - test_detach_path_releases_speculative_reservation
  local_environment:
    interpreter_probe_command: |
      /usr/bin/python3 - <<'PY'
      import sys
      print("executable", sys.executable)
      print("version", sys.version)
      for n in ("pytest","orjson","msgspec","torch","numpy","sglang"):
       try:
        m=__import__(n)
        print(n, getattr(m,"__version__","unknown"))
       except Exception as e:
        print(n, "ERROR", type(e).__name__, str(e))
      PY
    interpreter_probe_exit_status: 0
    interpreter_probe_stdout: |
      executable /usr/bin/python3
      version 3.12.3 (main, Jul 15 2026, 23:46:41) [GCC 13.3.0]
      pytest ERROR ModuleNotFoundError No module named 'pytest'
      orjson ERROR ModuleNotFoundError No module named 'orjson'
      msgspec ERROR ModuleNotFoundError No module named 'msgspec'
      torch ERROR ModuleNotFoundError No module named 'torch'
      numpy 1.26.4
      sglang ERROR ModuleNotFoundError No module named 'sglang'
    interpreter_probe_stderr: "(empty)"
    dependency_status: incomplete; no package installation or venv creation attempted
  remote_environment:
    probe_command: |
      ssh -o BatchMode=yes -o ConnectTimeout=10 -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com 'test -x /root/sglang-env-3060-4b/bin/python && /root/sglang-env-3060-4b/bin/python --version && /root/sglang-env-3060-4b/bin/python -m pytest --version'
    probe_exit_status: 0
    probe_stdout: |
      Python 3.11.11
      pytest 9.1.1
    probe_stderr: "(empty)"
    dependency_detail_command: |
      ssh -o BatchMode=yes -o ConnectTimeout=10 -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com 'cd /root/sglang-3060-12g-hicache; /root/sglang-env-3060-4b/bin/python - <<"PY" ...'
    dependency_detail_exit_status: 0
    dependency_detail_stdout: |
      PWD=/root/sglang-3060-12g-hicache
      executable /root/sglang-env-3060-4b/bin/python
      version 3.11.11 (main, Dec  4 2024, 08:55:07) [GCC 11.4.0]
      pytest 9.1.1
      orjson 3.12.0
      msgspec 0.21.1
      torch 2.6.0+cu124
      numpy 2.2.4
    dependency_detail_stderr: "(empty)"
    conclusion: remote dependency environment is usable in isolation, but its checkout content is not the current local target content.
  local_product_revision:
    command: git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt rev-parse HEAD
    output: 4f41f5bab562b99562f30c67540eb05344d13637
    local_status_observation: six target files are modified in the local working tree; .memory/, review/gates/, and storage/ are unrelated untracked material and were not touched.
  local_target_file_sha256:
    3090-dev/test_ready_horizon_unit.py: 4565319de153ea31f4e5c14d628d9a33203b34687e1383a4040d59734fdbc540
    3090-dev/test_prefetch_budget_split_unit.py: 8f66e2cad45dbd5978cc721f6017ead10df89255a4d8272dda0d320064af537f
    python/sglang/srt/managers/cache_controller.py: a41e623a2d6e462720d6584af992da290ba54e0cb3766df794117b87678b656f
    python/sglang/srt/managers/scheduler.py: 18c39a18aa7f8c672ce5a2373f9bcdd68058933ae8c2ec16a6b14e0b47488a0a
    python/sglang/srt/managers/scheduler_components/ready_horizon.py: 954161ce4d32ef2d376a735ccc4315b4300e1874792e4dd11ef467dfc705aeda
    python/sglang/srt/mem_cache/unified_radix_cache.py: 35fae989ddfca0d457009f810e16d0e8a56f05416a5bfb1ec3a99e9a9937ffe4
  remote_checkout_identity:
    checkout_path: /root/sglang-3060-12g-hicache
    git_revision_command: |
      ssh -o BatchMode=yes -o ConnectTimeout=10 -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com 'cd /root/sglang-3060-12g-hicache && printf "remote_revision_probe="; git rev-parse HEAD 2>&1; printf "remote_status_probe="; git status --short 2>&1'
    exit_status: 128
    stdout_and_stderr: |
      remote_revision_probe=fatal: not a git repository (or any of the parent directories): .git
      remote_status_probe=fatal: not a git repository (or any of the parent directories): .git
    remote_revision: UNKNOWN (checkout is not a Git repository)
  remote_target_file_sha256:
    command: |
      ssh -o BatchMode=yes -o ConnectTimeout=10 -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com 'cd /root/sglang-3060-12g-hicache && sha256sum 3090-dev/test_ready_horizon_unit.py 3090-dev/test_prefetch_budget_split_unit.py python/sglang/srt/managers/cache_controller.py python/sglang/srt/managers/scheduler.py python/sglang/srt/managers/scheduler_components/ready_horizon.py python/sglang/srt/mem_cache/unified_radix_cache.py'
    exit_status: 0
    output: |
      faa787d1b87e65a646235f3804cb6afea9a31dbc6e63d640ad9052cea5076db1  3090-dev/test_ready_horizon_unit.py
      59da7cb4d706585e41cd5d9d81849601f8b91bb1f76135f1a635a0ba8eeb6ee0  3090-dev/test_prefetch_budget_split_unit.py
      43b57f5a61340c00570eaeac5b7c8e5c0f6770783d999a9085c88ae3dd61079f  python/sglang/srt/managers/cache_controller.py
      e3a78d4856743c4842243a25307db84dec24a6f0303fb81c2fd2f0fa2f8f7d4e  python/sglang/srt/managers/scheduler.py
      5b8df78a2987108ecfc2ddddd4f6d506305f74ace8a84365197091d95113d34e  python/sglang/srt/managers/scheduler_components/ready_horizon.py
      9a5ac1214d686cc255114b523730f99db88eaa71f6f4388fd542e8f45ecad0b0  python/sglang/srt/mem_cache/unified_radix_cache.py
    per_file_comparison: all six remote SHA256 values differ from the corresponding local SHA256 values; no byte-identical target file exists between the two checkouts.
  source_drift_stop:
    exact_reason: >-
      STOP CONDITION: source/profile drift. The remote dependency-complete environment is
      available, but all six dispatch-designated target files in the remote checkout have
      SHA256 values different from the current local six files. The remote checkout has no
      Git metadata, so its revision cannot be independently reconciled. Running there would
      test a different source state and cannot verify the requested local product state.
    decision: blocked; NOT_VERIFIED
    actions_not_taken: no file synchronization, no remote checkout mutation, no dependency installation, no venv creation, no service start/restart/stop, no live workload, no cleanup, no commit, no push.
  local_test_invocation:
    command: |
      cd /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
      PYTHONPATH=/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python:/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev /usr/bin/python3 -m pytest -q 3090-dev/test_ready_horizon_unit.py -k 'spec_budget_cleared_only_by_budget_release or spec_budget_release_event_clears_unsampled_aba or spec_budget_park_uses_post_issue_cursor_and_wakes_on_release or spec_budget_park_wakes_after_unsampled_aba_release or physical_only_limiter_does_not_create_spec_budget_park or release_counter_monotonic_survives_reconsumption or no_event_epoch_no_refill or causal_epoch_change_triggers_new_refill or miss_recorded_and_held_across_ordinary_changes or anchor_version_advance_clears_and_reprobes_once or unrelated_chain_global_bump_never_clears_no_l3 or after_reprobe_miss_reparks_at_new_cursor'
    exit_status: 1
    stdout: "(empty)"
    stderr: "/usr/bin/python3: No module named pytest\n"
    result: no collection; no test case ran
  unexecuted_remote_test_commands:
    ready_horizon: |
      ssh -o BatchMode=yes -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com 'cd /root/sglang-3060-12g-hicache && PYTHONPATH=/root/sglang-3060-12g-hicache/python:/root/sglang-3060-12g-hicache/3090-dev /root/sglang-env-3060-4b/bin/python -m pytest -q 3090-dev/test_ready_horizon_unit.py -k "spec_budget_cleared_only_by_budget_release or spec_budget_release_event_clears_unsampled_aba or spec_budget_park_uses_post_issue_cursor_and_wakes_on_release or spec_budget_park_wakes_after_unsampled_aba_release or physical_only_limiter_does_not_create_spec_budget_park or release_counter_monotonic_survives_reconsumption or active_prefetch_claim_blocks_duplicate_and_classifies_retry or no_event_epoch_no_refill or causal_epoch_change_triggers_new_refill or miss_recorded_and_held_across_ordinary_changes or anchor_version_advance_clears_and_reprobes_once or unrelated_chain_global_bump_never_clears_no_l3 or after_reprobe_miss_reparks_at_new_cursor"'
      status: NOT EXECUTED due source drift
    prefetch_budget_split: |
      ssh -o BatchMode=yes -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com 'cd /root/sglang-3060-12g-hicache && PYTHONPATH=/root/sglang-3060-12g-hicache/python:/root/sglang-3060-12g-hicache/3090-dev /root/sglang-env-3060-4b/bin/python -m pytest -q 3090-dev/test_prefetch_budget_split_unit.py -k "reserve_release_roundtrip or double_release_idempotent or release_without_reservation_noop or demand_reservation_does_not_touch_spec_counter or revoke_path_releases_speculative_reservation or abort_path_releases_speculative_reservation or finalize_path_releases_speculative_reservation or hybrid_discard_path_releases_speculative_reservation or detach_path_releases_speculative_reservation"'
      status: NOT EXECUTED due source drift
    note: neither remote focused command was sent to the remote host; no remote test collection occurred.
  counts:
    local_attempt: pass=0 fail=0 error=0 skip=0; collection=0; exit=1 due missing pytest
    remote_attempt: pass=0 fail=0 error=0 skip=0; collection=0; command not executed
    aggregate_runtime_tests: pass=0 fail=0 error=0 skip=0; no runtime tests executed
summary:
  executed: environment/version probes; local SHA256 capture; remote SHA256 capture; remote Git metadata probe; one local pytest availability/test-start attempt that stopped before collection
  passed: 0 tests; remote dependency probes passed; source/hash probes completed
  failed: 0 tests; local pytest invocation exited 1 because pytest is absent; remote Git revision probe exited 128 because checkout is not a Git repository
  skipped: 0 tests
  not_executed: all requested Ready Horizon and prefetch focused runtime tests; remote focused pytest commands; no collection, import, fixture, or test body execution; no alternate interpreter or source synchronization attempted
followups:
  - Provide an already dependency-complete environment whose checkout is byte-identical to the current local six target files, or provide an authorized source/profile reconciliation.
  - After source identity is reconciled, rerun only the listed focused cases; do not infer PASS from prior reports or from the usable-but-drifted remote dependency environment.
open_issues:
  - P0-A acceptance remains blocked/NOT_VERIFIED.
  - Remote dependencies are usable, but remote source drift makes their environment invalid for verifying the current local target.
  - Local interpreter is dependency-incomplete (pytest/orjson/msgspec/torch/sglang unavailable).
  - Remote checkout has no Git metadata; exact remote revision is UNKNOWN.
  - No test result can be claimed for release epoch, SPEC_BUDGET, ABA, stale-negative, second-pass no-duplicate, or reservation cleanup invariants.
