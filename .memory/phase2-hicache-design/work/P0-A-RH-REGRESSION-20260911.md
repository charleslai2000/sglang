status: blocked

artifacts:
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/P0-A-RH-REGRESSION-20260911.md`
- Existing prior execution specification: `work/TEST-P0-A-RH-FOCUSED-REGRESSION-20260910.md`

evidence:
- Local target was inspected at `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`, branch scope `3060-12g-qwen35-4b`; the recorded local HEAD is `4f41f5bab562b99562f30c67540eb05344d13637`.
- Existing dependency-complete remote procedure was used without source synchronization or remote mutation. Remote target was the authorized RTX 3060 instance, `root@i-1.gpushare.com:27460`, checkout `/root/sglang-3060-12g-hicache`, interpreter `/root/sglang-env-3060-4b/bin/python`.
- Remote environment probe command:
  ```text
  ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 root@i-1.gpushare.com 'printf "hostname="; hostname; printf "gpu="; nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader 2>&1; printf "checkout="; pwd; test -d /root/sglang-3060-12g-hicache && printf OK || printf MISSING; printf "\\npython="; /root/sglang-env-3060-4b/bin/python --version; printf "pytest="; /root/sglang-env-3060-4b/bin/python -m pytest --version; printf "deps="; /root/sglang-env-3060-4b/bin/python -c "import orjson,msgspec,torch; print(orjson.__version__,msgspec.__version__,torch.__version__,torch.version.cuda)"; printf "\\nstatus="; cd /root/sglang-3060-12g-hicache && git status --short 2>&1; printf "revision="; git rev-parse HEAD 2>&1'
  ```
  Exit status: `0` for the shell command. Observed: RTX 3060, 12288 MiB, compute capability 8.6; Python 3.11.11; pytest 9.1.1; `orjson 3.12.0`, `msgspec 0.21.1`, `torch 2.6.0+cu124`; checkout directory exists. The checkout is not a Git repository (`git status` and `git rev-parse` each reported fatal error).
- Source identity comparison command:
  ```text
  sha256sum 3090-dev/test_ready_horizon_unit.py 3090-dev/test_ready_horizon_partition.py 3090-dev/test_prefetch_budget_split_unit.py 3090-dev/test_hicache_restore_scheduler_feed.py 3090-dev/test_prefetch_gate_skip_regression.py 3090-dev/test_rh_contract_dependency_free.py
  ```
  plus the same `sha256sum` command over the remote checkout via SSH. `test_ready_horizon_partition.py` matched, but `test_ready_horizon_unit.py`, `test_prefetch_budget_split_unit.py`, and `test_hicache_restore_scheduler_feed.py` differed. The remote checkout does not contain `test_prefetch_gate_skip_regression.py` or `test_rh_contract_dependency_free.py`, while both exist locally. Therefore the dependency-complete remote environment cannot verify the current local source state.
- The designated remote test commands were **not sent**, because doing so would test stale/drifted source and cannot establish the requested branch result:
  - `PYTHONPATH=/root/sglang-3060-12g-hicache/python:/root/sglang-3060-12g-hicache/3090-dev /root/sglang-env-3060-4b/bin/python -m pytest -q 3090-dev/test_ready_horizon_unit.py -k "spec_budget_cleared_only_by_budget_release or spec_budget_release_event_clears_unsampled_aba or spec_budget_park_uses_post_issue_cursor_and_wakes_on_release or spec_budget_park_wakes_after_unsampled_aba_release or physical_only_limiter_does_not_create_spec_budget_park or release_counter_monotonic_survives_reconsumption or active_prefetch_claim_blocks_duplicate_and_classifies_retry or no_event_epoch_no_refill or causal_epoch_change_triggers_new_refill or miss_recorded_and_held_across_ordinary_changes or anchor_version_advance_clears_and_reprobes_once or unrelated_chain_global_bump_never_clears_no_l3 or after_reprobe_miss_reparks_at_new_cursor"`
  - `PYTHONPATH=/root/sglang-3060-12g-hicache/python:/root/sglang-3060-12g-hicache/3090-dev /root/sglang-env-3060-4b/bin/python -m pytest -q 3090-dev/test_prefetch_budget_split_unit.py -k "reserve_release_roundtrip or double_release_idempotent or release_without_reservation_noop or demand_reservation_does_not_touch_spec_counter or revoke_path_releases_speculative_reservation or abort_path_releases_speculative_reservation or finalize_path_releases_speculative_reservation or hybrid_discard_path_releases_speculative_reservation or detach_path_releases_speculative_reservation"`
- No RH test case was collected or executed. No live RH-OFF/RH-ON blocker-horizon trace was run. No 3090, production, gate, storage, Git, product-code, or test-code resource was modified.

summary:
executed: remote hardware/dependency probes and local-vs-remote source hash comparison
passed: 0 RH regression tests; remote environment probe exited 0
failed: 0 RH test cases; source identity/revision gate failed (remote checkout is stale/unknown and incomplete)
skipped: 0
not_executed: `3090-dev/test_ready_horizon_unit.py` full suite; required focused tests; `test_ready_horizon_partition.py`; `test_prefetch_budget_split_unit.py`; `test_hicache_restore_scheduler_feed.py`; `test_prefetch_gate_skip_regression.py`; `test_rh_contract_dependency_free.py`; live RH-OFF/RH-ON blocker-horizon run

blocker_horizon_classification:
- environment blocker: local interpreter lacks pytest/runtime dependencies; remote dependency environment is usable, but remote checkout is not byte-identical to the local target.
- source/reconciliation blocker: remote checkout has no Git metadata, its revision is unknown, several target files differ, and two gate-designated files are absent. Source synchronization or remote checkout mutation was not authorized by this dispatch and was not attempted.
- old fixture/API: not freshly classified in this invocation. The prior report records six historical failures (one enum/API mismatch, one telemetry token mismatch, four `charge(origin=...)` fixture mismatches), but those are prior context only and were not reproduced.
- current regression: not assessable; zero RH test cases executed.

followups:
- Provide an already dependency-complete remote checkout byte-identical to the current local six target files, or separately authorize a safe source/profile reconciliation.
- After identity is reconciled, run the exact dependency-complete focused commands and the full `PYTHONPATH=python python3 -m pytest -q 3090-dev/test_ready_horizon_unit.py` procedure, then perform the separately required live RH-OFF/RH-ON blocker-horizon trace.

open_issues:
- P0-A remains `NOT_VERIFIED` and blocked at the source-identity/environment horizon.
- This report makes no claim about P0-B, P0-C, P1, production acceptance, or final quality acceptance.
