# M2-FROZEN-LAUNCHER-ARCH-DESIGN-20260918

- **工作标题：** M2-FROZEN-LAUNCHER-ARCH-DESIGN-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M2-FROZEN-LAUNCHER-ARCH-DESIGN-20260918.md`：**
Produce the real, complete file contents for a frozen M2 launch path with parity to M1's
fail-closed safety guarantees, parameterized for the M2 model. Install nothing; restart nothing.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/agents/M2-FROZEN-LAUNCHER-ARCH-DESIGN-20260918.md`：**
DONE. All six deliverables are embedded verbatim below and are backed by real execution evidence:
- M2 launcher: 231 lines, `bash -n` exit 0, sha256
  `9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4`.
- M2 `manifest/identity.json`: valid JSON (exit 0), sha256
  `f46e49b8f562040809dff4d081eabaaba52337f4acdc3e2539abf69cdb5fb1bc`.
- `start.sh` diff: pure-insertion (0 removed lines), `git apply --check` and `patch -p1 --dry-run`
  both exit 0; prod/test case lines byte-identical.
- `service.env` diff: applies cleanly; additive only.
- `stop-m2.sh` draft: 89 lines, `bash -n` exit 0, sha256
  `3d27a0cd4f728f6c9dd34df252cb6f7c2ca98f2f0f216c902ac49b96c75c3243`.
- `/opt` install sequence: provided, NOT executed; mechanically proven in an isolated sandbox.
The full M1 gate sequence was executed for real against a staging copy of the M2 envelope: the
canonical `tools/preflight_identity.py` gate returned **PASS** (exit 0) and the launcher dry-run
returned **exit 0** with `SGLANG_L3_MODE=disabled`. Every fail-closed negative case fails closed.

### 报告列出的产物/证据
- `phase2-hicache-design/agents/M2-FROZEN-LAUNCHER-ARCH-DESIGN-20260918.md`：```
----- FILE-BEGIN launcher/launch.sh -----
#!/bin/bash

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-FROZEN-LAUNCHER-ARCH-DESIGN-20260918.md` → `.memory/phase2-hicache-design/agents/M2-FROZEN-LAUNCHER-ARCH-DESIGN-20260918.md`; SHA256 `a29c537ac5106b8abb8365c9963bc64c7610c69fe72e9fc55dcb6b8a04626948`; source state `tracked`
