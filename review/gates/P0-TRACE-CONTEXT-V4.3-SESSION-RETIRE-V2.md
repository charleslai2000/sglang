ENTRY: ACCEPT

# P0 trace-context V4.3 same-node session-retirement V2 review

- Task ID: `REV-20260908-P0-TRACE-CONTEXT-V4.3-SESSION-RETIRE-V2`
- Orchestration epoch: `E20260908-P0P1P2`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Narrow patch verdict: **ACCEPT**
- P0 runtime verdict: **BLOCKED / not accepted**

## Revision identity and scope

Reviewed the dirty worktree at commit `9c9e7b7c7cfdf2ef2b0100662513361c1e17a013`,
branch `3090-24g-opt`. The reviewed V2 scope is the candidate filtering in
`_t38c_retire_session_trace` and its focused fixture coverage in
`3090-dev/test_p0_trace_context_v4.py`, on top of the accepted V4.3 positives.
No product source, test, memory/vehicle file, or remote process was modified;
this gate report is the only written artifact from this review.

Fresh worktree identities:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`:
  `10e0d53b3efa2d8a3a3202c546d7f36a2ef4655979d18d7f6c3722f72706ec6c`
- `3090-dev/test_p0_trace_context_v4.py`:
  `51871321be46ad51f356b5758dbf298b3b85e00d0c84b5bf0fe1c2e842dd6f08`

The worktree contains other pre-existing V4.3, vehicle, and tool changes. They
were outside this review scope and were not silently accepted as part of the
V2 verdict.

## Acceptance checks

The V2 implementation at `unified_radix_cache.py:748-772` now regards a
candidate as belonging to the retiring session only when its
`trace_context` is a dictionary whose `session_id` matches. Therefore a
marker-off candidate with `trace_context=None` is null-safe and is retained;
the attempt-keyed mapping for the node is filtered rather than deleted as a
whole. An explicitly matching session candidate is still removed.

The focused fixture at `3090-dev/test_p0_trace_context_v4.py:350-393` covers
the same-node mixed-attempt preservation case. The independent boundary probe
used one node with:

- a marker-off contextless attempt;
- an explicit candidate for the retiring session; and
- an explicit candidate for another live session.

After retiring the target session, only the explicit target candidate was
removed; the contextless and unrelated live attempts remained. No
`AttributeError` occurred.

## Evidence

All checks were run read-only from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-review-v2 python3 -m py_compile` over
  the V4.3 source files and focused fixture — **PASS**.
- Independent `ast.parse` over the same eight files — **PASS**.
- `python3 3090-dev/test_p0_trace_context_v4.py` — **PASS**:
  `P0 trace-context V4.3 focused checks: PASS`.
- `git diff --check` on the implementation and untracked-fixture check —
  **PASS / no whitespace diagnostics**; the untracked `--no-index` command
  returned its expected difference status `1`.
- `python3 -m pytest 3090-dev/test_p0_trace_context_v4.py -q` — **BLOCKED
  before collection** because `/usr/bin/python3` has no `pytest` module.
- Independent AST-extracted execution of the exact retirement function —
  **PASS** for contextless no-crash/preservation, same-node unrelated-attempt
  preservation, and explicit matching-session retirement.

## Findings

No blocking findings were identified in the narrow V2 patch. The previous
V4.3 findings are not reopened: this review specifically checked that the V2
change does not regress the accepted marker transitions, attempt-keyed
frontier model, or explicit retirement behavior.

Questions: none.

## Verdict and P0 distinction

The V2 same-node session-retirement patch is **ACCEPTED**. It fixes the
marker-off `trace_context=None` crash and prevents retirement from deleting
unrelated same-node attempts while preserving explicit session cleanup.

P0 runtime acceptance remains **BLOCKED** independently of this narrow product
verdict. Do not accept P0 until live **S=25 RH-off** vehicle evidence passes,
including barrier-before-lookup ordering, 25/25 build evidence, exact
`s00002` A-E classification, cleanup, and runtime health. This review did not
run the vehicle or a remote engine.

## Status packet

- Status: `done`
- Artifacts: [this gate report](review/gates/P0-TRACE-CONTEXT-V4.3-SESSION-RETIRE-V2.md) only.
- Evidence: source/test inspection, revision hashes, py_compile PASS, AST PASS,
  focused fixture PASS, diff-check PASS, pytest dependency blocker, and the
  independent contextless/same-node/explicit-session retirement probe.
- Summary: V2 candidate filtering is null-safe and attempt-isolated; explicit
  session candidates still retire.
- Followups: obtain the required live S=25 RH-off vehicle evidence; install or
  provide pytest only if the broader test invocation is required.
- Open issues: P0 live vehicle evidence is still required; pytest is
  unavailable in this environment; unrelated dirty worktree scope remains
  outside this gate.
