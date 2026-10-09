# G3-PROFILE-C-PREFLIGHT-20260908

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: G3-PROFILE-C-PREFLIGHT-20260908
epoch: E4
role: devops

## Result

**Preflight: FAIL (fail closed).** The v1 service, identity, runner, sidecar,
disk, and candidate-port checks passed, but the GPU-owner gate did not: the
driver's compute-app query persistently reports PID `483639` using 22,776 MiB
with process name `[Not Found]`, while `/proc/483639` is absent. `fuser`
attributes the open NVIDIA device handles to the v1 tree (`462700`,
`462794`, `462795`), but the stale/unknown driver entry cannot be explained
or cleared within this read-only task. C1 must not launch until a fresh task
resolves and re-verifies this condition.

No service transition, signal, launch, benchmark request, dmon, reset,
download, remote write, source/model edit, audit, tracing, or instrumentation
was performed. Remote access used only `root@175.155.64.171` with SSH port
`22109`.

## Evidence

Fresh local raw evidence and hashes:

`/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s/.memory/g3-baseline-20260907/work/raw/g3-profile-c-preflight-20260908T181900Z/`

- `remote_snapshot.txt`: process/listener snapshot, health/loads/models,
  GPU summary, disk, memory, and candidate port probes.
- `gpu_owner_recheck.txt`: repeated GPU queries, `/proc` check, service tree,
  NVIDIA file-descriptor ownership, and stale watcher details.
- `identity_readiness2.txt`: tokenizer sidecar hashes/readiness and PATH.
- `identity_readiness.txt`: retained first identity attempt; it timed out
  after model MD5/tokenizer stat while attempting an unnecessary GGUF glob
  hash. It is not used as a pass criterion.
- `owner_log_port_recheck.txt`: `fuser`, allocation/startup log lines,
  repeated idle health/loads, and selected-port probe.
- `recent_log_connections.txt`: recent log context and active 8035 socket
  check.
- `SHA256SUMS`: hashes for every raw evidence file.

The input plan, v1 restore report, and Profile-B OOM diagnosis were read:

- `.memory/g3-baseline-20260907/work/G3-PROFILE-C-PLAN-20260908.md`
- `.memory/g3-baseline-20260907/work/G3-E3-V1-RESTORE-20260908.md`
- `.memory/g3-baseline-20260907/work/G3-E3-PROFILE-B-OOM-DIAG-20260908.md`
- `.memory/g3-baseline-20260907/work/G3-RUNNER-OOM-FIX-SETTLE-20260907.md`

## Check results

| Check | Result | Observed evidence |
|---|---|---|
| v1 listener/PID | PASS | PID `462700`, listener `127.0.0.1:8035`, children `462793/462794/462795`; exact cmdline in `remote_snapshot.txt` and `gpu_owner_recheck.txt`. |
| v1 health and idle loads | PASS | `/health` HTTP 200; `/v1/loads?include=all` HTTP 200, `num_running_reqs=0`, `num_waiting_reqs=0`, `max_running_requests=5`, `max_total_num_tokens=132436`, `utilization=0.0`. |
| Frozen parser/tool/KV/Mamba/template flags | PASS | Actual PID cmdline contains `--reasoning-parser auto`, `--tool-call-parser qwen3_coder`, `--kv-cache-dtype fp8_e4m3`, `--mamba-radix-cache-strategy extra_buffer_lazy`, and `--default-chat-template-kwargs {"preserve_thinking": false}`. |
| Model/source/runner identity | PASS | Model size `11771546784`, MD5 `a37cff66ad81b0e6311d4b6671ac2b09`; `server_args.py` SHA-256 `aba8af3f6ee28ea3216bef7e6488683bb60ac03cec6cd511e01041c304e5fcb9`; settled `serving.py` SHA-256 `01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb`. |
| GGUF-safe runner/tokenizer sidecar | PASS | Runner `/data/sglang-qwen35/python/sglang/benchmark/serving.py`; deployed interpreter `/data/sglang-qwen35-env/bin/python`; sidecar `/data/models/Qwen3.8-27B-GSQ-RCO-GGUF` has readable `tokenizer.json`, `tokenizer_config.json`, and `config.json` with hashes in `model_tokenizer_readiness2.txt`. Settled no-client-GGUF-load evidence is in the referenced runner-settle report. |
| Exact v1 restore command/PATH readiness | PASS | `/data/qwen3-g3-baseline/e3-profile-b/g3-e3-profile-b-20260907T170803Z/restore/v1.command` SHA-256 `69f80370e67d3e8e4c364ee847c1ef914641567a07dfc1ba2edb882909d70007`; current PATH includes `/opt/cuda-conda/bin:/data/sglang-qwen35-env/bin:...`; interpreter and `sglang` resolve under `/data/sglang-qwen35-env/bin`. |
| GPU utilization/headroom | PASS as observation | RTX 3090 `0%` utilization, `22800 MiB / 24576 MiB` used, `1325 MiB` free. This is current v1 idle state, not candidate headroom approval. |
| GPU owner attribution/no stale owner | **FAIL** | `fuser` attributes `/dev/nvidia*` to `462700/462794/462795`, but five repeated `nvidia-smi --query-compute-apps` samples report `483639, [Not Found], 22776`; `/proc/483639` is absent and normal NVIDIA process table says no running processes. |
| Benchmark/dmon/query clients | PASS with caveat | No active `sglang.benchmark`, dmon, or sampler client appears in the process/socket evidence. Historical stale watcher loops remain (`13105`, `13252`, `15369`, `66834`, `69607`) but are shell waiters, not GPU owners or active benchmark clients; they were not touched. |
| Artifact disk | PASS | `/data` has `149467792 KiB` available (about 142 GiB), well above the 5 GiB minimum. |
| Candidate loopback port | PASS snapshot | Selected free port: **18035**. `ss` showed no listener at `2026-09-07T18:22:44Z`; no bind/reservation was attempted. |

## Plan binding confirmation

The plan's conservative tuples are confirmed without conflict:

```text
C1: (max_running_requests, max_mamba_cache_size, cuda_graph_max_bs_decode) = (4, 20, 4)
C2: (6, 30, 6)
C3: (8, 40, 8)
C4: (10, 48, 8)  # optional only after a fresh decision
```

The fixed workload assumptions are also confirmed: `ISL=1024`, `OSL=256`,
`seed=42`, `random-range-ratio=1.0`, native `random-ids`, and
`--tokenize-prompt`. The plan records the required note that ISL 1024 is
reused from prior B decode and has no new user binding. No Profile-B pool64/C16
or Profile-C pool64/C16 work was performed, and C1 was not launched.

## Observed facts versus hypothesis

Observed: PID `483639` is absent from `/proc`, the stale `[Not Found]` GPU
record persists across five one-second queries, normal `nvidia-smi` process
listing reports no running processes, and `fuser` sees NVIDIA handles held by
the live v1 process tree. Observed v1 health/load state is healthy and idle.

Hypothesis only: the `[Not Found]` entry is stale driver/process accounting,
not an additional live GPU owner. This cannot be accepted as fact without a
new authorized diagnostic or service transition. The terminal gate therefore
fails closed rather than treating `fuser` attribution as sufficient.

## Followups and open issues

Followup: issue a fresh Task ID to the appropriate operational owner to
resolve/recheck the stale GPU record, preserving the healthy v1 service and
using an explicitly authorized rollback/verification procedure. After the
owner gate is clean, rerun this read-only preflight before any C1 transition.

Open issues:

1. Persistent unknown GPU record `483639` prevents Profile-C admission.
2. Five unrelated legacy shell watcher loops remain on the host; they have no
   observed GPU handles, but their ownership/lifecycle is outside this task.
3. Selected port `18035` was free only at the snapshot; it must be rechecked
   immediately before any future launch.

Final status: **done; preflight FAIL**.
