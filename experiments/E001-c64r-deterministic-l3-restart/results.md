# E001 results

Status: BLOCKED — target liveness remains unproven; the proposed concurrent source-native verifier was rejected before use because canonical backend recovery takes an exclusive namespace lock.

## OBSERVED

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
- Exact runtime root `/data/l3/c64r-qwen-20260923-002`, run ID `c64r-qwen-20260923-002`. Correct process identity in the successful runtime was canonical Python `/home/ubuntu/venvs/sglang-3090/bin/python` importing `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang`; the unresolved frozen `launch.sh.tmpl` was not used as an identity authority.
- Exact current fixture HTTP body is `/data/l3/c64r-qwen-20260923-002-request.json`, SHA256 `3bc05ba7dd516616315cc083ce8f8f5d49b76e4b9a82e028f1f5da29680e574c`. It is a 254-token neutral document plus exact instruction to return `FIXTURE_OK`, temperature 0, max_tokens 64, non-thinking template option, and metadata request. Earlier 26-token test body is superseded for the fixture.
- `return_prompt_token_ids=true` was requested but prompt IDs did not appear in the chat response, despite `return_meta_info=true`; response serialization confirms this branch can omit these fields. Do not claim token IDs captured from responses so far.
- A short response was not a correctness pass: one returned a partial prompt excerpt instead of `FIXTURE_OK`; another exact answer passed on the older 26-token body only. Longer input attempt while server had exited returned connection failure and did not change cache state.
- No valid cache population was observed in the prior process attempt: Host metric remained zero, no extent write/persist events, manifest `entries=0`, sparse data actual usage ~36KiB. The fresh process reopened same empty root, so its storage miss says nothing about persistence correctness.
- The prior runtime was stopped and GPU returned to 4MiB used / 24121MiB free. Root was retained. No live key was lost.
- Existing production gate `3090-dev/gates/production/f2_restart_recovery.py` already implements real-process restart and extent membership, but its default 62K-token prompt/pressure is substantially larger than C6.4R's desired minimum; reuse only after reducing to the smallest bounded chain/fillers and retaining existing semantics. Its `gate_common.py` can capture exact tier details and snapshots.
- Backend `close()` always checkpoints current allocator (`extent_file_backend.py` around lines 2758–2785); with a nonempty valid index it should leave manifest entries after graceful stop. This is useful for direct before-shutdown and after-reopen proof.

## INFERRED

- Extent writes prove some cache keys reached L3, but do not identify the designated target key or prove that it stayed live. The lack of target matches could be a different token/hash window, incomplete WAL interpretation, or target eviction; available evidence does not distinguish these.
- The repeated eight-filler workload is not the desired minimum. Further pressure runs are unjustified until the target's runtime hash sequence and allocator state can be read correctly during the live process.

- 50GiB is the LRU free-space watermark, not the fixture's required allocation. Capacity is resolved and not a blocker.
- A target prefix ~254 tokens remains within GPU cache and is not automatically demoted; one short unrelated filler (~299 tokens) only showed device hit. Need minimal natural LRU eviction to move target to Host, then ensure write-back from Host to L3 without changing cache semantics.
- Runtime chat token IDs should be captured using the production ChatCompletionRequest's effective template arguments and compared against server `/generate` behavior; exact body alone is insufficient to certify template/hash identity.
- Use the existing frozen cache contract, but do not create an uncontrolled 57K×many pressure workload. Start with one target (actual prompt tokens obtainable from chat meta) and minimally sized fillers; inspect exact eviction/writeback acknowledgements after each bounded step.

## UNRESOLVED

- Runtime-generated target cache-key sequence, suffix-scoped live extent reference, and exact allocator liveness before shutdown.
- Why the current manifest parser produced no target evidence despite observed L3 writes; WAL replay must start from the actual checkpoint state and include every valid segment, or inspect the live backend allocator under its lock.
- Smallest natural pressure workload that preserves one exact target entry through graceful shutdown.
- Fresh-process replay with direct storage hit/read/restore evidence and response correctness.

## Current gate

```text
STORAGE_CAPACITY_GATE=PASS
EXACT_CHAT_TEMPLATE_IDS=RECONSTRUCTED_AND_MATCHED_FOR_SUCCESSFUL_REQUESTS
L3_EXTENT_WRITES=OBSERVED
LIVE_L3_KEY_BEFORE_SHUTDOWN=NOT_PROVEN
LIVE_L3_KEY_AFTER_REOPEN=NOT_TESTED
HICACHE_STORAGE_REUSE=NOT_TESTED
HICACHE_STORAGE_RESTORE=NOT_TESTED
HICACHE_CORRECTNESS=NOT_ACCEPTED
CANONICAL_TREE_CLEAN=YES (excluding this experiment's tracked evidence edits before commit)
```

No persistent-L3 defect is declared: no exact target key has been confirmed live before shutdown. The immediate blocker is sound runtime allocator/key evidence. Preserve the 005, 009–012 roots and evidence; never delete or overwrite C6.1. Before any additional workload, repair the external harness using the backend's actual live allocator state or correct checkpoint-plus-WAL replay, and reduce filler count. The current `run.py` must not be used as-is.
