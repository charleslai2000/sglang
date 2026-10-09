ENTRY: ACCEPT

# TEST3060-RH-PREADMISSION-FIX-20260909

status: done
task_id: TEST3060-RH-PREADMISSION-FIX-20260909
orchestration_epoch: 20260909-rh-ab23
role: tester
repository: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
branch: 3060-12g-qwen35-4b
commit: 3785c99759d4026ebc4364ee46edb07987ed3b1a

## Artifacts

- This report only:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-RH-PREADMISSION-FIX-20260909.md`
- Independently executed committed regression:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_prefetch_gate_skip_regression.py`
- Reviewed prior static report, coder fix report, Pattern Intake,
  Novel Mechanism, and RH architecture gate artifacts.
- No product, gate, remote-host, or 3090-branch files were modified.

## Independent verdict

**ACCEPT** for the requested deterministic/static and dependency-free
pre-admission verification. The gate-skip runtime defect reported at
`3ddc39c223` is corrected at `3785c99759`: the qualifying cache-mode
gate-skip frontier-wait path now returns typed `PrefetchIssueResult.DECLINED`
and no longer reads the gate-pass-only `outcome` local. No live deployment or
dependency-backed runtime acceptance is claimed.

## Evidence and commands

### Revision and scope

```text
git rev-parse HEAD
3785c99759d4026ebc4364ee46edb07987ed3b1a

git status --short --branch
## 3060-12g-qwen35-4b
?? pre-existing .memory/, review/gates/, and storage/ artifacts

git diff --name-status 3785c99759^ 3785c99759
A  3090-dev/test_prefetch_gate_skip_regression.py
M  python/sglang/srt/managers/scheduler.py
```

The complete RH implementation range `3ddc39c223^..3785c99759` contains the
five pre-admission implementation/test files from the prior change plus the
two-file fix commit, with no unrelated RH source scope. `git branch -a
--contains 3785c99759` reports only `3060-12g-qwen35-4b`; the 3090 branch
refs do not contain the target fix commit. This invocation performed no Git
writes.

### Gate-skip regression

```text
python3 3090-dev/test_prefetch_gate_skip_regression.py
test_gate_pass_preserves_storage_issue_and_typed_result ... ok
test_gate_skip_registers_wait_and_declines_without_storage_io ... ok
Ran 2 tests in 0.093s
OK
```

The regression is a dependency-free AST extraction of the committed
`_prefetch_kvcache_impl`. Its gate-skip fixture independently sets:

- `enable_hicache_storage=True`;
- `prefetch_gate_ok=False`;
- cache mode rather than buffer-only mode;
- a qualifying prompt (`prompt_can_qualify_for_prefetch=True`);
- `_no_material_fast_forward_for=False`, forcing the non-fast-forward
  frontier wait;
- a fake frontier waiter and restore-event recorder; and
- a storage prefetch recorder.

It asserts the result is the typed `DECLINED`, exactly one
`GATE_SKIP_FRONTIER` event and frontier registration, and zero
`prefetch_from_storage` calls. The companion gate-pass case asserts storage
issue execution and the existing typed result behavior. This genuinely
exercises the previously failing branch rather than only checking source text.

### Static and in-memory checks

```text
AST parse + in-memory compile of all six files in 3ddc39c223^..3785c99759
changed_files_ast_parse_compile: PASS 6 files

git diff --check 3ddc39c223^ 3785c99759
changed_files_diff_check: PASS
```

Independent AST inspection of `scheduler.py` found:

- `outcome` has one store at line 3139 and loads only in the gate-pass outcome
  handling at lines 3157, 3159, 3161, 3164, and 3166; no return expression
  reads it on the gate-skip path.
- All six `_prefetch_kvcache` call sites provide explicit origins: one
  `READY_HORIZON`, three `DEMAND_RETRY`, one `EAGER_RH_OFF`, and one
  `EAGER_DISAGG_PREFILL`.
- RH-OFF NULL enqueue calls eager prefetch at lines 4606-4609 before
  `waiting_queue.append` at line 4610.
- RH-ON NULL enqueue reaches `waiting_queue.append` without a prefetch call;
  `_ready_horizon_pass` calls prefetch only for `plan.to_issue` with
  `READY_HORIZON` at lines 3939-3942.
- The RH scheduler cycle invokes restore reconciliation before the RH pass.
- The claim wrapper returns `ACTIVE` for an existing active claim, retains a
  claim only for `ISSUED`, and releases it for non-issued results and
  exceptions.

An additional in-memory AST harness independently passed:

```text
active_claim_suppression: PASS
decline_claim_release: PASS
exception_claim_release: PASS
```

### Focused unit harness attempts

```text
PYTHONPATH=python python3 3090-dev/test_ready_horizon_unit.py
FAIL during import: ModuleNotFoundError: No module named 'orjson'

PYTHONPATH=python python3 3090-dev/test_hicache_restore_scheduler_feed.py
FAIL during import: ModuleNotFoundError: No module named 'orjson'
```

These are environment blocks, not product-test failures. No packages were
installed. The committed dependency-free regression and the independent
in-memory checks do not require `orjson`.

## Acceptance-criteria assessment

1. **Gate-skip fix:** PASS. The former `UnboundLocalError` branch now returns
   typed `DECLINED`, registers the required frontier wait/event, and performs
   no storage I/O.
2. **RH-OFF ordering:** PASS structurally and by the committed ordering test
   fixture: eager prefetch is before queue append and carries
   `EAGER_RH_OFF`.
3. **RH-ON sole initial owner:** PASS structurally and by the committed test
   fixture: direct NULL-mode enqueue is queue-first and does not prefetch; the
   RH pass is the initial `READY_HORIZON` issue owner.
4. **Explicit origins and demand-retry classification:** PASS by independent
   AST caller-origin scan; all six call sites are origin-tagged and retry
   paths use `DEMAND_RETRY`.
5. **Claim cleanup/no duplicate issue:** PASS in the independent in-memory
   wrapper harness and source inspection. Active claims suppress a second
   lower-layer call; decline and exception paths release claims.
6. **RH boundary/host allocation scope:** PASS by diff and source inspection.
   The fix changes only the return value in the gate-skip branch and does not
   alter allocator, host-allocation, Mamba, or persistence authority.
7. **Regression and branch scope:** PASS for the dependency-free regression
   and exact commit scope. Dependency-backed focused tests remain unexecuted
   because `orjson` is unavailable. No 3090 branch contains the target commit.

## Summary

Done. The gate-skip defect is independently reproduced as fixed, the new
regression covers the qualifying non-fast-forward frontier-wait case with
typed `DECLINED` and zero storage calls, RH ordering/origins are statically
verified, and claim lifecycle checks pass. No code defect was found in the
requested fix.

## Followups

- Run the two focused dependency-backed harnesses in a project environment
  providing `orjson` under a fresh tester Task ID.
- Obtain live 3060/runtime and performance evidence under the separately
  authorized deployment/performance gates if terminal deployment acceptance is
  required.

## Open issues

- `orjson` is missing, so full project-backed unit/runtime evidence is not
  available in this environment.
- No live remote or deployment test was authorized or collected.
- The supplied Pattern Intake, Novel Mechanism, and architecture documents
  remain design/gate inputs with their stated decision authority; this tester
  report does not self-approve those gates.
