ENTRY: ACCEPT

# DEVOPS-20260908-P0-EMITTER-FIX1-REMOTE-PREFLIGHT

- orchestration_epoch: `2026-09-08`
- role: `devops`
- invocation_status: `done`
- admission: `ACCEPT`

## Summary

The accepted P0 runtime prerequisite was activated and the remote preflight
bundle was created. The launcher now contains exactly one
`--enable-session-radix-cache`; RH remains off by default and all frozen S=25
settings were preserved. The accepted files were explicitly synchronized to
`root@175.155.64.171:24052:/root/sglang-b1-continuity`. No engine or vehicle was
started.

## Preconditions and authorization boundary

Observed before writes:

- Accepted gate: `review/gates/P0-BUILD-COMPLETE-EMITTER-FIX1.md`.
- Remote checkout existed at `/root/sglang-b1-continuity`.
- No matching `sglang`, `vllm`, `engine`, `vehicle`, or `gate3` process was
  present during preflight.
- The task-specific evidence directory did not already exist.

Writes were limited to the authorized local launcher flag insertion, the 11
explicit remote file destinations, and the new remote evidence directory:

`/root/evidence-gate3-parked/p0-s25-v43-fix1-remote-preflight`

No marker or event file was created or cleared, no prior evidence was changed,
and no live workload was launched.

## Launcher verification

- `--enable-session-radix-cache` count: `1`.
- `--enable-ready-horizon` remains only in the existing `RH=on` conditional;
  default resolved RH: `off`.
- Frozen settings verified: sessions `25`, active `8`, build workers `8`,
  history target `55000`, Mamba ratio `0.42`, HiCache ratio `1.3`, KV dtype
  `fp8_e4m3`, CUDA graph max batch `8`, and `--max-running-requests 8`.
- Local launcher `git diff --check`: PASS.

## Remote preflight resolution

Recorded in `resolved-preflight.txt`:

- scheduler flag: `--enable-session-radix-cache` (exactly once)
- marker path: `/tmp/t38c-durable-trace`
- event path: `/tmp/t38c-probe.log`
- fresh run-ID convention: `p0-s25-v43-fix1-live-<UTC_TIMESTAMP>`
- `engine_start_allowed=false`
- `vehicle_start_allowed=false`
- final matching-PID check: `no_matching_engine_vehicle_gate3_pids=true`

## Verification evidence

- Remote `py_compile` for the 10 Python files: PASS.
- Remote focused fixture `3090-dev/test_p0_trace_context_v4.py`: PASS —
  `P0 trace-context V4.3 focused checks: PASS`.
- Remote AST parse for the 10 Python files: PASS.
- Remote available whitespace/conflict-marker scan: PASS.
- Remote Git diff check was unavailable because the checkout has no Git
  metadata; this is recorded in `diff-check.txt`. The local launcher diff
  check passed and the remote available scan passed.
- No fixed-settle criterion, synthetic live evidence, RH-on mode, or large
  fleet was used.

## SHA-256 manifest

All 11 local hashes matched the corresponding remote hashes:

| path | SHA-256 |
|---|---|
| `python/sglang/srt/mem_cache/trace_context.py` | `aa8656e1e6e572dd139d4c18e4f6840083800df5b2692bdcad3bf2dab82e439e` |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | `27b5b47a857ac9012d4beaf42a24122a7441e9a823fdc748ba7c19c7c94e1d06` |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | `5bc3ac23e3a1f375f116744ac0c8bf91f07410526ea01e49147bb4838479c501` |
| `python/sglang/srt/mem_cache/hiradix_cache.py` | `b16f4e02b925ee320845295c625037b7e9d5d5e4e0478f1b20f03fce7b0cf845` |
| `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py` | `18ca54afe2936423842d04f06c98e477d82dae31fdb7a5b776dcae1d8a8e288f` |
| `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py` | `afec684803956cbcce637aa1896839a687c3c57e1d29f3dfbab4ae2eb68d339b` |
| `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` | `bef390f13e4479aae4016883ea45e713dc24f008997effed4aca7c4750a09600` |
| `3090-dev/test_p0_trace_context_v4.py` | `ebfe67d2ec733ee31be6e6d6fc3b27d3ec1da4d765465e48676efc705a5852d2` |
| `3090-dev/p0_session_barrier_vehicle.py` | `c557300fe8f287a4ef10c5105a89bd48e3c8f2c01d0621700da362031d1db5bc` |
| `3090-dev/gate3_parked.py` | `2cda1512666e72a28db0182882efe4b148a9f5816335cfc62de89f52e7beb469` |
| `3090-dev/direct-launch-gate3-parked.sh` | `8d59823b64ab7359b113c7ed790e22d1903ac3d529b837421777b14c81401b09` |

## Artifacts

Remote evidence directory:

`/root/evidence-gate3-parked/p0-s25-v43-fix1-remote-preflight`

It contains `resolved-preflight.txt`, `sha256.remote.txt`,
`evidence-sha256.txt`, `py_compile.txt`, `focused-fixture.log`,
`ast-check.txt`, `diff-check.txt`, `whitespace-check.txt`,
`launcher-check.txt`, `process-check-final.txt`, and evidence-only pycache
under `pycache/`.

This report is the local task artifact at:

`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/DEVOPS-20260908-P0-EMITTER-FIX1-REMOTE-PREFLIGHT.md`

## Rollback, followups, and open issues

- Rollback was not needed. Reverting the launcher or remote sync would be a
  new mutating operation and requires a fresh Task ID.
- Followup: a separately authorized live S=25/RH-off run may use the recorded
  marker/event paths and fresh run-ID convention.
- Open issue: live runtime acceptance remains intentionally unperformed;
  this task establishes preflight readiness only.

done
