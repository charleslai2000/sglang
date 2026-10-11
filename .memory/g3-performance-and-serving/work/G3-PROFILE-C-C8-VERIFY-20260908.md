# G3-PROFILE-C-C8-VERIFY-20260908

ENTRY: ACCEPT

task_id: G3-PROFILE-C-C8-VERIFY-20260908  
epoch: E4  
role: tester  
invocation_status: done  
verification_verdict: PASS_WITH_EVIDENCE_LIMITATION

## Scope and method

This was an independent, read-only verification of the completed C8 raw
artifacts. No workload was run, no product file was changed, no audit/tracing
hook was introduced, and no download or dataset access was attempted.

Remote source:

```text
/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c8-python-20260908/measure/
```

Local preserved copy:

```text
.memory/g3-baseline-20260907/work/raw/g3-profile-c8-python-20260908/
```

The remote tree and the local measured-file subset each contain 27 files; the
local copy additionally has `SHA256SUMS.txt`. SHA-256 comparison of every
measured file (excluding that local-only manifest) passed. The remote and local
hashes for the principal raw files are:

```text
raw/repeat1.jsonl  44759604dbcc23fd99fc761dd297757088593761e8ba927cbe19766fedcb38af
raw/repeat2.jsonl  6644ab4d75f22b0d6b02d21383879f6678459b93e56f296d88d6d8df15c451ff
raw/repeat3.jsonl  81aeaf95b0a28d32eb4c37b5d329eb4dbe0b2c473783e37125097e69a5d43330
repeat1.log       a187ad281e7a1d877eceb139b5295b40b43fe47ebb5668d7c0caf355445057ad
repeat2.log       f284673bc01420a027d08faec1e2fa237db35a30a0e74a4f10b1b392bc1cfc8f
repeat3.log       fe8eedf57b829431a67df53d8001d7fe430ef478964014507e708f96d667fd02
nvidia_dmon.txt   4ccb4708531c977d52f6e0a67df45b7ad5126b160a58127988178d7704cc7598
server_ps_before.txt/server_ps_after.txt
                   f54ce112db45ba2e506e8c4725af0d84680c9f5217d30d335af9da024f0f7053
```

## Service and runner invariants

The captured candidate command is the deployed interpreter and native server
on loopback port 18037, with the frozen v1 flags and only the C8 capacity
knobs changed:

```text
/data/sglang-qwen35-env/bin/python -m sglang.launch_server \
  --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --host 127.0.0.1 --port 18037 --tp-size 1 --pp-size 1 \
  --trust-remote-code --reasoning-parser auto --tool-call-parser qwen3_coder \
  --kv-cache-dtype fp8_e4m3 \
  --mamba-radix-cache-strategy extra_buffer_lazy \
  --default-chat-template-kwargs={"preserve_thinking":false} \
  --max-running-requests 8 --max-mamba-cache-size 40 \
  --cuda-graph-max-bs-decode 8 --log-level info
```

The launch identity is PID 497622. Startup `/v1/loads?include=all` and every
repeat snapshot report runner/server version `0.5.10.dev0`,
`max_running_requests=8`, `max_total_num_tokens=54093`, and memory fields:
weights 11.857 GB, KV cache 1.651 GB, graph 1.936 GB, token capacity 54093.
Snapshots are idle (`num_running_reqs=0`, `num_waiting_reqs=0`,
`num_used_tokens=0`) before and after each repeat. HiCache is disabled
(`hicache_size=0`, `enable_hierarchical_cache=false`); HiCache device/host/
storage fields are therefore N/A.

Every runner log records the same native command shape:

```text
/data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving \
  --backend sglang --base-url http://127.0.0.1:18037 \
  --dataset-name random-ids --tokenize-prompt \
  --random-input-len 1024 --random-output-len 256 \
  --random-range-ratio 1.0 --request-rate inf --seed 42 \
  --max-concurrency 8 --num-prompts 64 --output-details \
  --flush-cache --flush-cache-timeout 60 --warmup-requests 0
```

Streaming and ignore-EOS disable flags were omitted. The logs show
`dataset_name=random-ids`, `tokenize_prompt=True`, fixed ratio `1.0`, seed 42,
and `request_rate=inf`; all measured output files are the native runner's raw
JSONL results. The runner reports `completed=64`, 64 input lengths exactly
1024, 64 output lengths exactly 256, and 64 empty error strings in each
repeat. Thus the measured total is 192/192 successful requests, 196608 input
tokens, and 49152 requested output tokens, with no HTTP error, timeout, or
zero-progress marker.

## Repeat outcomes

| repeat | warmup arg | RC | completed | duration s | output tok/s | total tok/s | observed avg concurrency | TTFT p50/p95/p99 ms | TPOT p50/p95/p99 ms | full-turn p50/p95/p99 ms |
|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| 1 | 0 | 0 | 64/64 | 447.480 | 36.6139 | 183.0696 | 7.9868 | 8213.47 / 11530.33 / 11596.96 | 185.98 / 206.64 / 212.00 | 55985.23 / 56010.04 / 56011.52 |
| 2 | 0 | 0 | 64/64 | 448.166 | 36.5579 | 182.7896 | 7.9866 | 8974.25 / 11531.59 / 11680.63 | 184.35 / 206.60 / 208.20 | 55987.13 / 56009.13 / 56009.75 |
| 3 | 0 | 0 | 64/64 | 448.425 | 36.5368 | 182.6838 | 7.9856 | 8988.59 / 11573.59 / 11745.94 | 184.44 / 206.74 / 208.21 | 56017.67 / 56038.14 / 56039.33 |

The repeat-3 completed value in the table above is 64/64; its raw summary
contains the same `completed=64` value as repeats 1 and 2. The median
aggregate output throughput across the three repeats is **36.5579 tok/s**;
median total throughput is **182.7896 tok/s**. No prefill/decode-specific
throughput field was emitted by this runner, so those fields remain N/A.
Retokenized output totals are preserved as reported (15933, 15858, 15858)
and are not substituted for the requested output totals.

The runner's `max_concurrent_requests`/“Peak concurrent requests” field is 16
in all three summaries, which conflicts with the server admission cap of 8
and the measured average occupancy of approximately 7.986. It is retained as
a runner anomaly and is not interpreted as actual service concurrency. The
service's effective measured concurrency is therefore C8 by admission and
average occupancy, not the anomalous peak field.

## Cache flush and warmup

All three measured invocations explicitly set `--flush-cache` and
`--flush-cache-timeout 60`. The before-repeat snapshots are idle and show zero
used tokens, and the runner exited successfully after every invocation. This
supports the requested flush-before-each-repeat sequence. The preserved raw
files do not include a separate HTTP response/status capture for each flush;
the flush endpoint response is therefore an evidence limitation, not a
fabricated success claim.

All C8 measured invocations use `--warmup-requests 0`. CUDA graph/kernel
warmup was completed during the launch gate, but this artifact set does not
support a claim of three explicit warmup requests immediately before repeat
1. That limitation is recorded rather than inferred away.

## GPU telemetry

The raw 1-second `nvidia-smi dmon -s pucvmt` stream contains 1339 numeric
samples. Three sustained high-load windows are present, each 427 samples and
aligned with the three measured repeats. Parsed window summaries are:

| repeat window | samples | power avg/min-max W | temp avg/min-max C | SM avg/min-max % | MEM avg/min-max % | FB avg/min-max MiB |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 427 | 345.91 / 187-349 | 70.96 / 48-74 | 99.94 / 94-100 | 61.81 / 26-71 | 23027.57 / 22844-23028 |
| 2 | 427 | 346.04 / 236-349 | 71.79 / 63-73 | 99.96 / 93-100 | 61.82 / 26-70 | 23027.57 / 22844-23028 |
| 3 | 427 | 345.86 / 245-349 | 71.74 / 63-73 | 100.00 / 100-100 | 61.51 / 27-70 | 23027.57 / 22844-23028 |

Raw query samples are preserved before, after, and after each repeat. The
recorded endpoint rows show 22846 MiB framebuffer before the run and 23028
MiB after repeat 1, repeat 2, and repeat 3 (the complete CSVs remain raw in
the artifact tree). No unavailable per-kernel or bandwidth value is inferred.

## Comparison with independently verified C1/C6

Using the independently verified reports in the same task bus:

| point | median aggregate output tok/s | median TTFT ms | median TPOT ms | median full-turn ms |
|---|---:|---:|---:|---:|
| C1 | 33.9076 | 4754.20 | 99.47 | 30205.26 |
| C6 | 34.9597 | 6123.76 | 159.57 | 43965.60 |
| C8 | 36.5579 | 8974.25 | 184.44 | 55987.13 |

C8 is only **+4.6%** over C6 and **+7.8%** over C1 in aggregate output
throughput, while median TTFT is approximately **+46.5%** over C6 and
**+88.0%** over C1. Median TPOT rises approximately **+15.6%** over C6.
This supports a throughput plateau from C6 to C8 under the fixed 1024/256
workload, with materially worse latency; it does not support claiming strong
batch scaling.

## Evidence limitations and verdict

1. The C8 raw tree has no separate model-sha256 artifact. The server model
   path and GGUF load identity are captured, but this verification does not
   independently claim a C8-specific model digest.
2. Flush endpoint response bodies/statuses are not separately captured;
   `--flush-cache` is present on all three commands and before snapshots are
   idle/empty.
3. C8 used `warmup_requests=0`; launch graph/kernel warmup is evidenced, but
   the stronger three-explicit-request warmup contract is not evidenced.
4. Runner peak concurrency 16 is inconsistent with the server cap 8 and is
   not treated as actual service concurrency.
5. The runner emitted a non-fatal post-success
   `multiprocess.resource_tracker` `RLock._recursion_count` traceback in all
   three logs. All three return codes are 0 and all 192 requests completed;
   this is recorded as runner shutdown noise, not hidden.

Independent verdict: **PASS_WITH_EVIDENCE_LIMITATION** for the C8 measured
workload, service invariants, 3-repeat outcomes, and preserved raw telemetry.

Final status: **done**
