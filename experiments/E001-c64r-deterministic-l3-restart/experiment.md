# E001 — C6.4R deterministic L3 fixture and restart restore

Status: CLOSED — final consolidation ended the HiCache acceptance thread without establishing a persistent-L3 defect

## Question

Can the canonical Qwen3.5 production HiCache configuration write one exact, reproducible prefix into a fresh extent root, keep that exact live entry in L3 through graceful shutdown, reopen it in a fresh process, and restore it on replay without changing retention, eviction, key, namespace, or restore semantics?

## Hypothesis

If an exact request is preserved and the matching live allocator entry is confirmed in the extent manifest immediately before shutdown, a fresh process using the same model, storage namespace, geometry, and cache contract should find the same key and perform an L3 read/restore. A miss after confirmed live-key recovery would establish a persistence-path defect and localize the first failed link.

## Object and identity

- Canonical source worktree: `/home/ubuntu/workspaces/3rdparty/sglang`
- Branch/starting authority: `3090-24g-opt` / `dde7bb697b6743c690d580d37568217b769a30e3`
- Model: `/data/models/qwen35-9b-w4a16`
- Historical C6.1 root: `/data/l3/c61-qwen-20260922-220343` (preserve, do not use)
- New isolated root for run 014: `/data/l3/c64r-qwen-20260923-014` (preserve as failed-run evidence; never overwrite)
- Runtime: canonical Python `/home/ubuntu/venvs/sglang-3090/bin/python -m sglang.launch_server`
- Production cache flags: `--enable-hierarchical-cache --hicache-host-memory-mode cache --hicache-write-policy write_back --hicache-storage-backend extent --hicache-storage-prefetch-policy wait_complete --hicache-size 32 --kv-cache-dtype fp8_e4m3 --tp-size 1`; retain the C5 frozen Qwen model/runtime flags and `/data/l3` max-size/min-free contract.
- Isolated endpoint: 127.0.0.1:30004 unless occupied; select and record another free local port rather than interrupting unrelated services.
- Use `/v1/chat/completions` with `return_prompt_token_ids=true`, `return_meta_info=true`, and `return_cached_tokens_details=true`; verify the returned `choices[0].prompt_token_ids` field. The later run-012 did return exact IDs, correcting earlier runs where they were absent.

## Controlled inputs

- One designated HTTP completion request body, saved byte-for-byte before sending and replayed byte-for-byte after restart.
- Same tokenizer/model revision, template, model path, source code, command-line flags, environment namespace, storage root, TP rank, extent geometry, and runtime key scheme across both processes.
- No concurrent workload against the fixture root.
- Only the minimum bounded request/population necessary to make the designated exact key durable. Do not repeat C6.1 pressure workload.
- GPU and Host pools must be empty in the new process before replay (fresh process is required; prove metrics/state).

## Procedure

1. Before launch, verify the selected unique root does not exist, historical C6.1 root remains untouched, endpoint is free, no server owns the selected GPU, and sufficient disk space exists. Do not delete/overwrite any existing root.
2. Start canonical Qwen runtime with the frozen production HiCache flags and isolated root. Record full argv, relevant environment, source HEAD, model identity, server info, storage geometry, and startup log.
3. Save exact HTTP JSON body and deliver the designated request. Preserve bytes and SHA256 plus returned server prompt IDs.
4. Use `ExtentFileBackend.inspect_storage_key` on exact keys returned by the same runtime controller/backend. The API checks generation validity under the backend index lock without touching recency or removing stale index records. Require all queried target page keys live; after normal close, use a fresh process opening the same root through canonical backend recovery and query those exact keys again.
5. Ensure all writes/acks are durable, verify exact key remains live immediately before shutdown, then stop normally and record exit status and final metadata/WAL state.
6. Start a new process using the identical root and contract. Prove startup recovered the exact entry/generation and that GPU/Host pools are empty before the replay request.
7. Replay the saved exact request bytes. Collect direct runtime evidence for storage_hit, storage cached tokens, prefetch/read completion, restore state, output correctness, and absence of errors. Do not infer reuse from latency.
8. If the exact key was confirmed live pre-shutdown and after reopen but query returns MISS, identify first mismatch through namespace/key bytes -> recovered index/reference -> lookup -> pread/read -> KV restore. Only then consider a minimal canonical source fix. Otherwise stop at the actual earlier failed precondition.
9. Stop the server normally; verify GPU memory, root identity/integrity, and canonical worktree status. Preserve all generated artifacts under the experiment evidence/artifact store, not source tree.

## Measurements and acceptance

Required artifacts: exact request JSON bytes/hash; server-side templated token sequence/hash; exact cache key bytes/hash; suffix/namespace identity; pre-shutdown extent ref and manifest membership; post-reopen allocator/ref membership; both process logs and metrics; HTTP response correctness; shutdown/restart identities; root file identity/hash/geometry; clean canonical `git status` and final commit SHA.

Pass only if all are directly observed:

```text
RUNTIME_OBSERVER=PASS (run 014)
EXACT_TARGET_KEY_CAPTURED=YES
LIVE_L3_KEY_BEFORE_SHUTDOWN=NO
LIVE_L3_KEY_AFTER_REOPEN=NO
HICACHE_STORAGE_REUSE=NOT_TESTED
HICACHE_STORAGE_RESTORE=NOT_TESTED
PERSISTENT_L3_ACROSS_RESTART=NOT_TESTED
HICACHE_CORRECTNESS=NOT_TESTED
```

The run stopped at the required pre-shutdown liveness gate. The target page key was absent in the live serving backend and remained absent after graceful writer exit plus fresh canonical recovery. This is not evidence of a persistent-L3 recovery defect.
