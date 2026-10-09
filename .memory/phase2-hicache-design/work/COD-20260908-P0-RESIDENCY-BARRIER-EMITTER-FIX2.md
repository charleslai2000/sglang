STATUS: done

Changed files:

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py`

`mamba_component.py` was not changed. Vehicle, fixture, ledger, gate reports,
remote host, and unrelated files were not modified by this task.

Root cause closed:

- F-1: the residency ledger is now keyed by the full logical identity
  `(session_id, session_generation, build_rid, node_id, final_kv_hash)`, and
  publication deduplicates on that identity rather than the physical expected
  token set. A later recycle with new detach tokens is suppressed after the
  first successful event.
- F-2: detached, completed, and published state now belongs to each
  `UnifiedRadixCache` instance and is protected by its `_t38c_residency_lock`.
  Registration, completion, poll, publication, reset, and session retirement
  use that ownership boundary. A completion token not present in the current
  cache ledger is ignored and is not completed or retired, so same-node tokens
  from another cache cannot join the fold.
- Pending identities remain separate across generations; polling requires the
  current node context to match the pending identity. Session/full reset retires
  only tokens owned by that cache.

Focused test additions:

- repeated recycle with a distinct token set;
- same numeric node ID across two cache instances and cross-cache token use;
- concurrent completion/poll handoff;
- stale generation;
- partial, host-only, missing durability, ambiguous/warm, forced-miss, and
  marker-off fail-closed cases;
- existing nominal post-queue retry and exact payload assertions.

Verification evidence:

- `python3 3090-dev/test_p0_residency_barrier_emitter.py` — PASS.
- `python3 3090-dev/test_p0_trace_context_v4.py` — PASS:
  `P0 trace-context V4.3 focused checks: PASS`.
- `PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-fix2-pycache python3 -m py_compile`
  over both authorized product files and the focused test — PASS.
- `ast.parse` over both authorized product files and the focused test — PASS.
- tracked authorized-path `git diff --check` — PASS; the untracked focused
  test no-index check returned the expected status 1 with no diagnostics.
- No pytest, engine, remote, launcher, vehicle, or live run was performed.

Next fresh review conditions:

- Independent reviewer must inspect the exact diff and confirm that the
  cache-owned lock covers every detach/completion/poll/publication/retirement
  mutation, that logical-identity deduplication survives repeated recycle, and
  that the legacy AST compatibility branch is unreachable for real cache
  instances.
- Reviewer should rerun both focused suites plus independent multi-cache,
  repeated-token, stale-generation, and concurrent poll/release probes before
  any remote live acceptance task.

Open issues:

- No remote runtime residency evidence is claimed; that remains outside this
  coder task and requires a fresh accepted review first.
