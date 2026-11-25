# T003-L3 cold-start FULL+MAMBA Storage→Host→GPU recovery

Status: **PASS for Storage-source cold restore and exact greedy output**. The preceding target capacity-eviction path remains unqualified; this run validates restore directly from the exact durable Extent object after a fresh server/cache process starts empty. This does not claim a single-session natural target Host eviction→restore cycle.

## Identity and source
- Branch `3090-24g-hicache`; model Falcon-H1-7B-Instruct-GPTQ-Int4, revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`; service port 30129, served-model-name `falcon-h1-t003-l3`.
- Target prompt: 1,920 IDs, SHA256 `987fd70caf2045c84b952b73b36e6b1086b089972eee730daf15b6225e071999`; expected exact final hash `721e82b98783b54519c46e4be90f5363be52d20bcbba82a614d022a61eafe09c`.
- Durable object was written by prior T003-L3 run, node26, Extent backend. Cold process had zero Host used tokens, and request reported `device=0, host=0, storage=1792` from `ExtentFileBackend`, proving no L1/L2 source. Output exactly `[10553]`.
- T38C storage query: MAMBA exact key `721e82...eafe09c.mamba_falcon-h1-t003-l3_0_1`, `extent_id=0`, `extent_generation=0`, `result=true`, `query_present`. Restore operation RID `f160e16a7624446a9038477ccdad6c97`; exact FULL KV hash matched target. `load_back_registered` ties that RID to node26/hash with matched Host 1,792, FULL queued 1,792 tokens, MAMBA 2 state units.

## Transfer and timings
- Storage hit: 1,792 tokens; new prefill/input: 128 tokens; device hit=0; host hit=0.
- Extent physical syscall-byte count is not exposed to scheduler metrics and the run did not export `ExtentFileBackend.stats_snapshot()`. To distinguish physical I/O, the test ran `sync`, then `sudo -n sh -c 'echo 3 > /proc/sys/vm/drop_caches'` before the one restore. `/proc/diskstats` on `sda` advanced 454,952 sectors = **232,935,424 bytes** over the request. This is block-device traffic during the isolated cold read window, not asserted equal to Extent requested bytes; extent/file read amplification and metadata are included. It is not an OS page-cache-served read claim.
- H2D completion: event `load_back_ack_batch`, operation 0, `finish_event_synchronized=true`, FULL KV 1,792 + MAMBA 2 state units, **359,456,768 bytes**, CUDA event **51.1867 ms**.
- Request: e2e **0.9254 s**, queue **0.5959 s**, wall client elapsed **0.9323 s**; output `[10553]`. Host pool after restore used 1,792 / 326,541 tokens.

## Evidence boundaries
- Source proves same-process `storage_query` match and the request's source breakdown `storage=1792`; H2D operation/RID/hash join proves transfer completion and Forward output. The byte/time table is in `requests.jsonl`, `before_restore.metrics`, `after_restore.metrics`, and `t38c-probe.jsonl`.
- A prior exact target write `storage_persisted result=false/context_complete=false` was a **marker-gated diagnostic context binding failure**, not functional publication: `complete_trace_context()` requires session_id, build_rid, generation and matching node/hash, while that ordinary request had `session_generation=None` and hence no context. In the same ACK branch `advance_storage_persisted(node_id)` had already run and the event reports `storage_version=1`; Storage keys and the fresh read above prove data remained queryable. Do not use this diagnostic boolean as the functional chain-publish predicate.
- This cold-start restore is not proof that normal Host allocator eviction removed this target. A separate controlled 1-GiB `write_back` test first cold-restored target successfully, then used 8 unique competitors without device eviction; a separate 1-GiB Host pool had only 622 usable KV tokens, less than the target. With `--max-total-tokens 4096`, after 6 further bounded requests the normal device allocator evicted 756 slots + 1 MAMBA state, but it was competitor hash `b1c762...`, not target. No forced host detach occurred. Do not represent this as target eviction or as production-capacity pressure.
- Existing production `cache.evict_host()` tests passed 18 passed/2 skipped; separate MAMBA membership regression 4 passed. New `ComponentType` local-shadowing regression passes (1 passed) and was confirmed to fail with the original shadowing line (`UnboundLocalError`) before restoring the fix.

The recovery service and bounded eviction service were stopped; their ports were released and GPU was returned to idle.
