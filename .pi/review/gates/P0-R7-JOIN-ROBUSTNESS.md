# P0 R7 join-robustness independent gate

- Task ID: `REV-20260908-P0-R7-JOIN-ROBUSTNESS`
- Orchestration epoch: `2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **REJECT**

## Scope and inputs

Read-only review of the authorized current worktree artifacts:

- `tools/p0_session_barrier_vehicle.py`
- `test/registered/unit/mem_cache/test_p0_trace_context_v4.py`
- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- current worktree diff and repository status
- `DEBUG-20260908-P0-R7-MISSING-BUILD-JOIN`
- accepted `P0-BUILD-COMPLETE-EMITTER-FIX2` gate
- the P0 build-complete architecture contract and prior emitter gates

No product, vehicle, launcher, ledger, remote, or live-run artifact was modified by
this review. The named `COD-20260908-P0-R7-JOIN-ROBUSTNESS` summary was not present
in the inspected workspace; this is recorded as a provenance gap, not treated as
evidence of correctness.

## Findings

### F-1 — High / blocking: complete malformed JSONL can still satisfy a barrier wait

Location: `tools/p0_session_barrier_vehicle.py:439-445` and `453-463`.

`EventTailer._run` correctly marks a completed malformed line with `self.error`,
but then continues reading and ingesting later lines. More importantly,
`EventTailer.wait_for` evaluates `predicate()` before checking `self.error`:

```text
while not predicate():
    if self.error:
        return False
```

Therefore a malformed complete line followed by valid evidence can make the
predicate become true and return `True` while `tailer.error` is non-null. This is
not merely theoretical; the independent reproduction wrote
`{malformed-complete}\n` followed by a valid JSON event, then called
`wait_for(lambda: len(reducer.events) == 1, 2.0)`. It observed:

```text
wait_result= True
tailer_error= invalid JSONL: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)
events= [{'evt': 'later-valid', '_vehicle_order': 1}]
```

The live build wait at `p0_session_barrier_vehicle.py:837` can consequently
return ready after a malformed trace record, allowing the vehicle to issue the
warm request despite invalid event-stream evidence. This violates the required
fail-closed behavior for complete malformed lines and can create an accepted
join from a corrupted stream.

Acceptance impact: **merge-blocking**. The tailer must remain invalid for the
whole wait once a complete malformed/non-object record is observed. The repair
must preserve the existing deadline semantics, and should either make the error
check precede predicate success or otherwise make the tailer terminal on parse
failure while preventing later records from re-establishing readiness.

### F-2 — Medium / blocking evidence gap: focused regression does not exercise the
malformed-before-success boundary

Location: `test/registered/unit/mem_cache/test_p0_trace_context_v4.py:379-414`.

The focused test verifies an unterminated fragment is buffered, valid records are
delivered in order, and a malformed record eventually sets `tailer.error`. It
appends the malformed record only after the two valid events and never asserts
that a ready predicate remains false when malformed input is followed by valid
input. The independent reproduction above demonstrates the uncovered boundary
fails. Add a deterministic regression for that sequence before re-gating.

## Requirement review

### Fragment buffering and event order — PASS for the covered path

At `p0_session_barrier_vehicle.py:423-445`, an unterminated trailing record is
retained in `pending` until a newline arrives; it is not parsed prematurely.
The focused test and an independent check confirmed that a first record written
without its newline is not ingested, then is followed by the second record in
arrival order after the newline is appended. Blank completed lines remain
ignored. The independent timeout check returned `False` at the requested
deadline (approximately 0.15 seconds for a 0.15-second wait), so no timeout
regression was observed on the covered path.

This pass does not override F-1: the complete-malformed-line failure boundary is
not fail-closed.

### Diagnostics — PASS by source inspection and focused fixture

`_t38c_build_complete_debug` at
`python/sglang/srt/mem_cache/unified_radix_cache.py:277-280` is disabled unless
`T38C_BUILD_COMPLETE_DEBUG == "1"`. It logs only a fixed guard reason through
`logger.warning`; it does not include request IDs, prompts, tokens, cache bytes,
state contents, or serialized event payloads. The focused fixture at
`test_p0_trace_context_v4.py:347-376` verified no diagnostic with the marker
absent and one reason-only diagnostic when explicitly enabled. The diagnostic
path does not call `_t38c_durable_log` or manufacture accepted evidence.

### Build/barrier guard preservation — PASS by diff and source inspection

The diagnostic calls added to the build emitter are side-effect-free logging
before existing fail-closed returns. The existing marker, insert, abort,
unfinished, TP-leader, V3-context, request-RID, node/hash, and node-context
guards remain intact at `unified_radix_cache.py:909-976`. No vehicle helper is
used to synthesize a live `build_complete`; `Reducer.record_build_complete` is a
fixture/helper surface only. No durability or residency barrier condition was
changed by the reviewed R7 surface.

### FIX2 emitter semantics — PASS

The accepted FIX2 normalization remains present at
`unified_radix_cache.py:952-956`: an integer `last_device_node` is resolved via
`tree_core.node_by_id` before hash/readback checks, while lookup failures fail
closed. The focused fixture still exercises the integer node, missing/invalid
handles, unfinished request, TP publication, warm-RID exclusion, and ordering
checks. No regression was observed in this narrow emitter review.

## Evidence executed

From `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-r7-review python3 test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — **PASS** (`P0 trace-context V4.3 focused checks: PASS`).
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-r7-review python3 -m py_compile tools/p0_session_barrier_vehicle.py test/registered/unit/mem_cache/test_p0_trace_context_v4.py python/sglang/srt/mem_cache/unified_radix_cache.py` — **PASS**.
- Independent AST parse of all three reviewed files — **PASS**.
- `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py` — **PASS**.
- `git diff --no-index --check /dev/null tools/p0_session_barrier_vehicle.py` and the equivalent focused-test check — exit status reflects untracked-file difference; no whitespace diagnostics were produced.
- Independent fragment/order/timeout check — **PASS** for the covered path.
- Independent malformed-complete-line followed by valid-event check — **FAIL**: `wait_for` returned `True` while `tailer.error` was set.
- No engine, launcher, remote, deployment, or live run was started.

## Summary

The R7 tailer correctly buffers an unterminated JSONL fragment and preserves
arrival order and deadline behavior on valid input. The marker-gated build guard
diagnostics are default-off, reason-only, and do not emit accepted evidence or
change the existing FIX2/build/barrier guards. FIX2 focused semantics remain
accepted at the narrow unit level.

However, the tailer is not fail-closed for a complete malformed line under the
required boundary condition: valid records arriving after the malformed line
can satisfy `wait_for` before its error check. This is a blocking gate failure;
no new live run is authorized by this review.

## Followups

- Repair the tailer error/terminal-state handling under a fresh implementation
  Task ID, preserving fragment buffering, event order, and timeout deadlines.
- Add the malformed-before-valid readiness regression to the focused fixture,
  then rerun this independent gate.
- Preserve the current no-live-run decision until the corrected gate is accepted.

## Open issues

1. F-1: complete malformed JSONL can be followed by a successful barrier wait.
2. F-2: the focused fixture lacks the failing boundary regression.
3. The named R7 coder summary was not found in the inspected memory/workspace
   paths, leaving task provenance incomplete.
4. Live runtime/vehicle acceptance remains outstanding; prior R7 evidence is
   `NOT_VERIFIED`.

