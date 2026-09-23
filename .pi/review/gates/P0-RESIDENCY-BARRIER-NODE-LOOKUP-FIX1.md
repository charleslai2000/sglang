ENTRY: ACCEPT

STATUS: done

# P0 residency-barrier typed NodeId lookup FIX1 independent gate

- Task ID: REV-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1
- Orchestration epoch: phase2-hicache-design/2026-09-08
- Role: reviewer
- Invocation status: done
- Admission: ACCEPT
- Gate verdict: ACCEPT for the narrow implementation gate

## Scope and independence

Reviewed directly:

- python/sglang/srt/mem_cache/unified_radix_cache.py
- test/registered/unit/mem_cache/test_p0_residency_barrier_emitter.py

Inputs included the coder report
COD-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1.md, the ledger's r16
evidence summary, the prior node-sidecar FIX1 gate/report, and the prior
debugger diagnosis. The product checkout is an aggregate dirty worktree with
no task-specific commit boundary; attribution is therefore path- and
behavior-scoped. No product source or test was modified. No SSH, remote,
live, vehicle, or telemetry-as-runtime-evidence action was performed.

## Gate contract

Acceptance requires all of the following:

1. The strict residency lookup resolves the actual TreeCore NodeId (int)
   and its canonical decimal serialization without changing the six-field
   identity representation.
2. The resolved node's ID is checked; missing, wrong-node, and distinct
   integer/string alias resolutions fail closed.
3. The change does not relax queue, barrier, predicate, deduplication,
   scheduler, vehicle, or Ready Horizon behavior.
4. Existing parent/hash and six-field identity checks remain authoritative.
5. Focused, V4.3, compile, AST, and diff/whitespace evidence is reproducible.
6. The focused regression exercises the r16 typed-lookup failure and cannot
   publish through a wrong-node join.

## Requirement assessment

| Requirement | Result | Evidence |
|---|---|---|
| Actual typed NodeId and canonical string resolve | PASS | NodeId = int in unified_tree_core_interface.py:15-17; TreeCore resolves the arena with node_by_id at unified_tree_core.py:529-534; _t38c_residency_node_lookup tries the original ID and only an exactly canonical decimal string conversion at unified_radix_cache.py:494-518. |
| Resolved ID/hash and fail-closed lookup | PASS | The lookup validates str(node.id) against the serialized ID and rejects missing, wrong, and ambiguous candidates. The barrier then reads get_last_hash_value() and re-runs strict identity/hash validation at unified_radix_cache.py:536-573. Focused assertions are at test_p0_residency_barrier_emitter.py:762-805; the additional matrix also covered bool/noncanonical input. |
| No lifecycle or admission relaxation | PASS | The helper is used only at the existing barrier lookup boundary (unified_radix_cache.py:536); the existing queue snapshot/queue-nonempty guard, token-completion guard, publication deduplication, and poll retry remain in the same barrier path (:604-757, :773-788). No scheduler, vehicle, or RH code was changed by this task. |
| Parent/hash and six-field identity invariants | PASS | Existing strict identity still requires schema, run, session, generation, build, null warm RID, node, and final hash (unified_radix_cache.py:146-181). The focused fixture retains leaf/parent own-ID/hash assertions and no-last-write-wins checks at test_p0_residency_barrier_emitter.py:642-759. |
| Reproducible static/focused evidence | PASS | Independent focused, V4.3, py_compile, AST, product diff-check, and untracked-test whitespace checks all passed. |
| r16 regression and wrong-node join | PASS | The focused lookup case resolves int/string forms, rejects missing/wrong/ambiguous alias results, and the full fixture's strict fold tests preserve no-publication behavior for invalid identity and existing fail-closed predicates. The old r16 failure mode (serialized string sent to int-keyed TreeCore lookup) is directly covered by the "41" against {41: node} assertion. |

## Independent evidence

Run from /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt:

- python3 test/registered/unit/mem_cache/test_p0_residency_barrier_emitter.py — PASS; exact
  NodeId/string lookup, missing/wrong/ambiguous cases, six-field sidecars,
  queue guards, completion triggers, deduplication, invalid identity cases,
  and the TP=1 scheduler checkpoint passed.
- python3 test/registered/unit/mem_cache/test_p0_trace_context_v4.py — PASS.
- PYTHONPYCACHEPREFIX=<temporary> python3 -m py_compile
  python/sglang/srt/mem_cache/unified_radix_cache.py
  test/registered/unit/mem_cache/test_p0_residency_barrier_emitter.py — PASS.
- Independent ast.parse of both authorized files — PASS.
- git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py —
  PASS.
- git diff --no-index --check /dev/null
  test/registered/unit/mem_cache/test_p0_residency_barrier_emitter.py — expected status 1 for
  the untracked file and no whitespace diagnostics — PASS.
- Additional extracted-helper matrix — PASS for int, canonical decimal
  string, bool rejection, noncanonical decimal rejection, missing, wrong
  node, distinct int/string objects, and one object returned through both
  aliases.
- Source inspection independently confirmed the TreeCore NodeId type and
  dictionary lookup contract. No live claim is made.

## Findings

No blocking findings. No questions.

The prior non-blocking P2 observation remains outside this gate: the
node-sidecar recorder at unified_radix_cache.py:1423 still directly resolves
its production node handle and is not the strict residency-fold lookup helper
reviewed here. Any additional stale-recorder hardening requires a fresh Task
ID; no repair was made in this review.

## Followups and open issues

- Run the separately authorized fresh live S=25 RH-off vehicle task after this
  gate; this gate does not accept r16 or any local fixture as runtime PASS.
- Preserve path-level attribution before merge/release because the aggregate
  worktree contains unrelated dirty changes and untracked files.
- No live deployment approval is implied beyond acceptance of this narrow
  implementation gate.

## Status packet

- Status: done
- Artifacts: this gate and the designated memory review report
  .memory/phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-NODE-LOOKUP-FIX1.md.
- Evidence: direct source/test review, r16 ledger summary, prior debugger and
  node-sidecar gate review, focused/V4.3/static checks, and an independent
  typed-lookup matrix.
- Summary: ACCEPT FIX1 for the strict typed NodeId lookup boundary;
  wrong-node and ambiguity joins fail closed and existing identity/lifecycle
  gates remain intact.
- Followups: fresh live evidence under its own task; optional recorder stale
  lookup hardening under a fresh Task ID.
- Open issues: no blocking implementation issue; no live claim; no
  task-specific commit boundary; prior recorder P2 remains outside scope.
