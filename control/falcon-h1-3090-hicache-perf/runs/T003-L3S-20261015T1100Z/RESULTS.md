# T003-L3S same-process target eviction and Storage restore

## Scope / identity

Branch `3090-24g-hicache`, checkout HEAD `6331babe4e03781c65164e4d1e5f93b09ad58a94` with preserved dirty Runtime overlay. Server process 222402, model revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`, extent store reused from T003-L3 write run. GPU UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587`. This is a controlled function test, not a performance comparison.

Launch: `--max-total-tokens 8192 --hicache-size 2 --context-length 8192`, FULL+MAMBA, write_back, Extent backend. Startup gauges: KV Host usable/total 2,417 tokens; MAMBA Host usable 14 states. Thus target FULL 1,792-token prefix is representable (unlike prior 622-token Host configuration), but pool has little spare capacity.

## Same-process event sequence

- Seed request session `t003-l3s-target` queried the exact durable MAMBA Extent key (extent 0, generation 0, query_present), restored `[10553]`, and registered RID `f83d9631b1f142cc8d7285d664c91de2`, node 26, hash `721e82b98783b54519c46e4be90f5363be52d20bcbba82a614d022a61eafe09c`. H2D was synchronized (FULL 1,792 + MAMBA 2 state units; 359,456,768 B, 51.5983 ms). Closing seed session left the target in Host and Device.
- Bounded unique 1,920-token competitor requests 1–4 triggered ordinary allocator Device leaf eviction for node 26/hash: FULL 1,791 slots and MAMBA 1 state, both `residency_detach`, reason `device_leaf`. This is the normal driver/allocator path, not forced eviction.
- Competitor 5 triggered MAMBA Host LRU detach for target node 26/hash, reason 3. The subsequent `residency_free_complete` events show FULL Host 1,792 slots and MAMBA Host 1 state actually freed. This is the production Host eviction path, not merely an attempted candidate.
- Target restore RID `8abb6cc8509a468fb6ef9dabc896cc86` returned `[10553]`; request reports effective source `{storage:1791, device:1, host:0}`, cached tokens 1,792, E2E 549.7 ms and queue 299.4 ms. `load_back_registered` joins RID to node34/hash, matched Host tokens 1,791, FULL queued 1,791, MAMBA queued 2 states. H2D operation 4 ACK: synchronized CUDA finish event, FULL 1,791 + MAMBA 2, 359,411,712 bytes, 34.9796 ms. Request success follows the ACK; no scheduler-ready timestamp is claimed.
- Identity nuance: the surviving one Device token is the target prompt's terminal sentinel, part of the known prefix/tree shape. New competitor prefixes extend that shared prompt and cannot make this ancestor an eligible Host-only leaf under the configured 8,192 context length. Additional request pressure was stopped after a subsequent competitor began evicting itself. Do not claim FULL Storage source=1,792 or target all-component Host detach: observed exact Storage contribution is 1,791 and Device contribution 1.

## Result / limits

PASS: same process, exact target hash, normal FULL+MAMBA Device detach, normal target MAMBA Host detach with FULL Host slots released, Storage-backed restoration of 1,791 effective prefix tokens, synchronized H2D completion, and exact one-token greedy output `[10553]`.

NOT established: all 1,792 FULL tokens Storage-sourced with zero Device residue; long/multi-turn/logits/MAMBA-state equivalence; physical extent payload/pread bytes or device I/O attributable to this request; latency benefit or cache net gain. No Cache OFF/L2/L3 A/B. Runtime/test changes remain uncommitted due unrelated dirty hunks. Service on 30131 was stopped; no active process/port, GPU memory returned to 1 MiB.

## Artifacts

`launch.sh`, `driver.py` (first driver intentionally stopped on missing `build_complete` event; Storage restoration does not create that event), `requests.jsonl`, `t38c-probe.jsonl`, `restore_result.json`, `server.log`. The follow-up bounded drivers ran inline and are reflected in the event log.
