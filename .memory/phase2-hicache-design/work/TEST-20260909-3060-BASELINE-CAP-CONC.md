# TEST-20260909-3060-BASELINE-CAP-CONC

Task ID: `TEST-3060-BASELINE-20260909`  
Orchestration epoch: `3060-P4`  
Role: `tester`  
Status: `done`

## Scope and verdict

This is an independent, read-only packaging/verification pass for the already-run
RTX 3060 Qwen3.5-4B baseline. No product files, remote model files, server
configuration, or running processes were modified. No HiCache experiment was run.

| Gate | Result | Evidence |
|---|---|---|
| P1 — checkpoint/runtime boot and one-request service smoke | PASS | All four capacity logs show weight load, graph capture, server-ready, and HTTP 200; the concurrency log shows the same. |
| P2 — capacity probes | PASS | 65K, 128K, 193K, and 226K probes all reached `pending-token: 0` and returned HTTP 200. |
| P3 — concurrency baseline | PASS | c1/c2/c4/c6/c8 all reached their target running-request count with CUDA Graph decode, queue 0, and HTTP 200 completion responses. |

The PASS results mean “the observed baseline run booted and completed its
probe requests.” They do not establish HiCache correctness, long-duration
stability, output-quality equivalence, or classic AWQ/Marlin checkpoint
compatibility.

## Exact verification commands

Repository instructions were read from `/home/dev-codex/workspaces/nerun-dev/AGENTS.md`.
The following read-only command was used against the authorized host; it did not
send a signal or start a process:

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=no \
  -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  root@i-1.gpushare.com \
  'ps -p 58991 -o pid=,ppid=,stat=,etime=,lstart=,cmd=;
   nvidia-smi --query-gpu=name,compute_cap,memory.total,memory.used,utilization.gpu --format=csv,noheader;
   stat -c "%n %s %y" /tmp/sglang3060-conc.log;
   sed -n "1,180p" /tmp/sglang3060-conc.log;
   tail -180 /tmp/sglang3060-conc.log'
```

The focused extraction command was:

```bash
for f in /tmp/sglang3060-smoke10.log /tmp/sglang3060-cap128.log \
         /tmp/sglang3060-cap192.log /tmp/sglang3060-cap256.log; do
  grep -m1 'Load weight end' "$f"
  grep -m1 'Mamba Cache is allocated' "$f"
  grep -m1 'KV Cache is allocated' "$f"
  grep -m1 'max_total_num_tokens=' "$f"
  grep -m1 'Engine startup timings' "$f"
  grep -m1 'server is fired up' "$f"
  grep 'pending-token: 0' "$f" | tail -1
  grep -c 'POST /v1/chat/completions.*200 OK' "$f"
done
grep -E 'Decode batch, #running-req: (1|2|4|6|8),' /tmp/sglang3060-conc.log
```

The endpoint check was observational only:

```bash
curl --connect-timeout 2 --max-time 3 -sS -o /dev/null \
  -w 'GET /health http=%{http_code} exit=%{exitcode}\n' \
  http://127.0.0.1:30000/health
```

## Host and process observations

- Host: `I2aff9805ac001019d1`.
- GPU: `NVIDIA GeForce RTX 3060`, compute capability `8.6`, 12288 MiB.
- At the observation time, GPU usage was 2 MiB / 0%.
- PID `58991` was absent when queried. The log records `SIGTERM received` at
  `05:26:14`, graceful drain at `05:26:15`, and exit cleanup at `05:26:16`.
  This shutdown was already present in the evidence; this verification did not
  issue it.
- Consequently, the post-run `/health` check returned connection refused
  (`HTTP 000`, curl exit 7). This is a lifecycle caveat, not a probe failure.

## Runtime/checkpoint profile

The launch log records:

- Model/tokenizer: `/hy-tmp/models/Qwen3.5-4B-AWQ`.
- TP 1; `max_running_requests=8`; `max_total_tokens=65536` for the concurrency
  run; `context_len=262144`; chunked prefill 2048; max prefill 16384.
- KV dtype: `torch.float8_e4m3fn` (`fp8_e4m3`); no scale factors were supplied,
  so the runtime logged that it defaulted scale factors to 1.0.
- CUDA Graph: prefill backend `breakable`, captured token sizes 4/8/16/32;
  decode backend `full`, captured batch sizes 1/2/4/8. Steady decode samples
  have `cuda graph: True`.
- Linear-attention/GDN path: Triton decode/prefill/verify; hybrid linear
  attention enabled; packed decode enabled.
- The checkpoint `config.json` declares `quantization_config.quant_method` as
  `compressed-tensors`, `format=pack-quantized`, INT4 (`num_bits=4`), symmetric,
  group size 128, and `quantization_status=compressed`. The launch log agrees:
  `quant=compressed-tensors`.
- Important naming caveat: the repository/model label contains `AWQ`, but this
  observed checkpoint is not a classic AWQ/Marlin checkpoint format. The log did
  emit a Marlin kernel warning during CUDA Graph capture on pre-SM90 hardware;
  that runtime kernel warning must not be rewritten as proof that the checkpoint
  itself is classic AWQ/Marlin.

## Capacity probes

Each probe was a fresh server run using the same checkpoint/runtime family and a
single long-prefill request. “Completed” below means the log reached
`pending-token: 0` and recorded `POST /v1/chat/completions ... 200 OK`.

| Probe label | Runtime `#tokens` / `max_total_num_tokens` | KV K/V allocation | Mamba allocation | Available GPU memory after sizing | Startup | Probe result |
|---|---:|---:|---:|---:|---:|---|
| 65K | 65,536 | 0.50 / 0.50 GB | max 53; conv 0.06 GB; SSM 2.53 GB | 3.61 GB | 34.45 s tokenizer end-to-end | PASS; pending 0; HTTP 200 |
| 128K | 131,072 | 1.00 / 1.00 GB | max 53; conv 0.06 GB; SSM 2.53 GB | 2.61 GB | 34.42 s tokenizer end-to-end | PASS; pending 0; HTTP 200 |
| 193K | 193,294 | 1.47 / 1.47 GB | max 53; conv 0.06 GB; SSM 2.53 GB | 1.67 GB | 34.13 s tokenizer end-to-end | PASS; pending 0; HTTP 200 |
| 226K | 225,982 | 1.72 / 1.72 GB | max 62; conv 0.07 GB; SSM 2.95 GB | 0.72 GB | 38.45 s tokenizer end-to-end | PASS; pending 0; HTTP 200 |

The exact observed files and SHA-256 fingerprints were:

```text
8734512fc07c1d631533cfb182491106515b5d8c6e08349da82a4ab7a3f699bf  /tmp/sglang3060-conc.log
c0cfae815ec73727787cfec033637aa603ab1360a3afd03d1ca3716a4f3238e9  /tmp/sglang3060-smoke10.log
4984471bfe55c08df04262609053a30a5d9581893cbddfea554045bc3ae28512  /tmp/sglang3060-cap128.log
c9ffb8b5824c5365d11e05c0b50b48c4fa3ec0a660c3816f21cb502ca701dbd3  /tmp/sglang3060-cap192.log
25fd8e52f218fe2a0f520bd95a1018979359ce226a5878b7d903ab2ff64386ff  /tmp/sglang3060-cap256.log
```

All four logs show the expected weight-load, Mamba/KV allocation, CUDA Graph
capture, server-ready, and request-completion sequence. No `out of memory`,
`OutOfMemory`, or CUDA-error text was observed. The `Traceback` text at the end
of each log is the expected Uvicorn cancellation path after the recorded
SIGTERM, not a capacity-probe error.

## Concurrency baseline

The concurrency log is `/tmp/sglang3060-conc.log`. The server configuration in
that log has `max_running_requests=8`, FP8 E4M3 KV, Mamba `extra_buffer`,
`mamba_full_memory_ratio=0.9`, and CUDA Graph decode batches 1/2/4/8.

The table uses the last non-zero steady decode sample for each target, rather
than the first ramp-up sample. All listed rows show `cuda graph: True` and
`#queue-req: 0`.

| Target concurrency | Observed `#running-req` | Mamba num | Mamba usage | Steady decode throughput (tok/s) |
|---:|---:|---:|---:|---:|
| c1 | 1 | 3 | 0.06 | 90.04 |
| c2 | 2 | 6 | 0.11 | 173.46 |
| c4 | 4 | 12 | 0.23 | 324.22 |
| c6 | 6 | 18 | 0.34 | 457.57 |
| c8 | 8 | 24 | 0.45 | 575.63 |

The log contains 22 successful chat-completion HTTP responses: one warmup plus
1+2+4+6+8 concurrency requests. The evidence proves HTTP completion and engine
throughput behavior only; it does not include an independent decoded-output
quality oracle.

## Artifacts, followups, and open issues

- Artifact: this report at
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST-20260909-3060-BASELINE-CAP-CONC.md`.
- Evidence: the five remote log files and fingerprints above; remote host/GPU,
  process, model config, and endpoint observations recorded above.
- Followup: if this baseline is used for a later HiCache comparison, rerun the
  same request trace with an explicit output-correctness oracle and preserve the
  exact checkpoint/config hash and launch command.
- Open issue: PID 58991 is no longer running, and port 30000 is currently closed;
  no live endpoint evidence can be collected without a separately authorized
  server start and a fresh Task ID.
- Open issue: the original launch shell command was not recoverable from the
  remote shell history; the effective arguments are preserved in the SGLang
  `server_args` line in `/tmp/sglang3060-conc.log`.
- Extra work requires a fresh Task ID.

## Invocation handoff

`status`: `done`  
`artifacts`: this report  
`evidence`: remote logs, hashes, server arguments, GPU/process checks, and
read-only endpoint check above  
`summary`: P1/P2/P3 PASS for the observed compressed-tensors INT4 baseline;
65K/128K/193K/226K capacity probes completed, and c1/c2/c4/c6/c8 completed
with 90.04/173.46/324.22/457.57/575.63 tok/s steady decode samples  
`followups`: preserve an exact launch script and add output-correctness checks
before comparing a future HiCache run  
`open_issues`: server exited before post-run live check; checkpoint format must
remain labeled compressed-tensors INT4, not classic AWQ/Marlin; no HiCache claim
is made

