# O3060-RH-TELEMETRY-DEPLOY-PROBE-20260910

- **工作标题：** OPS3060-RH-ENV-PATH-RESTORE-20260910
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 3
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/OPS3060-RH-ENV-PATH-RESTORE-20260910.md`：**
entry: ACCEPT
task_id: O3060-RH-TELEMETRY-DEPLOY-PROBE-20260910
invocation_id: INV-20260910-OPS-ENV-PATH-RESTORE-R2
orchestration_epoch: 20260910-rh-env-path-restore
role: devops-executor
capability_level: L4
workdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
memory_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design

**`phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-20260910.md`：**
entry: ACCEPT
task_id: O3060-RH-TELEMETRY-DEPLOY-PROBE-20260910
invocation_id: INV-20260910-OPS-DEPLOY-PROBE-R1
orchestration_epoch: 20260910-rh-telemetry-live-probe
role: devops-executor
capability_level: L4
workdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
memory_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design

**`phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-R3-20260910.md`：**
entry: ACCEPT
task_id: O3060-RH-TELEMETRY-DEPLOY-PROBE-20260910
invocation_id: INV-20260910-OPS-DEPLOY-PROBE-R3
orchestration_epoch: 20260910-rh-telemetry-live-probe-r3
role: devops-executor
capability_level: L4
workdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
memory_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** blocked; done

**`phase2-hicache-design/work/OPS3060-RH-ENV-PATH-RESTORE-20260910.md`：**
Restored the remote 3060 AWQ service using the exact prior RH-ON launch flags with
`PATH=/root/sglang-env-3060-4b/bin:$PATH`. No product code or scheduler file was changed,
no request was sent, and no Neuron or unrelated GPU process was touched.

**`phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-20260910.md`：**
Deployment was attempted exactly once. The scheduler file was backed up and replaced, but the restarted service failed during FlashInfer CUDA-graph initialization because `ninja` is absent. No 55K request was sent. Rollback restored the scheduler backup, but the original service also failed at the same pre-request startup point; final health is HTTP 000 and no SGLang launch PID remains.

**`phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-R3-20260910.md`：**
The authorized scheduler deployment and exactly one short request completed. The deployed code reached health 200 and the request returned HTTP 200 with `prompt_tokens=55024`. For RID `1c70d8ab5b2b4829bcea21095690e1f2`, `rh_match_prepare_emit_failed.v1` was observed before `rh_stage.v2`; no normal `rh_match_prepare.v1` was observed. The service was subsequently restored to the timestamped baseline backup and final health is 200 with PID 137660.


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `1a8879750de9560a9acb3710357a45c115d4ac09`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/OPS3060-RH-ENV-PATH-RESTORE-20260910.md` → `.memory/phase2-hicache-design/work/OPS3060-RH-ENV-PATH-RESTORE-20260910.md`; SHA256 `0501454a6de26472f7a34a5b91158c8d8668dfba5706d43f7dff371ac483b7ad`; source state `tracked`
- `phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-20260910.md` → `.memory/phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-20260910.md`; SHA256 `ab7dce0129abb13e601f6a7dbddaa7caa1e6d6eed38b4b01f7600f27a7991888`; source state `tracked`
- `phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-R3-20260910.md` → `.memory/phase2-hicache-design/work/OPS3060-RH-TELEMETRY-DEPLOY-PROBE-R3-20260910.md`; SHA256 `1750ce068785fc4861b49505708d997079dc5a3fb80349b41eba9f10b8353909`; source state `tracked`
