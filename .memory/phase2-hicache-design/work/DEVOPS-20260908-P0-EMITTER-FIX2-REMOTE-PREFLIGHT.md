ENTRY: ACCEPT

# DEVOPS-20260908-P0-EMITTER-FIX2-REMOTE-PREFLIGHT

- orchestration_epoch: `2026-09-08`
- role: `devops`
- invocation_status: `done`
- admission: `ACCEPT`

## Summary

FIX2 and the previously accepted P0 prerequisite files were explicitly
synchronized to `root@175.155.64.171:24052:/root/sglang-b1-continuity`.
All 11 local/remote SHA-256 pairs match. The no-engine remote preflight
bundle passed compile, focused fixture, AST, launcher, fallback diff, and
zero-process checks. No engine or vehicle was started.

## Preconditions and authorization boundary

Observed before writes:

- Accepted unit gate:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-BUILD-COMPLETE-EMITTER-FIX2.md`;
  verdict `ACCEPT` for the narrow emitter unit gate.
- Remote checkout existed at `/root/sglang-b1-continuity`.
- No matching `sglang`, `vllm`, `engine`, `vehicle`, or `gate3` process was
  present.
- New evidence directory did not exist:
  `/root/evidence-gate3-parked/p0-s25-v43-fix2-remote-preflight`.

Remote writes were limited to the 11 explicit accepted destinations and the
new evidence directory. No prior evidence/storage namespace was touched. No
launcher or product file was edited other than syncing the accepted local
files. No `/tmp` marker/event path was created, cleared, or truncated.

## Explicit synchronized files

Source root:
`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`

1. `python/sglang/srt/mem_cache/unified_radix_cache.py` (FIX2)
2. `3090-dev/test_p0_trace_context_v4.py` (FIX2 fixture)
3. `3090-dev/p0_session_barrier_vehicle.py`
4. `python/sglang/srt/mem_cache/trace_context.py`
5. `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`
6. `python/sglang/srt/mem_cache/hiradix_cache.py`
7. `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`
8. `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py`
9. `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`
10. `3090-dev/gate3_parked.py`
11. `3090-dev/direct-launch-gate3-parked.sh`

Each file was transferred with an explicit `scp -p` command to the identical
relative path under the remote checkout.

## SHA-256 manifest

The following values were independently obtained from local and remote
checkouts and matched for every row:

| path | SHA-256 |
|---|---|
| `python/sglang/srt/mem_cache/trace_context.py` | `aa8656e1e6e572dd139d4c18e4f6840083800df5b2692bdcad3bf2dab82e439e` |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | `0aba7eafb701d8855fc370cc7a43302f618512e9992f2319784b1cbcc0d4a873` |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | `5bc3ac23e3a1f375f116744ac0c8bf91f07410526ea01e49147bb4838479c501` |
| `python/sglang/srt/mem_cache/hiradix_cache.py` | `b16f4e02b925ee320845295c625037b7e9d5d5e4e0478f1b20f03fce7b0cf845` |
| `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py` | `18ca54afe2936423842d04f06c98e477d82dae31fdb7a5b776dcae1d8a8e288f` |
| `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py` | `afec684803956cbcce637aa1896839a687c3c57e1d29f3dfbab4ae2eb68d339b` |
| `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` | `bef390f13e4479aae4016883ea45e713dc24f008997effed4aca7c4750a09600` |
| `3090-dev/test_p0_trace_context_v4.py` | `6c3610ee5d6689f5fabf67a5f4a8bb7356d00a5a9364ea38122829fee3a25962` |
| `3090-dev/p0_session_barrier_vehicle.py` | `c557300fe8f287a4ef10c5105a89bd48e3c8f2c01d0621700da362031d1db5bc` |
| `3090-dev/gate3_parked.py` | `2cda1512666e72a28db0182882efe4b148a9f5816335cfc62de89f52e7beb469` |
| `3090-dev/direct-launch-gate3-parked.sh` | `8d59823b64ab7359b113c7ed790e22d1903ac3d529b837421777b14c81401b09` |

## Remote preflight evidence

Evidence root:
`/root/evidence-gate3-parked/p0-s25-v43-fix2-remote-preflight`

- `resolved-preflight.txt` records:
  - marker `/tmp/t38c-durable-trace`
  - event `/tmp/t38c-probe.log`
  - run-ID convention `p0-s25-v43-fix2-live-<UTC_TIMESTAMP>`
  - exactly enabled flag `--enable-session-radix-cache`
  - `engine_start_allowed=false` and `vehicle_start_allowed=false`
  - no transient log truncation and no prior evidence touch
- `sha256.remote.txt`: remote 11-file manifest.
- `py_compile.txt`: 10 unique Python files, `REMOTE_PY_COMPILE_OK`.
- `focused-fixture.log`: `P0 trace-context V4.3 focused checks: PASS`.
- `ast-check.txt`: 10 AST parses, `REMOTE_AST_OK`.
- `launcher-check.txt`: shell syntax pass, session-radix flag count `1`,
  `REMOTE_LAUNCHER_CHECK_OK`; synced mode observed as `700`.
- `diff-check.txt`: checkout has no Git metadata; fallback conflict-marker
  scan passed as `REMOTE_CONFLICT_MARKER_SCAN_OK`.
- `process-check-final.txt`: `none`, `ZERO_PROCESS_CHECK_OK`.
- `evidence-sha256.txt`: hashes of the top-level evidence artifacts.

Read-only post-check status of transient paths:

- `/tmp/t38c-durable-trace`: exists, size `0`, `0` lines.
- `/tmp/t38c-probe.log`: exists, size `464782` bytes, `405` lines.

These files were not modified by this task.

## Rollback and execution boundary

Rollback was not needed. Reverting synced remote files or changing launcher
permissions would be a new mutating operation and requires a fresh Task ID.
This task only establishes deployment and preflight readiness; it does not
authorize a live engine/vehicle run.

## Evidence

- Remote evidence bundle:
  `/root/evidence-gate3-parked/p0-s25-v43-fix2-remote-preflight`
- Authoritative gate:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/P0-BUILD-COMPLETE-EMITTER-FIX2.md`
- This report:
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/DEVOPS-20260908-P0-EMITTER-FIX2-REMOTE-PREFLIGHT.md`

## Followups

- A separately authorized fresh S=25/RH-off live run may use the recorded
  launcher, marker/event paths, and fresh FIX2 run-ID convention.
- The live runtime gate must independently verify exact V3 identity joins and
  causal ordering; this preflight does not claim runtime acceptance.

## Open issues

1. Live runtime/vehicle acceptance remains outstanding by design.
2. Remote checkout lacks Git metadata, so native `git diff --check` was not
   available; the explicit conflict-marker fallback passed.

done
