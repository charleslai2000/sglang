# B5/B6-R2 report

## Verdict

```text
BLOCKED — micro gates did not both pass; formal B5/B6 not run
```

B4 remains PASS. No HiCache mechanism was revalidated or modified.

## R2A old-harness audit

The old harness constructed each request as independent plain text. It did not
include the previous assistant response, did not use a chat template, and did
not reconstruct a role-based conversation. Same-session token LCP was not the
main cause of zero hits, however:

```text
10 sessions, all four turn transitions:
turn 0→1: previous 75 tokens, LCP 59, ratio 0.787
turn 1→2: previous 93 tokens, LCP 77, ratio 0.828
turn 2→3: previous 111 tokens, LCP 95, ratio 0.856
turn 3→4: previous 129 tokens, LCP 113, ratio 0.876
```

Different-session LCP was 8 tokens. The audit confirms the old serialization was
not a faithful assistant-inclusive conversation replay, and no micro cache gate
had been established before the previous benchmark.

Artifact:

```text
control/G003-phase2b-hicache/R2A-AUDIT.md
```

## R2B micro gates

The new micro harness used append-only stable context and short per-session
codes. It first ran on a clean HiCache-OFF service for the device/serialization
gate.

### Device-hit gate

```text
turn1 → immediate turn2
```

Runtime result:

```text
turn2 cached_tokens: 1792
device_hit: +1792
host_hit: 0
```

The aligned runtime hit agrees with the offline LCP-derived cached span. The
cache device-hit mechanism is therefore demonstrated for this serialization.

The response oracle itself did not pass: turn2 did not contain a parseable
four-digit code under the initial free-form generation setup. This is an oracle
qualification failure, not evidence of cache contamination.

### Host-hit gate

The attempted pressure used 160 distinct sessions. Their actual prompt size
was approximately 2020 tokens each, so the pressure workload was approximately
323K tokens, exceeding the ratio-2 runtime FULL host capacity:

```text
runtime FULL host capacity: 290773 tokens
```

Observed:

```text
evicted_tokens_total: 185142
host_hit: 0
```

The design therefore exhausted/overran the intended host-余量 condition and
failed to preserve the target host copy. This host gate is invalid and is not
classified as a restore bug.

## Stop decision

Per the requested STOP rules:

```text
micro device hit: PASS
micro host hit: FAIL
oracle qualification: FAIL
formal B5: NOT RUN
formal B6: NOT RUN
```

No 200-session churn or OFF/ON performance benchmark was started. No source
behavior patch was made. The R5 marker-gated telemetry remains available.

## Required correction before another run

1. Use a deterministic oracle that reliably returns a short code, preferably a
   constrained/minimal response; do not interpret free-form omission as cache
   contamination.
2. Recompute actual token lengths before pressure.
3. For ratio=2 FULL host capacity 290773, keep pressure clearly below host
   capacity while above device capacity. The attempted 160×~2020 trace was too
   large; use a bounded pressure set or shorter stable contexts and verify
   runtime host occupancy after each batch.
4. Require target host-only snapshot plus FULL/MAMBA host-hit and R5 transfer
   evidence before formal B5/B6.

## Artifacts

```text
control/G003-phase2b-hicache/r2_micro.py
control/G003-phase2b-hicache/runs/r2-micro-off/
control/G003-phase2b-hicache/runs/R2-REPORT.md
```
