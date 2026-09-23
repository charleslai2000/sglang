# B5/B6 report

## Verdict

```text
BLOCKED — B5 correctness gate failed; B6 OFF/ON performance results are not admissible.
```

Both experimental harness versions are retained. The first version used `MAX_NEW=8`,
which truncated the deterministic identity sentinel. It was discarded. The corrected
version used `MAX_NEW=32` and five deterministic revisit waves (200 sessions × 5 turns
= 1000 turns), but the model still did not reliably emit the requested identity in all
responses; OFF wrong-sentinel counts were 24/24/25 and ON counts were 23/26/23.
Therefore B5 is not PASS.

## Corrected replay result

```text
OFF:
  rep1: 1000 completed, 0 errors, 24 wrong sentinels
  rep2: 1000 completed, 0 errors, 24 wrong sentinels
  rep3: 1000 completed, 0 errors, 25 wrong sentinels

ON ratio=2:
  rep1: 1000 completed, 0 errors, 23 wrong sentinels
  rep2: 1000 completed, 0 errors, 26 wrong sentinels
  rep3: 1000 completed, 0 errors, 23 wrong sentinels
```

No scheduler crash, CUDA error, or HTTP failure occurred. The wrong outputs are a
semantic correctness failure for the requested gate, not evidence of cross-session
cache contamination. One example was a valid explanatory answer that omitted the
requested identity, so the harness cannot classify it as a correct sentinel response.

## Observed metrics

The corrected ON runs showed no host-hit tokens in the sampled end metrics:

```text
prefill_effective_tokens_total{mode="host_hit"}: 0
prefill_effective_tokens_total{mode="device_hit"}: 0
hicache_dropped_tokens_total{pool="kv"}: 0
hicache_dropped_tokens_total{pool="mamba"}: 0
```

This means the trace did not produce an admissible L2 reuse signal for performance
comparison. It is not a basis for claiming HiCache has no benefit; B5 correctness and
trace reuse validity must be fixed first.

The initial invalid run and corrected run are both retained; neither is used for B6
claims.

## B6

B6 OFF and ON measured repetitions were executed as exploratory data only, but are
not accepted because B5 failed and ON produced no host-hit evidence. No OFF-vs-ON
performance conclusion is reported.

Exploratory corrected-run wall times:

```text
OFF: 85.557 s, 86.213 s, 87.581 s
ON:  87.129 s, 86.743 s, 87.179 s
```

These are not an accepted B6 result.

GPU sampler artifacts were collected. The corrected-run samples showed approximately
76–78% mean GPU utilization, up to 100%, and approximately 22.3 GiB peak VRAM; DRAM
utilization and power samples are retained per repetition. Scheduler batch-distribution
telemetry was not sufficient for an accepted report.

## Root cause / remaining

The corrected harness made all prompts deterministic and replayable, but requiring the
model to reproduce a long opaque identity in free-form generation is not a reliable
correctness oracle at `temperature=0`. The next authorized B5 run needs a robust exact
sentinel protocol (for example, a short constrained response or a deterministic
machine-checkable suffix) while preserving distinct session prefixes. It must also
prove actual reuse with per-request cache telemetry before B6 is accepted.

No cache behavior patch was made. The R5 marker-gated diagnostics remain available.

## Artifacts

```text
runs/b6-off/
runs/b6-on/
runs/b6-off-r2/
runs/b6-on-r2/
control/G003-phase2b-hicache/b5_b6_replay.py
```
