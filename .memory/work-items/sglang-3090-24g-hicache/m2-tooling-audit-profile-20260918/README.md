# M2-TOOLING-AUDIT-PROFILE-20260918

- **工作标题：** M2-TOOLING-AUDIT-PROFILE-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M2-TOOLING-AUDIT-PROFILE-20260918.md`：**
Implement design D3 of `M2-HICACHE-RELEASE-DESIGN-R2-20260918.md`: introduce model-aware
`LAUNCHER_PROFILES` keyed by identity plus a `--profile` selector in
`3090-dev/tools/freeze/pysrc/audit_launcher.py`; add negative/positive profile tests in
`3090-dev/tools/freeze/pysrc/test_audit_launcher.py`; demonstrate real behavior against the
installed M1/M2 launchers (read-only). CPU-only; no GPU; no signalling; no port binds;
`freeze.sh`/`launcher-repin.sh` not run.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。

### 报告列出的产物/证据
- `phase2-hicache-design/agents/M2-TOOLING-AUDIT-PROFILE-20260918.md`：- Real command output pasted above for `py_compile`, the full 81/0 test run, and four
  `audit_launcher.py` invocations (M1 installed PASS, M2 installed pre-change FAIL, NEW M2 PASS,
  auto-select PASS), plus fail-closed probes.
- Exact literals implemented in `audit_launcher.py`: `M1_PROFILE` L167, `M2_PROFILE` L200,
  `LAUNCHER_PROFILES` L253, `select_profile` L259, `--profile` CLI L553, `LauncherProfile`
  dataclass L124, `UnknownProfileError` L119.
- Installed M1 launcher (`/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh`):
  bind L146 `--host 0.0.0.0`; no `--served-model-name`; extent L3 args L161-164.…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-TOOLING-AUDIT-PROFILE-20260918.md` → `.memory/phase2-hicache-design/agents/M2-TOOLING-AUDIT-PROFILE-20260918.md`; SHA256 `4c7860ebe1b876530c5142dc588635bdc94c4992e902f5cd0d8b6e19a8d45df8`; source state `tracked`
