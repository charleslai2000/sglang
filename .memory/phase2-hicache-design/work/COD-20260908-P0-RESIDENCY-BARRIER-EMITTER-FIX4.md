STATUS: done

# COD-20260908-P0-RESIDENCY-BARRIER-EMITTER-FIX4

## Changed files

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
  - Added the product-owned retry trigger in `_t38c_note_completion`.
  - After cache ownership validation, exact keyed completion, and token retirement, the existing strict `_t38c_residency_barrier` fold is re-entered with the exact six-field identity and expected-identity guard.
  - The existing cache-owned `threading.RLock` makes the re-entry safe. No module-global polling, client request, vehicle event, cross-cache join, or predicate relaxation was added.
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_p0_residency_barrier_emitter.py`
  - Added a deterministic no-next-request probe: the first two of three keyed tokens do not publish; the final token publishes exactly one barrier; repeated completion and a later poll remain at one.
  - Retained the FIX3 F-1/F-2/F-3/F-4, strict predicate, marker-off, and concurrency probes.
- This report.

## Root cause

FIX3 retried the strict fold only at the end of storage-control draining. In r13,
the final exact KV/Mamba release completed after that product-owned drain, so the
cache had complete detach/free evidence but no later trigger. The vehicle then
waited without issuing a new request or causing another queue drain.

## Implemented semantics

The completion hook invokes the already accepted strict fold only after the keyed
completion has been accepted for the owning cache. The fold still requires the
FIX3 six-field identity `(run_id, session_id, session_generation, build_rid,
node_id, final_kv_hash)`, build identity, durability readiness, expected device
detach, all expected keyed completions, exact node identity/hash, non-root and
non-tombstone status, no live FULL/Mamba values, successful event publication,
and the existing identity-level at-most-once set update. An incomplete token set
therefore remains fail-closed.

## Verification evidence

Executed locally in `sglang-3090-24g-opt`:

- `python3 3090-dev/test_p0_residency_barrier_emitter.py` — PASS, including:
  `No-next-request final-token trigger: PASS`, F-3 run-ID collision, all F-4
  invalid-context cases, and the final focused PASS line.
- `python3 3090-dev/test_p0_trace_context_v4.py` — PASS.
- `PYTHONPYCACHEPREFIX=/tmp/codex-p0-residency-fix4-pycache python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py 3090-dev/test_p0_residency_barrier_emitter.py` — PASS.
- AST parse of both authorized files — PASS.
- `git diff --check -- python/sglang/srt/mem_cache/unified_radix_cache.py` — PASS.
- `git diff --no-index --check /dev/null 3090-dev/test_p0_residency_barrier_emitter.py` — no whitespace diagnostics; expected status 1 for the pre-existing untracked focused fixture.
- No remote or live run was performed.

## Fresh review conditions

An independent FIX4 review should inspect the delta from the accepted FIX3
contract, confirm that completion-triggered re-entry is protected by the
cache-owned `RLock`, and verify that no publication occurs before all expected
tokens and strict node/queue predicates hold. The reviewer should rerun the
focused emitter and V4.3 fixtures, `py_compile`, AST, and diff checks, and
confirm the no-next-request assertions plus all prior F-1/F-4 probes. Live
S=25 acceptance remains a separate tester/devops task and is not claimed here.

## Open issues

- The fresh live r13 runtime behavior is not re-run by this implementation task.
- The worktree retains unrelated aggregate changes and has no task-specific
  commit boundary; attribution must remain scoped to the two authorized files
  above.
