status: done
artifacts:
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py
- /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODER-RH-DUPLICATE-TEST-FIX-20260910.md
evidence:
- Read final review finding in REVIEW-RH-RELEASE-EPOCH-FINAL-20260910.md. It identified that the appended eligible r3 is correctly issued, so asserting the complete issued list remains exactly [r1, r2] is invalid; the test must isolate duplicate r2.
- Modified only the target test assertion block. The production modules were not changed by this task.
- `python3 -m py_compile /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_ready_horizon_unit.py` passed (exit 0, no output).
- `git -C /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt diff --check` passed (exit 0, no output).
- Dependency-light unittest attempt without source path failed at import because `sglang` is not installed: `ModuleNotFoundError: No module named 'sglang'`.
- Dependency-light unittest attempt with `PYTHONPATH=/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python` failed during import because the environment lacks `orjson`: `ModuleNotFoundError: No module named 'orjson'`. No installs were performed.
- Current git status confirms the target test is modified and the product files already had unrelated working-tree modifications; this task did not alter those product files.
summary:
Fixed the false duplicate-event assertion in `test_spec_budget_park_wakes_after_unsampled_aba_release`. The later pass may legitimately issue the newly appended eligible r3; the test now requires r1/r2 as the first two issues, requires r2 exactly once, and requires r3 to be issued. The release epoch and cleanup assertions remain intact.
exact_diff:
```diff
             scheduler.waiting_queue.append(_req("r3", NONE))
             scheduler._ready_horizon_pass()
-            self.assertEqual(scheduler.issued, ["r1", "r2"])
+            self.assertEqual(scheduler.issued[:2], ["r1", "r2"])
+            self.assertEqual(scheduler.issued.count("r2"), 1)
+            self.assertIn("r3", scheduler.issued)
             self.assertEqual(cc.speculative_release_epoch, 2)
```
followups:
- Run the focused Ready Horizon test in a dependency-complete environment containing the project runtime dependencies (`orjson`, and any other required test dependencies).
open_issues:
- Focused unit execution remains unverified in this environment because `orjson` is unavailable; py_compile and diff checks passed.
