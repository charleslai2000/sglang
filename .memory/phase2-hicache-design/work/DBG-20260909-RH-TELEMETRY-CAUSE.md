ENTRY: ACCEPT

# RH-ON final telemetry causal diagnosis

status: done
task_id: T3060-RH-TELEMETRY-CAUSE-20260909
orchestration_epoch: 20260909-rh-ab42
role: debugger-deep
scope: read-only source, report, test, and 3060 remote inspection; no product edits, process control, or load
revision: f629d4e2c19eb74571b4154438fd651ce24ff53b

## Verdict

The primary cause is an RH eligibility logic defect, exposed by the queue-first
RH-ON ownership change: `Scheduler._ready_horizon_views()` makes
`has_restore_potential()` a prerequisite to selecting `plan.to_issue`, but that
predicate is narrower than the real prefetch issue gate.  In particular,
`prefetch_gate_ok()` permits an L3-durable anchor, while
`has_restore_potential()` does not.  A long request with no host hit and an
existing, non-root, L3-durable anchor is consequently excluded before RH can
call `_prefetch_kvcache()`, even though that call's own gate would permit the
storage query.

The final ON run reached precisely this upstream exclusion for every RID.
The lack of request-correlated storage/RH lifecycle telemetry is downstream of
the absence of an issue attempt, not a probe/correlation failure: the probe
toggle was present and there are no target-RID `pc_prefetch_enter`,
`pc_outcome`, or `pc_storage_query` records.  The five HTTP 200 responses only
establish successful recomputation/admission; they do not establish storage
hits or RH benefit.

The exact runtime anchor class was not logged.  Therefore the evidence proves
the false `restore_potential=False` decision and the source-level gate
inconsistency, but does not directly observe whether the false result came
from a stale/deleted anchor or from the L3-durable-only branch.  The latter is
the supported and causally sufficient defect hypothesis because the matched
OFF control, with unchanged seed and same 55K shape, reported 54,976-token
KV+Mamba storage hits for every suffix.

Classification:

| Candidate | Disposition | Evidence |
| --- | --- | --- |
| (a) Genuine no restore potential | Not established; contradicted as a blanket workload explanation | Prompt length was 55,001 and cannot be the too-short case.  The prior OFF control recorded 54,976 KV + Mamba storage hits for each same-shaped suffix with the protected seed unchanged.  Per-request anchor facts are missing, so a single-run state change cannot be excluded. |
| (b) RH eligibility logic bug | Primary cause, source-confirmed; runtime anchor subtype not directly observed | `has_restore_potential` lacks `is_l3_durable`, whereas the actual issue gate includes it.  The ON trace logs `staging_eligible=False`, `restore_potential=False`, `decision=exclude`, and no attempt for all five requests before any prefetch call. |
| (c) Telemetry/probe correlation failure | Rejected for the storage-query absence | `/tmp/t38c-on` was present.  The probe has zero target-RID records, including zero `pc_prefetch_enter` and `pc_storage_query`; those records are emitted by the lower issue/query paths never entered.  RH preadmission logs correlated all five RIDs correctly. |
| (d) Other runtime issue | No evidence of a crash, flag/deploy mismatch, or budget/headroom denial | PID 112337 ran the RH-ON flags; deployed marker and local/remote hashes match f629.  First decisions had headroom 131,009, physical use 0, speculative use 0, and exclusion reason was not a budget/headroom state. |

## Reconstructed causal timeline

1. The process was deployed from the f629 marker and ran with
   `--enable-ready-horizon`, frontier 8, and speculative fraction 0.6.  Remote
   `/proc/112337/cwd` was `/root/sglang-3060-12g-hicache`; its
   `.codex-deployed-revision` is f629.  Remote SHA-256 values match the local
   f629 checkout exactly: scheduler
   `dfba8aa09f829f501da7ae143fde64e481a33a35a15fc2e9806bfb00db628e0f`, cache
   `482ee59f938110a8bee228beede55d8d4aa8dffabbf706110345b8ff463d966f`.
2. In RH-ON, `_add_request_to_queue` deliberately does **not** eagerly call
   `_prefetch_kvcache`; it appends the direct request to `waiting_queue`
   (`scheduler.py:4984-4999`, notably `4994-4998`).  This is the accepted
   queue-first ownership contract, rather than a deploy/configuration fault.
3. `_ready_horizon_pass` builds a view with
   `staging_eligible=self._restore_potential_for(req)`
   (`scheduler.py:4411-4440`, especially `4435`).  The RH pass emits
   `exclude/no_restore_potential` when that field is false
   (`scheduler.py:4192-4221`, especially `4205-4206`).  It calls the lower
   prefetch path only for `plan.to_issue` (`4253-4257`).
4. At 18:08:42, q's first decision (launch log line 88) reports
   `restore_state_before=null`, `active_prefetch_attempt_id=null`,
   `staging_eligible=False`, `restore_potential=False`, no negative-cache
   block, 131,009 host-headroom tokens, zero physical/speculative use, and
   `decision=exclude reason=no_restore_potential`.  At 18:08:43, x/y/z/w
   report the same facts at lines 91-94.  They are all inside the configured
   frontier.  Counts over the complete final range are q=1, x=2, y=13, z=24,
   w=35 decisions; all are the same exclusion.
5. Thus `plan.to_issue` was empty for each observed pass.  No RH attempt ID
   existed, no `ready_stage.v2`, `rh_ready_host.v1`, or `rh_admission.v2`
   could be emitted, and no caller reached `_prefetch_kvcache` or
   `prefetch_from_storage`.  The final report's zero issue attempts and absent
   join fields are expected consequences, not values to report as zero hits.
6. The storage probe is guarded only by the presence of `/tmp/t38c-on`
   (`unified_radix_cache.py:249-263`); remote inspection found it present.
   Nevertheless the probe has zero final-RID records, including zero
   `pc_prefetch_enter`, `pc_outcome`, and `pc_storage_query`.  Since the lower
   prefetch entry emits `pc_prefetch_enter` before its storage gate
   (`scheduler.py:3164-3171`) and the query emitter resides in the controller,
   this is consistent with no lower call, not with a missing RID join.

## Source defect

`_restore_potential_for` delegates directly to `has_restore_potential`
(`scheduler.py:4751-4760`).  For a long prompt, the latter returns false when
there is no host hit, no active/missed request marker, and the anchor is not
backuped/root (`unified_radix_cache.py:6061-6098`).  It does not consider
`is_l3_durable`.

```text
prefetch_gate_ok (4944-4956): backuped OR root OR l3_durable OR buffer hash
has_restore_potential (6086-6098): host hit OR active/missed OR (backuped OR root)
```

This violates the accepted RH contract's policy-completeness requirement:
RH-ON may not bypass or become stricter than the lower restore eligibility
without an intended policy rule (ARCH gate `INV-RH-5`, and G03's fake complete
KV+Mamba hit oracle in `ARCH-20260909-RH-PREADMISSION.md:273-275, 396-403`).
The focused f629 contract suite passed 6/6, but its ready-pass fixture fixes
`staging_eligible=False` and does not exercise this L3-durable-only
counterexample; it therefore does not falsify this diagnosis.

## Minimal next work (fresh Task ID required)

Recommended narrow patch: make RH's restore-potential predicate recognize the
same L3-durable anchor condition that `prefetch_gate_ok` recognizes, while
retaining the existing too-short guard and no-active-duplicate semantics.
Do not simply make every long request eligible and do not reintroduce RH-ON
eager enqueue.

Required deterministic oracle before a new live run:

1. Build a cache/request fixture with a long qualifying prompt, zero host hit,
   an existing non-root `is_l3_durable=True`, `is_backuped=False` anchor, and
   no active/missed marker.
2. Assert `has_restore_potential` / RH `staging_eligible` is true and the RH
   pass issues exactly one `READY_HORIZON` attempt before admission.
3. Assert the lower prefetch gate and RH predicate agree for root, backuped,
   L3-durable-only, deleted, short-prompt, active, and miss-marker cases.
4. Join the issue to a storage-query record, hybrid finalize, ready-host, and
   admission; retain `not_computable` if any required record is absent.

artifacts: this report; TEST3060-RH-FINAL-ON-TRACE-20260909.md; TEST3060-RH-FINAL-OFF-TRACE-20260909.md; OPS3060-DEPLOY-F629-RH-ON-20260909.md; remote /tmp/sglang3060-f629-rh-on-20260909.log and /tmp/t38c-probe.log
evidence: exact f629 local/remote hashes and revision marker; per-RID remote RH-decision lines 88, 91-94 and complete-count extraction; remote probe-toggle/target-RID extraction; source lines cited above; accepted RH design/review gates; local dependency-free RH contract suite 6/6 passing
summary: RH-ON correctly reached queue-first preadmission, but a narrower restore-potential predicate excluded all five storage-capable long prompts before the prefetch/query path.  Missing storage/RH joins are downstream of no issued attempt, not a telemetry-correlation failure.
followups: fresh Task ID for the narrow eligibility-alignment patch plus deterministic oracle; separate fresh task only if a new bounded live replay is wanted
open_issues: no target-run telemetry records the anchor ID, `node_exists`, `is_backuped`, `is_root`, or `is_l3_durable`; therefore the exact runtime false branch is not directly observed.  OFF-hit evidence strongly supports the L3-durable-only false-negative but does not prove the ON anchor identity.
