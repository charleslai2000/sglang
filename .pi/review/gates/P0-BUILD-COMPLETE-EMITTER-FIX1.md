ENTRY: ACCEPT

# P0 durable V3 `build_complete` emitter FIX1 independent gate review

- Task ID: `REV-20260908-P0-BUILD-COMPLETE-EMITTER-FIX1`
- Orchestration epoch: `2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **ACCEPT**

## Scope and authoritative inputs

Read-only review of:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `test/registered/unit/mem_cache/test_p0_trace_context_v4.py`
- `tools/p0_session_barrier_vehicle.py`
- `python/sglang/srt/mem_cache/trace_context.py`
- `ARCH-20260908-P0-BUILD-COMPLETE-CONTRACT.md`
- `COD-20260908-P0-BUILD-COMPLETE-EMITTER-FIX1.md`
- prior `review/gates/P0-BUILD-COMPLETE-EMITTER.md`

No product, vehicle, launcher, ledger, or prior gate artifact was modified by
this review. No repository-root `AGENTS.md` exists; the supplied orchestration
instructions were followed. The nearest `docs/AGENTS.md` is documentation-only
and does not govern the reviewed Python product files.

## Previous blocking findings

Both blockers from the prior REJECT gate are closed:

1. `_t38c_record_node_context` now scans all existing bindings for the node and
   permanently sets the node-only index to `None` on a conflicting or already
   ambiguous binding. It does not replace the authoritative index with the
   later context.
2. The focused fixture now invokes `_t38c_emit_build_complete` with
   `finished_reason=None` and asserts zero records.

## Requirement review

### Exact producer boundary — PASS

`cache_finished_req` calls the emitter only after `insert` returned a result,
`result.last_device_node` is present, `req.last_node` is assigned, and
`_t38c_record_node_context` has run (`unified_radix_cache.py:1875-1883`). The
call is before component cleanup and session-reference registration. Static
review also confirms `cache_unfinished_req` contains no emitter call.

### Marker, V3, and identity fields — PASS

The helper is marker-gated, requires a complete `p0_durable.v3` context, and
uses `_t38c_durable_log` rather than creating a second envelope. The event
supplies `build_complete`, `session_id`, non-null generation, `build_rid`,
`warm_rid=None`, `node_id`, non-empty `final_kv_hash`, null storage operation
and attempt IDs, and `result=True`. The logger promotes the record to the
existing V3 envelope and preserves run/event/rank/timestamp fields. Marker-off
behavior remains no event and no emitter state.

### RID, node, and hash equality — PASS

The request RID must be present and equal the preserved context `build_rid`.
The finalized result node must be non-root, have a non-empty string ID and
non-empty string final hash, and its node-context readback must exactly equal
the request context. The FIX1 conflict logic now makes ambiguous readback
return `None`, so a conflicting node cannot publish.

### Warm, abort, and unfinished exclusion — PASS

The helper rejects non-inserts, explicit aborts, missing/unfinished
`finished_reason`, missing result/node/hash/context, and warm RID mismatches.
The fixture covers warm and abort/non-insert paths and now covers the explicit
`finished_reason=None` path. The production unfinished path does not call the
emitter.

### TP leader semantics — PASS

TP=1 publishes. For TP>1, publication requires initialized distributed state
and `torch.distributed.get_rank(group=self.tp_group) == 0`; missing/ambiguous
group state and non-leaders fail closed. There is no global-rank fallback.
The focused fixture covers leader, non-leader, uninitialized, and missing-group
cases.

### Duplicate, reopen, and ordering — PASS

Repeated exact identities are emitted as exact duplicates, which the contract
allows the consumer to reduce idempotently. A changed RID or generation is not
accepted as the previous build; the fixture covers warm RID exclusion and
session-generation/RID separation. The emitter follows node-context binding
and precedes accepted later persistence/barrier evidence in the lifecycle.

### Scope and compatibility — PASS with attribution caveat

The FIX1 coder manifest names only the authorized implementation and focused
fixture. The current checkout remains dirty with unrelated earlier Phase-2
product/vehicle/fixture changes and has no task-specific commit boundary, so
the aggregate worktree cannot independently attribute every changed line to
FIX1. No unauthorized file was changed by this review, and the reviewed FIX1
surface is limited to the requested two files.

## Independent evidence

Executed read-only from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- Independent AST-extracted conflict probe: **PASS**. After binding one node
  to `s1/r1` and then attempting `s2/r2`, the node index was `None`, node
  readback was `None`, and invoking the extracted emitter produced zero
  records.
- `python3 test/registered/unit/mem_cache/test_p0_trace_context_v4.py`: **PASS** —
  `P0 trace-context V4.3 focused checks: PASS`.
- `PYTHONPYCACHEPREFIX=/tmp/codex-pycache-review-build-complete-fix1 python3
  -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py
  test/registered/unit/mem_cache/test_p0_trace_context_v4.py`: **PASS**.
- AST parse of the implementation and fixture: **PASS**.
- Static producer-boundary and unfinished-path assertions: **PASS**.
- `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py`:
  **PASS**. The fixture is untracked; an independent
  `git diff --no-index --check /dev/null test/registered/unit/mem_cache/test_p0_trace_context_v4.py`
  returned the expected status 1 for a file difference with zero whitespace
  diagnostics.
- No engine, pytest, launcher, remote, deployment, or live S=25 run was
  performed. Those are outside this unit emitter gate and remain separate
  acceptance work.

## Findings

No blocking or non-blocking findings identified for this FIX1 gate.

## Verdict

`done`; gate **ACCEPT**. The two prior blocking findings are repaired and the
minimal V3 emitter satisfies the reviewed contract. This verdict accepts the
unit-level emitter gate only; it does not claim live S=25 RH-off vehicle
acceptance or launcher activation.

## Followups

- Dispatch the separately authorized launcher/configuration verification.
- Run the fresh live S=25 RH-off vehicle and perform its independent runtime
  gate review.

## Open issues

1. Live runtime/vehicle acceptance remains outstanding.
2. The dirty worktree has no task-specific commit boundary; aggregate diff
   attribution remains a process caveat.
3. The prior V4.3 rank-topology fallback concern remains a separate existing
   issue and is not widened or resolved by this emitter gate.
