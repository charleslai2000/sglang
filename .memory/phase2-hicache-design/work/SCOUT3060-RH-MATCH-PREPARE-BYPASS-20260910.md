# SCOUT3060-RH-MATCH-PREPARE-BYPASS-20260910

status: done
entry: ACCEPT
task_id: S3060-RH-MATCH-PREPARE-BYPASS-20260910
invocation_id: 20260910T-FRESH-SCOUT-RH-BYPASS-01
orchestration_epoch: E3060-RH-MATCH-EMIT-20260910-SCOUT
role: scout
capability_level: L3
workdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
memory_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design
memory_inputs:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/SCOUT3060-RH-TELEMETRY-AUDIT-20260910.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-MATCH-EMIT-PROBE-SHORT-20260910.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260910-RH-MATCH-EMIT.md
memory_report: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/SCOUT3060-RH-MATCH-PREPARE-BYPASS-20260910.md
parent_thread_id: 01a07bea-d668-75b2-8280-6a2cf0870c1e
observed_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
native_event_call: failed; MCP tool unavailable to this invocation
last_event_sent: none; communication path degraded

## Workspace evidence

- `pwd` returned `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`.
- `git rev-parse --show-toplevel` returned the same path.
- Branch: `3060-12g-qwen35-4b`.
- Local `HEAD`: `03a170ef4f35fe1d87d80a7b6f09e83261aef94e`; parent:
  `9213ee01d90ba3925e7fe928e80cc41354ee4fff`.
- No source files were modified. Existing untracked `.memory/`, `review/gates/`,
  and `storage/` entries were preserved.

## Call-path facts

1. `_ready_horizon_pass` is the sole local RH pass inspected. After its enable,
   controller, epoch, and refill gates, it loops over every `frontier_reqs`
   member and calls `_prepare_ready_horizon_match(req, self._rh_pass_seq)` at
   `python/sglang/srt/managers/scheduler.py:4665-4669`.
2. `_prepare_ready_horizon_match` emits `rh_match_prepare.v1` on every observed
   exit: candidate rejection (`skipped`/`ineligible`, lines 4494-4507), match
   exception (`failed`, lines 4511-4525), invalid anchors (`failed`, lines
   4530-4543), and successful preparation (`prepared`, lines 4545-4576).
3. The prepared-match result is placed in `prepared_matches`; views mark
   `staging_eligible` only when the request RID is present in that map and has
   restore potential (`_ready_horizon_views`, lines 4921-4953).
4. `ready_horizon.refill_plan` can place only those eligible views in
   `plan.to_issue` after low-watermark, candidate, headroom, and budget gates
   (`scheduler_components/ready_horizon.py:502-545`).
5. Each `plan.to_issue` item is passed to `_prefetch_kvcache` with the popped
   `prepared_match` at `scheduler.py:4760-4767`; the only local
   `rh_stage.v2` logger occurrence is immediately in that same loop at
   `scheduler.py:4833-4857`.
6. `_prefetch_kvcache_impl` independently validates a READY_HORIZON ticket at
   `scheduler.py:3204-3213`. If absent/stale, it emits `invalidated`, performs
   a fallback `init_next_round_input(..., cow_mamba=False)`, and emits either
   fallback failure or fallback prepared at `scheduler.py:3213-3280` before
   continuing toward issue.

## Bypass determination

The observed stage path cannot legally bypass match preparation in this local
source. A request can reach the local `rh_stage.v2` site only through
`plan.to_issue`; that list is built from views whose RID is in
`prepared_matches`, and the preparation loop precedes view construction.
Furthermore, the READY_HORIZON prefetch implementation has a second
invalid-ticket preparation/fallback branch. `rg` found no other local
`rh_stage.v2` or `ready_stage` emission site and no other local
`READY_HORIZON` call to `_prefetch_kvcache`.

Therefore the supplied runtime observation of `rh_stage.v2` with zero
`rh_match_prepare.v1` is not an expected semantic bypass of this source path.
It remains consistent with a different imported scheduler revision, logging
handler/filter or swallowed logger failure, or an incomplete capture window.
The emitter itself wraps its `logger.info` call in a broad `try/except` at
`scheduler.py:4442-4470`, so an emission-side exception is not surfaced to
the staging path.

## Minimal-fix symbol/branch locator (no fix applied)

If a fresh runtime identity/raw-log check confirms the running source matches
this tree and the event is still absent, the narrow telemetry investigation
should center on `Scheduler._emit_rh_match_prepare` at
`scheduler.py:4356-4470`, specifically its swallowed logging branch, rather
than adding a policy or staging bypass. The source control-flow branch that
must remain the oracle is `_ready_horizon_pass` at `4665-4669` followed by
the `plan.to_issue` loop at `4760-4767`. No implementation recommendation
or source change was made in this read-only dispatch.

## Artifacts and evidence

artifacts: this report only
evidence:
  - `python/sglang/srt/managers/scheduler.py:3117-3282, 4356-4470, 4490-4576, 4642-4670, 4760-4857, 4921-4953`
  - `python/sglang/srt/managers/scheduler_components/ready_horizon.py:502-545`
  - supplied `SCOUT3060-RH-TELEMETRY-AUDIT-20260910.md`
  - supplied `OPS3060-RH-MATCH-EMIT-PROBE-SHORT-20260910.md`
  - supplied `REVIEW-20260910-RH-MATCH-EMIT.md`
summary: local source has no legal RH stage path that skips preparation; stage issuance is downstream of the preparation map, with an additional fallback preparation branch in `_prefetch_kvcache_impl`. Runtime stage-without-prepare remains a source/runtime/log-capture discrepancy.
followups: run only a fresh bounded runtime identity/raw-stream check if authorized; compare imported scheduler path/hash and logger handlers, then correlate same RID/pass. Any code change or additional probe requires a fresh Task ID.
open_issues: live imported source identity, logger handler/filter behavior, and capture completeness remain unknown; the broad swallowed `logger.info` exception means source execution can continue without observable preparation telemetry; no claim is made about cache, hit, Mamba, allocator, or RH value fields.
