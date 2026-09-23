ENTRY: ACCEPT

# P0 finished zero-key guard FIX1 independent gate review

- Task ID: `REV-20260908-P0-FINISHED-ZERO-KEY-GUARD-FIX1`
- Orchestration epoch: `2026-09-08-P0`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **ACCEPT**

## Scope and authoritative inputs

Read-only review of:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `test/registered/unit/mem_cache/test_p0_trace_context_v4.py`
- prior `P0-FINISHED-ZERO-KEY-GUARD.md` gate and report
- `ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`
- `COD-20260908-P0-FINISHED-ZERO-KEY-GUARD-FIX1.md`
- accepted `P0-BUILD-COMPLETE-EMITTER-FIX1.md`,
  `P0-BUILD-COMPLETE-EMITTER-FIX2.md`, and
  `P0-R7-JOIN-ROBUSTNESS-FIX5.md`

The target checkout has no repository-root `AGENTS.md`; the supplied
orchestration contract was followed. No product or fixture file was modified
by this review. Only this authorized gate artifact and the authorized memory
report were written.

## Previous blocker closure

The prior gate's false-session-reference finding is closed. At
`unified_radix_cache.py:968-1034`, `_t38c_finished_boundary_result` now
returns a non-empty `InsertResult` only after all of these checks succeed:

- finished and not abort;
- complete `p0_durable.v3` request context;
- non-empty session/build identity, non-null generation, no warm RID, and
  request RID equal to the build RID;
- exactly one recorded boundary for the same node/request/context;
- current node resolves, is non-root/not a tombstone, and has live FULL and
  MAMBA values;
- current final hash is a non-empty `str` matching the recorded hash; and
- current node sidecar is exactly equal to the request context.

The caller at `unified_radix_cache.py:2087-2103` uses that same
`event_result` for build emission and session-ref registration. Consequently,
an ambiguous sidecar or invalid hash cannot produce either a build event or a
session reference.

## Requirement review

- Valid prior-boundary reuse: **PASS**. It returns the validated node result,
  emits one build event through the existing emitter, and reaches the existing
  session-ref path.
- Ambiguous/missing sidecar: **PASS**. The helper returns `None`; no event or
  session ref is produced.
- Non-string/empty/mismatched current hash: **PASS**. The helper returns
  `None`; no event or session ref is produced.
- V3/RID/session/generation/warm constraints: **PASS**. Missing or mismatched
  context, missing generation, warm RID, or request/build RID mismatch fails
  closed.
- Abort, unfinished, missing boundary, missing last node, root, tombstone, and
  missing live component cases: **PASS**. They do not reach event emission or
  registration.
- Zero-key behavior: **PASS**. The `effective_cache_len <= 0` branch frees the
  request tail, performs no radix `insert`, preserves `result=None` for
  component cleanup, and only uses a fully validated prior boundary as
  `event_result`.
- Compatibility/security: **PASS** for this scope. The repair is marker-gated,
  uses the existing V3 emitter/context path, does not synthesize a root or
  storage identity, and introduces no remote or external behavior.

## Independent evidence

From `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-review-zero-key-fix1 python3
  test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — **PASS** (`P0 trace-context V4.3
  focused checks: PASS`).
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-review-zero-key-fix1 python3 -m
  py_compile python/sglang/srt/mem_cache/unified_radix_cache.py
  test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — **PASS**.
- Independent AST-extracted helper plus production caller-registration probe —
  **PASS**. Valid reuse produced `(event_result, session_ref) == (True, True)`;
  ambiguous sidecar, non-string hash, hash mismatch, invalid V3/context,
  warm RID, abort, unfinished, no-boundary, and missing-node cases all
  produced `(False, False)`.
- Focused fixture source checks confirm the zero branch precedes all insert
  calls and contains no insert call, and exercise valid reuse plus the
  ambiguous-sidecar/non-string-hash/abort/unfinished/no-boundary cases.
- `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py` —
  **PASS**.
- `git diff --no-index --check /dev/null
  test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — expected status 1 for the untracked
  file comparison, with no whitespace diagnostics.
- No engine, launcher, remote, deployment, or live run was performed, as
  prohibited by this dispatch.

## Findings

No blocking or non-blocking implementation findings identified for FIX1.

## Verdict

`done`; gate **ACCEPT** for the zero-key guard FIX1 unit scope. The prior
false-session-reference blocker is independently closed. This is not live
runtime or remote vehicle acceptance.

## Followups

- Preserve the no-remote/no-live-run boundary for this unit gate.
- Any live/runtime acceptance remains a separate authorized task.

## Open issues

1. Live/runtime acceptance is outside this invocation and remains outstanding.
2. The aggregate checkout is dirty and has no task-specific revision boundary,
   so broad diff attribution remains a process caveat.
