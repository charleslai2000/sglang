# G3-CORE-UNBLOCK-20260907 remote audit

ENTRY: ACCEPT

Task ID: `G3-CORE-UNBLOCK-20260907-REMOTE-AUDIT`  
Orchestration epoch: E3  
Role: devops  
Invocation status: **done**

## Scope and method

Read-only reconciliation was performed over passwordless SSH to the explicit experimental host `root@175.155.64.171:22109`. No benchmark request, download, kill, restart, service change, product edit, or remote write was performed. The only local write is this report.

Principal command:

```text
ssh -o BatchMode=yes -o ConnectTimeout=10 -p 22109 root@175.155.64.171 'bash -s'
```

The remote script read only the named run directory `/data/qwen3-g3-baseline/prod-a/prod-a-20260907-121530/`, process trees and `/proc`, `127.0.0.1:8035` health/loads endpoints, deployed source identity, and `nvidia-smi` state. It used `find`, `sed`, `ps`, `pstree`, `curl`, `sha256sum`, `/data/sglang-qwen35-env/bin/python` for JSON parsing, and read-only `nvidia-smi` queries.

Observation window: 2026-09-07 20:36:39–20:38:49 +0800. Remote hostname: `pytorch-9802`.

## Existing run provenance

Reconciled directory:

```text
/data/qwen3-g3-baseline/prod-a/prod-a-20260907-121530/
```

Its manifest identifies:

```text
task_id=G3-PRODUCTION-A-20260907
epoch=E2
run_id=prod-a-20260907-121530
authorized_host=175.155.64.171:22109
loopback_service=http://127.0.0.1:8035
service_pid=298123
dataset_name=random-ids
random_input_len=2048
random_output_len=512
random_range_ratio=1.0
seed=42
tokenize_prompt=true
backend=sglang
points=C1/20, C4/40, C5/50
repeats_per_point=3
```

The protocol manifest records `--flush-cache` / `POST /flush_cache?timeout=60` after warmup and before every measured repeat, plus the required compatibility and dataset compatibility notes. This is a prior E2 task, not E3. Its evidence must not be copied into, combined with, or used as admission evidence for a new E3 smoke or matrix.

## Process and completeness

At the observation time the old wrapper was still active:

```text
PID 368185  PPID 1       bash /data/qwen3-g3-baseline/prod-a/prod-a-20260907-121530.sh
PID 381226  PPID 381225  /data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving
  --backend sglang --base-url http://127.0.0.1:8035
  --model /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
  --dataset-name random-ids --random-input-len 2048 --random-output-len 512
  --random-range-ratio 1.0 --request-rate inf --seed 42
  --max-concurrency 4 --num-prompts 40 --tokenize-prompt --output-details
  --output-file /data/qwen3-g3-baseline/prod-a/prod-a-20260907-121530/C4/repeat-1/result.jsonl
  --flush-cache --flush-cache-timeout 60 --warmup-requests 3
PID 381217  child of wrapper  nvidia-smi dmon -s pucvmt -d 1 -o DT
```

Top-level `progress.log` contained only:

```text
2026-09-07T12:20:29.608788262Z C1 repeat=1 rc=0
2026-09-07T12:27:52.693371481Z C1 repeat=2 rc=0
2026-09-07T12:35:17.048900284Z C1 repeat=3 rc=0
```

Point/repeat state:

| Point | Repeat 1 | Repeat 2 | Repeat 3 | State |
|---|---|---|---|---|
| C1, 20 prompts | complete, rc 0, 20/20 | complete, rc 0, 20/20 | complete, rc 0, 20/20 | Complete only as old E2 evidence |
| C4, 40 prompts | **active**, 1/40 observed | not started | not started | Incomplete; exclude |
| C5, 50 prompts | not started | not started | not started | Absent; exclude |

Each completed C1 result was parsed with the deployed interpreter and had `completed=20`, 20 empty error strings, all `input_lens=2048`, all `output_lens=512`, `total_input_tokens=40960`, and `total_output_tokens=10240`. Durations were 415.8473 s, 416.1837 s, and 416.2897 s. Each has raw result JSONL, runner stdout/stderr, server-log delta, loads snapshots, GPU telemetry, and `service-invariant.txt=pass`.

C4/repeat-1 had no `result.jsonl`, exit code, ended-at, or service-invariant file. Runner stdout showed warmup completed and the first measured request; stderr showed 1/40. Current `/v1/loads?include=all` showed `num_running_reqs=4`, `max_running_requests=5`, and `max_total_num_tokens=132436`.

## Service invariant

PID 298123 remained alive on loopback port 8035. `GET /health` returned HTTP 200. Current `/v1/loads?include=all` returned HTTP 200, version `0.5.10.dev0`, one RTX 3090, `num_running_reqs=4`, `max_running_requests=5`, `max_total_num_tokens=132436`, and memory `weight_gb=11.857`, `kv_cache_gb=4.042`, `graph_gb=1.955`.

The exact current service arguments remained:

```text
/data/sglang-qwen35-env/bin/python /data/sglang-qwen35-env/bin/sglang serve
  --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
  --host 127.0.0.1 --port 8035 --tp-size 1 --pp-size 1 --trust-remote-code
  --reasoning-parser auto --tool-call-parser qwen3_coder
  --kv-cache-dtype fp8_e4m3
  --mamba-radix-cache-strategy extra_buffer_lazy
  --default-chat-template-kwargs {"preserve_thinking": false} --log-level info
```

Direct SHA-256 of the NUL-separated `/proc/298123/cmdline` representation was:

```text
750ac48907968dacfd3175b1547a1cd8b9b89cb3eeaa5ebfd625ce221717d200
```

The current textual command line matches the saved preflight command. The old per-repeat `service-invariant.txt` files all say `pass`. The saved expected command hash `7832781e...` is over its captured command representation and is not directly comparable to the NUL-separated `/proc` hash.

## Deployed source identity

`/data/sglang-qwen35` is not a Git worktree, so no deployed Git commit is available. Read-only identity:

```text
Python: 3.12.0 (conda-forge)
SGLang: 0.5.10.dev0
source root: /data/sglang-qwen35/python
serving.py SHA-256: 01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb
artifact source-manifest SHA-256: 66d0ab65b45d72a8d0fb0fcc5835ea5b4c70956234e7021c2c857faa17ccb9ae
```

The model artifact evidence records path `/data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`, size 11,771,546,784 bytes, mtime `2026-09-06 01:29:07.432608472 +0800`, inode 10747915. No model SHA-256 was present in this existing artifact set; none was computed during this audit.

## GPU / telemetry

During active C4 traffic, a query sample reported the RTX 3090 at 100% GPU utilization, 66% memory utilization, 348.87 W / 350 W, 72 C, and 22,912 MiB / 24,576 MiB used. `nvidia-smi pmon -c 1` produced no attributable rows; a later compute-app query transiently reported PID 315744 as `[Not Found]` with 22,888 MiB before that PID disappeared. GPU exclusivity therefore cannot be proven from available attribution output; the old runner/service clearly occupy the single GPU during the audit. The old run's per-repeat dmon/query telemetry remains under its remote artifact directory.

## Admission recommendation

**Do not admit a fresh E3 smoke yet.** The old E2 wrapper is active and sending C4 traffic to the same loopback service, with the GPU at full utilization. Starting a smoke now would contaminate service/GPU state and duplicate traffic. This audit did not stop it because no kill or state change was authorized.

After an independently authorized operator confirms PID 368185 and descendants are terminal, the service is idle, and `/v1/loads?include=all` reports zero running/waiting requests, a fresh E3 smoke may use a new run ID. The old C1 outputs may remain preserved as E2 evidence, but all old-run data—including completed C1—must remain excluded from E3 smoke/matrix scorecards and must not be merged with new JSONL files.

## Selected artifact hashes

```text
manifest.txt:      710094cc919029cabf843663f9ce830032e49f19a12b9ab26e83efd51b8c108f
protocol-manifest:  402b32337abff076d92df878eb81ecac24c2784671b44c430982a25c63abf61a
progress.log:      4159345f37c0b2d4e075fce7257df7fac42d564d9871209e5c0f2aceffe34abb
C1/r1 result:      a65a32a3a1604f609b924771d933da395b725c10f5206e65bf5d905089a700a4
C1/r2 result:      69832cc8e160ddbab717a19dec06a32fbb60de4ffaf2275b07875687528a774a
C1/r3 result:      9fd7aeb8d50feb11764d9856a89dca89ed114cef14c52e387aaa78e9fef6bc6c
```

## Open issues

1. The prior wrapper must reach terminal state before E3 traffic can be admitted; stopping it requires a separate authorized execution decision.
2. GPU process attribution is incomplete; record this limitation in any fresh smoke.
3. Deployed source has no Git metadata; preserve the serving.py hash and SGLang version in the fresh smoke manifest.
4. Existing artifacts contain model stat evidence but no model SHA-256.

Final status: **done**

