ENTRY: ACCEPT

STATUS: done

# P0 residency-barrier node-sidecar FIX1 independent gate

- Task ID: `REV-20260908-P0-RESIDENCY-BARRIER-NODE-SIDECAR-FIX1`
- Orchestration epoch: `phase2-hicache-design/2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: **ACCEPT**

## Scope and independence

Reviewed the authorized product file and focused fixture directly, the coder
report, debugger diagnosis, authoritative build-complete contract, and
accepted FIX5/FIX6 gates. Review was limited to:

- `python/sglang/srt/mem_cache/unified_radix_cache.py`
- `3090-dev/test_p0_residency_barrier_emitter.py`

The aggregate `3090-24g-opt` worktree is dirty and has no task-specific commit
boundary. Attribution is therefore path- and behavior-scoped; unrelated dirty
files were not accepted by this gate. No product source or test was modified.
No SSH, remote, live, vehicle, or telemetry-as-runtime-evidence action was
performed.

## Verdict summary

ACCEPT. `_t38c_record_node_context` now enriches every recorded node and each
visited parent with that node's own string ID and final KV hash. The resulting
sidecar carries the existing run/session/generation/build context and
`warm_rid=None`; `_t38c_residency_identity` remains strict and unchanged.
Conflict and ambiguity leave the node index unresolved (`None`) instead of
selecting a last writer. The generated sidecar was independently joined to
build emission, detach/completion registration, and residency publication.

## Requirement assessment

| Requirement | Result | Evidence |
|---|---|---|
| Exact six-field strict identity with `warm_rid=None` | PASS | Source `unified_radix_cache.py:1397-1446` copies request context and adds `node_id`/`final_kv_hash`; strict helper at `:146-181` requires run/session/generation/build/node/hash and rejects non-null warm RID. Fixture assertions at `test_p0_residency_barrier_emitter.py:641-707`. |
| Parent contexts bind each parent’s own hash | PASS | The recorder walks `node.parent` and recomputes `node.id` plus `get_last_hash_value()` per node (`unified_radix_cache.py:1408-1420`); fixture checks distinct leaf/parent hashes at `:682-694`. |
| Conflict/ambiguity fail-closed; no last-write-wins | PASS | Existing same-node contexts are compared before index selection (`:1421-1445`); conflict sets index to `None`. Fixture checks conflict rejection and preserved original context at `:720-758`; independent same-generation/different-build probe also left the index unresolved. |
| Build, durability, detach/completion, and residency paths join identity | PASS | Build registration consumes the node sidecar (`:1689-1724`); detach uses it (`:332-355`), durability uses it before readiness/barrier (`:5692-5703`), and barrier revalidates the strict identity (`:545-579`). Independent generated-sidecar join probe passed for build, detach, exact completions, and one barrier payload. |
| Regression coverage and no queue/vehicle/admission relaxation | PASS | Focused fixture retains FIX3/FIX5/FIX6 cases and adds leaf/parent/mismatch/ambiguity checks. The sidecar change is confined to context binding; accepted queue predicates and marker-gated barrier behavior remain intact. Focused test passed all named cases. |
| Reproducible focused/V4.3/compile/AST/diff evidence | PASS | Independent commands below passed. No live claim is made. |

## Independent evidence

Run from `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `python3 3090-dev/test_p0_residency_barrier_emitter.py` — **PASS**; leaf/parent sidecar, no-last-write-wins, FIX3/FIX5/FIX6 negative cases, real TP=1 scheduler checkpoint, and focused completion all passed.
- `python3 3090-dev/test_p0_trace_context_v4.py` — **PASS**.
- `PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-fix1-review-pycache python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_residency_barrier_emitter.py` — **PASS**.
- Independent `ast.parse` of both authorized Python files — **PASS**.
- `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py` — **PASS**.
- Direct trailing-whitespace check of the untracked focused fixture — **PASS**.
- Independent generated-sidecar identity join probe — **PASS**: the same generated leaf sidecar drove build-complete registration, KV/Mamba detach tokens, exact completion, and one residency barrier with `(run_id, session_id, session_generation, build_rid, node_id, final_kv_hash) = (run-join, session-join, 7, build-join, leaf, hash-leaf)`.
- Independent malformed-node probe — observed `KeyError` from `node_by_id` in the recorder; this is recorded below as a non-blocking hardening finding, not a valid-path failure.

## Findings

### P2 — recorder lookup is not exception-guarded

- Location: `python/sglang/srt/mem_cache/unified_radix_cache.py:1408`.
- Evidence: an extracted execution of `_t38c_record_node_context` with a
  missing node ID raises `KeyError` from `self.tree_core.node_by_id(node_id)`.
- Impact: if a stale/deleted result ID reaches this post-insert bookkeeping
  path, request completion can raise instead of returning fail-closed with no
  identity evidence. The authorized valid production callers return live node
  IDs, and no such failure occurred in the focused or scheduler-surface
  probes; this does not block this narrow gate.
- Recommended follow-up: catch the tree lookup’s expected stale/missing-node
  exceptions and return before mutating the sidecar/session maps. Requires a
  fresh Task ID; no repair was made in this review.

No blocking findings. Questions: none.

## Followups and open issues

- Obtain the separately required fresh marked live S=25 RH-off evidence; this
  gate does not accept telemetry or local fixtures as runtime evidence.
- Preserve path-level attribution before merge/release because the aggregate
  worktree has unrelated dirty changes.
- The P2 lookup-hardening observation remains open under a future Task ID.

## Status packet

- Status: `done`
- Artifacts: this gate and the designated memory report
  `.memory/phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-NODE-SIDECAR-FIX1.md`.
- Evidence: direct source/test review, authoritative contract and prior gate
  review, focused/V4.3/static checks, conflict probes, malformed-node probe,
  and generated-sidecar identity join probe.
- Summary: **ACCEPT FIX1** for the narrow node-sidecar identity gate; strict
  six-field identity and fail-closed ambiguity are preserved.
- Followups: separate live/remote task and optional P2 lookup hardening under
  a fresh Task ID.
- Open issues: no blocking implementation issue; no live claim; no
  task-specific commit boundary; P2 lookup hardening remains open.
