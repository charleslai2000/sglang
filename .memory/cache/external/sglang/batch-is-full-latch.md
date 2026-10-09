---
source: https://api.github.com/repos/sgl-project/sglang/issues/35537
discovery: task spec (issue number) -> GitHub API
library: sglang
topic: issue-35537-batch-is-full-latch-and-family-28530-22518-14872
fetched: 2026-08-30T02:20:00Z
http_status: 200
expires: 2026-09-06T02:20:00Z
official_docs: https://github.com/sgl-project/sglang/issues/35537
---

# SGLang upstream issue #35537 — `batch_is_full` latched during final chunked-prefill pass

## 1. Issue #35537 — status and content

- URL: https://github.com/sgl-project/sglang/issues/35537 (API: https://api.github.com/repos/sgl-project/sglang/issues/35537)
- Title: "`batch_is_full` latched during final chunked-prefill pass starves waiting queue until a running request finishes (self-healing variant of #28530 / #22518)"
- Author: atlantistony (NONE). State: **open**, 0 comments, no labels/assignee, created 2026-08-19T14:46Z, last updated 2026-08-19T14:46Z (no activity since).
- Environment: sglang v0.5.17 (`lmsysorg/sglang:latest` pulled 2026-08), Qwen3.8-27B-NVFP4, single GPU Docker WSL2. Flags: `--max-running-requests 4 --cuda-graph-max-bs 4 --chunked-prefill-size 2048 --max-prefill-tokens 16384`, NEXTN speculative (3 steps, topk 1, 4 draft tokens), `--kv-cache-dtype fp8_e4m3`, `--context-length 262144 --disable-prefill-cuda-graph`.
- Symptom: 4 concurrent ~3100-token cold prompts (staggered) -> 3 run, 4th stays queued until one of the 3 finishes decoding entirely. Production-like longer-prompt run: queued request waited **~4.5 minutes** while server otherwise idle-capable. Resource headroom at starvation: KV pool 382,958 tokens with <=4% used; mamba state pool 16/24 slots. **Self-healing**: admission resumes as soon as a running request completes (no restart, unlike #28530).

## 2. Root-cause mechanism (verbatim from issue body, v0.5.17 `python/sglang/srt/managers/scheduler.py`)

1. During the pass where the last chunked-prefill continuation finishes, the in-flight `chunked_req` occupies the last allocatable slot, so one admission path sets the flag:
   `len(adder.can_run_list) >= self.get_num_allocatable_reqs(running_bs)` (trace L3204) — other set sites L3138 / L3209 / L3246.
2. Batch transitions to steady-state decode. On the decode path `batch_is_full` is only reset when the batch shrinks / becomes empty / retracts — none happen while all requests are mid-decode.
3. Every subsequent scheduler pass hits the early return:
   ```python
   if (running_batch.batch_is_full or len(self.waiting_queue) == 0) and self.chunked_req is None:
   ```
   so the waiting queue is starved until a running request finishes and the batch rebuild path clears the flag.
- Author diffed v0.5.17 against main (fetched 2026-08-19): "all 14 read/write sites of `batch_is_full` are equivalent — the bug is still present on main."
- Proposed fix (issue body): unconditional `running_batch.batch_is_full = False` immediately before the early-return check, each pass. Rationale: "batch_is_full is a per-pass admission hint, but it is persisted on the long-lived ScheduleBatch object, so a stale value survives across scheduler passes. The flag is re-derived inside the pass anyway ... and PrefillAdder budget gates enforce all real resource limits, so an unconditional reset cannot over-admit."
- Verification (author): before — 3 running + 1 queued, 4th delayed ~4s (minimal repro) / ~4.5 min (long prompts); after — all 4 admitted immediately, 8.3–9.2s uniform completion, zero decode-phase queue events.

## 3. Fix PR #35609 (cross-referenced from #35537 timeline, 2026-08-20T02:16Z)

- URL: https://github.com/sgl-project/sglang/pull/35609 — title "Fix stale batch fullness after chunked prefill". **open, unmerged** (created 2026-08-20, 0 comments).
- Body: "Fixes #35537. `batch_is_full` could remain set after the final chunked-prefill pass. The next scheduler pass returned before recalculating available request slots, which left a waiting request queued until a running request finished." Modifications: "Reset `batch_is_full` at the start of each prefill admission pass. Add a regression test that starts with the stale post-chunk state and verifies that the waiting request reaches admission." Author thanks @atlantistony for report+trace. Tested CPU-side (A40s, CUDA hidden); full NVFP4 repro not run (sm_86).

## 4. Sibling issue #35642 (cross-referenced 2026-08-20T05:09Z)

- URL: https://github.com/sgl-project/sglang/issues/35642 — "[Bug] Scheduler scans waiting queue after resumed chunk exhausts chunk budget". **open**, 0 comments.
- Content: when a resumed chunked request's `add_chunked_req()` consumes the remaining `rem_chunk_tokens`, the scheduler still enters the waiting-queue loop without re-checking the budget; waiting requests do prefix-cache matching (host-cache hit can call `init_load_back()`) and are rejected only later when `add_one_req()` computes non-positive truncation length. Expected: stop scanning once chunk budget exhausted. (Same scheduler region as #35537.)

## 5. Variant family — #28530 / #22518 / #14872 (titles + states + essentials)

| Issue | Title | State | Notes |
|---|---|---|---|
| #28530 | "[Bug] Scheduler NO_TOKEN admission rejection causes deadlock when page_size > 1 and context_len > max_total_num_tokens" | **closed 2026-06-18** (fixed) | Permanent deadlock variant: NO_TOKEN budget rejection (demand == supply, `>=` check) sets `running_batch.batch_is_full = True` (no-HiCache path); even AbortReq doesn't reset it; server frozen until restart. Log signature: endless `total_tokens(4096) = req.extend_input_len(10) + max_new(4084) + self.page_size(2) rem_total_tokens: 4096` loop (schedule_policy.py:809). Fixed by **PR #25126** (merged 2026-05-13, "Fix scheduler admission for near-full KV requests") — clamps `max_new_tokens <= max_total_num_tokens - ceil_page(input_len) - page_size - 1` so near-full requests never enter the waiting queue. |
| #22518 | "[Bug] SGLang embedding server deadlocks after first full batch" | closed 2026-06-10 (stale-bot, inactivity; **no fix PR referenced**) | Prefill-only models (embeddings), overlap scheduler: stale `batch_is_full` after first full batch; set when `len(can_run_list) >= get_num_allocatable_reqs(running_bs)` (`0 >= 2-2 = 0`); cancel does not recover. Maintainer root-cause analysis confirms same sticky-flag defect. |
| #14872 | "[Bug] AddReqResult.NO_TOKEN sets batch_is_full = True too late to trigger preemption" | closed 2026-02-15 (stale-bot, inactive) | v0.5.6.post1: `NO_TOKEN` set site runs **after** the preemption branch, so preemption never triggers; claims flag is reset at start of each `get_new_batch_prefill()` run (older semantics — differs from #35537's sticky-across-passes semantics; version evolution between v0.5.6 and v0.5.17 not established by these fetches). |

## 6. Sources

- https://github.com/sgl-project/sglang/issues/35537 (API + /comments [empty])
- https://github.com/sgl-project/sglang/pull/35609 (API)
- https://github.com/sgl-project/sglang/issues/35642 (API)
- https://github.com/sgl-project/sglang/issues/28530 (API + /comments: "fixed in #25126")
- https://github.com/sgl-project/sglang/pull/25126 (API; merged_at 2026-05-13T22:30:49Z)
- https://github.com/sgl-project/sglang/issues/22518 (API + /comments)
- https://github.com/sgl-project/sglang/issues/14872 (API)
- #35537 timeline (API): 2 events only — cross-refs to #35609 (PR) and #35642 (issue).

Not included: full bodies of #22518 repro details beyond the mechanism; nvidia-smi environment dump from #28530; PR #25126's 3 comments (details beyond merged status not needed).
