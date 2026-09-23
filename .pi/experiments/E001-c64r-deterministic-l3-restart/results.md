# E001 results

Status: CLOSED — final consolidation superseded the unfinished HiCache acceptance line; no production observer or persistent-L3 defect was established.

## OBSERVED

- Added `ExtentFileBackend.inspect_storage_key(storage_key)` as a read-only snapshot API. It accepts the already-scoped exact runtime key, reads the allocator index under the backend lock, validates generation without calling mutating `allocator.lookup`, and does not touch LRU recency. It returns the existing immutable `ExtentRef` (slot, generation, offset, length) or `None`. No writer/eviction/retention/restore code changed.
- Added a unit contract test for live entries, absent key, unchanged LRU order, and canonical backend close/reopen recovering identical refs. Directly ran that single unittest case: PASS (0.030 s).
- V3 explicit experiment-local Scheduler.__init__ around-hook bootstrapped successfully in the real serving process. It captured `scheduler.tree_cache`, its HiCacheController, and that controller's actual `ExtentFileBackend` (`backend_id=139533679544176`, controller/cache identities recorded in `live-progress.json`). The observer used the controller's `get_hash_str` and backend `_storage_key`, then called `inspect_storage_key` twice on the same one-page tail key; exact output was internally stable. `RUNTIME_OBSERVER=PASS` for object/key/ref plumbing. The test-only loopback observer did not open a second backend and was not reachable except on 127.0.0.1.

- Run 014 ordinary shutdown checkpointed a manifest (20,604 bytes) and WAL; fresh canonical backend recovery read UUID `777933381592a4ad09081d4da9f712bf`, namespace epoch `016acab5d71fb13ee482f4d21091b466`, and reported target key absent with WAL generation 0. No recovery loss is inferred because the same key had already been absent in the live observer.
- C6.4R-V review of `ExtentFileBackend._acquire_backend_meta_lock` and `extent_metadata.acquire_meta_lock` confirmed that a second backend instance cannot safely open the same namespace while the serving backend is live: recovery uses an exclusive flock and fails closed on lock contention. An in-process same-writer lookup is the only viable live query; no unvalidated alternate lock-free recovery was used.
- A draft test-only scheduler plugin and driver were removed before runtime launch. They must not be treated as a verifier or authority. The failed `run.py` was removed. No production source semantics changed and no new runtime root/server was started for C6.4R-V.

- Follow-up runs 005–012 used exact HTTP chat bodies and server-equivalent template rendering/tokenization. Each successful 50,000-token target request matched the locally reconstructed chat-template token IDs; each run then sent eight unique ~60,000-token fillers. These were larger than the originally intended minimal filler workload and are retained as failed runs, not treated as acceptance.
- Direct logs from run 012 show successful KV extent writes (e.g. `keys_n=1024`, `bytes=16777216`) and metadata/WAL growth. Startup confirms the actual extent root `/data/l3/c64r-qwen-20260923-012`, 64 MiB extents, 1024 slots, 100Gi max and 50Gi minimum-free watermark. The target membership check nevertheless found no manifest before cleanup; its probe is not sufficient because it reads only the manifest and its fallback WAL replay incorrectly used a post-replay index as a pre-replay checkpoint.
- Five completed roots (005, 009–012; 007/008 were aborted during harness integration) remain under `/data/l3`; roots 005, 009–012 contain large WALs and sparse data files. All servers exited, GPU returned to 4MiB used / 24121MiB free. C6.1 remains untouched. Do not interpret these non-live manifest snapshots as proof of no L3 publication: WAL may contain SET records not checkpointed.
- The earlier `run.py` was removed; it used a known-invalid manifest/WAL inspection path and cannot prove membership. No fresh-process replay was attempted.

- Canonical branch `3090-24g-opt` reached `937946bf975635cb29bbf9fc57461a5b33b611c3`. Experiment procedure/result changes are being recorded here; source code is unchanged.
- User authorized deletion of runtime HiCache data beneath `/data/l3`. All 37 immediate child roots other than protected `/data/l3/c61-qwen-20260922-220343` were checked unlocked with no active SGLang/GPU process and removed. No data outside `/data/l3` was touched. Space rose from 32 GiB to 215 GiB. Historical C6.1 root remains intact.
- `/mnt/data` is not a separate mount in this namespace; `/data/l3` is on `/dev/sda1` mounted at `/`.
- Current production contract retained: Qwen3.5-9B W4A16, TP=1, fp8_e4m3, host cache, `write_back`, extent, `wait_complete`, hicache-size 32, max 100Gi, min-free 50Gi, 64MiB extent and 64GiB sparse file.
- Earlier run 002 process identity: canonical Python `/home/ubuntu/venvs/sglang-3090/bin/python` importing `/home/ubuntu/workspaces/3rdparty/sglang/python/sglang`; frozen launch template was not used as authority.
- Exact current fixture HTTP body is `/data/l3/c64r-qwen-20260923-002-request.json`, SHA256 `3bc05ba7dd516616315cc083ce8f8f5d49b76e4b9a82e028f1f5da29680e574c`. It is a 254-token neutral document plus exact instruction to return `FIXTURE_OK`, temperature 0, max_tokens 64, non-thinking template option, and metadata request. Earlier 26-token test body is superseded for the fixture.
- In earlier run 002, `return_prompt_token_ids=true` was requested but prompt IDs did not appear; this was superseded by run 014 where exact target IDs were returned and matched.
- A short response was not a correctness pass: one returned a partial prompt excerpt instead of `FIXTURE_OK`; another exact answer passed on the older 26-token body only. Longer input attempt while server had exited returned connection failure and did not change cache state.
- Earlier run 002 had no valid cache population (Host metric zero, no extent writes, empty manifest); its miss was not persistence evidence. This is superseded by run 014, which did log extent writes but did not establish the exact target page as live.
- The prior runtime was stopped and GPU returned to 4MiB used / 24121MiB free. Root was retained. No live key was lost.
- Existing production gate `tools/gates/production/f2_restart_recovery.py` already implements real-process restart and extent membership, but its default 62K-token prompt/pressure is substantially larger than C6.4R's desired minimum; reuse only after reducing to the smallest bounded chain/fillers and retaining existing semantics. Its `gate_common.py` can capture exact tier details and snapshots.
- Backend `close()` always checkpoints current allocator (`extent_file_backend.py` around lines 2758–2785); with a nonempty valid index it should leave manifest entries after graceful stop. This is useful for direct before-shutdown and after-reopen proof.

## INFERRED

- First V3 fixture (run 014, root `/data/l3/c64r-qwen-20260923-014`) served the exact 60,006-token target; server prompt IDs matched local template reconstruction and output was the expected marker `C64R-V2-EXACT-7C`. Two distinct ~60k-token filler completions completed and logs showed extent writes. After population, the same-runtime observer derived final target page hash `577dbe97517342b5c458f8bd0aa14ee441c24d3edf3b655d287a2922fbe164d7` and scoped key `577dbe97517342b5c458f8bd0aa14ee441c24d3edf3b655d287a2922fbe164d7_qwen35-9b-w4a16_0_1`; `inspect_storage_key` returned `None` (live_count=0). Thus `LIVE_L3_KEY_BEFORE_SHUTDOWN=NO`; fixture correctly stopped before restart replay.
- Runner failure cleanup sent SIGTERM to the writer. A separate fresh process opened the root through canonical `ExtentFileBackend` recovery: same key absent (live_count=0), WAL generation 0. Because the key was absent before close, this does not establish a recovery defect.

- Extent writes prove some keys reached L3 but not this exact target-tail key. Run 014's observer used the serving controller's hash method, page size, backend key transform, and suffix; the exact final target page was absent after two completed fillers. Evidence localizes the first failed gate to target-page live publication/retention before shutdown; it does not distinguish never-backed-up from later evicted/replaced.
- The repeated eight-filler workload is not the desired minimum. Further pressure runs are unjustified until the target's runtime hash sequence and allocator state can be read correctly during the live process.

- 50GiB is the LRU free-space watermark, not the fixture's required allocation. Capacity is resolved and not a blocker.
- A target prefix ~254 tokens remains within GPU cache and is not automatically demoted; one short unrelated filler (~299 tokens) only showed device hit. Need minimal natural LRU eviction to move target to Host, then ensure write-back from Host to L3 without changing cache semantics.
- Runtime chat token IDs should be captured using the production ChatCompletionRequest's effective template arguments and compared against server `/generate` behavior; exact body alone is insufficient to certify template/hash identity.
- Use the existing frozen cache contract, but do not create an uncontrolled 57K×many pressure workload. Start with one target (actual prompt tokens obtainable from chat meta) and minimally sized fillers; inspect exact eviction/writeback acknowledgements after each bounded step.

## UNRESOLVED

- Why the exact target final-page key was absent after two completed fillers despite extent writes; determine whether that page's backup was acknowledged and whether its runtime hash chain matches the observer's whole-request chain.
- A bounded population pattern that makes the designated target page live before shutdown without changing retention or cache semantics.
- Fresh-process replay with direct storage hit/read/restore evidence and response correctness; not reached because pre-shutdown liveness failed.

## Current gate

```text
RUNTIME_OBSERVER=PASS
EXACT_TARGET_KEY_CAPTURED=YES
LIVE_L3_KEY_BEFORE_SHUTDOWN=NO
LIVE_L3_KEY_AFTER_WRITER_EXIT=NO
HICACHE_STORAGE_REUSE=NOT_TESTED
HICACHE_STORAGE_RESTORE=NOT_TESTED
PERSISTENT_L3_ACROSS_RESTART=NOT_TESTED
HICACHE_CORRECTNESS=NOT_TESTED
STORAGE_CAPACITY_GATE=PASS
EXACT_CHAT_TEMPLATE_IDS=SERVER_RETURNED_AND_MATCHED_FOR_TARGET
L3_EXTENT_WRITES=OBSERVED
CANONICAL_TREE_CLEAN=NO (changes remain uncommitted)
```

No persistent-L3 defect is declared: no exact target key has been confirmed live before shutdown. The immediate blocker is sound runtime allocator/key evidence. Preserve the 005, 009–012 roots and evidence; never delete or overwrite C6.1. Before any additional workload, repair the external harness using the backend's actual live allocator state or correct checkpoint-plus-WAL replay, and reduce filler count. The current `run.py` must not be used as-is.
