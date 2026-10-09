# M1-CACHE-IDENTITY-CLOSURE-20260917

- **工作标题：** M1-CACHE-IDENTITY-CLOSURE-20260917
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/M1-CACHE-IDENTITY-CLOSURE-20260917.md`：**
Baseline: `3090-24g-opt@792d89a058` (final M1 form).
Owner ruling applied: reduce M1 to the minimal one-line change. The interim
`SGLANG_L3_NATIVE_WRITE_CACHE_DIR` env var was a redundant second configuration layer
and was removed.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/M1-CACHE-IDENTITY-CLOSURE-20260917.md`：**
**Check 1 — no cache in the repo.**
Pre-M1 stale `rust-cache/` (67M, mtime 12:06) predated the M1 commit (12:54), so it
was residue, not a regression. Removed. Then exercised the native load path
(`test_l3_native_wal_equivalence.py`, arm B) and re-asserted:
`<repo>/rust-cache` does **not** reappear.
**Check 2 — actual load path is outside the repo.**
```
workspace      : <repo>/rust
cache override : (unset -> SGLANG_CACHE_DIR/rust_extensions)
loaded .so     : /home/ubuntu/.cache/sglang/rust_extensions/artifacts/l3-native-wal/
                 51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376/
                 _l3wal.cpython-312-x86_64-linux-gnu.so
```
Loads from `~/.cache/sglang/...`, i.e. outside the source tree.


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `792d89a058`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/M1-CACHE-IDENTITY-CLOSURE-20260917.md` → `.memory/phase2-hicache-design/work/M1-CACHE-IDENTITY-CLOSURE-20260917.md`; SHA256 `715a94eb3a28642d392cf5cff9c37f57c8d7c365b24528143d85a43949dca6f6`; source state `tracked`
