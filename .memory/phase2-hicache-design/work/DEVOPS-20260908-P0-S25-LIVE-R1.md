ENTRY: ACCEPT

# DEVOPS-20260908-P0-S25-LIVE-R1

Invocation status: blocked

## Summary

The live vehicle did not start. The authorized remote checkout has no copy of the required launcher `3090-dev/direct-launch-gate3-parked.sh`, and no matching file exists anywhere under `/root/sglang-b1-continuity`. Per procedure, no substitute launcher or alternative procedure was selected.

## Resolved configuration

- Remote: `root@175.155.64.171:24052`
- Checkout: `/root/sglang-b1-continuity`
- Model: `/root/models/Qwen3.5-9B-w4a16`
- Evidence root: `/root/evidence-gate3-parked/p0-s25-v43-live-r1`
- Storage: `/root/evidence-gate3-parked/p0-s25-v43-live-r1/storage`
- Frozen parameters: `S=25`, `history_target=55000`, `active=8`, `build_workers=8`, `RH=off`, `mamba_ratio=0.42`, `hicache_ratio=1.3`, `kv_dtype=fp8_e4m3`, `cuda_graph_max_bs=8`, `max_total_num_tokens=600000`, `extent/file_size=120G`, `short suffix threshold=256`, `tp_size=1`, model `Qwen3.5-9B`.
- `T38C_RUN_ID=p0-s25-v43-live-r1` was prepared for the intended engine and vehicle.

## Commands and evidence

1. Remote process preflight:

   `ps -eo pid=,stat=,cmd= | grep -E "(sglang|p0_session_barrier_vehicle|gate3)" | grep -v grep || true`

   Output: no matching process.

2. Local vehicle hash:

   `c557300fe8f287a4ef10c5105a89bd48e3c8f2c01d0621700da362031d1db5bc  /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/p0_session_barrier_vehicle.py`

3. Vehicle sync completed to `/root/sglang-b1-continuity/3090-dev/p0_session_barrier_vehicle.py`; remote hash matched:

   `c557300fe8f287a4ef10c5105a89bd48e3c8f2c01d0621700da362031d1db5bc`

4. Remote product hashes verified at the resolved checkout locations:

   - `python/sglang/srt/mem_cache/trace_context.py`: `aa8656e1e6e572dd139d4c18e4f6840083800df5b2692bdcad3bf2dab82e439e`
   - `python/sglang/srt/mem_cache/unified_radix_cache.py`: `10e0d53b3efa2d8a3a3202c546d7f36a2ef4655979d18d7f6c3722f72706ec6c`
   - `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`: `5bc3ac23e3a1f375f116744ac0c8bf91f07410526ea01e49147bb4838479c501`
   - `python/sglang/srt/mem_cache/hiradix_cache.py`: `b16f4e02b925ee320845295c625037b7e9d5d5e4e0478f1b20f03fce7b0cf845`
   - `python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py`: `18ca54afe2936423842d04f06c98e477d82dae31fdb7a5b776dcae1d8a8e288f`
   - `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py`: `afec684803956cbcce637aa1896839a687c3c57e1d29f3dfbab4ae2eb68d339b`
   - `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`: `bef390f13e4479aae4016883ea45e713dc24f008997effed4aca7c4750a09600`

5. Storage directory was newly created (`STORAGE_NEW`). With no matching process, only the specified stale temporary paths were removed, then `/tmp/t38c-probe.log` was recreated empty and `/tmp/t38c-durable-trace` was touched. Output: `TEMP_CLEAN_PREPARED`.

6. Launcher validation:

   `sed -n '1,220p' /root/sglang-b1-continuity/3090-dev/direct-launch-gate3-parked.sh`

   Output: `No such file or directory`.

   `find /root/sglang-b1-continuity -type f -name "direct-launch-gate3-parked.sh" -print`

   Output: empty.

## Engine and vehicle lifecycle

- Engine PID: none; engine was not started.
- Health polling: not applicable.
- Vehicle command: not executed because the authorized launcher prerequisite was absent.
- Vehicle sessions: 0/25 started; no verdict.json, restore metrics, or TTFT metrics produced.
- Durability/residency barriers: not evaluated.
- Cleanup: no engine PID to stop; prepared temporary paths and new storage remain preserved as instructed. No old evidence or old storage was deleted.

## Branch classification and open issues

Classification: `BLOCKED / NEEDS_REROUTE` — the named launcher is absent from the authorized remote target, so the prescribed execution method cannot be executed without a fresh Task ID or corrected target artifact.

Open issue: provide/restore the exact accepted launcher at `/root/sglang-b1-continuity/3090-dev/direct-launch-gate3-parked.sh` (or issue a fresh authorized task defining the corrected launcher and method). No RH-on run, scale test, rerun, or alternative launcher was attempted.

Followup: none within this Task ID; extra work requires a fresh Task ID.
