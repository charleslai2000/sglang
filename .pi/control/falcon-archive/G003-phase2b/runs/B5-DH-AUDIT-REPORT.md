# B5-DH device-hit audit

## Verdict

```text
C — harness revisit-classification defect
```

The Formal B5 aggregate `device_hit=0` cannot be uniquely attributed to all
prefixes being host-only at lookup from the existing artifacts. The artifacts
do, however, prove that the harness labels are not runtime-immediate revisits.
Therefore the formal B5 result remains:

```text
B5 correctness/stability: PASS
B5 host-tier churn: PASS
B5 device-hit observation: UNRESOLVED (not a correctness failure)
B5 overall: HOLD
B6: BLOCKED
```

No runtime, scheduler, radix, Mamba, or production-configuration change was
made. No replay was run.

## 1. Actual revisit semantics

`formal_b5.py` defines five complete waves:

```python
orders = [
  range(200),
  range(200),
  range(40, 200) + range(40),
  reversed(range(200)),
  range(100, 200) + range(100),
]
```

For every wave it constructs all 200 requests, then submits all requests to a
`ThreadPoolExecutor(max_workers=16)`:

```python
with ThreadPoolExecutor(max_workers=CONC) as ex:
    wave = list(ex.map(request, items))
```

Consequently:

- `immediate` was a logical description of wave 1's same-order revisit, not a
  request-level completion-to-submission dependency.
- No request waits for its session's previous request to complete before the
  next request is submitted.
- Other sessions are submitted between any two same-session requests in the
  next wave; the wave itself contains 200 concurrent HTTP requests with only
  16 active workers.
- `ThreadPoolExecutor.map` preserves result-list/input order; it does not
  make the server execute requests in that order. `trace_meta.order` is the
  client submission/input order, not scheduler admission or lookup order.
- `result.json` records per-request elapsed time but no absolute submit time,
  completion time, scheduler admission sequence, lookup sequence, or
  per-request residency snapshot.

Thus the claimed “immediate” category was not a true immediate runtime
revisit. This is Branch C, not Branch A.

## 2. Available sampled evidence

The required 10/10/10 per-category lookup snapshots cannot be reconstructed
from the existing artifacts:

```text
rh_match_prepare records in formal-b5-r3 t38c-probe.log: 0
rh_match_prepare records in stdout/server.log: 0
per-request absolute submit/completion timestamps: absent
per-request cache node/residency snapshots: absent
```

The 217 `load_back` records and backup/eviction records are aggregate/event
telemetry without a request/session identifier that can be joined to the 1000
client records. They prove host-tier movement, but cannot establish whether a
specific labeled revisit was device-resident at lookup.

Therefore it would be incorrect to claim that all sampled immediate, warm, and
dormant requests were host-only before lookup. That stronger Branch-A claim is
not supported by the existing trace.

## 3. Aggregate timing and pressure evidence

Recorded wave wall times were:

```text
wave 0: 109.24 s
wave 1: 111.10 s
wave 2: 112.94 s
wave 3:  93.64 s
wave 4: 115.85 s
```

Each wave submitted 200 requests, not one request followed immediately by its
same-session successor. The run also produced:

```text
host_hit: 88,930
FULL H→D: 55,072
MAMBA H→D: 118
FULL D→H: 1,165,389
MAMBA D→H: 1,504
device evictions: 1,171,474
host-pressure drops: 0
```

These numbers make pressure-driven host churn clear, but event ordering in the
available trace is insufficient to assign every D→H/eviction event to a
particular revisit category.

## 4. Counter semantics

The accounting path is explicit:

```text
PrefillAdder._update_prefill_budget()
  -> split_cached_prefix_by_tier(
       prefix_len,
       host_hit_len,
       storage_hit_len,
     )
  -> log_device_hit_tokens
  -> metrics_reporter.increment_effective_prefill_tokens()
```

For a first-attempt request, `device_hit` is the device portion of the matched
cached prefix after host/storage portions are removed. It is not a generic
“request reused a prefix” counter. Reprocessed/retracted work is excluded from
this first-attempt tier accounting.

In UnifiedTreeCore, HiCache matching separately tracks:

```text
best_match_node              # component-consensus full match
best_match_device_node       # device-valid match
best_match_device_value_len  # device prefix length
```

The returned `device_indices` length is the L1/device prefix. Components then
finalize `host_hit_length`; the scheduler splits the prefix by tier. Therefore
a host-only lookup contributes host_hit, not device_hit. A mixed device+host
match contributes only its device-resident prefix to device_hit. H→D restore is
a transfer operation and does not retroactively turn the original host lookup
into a device_hit event.

This semantics is consistent with R2B's independently observed 1792-token
immediate device hit and with Formal B5's positive host-hit/H→D counters.
No telemetry/accounting anomaly is demonstrated.

## 5. Root cause classification

The unique supported explanation from current artifacts is:

```text
Branch C: Formal B5's immediate/warm/dormant labels describe wave order,
not runtime lookup adjacency. The workload did not guarantee a true immediate
same-session revisit before other requests could execute, evict, or demote the
prefix. The trace also lacks the per-request evidence needed to prove the
alternative Branch A.
```

The original `device_hit > 0` requirement is therefore not a valid acceptance
condition for this high-pressure wave-based churn as implemented. It is
workload-dependent and cannot be used to fail the otherwise successful B5
correctness/host-tier result.

## 6. Supplementary replay

Not run. The root cause—the harness does not implement true immediate runtime
revisit—is already established by source inspection, and the stage instruction
says to stop once the revisit-classification defect is found. A future minimal
supplement, if explicitly authorized, should separately prove true sequential
same-session immediate reuse plus pressure-driven host churn; it must not be
called a rerun of Formal B5.

## 7. Recommended state

```text
B4: PASS
B5 correctness/stability: PASS
B5 host-tier churn: PASS
B5 device-hit observation: UNRESOLVED
B5 overall: HOLD
B6: BLOCKED
```
