# T004 high-pressure per-RID phase ledger

Reproducible exact-run rejoin: `rejoin_highpressure.py` reads only the two named run manifests, probe JSONL, server logs and driver artifacts, and emits `highpressure-stage-ledger-20261018.json`; `analyze_highpressure_ledger.py` summarizes without splitting shared work. Each arm manifest names Falcon revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`, 8/32768/queue-8, isolated Extent, and ON/OFF mode. Source Git HEAD and executable/binary SHA were **not recorded** by either original run's manifest/driver log; ledger marks both `NOT_RECORDED`, not inferred from the current checkout. No cross-run joins.

Each measured B/C/D prompt was 2,112 tokens; corresponding same-run durable prefix had 2,048 FULL KV + MAMBA coverage, leaving 64 suffix tokens for new Prefill, and output was 128 tokens. A was a 2,048-token prompt / 1,024-output Decode occupant. Request stage timestamps are HTTP metadata (not kernel boundaries). L3 event times are wall clock; Host-ready/admission/H2D are monotonic and joined only within the same run. Extent event spans are not physical-device service time.

## RID phase table

Seconds except H2D service. `H2D wait` is admission monotonic → matching ACK monotonic **only for a uniquely owned ACK**. ON C/D match the same ACK batch, so per-RID wait and per-RID service are `SHARED_BATCH` and not split.

| Mode | Label / RID | Prefetch origin | arrival→admission (includes queue) | queue_time | L3 query→Host event span | Host-ready→admit | H2D wait | H2D service | admission→Prefill metadata | Prefill metadata→finish | E2E |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| OFF | B `4bda23c9758f44b495abb91ec5170717` | DEMAND_RETRY | 21.117 | 21.114 | 0.374 | 0.004 | 0.590 | 134.49 ms | 0.547 | 4.020 | 25.685 |
| OFF | C `3d5c6f5d075d4bd4b7ddbbb41318d30b` | DEMAND_RETRY | 21.613 | 21.606 | 0.962 | 0.002 | 0.348 | 45.73 ms | 0.345 | 3.627 | 25.585 |
| OFF | D `95421668e309462da6dadc8a2f7dd8a6` | DEMAND_RETRY | 21.865 | 21.854 | 1.312 | 0.002 | 0.327 | 35.25 ms | 0.262 | 3.358 | 25.485 |
| ON | B `3ed1086d9950458cad2e7c6d23728d87` | READY_HORIZON | 21.374 | 21.358 | 0.320 | 21.031 | 0.250 | 36.38 ms | 0.244 | 3.994 | 25.613 |
| ON | C `6ccf3b6097184df88e38801e84181ae1` | READY_HORIZON | 21.550 | 21.461 | 0.380 | 21.071 | SHARED_BATCH | SHARED_BATCH | 0.453 | 3.531 | 25.535 |
| ON | D `b150555a582c44979978f652410a5a61` | READY_HORIZON | 21.449 | 21.433 | 0.603 | 20.822 | SHARED_BATCH | SHARED_BATCH | 0.454 | 3.531 | 25.434 |

ON C/D's one synchronized ACK event is `falcon-t004-highpressure-on-20261018T005414Z:376345:128483964895360:radix:240`, with node/operation pairs `(81,28)` and `(83,29)`, 4,086 FULL KV tokens + 4 MAMBA state units total, 741,531,648 B, 79.05 ms. The batch service interval is one operation, shown once in source event evidence, not added twice or split across requests. OFF B/C/D each have separate ACKs.

A OFF RID `28aaa34ffdf54929bd0d8b474b900d7d`: arrival→forward 0.014s, metadata Prefill-finish 0.567s after forward, finish 26.453s after Prefill-finish, E2E 27.035s. A ON RID `9957d137fb964ce8bcf73960c8882ce1`: 0.013s, 0.567s, 27.100s, 27.680s. No GPU activity attribution for A.

## Interpretation and unverified metrics

- OFF B/C/D Host-ready is followed by admission in ~2–4 ms; ON has ~20.8–21.1 s between Host-ready and admission. OFF uses demand-retry, ON stages ahead with Ready Horizon. The ON early staging overlaps the deliberate queue residence; it does not remove queue delay.
- Each B/C/D has three `pc_get_v2` events; first→last spans are ~0.316–0.326s OFF / 0.231–0.242s ON. These event spans are not additive/disjoint service intervals. Extent snapshots are process-window totals; they do not distinguish OS page cache from physical media or map bytes to each RID.
- Request cache metadata reports 2,048 cached tokens; the 64-token prompt suffix is beyond that durable prefix. `prefill_finished_time - forward_entry_time` includes scheduler/forward-stage time and is not GPU Prefill execution. `request_finished_ts - prefill_finished_time` includes Decode and non-kernel overhead, not GPU Decode execution.
- H2D service and admission→ACK chronology are distinct. Admission→ACK may include unrelated overlap; it is not GPU-ready dispatch wait. No same-run RID→first GPU step→batch→kernel join exists. Actual Prefill/Decode GPU time, GPU idle/busy efficiency, online L0, exclusive occupancy, and I/O-caused GPU disk stall are `NOT_VERIFIED`, not zero. T002 CUDA-graph-only CUPTI and offline Falcon forward metrics do not cover/join this eager-Prefill service run and cannot be substituted.
- B/C/D mean E2E: OFF 25.585s, ON 25.527s; means contain ~21.5s queue residence. One arm per mode; descriptive only, no causal/net-benefit or continuous saturation throughput claim.

Run the two scripts above to regenerate and summarize. The JSON carries each RID's producer events, FULL/MAMBA counters, ACK event IDs/operation mappings, metadata marks, and explicit `NOT_VERIFIED` fields.
