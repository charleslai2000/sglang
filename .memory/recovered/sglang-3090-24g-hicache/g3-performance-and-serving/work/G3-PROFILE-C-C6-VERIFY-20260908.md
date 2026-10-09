# G3-PROFILE-C-C6-VERIFY-20260908

ENTRY: ACCEPT

task_id: G3-PROFILE-C-C6-VERIFY-20260908
epoch: E4
role: tester
invocation_status: done
verification_verdict: PASS_WITH_EVIDENCE_LIMITATION

## Scope and method

This was an independent, read-only verification. No workload was launched, no
product file was changed, and no audit/tracing hook or additional telemetry
process was introduced.

Authorized remote artifact tree:

```text
/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c6-equals-20260908/
```

Local preserved copy:

```text
.memory/g3-baseline-20260907/work/raw/g3-profile-c6-equals-20260908/
```

The complete local `measure/` tree was copied from the named remote directory.
The remote and local SHA-256 lists for all 33 measure files matched exactly
(`HASH_COMPARE=PASS`). Missing launch telemetry files were also copied locally
(`gpu-apps.csv`, `gpu-query.csv`, and `server.log`).

## Service and workload invariants

Launch artifacts identify candidate PID `488839` on loopback port `18036`:

```text
/data/sglang-qwen35-env/bin/python -m sglang.launch_server \
  --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --host 127.0.0.1 --port 18036 --tp-size 1 --pp-size 1 \
  --trust-remote-code --reasoning-parser auto --tool-call-parser qwen3_coder \
  --kv-cache-dtype fp8_e4m3 \
  --mamba-radix-cache-strategy extra_buffer_lazy \
  --default-chat-template-kwargs={"preserve_thinking":false} \
  --max-running-requests 6 --max-mamba-cache-size 32 \
  --cuda-graph-max-bs-decode 8
```

The launch gate and `/v1/loads?include=all` identify weights `11.857 GB`, KV
cache `2.798 GB`, graph memory `1.936 GB`, `max_total_num_tokens=91677`,
`max_running_requests=6`, and `token_capacity=91677`. The served model is GGUF
with KV dtype `fp8_e4m3`; `hicache_size=0` and hierarchical cache is disabled.
The recorded model digest is:

```text
64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810  Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
```

All three runner logs independently record runner version `0.5.10.dev0` and
the same native command shape:

```text
/data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving \
  --backend sglang --base-url http://127.0.0.1:18036 \
  --dataset-name random-ids --tokenize-prompt \
  --random-input-len 1024 --random-output-len 256 \
  --random-range-ratio 1.0 --request-rate inf --seed 42 \
  --max-concurrency 6 --num-prompts 48 --output-details \
  --flush-cache --flush-cache-timeout 60 --warmup-requests 0
```

Streaming and ignore-EOS disable flags were omitted. Each JSONL has exactly 48
input lengths, all `1024`, and 48 output lengths, all `256`. Each repeat has
`completed=48`, zero non-empty error strings, and RC 0. Across measured
repeats this is `144/144` successful requests, `147456` input tokens, and
`36864` requested output tokens. There are no HTTP errors, timeout markers, or
zero-progress signals. The only recurring stderr is a post-success
`multiprocess.resource_tracker` destructor traceback; it does not change RC 0.

## Repeat outcomes

| repeat | warmup arg | RC | completed | duration (s) | output tok/s | total tok/s | measured concurrency | TTFT p50/p95/p99 (ms) | TPOT p50/p95/p99 (ms) | full-turn p50/p95/p99 (ms) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 0 | 48/48 | 350.678 | 35.0407 | 175.2033 | 5.99 | 6127.48 / 8662.38 / 8663.70 | 148.15 / 161.31 / 164.29 | 43901.00 / 43942.39 / 43943.52 |
| 2 | 0 | 0 | 48/48 | 351.764 | 34.9325 | 174.6627 | 5.99 | 6121.96 / 8712.39 / 8738.15 | 148.40 / 159.58 / 161.59 | 43965.60 / 43981.88 / 43983.43 |
| 3 | 0 | 0 | 48/48 | 351.490 | 34.9597 | 174.7986 | 5.99 | 6123.76 / 8718.30 / 8747.37 | 148.38 / 159.57 / 161.67 | 43960.46 / 43974.17 / 43975.27 |

Median aggregate output throughput across repeats is **34.9597 tok/s**; median
total throughput is **174.7986 tok/s**. Median repeat output throughput is
`35.0407 / 34.9325 / 34.9597` tok/s. Runner aggregate concurrency is
`5.99 / 5.99 / 5.99`, consistent with nominal C6 and the service admission
cap. The runner also reports peak concurrent requests `12` in every repeat;
that field is inconsistent with nominal C6 and the server cap and is retained
as a runner anomaly, not interpreted as actual service concurrency.

No prefill/decode-specific throughput fields were emitted. They remain
unavailable and were not inferred. Retokenized output totals are preserved in
the raw JSONL and differ from requested output totals; this is not treated as
a request failure.

## Cache flush and warmup verification

Every measured invocation has `flush_cache=True` and
`flush_cache_timeout=60.0`. In this checkout, the documented `sglang` path
performs `POST /flush_cache?timeout=60` and raises on a non-2xx response; this
is the implementation in `python/sglang/benchmark/serving.py` at the deployed
runner version. The measured runner exited RC 0 and produced all requests,
which supports successful flush handling. The runner does not print the HTTP
response body/status, so a separate per-repeat endpoint response capture is not
available in the preserved raw artifacts.

The C6 measured repeats explicitly use `--warmup-requests 0`; CUDA graph and
kernel warmup occurred during the candidate launch gate. The artifacts do not
contain three explicit warmup requests immediately before repeat 1. Therefore
the measured data is valid for the recorded runner invocation, but the exact
stronger “three request warmup before repeat 1” claim is not supported for this
C6 run and must not be silently inferred.

The before/after load snapshots are idle and report `num_used_tokens=0` at
the snapshots. The regular radix cache was requested to flush between repeats;
HiCache device/host/storage fields are **N/A** because HiCache is disabled.

## GPU telemetry

Raw one-second `nvidia-smi dmon -s pucvmt` streams are preserved for all three
repeats. Numeric sample summaries over each raw stream (including its small
startup/tail portions) are:

| repeat | rows | power avg/min-max (W) | temp avg/min-max (C) | SM avg/min-max (%) | MEM avg/min-max (%) | FB avg/min-max (MiB) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 353 | 329.8 / 26-349 | 69.0 / 33-73 | 94.5 / 0-100 | 59.0 / 0-71 | 23000.2 / 22688-23010 |
| 2 | 355 | 333.9 / 71-350 | 71.0 / 52-74 | 94.1 / 0-100 | 59.1 / 0-71 | 23008.1 / 22688-23010 |
| 3 | 354 | 335.0 / 71-349 | 71.1 / 54-74 | 94.7 / 0-100 | 59.0 / 0-71 | 23008.3 / 22688-23012 |

These are summaries of the preserved raw streams, not fabricated in-flight
instantaneous values. Raw query samples and `/v1/loads` snapshots remain in the
artifact tree.

## Comparison with independently verified C1

The independently verified C1 report records median aggregate output
throughput `33.9076 tok/s`, median TTFT `4754.20 ms`, median TPOT `99.47 ms`,
and median full-turn latency `30205.26 ms`. C6 therefore changes aggregate
output throughput by only approximately **+3.1%** (`34.9597 / 33.9076 - 1`),
while median TTFT rises approximately **+28.8%** and median TPOT approximately
**+49.2%**. This is evidence of a throughput plateau by C6 under this
1024/256 workload; it is not evidence that C6 materially scales aggregate
decode throughput.

## Artifact hashes

Key local SHA-256 values (the complete local/remote measure tree comparison
passed) are:

```text
72159d670406555e948905f191e28f988ed39a6cd30e9c8d23f7b9e4c1a33bc8  measure/repeat1/runner.jsonl
af772f099016305bd23014ce9e2d4e81b64e6af80ee7d136b360608b294ff686  measure/repeat2/runner.jsonl
b3883c5bba1eccde38d85bc86cda01eb56bdf3630eaeb66dea5e9d38c8701ce5  measure/repeat3/runner.jsonl
432270324aca68acdf98448db60811669dc750d6a152b427f2e5c770a67a4bfd  measure/repeat1/nvidia_dmon.txt
cf551f3546145fa057e10f5bedc1f3ad302dc460517daf5f618d61b0016a8ae4  measure/repeat2/nvidia_dmon.txt
fab06921807a81b53924a9f7b783dca0154d6cecb1153545acf157cc196fc069  measure/repeat3/nvidia_dmon.txt
97c515db1d1809a1edf3c7b2a4081ac8f67fc80cfb26091780c5086c05133c9b  launch/proc.cmdline
573f6bcafb442ea0c406f1a14d9fdab5d37c98501e5b0ac4047806752186482d  launch/gate-lines.txt
64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810  model-sha256.txt content
```

The raw remote directory remains authoritative at
`/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c6-equals-20260908/`.

## Independent verdict

**PASS_WITH_EVIDENCE_LIMITATION** for the C6 measured workload and three
repeat outcomes: the requested random-ids fixed lengths, exact 144/144
completion count, nominal/observed C6 concurrency, runner metrics, and raw
telemetry are independently supported. The two limitations are (1) the run
used `warmup_requests=0` rather than an explicit three-request warmup, and (2)
flush endpoint HTTP responses were not separately captured even though the
runner's documented `--flush-cache` path was enabled and all runs exited 0.
The peak-concurrency value `12` is a retained runner anomaly and must not be
used as the service's actual concurrency.

At the read-only verification time, a later direct host check found neither
candidate nor restored v1 listening on ports 18036/8035. This is a transient
post-run service-state observation, not a claim about the measured requests;
the launch/measure/postflight artifacts are preserved for the parent restore
gate to reconcile.

Follow-up: parent may use the C6 result as evidence of the C4-to-C6 plateau,
but should not claim a strict three-request C6 warmup contract without a fresh
authorized run.

Final status: **done**
