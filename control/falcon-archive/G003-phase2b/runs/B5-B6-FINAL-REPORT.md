# B5/B6 Final Report

## Decision

```text
B5: PASS
B6: COMPLETE
```

B5 passed the formal correctness/stability/cache gates. B6 completed the
requested HiCache OFF vs ON comparison using the same 1000-request materialized
trace. No further phase was started.

## B5 correctness/stability

Configuration:

```text
Falcon-H1-7B-Instruct-GPTQ-Int4
RTX 3090 24GB
Mamba extra_buffer, BF16
prefill CUDA graph disabled
decode CUDA graph full
HiCache ON, ratio=2, write_through, FULL + MAMBA
L3/storage OFF
max concurrency=16
seed=20260921
```

Workload:

```text
200 logical sessions
5 turns/session
1000 total turns
append-only actual chat-template history
```

Acceptance:

```text
HTTP completed: 1000/1000
errors: 0
oracle correct: 1000/1000
wrong session codes: 0
missing codes: 0
```

Cache counters:

```text
device_hit: 1,959,273 tokens
host_hit: 6,982 tokens
FULL/KV H→D: 1,862 tokens
MAMBA H→D: 6 states
FULL/KV D→H backup: 476,072 tokens
MAMBA D→H backup: 489 states
device evictions: 363,590 tokens
KV host-pressure drops: 0
MAMBA host-pressure drops: 0
```

No CUDA error, scheduler crash, deadlock, OOM, or cross-session contamination
was observed. The short-code oracle checked every response.

## B6 method

The exact B5 trace was materialized into `trace.json` with all 1000 tokenized
prompts, session IDs, turns, and submission sequence. OFF and ON used the same
trace, seed, prompt IDs, generation parameters, concurrency, and request order.

Each condition:

```text
1 warmup
3 measured repetitions
```

The first OFF server lifetime reached the execution harness's 600-second
background lifetime after OFF rep1; this was not a model/runtime failure (the
server log had no CUDA/OOM/traceback evidence). OFF rep2 and rep3 were completed
in a fresh identical server lifetime. ON had the same harness-lifetime split:
ON warmup/rep1 completed, then ON rep2/rep3 completed in a fresh identical
server lifetime. Only measured reps are reported below.

## B6 OFF vs ON: measured means

| Metric | HiCache OFF | HiCache ON | ON vs OFF |
|---|---:|---:|---:|
| Wall time / trace | 229.561 s | 229.514 s | -0.02% |
| Mean TTFT / prefill latency | 2.2773 s | 2.2819 s | +0.20% |
| Mean queue time | 1.0269 s | 1.0718 s | +4.37% |
| Mean end-to-end request latency | 3.6370 s | 3.6364 s | -0.02% |
| Mean prefill throughput* | 1141.27 tok/s | 1138.95 tok/s | -0.20% |
| Mean decode throughput** | 10,675,736 tok/s | 10,458,362 tok/s | -2.04% |
| Aggregate throughput | 11,365.60 tok/s | 11,368.03 tok/s | +0.02% |

`*` Prefill throughput is total logical prompt tokens divided by the sum of
per-request prefill/TTFT intervals; it is not a scheduler aggregate throughput
counter. `**` The response `decode_throughput` field is retained as reported by
the runtime; its absolute value is not physically plausible for a human-scale
aggregate and should be treated as a relative instrumentation field only.
Wall-clock aggregate throughput and latency are the reliable comparison.

All six measured repetitions completed:

```text
OFF: 1000/1000 correct in rep1, rep2, rep3
ON:  1000/1000 correct in rep1, rep2, rep3
```

## Cache movement evidence

OFF measured means:

```text
device_hit: 1,955,948 tokens
host_hit: 0
H→D: none
```

This is expected: HiCache OFF still uses the local device radix cache, hence
positive L1/device hits, but has no host-tier movement.

ON measured means:

```text
device_hit: 1,962,306 tokens
host_hit: 2,316 tokens
FULL/KV H→D: 1,315 tokens average per rep
MAMBA H→D: 2 states average per rep
```

The ON repetitions also recorded substantial D→H backup and device eviction;
all host-pressure drops were zero. Host hits and H→D are workload-dependent
across repetitions: ON rep1 had host_hit=2304 and H→D=256 KV/+2 MAMBA, rep2
had host_hit=4643 and H→D=1059 KV/+4 MAMBA, while rep3 had no host hit or
restore despite remaining correct.

## Runtime stability

```text
B5: 1000/1000 correct, no errors
B6 OFF measured reps: 3/3 complete, 1000/1000 correct each
B6 ON measured reps: 3/3 complete, 1000/1000 correct each
CUDA/runtime/OOM/deadlock evidence: none
```

GPU utilization, power, VRAM, and CPU/DRAM traffic were not captured by the
existing request/metrics artifacts. No values are invented here. The available
runtime metrics provided cache counters and request metadata only.

## Recommendation

For this exact 200-session/1000-turn trace, HiCache ON is correctness-safe and
has neutral aggregate wall-clock performance within measurement noise:

```text
aggregate throughput: +0.02%
mean e2e latency: -0.02%
mean TTFT: +0.20%
```

The trace is not evidence of a material performance gain. It does provide
realistic host-tier backup, host-hit, and FULL/MAMBA restore evidence under ON.
Production enablement remains a policy decision; based on this benchmark alone,
recommend enabling HiCache only when its capacity/churn benefit is required,
not for expected throughput improvement.

## Artifacts

```text
runs/formal-b5-final/b5.json
runs/formal-b5-final/trace.json
runs/b6-off/rep1/rep1.json
runs/b6-off/rep2/rep2.json
runs/b6-off/rep3/rep3.json
runs/b6-on/rep1/rep1.json
runs/b6-on/rep2/rep2.json
runs/b6-on/rep3/rep3.json
control/G003-phase2b-hicache/formal_trace_run.py
control/G003-phase2b-hicache/materialize_b6_trace.py
```
