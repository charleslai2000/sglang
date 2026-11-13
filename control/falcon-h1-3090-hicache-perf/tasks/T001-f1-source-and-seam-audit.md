# T001 — F1 lifecycle and trace seam audit

Status: **ACTIVE**

## Work area
`3090-24g-hicache` checkout only. Sibling `../sglang` remains untouched/read-only.

## Objective
Validate Falcon-H1 FULL/KV+MAMBA L2/L3 lifecycle and matched high-concurrency performance using existing SGLang/HiCache paths and evidence.

## Inputs
Frozen model revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`, checkpoint `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`; retained commits `601158469`, `fd93a2ec2`, `e80f144dd`, `481f2b485`.

## Completion
Target-specific D→H operation/ACK, measured Device eviction, Host and Extent restore, greedy equality; then matched GPU-only / Host / Extent concurrency profiles. Report all gates PASS/FAIL/NOT_RUN.

## Results
- Prior R4/R5 attempts do not prove target cold restore or L3. See retained R4/R5 reports and artifacts.
- R6 actual GPU trace proved a completed 1,920-token target build: session generation 1, node 26, hash `721e82b98783b54519c46e4be90f5363be52d20bcbba82a614d022a61eafe09c`. First and repeat output token IDs both `[10553]`; repeat hit 1,792 device tokens. A node/hash-bound commit row showed FULL+MAMBA, but had no operation/ACK closure.
- Source proves `backup_host_commit` is **not** transfer completion: `HiCacheController.write()` allocates host slots, enqueues operation, launches async device-to-host transfer, and returns before its `finish_event`; radix commits host metadata immediately. Later `writing_check`/`_drain_write_through_acks` synchronizes finish_event and consumes node IDs. R6 commit-only evidence cannot assert async ACK completion.
- R7 minimal instrumentation adds `CacheOperation.id`, operation/node and node/host-index mappings through merges to HiCacheAck, and emits marker-gated `backup_host_ack` after the existing event synchronization and ACK processing. It does not alter transfer/event execution. Hashes host slot indices only under durable marker. `CacheController.write()` is being kept compatible with its existing Tensor return; operation ID is propagated separately using existing operation metadata. Split replacement preserves operation identity.
- R7 tests: operation merge mapping, existing staged write dispatch, and targeted UnifiedRadixCache write-through/session trace selection: **12 passed, 11 skipped**. After identifying the actual runtime `_MambaStrategy -> build_hybrid_mamba_stack -> HybridCacheController` path, ordinary and Hybrid dispatch suite plus operation mapping: **16 passed, 1 skipped**. Compile and `git diff --check` pass.
- **R7B GPU ACK closure PASS:** fresh run `runs/R7B-20261010T0000Z/`, one service boot/run ID `falcon-r7b-l2-20261010T022143Z`; exact target hash `721e82b98783b54519c46e4be90f5363be52d20bcbba82a614d022a61eafe09c`, node 26, FULL+MAMBA commit operation 0, ACK event after `finish_event.synchronize()` with `ack_node_ids=[26]`, host-index digest `8347d43d…76c7a80`, 1,792 KV host tokens. A/A output `[10553]` and L1 repeat hit 1,792 device tokens. This validates target submit/ACK causality, not L2 restore.
- R7B bounded unique-prefix pressure reached 256 requests; aggregate host occupancy 162,379/326,541 tokens and eviction counter 381,783. Target node/hash has per-component `residency_detach` evidence for FULL KV and MAMBA device. It has no successful `residency_barrier`; target MAMBA host detach was also recorded, so FULL+MAMBA host residency is NOT proven. No H→D request ran. Driver correctly stopped before restore. Inference from source: session references were released through `/close_session`; high session-LRU protection ordering can defer eviction, but the observed MAMBA host detach means node-level state likely did not retain both host components. Inspect exact target detach rows and component cascade / tree-delete ordering before another pressure attempt.
- R7B trace also records exactly 257 `backup_host_ack` events, one per host commit; target row is causally matched through operation ID, node, hash, host indices, and finish event. Initial scratch driver attempts had mismatched session naming and were corrected; final L2 driver reached full bounded pressure and failed closed because no cold barrier, not due ACK ambiguity.
- Service stopped after driver exit; GPU returned to 1 MiB/0%, port 30127 closed; temporary marker/link cleaned. All R7B artifacts retained.

## Remaining
- Resolve why UnifiedRadixCache sees no operation ID despite edited CacheController returning `(host_indices, op.id)`. Inspect actual runtime class/path via source and worker imports; do not repeat GPU requests until CPU proof and one fresh service verifies non-null ID and ACK event. Current R7 trace contains two build events due multiple attempted server runs sharing the run directory; next attempt must use a new unique run dir or truncate only the known R7-owned trace after all service processes are stopped.
- Make driver select exactly the current `T38C_RUN_ID`/producer process and one build per fresh run. It currently assumes all rows in the run file are from one service boot.
- Once exact target ACK passes, close target session and verify lock/residency lifecycle. Reuse bounded unique-prefix pressure from R5 only with target identity barriers. Require target FULL+MAMBA both Device absent/Host present before revisiting; require Host source and H→D evidence plus greedy token equality afterward.
- Only after L2 PASS: start a new server with a unique Extent directory/config; prove FULL+MAMBA storage write/host eviction/storage read/restore and failures/cancel cleanup. `ExtentFileBackend` explicitly uses buffered pwrite/pread and no fsync; backend read bytes, page cache, and physical device I/O need separate evidence.
- Only after L3 PASS run the existing matched multi-turn benchmark for GPU-only / GPU+Host / GPU+Host+Extent, multiple useful concurrency levels and hit ratios, without profiling markers; profile separately.
