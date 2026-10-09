# OPS3060-BF16-CORRECTNESS-SMOKE-20260910

status: blocked
entry: ACCEPT
task_id: O3060-BF16-CORRECTNESS-SMOKE-20260910
invocation_id: INV-20260910-OPS-BF16-SMOKE-R1
orchestration_epoch: 20260910-bf16-correctness-smoke
role: devops-executor
capability_level: L4
workdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
memory_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design
memory_inputs:
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/TEST3060-AWQ-RUNTIME-AUDIT-20260910.md
  - /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-TENSOR-BOOL-PROBE-R4-20260910.md
memory_report: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-BF16-CORRECTNESS-SMOKE-20260910.md
parent_thread_id: 01a07bea-d668-75b2-8280-6a2cf0870c1e
observed_workspace_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
native_event_success: false
last_event: blocked

## Summary

blocked: the required local BF16 shard files were absent, so exact local/remote
hash verification could not pass. Per procedure, no service stop, BF16 launch,
inference request, or restoration action was performed. The existing AWQ service
was left untouched and remained healthy (HTTP 200).

## Completed preflight and hash evidence

- Workspace check: `pwd` returned
  `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`.
- Recorded synchronization evidence was read from
  `OPS3060-BF16-WEIGHTS-SYNC-20260910-R3.md`.
- That evidence records both authorized local inputs as absent:
  `/tmp/qwen35-bf16/model.safetensors-00001-of-00002.safetensors` and
  `/tmp/qwen35-bf16/model.safetensors-00002-of-00002.safetensors`.
- Recorded `stat` and `sha256sum` checks returned `No such file or directory`
  for both files; therefore local hashes cannot be verified or compared to
  remote hashes.
- Existing AWQ runtime evidence records PID `140507`, listener
  `127.0.0.1:30000`, and final `/health` HTTP 200.
- Existing AWQ runtime evidence records the known RH-ON launch flags and final
  service health 200.

## Commands / actions

- Read-only workspace and memory-input inspection completed.
- No SSH command was issued in this invocation.
- No process was stopped or started.
- No model request was sent.
- No repository or service file was edited.
- No Neuron or unrelated GPU process was touched.

## Changed resources

None. The AWQ service, remote files, local repository, and GPU state were left
unchanged.

## Verification evidence

- AWQ service remained healthy: HTTP 200, based on the supplied prior runtime
  audit evidence.
- BF16 correctness smoke: not run.
- BF16 startup memory/OOM, response tokens, and log-error checks: not available.
- Restoration verification: not needed; no mutation occurred.

## Followups

Provide or restore both local BF16 shard files at the exact authorized
`/tmp/qwen35-bf16/` paths, then dispatch a fresh invocation for hash verification
and the bounded smoke.

## Open issues

- Missing local BF16 shard files prevent the mandatory hash gate.
- Native lifecycle event delivery was interrupted before confirmation; report
  remains the authoritative artifact for this blocked invocation.
