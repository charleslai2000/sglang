# Phase 2A — Mamba 5-slot to 4-slot

## Verdict

```text
PASS: extra_buffer_lazy correctness, accounting, lifecycle churn
NO THROUGHPUT WIN: do not advance to experimental 3-slot based on this run
```

The experiment used the fixed GPTQ checkpoint, BF16 Mamba state, context 8192,
eager/disabled prefill CUDA graph, full decode CUDA graph, radix cache on,
HiCache off, speculative decoding off, overlap scheduler on, and no
`SGLANG_OPT_MAMBA_SKIP_DECODE_LOCK`.

## Safe baseline and control

Control startup logs:

```text
strategy: extra_buffer
max_mamba_cache_size: 83
Mamba cache: 0.07 GB conv + 5.41 GB SSM
state slots/request: 5
max_running_requests: 16
KV cache: BF16, 145386 tokens, K=3.05 GB, V=3.05 GB
prefill graph: disabled
decode graph: full, captured bs 1/2/4/8/12/16
```

Canonical semantic gate passed:

```text
France: The capital of France is Paris...
2+3: 5<|im_end|>\n
sentinel: FALCON_SENTINEL_7B<|im_end|>\n
```

The 20 sequential-request gate passed. All requests at c=1, 4, 8, 16,
20, and 24 returned successfully in the baseline probe; no token-id-0
corruption, CUDA error, scheduler crash, or decode-graph regression was
observed.

## Candidate accounting

Candidate startup logs explicitly resolved:

```text
strategy: extra_buffer_lazy
max_mamba_cache_size: 83
Mamba cache: 0.07 GB conv + 5.41 GB SSM
state slots/request: 4
max_running_requests: 20
KV cache: BF16, 145386 tokens, K=3.05 GB, V=3.05 GB
prefill graph: disabled
decode graph: full, captured bs 1/2/4/8/12/16/20
```

This is runtime evidence, not CLI-only evidence: both the resolved
`server_args` and the cap warning agree on `extra_buffer_lazy`, 4 slots per
request, and effective cap 20.

## Candidate correctness and lifecycle

Canonical prompts and ten deterministic prompts were run through the
correctness probe. The canonical outputs matched the baseline. The 20
sequential-request gate passed.

The 100-request mixed-length churn test ran at concurrency 20, with a fixed
sentinel request every tenth request. Result:

```text
completed: 100
failed: 0
sentinel/state contamination observed: no
slot leak or scheduler crash: no
CUDA/runtime errors: no
```

Decode scheduler logs continued to show `cuda graph: True`.

## Active/queue telemetry

HTTP completion counts were not used as active-capacity evidence. The
scheduler logs were used instead.

Control (`extra_buffer`) showed:

```text
effective max_running_requests: 16
c=20/c=24 workload: #running-req reached 16
queued requests: nonzero while the 16-request state cap was occupied
mamba state usage: mamba num up to 50 in observed mixed batches;
                 mamba usage up to 0.60 of the 83-state pool
```

Candidate (`extra_buffer_lazy`) showed:

```text
effective max_running_requests: 20
c=20 workload: #running-req reached 20; #queue-req reached 4/5 during admission
c=24 workload: #running-req reached 20; #queue-req was nonzero (up to 17
               in mixed-length phases)
mamba state usage: mamba num up to 43 in observed mixed batches;
                 mamba usage up to 0.52 of the 83-state pool
```

The exact instantaneous `#running-req` and `#queue-req` values are preserved
in the server logs. The startup cap and state-slot accounting are the primary
capacity evidence; scheduler telemetry confirms that requests beyond 16/20
queue rather than increasing active capacity.

## Throughput methodology

The control and candidate used the same generated workload definitions,
request order, prompt lengths, generation parameters, concurrency list, and
fixed warmup. Each workload contained 24 requests, and both configurations
were measured at c=1/2/4/8/12/16/20/24.

Generation parameters were identical:

```text
temperature=0
top_p=1
skip_special_tokens=false
decode-heavy max_new_tokens=128
agent-like max_new_tokens=64
```

The request set was fixed in `churn_and_workload.py`; no cache-specific
workload optimization was introduced. The 24-request throughput runs were
submitted in the same order for both configurations. The recorded per-request
elapsed time is request latency, not a separately instrumented first-token
latency.

The recorded elapsed times and aggregate output-token throughput were:

### Decode-heavy — approximately 256–512 input tokens, 128 output tokens

| c | control tok/s | lazy tok/s | lazy delta |
|---:|---:|---:|---:|
| 1 | 64.8 | 67.1 | +3.5% |
| 2 | 104.5 | 117.6 | +12.5% |
| 4 | 206.6 | 196.7 | -4.8% |
| 8 | 371.2 | 337.6 | -9.1% |
| 12 | 485.7 | 454.2 | -6.5% |
| 16 | 465.5 | 412.1 | -11.5% |
| 20 | 472.5 | 443.1 | -6.2% |
| 24 | 495.1 | 474.2 | -4.2% |

Approximate saturation was already visible around c=12–16. Increasing the
control from 16 to queued c=20/24 did not produce a reliable throughput gain.
The candidate's extra active capacity also did not produce a gain and was
slower at c=16–24 in this run.

### Agent-like — approximately 2K input tokens, 64 output tokens

| c | control tok/s | lazy tok/s | lazy delta |
|---:|---:|---:|---:|
| 1 | 48.5 | 50.0 | +3.2% |
| 2 | 82.4 | 83.3 | +1.2% |
| 4 | 127.0 | 107.0 | -15.8% |
| 8 | 224.6 | 220.0 | -2.0% |
| 12 | 286.4 | 235.7 | -17.7% |
| 16 | 352.2 | 341.2 | -3.1% |
| 20 | 360.4 | 301.9 | -16.2% |
| 24 | 396.3 | 312.4 | -21.2% |

This workload was still improving through c=16 and showed some additional
control throughput at c=20/24, but the lazy candidate did not reproduce that
benefit. These single-run measurements are sufficient to reject the claim
that 4-slot lazy mode is an observed throughput improvement here; they are not
a performance-tuning authorization.

## Artifacts

```text
runs/control-extra-buffer/server.log
runs/control-extra-buffer/baseline.json
runs/control-extra-buffer/throughput.json
runs/control-extra-buffer/throughput.stdout
runs/candidate-extra-buffer-lazy/server.log
runs/candidate-extra-buffer-lazy/correctness.json
runs/candidate-extra-buffer-lazy/throughput-churn.json
runs/candidate-extra-buffer-lazy/throughput-churn.stdout
run_probe.py
churn_and_workload.py
```

## Measurement limitations

The preserved runs include per-request elapsed latency, aggregate output-token
throughput, server-side prefill/decode throughput, and scheduler telemetry.
They do not include a separate TTFT p50/p95 series or a synchronized
GPU-utilization sampler. Those fields are therefore not fabricated in this
report. The acceptance decision is based on the required accounting,
correctness, churn, queue behavior, and aggregate throughput comparison.

## Recommendation

```text
extra_buffer_lazy correctness: PASS
extra_buffer_lazy accounting: PASS (83 states / 4 slots => effective 20)
100-request churn: PASS
16 -> 20 throughput improvement: NOT OBSERVED for lazy candidate
3-slot worth testing now: NO
```

Keep the existing production baseline until an owner explicitly authorizes a
new experiment. No source changes were made for Phase 2A.
