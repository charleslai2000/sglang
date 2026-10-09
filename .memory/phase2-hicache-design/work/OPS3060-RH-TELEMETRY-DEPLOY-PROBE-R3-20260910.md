# O3060-RH-TELEMETRY-DEPLOY-PROBE-20260910

status: done
entry: ACCEPT
task_id: O3060-RH-TELEMETRY-DEPLOY-PROBE-20260910
invocation_id: INV-20260910-OPS-DEPLOY-PROBE-R3
orchestration_epoch: 20260910-rh-telemetry-live-probe-r3
role: devops-executor
capability_level: L4
workdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
memory_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design
memory_inputs: declared inputs in dispatch
memory_report: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-R3-20260910.md
parent_thread_id: 01a07bea-d668-75b2-8280-6a2cf0870c1e
observed_workspace_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt

## Summary

The authorized scheduler deployment and exactly one short request completed. The deployed code reached health 200 and the request returned HTTP 200 with `prompt_tokens=55024`. For RID `1c70d8ab5b2b4829bcea21095690e1f2`, `rh_match_prepare_emit_failed.v1` was observed before `rh_stage.v2`; no normal `rh_match_prepare.v1` was observed. The service was subsequently restored to the timestamped baseline backup and final health is 200 with PID 137660.

## Commands and evidence

- Local commit file SHA256: `033ddc8d643b332eed010372a49d19e33ce8011f71035ed4e1671cf76523c347`.
- Preflight remote PID: `135729`; health HTTP 200; baseline scheduler SHA256 `cc63e1319e7c84f525647bc20370e6f8ad84dbdcc5fa70ce531457ace3cb846`.
- Backup: `/root/sglang-3060-12g-hicache/python/sglang/srt/managers/scheduler.py.deploy-backup-20260910-015524`; backup SHA256 equals baseline.
- Deployed scheduler SHA256 equals required `033ddc8d643b332eed010372a49d19e33ce8011f71035ed4e1671cf76523c347`.
- Deployment log: `/tmp/sglang3060-rh-telemetry-20260910-015524.log`.
- Exactly one request used text prefix `RHMatchEmitProbeShort_1a887975_20260910 ` plus `x ` repeated 54999 times, and only `sampling_params={temperature:0,max_new_tokens:1}`.
- Raw response: `/tmp/rh-telemetry-probe-20260910-015524.raw`, 446 bytes, SHA256 `1d7983ea69cd90aa6c9c89eac13b8ba02f464c1e2a8988a38db03cd1bd413f0f`.
- Request response: HTTP 200, generated one token, `prompt_tokens=55024`, RID `1c70d8ab5b2b4829bcea21095690e1f2`.
- For the probe RID: `rh_match_prepare_emit_failed.v1` count 2; `rh_match_prepare.v1` count 0; `rh_preadmission.v1` included issue then exclude; `rh_stage.v2` count 1. The first failure marker precedes the stage event; strict required marker-before-stage ordering is satisfied.
- Rollback restored scheduler SHA256 `cc63e1319e7c84f525647bc20370e6f8ad84dbdcc5fa70ce531457ace3cb846`; final health HTTP 200; final PID 137660.

## Changed resources

Only the authorized remote scheduler file was temporarily replaced and restored. One timestamped backup and deployment/rollback logs remain. No Neuron or unrelated GPU process, RH policy, capacity test, or storage was touched.

## Verification

Deployment hash: PASS. Health after deployment: PASS (200). Exact single probe: PASS (HTTP 200). Failure-marker ordering: PASS. Rollback hash and final health: PASS.

## Followups

None within this invocation.

## Open issues

Normal `rh_match_prepare.v1` was not emitted; the observed telemetry path used the approved failure marker. Native lifecycle event tool was unavailable/not callable, so communication is degraded.
