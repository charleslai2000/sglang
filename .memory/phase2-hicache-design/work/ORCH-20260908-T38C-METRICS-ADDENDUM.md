# ORCH-20260908-T38C-METRICS-ADDENDUM

## Metrics correction

The paired trace run completed 25/25 builds, one 300-second post-build settle,
and 8/8 warm requests. All 8 returned HTTP 200 / `rc=0`; total elapsed time
was 954.9 seconds.

Warm request metrics from `runs.csv`:

| session | TTFT (s) | prefill input | device hit | host hit | storage hit | restore result |
|---:|---:|---:|---:|---:|---:|---|
| s00000 | 2.361 | 37 | 6 | 0 | 55139 | KV+Mamba |
| s00001 | 0.638 | 78 | 7 | 55097 | 0 | short suffix; below 256 threshold |
| s00002 | 17.308 | 55182 | 0 | 0 | 0 | full miss; Mamba boundary 0 |
| s00003 | 2.613 | 57 | 6 | 0 | 55119 | KV+Mamba |
| s00004 | 2.952 | 80 | 6 | 0 | 55096 | KV+Mamba |
| s00005 | 2.620 | 58 | 6 | 0 | 55118 | KV+Mamba |
| s00006 | 3.001 | 79 | 6 | 0 | 55097 | KV+Mamba |
| s00007 | 2.667 | 78 | 6 | 0 | 55098 | KV+Mamba |

For all 8 requests, TTFT is min/p50/p95/max `0.638/2.644/12.301/17.308s`.
For the 7 full-suffix requests, storage-hit total is `330667` tokens and the
full restore ratio is `6/7`; the successful full restores have TTFT
min/p50/max `2.361/2.641/3.001s` (the p50 is over the six successful restores).

Final metric snapshot: `prefill_storagehit=330667`, `prefill_hosthit=55097`,
`prefill_devicehit=43`, `load_back(kv/mamba)=385764/14`,
`backup(kv/mamba)=2178758/25`, `evicted_tokens=1318633`, host cache
`651960/652407` used/total, and `max_total_num_tokens=501851`.
No host-pressure drops were recorded. The observed extent footprint was
`22959378432` bytes (~21.4 GiB).

## Caveat

The 25 successful Mamba writes are not all pre-warm: 23 occurred before the
first warm query and two occurred during the warm window. Therefore the
300-second settle reduces but does not fully close the late asynchronous-write
alternative. The `s00002` missing-key conclusion remains valid as a key-set
observation, but omission-vs-late-write timing still needs correlated tracing.

