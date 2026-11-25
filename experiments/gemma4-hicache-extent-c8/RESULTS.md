# Gemma4 HiCache / Extent investigation and run-storage disposition

## Scope and disposition

This note consolidates the durable findings from `/data/sglang-hicache/gemma4/runs` before deleting that runtime-output tree at the owner's direction. It is intentionally text-only: no model, cache payload, WAL, raw metric stream, request body, or binary artifact is copied into the repository. The source runs remain un-replayable after deletion unless rerun; the summarized observations below are not substitutes for raw artifacts.

**C-8 outcome: incomplete / no valid performance result.** Do not compare its partial request count or treat it as a completed benchmark.

## C-8 configuration and final attempt

- Branch/worktree: `3090-24g-hicache`; expected source head `c6907ccf6a1e2aa011e958471c0b5e79898dd00e`.
- Mode C, offered rate 8; Gemma4 E4B W4A16 with E5M2 KV; 40 clients × 20 rounds (800 requests), 1024 input / 256 output, Poisson seed 42, max-parallel 64; context 131,072, max-running 32, max-total 139,264; HiCache 8 GB; fresh 32 GiB Extent; write-through; CUDA Graph decode max batch 32.
- Attempts r2–r16 were incomplete. Earlier recorded counts: r2 470, r3 505, r4 188, r5 163, r6 187, r7/r8 232, r9 164, r10 163, r11 188, r12 198, r13 211, r14 131, r15 200. These counts are diagnostic only.
- Final attempt r16 stopped at 437/800. Its Extent log recorded `reclaim relocation of 261 live refs refused: no destination capacity outside victims [0]`, followed by `kv_set_failed` and the HiCache backup thread entering degraded state. The server stayed alive but the benchmark stopped making progress; the health monitor was corrected to avoid killing a live process after a transient health-check failure. A later actual server-process exit caused the client to end with `bench_exit=143`; this is not a successful run.
- No C-8 attempt completed all 800 requests. No C-8 performance result is established.

## Extent relocation finding

The r3 forensic review established that a fail-closed refusal must not be weakened: live references were refused relocation when no destination space existed outside the victim slots. WAL scanning did not reconstruct the exact operation-time allocator state; production replay exceeded its bounded attempt. Later r16 reproduced the general no-destination-capacity refusal, but not the exact r3 operation-time geometry. Preserve this distinction; do not claim the allocator root cause is fully reconstructed.

## Related verified work

- Async anchor identity validation at graft/ACK boundaries was committed as `6632449433` and `c6907ccf6a`; it permits anchor eviction without long-lived GPU pins and rejects stale anchors.
- Focused anchor/flush CPU tests passed 45; write-through tests passed 12 (11 skipped); the full Extent unit suite passed 119 (1 skipped). A nested flush reentrancy guard and regression test were also added locally but were not part of the above commits.
- Extent relocation test was strengthened to verify failed relocation leaves WAL offset unchanged and retained keys readable across slots.
- A guarded C-8 wrapper initially treated a single failed `/health` request as server exit. This was corrected so a transient health-check failure alone does not terminate the benchmark; only confirmed service-process exit does.

## Prior tier lifecycle evidence (separate from C-8)

- `20261120T-g1-live-tier-gap-r12` was a completed tier-lifecycle acceptance run under a different 36-request probe workload, not C-8. Its recorded result: wrapper/client exit 0, production idle sanity pass, L1/L2/L3/mixed restores with 256-token outputs, L3 physical reads and accepted-ready evidence; it explicitly did not prove branch-exclusive L3 or Frontier recovery.
- `20261121T-g1-branch-exclusive-r30` recorded 6/6 L3-qualified 256-token decodes on each of two branches, using an 8.5 GB Host diagnostic configuration rather than the authorized 8 GB acceptance setting. Its wrapper later exited 1 due to a phase-completeness gate mismatch; the branch evidence was recorded as passed. This is not C-8 evidence.
- `20261121T-g1-frontier-recovery-r29` did not reproduce `frontier_wait → frontier_wake → admission → Decode`; the RESULTS record states zero frontier-wait events. Its partial incidental decode evidence is not acceptance.

## Storage cleanup performed

At the time of cleanup, `/` had 484 GiB total, about 355 GiB used and 129 GiB available (74%). The `gemma4/runs` tree had been about 199 GiB after selective cleanup. The broader historical run tree contained model/cache experiments and large sparse Extent data payloads. The owner directed that durable repository records be comprehensive text files and that the remaining run outputs be deleted.

Before deleting the run tree, checks found no active `c8-r*` service, no listener on port 31401, and no open files under `/data/sglang-hicache/gemma4/runs`. C-8 r16 had stopped at 437/800. The explicit cleanup removed remaining runtime outputs under `/data/sglang-hicache/gemma4/runs`; it did not remove model assets, datasets, the Gemma4 compiled-kernel cache, unrelated `/data` experiments, or repository worktree changes.

Previously removed as regenerable payloads while preserving then-existing text/WAL evidence: failed r5b, r16, r29 C-8/HiCache Extent data, stopped smoke-test Extent data, and pip/uv download caches. Those raw run directories and their non-text evidence are subject to the owner's subsequent deletion of the entire `gemma4/runs` tree.

## Limits

This summary is based on run records inspected before cleanup and contemporaneous shell observations. Raw request logs, server logs, metrics, manifests, WALs and cache data are not retained here. The results above are stated only to the extent evidenced by those records; this document does not establish successful C-8 completion, exact r3 allocator reconstruction, or a valid C-8 throughput comparison.
