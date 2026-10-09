ENTRY: ACCEPT

# DEVOPS-20260908-P0-S25-LIVE-R3

Invocation status: pending
Verdict: NOT_VERIFIED
Task ID: DEVOPS-20260908-P0-S25-LIVE-R3
Orchestration epoch: E20260908-P0P1P2
Role: devops-executor

## Summary

The required `gate3_parked.py` dependency was explicitly synchronized and hash-verified. The frozen R3 engine reached readiness and the exact vehicle was started once. At report time the vehicle is still running, so no terminal vehicle stdout/stderr or exit code exists and the engine cannot be stopped under the stated cleanup rule (stop only after vehicle terminal result). No rerun, alternate vehicle, manual warm, RH-on run, scale test, or fixed-settle criterion was used.

## Commands and evidence

Remote preflight and parent creation:

```text
ssh -o BatchMode=yes -p 24052 root@175.155.64.171 "ps -eo pid=,stat=,etime=,cmd= | grep -E 'sglang|vllm|engine|vehicle|gate3' | grep -v grep || true; test -d /root/sglang-b1-continuity && echo CHECKOUT_OK; mkdir -p /root/sglang-b1-continuity/3090-dev"
```

Output: `CHECKOUT_OK`; no matching process was present before launch.

Dependency sync:

```text
scp -P 24052 /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/gate3_parked.py root@175.155.64.171:/root/sglang-b1-continuity/3090-dev/gate3_parked.py
```

Hashes before start:

```text
2cda1512666e72a28db0182882efe4b148a9f5816335cfc62de89f52e7beb469  gate3_parked.py (local and remote)
40262b8ab82b244b6489105559a5f43012b97601d52ff2aa0f50fc030408aaec  direct-launch-gate3-parked.sh (remote)
c557300fe8f287a4ef10c5105a89bd48e3c8f2c01d0621700da362031d1db5bc  p0_session_barrier_vehicle.py (remote)
```

Accepted product hashes remained equal to R2: `trace_context.py` aa8656e1e6e572dd139d4c18e4f6840083800df5b2692bdcad3bf2dab82e439e; `unified_radix_cache.py` 10e0d53b3efa2d8a3a3202c546d7f36a2ef4655979d18d7f6c3722f72706ec6c; `hybrid_cache_controller.py` 5bc3ac23e3a1f375f116744ac0c8bf91f07410526ea01e49147bb4838479c501; `hiradix_cache.py` b16f4e02b925ee320845295c625037b7e9d5d5e4e0478f1b20f03fce7b0cf845; `mamba_component.py` 18ca54afe2936423842d04f06c98e477d82dae31fdb7a5b776dcae1d8a8e288f; `extent_allocator.py` afec684803956cbcce637aa1896839a687c3c57e1d29f3dfbab4ae2eb68d339b; `extent_file_backend.py` bef390f13e4479aae4016883ea45e713dc24f008997effed4aca7c4750a09600.

Evidence setup used `/root/evidence-gate3-parked/p0-s25-v43-live-r3/{storage,vehicle}`, cleaned only `/tmp/t38c-durable-trace` and `/tmp/t38c-probe.log`, then recreated both empty. Prior R1/R2 evidence and storage were not touched.

Launcher command was the requested frozen environment, redirected to `/root/evidence-gate3-parked/p0-s25-v43-live-r3/engine.log`; recorded engine PID: `998868`. Remote log reached ready state at `2026-09-08 05:49:48`, with extent file size 120000000000, FP8 E4M3 KV, profiled max total 501851, graph decode batch sizes through 8, and requested storage path.

Exact vehicle command:

```text
cd /root/sglang-b1-continuity && T38C_RUN_ID=p0-s25-v43-live-r3 /root/miniconda3/envs/sglang-patch/bin/python 3090-dev/p0_session_barrier_vehicle.py --events /tmp/t38c-probe.log --endpoint http://127.0.0.1:8024 --model qwen3.5-9b-gptq --model-path /root/models/Qwen3.5-9B-w4a16 --evidence-dir /root/evidence-gate3-parked/p0-s25-v43-live-r3/vehicle --run-id p0-s25-v43-live-r3 --task-id DEVOPS-20260908-P0-S25-LIVE-R3 --sessions 25 --active 8 --build-workers 8 --history-target 55000 --rh off
```

Vehicle PID at final check: `999350`, state `Ssl`, elapsed `06:16`. No vehicle result files were present. `/tmp/t38c-probe.log` contained 405 lines; `/tmp/t38c-durable-trace` contained 0 lines. Engine log showed the workload still serving requests at 05:53:58.

## Terminal status, cleanup, and open issues

Status is `pending`; vehicle stdout/stderr and exit code are not terminally available because PID 999350 remains active. The live SSH capture had no output before interruption, which is consistent with the vehicle still running rather than an exit.

Required cleanup is not yet authorized by the frozen procedure: stopping engine PID 998868 before the vehicle exits would violate “stop only task engine PID” after terminal result. Current matching processes include engine PID 998868, scheduler PID 998917, and vehicle PID 999350. Evidence and 120G storage remain preserved.

Open issue: the vehicle has not reached a terminal result; PASS/FAIL eligibility, per-session verdicts, joins/barriers, TTFT, restore metrics, and final hashes cannot yet be verified.

Followup: continue the same Task ID only until vehicle exit, capture terminal stdout/stderr/exit, then stop PID 998868 and perform final process/evidence/hash verification. Any rerun or altered procedure requires a fresh Task ID.
