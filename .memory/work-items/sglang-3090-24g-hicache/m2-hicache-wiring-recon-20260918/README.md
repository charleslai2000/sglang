# M2-HICACHE-WIRING-RECON-20260918

- **工作标题：** M2-HICACHE-WIRING-RECON-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M2-HICACHE-WIRING-RECON-20260918.md`：**
Map exactly what must change, where, and in what order to make M2 serve with
`--enable-hierarchical-cache`, and to promote the shared-src telemetry revision into the
frozen runtime identity. Read-only: no edits, no process signals, no GPU, no port binds,
no inference.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。

### 报告列出的产物/证据
- `phase2-hicache-design/agents/M2-HICACHE-WIRING-RECON-20260918.md`：All evidence below is from read-only commands on this host.
1. M2 argv/exec: `/opt/.../candidate-M2/launcher/launch.sh` lines 144-166 (ARGS), 168-213
   (GATE 3/3), 231 (exec); dry-run output quoted in R1 with `SGLANG_LAUNCH_DRY_RUN=1`,
   `CUDA_VISIBLE_DEVICES=999`, `LOG_DIR=/tmp/opencode/recon-dryrun-log`; exit 0, no bind.
   `bash -n launch.sh` exit 0.
2. Scaffold: `bin/start.sh` 34-41; `conf/service.env` 47-51, 90; grep for
   `M2_EXTRA_ARGS|EXTRA_ARGS` over `service.env`/`common.sh`/`start.sh` => none.
3. Gates: launcher lines 33-39/168-213 (quoted); audit runs quoted with exit codes 1/1 for
   M2/M1; `audit_launcher.py` lines 54-81 (allowlists), 116-121 (repin call site);…（节选；见来源报告）

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `ea7b0e9b44`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-HICACHE-WIRING-RECON-20260918.md` → `.memory/phase2-hicache-design/agents/M2-HICACHE-WIRING-RECON-20260918.md`; SHA256 `ebaec86eb2bc5a5f1c319ba65e904cbbcbe299c1884b2a3f88a63dd9f7abc427`; source state `tracked`
