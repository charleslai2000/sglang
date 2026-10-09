ENTRY: ACCEPT

# TEST-20260908-P0-S25-LIVE-FIX1

- Task ID: `TEST-20260908-P0-S25-LIVE-FIX1`
- Orchestration epoch: `2026-09-08-P0`
- Role: `tester`
- Invocation status: **blocked**
- Admission: `ACCEPT`
- Host: `root@175.155.64.171:24052` (`pytorch-4402`)
- Checkout: `/root/sglang-b1-continuity`
- Evidence root: `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r9`

## Summary

The accepted FIX1 source was synchronized and passed the focused V4.3 fixture,
but the frozen live P0 S=25 vehicle could not be started. The required
root-backed filesystem was already 100% full with 0 bytes available. Starting
the launcher would require a fresh 120G storage file under the authorized
evidence root; the only observed alternative, `/data`, is outside the frozen
storage path and was not substituted. No P0 runtime acceptance claim is made.

This is an **infrastructure block with missing live evidence**, not a product
defect or test failure. No prior evidence or storage was deleted.

## Artifacts

- Remote evidence directory: `/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r9`
- Prior transient snapshots:
  - `raw/t38c-probe.log.pre-r9`, MD5 `8d0a495416c02071481afd8150f74317`, SHA-256 `f5def3f605c8cb630b51a3a7341bde13993a5b8d0403cd0c873bc9b3cd227a65`, 464782 bytes.
  - `raw/t38c-durable-trace.pre-r9`, MD5 `d41d8cd98f00b204e9800998ecf8427e`, SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`, 0 bytes.
- Remote focused fixture log: `focused-fixture.log` — `P0 trace-context V4.3 focused checks: PASS`.
- Remote preflight record: `resolved-preflight.txt` — `engine_start_allowed=false`, `vehicle_start_allowed=false`, root filesystem full.

## Source synchronization

Only the authorized product file was synchronized:

- Source: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
- Remote destination: `/root/sglang-b1-continuity/python/sglang/srt/mem_cache/unified_radix_cache.py`
- Source MD5: `e1111771af0c01e34b7ca6288c3c2c92`
- Remote post-sync MD5: `e1111771af0c01e34b7ca6288c3c2c92`
- Source/remote SHA-256: `acc21828eac866f0d2f05f465273c8d77f586693544b796f15e62b9f810b9460`
- Remote size: `268141` bytes.
- Pre-sync remote SHA-256 observed: `5b78644533af88a23b9a46c08d5f5ec460c32cccb5f81541a09f5b57d0a9c2da`.

The local source worktree was already dirty in unrelated files; no local
product file was modified by this test task.

## Intended frozen launch contract

No live launch command was executed. The resolved intended contract was:

```text
T38C_RUN_ID=p0-s25-v43-fix1-live-r9
MODEL_PATH=/root/models/Qwen3.5-9B-w4a16
SERVED=qwen3.5-9b-gptq
RH=off
MAMBA_RATIO=0.42
HICACHE_RATIO=1.3
KV_DTYPE=fp8_e4m3
MAX_SIZE=120G
FILE_SIZE=120G
STORAGE_DIR=/root/evidence-gate3-parked/p0-s25-v43-fix1-live-r9/storage
SGLANG_PORT=8024
SGLANG_ENABLE_UNIFIED_RADIX_TREE=1
T38C_BUILD_COMPLETE_DEBUG=1
```

The accepted launcher contains exactly one `--enable-session-radix-cache`,
`--max-running-requests 8`, `--cuda-graph-max-bs 8`, `--max-total-tokens
600000`, `--hicache-storage-prefetch-policy wait_complete`, TP=1, and RH off.
The intended vehicle command was the accepted shape using:

```text
cd /root/sglang-b1-continuity
PYTHONPATH=/root/sglang-b1-continuity/3090-dev \
/root/miniconda3/envs/sglang-patch/bin/python \
3090-dev/p0_session_barrier_vehicle.py \
--events /tmp/t38c-probe.log --endpoint http://127.0.0.1:8024 \
--model qwen3.5-9b-gptq --model-path /root/models/Qwen3.5-9B-w4a16 \
--evidence-dir /root/evidence-gate3-parked/p0-s25-v43-fix1-live-r9/vehicle \
--run-id p0-s25-v43-fix1-live-r9 \
--task-id TEST-20260908-P0-S25-LIVE-FIX1 \
--sessions 25 --active 8 --build-workers 8 --history-target 55000 --rh off
```

## Process and environment evidence

- Initial and final matching-process checks: no `sglang.launch_server`, vehicle,
  launcher, or gate3 process.
- Engine PID: none; vehicle PID: none; launcher PID: none.
- `/proc/$engine_pid/environ` verification: not applicable because no engine
  was started.
- No HTTP health/readiness request was made.
- No fixed sleep, synthetic durable event, manual warm request, RH-on mode, or
  session count above 25 was used.

## Blocking infrastructure evidence

At preflight and after the focused fixture:

```text
overlay  98G  94G  0  100%  /
/dev/sdb  197G 54G 134G 29%  /data
```

The root-backed evidence area already contained six prior logical 120G
HiCache files under preserved runs (`r2`, `r3`, `r4`, `r5`, `r7`, `r8`). Their
prior evidence/storage was outside this task's cleanup authorization and was
not removed. Repointing `STORAGE_DIR` to `/data` would change the frozen launch
contract, so it was not attempted.

## Transient cleanup

After the pre-sync snapshots, `/tmp/t38c-probe.log` was truncated to an empty
file and `/tmp/t38c-durable-trace` was removed. The preserved r9 raw snapshots
remain intact. Final checks found no matching processes and no active marker.

## Acceptance matrix

| Criterion | Result | Evidence |
|---|---|---|
| FIX1 source synchronized | PASS | Remote MD5/SHA-256 exactly match local source. |
| Focused V4.3 fixture | PASS | `focused-fixture.log`. |
| Fresh run ID in engine environment | NOT RUN | No engine was started. |
| `/proc` environment verification | NOT RUN | No engine PID. |
| S=25 durable vehicle | NOT RUN | Blocked before launch by root filesystem exhaustion. |
| Per-session KV ACK/durable/frontier | NO EVIDENCE | No live vehicle. |
| Per-session Mamba ACK/durable/frontier | NO EVIDENCE | No live vehicle. |
| Residency eviction and barriers | NO EVIDENCE | No live vehicle. |
| `s00002` / boundary=0 causal chain | NO NEW EVIDENCE | No r9 session ran; prior R8 diagnosis remains historical only. |
| Restore success | 0 observed / not run | No restore phase occurred. |
| P0 acceptance | NOT VERIFIED | Required runtime evidence is absent. |

## Followups

Free or provision the required root-backed capacity through an authorized
operations task, or explicitly authorize a new storage location. Then dispatch
a fresh Task ID for the complete S=25 run. The next run must re-verify the
source hash, set a fresh `T38C_RUN_ID`, enable `T38C_BUILD_COMPLETE_DEBUG=1`,
verify `/proc/$engine_pid/environ`, and preserve all raw logs.

## Open issues

1. Root filesystem capacity is the immediate blocker: 0 bytes available.
2. No live runtime evidence exists for this r9 invocation; P0 remains neither
   accepted nor rejected on product behavior.
3. The prior R8 root/false-session-ref diagnosis was not re-tested here and
   must not be treated as repaired by the focused fixture result.

blocked
