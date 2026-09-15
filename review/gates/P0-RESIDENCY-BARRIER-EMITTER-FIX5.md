STATUS: done

# P0 residency-barrier emitter FIX5 independent gate review

- Task ID: `REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX5`
- Orchestration epoch: `phase2-hicache-design / 2026-09-08`
- Role: `reviewer`
- Invocation status: `done`
- Admission: `ACCEPT`
- Gate verdict: `ACCEPT`

## Scope and independence

Reviewed the authorized `unified_radix_cache.py` product file and focused
fixture directly, the FIX5 implementation report, rejected FIX4 gate/report,
accepted FIX3 gate, and authoritative build-complete contract. The aggregate
worktree is dirty and has no task-specific commit boundary; attribution is
limited to the authorized product/test paths and the FIX5 queue-barrier
change. No product/test file or remote host was modified. No remote/live claim
is made.

## Verdict summary

ACCEPT. FIX5 closes the FIX4 B1 blocker. The strict residency fold now requires
the owning controller's primary KV release queue and every owning extra host
release queue to be empty while holding `_t38c_release_handoff_lock`, before
the barrier log call. Present-controller missing lock/queue/map surfaces return
without publication. The cache-owned residency `RLock` remains the outer lock,
and completion-triggered re-entry remains intact and reentrant.

## Requirement assessment

| Requirement | Result | Evidence |
|---|---|---|
| Non-empty primary or extra owning release queue fails closed | PASS | Direct source review at `unified_radix_cache.py:441-488`; independent primary and extra queue probes produced no event while queued. |
| No-next-request trigger, drain ordering, exact-one publication, repeat idempotence | PASS | Focused fixture passed; independent primary/extra probes verified drain + final exact completion publishes once and repeated completion/poll stays once. |
| Six-field identity, cache-owned `RLock`, F-1/F-2/F-3/F-4 and strict predicates | PASS | Structural audit verified six-field identity and lock/queue ordering; focused fixture passed F-1/F-2/F-3/F-4, recycle, cross-cache, stale generation, live-value, durability, root, and forced-miss cases. |
| Ownership-safe queue inspection, absent surfaces, race/deadlock behavior | PASS | Present-controller missing lock/primary/extra map/value probes returned without publication; absent controller was handled without exception as the no-queue-owner path. Queue enqueue/pop uses the same handoff lock in `hybrid_cache_controller.py:408-420,500-505`; 100 completion/poll races passed without deadlock or duplicate publication. |
| Focused/V4.3/static/whitespace/adversarial evidence | PASS | Focused emitter and V4.3 tests, `py_compile`, AST parse, product/untracked whitespace checks, structural audit, queue probes, and corrected lock-race probes passed. |
| No remote/live claim | PASS | All execution was local; no remote, engine, vehicle, launcher, or live S=25 run was performed. |

## FIX4 blocker closure

FIX4 B1 was a fail-open completion fold: after all keyed completions, a
non-empty host release queue could still produce `cold_residency=true`. FIX5
adds the missing predicate at `unified_radix_cache.py:456-476` and keeps the
logger call at `:477-488` inside the handoff lock. The focused fixture covers
both `host_mem_release_queue` and `extra_host_mem_release_queues`; independent
probes additionally exercised final completion after drain.

## Independently executed evidence

From `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`:

- `python3 3090-dev/test_p0_residency_barrier_emitter.py` — PASS.
- `python3 3090-dev/test_p0_trace_context_v4.py` — PASS.
- `PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-fix5-pycache python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_residency_barrier_emitter.py` — PASS.
- AST parse of both authorized Python files — PASS.
- `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py` — PASS.
- `git diff --no-index --check /dev/null 3090-dev/test_p0_residency_barrier_emitter.py` — expected status 1 for the untracked fixture, with no whitespace diagnostics.
- Independent primary and extra queue probes — PASS: non-empty queue suppressed publication; after drain plus final exact completion, exactly one event was emitted; repeats remained one.
- Absent-controller and missing queue/lock/map/value probes — PASS for safe handling; present-controller missing surfaces failed closed.
- 100 repeated completion/poll `RLock` race iterations — PASS with no deadlock, exception, or duplicate event.
- Structural audit — PASS for six-field identity, cache-owned lock, handoff-lock queue inspection, and logger ordering.

## Followups

- Live/remote S=25 residency, warm, and restore evidence remains a separate
  operational/test task and is not accepted by this local implementation gate.
- Preserve an explicit task boundary before any broader merge/release decision
  because the aggregate worktree contains unrelated dirty changes.

## Open issues

- No blocking implementation issue remains for FIX5.
- Live/remote behavior remains unverified; this is intentionally not a gate
  rejection or a live claim.

## Status packet

- Status: `done`
- Artifacts: this gate and
  `.memory/phase2-hicache-design/work/REV-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX5.md`.
- Evidence: direct source/diff review, FIX3/FIX4/contract review, focused and
  static checks, independent queue-boundary probes, and lock-race probes.
- Summary: **ACCEPT FIX5**; the FIX4 non-empty primary/extra release-queue
  publication blocker is closed without a detected regression in the scoped
  local checks.
- Followups: separate live/remote task; retain dirty-worktree attribution.
- Open issues: no live claim; no task-specific commit boundary.
