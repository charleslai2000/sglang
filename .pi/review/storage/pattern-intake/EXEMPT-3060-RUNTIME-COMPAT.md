# EXEMPT — 3060 runtime compatibility boundary

- Task ID: `D3060-DOC-090`
- Orchestration epoch: `2026-09-09`
- Declaration: narrow governance EXEMPT
- Reviewed task: `D3060-CODE-086`
- Commit: `ac1a869e6d9d11a798c11d7880169dc2d7d53789`
- Parent commit: `032bbe7e38f2b06c0efb01bdfb5baa79532974e3`
- Branch: `3060-12g-qwen35-4b`

## Boundary and basis

This declaration covers only the already-reviewed compatibility patch for the
experimental RTX 3060/SM86 hardware path. It is a maintenance and compatibility
boundary, not a new product capability or a change to the 3090 production
state machine.

The patch preserves the existing supported current-thread MemPool behavior,
keeps the existing disabled and TP=1 `nullcontext()` paths, and fails clearly
when a multi-rank path requires unavailable Torch controls. Its argparse change
preserves the rendered help text while escaping a formatting literal. The
independent review found no code-level defect in this bounded scope and records
that the reviewed commit is present only on the 3060 branch.

Evidence:

- [authoritative independent review](../../../../review/gates/P0-3060-RUNTIME-COMPAT.md)
- [implementation report](../../../../../../sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/CODE-20260909-3060-RUNTIME-COMPAT.md)
- [causal compatibility report](../../../../../../sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/DEBUG-20260909-3060-RUNTIME-COMPAT.md)

## Files covered

The declaration is limited to the three paths in commit
`ac1a869e6d9d11a798c11d7880169dc2d7d53789`:

- `python/sglang/srt/distributed/device_communicators/pynccl_allocator.py`
- `python/sglang/srt/server_args.py`
- `test/registered/core/test_runtime_compat.py`

No other product file, 3090 branch reference, review gate, remote, or runtime
state-machine component is covered or waived by this declaration.

## Why this qualifies for the narrow EXEMPT path

No new reusable implementation pattern is introduced. The change is confined
to an existing import/feature compatibility boundary and a behavior-preserving
help-string escape, with focused regression tests for the changed behavior. It
does not introduce a new authority, persistence contract, interface, cache or
session semantic, concurrency protocol, failure-domain owner, harness oracle,
or tuning mechanism. It also does not replace or weaken the existing allocator
contract with an older Torch API; unsupported multi-rank use remains an
explicit failure.

Accordingly, a full reusable-pattern intake or Novel Mechanism declaration is
not applicable to this bounded maintenance/compatibility artifact. This is a
classification for the stated files and commit only; it is not a broad waiver
for future compatibility work or for any semantic, authority, dependency,
interface, persistence, concurrency, failure, harness/oracle, or tuning change.

## Risks and limits

- The local environment lacked `pytest` and `torch`; no local Torch 2.5.1
  runtime or focused pytest pass is claimed.
- The patch does not establish Qwen3.5 model compatibility, CUDA readiness,
  SM86 kernel viability, HTTP readiness, generated output, or live TP=1 smoke
  success.
- Multi-rank symmetric-memory use with unavailable current-thread controls
  remains unsupported and must fail explicitly; this declaration does not
  approve a fallback.
- The separately reviewed SM86/kernel, model/runtime, and environment risks
  remain outside this EXEMPT boundary.

## Acceptance condition retained

This EXEMPT artifact satisfies only the governance-artifact prerequisite
identified by the independent review. Runtime acceptance still requires the
separate 3060 tester evidence in the approved Torch 2.5.1+cu124 environment,
including the focused compatibility tests and the separately authorized
bounded 3060 smoke. The reviewer must then re-run or re-open acceptance for
this exact revision (or an explicitly superseding revision). No runtime
acceptance is granted by this document.

Extra corpus, research, design, implementation, or test work requires a fresh
Task ID.

Status: `done` for the authorized documentation artifact.

Open issues: focused pytest/Torch runtime evidence and live 3060 tester
evidence remain outstanding; the independent review gate remains subject to
its stated follow-up acceptance conditions.
