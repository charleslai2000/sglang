# Comprehensive Layered Performance Baseline Specification v2

**Status:** normative specification only; no workload, GPU, or server was run.
**Task:** `LOCAL-PERF-BASELINE-SPEC-V2-20260914`
**Scope:** documentation and machine-readable contract under
`/mnt/data/cache/performance-baseline-v1/`. This task does not modify source,
model, runtime, or raw runs. Existing v1 artifacts and accepted runs remain
preserved.

## 1. Rules and evidence boundary

Each run is immutable and comparable only when its identity, effective argv,
corpus, workload cell, profile, and measurement rules match. A missing
authoritative counter is recorded as `UNAVAILABLE` with source and reason. It is
never inferred from occupancy, latency, or total-token throughput. Derived
summaries link to raw evidence and hashes; failed or incomplete attempts remain
visible. Synthetic or bounded semantic evidence is not production performance
evidence.

The hierarchy is:

```text
manifest/  compute/  prefill/  cache-l1/  cache-l2/  cache-l3/
agent/  stability/  telemetry/
```

These are evidence namespaces, not permission to execute anything. A workload
may use streaming for UX and agent cells; non-streaming is permitted for
throughput-only measurements.

## 2. Frozen run identity and controls

Every run manifest MUST freeze and record, without secrets:

- source commit, dirty-tree hash, and hashes of relevant production files;
- model SHA/revision and loader/shim identity;
- launcher and the exact effective argv (after defaults/config expansion);
- Python, Torch, CUDA, Triton, SGLang, and kernel versions/identities;
- GPU UUID, GPU model, driver, host/time basis, and storage namespace;
- corpus/seed identity, profile, sampling/tool policy, timeouts, and warmup
  versus measured boundaries;
- concurrency, request count, prompt/output budgets, and percentile method.

For RTX 3090 work, the exclusive `/mnt/data/gpu/3090.lock` must be acquired
before startup and referenced by the run manifest. Identity changes create a new
run; they do not amend an existing result.

## 3. Frozen metric contract

UX latency is reported as **TTFT, E2E, TPOT, and ITL**, each at p50/p95/p99
when the sample is sufficient. TTFT starts at dispatch and ends at the first
valid output event; E2E ends at completion. TPOT and ITL use valid generated
token events and state their denominator and zero-token behavior. A percentile
with insufficient samples is `UNAVAILABLE`, not extrapolated.

Throughput metrics are:

- `req/s = completed_requests / wall_time`;
- `aggregate_output_tps = output_tokens / wall_time`;
- `effective_compute_tps = (actual_prefill_tokens + output_tokens) / wall_time`;
- `served_context_tps = (prompt_tokens + output_tokens) / wall_time`.

Also record prefill tok/s, decode tok/s, batch-size histogram, queue wait,
admission latency, active requests, and queued requests. Wall time and token
boundaries are explicit; warmup is not silently included.

### Cache and state accounting

For every measured request, exact prompt accounting is:

`prompt_tokens = L1_tokens + L2_tokens + L3_tokens + newly_prefilled_tokens + avoidable_recompute_tokens`.

The components must be authoritative and mutually auditable; otherwise the
affected field is `UNAVAILABLE`. Record hit tokens and hit requests, full,
partial, and miss classifications, restore tokens, and stage latency. Record
Mamba slots, restores, rebuilds, and evictions. Record RH lead, slack,
ready-before-admission, avoidable recompute, and cache-idle metrics when the
runtime exposes authoritative counters. Never derive these from occupancy or
aggregate token rates.

### Telemetry

When available, record timestamped GPU utilization, VRAM, memory bandwidth,
power, and clocks; CPU utilization, RAM, PCIe H2D/D2H; and NVMe read/write
GB/s, IOPS, latency, and bytes staged. Each value names its source, unit,
sampling interval, reset semantics, and coverage. Unsupported telemetry is
`UNAVAILABLE`.

## 4. Workload hierarchy and cells

All cells use fixed seed/corpus, at least three measured repeats, and
`num_prompts >= 5 * concurrency`. Report median across repeats and p99 only
when the sample is sufficient. Separate cold flush from warm no-flush behavior.

| Namespace | Required cells |
|---|---|
| `compute/` | ceiling cells with short prompt/long output at C1, C4, C8, C16 |
| `prefill/` | 2K, 8K, 32K, 64K input plus 32 output at C1 and C4 |
| `cache-l1/` | L1-hot and exact accounting |
| `cache-l2/` | L2-hot and restore/stage accounting |
| `cache-l3/` | L3-hot and NVMe/staging accounting |
| `agent/` | fixed multi-round/tool corpus with growing context |
| `stability/` | separate soak and restart/recovery evidence, never a performance score |
| `telemetry/` | synchronized resource samples for measured cells |

Cache reuse additionally requires `partial` and `miss` cells. A hit must be
shown by an authoritative counter or event, not by naming the arm or observing
similar latency. Agent and UX cells are streaming; throughput cells may be
non-streaming, with mode recorded.

## 5. Semantic, lifecycle, and acceptance rules

The local versioned oracle checks transport, schema, own marker, absence of
cross-request markers, nonempty output, and unambiguous completion. Counts for
success, error, timeout, cancellation, and unclassifiable responses are
separate. A semantic failure invalidates the affected cell; it is not dropped.

Stability is independent: a soak must meet its declared duration/rounds,
maintain health and drain state, and retain shutdown/cleanup evidence. Restart
requires verified post-restart health and semantic checks. Soak/restart is
`INCOMPLETE` if duration, semantic integrity, or restart evidence is missing;
it cannot be converted into a performance score.

An accepted v2 performance record requires identity, corpus, semantic, requested
cell, metric, artifact-hash, and applicable authoritative-counter gates. A
bounded archive can be accepted only for the fields it actually proves. This
specification makes no performance-completion claim.

## 6. Artifact contract and current status

Use immutable run IDs and retain raw artifacts under the appropriate hierarchy;
the manifest records relative paths and SHA-256 hashes. The v2 specification
artifacts are this file, its JSON companion, and its SHA-256 file. Validation
commands and exit codes are recorded by the documentation task; they do not
constitute workload evidence.

Current known status is explicitly limited: the accepted bounded non-streaming
semantic aggregate lacks TTFT and authoritative cache counters. The soak/restart
archive is incomplete at **35/36 semantic**, with restart **unverified**. The
comprehensive v2 corpus is **pending**. No performance completion, cache
completion, TTFT completion, soak completion, or restart completion is claimed.
See the [v1 README](../README.md), [v1 specification](../manifests/PERFORMANCE-BASELINE-SPEC-v1.md),
and [soak summary](../summaries/B3-soak-restart-shim-20260914T061229Z.md).

## 7. Validation boundary

Validation is limited to Markdown presence/link targets, JSON syntax/schema
shape, and SHA-256 consistency for these specification artifacts. It does not
start a GPU/server, modify source/model/runtime, or inspect raw runs as a new
performance experiment.
