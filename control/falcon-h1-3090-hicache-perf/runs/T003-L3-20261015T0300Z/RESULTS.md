# T003-L3 controlled Host capacity trial (2026-10-15)

Status: NOT_QUALIFIED for Storage→Host→GPU read-back. The run proves the exact target FULL+MAMBA Host backup and same-run FULL+MAMBA Extent durable write, but target Host eviction/Storage-source restore was not reached. No L3 correctness or performance claim.

## Configuration and capacity
- Mainline `3090-24g-hicache`; model `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`, revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`; isolated service port 30128.
- Reused R11 Extent settings (extent 150,994,944 B, file/max 4,294,967,296 B, min free 10,737,418,240 B), with a fresh `extent/` directory so historical R11 data was not overwritten.
- `--hicache-size 1` (integer GiB; fractional values are rejected by argparse). Startup metrics: KV Host pool/usable 11,860 tokens; MAMBA Host usable 4 states; no reserve/margin. This is a functional test capacity, not production capacity.
- Historical R10/R11 used `--hicache-ratio 2`; metrics report 326,541 aggregate KV tokens/usable tokens and 91 MAMBA states. Target occupancy was 1,792 KV tokens / 1 MAMBA state. R11's 19 competitor loop reused the same competitor token sequence, so it was not evidence of unique-prefix capacity pressure.

## Run evidence
- Target prompt: exact R11 tokenizer input, 1,920 tokens, prompt SHA256 `987fd70caf2045c84b952b73b36e6b1086b089972eee730daf15b6225e071999`.
- Target identity: node `26`, final hash `721e82b98783b54519c46e4be90f5363be52d20bcbba82a614d022a61eafe09c`, output `[10553]`.
- Target H2D Host ACK: 1,792 tokens / 220,098,560 bytes; `finish_event_synchronized=true`. ACK snapshot reports FULL and MAMBA device+host present, both lock refs 0; `host_leaf_expected=false`, `host_leaf_eligible=false` at that point (device copies still present and non-leaf).
- Same-run target Storage submit operation 1, node 26/hash above: FULL 1,792 pages + MAMBA 1 page. `backup_ack_drain`: `result=complete`, `kv_durable=true`, `mamba_durable=true`, 1,792 completed tokens. `storage_persisted` was emitted, but it says `result=false`, `context_complete=false`; therefore the target storage frontier was not sealed/fully published despite component durable flags.
- Up to 14 deterministic distinct 1,920-token competitor requests were sent across the attempts (six in the first attempt, eight in the live corrected attempt). The R11-style pressure condition still did not remove the target Host copy. `hicache_host_used_tokens` plateaued at 7,162/11,860 tokens; MAMBA has its own 4-state usable pool and was not exhausted. No target Host `residency_detach`, Storage-source target restore, or restore H2D was observed. Per-request timings and raw detail are in `requests.jsonl`, `t38c-probe.jsonl`, and `server.log`.

## Implementation issue found and fixed locally
The first marker-gated host ACK crashed the scheduler with `UnboundLocalError: ComponentType` in `UnifiedRadixCache._t38c_log_host_ack`: a conditional local import shadowed the module-level name used by later marker-gated snapshot code when lock audit was disabled. Removed only the shadowing import from the pre-existing dirty `python/sglang/srt/mem_cache/unified_radix_cache.py`; Python compilation passes. The targeted eviction-membership pytest cannot collect in this environment because installed `sgl_kernel` does not export `fp8_scaled_mm`; no test assertion ran. No commit made.

## Conclusion / next action
The bounded 1-GiB test is sufficient to establish pool-sizing behavior, exact Host ACK and same-run FULL+MAMBA durable component write; it is not sufficient for L3 restore. Do not keep expanding requests. Decisive gap is target L3 chain publication (`storage_persisted result=false/context_complete=false`) plus no natural eligible target Host eviction. Inspect target storage-chain parent/anchor continuity and why the write-through persist epoch did not become context-complete; independently inspect MAMBA's 4-state pool/eligible Host leaves and pressure callback attribution. Any follow-up must use ordinary allocation/eviction, preserve locks, stop on exact target detach, and verify Storage source + H2D + output. Restore `--hicache-ratio 2` for any later performance A/B.

The final corrected server stayed healthy through the six-prefix bounded run; it was then deliberately stopped with SIGTERM to release GPU resources. Its background shell consequently reported exit 137 (`Killed`); this is expected from that deliberate cleanup, not evidence of an OOM or spontaneous server crash. Earlier trial servers also exited 137 after explicit termination during retries. The initial exit 127 was only a wrong relative launch path; no server started in that attempt. Port 30128 is released; RTX 3090 returned to 1 MiB/0%.
