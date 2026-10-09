ENTRY: ACCEPT

# TEST3060-RH-PREADMISSION-STATIC-20260909

status: done
task_id: TEST3060-RH-PREADMISSION-STATIC-20260909
orchestration_epoch: 20260909-rh-ab21
role: tester
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
commit: 3ddc39c2231d220466ca84310c55ceb7080702bf

## Artifacts

- This report only:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-RH-PREADMISSION-STATIC-20260909.md`
- Reviewed inputs: the Pattern Intake, Novel Mechanism, RH architecture gate,
  `CODE3060-RH-PREADMISSION-20260909.md`,
  `DBG-20260909-RH-NO-STAGING.md`, and the exact commit diff.
- No product, gate, or remote-host files were modified.

## Independent verdict

**BLOCK** — the commit introduces a runtime regression in the existing
non-gate prefetch path. In `scheduler.py:3234-3237`, the gate-skip branch
returns based on `outcome`, but `outcome` is assigned only in the preceding
`prefetch_gate_ok(...)` branch (`scheduler.py:3139`). The prior commit returned
cleanly from this branch. With storage enabled, a qualifying request whose
anchor is not currently a storage gate passes and has material/in-flight state
(`_no_material_fast_forward_for(...)` false), the code registers a frontier
wait and then raises `UnboundLocalError` instead of returning
`PrefetchIssueResult.DECLINED`.

This is an implementation defect, not an environment issue. It can be reached
from RH-ON staging, RH-OFF eager enqueue, and demand-retry calls because all
use the same `_prefetch_kvcache_impl` body. Deployment acceptance is blocked
until the owner corrects this path and adds or runs a regression oracle for it.

## Evidence and exact commands

### Revision and scope

```text
$ git rev-parse HEAD
3ddc39c2231d220466ca84310c55ceb7080702bf

$ git diff --name-status 3ddc39c2231d220466ca84310c55ceb7080702bf^ 3ddc39c2231d220466ca84310c55ceb7080702bf
M  3090-dev/test_hicache_restore_scheduler_feed.py
M  3090-dev/test_ready_horizon_unit.py
M  python/sglang/srt/managers/schedule_batch.py
M  python/sglang/srt/managers/scheduler.py
M  python/sglang/srt/managers/scheduler_components/hicache_restore.py
```

The worktree had pre-existing unrelated untracked `.memory/`, `review/gates/`,
and `storage/` entries. No source file was changed by this verification.

### Static checks

```text
$ python3 -c "... ast.parse(...) ..."
ast.parse: PASS 5 files

$ python3 -c "... compile(open(...).read(), ..., 'exec') ..."
compile(source): PASS 5 files; no repository bytecode written

$ git diff --check 3ddc39c2231d220466ca84310c55ceb7080702bf^ 3ddc39c2231d220466ca84310c55ceb7080702bf
PASS (no output)

$ dependency-free AST caller scan for _prefetch_kvcache
calls: [(3945, True, False), (3476, True, False),
        (3505, True, True), (3664, True, True),
        (4611, True, False), (4626, True, False)]
origin: PASS
```

The bounded `py_compile.compile(..., cfile='/dev/null')` attempt was not usable
because Python rejects `/dev/null` as a non-regular bytecode target
(`FileExistsError`). The in-memory `compile(source)` check above avoided any
repository write and passed. No packages were installed.

### Focused test attempts

```text
$ python3 3090-dev/test_ready_horizon_unit.py
FAIL: ModuleNotFoundError: No module named 'sglang'

$ PYTHONPATH=python python3 3090-dev/test_ready_horizon_unit.py
FAIL during collection: ModuleNotFoundError: No module named 'orjson'

$ PYTHONPATH=python python3 3090-dev/test_hicache_restore_scheduler_feed.py
FAIL during collection: ModuleNotFoundError: No module named 'orjson'
```

These are blocked-environment results, not product-test failures. No remote
load or runtime deployment test was run.

### Minimal dependency-free reproduction

The following bounded harness extracted only the committed
`_prefetch_kvcache_impl` AST function and supplied a fake cache with:
`enable_hicache_storage=True`, `prefetch_gate_ok=False`,
`prompt_can_qualify_for_prefetch=True`, and
`_no_material_fast_forward_for=False`.

```text
$ python3 <dependency-free AST harness>
UnboundLocalError: cannot access local variable 'outcome' where it is not associated with a value
registered_frontier_wait: True
```

This confirms both the causal branch and the failure: the frontier wait is
registered before the invalid return expression is evaluated. The source
static check independently reports `outcome` stores at line 3139 and a load at
line 3236.

## Acceptance-criteria assessment

1. **RH-OFF enqueue order/behavior — PARTIAL/BLOCKED.** Static inspection and
   the added unit fixture show `EAGER_RH_OFF` prefetch is called before queue
   append at `scheduler.py:4610-4616`. The shared implementation regression
   means behavior is not accepted for gate-skip requests.
2. **RH-ON queue-first sole initial owner — PASS structurally.** NULL-mode
   RH-ON enqueue appends without calling prefetch, and `_ready_horizon_pass`
   is the only RH-ON initial caller. The stage path is nevertheless affected
   by the blocker above.
3. **Explicit origins and demand-retry classification — PASS statically.**
   Every six scheduler call sites supplies `origin`; reconciliation/frontier/
   capacity retry sites use `DEMAND_RETRY`; enqueue and RH use their explicit
   eager/RH origins.
4. **Claim cleanup/no duplicate paths — PARTIAL.** The request-local active
   claim blocks a second lower-layer call, non-issued outcomes and exceptions
   release it, and terminal/abort paths release it in the reviewed direct
   paths. The gate-skip defect prevents clean typed completion on one path, and
   the focused runtime tests that exercise claim behavior could not collect.
5. **Telemetry joins/no logging side effects — PARTIAL.** The added records
   carry RID plus attempt/origin where an attempt exists (`rh_preadmission`,
   `ready_stage.v2`, `ready_host`, `admission.v2`), and the source diff shows
   no telemetry field used as a scheduling predicate. Runtime/logging tests
   were unavailable; the shared prefetch defect blocks behavioral acceptance.
6. **Host-alloc/Mamba untouched except origin plumbing — PASS by diff scope.**
   The commit changes exactly five expected files, adds no `unified_radix_cache`
   or Mamba implementation changes, and the added scheduler lines contain no
   host-allocator/Mamba implementation edits; existing host-allocation argument
   plumbing remains in place.
7. **Meaningful tests/no accidental 3090 scope violation — PARTIAL.** The
   added fixtures directly assert RH-ON queue-first ordering, RH-OFF call
   order/origin, active-claim suppression, demand-retry classification, and
   stage telemetry. They do not cover the gate-skip regression, and imports are
   blocked by missing `orjson`. The diff remains within the five expected
   branch-scoped files.

## Summary

The requested ownership split is present structurally: RH-OFF retains eager
ordering, RH-ON direct NULL requests are queue-first, all prefetch callers are
origin-tagged, and the diff leaves lower host-allocation/Mamba implementations
outside the changed files. Independent verification cannot accept the commit,
however, because the refactored prefetch body raises
`UnboundLocalError` on a valid frontier-wait branch. Focused test execution is
also unavailable in this environment due to missing project dependencies.

## Followups

- Fresh implementation Task ID: fix the gate-skip return so it does not read
  an unassigned `outcome`, preserving the prior clean frontier-wait behavior
  and typed `DECLINED` result.
- Add a dependency-free or project-runtime regression test covering
  `prefetch_gate_ok=False`, qualifying prompt, and non-fast-forward frontier
  wait; then rerun both focused test files in an environment with `orjson`.
- Fresh tester Task ID is required for post-fix independent verification.

## Open issues

- Focused runtime/unit evidence is missing because `orjson` is unavailable;
  this is an environment block, separate from the reproduced product defect.
- Formatter/type-checker evidence was not run because the executables were not
  installed and installation was out of scope.
- The supplied debugger report notes source-to-runtime hash identity and live
  RH acceptance evidence remain unavailable; no remote test was authorized.

```text
status: done
artifacts: TEST3060-RH-PREADMISSION-STATIC-20260909.md
evidence: exact commit/branch; five-file diff; AST/compile/static checks; dependency-free gate-skip reproduction; focused-test collection failures
summary: BLOCK due to UnboundLocalError in committed frontier-wait prefetch path; ownership/origin wiring otherwise structurally aligned
followups: fresh implementation fix and fresh independent tester verification
open_issues: missing orjson/runtime tests; missing formatter/typecheck tools; no remote/live evidence
```
