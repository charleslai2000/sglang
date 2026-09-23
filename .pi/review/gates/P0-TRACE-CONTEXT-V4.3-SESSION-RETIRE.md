ENTRY: ACCEPT

# P0 trace-context V4.3 session-retirement independent review

- Task ID: `REV-20260908-P0-TRACE-CONTEXT-V4.3-SESSION-RETIRE`
- Orchestration epoch: `E20260908-P0P1P2`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Fresh patch verdict: **REJECT**
- P0 runtime verdict: **BLOCKED / not accepted**

## Revision identity and scope

Reviewed the dirty worktree at commit `9c9e7b7c7cfdf2ef2b0100662513361c1e17a013`,
branch `3090-24g-opt`, with the coder report
`COD-20260908-P0-TRACE-CONTEXT-V4.3-SESSION-RETIRE.md` and the prior gate
`P0-TRACE-CONTEXT-V4.3.md`.

Fresh reviewed artifact identities:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`:
  `e36ec4432feec6ee8b53e8be60887408b67f22453b8d9364cb2de3aac75563a8`
- `test/registered/unit/mem_cache/test_p0_trace_context_v4.py`:
  `e8ee9c7be494699bd220f2ffeceef79dcd045659c2b553c544dc22b7458edee3`

The worktree also contains the previously reviewed V4.3 dirty changes and
unrelated vehicle/tool files. This review did not modify any reviewed source,
test, memory file, vehicle, or remote process.

## Evidence

Read-only checks from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-rev-session-retire python3 -m py_compile`
  over the eight V4.3 source/fixture files — **PASS**.
- Independent `ast.parse` over the same eight files — **PASS**.
- `python3 test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — **PASS**:
  `P0 trace-context V4.3 focused checks: PASS`.
- `git diff --check` for the implementation and untracked fixture check —
  **PASS / no diagnostics**.
- `python3 -m pytest test/registered/unit/mem_cache/test_p0_trace_context_v4.py -q` — **BLOCKED
  before collection**: `/usr/bin/python3: No module named pytest`.
- Independent AST-extracted execution of
  `_t38c_retire_session_trace` with a candidate whose `trace_context` is
  `None` — **PASS**: no `AttributeError`; the contextless candidate is
  retired.
- Independent AST-extracted boundary probe with two outstanding attempts on
  one node — **FAIL**: retiring the contextless attempt for session `s-off`
  leaves `{}` instead of preserving the other-session attempt.

## Positive checks that remain intact

The null-safe branch at `unified_radix_cache.py:747-751` no longer calls
`.get()` on `None`. The new fixture at
`test/registered/unit/mem_cache/test_p0_trace_context_v4.py:219-340` covers marker-off cleanup and
preservation of a separate node's session state. The full focused fixture also
continues to pass the prior V4.3 checks for paired release metadata, exact
tokens, marker transitions, rank/mamba fail-closed modeling, and attempt-keyed
frontier behavior in its covered cases.

The prior V4.3 topology fallback concern and inherited marker-off storage-query
compatibility concern remain open; this narrow patch did not change them.

## Findings

### F-1 — High / blocking: retirement deletes unrelated outstanding attempts on the same node

Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:747-767`.

`_candidate_session_id()` maps every candidate with `trace_context is None` to
the session currently being retired. If any such candidate is found for a
node, `retired_nodes` is populated and line 767 removes the entire
`_t38c_durability_evidence[node_id]` mapping. The candidate store is explicitly
attempt-keyed and intentionally keeps every outstanding attempt at
`unified_radix_cache.py:4624-4630`.

Independent reproduction used one node with:

- attempt A: `trace_context=None`;
- attempt B: `trace_context={"session_id": "s-live"}`;
- retirement of session `s-off`.

The resulting evidence mapping was `{}`; attempt B was lost. The focused
fixture does not catch this because its marker-off and preserved candidates
are on different nodes (`node-off` and `node-keep`).

Acceptance impact: **merge-blocking**. A session release can erase another
active session's pending attempt, suppressing its later promoted-candidate and
durability-barrier evidence and violating the prior V4.3 attempt-keyed
evidence invariant. The null-safe crash is fixed, but cleanup is not isolated
to the evidence that can be retired. Preserve unrelated attempts when
removing contextless evidence, and add a same-node mixed-attempt regression
fixture.

Fresh task recommendation: `COD-20260908-P0-TRACE-CONTEXT-V4.3-SESSION-RETIRE-V2`.

## Verdict and P0 distinction

The fresh session-retirement patch is **REJECTED** because F-1 is blocking.
The marker-off `trace_context=None` crash is fixed and isolated cleanup passes,
but the same-node boundary regression prevents acceptance of the narrow patch.

P0 runtime acceptance remains **BLOCKED** independently of this product
verdict. Keep P0 blocked until the live **S=25 RH-off** vehicle passes with
barrier-before-lookup ordering, 25/25 build evidence, exact `s00002` A-E
classification, cleanup, and runtime health. This review ran no vehicle and
no remote engine.

## Status packet

- Status: `done`
- Artifacts: this gate report only; reviewed source and fixture were not
  modified.
- Evidence: prior gate and coder report, current revision/hash capture,
  source and fixture inspection, py_compile PASS, AST PASS, focused fixture
  PASS, diff-check PASS, pytest dependency blocker, null-safe retirement probe,
  and same-node mixed-attempt regression probe.
- Followups: use the fresh task recommendation above; no extra work was
  accepted under this invocation.
- Open issues: F-1 same-node evidence deletion, prior rank-topology fallback,
  inherited marker-off query compatibility, unavailable pytest dependency,
  pre-existing dirty V4.3/vehicle scope, and required live S=25 RH-off
  vehicle evidence.
