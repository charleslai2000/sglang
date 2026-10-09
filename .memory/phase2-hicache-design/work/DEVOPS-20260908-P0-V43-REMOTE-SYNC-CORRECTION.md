ENTRY: ACCEPT

# DEVOPS-20260908-P0-V43-REMOTE-SYNC-CORRECTION

status: done
task_id: DEVOPS-20260908-P0-V43-REMOTE-SYNC-CORRECTION
orchestration_epoch: E20260908-P0P1P2
role: devops-executor

## Scope and r1 diagnosis

Remote target: `root@175.155.64.171:24052`, checkout `/root/sglang-b1-continuity`.
Evidence target: `/root/evidence-gate3-parked/p0-v43-remote-test-r2`.
No engine, vehicle, server, or long-running process was started.

r1 was invalidated because its fixture failed at `check_prefetch_signature`; review found the remote controller hash (`d0f0...`) differed from the local hash (`5bc3...`), so r1's hash-match conclusion was invalid and cannot serve as V4.3 evidence. The r1 evidence was not altered.

## Commands and evidence

The exact operational commands were run over SSH/scp with `BatchMode=yes`, `-P 24052`, one explicit destination per file, and `mkdir -p dirname` before each copy. Local and remote manifests below are the captured SHA-256 evidence.

Local source: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`.

| relative path | local SHA-256 | remote SHA-256 | result |
|---|---|---|---|
| `python/sglang/srt/mem_cache/trace_context.py` | `aa8656e1e6e572dd139d4c18e4f6840083800df5b2692bdcad3bf2dab82e439e` | same | MATCH |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | `10e0d53b3efa2d8a3a3202c546d7f36a2ef4655979d18d7f6c3722f72706ec6c` | same | MATCH |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | `5bc3ac23e3a1f375f116744ac0c8bf91f07410526ea01e49147bb4838479c501` | same | MATCH |
| `python/sglang/srt/mem_cache/hiradix_cache.py` | `b16f4e02b925ee320845295c625037b7e9d5d5e4e0478f1b20f03fce7b0cf845` | same | MATCH |
| `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py` | `18ca54afe2936423842d04f06c98e477d82dae31fdb7a5b776dcae1d8a8e288f` | same | MATCH |
| `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py` | `afec684803956cbcce637aa1896839a687c3c57e1d29f3dfbab4ae2eb68d339b` | same | MATCH |
| `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py` | `bef390f13e4479aae4016883ea45e713dc24f008997effed4aca7c4750a09600` | same | MATCH |
| `3090-dev/test_p0_trace_context_v4.py` | `51871321be46ad51f356b5758dbf298b3b85e00d0c84b5bf0fe1c2e842dd6f08` | same | MATCH |

Pre-sync process check command:

```text
ssh -p 24052 -o BatchMode=yes root@175.155.64.171 "ps -eo pid=,stat=,etime=,cmd= | grep -E 'sglang|vllm|engine|vehicle' | grep -v grep || true"
stdout: empty
status: 0
```

Verification commands and captured results:

```text
cd /root/sglang-b1-continuity && /root/miniconda3/envs/sglang-patch/bin/python -m py_compile <all eight specified files>
stdout: empty
stderr: empty
exit: 0

cd /root/sglang-b1-continuity && /root/miniconda3/envs/sglang-patch/bin/python 3090-dev/test_p0_trace_context_v4.py
stdout: P0 trace-context V4.3 focused checks: PASS
stderr: empty
exit: 0

cd /root/sglang-b1-continuity && /root/miniconda3/envs/sglang-patch/bin/python test/registered/unit/mem_cache/test_extent_file_backend_unit.py
stdout: 77 tests ran; OK
stderr: expected JIT/environment warnings (missing /usr/local/cuda/bin/nvcc and ninja), plus test diagnostic messages
exit: 0
```

Post-process check used the same `ps` filter as the pre-check; stdout was empty and exit status was 0. No engine/vehicle process was present.

## Result

All eight files were explicitly synchronized to the requested absolute remote paths, all hashes matched before tests, py_compile passed, the V4.3 focused fixture passed, and the extent backend unit suite passed (`77` tests, `OK`). No storage cleanup, old-evidence modification, or server/vehicle launch occurred.

Followups: none.
Open issues: none for this task. Extra work requires a fresh Task ID.
