# Exhaustively locate `switch-codex` on this host and resolve the EXISTS / NOT-EXISTS

- **工作标题：** SWITCHCODEX-HUNT-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/SWITCHCODEX-HUNT-20260918.md`：**
contradiction; inventory any context/model declarations it contains; enumerate all remaining
context-window declarations reachable from this host; determine the authoritative component on the
request path; probe gateway reachability read-only.
Owner: orchestrator (SWITCHCODEX-HUNT-20260918 dispatch). Artifact owner: this file only.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。

### 报告列出的产物/证据
- `phase2-hicache-design/agents/SWITCHCODEX-HUNT-20260918.md`：Raw, trimmed where noted. Full outputs are in the OpenCode tool-output store
(`~/.local/share/opencode/tool-output/`) as produced by this session.
**E1 — /usr/local/bin and PATH (name absence, not permission-limited)**
```
$ command -v switch-codex; type -a switch-codex
(no output; rc=1)   # "type: switch-codex: not found"
$ ls -la /usr/local/bin/
-rwxr-xr-x 1 root root 185989248 Sep 15 19:23 opencode
lrwxrwxrwx 1 root root        22 Mar  1  2025 nsys -> /etc/alternatives/nsys
lrwxrwxrwx 1 root root        25 Mar  1  2025 nsys-ui -> /etc/alternatives/nsys-ui
$ sudo -n true; echo rc=$?
rc=0                # sudo -n available; absence is not a sudo limitation
```…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/SWITCHCODEX-HUNT-20260918.md` → `.memory/phase2-hicache-design/agents/SWITCHCODEX-HUNT-20260918.md`; SHA256 `d298a136a58106deb1380b2e5ab2d3c7efd6707b38e14c2975b1699116031d32`; source state `tracked`
