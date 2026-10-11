# DBG-20260909-MAMBA-FILE-MISMATCH

- **工作标题：** DEBUG-20260909-MAMBA-FILE-MISMATCH
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DEBUG-20260909-MAMBA-FILE-MISMATCH.md`：**
```text
status: done
task_id: DBG-20260909-MAMBA-FILE-MISMATCH
orchestration_epoch: 20260909-P4
role: debugger-deep
scope: read-only local source and authorized remote source/log/storage inspection
```

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/DEBUG-20260909-MAMBA-FILE-MISMATCH.md`：**
The two failures are caused by a **hybrid prefetch frontier mismatch introduced
by cache-mode host allocation**, not by a file-name construction mismatch.
The storage query correctly found a 54,976-page KV prefix and confirmed that a
Mamba state existed at *that queried prefix's tail*.  The scheduler then lacked
enough host staging space and silently shortened each operation to 21,060 or
21,121 pages.  The hybrid sidecar reader consequently changed the required
Mamba key to the tail of the shortened prefix, but did not re-run the
existence check at that new frontier.  Those two new keys do not have Mamba
files.  The file read returns `FileNotFoundError`, the all-or-nothing hybrid
check discards the otherwise-read KV prefix, and the request recomputes.
This makes the diagnostic field `sidecar_hits={mamba:54976}` easy to
misinterpret.  For `TRAILING_PAGES`, it means “the Mamba tail condition holds
at the 54,976-page query frontier,” not “54,976 independently retrievable
Mamba pages” and not “a Mamba file exists at every later host-cropped

### 报告列出的产物/证据
- `phase2-hicache-design/work/DEBUG-20260909-MAMBA-FILE-MISMATCH.md`：- Remote read-only sources: `/tmp/sglang3060-p4-fix.log`,
  `/tmp/t38c-probe.log`, and
  `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`.
- Local source: branch `3060-12g-qwen35-4b`, commit reported by prior audit as
  `277dd611001c31edcd3a8894213c5a44b00e9bd4`.
- This report is the only local write made by this task. No product files,
  3090 code, remote source, remote storage, or remote process was changed.

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DEBUG-20260909-MAMBA-FILE-MISMATCH.md` → `.memory/phase2-hicache-design/work/DEBUG-20260909-MAMBA-FILE-MISMATCH.md`; SHA256 `735bcb4c46c500d218b114019867c377743d48dce913a198baf5ce2eb2c70748`; source state `tracked`
