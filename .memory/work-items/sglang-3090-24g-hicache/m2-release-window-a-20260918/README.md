# M2-RELEASE-WINDOW-A-20260918

- **工作标题：** M2-RELEASE-WINDOW-A-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M2-RELEASE-WINDOW-A-20260918.md`：**
在单个发布窗口内，按 `QWEN3CODER-INVALID-INDEX-PROD-20260918.md` 的 runbook 将 M2 新冻结树
（detector 加固 + telemetry + HiCache trio）上线 `:30000`。只冻 M2，M1 字节必须保持不变；任何步骤失败
即回滚。本任务为**执行**角色：只执行已定义方法，不诊断、不设计、不选择替代方案、不扩大范围；方法无效
或越权须报 BLOCKED 并停止。产出终态 artifact 即本文件。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** BLOCKED

**`phase2-hicache-design/agents/M2-RELEASE-WINDOW-A-20260918.md`：**
**未进入发布窗口，未停止 `:30000`，未做任何破坏性动作。** 在执行前对 runbook 步骤 2 与步骤 7 的
输入做确定性门禁复现时，发现两处方法缺陷，导致按 runbook 字面命令**无法达成 freeze exit 0**：
- **BLOCKER-1（命令缺陷）**：runbook 步骤 7 给出的 `freeze.sh` 命令**缺少 `--allowed-source-changes-file`**。
  `freeze.sh` 的 `ALLOWED_SOURCE_CHANGES_FILE` 默认为空，且**无任何自动加载**（仅由该 CLI 参数注入，
  `freeze.sh:60,86,311-317`；全仓库无其它注入点）。缺此参数时，源码范围门使用内置 2 条 literal
  allowlist，而 stage 相对 baseline v1.1 有 140 条新增路径、且 7 个 `src/` 文件内容非预期变化
  （因为这些路径本应由 164 条 allowlist 覆盖）。结果：`compare` RC=1 → `freeze.sh` 在源码范围门
  `exit 8`，**不可能 exit 0**。
- **BLOCKER-2（基底缺陷）**：runbook 步骤 2 要求"以现冻结 M2 树为基底"构造 stage，但该基底本身
  `tools/` 与 `launcher/` 与 baseline 不同：含 `tools/l3_namespace.py`、`tools/preflight_identity.py`，
  且 `launcher/launch.sh`、`tools/validate_telemetry.py` 已被重绑定/重指向。若以其为 `--src`，即使补上
  allowlist，源码范围门仍报 `unapproved_added=['tools/l3_namespace.py','tools/preflight_identity.py']` 与
  `changed unexpectedly=[./launcher/launch.sh, ./tools/validate_telemetry.py]`（allowlist 条目全部为
  `src/` 前缀，不含 `tools/`；`tools/` 由 `freeze.sh:195-196` 在门禁**之后**安装，故源清单里不应预置）。

### 报告列出的产物/证据
- `phase2-hicache-design/agents/M2-RELEASE-WINDOW-A-20260918.md`：采集时间 2026-09-18T20:52Z；采集时未执行任何冻结/停服。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-RELEASE-WINDOW-A-20260918.md` → `.memory/phase2-hicache-design/agents/M2-RELEASE-WINDOW-A-20260918.md`; SHA256 `da0c5602ce4abdb307e9f9eb2ef30895157b37d08fa381fd590fda1620ba4e8e`; source state `tracked`
