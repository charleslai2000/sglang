# F1-R4 — Falcon checkpoint-aware cache lifecycle attempt

Status: BLOCKED (cache lifecycle not accepted; performance NOT_RUN)

## Scope and identity
- Branch `3090-24g-hicache`, baseline `fd93a2ec260a9df47d0d21a5c0d5938d0a8c3a8e`.
- Model `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`, frozen revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`; service loopback `127.0.0.1:30126`; run evidence preserved under `runs/R4-20261009T0920Z/`.
- RTX 3090 was confirmed unused before this local experiment. R4 service stopped; final observation GPU 1 MiB / 0%, no listener on 30126. No sibling work touched.

## Evidence and interpretation
- The frozen-tokenizer request driver used 300-token prompts and 270-token greedy generations. First target request generated real D→H backup counters: KV 6,837+ tokens and MAMBA 27 states; Host KV capacity was 94,879 tokens and MAMBA host usable capacity 27 states. This establishes some D→H backup, not target-specific restore.
- Revisit before pressure had 256 device-hit tokens, zero host-hit and zero storage-hit tokens, with matching greedy output. Thus target was still at least partially in device cache; this is not H→D evidence.
- Later metrics reached `mamba_available_tokens=0`, `mamba_evictable_tokens=41`, and `evicted_tokens_total=6,337`, while host-used remained ~6,847 tokens, host capacity ~94,879, host-hit/storage-hit remained zero. MAMBA slot availability/evictability and global eviction counters do not identify the target node or prove its host restore.
- The pressure driver used different `SessionKey...` prefixes from the target, so it did not construct target descendants. Tree-core inspection confirms write-through backup is driven by repeated insert hits to the same non-evicted node (threshold is 1 for write_through, but hit count starts with its first insert); requests with unrelated keys cannot establish target reuse. It also confirms evicted nodes skip hit count. The workload therefore could not prove target backup/eviction/restore.
- The only Extent files are manifest/WAL/lock and a preallocated 4 GiB data file; WAL is metadata-sized (28 bytes), with no evidence of KV page writes, storage hits, backend read, or MAMBA sidecar restoration. Do not claim L3 success.
- Source review of `UnifiedTreeCore._insert_walk_step` and `_inc_hit_count_and_check` was read-only; no production rule/config changed.

## Result
- D→H: **PASS, limited to aggregate observed KV+MAMBA backup counters**; target-specific ownership/restore not established.
- Actual target device eviction: **NOT_PROVEN**. Aggregate eviction counters and exhausted MAMBA available slots are insufficient attribution.
- H→D, L3 write/read, joint FULL+MAMBA restoration, post-restore output equivalence: **NOT_RUN / NOT_PROVEN**.
- GPU-only / GPU+Host / GPU+Host+L3 performance baseline: **NOT_RUN**.
- R4 is not an acceptance run. Do not extrapolate from request count or ordinary greedy output.

## Decisive next action
Design a new, independently identified workload/run before restarting a service: use exact frozen-tokenizer IDs with a fixed shared prefix and session tails that cause repeated insertion of the same radix node; cross the 256-token MAMBA checkpoint grid deliberately. Measure actual Host occupancy versus 94,879-token capacity and 27-state capacity. Establish target-node D→H, then drive actual measured capacity pressure (not request count) until the target's device residency is absent; revisit the identical token IDs and require per-request host source plus load-back counters and identical greedy IDs. Only after that, prove target KV+MAMBA Extent write/read/restore and sidecar correctness. If evidence shows the current tree cannot expose target-specific residency/source, instrument only with user-authorized, profiling-only attribution or report the concrete blocker—never alter production thresholds to manufacture a hit. Performance stays gated on lifecycle correctness.
