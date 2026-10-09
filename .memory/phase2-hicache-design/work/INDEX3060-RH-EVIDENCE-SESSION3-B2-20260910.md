# RH evidence index — session 3 step B2

status: done
invocation: fresh
scope: read-only local indexing of the designated session-2 handoff, session-3-A recon report, bounded RH task reports, and product workspace review/evidence directories; no remote access, trace, service mutation, or Git mutation performed.

## Inputs

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/HANDOFF-2026-09-10-RH-SPEC-BUDGET-SESSION2.md`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/RECON3060-RH-LIVE-STATE-SESSION3-A-20260910.md`

## VERIFIED — local reports name retained output paths

The following exact remote paths are recorded by local task reports; this index did not inspect those remote files directly:

- `/tmp/sglang3060-rh-fix-4f41f5.log` — concurrent 4f41f5 RH launch/service log. The session-2 handoff says it is retained and must not be deleted; the earlier test report records the concurrent deploy/restart under this path.
- `/tmp/t38c-probe.log` — retained probe log, referenced by the session-2 handoff, session-3-A recon, and final RH-ON test report.
- `/tmp/b15-probe.log` — retained probe log, referenced by session-2 handoff, session-3-A recon, and the pre-fix test report.
- `/tmp/sglang3060-rh-on-9213-20260910.log` — retained RH-ON launch log for the later five-RID run.
- `/tmp/rh-match-emit-probe-short-03a170-20260910.raw` and `/tmp/sglang3060-rh-match-emit-03a170-20260910.log` — retained paths recorded in `DEBUG3060-RH-MATCH-RUNTIME-PROVENANCE-20260910.md`; these concern match-emitter telemetry, not the requested blocker+A/B driver join.

The product workspace has `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/evidence/`, but its bounded file listing contains only `gate2-k16`, `gate2-k4`, and `gate2-k8` collected/metrics/verdict files. No RH blocker+A/B driver or join output file was found there. The workspace review gates do contain `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260910-RH-SPEC-BUDGET-RETRIGGER-R3.md`, but it is a review artifact, not driver output.

## VERIFIED — available RID-level evidence, with limits

`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-RH-FINAL-ON-9213-20260910.md` records a later five-RID RH-ON replay with explicit suffix RIDs `x`, `y`, `z`, `w`, and `q`, including per-RID RH events and exact attempt joins. It reports:

- `y` and `q` as the only RH-eligible RIDs; both had accepted `rh_ready_host.v1` before `rh_admission.v2` (2/2).
- `q` had an initial `:prefetch:1` allocation failure and a final successful `:prefetch:2` retry.
- `x`, `z`, and `w` had response `cached_tokens=0`; no B label is assigned to any of these suffixes.
- `rh_match_prepare.v1` was absent for all five RIDs; no `restore_recompute` or `hybrid_discard` event was emitted in the post-preflight range.
- The exact harness output is described as “captured ... in the task execution record,” not as a local product-workspace output file.

This later five-RID run is not the interrupted concurrent two-request A/B trace described by the designated handoff and does not establish which RID was intended request B.

`/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-HORIZON-COMPARE-R2-20260910.md` records the pre-fix blocker plus two approximately-55K parked requests A/B and says RH-ON B fell through to `cached=0`; it is explicitly marked pre-fix and NOT VERIFIED for acceptance. It does not provide a readable driver/join output path or cryptographically bind request labels to retained raw output.

## NOT_FOUND — requested driver/join output

Within the searched local scope (designated handoff, session-3-A recon, RH/SPEC_BUDGET/FINAL-ON/FINAL-OFF task reports, and product `3090-dev/evidence` plus `review/gates` listings), no standalone driver output, join output, or raw A/B correlation artifact was found for the interrupted blocker+A/B trace.

The session-2 handoff states that readable artifacts did not establish A/B labels, the driver's join/output conclusion, or the required B-specific `cached=0` and full-history-recompute result. The session-3-A recon reports that its final bounded process scan observed no matching driver/join/trace process, while availability of output in retained files beyond inspected identifiers remains UNKNOWN.

## NOT_ESTABLISHED — acceptance implications

- `negative_cursor=54999` for the specifically identified B: not established by the indexed local evidence.
- B waking after speculative-budget release: not established for a labeled B.
- B Host-ready/RH stage before admission: not established for a labeled B. The later `y`/`q` run proves this only for those suffixes, not A/B.
- B avoiding `cached=0`: not established; the later five-RID run explicitly has `cached_tokens=0` for `x/z/w`, with no B mapping.
- B avoiding full-history recompute: not established for a labeled B.
- The current remote service state after the session-3-A transient `503` observation is not part of this local evidence index; session-3-A records readiness after that point as UNKNOWN.

## Exact caveat

The indexed evidence is sufficient to point downstream work to retained log names and to distinguish later five-RID per-RID telemetry from the interrupted A/B trace. It is insufficient to recover the missing driver/join correlation. Therefore the live RH blocker+A/B acceptance remains **NOT VERIFIED**; no A/B conclusion should be inferred from filenames, partial RID telemetry, or process absence.

artifacts:
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/INDEX3060-RH-EVIDENCE-SESSION3-B2-20260910.md`
evidence:
- Designated handoff and session-3-A recon read directly.
- Bounded local report/path searches and product evidence/review directory listings completed.
summary:
- Retained log path names are available in local reports, but no standalone driver/join output or readable A/B correlation artifact was found in the searched local scope; acceptance remains NOT VERIFIED.
followups:
- If a future authorized step needs B-specific acceptance, obtain the driver/join output or a fresh explicitly authorized trace with stable A/B labels; do not infer labels from the later x/y/z/w/q run.
open_issues:
- Missing driver/join output and A/B mapping.
- B-specific negative cursor, wake, Host-ready-before-admission, no-cached-zero, and no-full-history-recompute remain unestablished.
