# O3060-RH-TELEMETRY-DEPLOY-PROBE-20260910

status: blocked
entry: ACCEPT
task_id: O3060-RH-TELEMETRY-DEPLOY-PROBE-20260910
invocation_id: INV-20260910-OPS-DEPLOY-PROBE-R1
orchestration_epoch: 20260910-rh-telemetry-live-probe
role: devops-executor
capability_level: L4
workdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
memory_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design
memory_inputs:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-TELEMETRY-COMMIT-20260910.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/review/gates/REVIEW-20260910-RH-TELEMETRY-FAILURE-MARKER.md
memory_report: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-20260910.md
parent_thread_id: 01a07bea-d668-75b2-8280-6a2cf0870c1e
observed_workspace_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt

## Summary

Deployment was attempted exactly once. The scheduler file was backed up and replaced, but the restarted service failed during FlashInfer CUDA-graph initialization because `ninja` is absent. No 55K request was sent. Rollback restored the scheduler backup, but the original service also failed at the same pre-request startup point; final health is HTTP 000 and no SGLang launch PID remains.

## Commands and evidence

- Preflight SSH read: PID 127023 had the authorized launch flags; baseline health HTTP 200; pre-deploy scheduler SHA256 was `cc63e1319e7c84f525647bc20370e6f8ad84dbdcc5fa70ce531457ace3cb846`.
- Remote checkout had no `.git` metadata, so file hashes were used for revision verification.
- SCP copied local commit `1a8879750de9560a9acb3710357a45c115d4ac09` scheduler.py to the remote staging path.
- Backup created: `/root/sglang-3060-12g-hicache/python/sglang/srt/managers/scheduler.py.deploy-backup-20260910-014725`.
- Deployed scheduler SHA256: `033ddc8d643b332eed010372a49d19e33ce8011f71035ed4e1671cf76523c347`.
- Restart launch PID: `133272`; probe log: `/tmp/sglang3060-rh-telemetry-20260910-014725.log`.
- Startup failure evidence: `FileNotFoundError: [Errno 2] No such file or directory: 'ninja'`; process tree was terminated by the launcher.
- Rollback command copied the timestamped backup over scheduler.py. Restored SHA256: `cc63e1319e7c84f525647bc20370e6f8ad84dbdcc5fa70ce531457ace3cb846`.
- Original-flags restart PID: `134104`; rollback log: `/tmp/sglang3060-rh-telemetry-rollback-20260910-014725.log`.
- Rollback startup hit the same `ninja` failure; final `curl http://127.0.0.1:30000/health` returned HTTP `000`; final launch PID absent.

## Changed resources

- Remote scheduler.py temporarily changed to the authorized commit, then restored from the timestamped backup.
- Two timestamped backup/log artifacts remain on the remote host.
- No Neuron or unrelated GPU process was targeted. No request, capacity test, RH policy change, or other product file was performed.

## Verification

- Deployment hash: PASS before restart.
- Backup/rollback hash: PASS; restored baseline hash exact.
- Probe request/RID/event counts/per-RID ordering: NOT RUN because service never became healthy.
- Final service health: FAIL/HTTP 000; final service PID: absent.

## Followups

- Resolve the remote environment prerequisite (`ninja`) under a fresh authorized operations invocation, then retry deployment/probe if still required.

## Open issues

- Live telemetry evidence is unavailable due to startup failure.
- Service is not healthy after rollback because the same pre-existing runtime prerequisite failure prevents startup.
- Native `mcp__codex_tui__send_message_to_thread` was unavailable/not callable; lifecycle communication is degraded.
