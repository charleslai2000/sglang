# EXP-20260908-T38C-PAIRED-TRACE-S25

## Invocation

- Scope: `3090-24g-opt`, RH-off causal probe only; frozen Phase-2 parameters unchanged.
- Remote tag: `s25-t38c-paired-trace-fix1`.
- Evidence: `/root/evidence-gate3-parked/s25-t38c-paired-trace-fix1/`.
- Driver run: `run-20260908-013025`, `25/25` builds, `300s` post-build settle,
  one round, active `8`, build workers `8`.
- Vehicle: `r=0.42`, ratio `1.3`, FP8, Graph8, `file_size=120G`, RH off.

## Observed evidence

- `t38c-probe.log`: 1286 JSON events, 25 `pc_mamba_write` events, all with
  `mamba_transfer_exists=true` and `batch_set_v2=true`.
- All build-side Mamba writes therefore reached `batch_set_v2`; this run does
  not support “async settle” or “write API returned false” as the explanation.
- Warm rows `s00000..s00007` all returned successfully. `s00001` had only an
  84-token suffix and was correctly below the 256-token prefetch threshold, so
  it is not a full restore sample.
- The seven full warm queries produced six KV+Mamba restores and one KV-only
  miss:
  - `s00000`: KV/Mamba `55145/55145`, key `e4799060...`, present.
  - `s00002`: KV/Mamba `55145/0`, key `3bb6ca49...`, absent, `boundary=0`.
  - `s00003`: KV/Mamba `55125/55125`, key `05305610...`, present.
  - `s00004`: KV/Mamba `55102/55102`, key `8b26247e...`, present.
  - `s00005`: KV/Mamba `55124/55124`, key `30f72bac...`, present.
  - `s00006`: KV/Mamba `55103/55103`, key `53454b89...`, present.
  - `s00007`: KV/Mamba `55104/55104`, key `cc7d46c2...`, present.
- Exact key-set comparison: `3bb6ca49...` does not occur in any of the 25
  `pc_mamba_write.mamba_key` values; every other full warm query key does.
- The failed query was not an early-settle artifact: build completion was
  followed by the required 300-second settle, and the failed query happened
  afterward. The failed query's `pc_mamba_query` recorded
  `raw_kv_frontier=55145`, `tested_present=false`, `boundary=0`, and
  `final_pages=0`.
- The short-suffix `s00001` request was logged as `declined_too_short`; it did
  not call the extent query path and is excluded from the 6/7 restore ratio.

## Causal verdict

The frontier fix is effective for the common path: it restored the L3 read and
Mamba all-or-nothing fold for 6/7 full warm samples. The remaining failure is
session-specific. Since the failed warm key is absent from the complete write
key set while all observed write calls reported success, the leading hypothesis
is a build-to-warm key/lifecycle mismatch or omission for `s00002`, not a
generic extent folding defect, insufficient settle, or failed `batch_set_v2`.

This remains a causal probe, not Gate A/B/C evidence. Do not start S=100,
RH-on, or 4-Gate merge until the session-specific mismatch is fixed and an
independent retest reaches stable full-warm coverage.

## Follow-up

1. Inspect the build-side node/key mapping for `s00002` and compare it with
   the warm `3bb6ca49...` key; add session/node correlation only if needed.
2. Trace the lifecycle/removal path for the missing key without weakening the
   all-or-nothing Mamba/KV fold.
3. Re-run the same S=25 vehicle after the minimal fix; require all full warm
   samples to have exact write-key/query-key correspondence before scaling.

