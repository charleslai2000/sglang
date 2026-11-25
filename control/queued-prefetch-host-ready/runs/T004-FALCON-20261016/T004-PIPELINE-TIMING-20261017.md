# T004 pipeline timeline and efficiency — existing three ON/OFF pairs

Date: 2026-10-17. This is an offline re-join of existing same-run artifacts only; no new profiler, cross-run event join, or new GPU workload. Pair modes are Queue Prefetch OFF=`DEMAND_RETRY` with demand restore still enabled, and ON=`READY_HORIZON`. All six runs have independent server, request and probe artifacts. Model revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`; max-running=8, max-total-tokens=32768, Ready Horizon enabled in both modes. The workload deliberately holds eight active requests and three Pending B/C/D until A finishes; these timings are stress-queue residence, not a representative steady-state latency benchmark.

## Join method and evidence boundary

Join each measured request only within its own run by HTTP `meta_info.id`/RID to request JSONL, probe JSONL and server log; storage events use RID; `ready_host` and `admission.v2` use RID plus monotonic timestamps. `load_back_registered` carries RID and FULL node ID; match `load_back_ack_batch.node_operation_ids` to that node ID in the same run. Do not match ACKs by proximity alone. `ready_host_observed` is deliberately not used for chronology. The durable operation ID linking L3 read → restore operation → H2D ACK is missing in the current event schema (RID→node and node→operation are available, but no common restore operation ID), so the report labels this composite relationship as node-linked, not operation-ID exact. No matching first-GPU-step event is present in any of the six runs.

The artifacts provide: request receipt / admission-derived `forward_entry_time` / prefill-finished / request-finished / client completion; prefetch origin, storage-query result, L3-to-Host completion; Host-ready and admission; node-linked H2D ACK. They do not provide first GPU execution, request-tagged Prefill and Decode step intervals, per-RID L3→L2 vs L2→L1 operation boundaries, physical-device I/O, or GPU idle/busy. Server scheduler activity confirms eight running requests and three queue entries, but these do not replace unavailable per-RID GPU stages.

## B/C/D exact-RID timeline

Times below are elapsed seconds. `queue` / `E2E` are SGLang response metadata; `arrival→admit` uses `forward_entry_time - request_received_ts`; `admit→Prefill finish` is service residence before Prefill completion; `Prefill finish→Complete` is request metadata difference. `L3 query→Host` uses `pc_storage_query.ts` to `pc_l3_host.ts`. Queue E2E includes imposed waiting. All B/C/D prompts have 2,111 tokens and output one token; A has 2,048 input / 1,024 output and is a real long-Decode occupant, not a single-token/max-running=1 benchmark sample.

| Pair/mode | RID (B / C / D) | Origin | L3 pages (FULL; MAMBA) | L3 query→Host | ready→admission | queue | E2E | arrival→admit | admit→Prefill finish | Prefill finish→complete |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 OFF | `2ee3a20a23b241aeb8f4782fb0116da6` | DEMAND_RETRY | 2048; 2048 | 0.36 | 0.004 | 21.227 | 21.683 | 21.24 | 0.46 | 0.003 |
| 1 OFF | `74d1db4d3b234082aee95851148562ef` | DEMAND_RETRY | 2048; 2048 | 0.95 | 0.002 | 21.712 | 22.123 | 21.48 | 0.51 | 0.003 |
| 1 OFF | `1be5d6e754004b64b9cba9f0bee258fc` | DEMAND_RETRY | 2048; 2048 | 1.34 | 0.002 | 22.010 | 22.305 | 21.78 | 0.37 | 0.003 |
| 1 ON | `5b545d501ee04cf3866db4f7cb34e5b0` | READY_HORIZON | 2048; 2048 | 0.29 | 21.042 | 21.336 | 21.335 | 21.35 | 0.212 | 0.003 |
| 1 ON | `daf335178a9a4d42a6afa3609de6676b` | READY_HORIZON | 2048; 2048 | 0.38 | 21.007 | 21.391 | 21.768 | 21.48 | 0.290 | 0.003 |
| 1 ON | `daeadd26a4244e9bb428aa68b5dd2fc9` | READY_HORIZON | 2048; 2048 | 0.61 | 21.146 | 21.761 | 22.080 | 21.77 | 0.305 | 0.003 |
| 2 OFF | `6effba5e4c8146b790d989fbec8e8ccc` | DEMAND_RETRY | 2048; 2048 | 0.39 | 0.004 | 21.371 | 21.842 | 21.391 | 0.448 | 0.003 |
| 2 OFF | `cee81459e9bf48dc86b572125cbf1643` | DEMAND_RETRY | 2048; 2048 | 0.98 | 0.002 | 21.889 | 22.391 | 21.892 | 0.494 | 0.004 |
| 2 OFF | `ae0792c6f491433a90d301ada202311e` | DEMAND_RETRY | 2048; 2048 | 1.48 | 0.005 | 22.293 | 22.667 | 22.301 | 0.363 | 0.003 |
| 2 ON | `fb2111f62dba4faa99c020fdfc7dd203` | READY_HORIZON | 2048; 2048 | 0.30 | 20.965 | 21.275 | 21.285 | 0.220 | 0.003 |
| 2 ON | `e85c387f678e4ca991c4a28f337c3e79` | READY_HORIZON | 2048; 2048 | 0.40 | 20.932 | 21.341 | 21.432 | 0.295 | 0.003 |
| 2 ON | `fbe89b2c7a5c4e8d87d106c304c8cf0f` | READY_HORIZON | 2048; 2048 | 0.61 | 21.099 | 21.717 | 21.735 | 0.318 | 0.003 |
| 3 OFF | `9aa98bdb9d81426591652bac130b9154` | DEMAND_RETRY | 2048; 2048 | 0.38 | 0.004 | 21.215 | 21.767 | 21.217 | 0.547 | 0.003 |
| 3 OFF | `1633eb9b2a144fd2b563cdbd163c2625` | DEMAND_RETRY | 2048; 2048 | 0.93 | 0.003 | 21.669 | 22.015 | 21.675 | 0.338 | 0.003 |
| 3 OFF | `6d47d93a2356495eb386dc2013cce99d` | DEMAND_RETRY | 2048; 2048 | 1.28 | 0.002 | 21.911 | 22.187 | 21.920 | 0.264 | 0.003 |
| 3 ON | `b6f6716b3c1b48de83f6b146242f9e89` | READY_HORIZON | 2048; 2048 | 0.29 | 20.995 | 21.290 | 21.301 | 0.212 | 0.003 |
| 3 ON | `f1e176b98de442a3be99eb801c350023` | READY_HORIZON | 2048; 2048 | 0.38 | 20.954 | 21.342 | 21.421 | 0.280 | 0.003 |
| 3 ON | `0c132c726b5c47a88bc2fff5576e566c` | READY_HORIZON | 2048; 2048 | 0.61 | 21.086 | 21.699 | 21.704 | 0.300 | 0.003 |

The three full-queue OFF and ON run medians B/C/D response E2E are: pair 1 OFF 22.123s / ON 21.768s; pair 2 OFF 22.391s / ON 21.729s; pair 3 OFF 22.015s / ON 21.704s. Across nine queued requests per mode, OFF E2E median 22.123s (range 21.683–22.667) and ON median 21.729s (range 21.507–22.080). The runs are short, imposed-wait, one-token B/C/D completions after a 1,024-token A decode; they are not sufficient to assert net performance benefit or production throughput. OFF Queue Prefetch did not disable demand restore. In pair 2/3, OFF `ready_host` timestamps precede admission by 1.6–5.1ms even though `ready_host_observed=false`; ON READY_HORIZON has ~20.93–21.15s ready lead while requests wait behind A. This demonstrates actual Host-ready timing versus the decision-path boolean. Pair 1 OFF READY/admission chronology is now recovered from the run-specific server log and monotonic marks; the summary JSON itself did not embed the parsed lines.

Node-linked H2D ACKs are present for B/C/D. Bytes by request (370,720,768 or 370,810,880 B; MAMBA included) and ACK service/event timings by pair/mode:

| Pair/mode | B / C / D ACK event `gpu_elapsed_ms` | B / C / D ACK event time minus admission |
|---|---|---|
| 1 OFF | 133.47 / 36.04 / 35.93 ms | 584 / 398 / 365 ms |
| 1 ON | 36.82 / 36.79 / 35.94 ms | 219 / 394 / 309 ms |
| 2 OFF | 139.07 / 35.73 / 57.48 ms | 597 / 499 / 468 ms |
| 2 ON | 37.20 / 35.68 / 36.22 ms | 245 / 400 / 321 ms |
| 3 OFF | 134.38 / 36.79 / 35.89 ms | 551 / 341 / 320 ms |
| 3 ON | 37.49 / 36.22 / 35.67 ms | 218 / 381 / 303 ms |

ACK event GPU timing here is resource service duration, not request waiting duration. It occurs after admission in these rows; it is not a first GPU execution marker. H2D node IDs are matched within each run; lack of an explicit restore `operation_id` in the registration/ACK cross-event envelope remains an attribution limitation.

## Throughput and background GPU evidence

The measured queued B/C/D cohort produces three tokens over 22.2–22.9s from first request receipt through final completion (about 0.131–0.135 tok/s); this metric is dominated by the intentionally retained ~21s wait and one-token output limit and is not a useful saturated service throughput result. A's 1,024-token decode is the only long Decode in each arm; its run-level E2E was 26.76–27.55s. No valid L0, GPU Busy/Idle, SM Active/Compute, Tensor Active, or DRAM read/write/%Peak measurements are joined to these six runs. Historical R17 NCU and offline CUPTI are not current online measurements and are not substituted. The installed R17 online timeline/counters cannot be joined to these T004 RIDs.

Extent counters are process/run cumulative; use same-run snapshots bracketing the B/C/D measured workload, not sum request-level rows or pair arms. In each of the five complete arms (pair1 OFF lacks a completed measured artifact), the workload-window deltas are `bytes_read=694,898,688`, `preads=18`, `physical_bytes_read=694,898,688`; same-run query hits are 2,048 FULL pages and 2,048 MAMBA pages per B/C/D. This is process-window I/O, not per-RID attribution. It does not distinguish Linux page-cache hits from physical media, despite Extent's `physical_bytes_read` naming; no device-level counter was captured. L3→L2 bandwidth is therefore only the aggregate Extent window: 694,898,688 bytes / 18 preads across the complete five arms; no per-request byte rate. L2→L1 bytes are node-linked ACK bytes above, but exact wait-versus-service decomposition and per-RID bandwidth are not identified. Prefetch reads overlap ~21s queue wait by event chronology; no first-GPU marker permits quantifying compute overlap or saved GPU idle. No saved-prefill token/time claim is supported: all measured target prompts requested 2,111 prefix tokens while durable prefix only restored 2,048, and each has fresh suffix; measured restore is partial and actual recompute/Prefill remains material.

## Conclusions / limitations

- The existing three ON/OFF pairs are mechanics samples only. OFF = `DEMAND_RETRY`, ON = `READY_HORIZON`; demand retry legitimately restores L3 and may make Host-ready before admission. The RUN timeline, not `ready_host_observed`, is the chronology evidence.
- In pair 2/3, OFF's just-in-time ready→admit is ~1.6–5.1ms; ON has ~20.9–21.1s queue-overlap lead. This is real stage scheduling distinction; end-to-end pair medians differ modestly under the imposed queue load and do not establish a causal net performance gain.
- The user-directed immediate high-pressure workload requirements are only partially met by these already-existing samples: eight active and three Pending were observed; D/C/B are distinct L3-backed requests; A has 1,024 decode. But measured B/C/D output only one token each, and no representative high-concurrency Prefill+long Decode batch was measured. Do not label the existing runs a complete high-pressure performance experiment or declare task done.
- No L3 page-cache/device media split, GPU Disk Stall, stage overlap with first execution, GPU Busy/Idle, phase L0 counter, throughput benefit, or saved Prefill is proven. Preserve those as explicit NOT_VERIFIED, not zero.
- Long multi-round greedy/logits/FULL+MAMBA numerical acceptance and required regression/clean integration remain outstanding. No source was changed by this re-analysis and no commit/push performed.

## Source artifacts (same-run only)

For each listed `falcon-t004-ab{1,2,3}-{off,on}-queuecheck-20261017T{190632,191000,191407,191605,191802,191958}Z`, use matching:
- `ab-<run>.json` (RID, response metadata, request identities)
- `requests-<run>.jsonl` (client monotonic submit and HTTP completion)
- `t38c-probe-<run>.jsonl` (RID L3 query/Host completion, `load_back_registered`, H2D node operation ACK and Extent cumulative snapshots)
- `server-<run>.log` (READY and `admission.v2` monotonic markers, scheduler occupancy)

Pair 1 OFF measured artifact is present at `ab-falcon-t004-ab1-off-queuecheck-20261017T190632Z.json`; earlier failed attempts that ended before measured work retain their original logs and are not samples.
