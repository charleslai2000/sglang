# T004 Direct-I/O and cache-condition arms

Date: 2026-10-18. All arms use isolated per-run Extent directories, Falcon revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`, source HEAD `592a9ef996d8efc4a06cf64ce9079e34b1003637`, executable SHA256 `e50d468e8b0adfb05733f5b87b3cff34829c4a8c1aea50c865aa8bdfe4bb150f`, and run-scoped probe/server/request paths. GPU services were run under `/tmp/f1-r16b-gpu-exclusive.lock` and stopped after each arm.

## O_DIRECT implementation and checks

`SGLANG_HICACHE_L3_DIRECT_IO_MEASURE=1` enables a separate read-only `O_RDONLY|O_DIRECT` descriptor for Extent data reads. It uses aligned bounce buffers and outward alignment of read ranges. Buffered write/data, WAL, and ACK/durability semantics are unchanged. Strict measurement mode fails on direct open/read errors and has no buffered fallback. The new environment switch defaults off.

`test_extent_file_backend_unit.py`: **119 passed** (15 upstream pytest/PyTorch warnings). Python compile, launcher `bash -n`, and scoped `git diff --check` also passed. A startup O_DIRECT probe on `/dev/sda1` succeeded. `/dev/sda1` is a virtual block device; its sector counters confirm block-layer traffic only, not physical media or cache bypass.

## Paired low-concurrency ON/OFF, Direct enabled

Same bounded workload: 2 configured slots, 8,192 token budget, queue cap 8, Ready Horizon enabled, one A Decode occupant (1,024 outputs) and one queued B target (2,112 prompt tokens, one output). Each B used the same-run FULL+MAMBA L3 fixture, cached 2,048 tokens (Storage 2,042, Host 6, Device 0).

| Queue Prefetch | Run / manifest | B RID | Queue s | E2E s | Direct B reads | sda/sda1 run-window sectors |
|---|---|---|---:|---:|---|---:|
| ON | `falcon-t004-direct-low-on-20261018T060719Z` / `ab-falcon-t004-direct-low-on-20261018T060719Z.json` | `0195bdb58e7f4c2f93ac76dfa3232206` | 18.006 | 18.254 | 2 × 46,137,344 B; 0.02195 + 0.01488 s; 4 + 1 syscalls; 1,024 successful pages each | +452,416 |
| OFF | `falcon-t004-direct-low-off-20261018T061056Z` / `ab-falcon-t004-direct-low-off-20261018T061056Z.json` | `4978279b92544387a2129d8008e87a45` | 18.041 | 18.341 | 2 × 46,137,344 B; 0.02111 + 0.01483 s; 4 + 1 syscalls; 1,024 successful pages each | +452,408 |

Block-device counters cover all per-run fixture setup, occupant and request work, not B exclusively. One pair is descriptive, not evidence of a performance effect.

## Paired high-pressure ON/OFF, Direct enabled

Same bounded workload: 8 configured slots, 32,768 token budget, queue cap 8, A 1,024-output Decode occupant, B/C/D 2,112-token L3-backed prompts and 128 outputs. Each target had 2,048 cached tokens and two direct KV batches of 46,137,344 B (4 + 1 syscalls, each 1,024 pages). Both manifests set `direct_io_backend_confirmed=true` and the same source/executable identities.

| Mode | Run / manifest | B/C/D queue s | B/C/D E2E s | Mean E2E s | sda/sda1 sectors / reads / read-ms |
|---|---|---|---|---:|---|
| ON | `falcon-t004-direct-high-on-20261018T061931Z` / `ab-falcon-t004-direct-high-on-20261018T061931Z.json` | 22.328 / 22.464 / 22.391 | 25.433 / 25.353 / 25.252 | 25.346 | +1,357,720 / +599 / +9,613 |
| OFF | `falcon-t004-direct-high-off-20261018T062533Z` / `ab-falcon-t004-direct-high-off-20261018T062533Z.json` | 21.818 / 23.211 / 23.115 | 26.183 / 26.084 / 25.983 | 26.083 | +1,357,416 / +890 / +11,870 |

Only one arm per mode. Queue residence dominates these request latencies; do not infer causal benefit from the mean difference. Run-window sector counts include setup and all RIDs and are not per-RID or per-layer device service measurements.

## Buffered Warm vs Buffered no-preread control (Queue Prefetch ON)

These are bounded low-concurrency ON arms with the same A/B target setup and 2,048-token B Extent fixture. Warm arm explicitly issues one B pre-read against the same isolated Extent, then `/flush_cache` clears only volatile Device/Host residency. It does **not** clear filesystem page cache. There is no global `drop_caches` operation. Cold/control arm skips that warm pre-read and invokes the same run's ordinary volatile-cache flush. `expected_direct_io=false`; no O_DIRECT events should exist.

| Condition | Run / manifest | B RID | Queue s | E2E s | Cached details | sda1 run-window sectors / reads |
|---|---|---|---:|---:|---|---:|
| Buffered + warm pre-read | `falcon-t004-buffered-warm-on-20261018T065332Z` / `ab-falcon-t004-buffered-warm-on-20261018T065332Z.json` | `60454c01a1f440149b1d8d9d0a268e51` | 17.554 | 17.802 | cached 2,048; Storage 2,042, Host 6, Device 0 | +216 sectors / +4 reads |
| Buffered, no warm pre-read | `falcon-t004-buffered-cold-on-20261018T065836Z` / `ab-falcon-t004-buffered-cold-on-20261018T065836Z.json` | `f60127b24aca453197937f9dcdfc7862` | 17.629 | 17.852 | cached 2,048; Storage 2,042, Host 6, Device 0 | 0 sectors / 0 reads |

The manifests differ in the intended warm condition and each has one arm only. The warm arm's measured response remains attributed to the Extent backend by SGLang metadata, while block counter deltas show that the overall run had only 4 extra block reads. This is consistent with the warm pre-read touching filesystem cache, but the block counters cannot prove those bytes were served from RAM page cache, cannot isolate B's read, and cannot exclude other cache layers. Treat as cache-condition characterization, not media benchmark or causal latency claim. Both samples have long queue waits and no replication.

## Limits and unfinished work

- All latency/throughput values above are descriptive single-run observations; they are not confidence intervals or performance claims.
- `/proc/diskstats` deltas are system/block-layer totals. They do not assign physical I/O to an RID and do not distinguish Linux page cache, device cache or actual media operations.
- No request RID → first GPU step → batch/kernel join was captured. Actual GPU Prefill/Decode execution, online L0, exclusive GPU occupancy, stall causality and I/O/GPU overlap remain `NOT_VERIFIED`.
- Frozen long greedy/multi-round/logits and FULL+MAMBA numerical oracle/tolerance remain absent; current `[10553]` is a one-token smoke, not that contract.
- Earlier failed/retried arms remain preserved by their unique run IDs and are excluded; only the four Direct arms and two Buffered cache-condition arms listed above are complete manifests.
- No commit or push was performed. Unrelated dirty work remains untouched.
