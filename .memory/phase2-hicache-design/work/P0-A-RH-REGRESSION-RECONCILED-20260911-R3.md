status: done

artifacts:
- This report: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/P0-A-RH-REGRESSION-RECONCILED-20260911-R3.md`
- Remote checkout used: `/root/sglang-3060-12g-hicache`
- No source, test, Git, gate, storage, server, or live-trace files were modified.

evidence:
- Authorized endpoint: `root@i-1.gpushare.com:27460`, key `/home/dev-codex/.ssh/sglang_3060_ed25519`.
- Remote identity probe exited `0`: hostname `I2aff9805ac001019d1`; GPU `NVIDIA GeForce RTX 3060`, `12288 MiB`, compute capability `8.6`; interpreter Python `3.11.11`; pytest `9.1.1`.
- The required six test-file hashes and four observed modified product-file hashes were checked locally and remotely before execution. All ten matched exactly:
  - tests: `4565319de153ea31f4e5c14d628d9a33203b34687e1383a4040d59734fdbc540`, `6acc94fa1b99174dcd954520a4f1217d58e948c7df6eb9dc7a9184fdc428ebcd`, `8f66e2cad45dbd5978cc721f6017ead10df89255a4d8272dda0d320064af537f`, `e2887aecc92c0689c21a47e2bde587e10447212a950e9d381fdb37d14c9e52a1`, `9d9e684c7af5096b690c0b2cc71f7410d44e2ada4e387a51cbd70681aaa082af`, `7dfd47a4219e0aee7cae322386dcba89a554d636cd8c361130d8985a45230799`.
  - product: `a41e623a2d6e462720d6584af992da290ba54e0cb3766df794117b87678b656f`, `18c39a18aa7f8c672ce5a2373f9bcdd68058933ae8c2ec16a6b14e0b47488a0a`, `954161ce4d32ef2d376a735ccc4315b4300e1874792e4dd11ef467dfc705aeda`, `35fae989ddfca0d457009f810e16d0e8a56f05416a5bfb1ec3a99e9a9937ffe4`.
- Every test command used `PYTHONPATH=/root/sglang-3060-12g-hicache/python:/root/sglang-3060-12g-hicache/test` and `/root/sglang-env-3060-4b/bin/python -m pytest -q`.
- Exact executed commands and outcomes:
  1. `3090-dev/test_ready_horizon_unit.py -k "spec_budget_cleared_only_by_budget_release or spec_budget_release_event_clears_unsampled_aba or spec_budget_park_uses_post_issue_cursor_and_wakes_on_release or spec_budget_park_wakes_after_unsampled_aba_release or physical_only_limiter_does_not_create_spec_budget_park or release_counter_monotonic_survives_reconsumption or active_prefetch_claim_blocks_duplicate_and_classifies_retry or no_event_epoch_no_refill or causal_epoch_change_triggers_new_refill or miss_recorded_and_held_across_ordinary_changes or anchor_version_advance_clears_and_reprobes_once or unrelated_chain_global_bump_never_clears_no_l3 or after_reprobe_miss_reparks_at_new_cursor"`; exit `1`; `8 passed, 5 failed, 61 deselected, 2 warnings`.
  2. `3090-dev/test_prefetch_budget_split_unit.py -k "reserve_release_roundtrip or double_release_idempotent or release_without_reservation_noop or demand_reservation_does_not_touch_spec_counter or revoke_path_releases_speculative_reservation or abort_path_releases_speculative_reservation or finalize_path_releases_speculative_reservation or hybrid_discard_path_releases_speculative_reservation or detach_path_releases_speculative_reservation"`; exit `1`; `6 passed, 3 failed, 15 deselected`.
  3. `3090-dev/test_ready_horizon_partition.py`; exit `0`; `18 passed, 2 warnings`.
  4. `3090-dev/test_hicache_restore_scheduler_feed.py`; exit `1`; `43 passed, 3 failed, 2 warnings`.
  5. `3090-dev/test_prefetch_gate_skip_regression.py`; exit `0`; `2 passed`.
  6. `3090-dev/test_rh_contract_dependency_free.py`; exit `0`; `19 passed`.
  7. `3090-dev/test_ready_horizon_unit.py`; exit `1`; `68 passed, 6 failed, 2 warnings`.
- Material failure output/classification:
  - `test_ready_horizon_unit.py`: one enum assertion received `PrefetchIssueResult(status=SKIPPED_ACTIVE, ...)` instead of the enum member; four deterministic-miss fixture calls supplied a `charge` lambda that rejects the current `origin` keyword; one logging assertion expected the old `ready_stage.v2` token while implementation emitted `evt=ready_stage schema=rh_stage.v2`. Classified source/API fixture or contract mismatch, not environment.
  - `test_prefetch_budget_split_unit.py`: three issue-path tests raised `AttributeError: UnifiedRadixCache has no attribute _t38c_node_context_index` from `_t38c_trace_context_for_node`; classified environment/fixture initialization mismatch. No test code or product code was changed to bypass it.
  - `test_hicache_restore_scheduler_feed.py`: three failures: fixture lambda rejected `origin`; a host allocation capacity fixture returned `True` where it expected `False`; and a fixture omitted `pop_host_alloc_failure`; classified source/API fixture mismatch.
- No server was launched and no live RH-OFF/RH-ON trace was run.

summary:
executed: source/hash gate plus 7 authorized remote pytest commands covering focused RH, budget split, partition, restore-feed, prefetch-gate, dependency-free contract, and full `test_ready_horizon_unit.py`
passed: 164 test cases passed across commands; 3 commands fully passed
failed: 17 test cases failed across commands; 4 commands exited 1
skipped: 76 deselected by focused `-k` filters; pytest-reported skips were not reported by these runs
not_executed: server execution, live RH-OFF/RH-ON trace, any P0-B/P0-C/P1 or production verification

followups:
- P0-A RH regression is dependency-complete and source-reconciled, but not fully passing: preserve the failure classifications above for the owning coder/tester.
- Reconcile the affected test doubles/contracts and initialize the durable-trace node-context fixture before any rerun.
- This report makes no claim about P0-B, P0-C, P1, production acceptance, or final quality acceptance.

open_issues:
- Current P0-A result is `NOT_VERIFIED` because 17 authorized regression cases failed.
- The earlier reconcile discrepancy remains recorded: the dispatch referenced five modified product files, while four observed product files were available and verified.
