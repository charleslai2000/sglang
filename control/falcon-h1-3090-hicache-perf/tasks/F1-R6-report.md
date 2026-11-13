# F1-R6 — GPU tracing and L2/L3 acceptance status

Status: **BLOCKED at target-specific backup-operation attribution; lifecycle NOT PASS**. RTX 3090 was explicitly authorized for this run. No pressure, L2 restore, L3 test, or performance benchmark was attempted after the evidence gate failed.

## Execution evidence
- Model args in retained `runs/R6-20261009T1200Z/server.log`: checkpoint `/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4`, revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`, TP=1; R6 fixed 1,920-token prompt SHA256 `987fd70caf2045c84b952b73b36e6b1086b089972eee730daf15b6225e071999`, checkpoint grid 256.
- Service initialized the UnifiedRadixCache, `hybrid_ssm=True`, HiCache attached, and completed its startup request. Target A and repeat each completed one generated token with greedy token ID **10553**. Repeat reported 1,792 cached tokens, all from device (`host=0`). This is only an L1 control, not restore evidence.
- `t38c-probe.jsonl` has a successful target `build_complete`: session `falcon-r6-target-radix-session-9001`, generation 1, build RID `6922aac9e7da4714bfd179c79be3ebfc`, node 26, final hash `721e82b98783b54519c46e4be90f5363be52d20bcbba82a614d022a61eafe09c`. The matching prompt was 1,920 tokens; A/repeat token IDs agree. Runtime therefore confirms finished insert and target prefix identity.
- Same file reports `backup_host_commit` for node 26/hash above, `kv_transfer=true`, `mamba_transfer=true`, 1,792 KV host tokens. This event does **not** carry trace context, operation ID, ACK ID, or completion event. The backup commit is emitted immediately after `tree_core.commit_backup`; its implementation is invoked in `_execute_and_commit_kv_backup`, which copies D→H before committing node host references. A separate `HiCacheAck` in CacheController is grouped by `node_ids` and finish event, not linked in the durable row. Although build and commit node/hash match, the artifact cannot prove exact asynchronous operation/ACK-to-target association under the requested evidence standard. Therefore no pressure was permitted.
- After the guarded driver stopped, `/close_session` returned 200. Then service was stopped; GPU returned to 1 MiB/0%, no listener at 30127. Marker and probe symlink were removed; R6 trace data remains. No sibling worktree was changed.

## Driver defect
The prepared driver first required target build event context under `trace_context.session_id`, but the current v3 event places `session_id` at top level; source shows the build did emit. I corrected the predicate to match that schema, and added `return_token_ids=true` because `/generate` places IDs under `choices[].token_ids`, not top-level `output_ids`. This corrected driver has not yet been rerun; the first actual run's raw requests already contain the matching IDs.

## Gates
- GPU target finished build/hash: **PASS**.
- L1 repeat control with same greedy output: **PASS** (not an L2/L3 pass).
- Target FULL+MAMBA host commit observed: **PASS as a node/hash-bound synchronous commit record**; exact target async operation/ACK attribution: **BLOCKED / NOT_PROVEN**.
- Session close endpoint: **PASS response**; actual lock/reference counts and residency after close: **NOT_PROVEN**.
- Host retention, device eviction, Host source match, H→D, restore output: **NOT_RUN**.
- Extent write/read/prefetch/restore/sidecar/fault lifecycle: **NOT_RUN**.
- Three-configuration concurrency performance and profilers: **NOT_RUN**.

## Next concrete source-level fix
Existing `CacheOperation` and `HiCacheAck` carry node lists and completion events but no stable operation identity in the radix-side write-through queue. Add marker-gated tracing only at the actual D→H submit/ACK seam: preserve an operation ID with the node IDs and hash context from `CacheOperation` through `HiCacheAck`, emit submit and finish events after `finish_event.synchronize()`, then require that identity on target commit evidence. This is observability-only; do not change transfer, promotion, lock, or cache policy semantics. Add narrow CPU/unit seam coverage, then rerun R6 on GPU and proceed only after the exact operation closes with FULL+MAMBA and residency barrier confirms host state. This is a localized issue in the current checkout, not an absent external dependency.
