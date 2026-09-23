# E001 results

Status: ACTIVE — live L3 fixture design identified; no confirmed key population yet.

## OBSERVED

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

- 50GiB is the LRU free-space watermark, not the fixture's required allocation. Capacity is resolved and not a blocker.
- A target prefix ~254 tokens remains within GPU cache and is not automatically demoted; one short unrelated filler (~299 tokens) only showed device hit. Need minimal natural LRU eviction to move target to Host, then ensure write-back from Host to L3 without changing cache semantics.
- Runtime chat token IDs should be captured using the production ChatCompletionRequest's effective template arguments and compared against server `/generate` behavior; exact body alone is insufficient to certify template/hash identity.
- Use the existing frozen cache contract, but do not create an uncontrolled 57K×many pressure workload. Start with one target (actual prompt tokens obtainable from chat meta) and minimally sized fillers; inspect exact eviction/writeback acknowledgements after each bounded step.

## UNRESOLVED

- Exact server-side token sequence, native prefix hash sequence, storage key suffix, and live extent slot/generation for target.
- Smallest filler sequence that evicts the target from GPU and Host while successfully publishing it to L3.
- Fresh-process replay with `storage_hit>0`, storage cached tokens, read success, non-MISS_RECOMPUTE state, and correct `FIXTURE_OK` response.

## Current gate

```text
STORAGE_CAPACITY_GATE=PASS
LIVE_L3_KEY_BEFORE_SHUTDOWN=NO
LIVE_L3_KEY_AFTER_REOPEN=NO (previous manifest entries=0)
HICACHE_STORAGE_REUSE=NOT_TESTED
HICACHE_STORAGE_RESTORE=NOT_TESTED
HICACHE_CORRECTNESS=NOT_ACCEPTED (latest designated long fixture not yet successfully executed end-to-end)
CANONICAL_TREE_CLEAN=YES (except experiment procedure/result changes when uncommitted)
```

No persistent-L3 defect is declared: a confirmed live entry was never created. Next is a bounded experiment design using exact server tokenization and the existing F2 gate machinery with reduced workload, then execute only after the key/ref capture and correctness assertions are ready.
