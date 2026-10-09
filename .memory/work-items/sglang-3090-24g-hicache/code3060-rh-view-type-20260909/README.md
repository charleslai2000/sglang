# CODE3060-RH-VIEW-TYPE-20260909

- **工作标题：** CODE3060-RH-VIEW-TYPE-20260909
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/CODE3060-RH-VIEW-TYPE-20260909.md`：**
ENTRY: ACCEPT
status: done
task_id: CODE3060-RH-VIEW-TYPE-20260909
orchestration_epoch: 20260909-rh-ab37
role: coder

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/CODE3060-RH-VIEW-TYPE-20260909.md`：**
Fixed the RH-ON startup crash caused by treating raw `Req` objects from `frontier_reqs` as `ReadyHorizonView` instances. Policy-field decisions now use the corresponding view while RID/raw-request association and RH-OFF behavior remain unchanged.

### 报告列出的产物/证据
- `phase2-hicache-design/work/CODE3060-RH-VIEW-TYPE-20260909.md`：- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/managers/scheduler.py:4192-4195`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/test_rh_contract_dependency_free.py:197-271`
- Commit `f629d4e2c1` (`fix(hicache): join RH frontier requests to policy views`)
- This report: `CODE3060-RH-VIEW-TYPE-20260909.md`

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `f629d4e2c1`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/CODE3060-RH-VIEW-TYPE-20260909.md` → `.memory/phase2-hicache-design/work/CODE3060-RH-VIEW-TYPE-20260909.md`; SHA256 `af8eb09962353e97c6c38795d6b7b377977ab3c45a1d7f2017e6c4cdfd244d52`; source state `tracked`
