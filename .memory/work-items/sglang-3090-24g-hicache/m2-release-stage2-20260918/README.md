# M2-RELEASE-STAGE2-20260918

- **工作标题：** M2-RELEASE-STAGE2-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M2-RELEASE-STAGE2-20260918.md`：**
离线产出**已通过源码范围门（RC=0）的冻结交付 stage**，供随后极窄窗口一次 freeze 成功。不得停/起
`:30000`，不得碰 `/opt/**` 冻结树。只执行已定义方法（M2-HICACHE-RELEASE-DESIGN-R2-20260918 D4 +
M2-RELEASE-WINDOW-A-20260918 的两个 blocker 裁决），不设计、不扩大范围。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** BLOCKED

**`phase2-hicache-design/agents/M2-RELEASE-STAGE2-20260918.md`：**
**stage 已按 D4 完整构建，但源码范围门无法在已授权方法下达成 RC=0。终态 BLOCKED。**
1. **stage 构建完成**（`/tmp/opencode/m2-stage2-20260918/`，top-level 恰为 `src/ launcher/ tools/`）：
   - 以 D4 基底 `/tmp/opencode/v1.2.1-stage` 复制（`cp -a`）。
   - 覆盖 D4 的 14 条路径（12 modified + 2 added）。detector sha =
     `848e0690cb80719e70c7ceedb7c1eb253c879d39a1b7be1cb85645f861a9d151`（DETECTOR_SHA_OK）。
   - 14 条中 12 条相对原 stage 有 DIFF，2 条原 stage 不存在（ABSENT→added）。
   - stage 源清单确定性：重生成得到 14788 行，与 `stage2-source.txt` 逐字节相同。
2. **D4 步骤 4 重绑完成**：stage2 `tools/validate_telemetry.py` 的 `SOURCE_HASHES`
   `unified_radix_cache.py` `5b5dc29f…`→`4a512882…`；该文件相对原 stage 仅此 1 处（2 行）变化；
   编辑后 sha = `c62b3d5b35eb47bcf6cc651387ae2ccd5142d099bdf69ea598bbe39cc2a6362c`。
   `repoint_telemetry.py` dry-run（`--tree` = stage2）PASS：`bindings_checked=10`、
   `mismatched=[]`、`missing=[]`、audit ok。
3. **门禁字面复现 RC=1**（决定性）：以 `freeze.sh:311-319` 的精确语义（2 条内置 + 164 条 allowlist，
   逗号连接）对 stage2 源清单跑 `manifest_tool.py compare`：

### 报告列出的产物/证据
- `phase2-hicache-design/agents/M2-RELEASE-STAGE2-20260918.md`：采集时间 2026-09-18T21:00–21:03Z；`curl 127.0.0.1:30000/health -> 200`。
- **E1 stage 布局与 base sha**
  ```
  ls -A /tmp/opencode/m2-stage2-20260918          -> launcher  src  tools
  /tmp/opencode/v1.2.1-stage/tools/validate_telemetry.py
    sha256 = d1e8b95e73ca80c28d23c33811160e3b639345cc4815eb4d16d08910683eae4c  (== baseline)
  /tmp/opencode/m2-stage2-20260918/tools/validate_telemetry.py
    sha256 = c62b3d5b35eb47bcf6cc651387ae2ccd5142d099bdf69ea598bbe39cc2a6362c
  stage2/src/python/.../qwen3_coder_detector.py
    sha256 = 848e0690cb80719e70c7ceedb7c1eb253c879d39a1b7be1cb85645f861a9d151
  ```
- **E2 重绑 diff**（仅 unified_radix_cache 一行，2 行变化）
  `work/.../validate_telemetry.diff`：…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-RELEASE-STAGE2-20260918.md` → `.memory/phase2-hicache-design/agents/M2-RELEASE-STAGE2-20260918.md`; SHA256 `2c8b7416bb14ebe710aedc5e38b99606610b535c4d751019f04f79ba3884eee6`; source state `tracked`
