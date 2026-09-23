# E001 results

Status: BLOCKED at live L3 fixture creation; no production semantics changed.

## OBSERVED

- Canonical branch `3090-24g-opt` at `c0277180c9758302f61e7f434dde5094793c8223` before the uncommitted experiment results update. Python imports from canonical worktree `python/sglang` via `/home/ubuntu/venvs/sglang-3090/bin/python`.
- User explicitly authorized removal of runtime HiCache data under `/data/l3`. All 37 immediate child runtime roots except `/data/l3/c61-qwen-20260922-220343` were confirmed unlocked and no SGLang/GPU process was active, then removed. No non-L3 data was changed. Free space increased 32→215 GiB. C6.1 is preserved at 39 GiB actual usage.
- `/mnt/data` is not a mountpoint in this namespace. Usable persistent storage is `/dev/sda1` mounted at `/`.
- Production cache contract is unchanged: Qwen3.5-9B W4A16, TP1, fp8_e4m3, hierarchical cache, Host mode `cache`, `write_back`, extent, `wait_complete`, hicache size 32, extent max 100Gi, min-free watermark 50Gi, 64MiB extent/64GiB sparse file.
- A corrected process ran at port 30004 with run ID `c64r-qwen-20260923-002`; startup confirmed exact storage path `/data/l3/c64r-qwen-20260923-002/hicache.data_qwen35-9b-w4a16_0_1` and geometry. `/health` returned HTTP 200, and `/v1/models` identified `qwen35-9b-w4a16`.
- An initial wrong-start attempt used `/tmp/hicache` defaults; it was stopped immediately, its isolated empty test root/request removed, and GPU returned to idle. It did not touch historical roots.
- Exact intended fixture request is `/data/l3/c64r-qwen-20260923-002-request.json`, SHA256 `3bc05ba7dd516616315cc083ce8f8f5d49b76e4b9a82e028f1f5da29680e574c`. It includes the 254-token neutral document and sampling/chat-template metadata.
- In first process, a shorter predecessor request was HTTP 200 but had only 26 runtime prefill tokens and did not create a storage entry. In the second process, the intended body was replayed but response content was merely an excerpt of the prompt (no `FIXTURE_OK`); it is **not** accepted as a correctness response. A long unique filler request `/data/l3/c64r-qwen-20260923-002-filler.json` (SHA256 `e6af7f84b453bd8b6c81599de26747c1992e6d56c5ed58d4a7795b3647c24e56`) was also HTTP 200 and produced device reuse, but host usage remained zero and no storage write event occurred.
- Across attempts, metrics show `hicache_host_used_tokens=0`, `host_hit=0`, `storage_hit=0`. No `extent_write`, `storage_persisted`, `backup_ack_drain`, or `batch_set_result` event exists. Extent manifest remains ~21KiB with `entries=0`; data file is sparse (36KiB actual); current WAL is header-only. Thus no live L3 entry was ever established.
- Second process restarted with the same root and contract and reopened successfully. Replaying the exact long body had `storage_hit=0`, as expected because the recovered manifest had zero entries; this is **not** evidence of a persistence defect.
- The server was SIGTERM-stopped; PID exited, port 30004 is free, and GPU is back to 4MiB used/24121MiB free. Root is retained. No confirmed live-key entry was lost.

## INFERRED

- `MIN_FREE_SPACE=50GiB` is an eviction watermark, not a fixture-size prerequisite; capacity is now ample and not blocking.
- A 254-token prefix is far below the active GPU/Host cache working capacity and naturally remains device-resident. A single filler below 300 tokens does not induce L3 demotion. Meeting the fixture requirement needs a bounded eviction-driving sequence or another contract-preserving way to ensure target cache blocks are written to L3; this is the current decisive issue.
- The response field `return_prompt_token_ids` was not exposed for chat in these responses, despite being requested. Do not claim the server-side token list was captured from response JSON. A production-native exact token/key capture route must be chosen before the decisive run; offline re-tokenization must match verified server behavior before it can be used.
- The template `launch.sh.tmpl` contains unresolved `@@TREE@@` placeholders and is not an executable frozen launcher. The successful runtime used canonical editable source, not a frozen/deployment identity gate.

## UNRESOLVED

- The smallest bounded pressure/filler sequence that populates one designated exact prefix into extent while keeping that target live.
- How to capture and associate actual server-template token IDs, native hash sequence, suffix/namespace, extent slot/generation, and manifest membership before shutdown without changing production behavior.
- Exact non-approximate replay response correctness and direct post-restart storage read/restore.

## Current gate

```text
STORAGE_CAPACITY_GATE=PASS
LIVE_L3_KEY_BEFORE_SHUTDOWN=NO
LIVE_L3_KEY_AFTER_REOPEN=NO (manifest has zero entries)
HICACHE_STORAGE_REUSE=NOT_TESTED
HICACHE_STORAGE_RESTORE=NOT_TESTED
HICACHE_CORRECTNESS=NOT_ACCEPTED (latest long replay did not return FIXTURE_OK)
CANONICAL_TREE_CLEAN=NO (this result update is pending commit)
```

No persistence defect is declared because no exact live key existed before shutdown. Keep `/data/l3/c61-qwen-20260922-220343` untouched. Do not perform another speculative prompt replay. Next action: inspect the production eviction/writeback eligibility threshold and usable existing gate tooling, then construct one bounded, observable run with exact identities and a response that actually passes the fixture assertion.
