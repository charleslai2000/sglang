ENTRY: ACCEPT

# DEVOPS-20260908-P0-S25-LIVE-R2

Invocation status: blocked
Verdict: FAIL / NOT_VERIFIED
Task ID: DEVOPS-20260908-P0-S25-LIVE-R2
Orchestration epoch: E20260908-P0P1P2
Role: devops-executor

## Summary

The frozen live engine launched successfully and reached `/health`, but the exact
specified vehicle failed before session execution because the remote checkout did
not contain the required `gate3_parked` import. No rerun, substitute builder,
manual warm, RH-on run, scale test, or alternative procedure was performed.

## Target and frozen configuration

- Remote: `root@175.155.64.171:24052`, BatchMode SSH
- Checkout: `/root/sglang-b1-continuity`
- Model: `/root/models/Qwen3.5-9B-w4a16`
- Evidence root: `/root/evidence-gate3-parked/p0-s25-v43-live-r2`
- Storage: `/root/evidence-gate3-parked/p0-s25-v43-live-r2/storage`
- Run ID: `p0-s25-v43-live-r2`
- Frozen parameters: `S=25`, `history_target=55000`, `active=8`,
  `build_workers=8`, `RH=off`, `mamba_ratio=0.42`, `hicache_ratio=1.3`,
  `kv_dtype=fp8_e4m3`, `cuda_graph_max_bs=8`, `max_total_num_tokens=600000`,
  `extent/file_size=120G`, short suffix threshold `256`, `tp_size=1`.

## Artifact hashes

Local launcher hash:

```text
40262b8ab82b244b6489105559a5f43012b97601d52ff2aa0f50fc030408aaec  /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/direct-launch-gate3-parked.sh
```

Remote launcher hash (exact destination):

```text
40262b8ab82b244b6489105559a5f43012b97601d52ff2aa0f50fc030408aaec  3090-dev/direct-launch-gate3-parked.sh
```

Local and remote vehicle hash:

```text
c557300fe8f287a4ef10c5105a89bd48e3c8f2c01d0621700da362031d1db5bc  3090-dev/p0_session_barrier_vehicle.py
```

Accepted V4.3 product hashes verified remotely before start and again after cleanup:

```text
aa8656e1e6e572dd139d4c18e4f6840083800df5b2692bdcad3bf2dab82e439e  python/sglang/srt/mem_cache/trace_context.py
10e0d53b3efa2d8a3a3202c546d7f36a2ef4655979d18d7f6c3722f72706ec6c  python/sglang/srt/mem_cache/unified_radix_cache.py
5bc3ac23e3a1f375f116744ac0c8bf91f07410526ea01e49147bb4838479c501  python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py
b16f4e02b925ee320845295c625037b7e9d5d5e4e0478f1b20f03fce7b0cf845  python/sglang/srt/mem_cache/hiradix_cache.py
18ca54afe2936423842d04f06c98e477d82dae31fdb7a5b776dcae1d8a8e288f  python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py
afec684803956cbcce637aa1896839a687c3c57e1d29f3dfbab4ae2eb68d339b  python/sglang/srt/mem_cache/storage/extent/extent_allocator.py
bef390f13e4479aae4016883ea45e713dc24f008997effed4aca7c4750a09600  python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py
```

## Commands and evidence

1. Preflight used:

```text
ssh -o BatchMode=yes -p 24052 root@175.155.64.171 "ps -eo pid=,stat=,etime=,cmd= | grep -E 'sglang|vllm|engine|vehicle|gate3' | grep -v grep || true; test -d /root/sglang-b1-continuity && echo CHECKOUT_OK"
```

Output: no matching process; `CHECKOUT_OK`.

2. Launcher was copied explicitly to `/root/sglang-b1-continuity/3090-dev/direct-launch-gate3-parked.sh`, mode `0755`. New r2 evidence/storage directories were created. Only `/tmp/t38c-durable-trace` and `/tmp/t38c-probe.log` were cleaned and recreated empty. Prior r1 evidence/storage was not touched.

3. Launcher command used the requested environment:

```text
T38C_RUN_ID=p0-s25-v43-live-r2 MODEL_PATH=/root/models/Qwen3.5-9B-w4a16 SERVED=qwen3.5-9b-gptq RH=off MAMBA_RATIO=0.42 HICACHE_RATIO=1.3 KV_DTYPE=fp8_e4m3 MAX_SIZE=120G FILE_SIZE=120G STORAGE_DIR=/root/evidence-gate3-parked/p0-s25-v43-live-r2/storage SGLANG_PORT=8024 SGLANG_ENABLE_UNIFIED_RADIX_TREE=1 ./3090-dev/direct-launch-gate3-parked.sh
```

Recorded launcher PID: `997014`; actual server child observed as PID `997015`.
The engine reached HTTP `/health` 200 after model load, CUDA graph capture, and
storage initialization. Engine log records extent file size `120000000000`,
extent `67108864`, slots `1788`, and the requested FP8 KV configuration.

4. Exact vehicle command used:

```text
cd /root/sglang-b1-continuity && T38C_RUN_ID=p0-s25-v43-live-r2 /root/miniconda3/envs/sglang-patch/bin/python 3090-dev/p0_session_barrier_vehicle.py --events /tmp/t38c-probe.log --endpoint http://127.0.0.1:8024 --model qwen3.5-9b-gptq --model-path /root/models/Qwen3.5-9B-w4a16 --evidence-dir /root/evidence-gate3-parked/p0-s25-v43-live-r2/vehicle --run-id p0-s25-v43-live-r2 --task-id DEVOPS-20260908-P0-S25-LIVE-R2 --sessions 25 --active 8 --build-workers 8 --history-target 55000 --rh off
```

Vehicle exit code: `1`. Failure:

```text
ModuleNotFoundError: No module named 'gate3_parked'
RuntimeError: existing build_history_prompt/tokenizer path unavailable: No module named 'gate3_parked'
```

The failure occurred in `_load_builder` before session execution.

5. Cleanup sent `TERM` to the recorded launcher PID `997014`, then to its
observed server child PID `997015` so the task-started engine was fully stopped.
Final verification: no matching sglang/vehicle/gate3 process; HTTP `/health`
connection refused.

## Metrics and artifacts

- Eligible/full sessions: `0/25`; exact joins/barriers/restores: not evaluated.
- Vehicle verdict: no `verdict.json` produced.
- TTFT/restore metrics: not produced by vehicle.
- Trace counts: `/tmp/t38c-probe.log` = `0` lines; `/tmp/t38c-durable-trace` = `0` lines.
- Evidence files preserved: `engine.log` (81966 bytes), `engine.pid` (PID text),
  and storage file `hicache.data_qwen3.5-9b-gptq_0_1` (120000000000 bytes).
- No old r1 evidence/storage was deleted or modified.

## Result, followups, and open issues

Result is `blocked` with `FAIL / NOT_VERIFIED`; PASS criteria cannot be met.

Followups: none within this Task ID. A corrected remote vehicle dependency or
explicitly authorized synchronization procedure requires a fresh Task ID.

Open issue: remote `3090-dev/p0_session_barrier_vehicle.py` imports
`gate3_parked`, but the required module is absent from the remote checkout.
No diagnosis, dependency selection, or rerun was authorized or attempted.
