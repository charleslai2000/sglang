ENTRY: ACCEPT

# P0 residency-barrier emitter FIX3 independent gate review

- Task ID: `REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX3`
- Orchestration epoch: `phase2-hicache-design / 2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: `ACCEPT`

## Scope and independence

Reviewed the authorized product file and focused fixture directly, the FIX3
implementation report, the rejected FIX2 gate/report, and the authoritative
build-complete contract. The worktree is dirty and has no task-specific commit
boundary; the FIX3 report attributes the scoped implementation to the two
authorized files. This review did not attribute unrelated aggregate changes to
FIX3.

No product/test file, vehicle, launcher, remote host, or live environment was
modified. Only this gate and the authorized review report were written. No
remote or live claim is made.

## Verdict summary

ACCEPT. FIX3 closes both blocking FIX2 findings. The residency identity helper
now rejects absent/incomplete V3 context and returns exactly
`(run_id, session_id, session_generation, build_rid, node_id, final_kv_hash)`.
That identity is used for cache-owned detached/completed/barrier state,
build/durability readiness, publication deduplication, polling, and retirement.
The release token lifecycle carries the run boundary and is checked against the
owning cache before completion.

The focused fixture independently exercises the run-ID collision boundary and
direct residency-fold absence/mutation behavior for `None`, absent context,
every missing V3 field, and node-context mismatch. Existing F-1/F-2 and strict
producer-predicate probes remain passing.

## Requirement assessment

| Requirement | Result | Evidence |
|---|---|---|
| Exact six-field identity through residency state, lifecycle, dedup/publication, retirement, and event | PASS | `unified_radix_cache.py:146-180, 332-456, 1041-1067`; identity is the key for detached/readiness/barrier state and `identity[0]` is published as `run_id`. Lifecycle registration includes the run ID and context. |
| Different run IDs cannot collide/join; invalid run ID fails closed | PASS | Product validation at `:159-171`; focused F-3 probe at `test_p0_residency_barrier_emitter.py:337-352`; independent probe changed only run ID and separately tested `None`, empty, whitespace, integer, list, and dict values. Cross-run token presented to the wrong cache did not complete that cache's lifecycle. |
| Missing/absent context, each missing V3 field, node mismatch: no event/no ledger mutation | PASS | Focused direct fold cases at `:354-379`; all named cases passed. The helper returns before ledger mutation at `unified_radix_cache.py:332-343, 393-418`. |
| F-1/F-2 recycle, cache ownership, same-node isolation, concurrent protections | PASS | Focused fixture `:201-312`; repeated recycle remained one publication, cross-cache token was rejected, and concurrent release/poll produced one publication. The product lock encloses registration, completion, fold, reset, and retirement. |
| Strict producer predicates and at-most-one exact barrier | PASS | Product fold `:393-456` requires build identity, durability readiness, device detach, no live FULL/Mamba values, all expected completions, non-root/non-tombstone node, and successful logger publication before marking the identity published. Queue drains call the completion path and the final poll (`:2535-2590`, `:5490-5494`). |
| Focused/static evidence | PASS | Focused emitter, V4.3 fixture, `py_compile`, AST parse, tracked whitespace check, and untracked no-index whitespace check all passed. |
| Remote/live claim | PASS | None made; live/remote execution was not performed. |

## Blocking findings

None.

## Evidence executed independently

From `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `python3 test/registered/unit/mem_cache/test_p0_residency_barrier_emitter.py` — PASS, including
  named F-3 and F-4 output for all cases.
- `python3 test/registered/unit/mem_cache/test_p0_trace_context_v4.py` — PASS.
- `PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-fix3-review-pycache python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py test/registered/unit/mem_cache/test_p0_residency_barrier_emitter.py` — PASS.
- AST parse of both authorized files — PASS.
- `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py` — PASS.
- `git diff --no-index --check /dev/null test/registered/unit/mem_cache/test_p0_residency_barrier_emitter.py` — expected status 1 for an untracked file, with no whitespace diagnostics.
- Independent run-ID fail-closed probe — PASS for missing, empty,
  whitespace-only, and non-string values.
- Independent cross-run token ownership probe — PASS; a token from `run-a`
  did not complete or join the `run-b` cache ledger.
- No pytest, engine, launcher, vehicle, remote, or live S=25 run was performed.

## Followups

- A separate authorized operational/test task is required for launcher
  activation and fresh live P0 residency evidence.
- The aggregate dirty worktree should retain an explicit task boundary before
  any broader merge/release decision.

## Open issues

1. Live/remote residency, warm, and restore behavior remains unverified by
   this unit gate.
2. The worktree has pre-existing aggregate modifications without a
   task-specific commit boundary; attribution relies on the supplied FIX3
   report and scoped source/test review.

## Status packet

- Status: `done`
- Artifacts: this gate and
  `.memory/phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX3.md`.
- Evidence: direct source review, FIX2/contract review, focused and V4.3
  checks, static checks, and independent adversarial probes.
- Summary: ACCEPT FIX3 for the local residency-emitter implementation gate;
  both FIX2 blockers are closed and no blocking finding remains.
- Followups: separate live/remote task; preserve dirty-worktree attribution.
- Open issues: no live claim; no task-specific commit boundary.
