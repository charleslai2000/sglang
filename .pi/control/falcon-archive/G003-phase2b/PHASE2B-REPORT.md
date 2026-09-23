# Phase 2B — HiCache correctness and host-tier reuse

## Final closure — owner adjudication

```text
B4 hybrid HiCache lifecycle: PASS
B5 production correctness/stability: PASS
B6 correctness: PASS
B6 performance: VALID RESULT, NO MEASURABLE BENEFIT UNDER THIS WORKLOAD
Phase 2B: DONE
```

The B6 workload was dominated by device radix reuse rather than host-tier reuse:

```text
OFF device_hit mean: 1,955,948 tokens/rep
ON device_hit mean: 1,962,306 tokens/rep
ON host_hit mean: 2,316 tokens/rep
```

The approximately 847:1 device-hit/host-hit scale explains the near-identical
OFF/ON performance:

```text
wall time: -0.02% ON
mean TTFT: +0.20% ON
mean E2E latency: -0.02% ON
aggregate throughput: +0.02% ON
```

This does not establish that HiCache has no value. It establishes only that this
200-session/5-turn workload generated too little host-tier reuse to measure a
performance benefit. HiCache functionality and correctness remain proven,
including FULL/KV and MAMBA GPU→CPU→GPU lifecycle, host-only radix lookup, and
1000-turn churn correctness. OFF and ON each completed three measured reps with
1000/1000 correctness. The two 600-second executor timeouts were external
background-lifecycle terminations, not runtime failures.

B6 instrumentation was incomplete for some distributional/system fields. Per
owner decision, no rerun is warranted: repeating this workload would not solve
the underlying low-host-reuse limitation.

Future work, if needed:

```text
Design a separate high-session-pressure / long-dormancy benchmark where
host_hit is a significant fraction of the reusable prefix, then independently
measure HiCache performance value.
```

Production recommendation:

```text
HiCache is functionally available and correctness-proven.
Do not enable it by default for an expected throughput gain based on this B6.
Its performance value under higher session pressure remains unresolved.
```

## Historical execution record

The original pre-adjudication report follows below and is retained as execution
history. Its initial BLOCKED wording is superseded by the final closure above.

## Verdict

```text
VERDICT: BLOCKED at B4
```

B2 and B3 passed. B4 did not pass because the forced pressure workload filled
the host KV pool after successful D→H backup, so the target prefix was no
longer host-resident when requested again. No source patch was made. B5/B6
were not run.

## Lineage

```text
target source commit: b0bd1d96fc
reference lineage: sglang-3090-24g-opt / 3090-24g-hicache
reference HEAD: c72002ba14
```

The target retains the reference HiCache implementation. Central runtime source
hashes match the reference checkout for UnifiedRadixCache, UnifiedTreeCore,
HybridCacheController, and scheduler. No upstream replacement or reimplementation
was performed.

## B2 — Minimal L2 bring-up

Configuration:

```text
model: Falcon-H1 GPTQ-Int4
Mamba SSM: BF16
mamba strategy: extra_buffer
context: 8192
prefill graph: disabled
decode graph: full
HiCache: enabled
hicache ratio: 1
write policy: write_through
host memory mode: cache
I/O backend: kernel
memory layout: page_first
storage backend: none
```

Runtime resolved `server_args` explicitly show the requested configuration.
Startup logs show:

```text
Init Unified Radix Cache
Components: FULL, MAMBA
Tree Core: UnifiedTreeCore
Allocating kv hierarchical KV host pool: 145387 tokens, 6.55 GB
Allocating 5.89 GB host memory for hierarchical Mamba cache
Attached hybrid pool stack to UnifiedRadixCache: pools=KV + MAMBA
Tree cache initialized: impl=UnifiedRadixCache, hybrid_ssm=True,
hicache_attached=True
```

Recorded pools:

```text
FULL/KV device: 145386 KV tokens; BF16 K/V each 3.05 GB
FULL/KV host: 145387 tokens; approximately 6.55 GB
MAMBA device: max_mamba_cache_size=83 states; SSM 5.41 GB + conv 0.07 GB
MAMBA host: 84 logical state slots; approximately 5.89 GB
host DRAM allocated: approximately 12.44 GB for KV + MAMBA pools
```

No storage backend, L3 backend, swap, Mooncake, or file cache was configured.
Decode graph capture completed successfully with `cuda graph: True` in request
logs.

## B3 — HiCache correctness

Passed:

```text
France: PASS
2+3: PASS
sentinel: PASS
10 deterministic prompts: PASS
20 sequential requests: PASS
c=1/4/8/16/20/24 request probes: HTTP-success gate PASS
```

Canonical outputs remained correct:

```text
The capital of France is Paris...
5<|im_end|>\n
FALCON_SENTINEL_7B<|im_end|>\n
```

No CUDA error, scheduler exception, decode graph regression, or cross-request
contamination was observed during B3.

## B4 — Forced eviction / restore

### What was proven

The forced probe constructed a 2048-token prefix and injected 80 distinct
approximately 2K-token prefixes. Runtime telemetry proves:

```text
UnifiedRadixCache device evictions: 93
D→H backup operations: 80
FULL/KV D→H backup tokens: 163296
MAMBA D→H backup tokens: 80
backup bytes: approximately 12.97 GB
host pool used after pressure: 144924 / 145387 tokens
```

Thus categories A and B are excluded:

```text
A host backup did not happen: NO, backup happened
B device eviction did not happen: NO, eviction happened
```

The lineage also emitted no dropped-token host-pressure counter:

```text
hicache_dropped_tokens_total{pool="kv"}: 0
hicache_dropped_tokens_total{pool="mamba"}: 0
```

### What failed

The target prefix was requested after pressure, but the authoritative metrics
showed:

```text
prefill_effective_tokens_total{mode="host_hit"}: 0
load_back_tokens_total: no positive L2 load-back evidence
storage_hit: 0
```

The pressure sequence filled the host pool sufficiently that host residency of
the target prefix was not preserved. The final host usage was near capacity.
Therefore the required B4 state transition was not established:

```text
device-resident → host-resident only → host match → H→D restore
```

The probe's suffix-B request completed HTTP successfully, but its output was not
treated as evidence of host restore. The first attempt also included only one
request for the prefix before pressure; its `device_hit` counter later reached
2048, demonstrating device reuse on a subsequent attempt, not host reuse.

### Classification

Current classification:

```text
A: excluded — host backup succeeded
B: excluded — device eviction succeeded
C: not established — host-only node traversal was not proven because host
   residency was exhausted before the target lookup
D: not reached
E: not reached
F: not accepted; no semantic result was attributed to restore
G: no deadlock/retry failure observed
```

This is a **test/workload capacity failure**, not evidence of the old #33713
node-prune bug. The host pool ratio of 1 gives only approximately 145K KV
host tokens, while the forced campaign backed up approximately 163K KV tokens.
The target could have been host-evicted by legitimate host-tier pressure.
No patch is authorized from this result.

### FULL/MAMBA evidence boundary

The D→H side is separately evidenced:

```text
PoolName.FULL/KV: 163296 backup tokens
PoolName.MAMBA: 80 backup tokens
```

The H→D side is not evidenced:

```text
FULL host hit: 0
MAMBA host hit: 0
FULL H→D: not observed
MAMBA H→D: not observed
```

Node-level `value/host_value/mamba_value/mamba_host_value` snapshots were not
exported by the current public runtime telemetry for the target request. The
absence of host-hit telemetry after host-pool saturation is insufficient to
claim node pruning.

## B4-R2 — ratio 2 rerun

The owner-authorized rerun changed only `--hicache-ratio 1` to `--hicache-ratio 2`.
Before startup:

```text
MemAvailable: approximately 118 GiB
swap: 0 B
```

Runtime allocation succeeded without swap:

```text
FULL/KV host: 290773 tokens, approximately 13.10 GB
MAMBA host: approximately 11.72 GB
MAMBA device: 83 states
```

However, the adaptive pressure run did not establish the required transition.
It submitted ten batches of eight distinct prefixes, but the authoritative
metrics showed:

```text
host_used_tokens: 0
hicache_backup_tokens_total: no positive observed value
host_hit: 0
load_back_tokens_total: no positive observed value
evicted_tokens_total: 22458
```

The target's first repeat request was still explicitly reported as:

```text
cached_tokens_details: {device: 2048, host: 0}
```

The pressure therefore caused some device evictions but did not create a
verified host-retained target window. The target B request had no host-hit or
load-back evidence and was not accepted as a restore result. This is now
classified as:

```text
B4-R2: BLOCKED — device pressure occurred, but D→H host backup/host retention
       was not established by telemetry before the target lookup
```

No node-level diagnostic instrumentation was added, and no source patch was
made. B5/B6 remain stopped.

## B4-R3 — R3A single-request backup isolation

R3A was run on clean services with the requested `write_through`, FULL +
MAMBA topology and ratio=2. One approximately 2K-token target (`P + suffix A`)
was issued, followed by eight two-second idle drain observations. Runtime
FULL host usage remained zero; no positive FULL/MAMBA backup, enqueue/issued/
ack, pending-queue, retry-queue, or host-residency evidence was observed. The
request's HTTP success was not treated as backup evidence.

Per Gate A, R3B was not run. The identical target and wait procedure was then
run as a minimal ratio=1 A/B. It also showed host usage zero and no positive
single-request backup evidence. Therefore R3A does not isolate a ratio-dependent
bug:

```text
ratio=1 single target: no backup observed
ratio=2 single target: no backup observed
```

This result is consistent with backup being triggered at the pressure/eviction
boundary rather than by ordinary insertion alone. The earlier ratio=1 pressure
backup remains a separate observation and was not reproduced by this minimal
A/B. No source patch or diagnostic instrumentation was added. R3B, B5, and B6
remain stopped.

## B4-R4 — deterministic target eviction

R4 first performed the narrow call-chain audit. The actual write-through insert
path is `UnifiedTreeCore._insert_tail_step → _should_backup_after_insert →
_inc_hit_count_and_check → BackupKV → UnifiedRadixCache._execute_and_commit_kv_backup
→ build_backup_spec → cache_controller.write → commit_backup`. A new leaf only
backs up after the hit-count condition; `chunked=True` skips that condition.
The device-eviction path for write-through does not perform a deferred D→H for
an unbacked victim: `UnifiedTreeCore.evict_device_leaf()` deletes such a leaf.
A backed-up leaf is later demoted by `_demote()`, which cascades Full-triggered
release to MAMBA. The deferred D→H-before-demote branch in
`UnifiedRadixCache` is the write-back path.

R4 therefore used an unchunked 1900-token target. The target was backed up:

```text
FULL backup: +1792 tokens
MAMBA backup: +1 token
host_used after A: 1792
```

The marker-gated durable trace recorded `backup_host_commit` for target node
18 with `kv_transfer=true` and `mamba_transfer=true` before later device
detach events. Pressure used 14 batches × 8 distinct approximately 1900-token
prefixes, without requesting the target again. Runtime pressure reached
201423/281377 FULL host tokens and produced 67735 device evictions, with zero
KV/MAMBA dropped tokens.

For target node 18, the trace then recorded MAMBA device detach followed by
FULL/KV and MAMBA `device_leaf` detach. The target remained in the tree as a
host-backed entry: suffix B reported `cached_tokens=1792` and
`cached_tokens_details={device: 0, host: 1792}`. Public telemetry recorded
`host_hit +1792`; the request completed normally.

R4 is nevertheless **BLOCKED**, not B4 PASS: the existing public metrics and
trace do not independently expose completed FULL and MAMBA H→D transfer IDs,
nor a complete post-restore node snapshot proving both device values were
restored. The host-only match and backup/demotion lifecycle are proven, but the
requested component-specific restore seam is not. B5/B6 remain stopped.

Detailed report: `control/G003-phase2b-hicache/runs/R4-REPORT.md`.

## B4-R5 — authoritative H→D restore telemetry

R5 added only marker-gated diagnostics. No cache behavior, admission,
eviction, load-back scheduling, LRU, or policy logic was changed. The patch
adds target-correlated `load_back_issued` and `load_back_completed` records,
propagates the existing `CacheOperation.id` into `HiCacheAck`, and records
read-only target node snapshots immediately before load-back and after the
synchronized ACK/finalization.

The R4 trace was repeated unchanged with ratio=2, 1900-token target,
write-through, extra_buffer, prefill graph disabled, and decode graph full.

Before suffix B, target node 18 was:

```text
FULL:  device absent / host present, 1789 host slots
MAMBA: device absent / host present, 1 host slot
node: retained
```

Target-correlated restore operation:

```text
transfer_id: 113
node_ids: [18]

FULL/KV issued:     1789 tokens
FULL/KV completed:  1789 tokens
MAMBA issued:       1 node state + 1 request CoW state
MAMBA completed:    2 state slots
```

The completion records are emitted after `ack.finish_event.synchronize()`.
The MAMBA count of two is expected because the merged operation contains the
node restore transfer and the request/device-slot CoW transfer.

After completion and node finalization:

```text
node: retained
FULL:  device present (1789) / host present (1789)
MAMBA: device present (1) / host present (1)
```

This is the legal residency result: promotion materializes device values and
retains host copies as duplicates. Suffix B passed HTTP/semantic/sentinel
checks and reported:

```text
cached_tokens: 1792
cached_tokens_details: {device: 0, host: 1792}
host_hit delta: +1792
```

The cached prefix was not recomputed. All B4 seams therefore pass.

```text
B4-R5: PASS
```

Detailed report: `control/G003-phase2b-hicache/runs/R5-REPORT.md`.
No source patch was made. Do not enter 32K, extra_buffer_lazy/3-slot, FP8 KV,
L3/storage, or speculative decoding.

## B5/B6 exploratory transition result

B5/B6 were attempted after B4-R5, but the correctness gate failed and no B6
conclusion is accepted. The first harness used `MAX_NEW=8`, truncating identity
sentinels. The corrected replay used `MAX_NEW=32` and five deterministic revisit
waves (200 sessions × 5 turns = 1000 turns), but wrong-sentinel counts remained:

```text
OFF: 24 / 24 / 25
ON:  23 / 26 / 23
```

All requests completed without HTTP, CUDA, or scheduler errors, but B5 is not
PASS because deterministic session correctness was not established. The
corrected ON runs also produced zero host-hit and device-hit counters, so no
valid HiCache performance comparison exists. B6 is BLOCKED and no OFF-vs-ON
performance claim is made.

Detailed report:
`control/G003-phase2b-hicache/runs/B5-B6-REPORT.md`

## B5/B6-R2 micro-gate result

R2A confirmed the old harness omitted assistant responses and did not use chat-template conversation serialization. Same-session LCP was nevertheless substantial (0.787, 0.828, 0.856, 0.876 across the four transitions), so the old zero-hit result required micro-gate validation rather than an immediate cache conclusion.

R2B device micro gate passed on the new append-only serialization:

```text
turn2 device_hit: 1792 tokens
```

The initial free-form four-digit oracle did not parse a code from turn2, so oracle qualification failed. The host micro gate also failed because the attempted 160 distinct prompts were approximately 2020 tokens each, about 323K pressure tokens, exceeding the ratio-2 runtime FULL host capacity of 290773 tokens. Runtime evidence showed 185142 device evictions but host_hit remained zero.

Per STOP rules, formal B5/B6 were not run. No source behavior patch was made.

Detailed report:
`control/G003-phase2b-hicache/runs/R2-REPORT.md`

## R2C micro-gate result

R2C completed the two required gates without entering formal B5/B6. The adaptive host pressure stopped at the first target transition to device-absent/host-present, at only 123196 host tokens against the 290773-token runtime FULL host capacity. Target revisit produced:

```text
host_hit: +1024
FULL H→D: +1020 tokens
MAMBA H→D: +2 state slots
post-restore FULL: device+host present
post-restore MAMBA: device+host present
```

The two MAMBA slots are the established node-restore plus request CoW accounting. No runtime error occurred.

Oracle qualification used the exact parser `CODE\\s*=\\s*(\\d{4})` and HiCache-OFF cold/eager execution:

```text
200/200 correct
wrong code: 0
missing code: 0
```

Therefore:

```text
R2 host gate: PASS
oracle gate: PASS
formal B5/B6: authorized for a later explicit transition, not run in R2C
```

Detailed report:
`control/G003-phase2b-hicache/runs/R2C-REPORT.md`

## STOP decision

R2C ended after both micro gates passed. Formal B5 was subsequently authorized and executed. The real chat-template append-only workload completed 1000/1000 with 1000/1000 CODE oracle correctness and no runtime/scheduler/OOM errors. It produced host_hit=88930, FULL H→D=55072, MAMBA H→D=118, D→H FULL=1165389, D→H MAMBA=1504, device evictions=1171474, zero dropped KV/MAMBA tokens, and final host occupancy 233749/290773. However, runtime `device_hit` remained 0 in the formal churn. The subsequent B5-DH audit classified this as Branch C: the harness labels immediate/warm/dormant describe wave submission order, not true completion-to-submission runtime adjacency; the existing artifacts lack per-request lookup/residency timestamps and cannot prove a device-resident lookup. Therefore the prior device-hit gate is unresolved/workload-dependent rather than a correctness failure. Current adjudication after B5-INT closure: B5 correctness/stability PASS, host-tier churn PASS, prior wave-workload device-hit acceptance INVALIDATED, B5-INT PASS, B5 overall PASS. The narrow integration diagnostic demonstrated true sequential device_hit +2304, dormant host_hit +2304, FULL H→D +256, and MAMBA H→D +2 with correct A/B oracles and no runtime failures. B6 was then executed using the exact materialized B5 trace: one warmup and three measured repetitions for HiCache OFF and ON. All six measured repetitions completed 1000/1000 correctly. Aggregate measured means were OFF 11365.60 tok/s vs ON 11368.03 tok/s (+0.02%), TTFT 2.2773s vs 2.2819s (+0.20%), and E2E 3.6370s vs 3.6364s (-0.02%). ON recorded host_hit mean 2316 tokens/rep, FULL H→D mean 1315 tokens/rep, and MAMBA H→D mean 2 states/rep; OFF had no host tier. No CUDA/OOM/deadlock evidence. GPU utilization/power/VRAM/DRAM traffic were not captured. Final report: `control/G003-phase2b-hicache/runs/B5-B6-FINAL-REPORT.md`.

## Artifacts

```text
runs/hicache-on/server.log
runs/hicache-on/correctness.json
runs/hicache-on/forced-probe.json
runs/hicache-on/forced-probe.stdout
runs/hicache-on/metrics-before.txt
runs/hicache-on/metrics-A.txt
runs/hicache-on/metrics-pressure.txt
runs/hicache-on/metrics-B.txt
runs/hicache-on/metrics-final.txt
runs/hicache-on/forced-probe-retry.json
runs/hicache-on-retry/server.log
runs/hicache-on-retry/metrics-final.txt
runs/hicache-on-retry/metrics-final2.txt
forced_probe.py
forced_probe_retry.py
B1-AUDIT.md
```
