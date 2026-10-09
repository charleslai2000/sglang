ENTRY: ACCEPT

# SCOUT3060-RH-TELEMETRY-AUDIT-20260910

status: done
task_id: T3060-RH-TELEMETRY-AUDIT-20260910
orchestration_epoch: 20260910-rh-ab60
role: scout
target_revision: 9213ee01d90ba3925e7fe928e80cc41354ee4fff
authorized_inputs:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
  - TEST3060-RH-FINAL-ON-9213-20260910.md

## Observed facts

- The supplied final ON report says `rh_match_prepare.v1` was absent for all
  five RIDs, while `rh_preadmission.v1` was present for all five and
  `rh_stage.v2` was emitted for `y` and `q` (report lines 110-121).
- The same report records accepted `rh_ready_host.v1` and `rh_admission.v2`
  for both eligible requests, with an observed 2/2 host-ready-before-admission
  rate (lines 128-140). It explicitly treats missing internal evidence as
  not-computable, not zero (lines 169-185).
- At commit 9213, `_ready_horizon_pass` returns early only when RH is disabled,
  the cache controller is absent, or the causal/event refill gate declines
  the pass (`scheduler.py:4654-4674`). Once a refill proceeds, it iterates
  every `frontier_reqs` entry and calls `_prepare_ready_horizon_match`
  (`scheduler.py:4677-4682`).
- `_prepare_ready_horizon_match` calls `_emit_rh_match_prepare` on every
  observed exit: candidate rejection (`skipped`/`ineligible`), match
  exception (`failed`/`match_prepare_failed`), invalid anchors
  (`failed`/`anchor_unknown`), and successful preparation
  (`prepared`/`current_match`) (`scheduler.py:4502-4555` and the successful
  emission immediately after the prepared record at `scheduler.py:4578-4590`).
- `_emit_rh_match_prepare` logs the exact `evt=rh_match_prepare
  schema=rh_match_prepare.v1` record at INFO/P3 (`scheduler.py:4356-4369,
  4440-4453`). Its logging call is inside a broad `try/except`, so a logging
  failure can be swallowed (`scheduler.py:4442-4455` onward).
- A view is staging-eligible only when its RID is present in
  `prepared_matches` and restore potential is true (`scheduler.py:4933-4965`).
  `ReadyHorizonPolicy.refill_plan` can put such a view in `to_issue` when the
  low-watermark, candidate, headroom, and budget gates pass
  (`scheduler_components/ready_horizon.py:502-535`).
- Each `plan.to_issue` item is passed to `_prefetch_kvcache` and then emits
  `rh_stage.v2` (`scheduler.py:4772-4779, 4845-4865`). If the preparation
  ticket is invalidated in `_prefetch_kvcache`, that path itself emits an
  `rh_match_prepare.v1` `invalidated` record before fallback rematch; fallback
  failure/success also emits records (`scheduler.py:3214-3271`).

## Inference and classification

Under the accepted source and a complete INFO/P3 log stream, an observed
`rh_stage.v2` issue implies that the same RH refill pass had a prepared match,
and therefore should already have emitted at least one `rh_match_prepare.v1`
record for that RID. This is a source-level control-flow invariant, not a claim
that any absent cache or hit field was zero.

Therefore the absence in the final live trace is not an expected semantic path
where RH staging deliberately omits match preparation. It is evidence of a
telemetry/collection gap or runtime mismatch, with the following unresolved
possibilities:

1. The deployed process imported a different scheduler source than the
   hash-checked file, despite the file manifest matching 9213.
2. The log capture/filter/handler dropped the preparation records. The source
   uses the same logger and P3/INFO level as the observed stage records, and
   the preparation logger suppresses exceptions from the logging call.
3. The live trace began after preparation records or otherwise did not include
   the complete relevant stream.

The source inspection alone cannot select among these runtime/collection
causes. It does establish that `rh_preadmission.v1` alone is not the emission
condition: preparation is emitted during an eligible refill pass before plan
construction, including for rejected or failed preparation outcomes. A
non-empty `rh_stage.v2` path is the strongest concrete condition in the
supplied trace and should have a preceding preparation record.

## Recommended next bounded runtime check

For a fresh Task ID, run one short RH-ON request that produces one known
`ready_stage` issue, capturing the raw logger stream from before enqueue through
admission. In the same check, record the running interpreter's imported
`scheduler.py` path and SHA-256, logger level/handlers, and the contiguous raw
lines for the matching RID. The acceptance oracle is: for each `rh_stage.v2`
RID, count and order `rh_match_prepare.v1` records from the same RH pass;
classify a missing record as source/runtime mismatch or log-drop only after
those runtime identity and raw-stream checks. Do not infer absent storage,
KV, Mamba, or hit fields as zero.

artifacts: this report
evidence: source commit 9213 inspection at `scheduler.py:3214-3271, 4356-4555, 4639-4682, 4772-4865, 4933-4965`; policy inspection at `scheduler_components/ready_horizon.py:479-535`; supplied final ON report lines 110-121, 128-140, and 169-185; applicable `AGENTS.md` read
summary: accepted source emits `rh_match_prepare.v1` on every preparation exit, and RH stage issuance requires a prepared match; thus stage-without-prepare is not the expected source path and indicates a telemetry/collection or runtime-source mismatch, not proof of zero values
followups: fresh bounded runtime check as specified above; additional diagnosis or telemetry repair requires a fresh Task ID
open_issues: live imported source identity, logger handler/filter behavior, and trace capture start/completeness were not authorized or available for this read-only source audit; no conclusion is made about absent cache/hit fields beyond not-computable
