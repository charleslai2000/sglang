status: done
artifacts:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/P0-A-RH-REGRESSION-FIXED-20260911.md
  - remote reversible backups: /root/sglang-3060-12g-hicache/.p0a-backup-20260911/3090-dev/{test_ready_horizon_unit.py,test_ready_horizon_partition.py,test_prefetch_budget_split_unit.py}
evidence:
  dispatch:
    task_id: P0-A-RH-REGRESSION-FIXED-20260911
    invocation: test-runner-20260911-06
    remote: root@i-1.gpushare.com:27460
    checkout: /root/sglang-3060-12g-hicache
    interpreter: /root/sglang-env-3060-4b/bin/python
    live_server_or_trace: not launched; RH OFF/ON trace not run
  synchronization:
    command: >-
      ssh ... 'mkdir -p checkout/.p0a-backup-20260911/3090-dev; cp -a the three
      target files into that backup'; scp the three local files to checkout/3090-dev/
    initial_attempt: exit 1 because backup subdirectory was not created; no target file was overwritten by that failed attempt
    successful_sync_exit: 0
    sha256_local_and_remote_after_sync:
      3090-dev/test_ready_horizon_unit.py: bd87b5b1165ae2e21d3c652f908af37b18ce3714fb6ff1d30b09221362f83e64
      3090-dev/test_ready_horizon_partition.py: 6acc94fa1b99174dcd954520a4f1217d58e948c7df6eb9dc7a9184fdc428ebcd
      3090-dev/test_prefetch_budget_split_unit.py: 59da7cb4d706585e41cd5d9d81849601f8b91bb1f76135f1a635a0ba8eeb6ee0
    verification: all three local/remote SHA256 values matched
  commands:
    focused_rh: >-
      cd /root/sglang-3060-12g-hicache && PYTHONPATH=/root/sglang-3060-12g-hicache/python:/root/sglang-3060-12g-hicache/3090-dev
      /root/sglang-env-3060-4b/bin/python -m pytest -q 3090-dev/test_ready_horizon_unit.py -k
      "spec_budget_cleared_only_by_budget_release or spec_budget_release_event_clears_unsampled_aba or
      spec_budget_park_uses_post_issue_cursor_and_wakes_on_release or spec_budget_park_wakes_after_unsampled_aba_release or
      physical_only_limiter_does_not_create_spec_budget_park or release_counter_monotonic_survives_reconsumption or
      active_prefetch_claim_blocks_duplicate_and_classifies_retry or no_event_epoch_no_refill or
      causal_epoch_change_triggers_new_refill or miss_recorded_and_held_across_ordinary_changes or
      anchor_version_advance_clears_and_reprobes_once or unrelated_chain_global_bump_never_clears_no_l3 or
      after_reprobe_miss_reparks_at_new_cursor"
      exit: 1; result: 5 failed, 50 deselected, 2 warnings
    budget_split_focused: >-
      same PYTHONPATH/interpreter; pytest -q 3090-dev/test_prefetch_budget_split_unit.py -k
      "reserve_release_roundtrip or double_release_idempotent or release_without_reservation_noop or
      demand_reservation_does_not_touch_spec_counter or revoke_path_releases_speculative_reservation or
      abort_path_releases_speculative_reservation or finalize_path_releases_speculative_reservation or
      hybrid_discard_path_releases_speculative_reservation or detach_path_releases_speculative_reservation"
      exit: 1; result: 2 passed, 7 failed, 15 deselected, 2 warnings
    partition: same PYTHONPATH/interpreter; pytest -q 3090-dev/test_ready_horizon_partition.py
      exit: 0; result: 18 passed, 2 warnings
    restore_feed: same PYTHONPATH/interpreter; pytest -q 3090-dev/test_hicache_restore_scheduler_feed.py
      exit: 1; result: 43 passed, 3 failed, 2 warnings
    prefetch_gate: same PYTHONPATH/interpreter; pytest -q 3090-dev/test_prefetch_gate_skip_regression.py
      exit: 0; result: 2 passed
    dependency_free_contract: same PYTHONPATH/interpreter; pytest -q 3090-dev/test_rh_contract_dependency_free.py
      exit: 0; result: 19 passed
    full_ready_horizon_unit: same PYTHONPATH/interpreter; pytest -q 3090-dev/test_ready_horizon_unit.py
      exit: 1; result: 16 passed, 39 failed, 2 warnings
  failure_classification:
    environment: no environment blocker; remote Python/pytest and imports executed
    api_fixture_mismatch:
      - CausalEpochs fixture calls omit required host_release (multiple RH unit errors)
      - scheduler test doubles reject current _prefetch_kvcache origin keyword (RH/restore-feed errors)
      - restore-feed fixture lacks pop_host_alloc_failure
      - budget fixture controller lacks speculative_release_epoch
      - budget harness reaches durable-trace helper without initialized _t38c_node_context_index
    current_regression_or_behavior_mismatch:
      - RH pass tests expected issued r1 but observed no issue (3 focused/full cases)
      - restore-feed capacity-span test expected false but observed true
      - full unit ready-stage logging test observed match_prepare_failed/no_restore_potential
    material_failure_output: preserved in command output from the six remote pytest invocations; no test process was started with server/live workload
summary:
  executed: synchronized and hash-verified three test files; focused RH list; budget split focused list; partition; restore-feed; prefetch-gate; dependency-free contract; full 3090-dev/test_ready_horizon_unit.py
  passed: 148 tests (focused RH 0, budget focused 2, partition 18, restore-feed 43, prefetch-gate 2, dependency-free 19, full unit 16); counts overlap between focused and full-unit runs
  failed: 54 reported test outcomes (focused RH 5, budget focused 7, partition 0, restore-feed 3, prefetch-gate 0, dependency-free 0, full unit 39); counts overlap between focused and full-unit runs
  skipped: 0 reported skips; deselected: focused RH 50, budget focused 15
  not_executed: no server, no live RH OFF/ON trace, and no P0-B/P0-C/P1/P1 production verification
followups:
  - P0-A is not a green regression gate: resolve the observed fixture/API mismatches and rerun the exact same suite.
  - Preserve the remote backup until reconciliation is complete; no product code, storage, gate, or production state was changed by this invocation.
open_issues:
  - P0-A acceptance remains NOT_VERIFIED because focused RH and full unit runs failed.
  - Failures span both stale fixture/API contracts and observed RH behavior; this report does not choose a root-cause fix.
  - No claims are made for P0-B, P0-C, P1, production, or live RH behavior.
