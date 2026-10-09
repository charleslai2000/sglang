# external-scout report — SGLang HiCache upstream research (Phase-2 design reference)

- task-id: phase2-hicache-design | epoch: 1 | agent: external-scout
- date: 2026-08-30T01:54Z (UTC)

## 1. status

done

## 2. artifacts

Sources consulted (all curl-fetched, live at fetch time):
- https://raw.githubusercontent.com/sgl-project/sglang/main/docs/docs/advanced_features/hicache_design.mdx (200, 21,344 B) — HiCache design doc. Task-spec path `docs_new/docs/advanced_features/hicache_design.mdx` does NOT exist on main (raw fetch timed out twice; GitHub API contents → 404 "Not Found"). Correct location found via GitHub API directory listing of `docs/docs/advanced_features/`.
- https://api.github.com/repos/sgl-project/sglang/issues/32724 (200, 11,649 B) — issue body incl. root cause, measurements, proposed fix.
- https://api.github.com/repos/sgl-project/sglang/issues/32724/comments (200, "[]") — 0 comments.
- https://raw.githubusercontent.com/sgl-project/sglang/main/docs/docs/advanced_features/session_radix_cache.mdx (200, 2,855 B).
- https://api.github.com/repos/sgl-project/sglang/pulls/32725 (200) — the fix PR for #32724 (open, unmerged).
- https://api.github.com/repos/sgl-project/sglang/pulls/34568 (200) — related PP-prefill readiness PR (open, unmerged).
- https://api.github.com/repos/sgl-project/sglang/search/issues?q=repo:sgl-project/sglang+is:pr+"32724" (200) — located PR #32725.
- WebSearch (discovery only): located PR #9397/#8372/#23309/#31797, issue #30760, vLLM #41784; none quoted as originals.

Written files (all confirmed on disk):
- Deliverable: /home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/fetched-hicache-upstream.md
- Cache copy: /home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/cache/external/sglang/hicache-upstream.md
- This report: /home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-external-scout-e1.md
- Raw fetch files (work data): .memory/phase2-hicache-design/work/{hicache_design.mdx, issue-32724.json, issue-32724-comments.json, session_radix_cache.mdx, pr-32725.json, pr-34568.json, search-32724-prs.json, hicache-docs-site.html (Next.js error shell — discarded), adv-features-list*.json}

## 3. evidence

Each fetch used `curl -sL --max-time 30|45 --max-redirs 3` (one URL per command, no loops). Timestamps 2026-08-30T01:4xZ–01:5xZ.

| URL | Result | Filtered out |
|---|---|---|
| raw.githubusercontent.com/.../hicache_design.mdx (docs_new path) | 2× exit 28 (timeout) → channel switched, no further retry per rules | n/a |
| api.github.com/.../contents/docs_new/... | 404 Not Found → path obsolete on main | n/a |
| api.github.com/.../contents/docs/docs/advanced_features | 200 — file list; located hicache_design.mdx, hicache.mdx, session_radix_cache.mdx | other 40 doc names |
| raw.githubusercontent.com/.../docs/docs/advanced_features/hicache_design.mdx | 200, 21,344 B — full read (≤30 KB) | navigation, mermaid diagram, marketing text, per-backend repo links |
| api.github.com/repos/sgl-project/sglang/issues/32724 | 200 — full issue | GitHub API envelope fields (node_id, avatar_url, etc.) |
| api.github.com/.../issues/32724/comments | 200, "[]" | n/a |
| raw.githubusercontent.com/.../session_radix_cache.mdx | 200, 2,855 B — full read | n/a |
| api.github.com/.../pulls/32725 | 200 — full body | checklist boilerplate |
| api.github.com/.../pulls/34568 | 200 — full body | checklist boilerplate |
| api.github.com/search/issues?q=... | 200 — 1 hit (PR #32725) | n/a |
| docs.sglang.ai/advanced_features/hicache_design | 200 but Next.js `__next_error__` shell (noindex) — not content; discarded | n/a |

## 4. summary

### 4.1 HiCache official design (Q1)
- Tiers: L1 = GPU HBM (instance-private), L2 = host CPU DRAM (instance-private, node-local), L3 = storage backend (file/mooncake/hf3fs/nixl/aibrix/dynamic). L2 never shared across instances even on same node; cross-instance sharing only via L3.
- Write-back: three policies — write_through / write_through_selective / write_back. Doc verbatim: write_back = "Data is written back to the next level only when it is evicted from the upper level." → confirms eviction-time-only sinking for write_back (directionally consistent with observed behavior). write_through_selective = sink after hit-count threshold.
- Prefetch completion notification: no callback/event — scheduler polls via `check_prefetch_progress(rid)` (→ `can_terminate_prefetch()`), currently only during FCFS waiting-queue scan; completion predicate `completed_tokens == len(hash_value) * page_size`; operations tracked in `ongoing_prefetch`; scheduler safe point is `check_hicache_events()` after `drain_storage_control_queues()`. Prefetch trigger threshold default 256 tokens; policies best_effort / wait_complete / timeout (base 2 s, 0.1 s/1K tokens, max 30 s).
- Quota/capacity: no admission-control-class API documented. Capacity = `--hicache-ratio` (>1) / `--hicache-size` (GB per rank). In-flight budget `prefetch_tokens_occupied` pins host memory until finalization (per #32724). Concurrency knob `prefetch_io_workers` (default 1, PR #31797).

### 4.2 Issue #32724 (Q2)
- State: **open** (2026-07-29), 0 comments. Root cause: scheduler_ready confirmation coupled to FCFS waiting-queue position — IO-completed prefetches deep in queue stay unfinalized (host radix insertion / memory release / ongoing_prefetch cleanup pending) until scan reaches the rid; 4P1D: IO ~91 ms vs ~2.4 s lag; 4P2D: io_done→scheduler_ready p95 8.53 s / p99 22.16 s (56.2% of HiCache ready-time share); finalize_ms itself p50 3.36 ms (cheap).
- Fix PR exists: **#32725** (open, unmerged) — proactive finalization at `check_hicache_events()`: scan `ongoing_prefetch`, locally-ready ops (`completed_tokens == len(hash_value)*page_size` / terminated / timeout policy) get `check_prefetch_progress(req_id)`; req_id-sorted candidates + MIN all-reduce over ATTN TP/CP groups for cross-rank identical finalization; admission semantics unchanged. Reported: gap ~2.4 s → next check_hicache_events() round.
- Related: #28047 (same symptom), #21880 (prefetch lifecycle), vLLM #41784 (analogous), #30760 (TP all_reduce count-mismatch deadlock in can_terminate_prefetch), PR #34568 (PP-prefill readiness folded into bootstrap consensus; open).

### 4.3 Session radix cache (Q3)
- Mechanism: `SGLANG_ENABLE_UNIFIED_RADIX_TREE=1` + `--enable-session-radix-cache` (UnifiedRadixCache only); client passes `session_id` per request; on finish, reusable cache leaves auto-registered under session_id; `/close_session` removes references without freeing KV (returns to normal eviction).
- Eviction preference: unreferenced nodes first → referenced nodes with fewer session references → configured policy (LRU). Same on device and host.
- Soft vs hard pin: only soft. Verbatim: "Session references are soft protection, not memory pins. Referenced KV can still be evicted when reclaiming unreferenced KV is insufficient."
- Use for P2-4: directly reusable as fairness mechanism (eviction-preference fairness for active sessions) with caveats: (a) it is eviction-order preference only — no admission/rate/slot fairness, no capacity bound per session; (b) single top-level session_id per request; (c) needs UnifiedRadixCache + client cooperation; (d) no hard-pin primitive exists upstream.

### 4.4 P2-1 / P2-2 / P2-4 reusability
- P2-1 (prefetch completion notification): adopt upstream pattern from #32725 — safe-point proactive finalization + MIN all-reduce consensus; note PR unmerged (reference design, not shipped behavior). PP variant: #34568 approach (readiness folded into bootstrap consensus).
- P2-2 (write-back timing): `write_back` = eviction-time sinking per official doc — consistent. `write_through_selective` available as hot-data-only intermediate.
- P2-4 (fairness): session soft-reference eviction preference is directly reusable; hard-pin guarantee not available upstream (would need extension).

## 5. followups

1. PR #32725 is open/unmerged since 2026-07-29 — track merge status before citing as shipped behavior; location: https://github.com/sgl-project/sglang/pull/32725.
2. `hicache.mdx` and `hicache_best_practices.mdx` exist in docs/docs/advanced_features/ — recommended reads if Phase-2 needs operational/parameter guidance (quota tuning, backend selection); not fetched in this task.
3. `prefetch_tokens_occupied` budget semantics (how it is charged/released) only described indirectly in #32724 — if P2 needs exact budget math, source is `python/sglang/srt/mem_cache/hiradix_cache.py` (upstream code, fetchable via raw.githubusercontent.com).
4. Docs site root https://docs.sglang.ai/advanced_features/hicache_design returned a Next.js error shell at fetch time — official_docs link in metadata points there but the raw GitHub file is the authoritative copy; re-verify site if needed.

## 6. open_issues

- raw.githubusercontent.com timed out twice (exit 28) for the obsolete `docs_new/` path — channel issue for that specific URL; resolved via API-discovered correct path, so no open question remains on content.
- No evidence found of any admission-control (quota admission) mechanism in HiCache beyond capacity flags + prefetch budget — absence is documented but not exhaustively proven (code not reviewed in this task by design).
- Issue #32724 has no comments and its fix PR #32725 is unmerged — "fix exists" must be read as "fix proposed, not yet merged" (as of 2026-08-30).
