ENTRY: ACCEPT

# DEVOPS-20260908-P0-R7-JOIN-ROBUSTNESS-REMOTE-PREFLIGHT

- Task ID: `DEVOPS-20260908-P0-R7-JOIN-ROBUSTNESS-REMOTE-PREFLIGHT`
- Orchestration epoch: `2026-09-08`
- Role: `devops`
- Invocation status: `done`
- Admission: `ACCEPT`

## Scope and authorization

Remote target: `root@175.155.64.171:24052`  
Remote checkout: `/root/sglang-b1-continuity`  
Remote evidence: `/root/evidence-gate3-parked/p0-s25-v43-fix2-robustness-preflight`

Accepted inputs: `P0-BUILD-COMPLETE-EMITTER-FIX2` and
`P0-R7-JOIN-ROBUSTNESS-FIX5`.

The explicit sync wrote only the 11 accepted file destinations below and the
new evidence directory. No local product file was changed. No prior evidence,
storage, marker, event, or transient log was modified. No engine, server,
launcher, or vehicle was started.

## Observed environment facts

- Local source root: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`.
- The local source checkout had pre-existing unrelated dirty/untracked work;
  it was preserved. Local `git diff --check` passed.
- Remote checkout existed and the fresh evidence namespace was absent before
  the authorized write.
- A broad remote process scan showed unrelated archive/driver waiters whose
  command text contains broad `sglang`/`gate3` terms. The exact target filter
  found no engine, vehicle, launcher, or target gate process before or after
  the preflight.
- Remote host does not have `rg`; the launcher and fallback checks therefore
  used `grep`/`awk` equivalents after the initial `rg` attempt stopped only
  those two checks. The already completed checks were not rerun or weakened.

## Explicit synchronized files and SHA-256

Each file was copied with an explicit `scp -p` command to the identical
relative path under the remote checkout. Local and remote hashes matched:

| relative path | SHA-256 |
|---|---|
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | `5b78644533af88a23b9a46c08d5f5ec460c32cccb5f81541a09f5b57d0a9c2da` |
| `3090-dev/test_p0_trace_context_v4.py` | `8c583d1c7a74278232449fa22cc9aa084ed9645def1c816f1b462df8d51ec51c` |
| `3090-dev/p0_session_barrier_vehicle.py` | `621d742f0d1d672e7e936451118d929635f03591b2658175d300a3c2a9a7978b` |
| `python/sglang/srt/mem_cache/trace_context.py` | `aa8656e1e6e572dd139d4c18e4f6840083800df5b2692bdcad3bf2dab82e439e` |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | `5bc3ac23e3a1f375f116744ac0c8bf91f07410526ea01e49147bb4838479c501` |
| `python/sglang/srt/mem_cache/hiradix_cache.py` | `b16f4e02b925ee320845295c625037b7e9d5d5e4e0478f1b20f03fce7b0cf845` |
| `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py` | `18ca54afe2936423842d04f06c98e477d82dae31fdb7a5b776dcae1d8a8e288f` |
| `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py` | `afec684803956cbcce637aa1896839a687c3c57e1d29f3dfbab4ae2eb68d339b` |
| `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` | `bef390f13e4479aae4016883ea45e713dc24f008997effed4aca7c4750a09600` |
| `3090-dev/gate3_parked.py` | `2cda1512666e72a28db0182882efe4b148a9f5816335cfc62de89f52e7beb469` |
| `3090-dev/direct-launch-gate3-parked.sh` | `8d59823b64ab7359b113c7ed790e22d1903ac3d529b837421777b14c81401b09` |

The authoritative remote manifest is also in
`sha256.remote.txt`; `sha256.local.txt` records the expected local values.

## Remote no-engine preflight evidence

- Exact vehicle interpreter preflight passed:
  `/root/miniconda3/envs/sglang-patch/bin/python`.
- Exact vehicle `PYTHONPATH` recorded and tested:
  `/root/sglang-b1-continuity/3090-dev:/root/sglang-b1-continuity/python`.
- `transformers` version: `5.12.1`.
- `gate3_parked` imported from
  `/root/sglang-b1-continuity/3090-dev/gate3_parked.py`.
- Remote `py_compile`: PASS for all 10 authorized Python files;
  `REMOTE_PY_COMPILE_OK files=10`.
- Focused fixture: PASS — `P0 trace-context V4.3 focused checks: PASS`.
- AST parse: PASS for all 10 authorized Python files; `REMOTE_AST_OK files=10`.
- Launcher syntax and flag: PASS; exactly one
  `--enable-session-radix-cache`; mode observed as `700`.
- Fallback diff: remote checkout has no Git metadata; conflict-marker scan
  passed with `REMOTE_CONFLICT_MARKER_SCAN_OK`.
- Marker path recorded: `/tmp/t38c-durable-trace` — existing, 0 bytes.
- Event path recorded: `/tmp/t38c-probe.log` — existing, 1,119,590,959 bytes.
  Both paths were inspected with `stat` only and were not truncated, cleared,
  copied, or otherwise modified.
- Fresh run-ID convention recorded:
  `p0-s25-v43-fix2-robustness-live-<UTC_TIMESTAMP>`.
- Final exact target-process check: `none`, `ZERO_PROCESS_CHECK_OK`.

Evidence artifacts:

- `/root/evidence-gate3-parked/p0-s25-v43-fix2-robustness-preflight/resolved-preflight.txt`
- `sha256.local.txt`, `sha256.remote.txt`
- `vehicle-interpreter-preflight.txt`
- `py_compile.txt`, `focused-fixture.log`, `ast-check.txt`
- `launcher-check.txt`, `fallback-diff.txt`
- `transient-paths.txt`, `process-check-final.txt`
- `evidence-sha256.txt`

## Summary

The accepted FIX5 tailer/fixture and FIX2 emitter set is explicitly deployed
to the authorized remote checkout and is ready for a separately authorized
fresh runtime procedure. The no-engine remote preflight passed all requested
checks. This task makes no live runtime or P0 acceptance claim.

## Followups

- A fresh Task ID is required before any engine/vehicle launch, transient-log
  reset, live run, rollback, or additional remote mutation.
- A future live task may use the recorded marker/event paths, interpreter,
  `PYTHONPATH`, launcher, and fresh run-ID convention, subject to its own
  zero-process preflight.

## Open issues

1. Live runtime acceptance remains outstanding by design.
2. Remote native `git diff --check` was unavailable because the checkout has
   no Git metadata; the explicit conflict-marker fallback passed.

done
