# DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH

- **工作标题：** DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH.md`：**
- Task ID: `DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH`
- Orchestration epoch: `20260909-P4`
- Role: `devops`
- Target: `root@i-1.gpushare.com:27460` (RTX 3060, SM86)
- Status: `done`

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH.md`：**
Reconstructed the working 3060 runtime and brought the reviewed hybrid-frontier
fix online. The live service is PID `76671`; `/health` returned HTTP `200`, the
process remained alive, and port `30000` remained listening during final
verification.
The essential runtime correction is:
```text
PATH=/root/sglang-env-3060-4b/bin:$PATH
PYTHONPATH=/hy-tmp/ops-081-sm86-import-20260909:/root/sglang-3060-12g-hicache/python
```
The first reconstructed launch used the historical unquoted-prefix-key string
and exited with `JSONDecodeError`. That failed attempt is preserved. The final
launch uses the equivalent valid JSON object for the reviewed controller.

### 报告列出的产物/证据
- `phase2-hicache-design/work/DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH.md`：Remote artifacts:
- Final service log:
  `/tmp/qwen35-4b-hicache-p4-reconstruct-sm86-20260909-json.log`
  - SHA-256: `4df1162755980b60ba4bb760df59e8acda0c97c82d003ec479d37292e4e70f03`
- Final PID file:
  `/tmp/qwen35-4b-hicache-p4-reconstruct-sm86-20260909-json.pid`
  - content: `76671`
- Preserved failed-attempt log:
  `/tmp/qwen35-4b-hicache-p4-reconstruct-sm86-20260909.log`
  - SHA-256: `ae934782d1130ed032d16b657670694a7a2decc9c78d0f834fc6a5ce1b9d2965`
- Source pre-change backup:
  `/root/sglang-3060-12g-hicache/python/sglang/srt/mem_cache/unified_radix_cache.py.backup-DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH`
Prior reports read:
- `OPS-20260909-DEPLOY-HYBRID-GUARD.md`

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH.md` → `.memory/phase2-hicache-design/work/DEVOPS-20260909-RECONSTRUCT-SM86-LAUNCH.md`; SHA256 `230de0fd5b530c6c9234d58268c8ad571c9d6299db33b4d61cc447b63b2dbe1f`; source state `tracked`
