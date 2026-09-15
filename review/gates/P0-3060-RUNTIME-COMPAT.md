ENTRY: ACCEPT

# P0 3060 Torch runtime compatibility independent gate review

- Task ID: `D3060-REVIEW-091`
- Orchestration epoch: `2026-09-09`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Reviewed commit: `ac1a869e6d9d11a798c11d7880169dc2d7d53789`
- Parent commit: `032bbe7e38f2b06c0efb01bdfb5baa79532974e3`
- Branch: `3060-12g-qwen35-4b`
- Gate verdict: **REJECT** (the supplied EXEMPT is not applicable to this
  runtime/dependency/failure change; no new code-level defect was found in this
  bounded review)

## Scope and authoritative inputs

This is a fresh review of the exact revision previously reviewed under
`D3060-REVIEW-088`. I inspected the complete parent-to-commit diff in
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`, the prior gate
report, plus:

- causal report: `DEBUG-20260909-3060-RUNTIME-COMPAT.md`;
- implementation report: `CODE-20260909-3060-RUNTIME-COMPAT.md`;
- governance artifact:
  `storage/review/gates/pattern-intake/EXEMPT-3060-RUNTIME-COMPAT.md`;
- `python/sglang/srt/distributed/device_communicators/pynccl_allocator.py`;
- `python/sglang/srt/server_args.py`;
- `test/registered/core/test_runtime_compat.py`.

The commit is on branch `3060-12g-qwen35-4b`. `git branch --contains
ac1a869e6d` reports only that 3060 branch; the 3090 branch remains at
`d49214e592` and does not contain this commit. The commit's tracked scope is
exactly the three paths listed above. The current worktree contains only the
untracked gate report and untracked EXEMPT artifact in addition to the commit;
those governance files are not part of the implementation commit.

The independent checks below do not claim live runtime success. I did not
modify product code, the remote, memory, or the EXEMPT artifact.

## Requirement review

### Argparse percent rendering — PASS

`server_args.py:2998` changes the literal from `67%` to `67%%`. The focused
test asserts that complete `ServerArgs` help contains the rendered text
`67% of the kv pool at 8G/1.5G`. An independent dependency-free argparse
probe also rendered `67%%` as `67%` and confirmed that `67%%` was absent from
the output.

### Torch 2.5 missing controls are optional at import — PASS by source review

`pynccl_allocator.py:9-17` keeps `CUDAPluggableAllocator` as the direct import
and resolves each newer private control with `getattr(..., None)`. The module
therefore does not import-fail solely because the three current-thread
controls are absent. The local environment has no Torch installation, so an
actual Torch 2.5.1 import was not executable in this invocation.

### Disabled and TP=1 paths return `nullcontext` — PASS by source review

`pynccl_allocator.py:353-359` retains the existing decision order: disabled
configuration, explicit `disabled=True`, or `world_size == 1` returns
`nullcontext()` without constructing `SymmetricMemoryContext`. Focused tests
at `test_runtime_compat.py:30-57` remove all three controls and assert both
the explicitly disabled and TP=1 cases return `nullcontext`.

### Missing controls fail precisely before pool creation — PASS by source review

`pynccl_allocator.py:169-180` checks all three names for callability and
raises `RuntimeError` containing the Torch version, the current-thread MemPool
requirement, and every missing control. `SymmetricMemoryContext.__init__` calls
the guard at line 279 before `get_nccl_mem_pool()` at line 281. The focused
test at `test_runtime_compat.py:60-81` verifies the message and that pool
creation is not called. The guard is also repeated at `__enter__` and
`__exit__` (`:290`, `:315`) as defense in depth.

### All-controls behavior retained — PASS by source review

With all controls callable, the existing calls remain unchanged:

- `_cuda_beginAllocateCurrentThreadToPool(device, pool)` at line 307;
- `_cuda_endAllocateToPool(device, pool)` at line 316;
- `_cuda_releasePool(device, pool)` at line 317.

The focused test at `test_runtime_compat.py:84-113` supplies mocks for all
three and checks the exact device/pool arguments and one call each. No older
stream MemPool fallback or fabricated control was introduced.

### Scope and branch compatibility — PASS

The complete commit diff contains exactly these three paths:

- `python/sglang/srt/distributed/device_communicators/pynccl_allocator.py`;
- `python/sglang/srt/server_args.py`;
- `test/registered/core/test_runtime_compat.py`.

No remote, product file outside the requested compatibility surface, or 3090
branch ref was changed by this commit. `git show --check` and the parent-to-
commit `git diff --check` passed.

## Independent evidence

Run from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile` over the two product files
  and focused test — **PASS**.
- `git show --format= --check ac1a869e6d` — **PASS**.
- `git diff --check 032bbe7e38..ac1a869e6d` — **PASS**.
- Dependency-free argparse rendering probe — **PASS**.
- Dependency-free AST compatibility-boundary assertions — **PASS**.
- `python3 -m pytest -q test/registered/core/test_runtime_compat.py` —
  **BLOCKED before collection**: `/usr/bin/python3: No module named pytest`.
  The same interpreter has no `torch` module, so the focused runtime tests
  could not be executed here.
- No broad suite, server, GPU runtime, remote host, or live smoke was run.

## Findings

### F-1 — High / blocking: the supplied EXEMPT is not applicable to this diff

The governing contract in `/home/dev-codex/workspaces/nerun-dev/AGENTS.md:21-24`
requires full intake for any semantic, dependency, interface, failure, or
harness/oracle change. The detailed contract at
`storage/review/gates/pattern-intake/README.md:190-203` limits `EXEMPT` to
mechanical transformations that change none of those properties and expressly
excludes dependency/API changes and mixed code/documentation work.

This commit crosses those exclusions:

1. `pynccl_allocator.py:9-17` changes the Torch private-API dependency handling
   from mandatory import-time resolution to guarded optional resolution.
2. `pynccl_allocator.py:169-180` and `275-281` move the unavailable-control
   failure from module import to an explicit runtime failure when a symmetric-
   memory context is constructed. That is a material failure-boundary/runtime
   behavior change, even though the multi-rank outcome remains fail-safe.
3. The new `test/registered/core/test_runtime_compat.py` adds a test harness and
   regression oracle for those changed behaviors; it is not a documentation or
   mechanical-only transformation.

The EXEMPT is narrow in file and branch scope, but its classification is not
narrow enough under the contract. Its statement that unsupported multi-rank use
"remains an explicit failure" does not attest away the changed import/failure
boundary. Its claim that no dependency or failure change is covered is
contradicted by the changed symbols and control flow above. The artifact also
does not provide the contract's full exemption-section semantic-impact
attestation.

Acceptance impact: **terminal implementation acceptance cannot be granted**.
The missing prerequisite is now the applicable full Pattern Intake (and a
Novel Mechanism declaration if the intake finds no accepted existing pattern
for this compatibility/failure boundary), not another EXEMPT document.

## Residual risks and open issues

- Focused runtime tests remain unexecuted because this environment lacks both
  `pytest` and `torch`; no Torch 2.5.1 import or CUDA behavior is claimed.
- No live TP=1 Qwen3.5-4B startup or request evidence is claimed; the reports
  identify separate SM86/kernel and model/runtime risks outside this review.
- F-1 is the only acceptance-blocking finding from this bounded review. The
  prior code-level findings remain valid by independent source/static checks.

## Summary and followups

The exact implementation revision still satisfies the reviewed code-level
requirements and remains limited to the expected 3060 compatibility surface.
The newly supplied EXEMPT is not a valid exemption under the repository
contract because the patch changes dependency/API handling, runtime import and
failure behavior, and the test oracle. Therefore this re-opened gate remains
**REJECTED** despite the absence of a new code defect.

Followups:

1. Under a fresh Task ID, provide a completed full Pattern Intake for the
   three-path implementation, including the atomic invariant-to-pattern-to-test
   chain and failure-boundary evidence; include a Novel Mechanism declaration
   if required by that intake.
2. Under a separate fresh tester Task ID, run
   `test/registered/core/test_runtime_compat.py` in the approved Torch
   2.5.1+cu124 environment and perform the separately authorized bounded 3060
   smoke. Those results must not be inferred from this review.
3. Re-open this exact revision after the applicable intake and tester evidence
   are available. Do not alter or broaden the existing EXEMPT to bypass the
   full-intake requirement.

Extra work requires a fresh Task ID.

status: done
artifacts: `review/gates/P0-3060-RUNTIME-COMPAT.md`
evidence: exact commit diff/scope, source review, py_compile, argparse probe, git checks, prior implementation/causal reports, and EXEMPT applicability review
summary: bounded independent review completed; code-level checks remain valid, but the EXEMPT classification is invalid for the runtime/dependency/failure change
followups: full Pattern Intake/possible Novel Mechanism, approved-environment focused tests and bounded smoke, then fresh gate re-open
open_issues: F-1 invalid EXEMPT applicability; local pytest/Torch unavailable; no live runtime evidence.
