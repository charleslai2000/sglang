status: done
artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-RH-SPEC-BUDGET-RETRIGGER-20260910.md (this report)
- remote transient backup /tmp/sglang-rh-spec-budget-pre/ created then removed after verified restore
evidence:
  unit_suite_command: >-
    cd /root/sglang-3060-12g-hicache && PYTHONPATH=/root/sglang-3060-12g-hicache/python
    /root/sglang-env-3060-4b/bin/python -m unittest 3090-dev/test_ready_horizon_unit.py -v
  unit_suite_result: Ran 72 tests in 0.024s; FAILED (failures=2, errors=4); UNITTEST_EXIT=1
  unit_suite_pass_fail: passed(ok)=66, FAIL=2, ERROR=4, skipped=0, not_executed=0
  unit_suite_failure_detail:
    errors_4_DeterministicMissParkTests:
      - test_after_reprobe_miss_reparks_at_new_cursor
      - test_anchor_version_advance_clears_and_reprobes_once
      - test_miss_recorded_and_held_across_ordinary_changes
      - test_unrelated_chain_global_bump_never_clears_no_l3
      traceback_snippet: >-
        File ".../3090-dev/test_ready_horizon_unit.py", line NNNN, in <test>
          scheduler._ready_horizon_pass()
        File ".../python/sglang/srt/managers/scheduler.py", line 4773, in _ready_horizon_pass
          result = self._prefetch_kvcache(...)
        TypeError: DeterministicMissParkTests._make_scheduler.<locals>.charge()
        got an unexpected keyword argument 'origin'
    fail_1_test_active_prefetch_claim_blocks_duplicate_and_classifies_retry:
      - >-
        AssertionError: PrefetchIssueResult(status=<HiCachePrefetchIssueStatus.SKIPPED_ACTIVE: 3>,
        attempt_id='r1:prefetch:1', origin=<HiCachePrefetchOrigin.READY_HORIZON: 2>,
        reason='active_attempt', state_before='null', state_after='null')
        is not <HiCachePrefetchIssueStatus.SKIPPED_ACTIVE: 3>
    fail_2_test_ready_stage_log_reports_issue_result:
      - >-
        AssertionError: False is not true : ['INFO:...scheduler:[P3] ... evt=rh_match_prepare ...',
        'INFO:...scheduler:[P3] ... evt=rh_preadmission_decision ...',
        'INFO:...scheduler:[P3] ... evt=ready_stage schema=rh_stage.v2 rid=r1 decision_id=r1:rh:1
        attempt_id=r1:prefetch:1 issue_origin=READY_HORIZON ... result=issued reason=issued ...',
        'INFO:...scheduler:[P3] ... evt=ready_pool ...']
  pre_state_remote:
    health_http: 200
    git_rev_parse_HEAD: FAILED - /root/sglang-3060-12g-hicache is not a git repository
    sha256_scheduler.py: e3a78d4856743c4842243a25307db84dec24a6f0303fb81c2fd2f0fa2f8f7d4e
    sha256_test_ready_horizon_unit.py: faa787d1b87e65a646235f3804cb6afea9a31dbc6e63d640ad9052cea5076db1
    service_pid_generation_pre: 171166..173051 (old master generation; 171166 verified gone later)
  local_fix_state_deviations:
    - >-
      Dispatch assumed the two files carry an UNCOMMITTED local fix, but local repo
      /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt (branch 3060-12g-qwen35-4b)
      has HEAD=4f41f5bab5 '[3060] retrigger ready horizon after speculative budget release';
      git status --porcelain shows no tracked modifications and git diff --name-only HEAD is EMPTY.
      The fix is COMMITTED at HEAD, not uncommitted. The fix commit touches exactly the two
      dispatch-designated files (plus a review doc under review/gates/).
    - >-
      Local sha256 of the two files == remote pre-test sha256 exactly, i.e. remote already
      carried byte-identical fixed content before this run. scp was therefore a content no-op
      (still performed per procedure; post-copy hashes unchanged).
    - >-
      Remote /root/sglang-3060-12g-hicache is not a git repo, so step-1 git rev-parse HEAD
      cannot be satisfied on the remote (recorded; not blocking for the unit run).
  copy_step: scp of ONLY the two files local -> matching remote paths; SCP-OK; post-copy hashes unchanged.
  post_state_remote:
    restored_sha256_scheduler.py: e3a78d4856743c4842243a25307db84dec24a6f0303fb81c2fd2f0fa2f8f7d4e (match pre-test)
    restored_sha256_test_ready_horizon_unit.py: faa787d1b87e65a646235f3804cb6afea9a31dbc6e63d640ad9052cea5076db1 (match pre-test)
    health_http_final: 200 (5x consecutive at 05:40:15, then 3x consecutive at final check)
    transient_backup: removed after restore verified
  service_restart_observation:
    - >-
      Live service WAS restarted during this session at 2026-09-10 05:39:03 (new master PID 173342,
      PPID 1 docker-init, lstart Thu Sep 10 05:39:03 CST 2026). Pre-test master PID generation
      (171xxx..173051) is gone. This restart was NOT issued by me: I ran no restart/stop/kill command;
      my only writes to the checkout were identical-content scp (2 files) and identical-content cp
      restore (2 files), which cannot affect an already-imported running Python process.
    - >-
      Evidence of a concurrent intentional deploy of the fix commit: /tmp/sglang3060-rh-fix-4f41f5.log
      (log name references commit 4f41f5) shows SGLang launch banner at 05:39:16 and contains current
      PID 173342; probe logs (t38c-probe.log, b15-probe.log) and tmp dirs at 05:39-05:41 show concurrent
      activity. Remote checkout dir mtime 05:34 predates my session.
    - >-
      My post-restore health probe (immediately after restore) returned 000/connection-refused because
      it hit the concurrent deploy's startup window (server bound port after CUDA-graph init ~05:40:05).
      Health recovered to 200 and is stable. The unit suite itself is process-isolated and unaffected by
      the live-service restart.
summary:
  executed: 72 unit tests (focused suite, unittest runner, remote venv, PYTHONPATH set) - completed
  passed: 66
  failed: 2 (assertion FAIL) + 4 (ERROR)  [unittest summary: FAILED (failures=2, errors=4)]
  skipped: 0
  not_executed: 0
  post_conditions: two remote files byte-identical to pre-test state (sha256 verified); health 200;
    live service was NOT restarted by me but WAS restarted concurrently by an external deploy of commit 4f41f5.
followups:
- >-
  Diagnose the 2 failures + 4 errors (owner: coder/tester). All 4 errors share the same mechanism:
  _ready_horizon_pass -> _prefetch_kvcache now passes an 'origin' kwarg that the DeterministicMissParkTests
  fake charge() does not accept (scheduler.py:4773). The 2 failures are assertion mismatches
  (PrefetchIssueResult identity; ready_stage log content). Full verbatim output is preserved in this session.
- >-
  Reconcile the concurrent 3060 deploy/restart of commit 4f41f5 (log /tmp/sglang3060-rh-fix-4f41f5.log)
  with this test run's 'do not disturb live service' assumption (owner: orchestrator/devops).
  A quiescent-window re-run would yield an uncontested 'no restart' post-condition; unit results are
  expected to be identical because the suite is process-isolated and file content was identical throughout.
- >-
  Confirm remote sync/deploy mechanism for /root/sglang-3060-12g-hicache (not a git repo) (owner: devops).
- >-
  Local fix is committed (4f41f5bab5) rather than uncommitted as the dispatch assumed; no commit action was
  taken by me. Confirm whether the branch tip is the intended source of truth (owner: orchestrator/coder).
open_issues:
- Acceptance item 'service process was NOT restarted' is NOT confirmed: evidence shows an external
  concurrent restart at 05:39:03 (new PID 173342). It is attributed to a concurrent deploy of the fix
  commit, not to this run. Final health is 200.
- Remote is not a git repository, so remote HEAD capture was impossible (recorded, non-blocking).
- Remote 3090-dev/__pycache__ grew ~176K from the unittest import (transient bytecode; not a tracked product
  file; may partially pre-exist). Two target files are unaffected and verified byte-identical.
