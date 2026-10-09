# external-scout report — upstream #35537 (batch_is_full latch) research

## 1. status

done

## 2. artifacts

Sources consulted (all curl-fetched, GitHub API, HTTP 200):

- https://api.github.com/repos/sgl-project/sglang/issues/35537 (+ /comments [empty], + /timeline [2 cross-refs])
- https://api.github.com/repos/sgl-project/sglang/pulls/35609 — fix PR for #35537 (open)
- https://api.github.com/repos/sgl-project/sglang/issues/35642 — sibling bug (open)
- https://api.github.com/repos/sgl-project/sglang/issues/28530 (+ /comments: "fixed in #25126")
- https://api.github.com/repos/sgl-project/sglang/pulls/25126 — merged fix PR for #28530
- https://api.github.com/repos/sgl-project/sglang/issues/22518 (+ /comments)
- https://api.github.com/repos/sgl-project/sglang/issues/14872
- Cache reuse: .memory/cache/external/sglang/hicache-upstream.md (fresh, today) — #32724/#32725 context, no #35537 coverage

Written files (all exist on disk):

1. Deliverable: /home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/fetched-issue35537-batch-is-full-latch.md
2. Cache copy: /home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/cache/external/sglang/batch-is-full-latch.md
3. This report: /home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-external-scout-e2.md

## 3. evidence

| URL | Fetched (UTC) | Command | Filtered out |
|---|---|---|---|
| api.github.com/repos/sgl-project/sglang/issues/35537 | 2026-08-30T02:1x | `curl -sL --max-time 30 --max-redirs 3 -o /tmp/eg35537/issue35537.json` | user/label boilerplate JSON fields |
| .../issues/35537/comments | same | same | n/a (empty array) |
| .../issues/35537/timeline | same | `curl -sL -H 'Accept: application/vnd.github+json'` | full event objects; kept 2 cross-ref numbers |
| .../issues/28530 + /comments | same | same pattern | nvidia-smi env dump; repro script details |
| .../pulls/25126 | same | same | 3 PR comments not fetched (merged status sufficient) |
| .../issues/22518 + /comments | same | same | full repro prose beyond mechanism |
| .../issues/14872 | same | same | boilerplate |

All payloads ≤30KB, read fully per regex-safety rules; no cross-span regex used. Scratch copies in /tmp/eg35537/.

## 4. summary

### 4.1 Issue #35537 — mechanism (Q1)

- Open (0 comments, no labels), created 2026-08-19 by atlantistony; verified against v0.5.17; author states all 14 `batch_is_full` read/write sites are identical on main as of 2026-08-19 — **bug still present on main**.
- Semantics: `batch_is_full` is a sticky flag on the long-lived `ScheduleBatch` (`running_batch`). Set inside `_get_new_batch_prefill_raw()` when `len(adder.can_run_list) >= self.get_num_allocatable_reqs(running_bs)` (trace L3204; other set sites L3138/L3209/L3246). Cleared only on batch shrink/empty/retract (rebuild path). Decode path never re-evaluates it.
- Latch path: during the pass where the *final chunked-prefill continuation* finishes, the in-flight `chunked_req` occupies the last allocatable slot -> flag set True -> batch goes to steady-state decode -> every later pass early-returns on `if (running_batch.batch_is_full or len(self.waiting_queue) == 0) and self.chunked_req is None` -> waiting queue starved until a running request finishes and the rebuild clears the flag.
- Starvation conditions (self-healing not effective): all running requests mid-decode (no shrink/retract) AND `chunked_req is None` AND waiting queue non-empty. Self-healing works only via completion-triggered rebuild; with long decodes the stall is minutes (reported ~4.5 min).
- Issue's proposed fix: unconditional `running_batch.batch_is_full = False` each pass before the early return (flag is re-derived in-pass; `PrefillAdder` budget gates still enforce real limits).

### 4.2 Fix status (Q4)

- **#35537: no merged fix exists.** Fix PR **#35609** "Fix stale batch fullness after chunked prefill" (2026-08-20) — **open, unmerged**, 0 comments; same approach (reset at start of each prefill admission pass + regression test). No released sglang version contains it.
- Sibling **#35642** (2026-08-20, open): resumed chunk exhausts `rem_chunk_tokens` but scheduler still scans waiting queue (wasteful cache matching, late rejection) — same scheduler region.
- Family: #28530 **fixed** by PR #25126 (merged 2026-05-13; page-aligned `max_new_tokens` clamp) — merged before 2026-07, so a pre-2026-07 base likely contains it (verify locally). #22518 closed 2026-06-10 by stale-bot, no fix PR. #14872 closed 2026-02-15 by stale-bot, no fix PR.
- Our 3090-24g-hicache branch (pre-2026-07 base): cannot contain the #35537 fix because **none exists upstream**; #35609 (open) is the cherry-pick candidate once merged; the issue body itself contains the equivalent one-line patch.

### 4.3 Log signature (Q3)

- No dedicated log line for `batch_is_full` in any fetched issue — not directly observable upstream.
- Observable signatures: (a) admission timing — waiting requests admitted only after another request *completes decode* ("decode-phase queue events"); (b) family signature from #28530: endless loop of `total_tokens(4096) = req.extend_input_len(10) + max_new(4084) + self.page_size(2) rem_total_tokens: 4096` (schedule_policy.py:809) = NO_TOKEN admission rejection looping.

### 4.4 Match with our scenario (Q2)

- Mechanism family (sticky `batch_is_full`, self-healing only on completion): **match 高**. "96 serial requests, width 1, max-running-requests=8" is exactly the shape the latch produces (once latched, no new admission until a completion; with serial submission the first completion unblocks exactly one slot -> width pinned near 1).
- Trigger path: **中**. The issue's latch is the final chunked-prefill pass; it explains "宽 1 而 max=8" only if `get_num_allocatable_reqs()` was resource-limited to ~1 (KV token budget — our 32762-token cap with long prompts does that) rather than request-slot-limited. The 32762 rejection lines are a *different admission-rejection* event than the issue's L3204 trace; the NO_TOKEN-family set sites (#14872/#28530: NO_TOKEN -> batch_is_full=True) are the same sticky flag with a different set site and also fit. Which set site fired in our run cannot be determined from public material — needs local scheduler.py inspection (followup).
- Caveat: #14872 (v0.5.6, Dec 2025) claims the flag WAS reset at the start of each `get_new_batch_prefill()` run in that era; #35537 (v0.5.17, Aug 2026) asserts sticky-across-passes. Version evolution between these is unestablished by fetched material — whether our pre-2026-07 branch has per-pass-reset semantics (=> #35537 mechanism does NOT apply; NO_TOKEN set-site family is the explanation) or sticky semantics (=> #35537 applies) must be checked in local source. This is the key open item.

### 4.5 Relation to #32724 (Q5)

- **Independent mechanisms, same victim and same code region.** #32724: HiCache prefetch finalization (`check_prefetch_progress(rid)`) is coupled to the FCFS waiting-queue scan; saturated prefill budget stops the scan early -> IO-completed prefetches stay unfinalized for seconds (open; fix PR #32725 open/unmerged). #35537: sticky flag early-return skips the waiting queue entirely.
- Stacking effect (analysis derived from the two fetched texts, stated in neither): with HiCache enabled, the #35537 early return also *freezes prefetch finalization* for all queued rids (the scan never reaches them) — so the two compound: starvation plus prolonged host-memory / `prefetch_tokens_occupied` pinning, which additionally throttles later prefetches (#32724's secondary effect). Both issues remain open upstream; neither fix is merged.
- Also related on the same scan path (from cached research): #30760 (TP deadlock from mismatched `all_reduce` counts in `can_terminate_prefetch`) and PR #34568 (PP prefetch-readiness bootstrap).

## 5. followups

1. Local scheduler.py check (internal, out of scout scope): in our branch, is `batch_is_full` reset per-pass or only on shrink/empty/retract? Determines whether the #35537 mechanism or the #14872/#28530 NO_TOKEN set-site family explains width-1. Location: `python/sglang/srt/managers/scheduler.py` `_get_new_batch_prefill_raw` / `get_new_batch_prefill`.
2. Map our "32762 超限拒绝" log line to a rejection type (NO_TOKEN vs ADMISSION_REJECT vs token-budget) and to a `batch_is_full` set site — same file; the 24 rejection lines are the likely latch moment.
3. Verify our branch contains #25126 (init_req_max_new_tokens page-aligned clamp, merged 2026-05-13) — if absent, near-full-KV requests can enter the queue unschedulable (the #28530 permanent-deadlock variant).
4. Track PR #35609 (open since 2026-08-20): once merged, cherry-pick candidate; the issue body's one-line reset is the same fix and is safe to apply locally ahead of merge (author-verified; PrefillAdder gates prevent over-admission).
5. Check #35642 behavior in our branch (chunk-budget exhausted but waiting-queue scan continues) — same scheduler loop, likely also unfixed.
6. If our branch is pre-#32725 (safe point `check_hicache_events()` proactive finalization absent), the #35537 early return additionally suppresses prefetch finalization — consider fixing both together.

## 6. open_issues

- No merged upstream fix for #35537; PR #35609 open/unmerged — cannot cite a released version that fixes it.
- Version-evolution conflict: #14872 (2025-12) asserts reset-at-start-of-run semantics; #35537 (2026-08) asserts sticky semantics; neither issue's timeline pins the change. Resolved only by local source inspection (followup 1).
- #22518 closed by stale-bot with no fix PR — "fixed" only in the sense of auto-closed; its mechanism may still exist in prefill-only setups.
- Whether our 32762 rejections are the same guard as the issue's L3204 or the NO_TOKEN path is unverifiable from public sources.
