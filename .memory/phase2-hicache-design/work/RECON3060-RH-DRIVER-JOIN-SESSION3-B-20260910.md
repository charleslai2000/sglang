# RECON3060 RH driver/join — session 3 step B

Task ID: RH-SESSION3-B-DRIVER-JOIN-20260910  
Invocation: fresh  
Epoch: SESSION3-B  
Scope: strictly read-only remote/evidence inspection; no service, product-file, trace, cleanup, or Git mutation.

## Worker envelope

status: done
artifacts:
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/RECON3060-RH-DRIVER-JOIN-SESSION3-B-20260910.md`
evidence:
- Designated handoff read: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/HANDOFF-2026-09-10-RH-SPEC-BUDGET-SESSION2.md`.
- Step-A report read: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/RECON3060-RH-LIVE-STATE-SESSION3-A-20260910.md`.
- Remote target: `root@i-1.gpushare.com:27460`, accessed with the pre-existing read-only SSH identity `/home/dev-codex/.ssh/sglang_3060_ed25519` and `IdentitiesOnly=yes`.
- Remote metadata inventory at `2026-09-10T06:23:45+08:00` listed retained `/tmp` files and bounded `/root` files. Candidate RH logs were inspected read-only; no file was altered or deleted.
- Remote candidate inventory found scripts `/root/sglang-3060-12g-hicache/3090-dev/rh_durability_driver.py` and `rh_durability_analyze.py`, but no live driver process and no standalone blocker+A/B driver/join output bundle. The script's own `join.log`/`driver.log` contract is for a different P0 durability vehicle and is not evidence for this interrupted RH SPEC_BUDGET trace.
- Named-output search under `/tmp` and `/root` found only older durability `verdict.json` files under `/root/sglang-3060-12g-hicache/3090-dev/evidence/gate2-*`; no RH blocker+A/B `join.log`, driver verdict, run bundle, or A/B correlation artifact.
- Local evidence index independently records the same limitation: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/INDEX3060-RH-EVIDENCE-SESSION3-B2-20260910.md` lines 37–54.

## Availability and correlation findings

- Driver/join artifact: **NOT_AVAILABLE** for the interrupted concurrent blocker+A/B run. A bounded final process scan in Step A observed no driver/join/trace actor, and this step found no standalone retained output. Availability outside the inspected bounded paths is **UNKNOWN**, not negative proof.
- RID↔A/B mapping from a driver/join output: **NOT_AVAILABLE / UNKNOWN**. No driver result or stable external label mapping was found. Do not infer labels from filenames, log fragments, or process absence.
- Acceptance result for the specifically identified B: **NOT VERIFIED**. No acceptance criterion can be established as a complete B-specific gate from a driver/join artifact.

## Readable retained log evidence (not a driver/join artifact)

Two retained logs contain explicit literal `on-A`/`on-B` labels and are useful raw server telemetry, but they do not establish that those labels are the intended A/B labels from the missing concurrent driver, and therefore cannot replace the requested join output.

1. `/tmp/sglang3060-rh-queue-r1/on.log` (remote size 68,595 bytes; mtime `2026-09-10 04:26:46 +0800`):
   - Lines 96–99 show `on-A` issued a READY_HORIZON prefetch (`prefetch_length=54999`) and `ready_stage schema=rh_stage.v2`.
   - Lines 101–102 show `on-B` held for `speculative_budget` with `spec_budget=54999`; this is pre-fix/earlier queue evidence and does not prove the current fix's post-issue cursor behavior.
   - Lines 201–205 show `on-A` restore success and `admission.v2 ... ready_host_observed=true`.
   - No standalone driver/join output or correctness correlation is present in this file.

2. `/tmp/sglang3060-rh-horizon-r1/on.log` (remote size 338,832 bytes; mtime `2026-09-10 05:39:00 +0800`):
   - Lines 1000–1001 show `on-A`/`on-B` with `spec_budget=54999`, but B's logged `negative_cursor=0` in those retained server events; this is raw telemetry and not a driver-derived acceptance result.
   - Lines 3019–3027 show `on-A` prefetch completion/READY and then the B decision after release still logged `negative_cursor=0`.
   - Lines 3024 and 3933 show `on-A` `ready_host` and `admission.v2 ... ready_host_observed=true`.
   - Lines 3934–3944 show `on-B` admission and a prefill with `#cached-token: 0`; this is not a driver-labeled acceptance conclusion, and no complete B-specific no-cached-zero/no-full-history gate can be claimed.
   - No `negative_cursor=54999` literal was found in this file, and no `driver`/`verdict` marker was found.

3. `/tmp/sglang3060-rh-on-watermark55-4f41f5.log` (observed growing during the read-only inspection; size approximately 1.65 MB at the last bounded read):
   - It contains unrelated/later request traffic without `on-A`/`on-B` labels; the inspected events include multiple `restore_recompute ... cause=miss` records, including RIDs `b2b0512d252448e093c0b86938a09625` and `40b460d4c2d34d05bb168339dd5bca15`.
   - It contains no driver/join output and cannot supply A/B mapping. It must not be substituted for the interrupted concurrent A/B trace.

## Acceptance matrix

- Driver/join artifact available: **NOT_AVAILABLE**.
- Intended A/B labels correlated to concrete RIDs: **UNKNOWN** (no valid driver/join correlation).
- B `negative_cursor=54999`: **UNKNOWN / NOT ESTABLISHED** for the specifically intended B.
- B wakes after speculative-budget release: **UNKNOWN / NOT ESTABLISHED** for a driver-correlated B.
- B RH stage/Host-ready before admission: **UNKNOWN / NOT ESTABLISHED** for a driver-correlated B.
- B no `cached=0`: **UNKNOWN / NOT ESTABLISHED**; retained raw logs include an uncorrelated `#cached-token: 0` event.
- B no full-history recompute: **UNKNOWN / NOT ESTABLISHED** for a driver-correlated B; later unrelated watermark log has `restore_recompute cause=miss` events.
- HTTP/request correctness/cleanup: **NOT ESTABLISHED by this step**; this step was limited to driver/join retrieval and correlation.
- Live RH blocker+A/B acceptance: **NOT VERIFIED**, per the handoff and the evidence limitations above.

summary:
- Completed the requested read-only remote and retained-evidence search. No usable standalone driver/join output for the interrupted RH SPEC_BUDGET blocker+A/B trace is available in the bounded inspected scope. Explicit server-side `on-A`/`on-B` raw events exist in retained logs, but they are not a valid driver/join correlation and do not prove intended labels or acceptance. Live RH acceptance remains NOT VERIFIED.
followups:
- Preserve all remote model/cache/log paths. Do not infer A/B from the raw labels, filenames, or partial telemetry.
- Any future B-specific acceptance requires either the missing driver/join artifact or a separately authorized clean trace with stable A/B labels; no trace or service mutation is authorized by this step.
open_issues:
- Missing standalone blocker+A/B driver/join output and intended RID mapping.
- B-specific cursor, wake, Host-ready ordering, no-cached-zero, and no-full-history-recompute remain unestablished.
- Remote actor liveness/readiness after the Step-A observations remains outside this step's acceptance claim.
