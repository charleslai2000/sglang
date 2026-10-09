# TEST3060-RH-REALPATH-VERIFY-20260909

ENTRY: ACCEPT

task_id: T3060-RH-REALPATH-VERIFY-20260909
orchestration_epoch: 20260909-rh-ab55
role: tester
status: done
invocation_status: done
reviewed_revision: `9213ee01d90ba3925e7fe928e80cc41354ee4fff`

## Summary

Package-backed verification completed on the RTX3060 host using the existing
`/root/sglang-env-3060-4b` venv and an isolated checkout at
`/hy-tmp/sglang-test-9213`. The immutable archive and all relevant source/test
file hashes matched the requested commit.

The requested commit-specific acceptance evidence is green:

- RH contract: **16 passed**.
- Gate-skip regression: **2 passed**.
- Restore state suite: **92 passed**.
- Focused commit telemetry/no-COW/valid-ticket/fallback oracles: **7 passed**.
- Focused real Scheduler/Ready Horizon pass oracles: **13 passed**.
- Non-failing scheduler-feed oracles: **43 passed**.
- Ready Horizon partition suite: **18 passed**.

The two broader package-backed suites execute against the real component but are
not fully green because six existing test-fixture/expectation mismatches remain;
their exact failures are recorded below. No product implementation was edited.

## Artifacts

- Remote isolated checkout: `/hy-tmp/sglang-test-9213`
- Remote archive: `/hy-tmp/sglang-test-9213.tar`
- Remote archive SHA-256: `1b9fda7b0b266072a90e53e3afb7d854579baef3c8de61221a0c5aa69a881b0e`
- Preserved logs: [TEST3060-RH-REALPATH-VERIFY-20260909-logs](/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-RH-REALPATH-VERIFY-20260909-logs)

Log SHA-256 values:

| Log | SHA-256 |
| --- | --- |
| `focused_oracles.log` | `f83c3fab3f2301dc3709eb36d45cf85577f99416a25c8e80cf7b186112119e60` |
| `gate_skip_regression.log` | `261cf64cf594a8274f2c55f5bf1bb9bd40219b90ab5dd04ffcea250155379c31` |
| `hicache_restore.log` | `85ad146cf79c47ef05094df0b49c86bc5b689c0d88139b1a4cbee452c3c9340b` |
| `ready_horizon_unit.log` | `66c79934fe4d36b4a89c7b81b151633b9d4264e1dfce638b137bf015b2f77f0a` |
| `restore_scheduler_feed.log` | `171b9aae202d2d940d80b504c3ed7923e9a3a664c5786de7b85b0511fd380691` |
| `rh_contract_dependency_free.log` | `01cad83963a8a2225cc6a04083a40d4ead714ed872855537de45ae56858e4f35` |

## Environment evidence

Remote target: `root@i-1.gpushare.com:27460`, host
`I2aff9805ac001019d1`, timestamp `2026-09-09T19:54+08:00` onward.

Interpreter and package versions from `/root/sglang-env-3060-4b/bin/python`:

```text
Python 3.11.11
orjson 3.12.0
msgspec 0.21.1
torch 2.6.0
pytest 9.1.1
sglang 0.0.0.dev0
sglang-kernel 0.4.6.post1
transformers 5.12.1
numpy 2.2.4
```

The corrected package import probe resolved both Scheduler and Ready Horizon
code from the isolated checkout:

```text
scheduler_module /hy-tmp/sglang-test-9213/python/sglang/srt/managers/scheduler.py
scheduler_source /hy-tmp/sglang-test-9213/python/sglang/srt/managers/scheduler.py
ready_horizon_source /hy-tmp/sglang-test-9213/python/sglang/srt/managers/scheduler_components/ready_horizon.py
ready_policy_methods ['frontier', 'staging_candidates', 'epoch_event']
scheduler_methods ['_prepare_ready_horizon_match', '_prefetch_kvcache', '_emit_rh_decision', '_ready_horizon_pass']
```

The first probe incorrectly attempted to import a nonexistent `ReadyHorizon`
class; the actual implementation exposes `ReadyHorizonPolicy`. That probe was
discarded as a harness mistake and rerun correctly.

Relevant immutable-commit file hashes matched between local `git show` and the
remote extracted archive:

```text
4d90aa00e0c33929176f560180902df0e5507478022552fbd647c08087d80a63  3090-dev/test_ready_horizon_unit.py
e2887aecc92c0689c21a47e2bde587e10447212a950e9d381fdb37d14c9e52a1  3090-dev/test_hicache_restore_scheduler_feed.py
1ba95877f331457b796d2a1fb26a6c66800e23ea86b3eacf2a4796f962174b29  3090-dev/test_rh_contract_dependency_free.py
9d9e684c7af5096b690c0b2cc71f7410d44e2ada4e387a51cbd70681aaa082af  3090-dev/test_prefetch_gate_skip_regression.py
323af06dec1812206d6923446348a76de5795e73fc878681f6ddf8376b1b7568  3090-dev/test_hicache_restore.py
f6c3644a039df88ca2d9a47df1fac1fd7d0bf12f29538c7b87e3e5c810627bde  python/sglang/srt/managers/scheduler.py
5b8df78a2987108ecfc2ddddd4f6d506305f74ace8a84365197091d95113d34e  python/sglang/srt/managers/scheduler_components/ready_horizon.py
```

## Commands and results

All commands ran from `/hy-tmp/sglang-test-9213` with `PYTHONPATH=python` and
the remote venv interpreter. No HTTP requests, load generation, service start,
restart, or kill was performed.

Exact package-backed suite commands:

```text
PYTHONPATH=python /root/sglang-env-3060-4b/bin/python 3090-dev/test_ready_horizon_unit.py
PYTHONPATH=python /root/sglang-env-3060-4b/bin/python 3090-dev/test_hicache_restore_scheduler_feed.py
PYTHONPATH=python /root/sglang-env-3060-4b/bin/python 3090-dev/test_rh_contract_dependency_free.py
PYTHONPATH=python /root/sglang-env-3060-4b/bin/python 3090-dev/test_prefetch_gate_skip_regression.py
PYTHONPATH=python /root/sglang-env-3060-4b/bin/python 3090-dev/test_hicache_restore.py
```

Results:

| Suite | Result |
| --- | --- |
| `test_ready_horizon_unit.py` | **70 run; 2 failures, 4 errors; exit 1** |
| `test_hicache_restore_scheduler_feed.py` | **46 run; 1 failure, 2 errors; exit 1** |
| `test_rh_contract_dependency_free.py` | **16 run; OK; exit 0** |
| `test_prefetch_gate_skip_regression.py` | **2 run; OK; exit 0** |
| `test_hicache_restore.py` | **92 run; OK; exit 0** |

Focused pytest commands and results:

```text
PYTHONPATH=python /root/sglang-env-3060-4b/bin/python -m pytest -q 3090-dev/test_rh_contract_dependency_free.py -k "rh_preparation_is_one_shot_and_non_cow or real_impl_consumes_valid_ticket_without_issue_rematch or later_pass_preparation_joins_current_decision_and_null_session or real_impl_invalid_ticket_rematches_exactly_once or match_telemetry_classifies_buffer_device_fallback or ready_pass_joins_raw_frontier_req_to_policy_view or issue_join_uses_returned_attempt_and_event_order"
# 7 passed, 9 deselected in 0.61s

PYTHONPATH=python /root/sglang-env-3060-4b/bin/python -m pytest -q 3090-dev/test_ready_horizon_unit.py -k "pass_issues_candidates_via_prefetch_kvcache or no_event_epoch_no_refill or causal_epoch_change_triggers_new_refill or headroom_shortfall_never_evicts or no_headroom_park_wakes_on_release_epoch_not_level or release_counter_monotonic_survives_reconsumption or off_mode_is_a_noop or rh_on_enqueue_is_queue_first_and_rh_owned or rh_off_enqueue_preserves_eager_order_and_origin or ready_pool_log_on_change or off_mode_never_constructs_epoch_plumbing or issue_decision_precedes_stage_with_claimed_attempt_id or failed_issue_is_hold_and_never_false_issue"
# 13 passed, 57 deselected in 13.54s

PYTHONPATH=python /root/sglang-env-3060-4b/bin/python -m pytest -q 3090-dev/test_hicache_restore_scheduler_feed.py -k "not backup_pending_wake_reissues_as_demand_restore and not positive_alloc_failure_maps_to_host_capacity_wait and not host_alloc_wait_wakes_only_for_complete_requested_span"
# 43 passed, 3 deselected in 13.47s

PYTHONPATH=python /root/sglang-env-3060-4b/bin/python -m pytest -q 3090-dev/test_ready_horizon_partition.py
# 18 passed, 2 warnings in 13.62s
```

The focused commit-oracle selection directly exercised the real Scheduler
preparation/issue/decision paths and verified no-COW preparation, valid-ticket
consumption without rematch, invalid-ticket exactly-once rematch, buffer/device
fallback telemetry, current-pass decision joins, raw-frontier joins, and
returned-attempt event ordering.

## Failure evidence and classification

The two broad suites' failures are preserved in the copied logs. Observed
failures, without assigning hard causal ownership:

- `test_ready_horizon_unit.py`, four errors in
  `DeterministicMissParkTests`: each fixture-local `charge()` does not accept
  the current required `origin=` keyword passed by real `_ready_horizon_pass`.
  This is a test-harness signature mismatch.
- `test_ready_horizon_unit.py`,
  `test_active_prefetch_claim_blocks_duplicate_and_classifies_retry`: the test
  expects the legacy enum identity, while the real method returns the typed
  `PrefetchIssueResult(status=SKIPPED_ACTIVE, ...)` object.
  This is a test expectation/API-contract mismatch requiring owner review.
- `test_ready_horizon_unit.py`,
  `test_ready_stage_log_reports_issue_result`: the test searches for
  `evt=ready_stage.v2`; the real log is
  `evt=ready_stage schema=rh_stage.v2` and contains `result=issued`.
  This is a telemetry-token expectation mismatch.
- `test_hicache_restore_scheduler_feed.py`,
  `test_backup_pending_wake_reissues_as_demand_restore`: the fixture lambda
  does not accept the current `origin=` keyword.
  This is a test-harness signature mismatch.
- `test_hicache_restore_scheduler_feed.py`,
  `test_positive_alloc_failure_maps_to_host_capacity_wait`: the fixture's
  `tree_cache` lacks `pop_host_alloc_failure`, which the real terminal path
  reads for an allocation-failure event. This is an incomplete fixture.
- `test_hicache_restore_scheduler_feed.py`,
  `test_host_alloc_wait_wakes_only_for_complete_requested_span`: the test
  expects `False` at available size `54976`; the real helper returned `True`
  for that fixture. This is an unresolved expectation/semantic mismatch; no
  causal product conclusion is made here.

The failing paths are outside the two symbols changed by the reviewed commit,
which changes RH telemetry decision-id/session-generation formatting. The
commit-specific focused oracles and the complete 16-test contract passed.

## Protected runtime safety evidence

PID `112337` was read-only checked before and after verification and remained
alive with the same server command line. The protected checkout
`/root/sglang-3060-12g-hicache`, its service files, seed, and process were not
used as a test checkout and were not modified. Final read-only GPU observation:

```text
NVIDIA GeForce RTX 3060, 550.144.03, 9325 MiB, 0 %
```

The memory use is attributable to the pre-existing service; verification was
CPU-only and did not issue HTTP/load traffic.

## Followups

- Reconcile the six broad-suite fixture/expectation mismatches in a fresh task
  before claiming those two full suites green.
- Preserve the focused-oracle log and the three passing requested-suite logs
  as the acceptance evidence for commit `9213ee01d9`.

## Open issues

- `test_ready_horizon_unit.py` is not fully green: 2 failures and 4 fixture/API
  errors.
- `test_hicache_restore_scheduler_feed.py` is not fully green: 1 failure and 2
  fixture/API errors.
- The host-allocation threshold mismatch remains unresolved by this tester
  invocation; causal diagnosis or implementation changes require a fresh owner
  task.
