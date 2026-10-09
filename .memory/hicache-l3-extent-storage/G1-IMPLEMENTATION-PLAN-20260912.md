# G1 implementation plan (orchestrator)

Authority: user ruling 2026-09-12 (D1=b process-crash / D3=a fail-closed / D7=a epoch+seq;
D2=a / D4=b / D6=a; NM-EXTENT-RESTART-REBUILD-01 ACCEPTED). Frozen design = bundle at
R4-docalign + the ruling write-back. Implementation must NOT change D1/D3/D7 semantics; if it
must, return to the authority gate.

Pre-change anchor: 77/77 extent unit tests pass, command in ledger:
  cd <repo>; source /mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh
  export PYTHONPATH="$PWD/python:$PYTHONPATH"
  CUDA_VISIBLE_DEVICES=0 python test/registered/unit/mem_cache/test_extent_file_backend_unit.py
(pytest is NOT installed; CUDA_VISIBLE_DEVICES must be non-empty.)

Target repo: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt @ HEAD 4f41f5ba
(dirty worktree is intentional; do NOT reset/clean). Build artifacts -> /mnt/data.

## Deliverables (one owner each; sequential to avoid write-set overlap)

### D-I1 — Metadata core (manifest + WAL + recovery) and allocator API split
Owner: coder. Scope: new metadata module(s) for the compact manifest/checkpoint and the
append-only WAL records (segment header, frames, CRC header[0..22), SET/BATCH_COMMIT/
GROUP_COMMIT/DROP_SLOT/CLEAR), recovery (torn active-tail ftruncate+fdatasync, contiguous
`[wal_floor, G_active]` enumeration with the pending-rotation promotion, D3 fail-closed), and
the `ExtentAllocator` split: pure `plan(pending_drops) -> (refs, passed, drop_events)` with the
unified generation form, `apply_drops(drop_events)` once, `commit_install(keys, refs)`
install-only. Unit tests for format/replay/generation arithmetic/torn tail/fail-closed.
Acceptance: the 77-test file stays green except the intentionally re-dispositioned
`test_crash_reopen_all_cold`; new unit tests pass.

### D-I2 — Backend integration (write path, checkpoint/rotation, hooks)
Owner: coder (continuation of D-I1 session). Scope: `ExtentFileBackend` constructor recovery;
write-path ordering D-01 (durable invalidation -> RAM drop -> clobber -> data-plan durable ->
install -> ACK); D1 hard invariant (extent data write completed to kernel/page-cache BEFORE WAL
`GROUP_COMMIT` durable and BEFORE ACK); `checkpoint()` exclusive `_write_gate` through step 6,
rotation, unlink strictly below `wal_floor`; `close()/clear()/detach/reset` hooks take the gate;
lock order `_write_gate -> _lock` (`_write_gate` is new; `self._lock` is at
extent_file_backend.py:348).
Acceptance: crash/reopen oracles NM-F-15..22 with a real SIGKILL subprocess (not a mock),
including: uncommitted/torn tail no resurrection; committed corruption fail-closed; stale
generation no resurrection.

### D-I3 — Durable group identity (D7)
Owner: coder (continuation). Scope: `namespace_epoch` (16B CSPRNG per writer/runtime
incarnation, persisted) + per-run monotonic `group_seq`; `group_id=(epoch,seq)`; `(0,0)`
ungrouped sentinel; all-zero epoch forbidden; KV and Mamba sidecar use the identical group_id;
backend sole `group_seq` owner via `open_group()/commit_group()` under the writer sequencer;
wire into hybrid_cache_controller.py and managers/cache_controller.py at the design anchors.
Acceptance: KV+Mamba group all-or-nothing across restart; new run uses a new epoch; no
cross-run seq collision (oracle NM-F-18/19).

### D-I4 — E2E acceptance oracle
Owner: tester (independent). Scope: run `TestHiCacheSpecExtentStorage`
(`test/registered/hicache/test_hicache_spec_file_storage.py`) with the real server and a real
process restart; expect RED before the fix, GREEN after; assert
`storage_cached_tokens >= input_token_len - 2*page_size` and `storage_backend == expected`
(`python/sglang/test/hicache_spec_storage_common.py:228-272`). Also confirm the `file` variant
stays green.
GPU: acquire `/mnt/data/gpu/3090.lock` via `exec 9>/mnt/data/gpu/3090.lock; flock -w <N> 9`;
hold only during the run; `CUDA_VISIBLE_DEVICES=GPU-2e3ed202-...`; host RAM >= ~22 GiB gate.

### D-I5 — Re-disposition `test_crash_reopen_all_cold`
Owner: coder (with D-I1). Scope: update the oracle at
`test/registered/unit/mem_cache/test_extent_file_backend_unit.py:461` to the warm-restart
semantics (NOT "all cold"); this is an intentional test-oracle change, recorded as such.

## Required acceptance points (user ruling; map to NM-F/NM-INV in the bundle)
1. pre-SIGKILL ACKed + GROUP_COMMIT durable -> present after restart;
2. uncommitted / torn active tail -> no resurrection;
3. committed corruption -> fail closed;
4. stale generation -> no resurrection;
5. KV + Mamba group -> all-or-nothing;
6. new process uses a new namespace epoch, no seq collision with old runs;
7. `TestHiCacheSpecExtentStorage` RED -> GREEN;
8. RAM index restart-rebuild byte/identity equivalent.

## Verification chain
coder (D-I1..I3, I5) -> orchestrator repin/verify diff -> independent tester (D-I4 + real
SIGKILL crash/reopen NM-F-15..22) -> reviewer -> orchestrator VERIFIED DONE. Then P3
soak/restart/fallback.

## Stop rule
No implementation while D-I1..D-I3 tests are red for a cause that changes D1/D3/D7; escalate to
the authority gate instead of silently deviating.
