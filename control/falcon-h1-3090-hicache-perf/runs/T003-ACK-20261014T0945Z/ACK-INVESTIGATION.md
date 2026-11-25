# T003 ACK investigation — 2026-10-14

## Identity
- Repo `/home/ubuntu/workspaces/3rdparty/sglang-hicache`, branch `3090-24g-hicache`, HEAD `6331babe4e03781c65164e4d1e5f93b09ad58a94`.
- Runtime `/home/ubuntu/venvs/sglang-3090/bin/python`, Torch `2.13.0+cu129`, CUDA 12.9. `inspect.getfile()` verified UnifiedRadixCache, HybridCacheController and HiCacheController resolve to this checkout.
- RTX 3090 UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587`.

## Root cause of `operation_id=null`
Original null first appeared in `UnifiedRadixCache._execute_and_commit_kv_backup()` when it expected `(host_indices, operation_id)` but both Hybrid and base `write()` returned only Host indices. The compatibility fallback therefore set ID to `None`. This is **A: observability/correlation identity loss**, not evidence D2H failed. `CacheOperation` already held per-node operation/Host mappings, merge preserved them, and `HiCacheAck` carried these plus a CUDA finish event.

Added additive `write_with_operation()` APIs to Hybrid/base controllers, preserving legacy `write()` Tensor returns. Unified backup uses the additive API where available. Target node 26 then committed FULL+MAMBA with operation 0 and 1792 Host tokens. The raw ACK batch after `finish_event.synchronize()` independently confirmed node 26/op0, Host 1792 tokens, aggregate ACK 1792 tokens and 220,098,560 bytes. Thus the **CUDA completion/ACK batch did occur**, resolving A; no evidence indicates transfer failed (C).

## Critical observation and unresolved ownership result
The per-node ACK path reaches target node 26, exact op0, exact hash, pending-present/op/hash match, Host indices 1792. However the first node-scoped snapshot reported `component_residency={}`, `host_leaf_expected=false`, `host_leaf_eligible=false`, with no caught AttributeError/IndexError/KeyError/TypeError. That conflicts with the preceding commit's `kv_transfer=true`, `mamba_transfer=true`, and 1792 Host tokens. Do not proceed to eviction: Host ownership is not proven.

Likely inspection seam issue: `node.component_data` may be a property/sequence shape different from the diagnostic's `if component_type in node.component_data` membership assumption; this is only a hypothesis until verified. Importantly, the guard can suppress the more stringent `backup_host_ack` event whenever either mapped host indices or `_t38c_host_backup_pending` is missing, while the raw synchronized batch is still emitted. Need inspect `node.component_data` actual keys/values and adapter mappings in a fresh run, without weakening predicates.

Prior `detach_not_sealed` at trigger `build_registered` is pre-ACK with expected release count zero and is unrelated proof-wise. The producer manifest's source HEAD is `4f41f5bab...`; the actual service module paths are this checkout, so producer HEAD metadata must not be mistaken for module origin.

## Tests and current evidence
- `test_hicache_operation_identity.py` + `test_hicache_staged_write_back_dispatch.py`: **17 passed, 1 skipped**.
- `py_compile`, `git diff --check` pass.
- The target output was greedy `[10553]`; `hicache_request.v1` says 1920 prompt tokens all newly prefilled, L1/L2/L3=0 for the initial request.
- No eviction pressure, Host-only L2 H→D, L3 Storage readback, tier performance comparison, or gain accounting ran. All remain NOT_QUALIFIED / NOT_MEASURED.
- Latest server process was explicitly stopped; port 30130 has no listener; GPU is 1 MiB / 0%. No commit or push.
