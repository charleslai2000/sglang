# OPS3060-BF16-CORRECTNESS-SMOKE-R3-20260910

- **工作标题：** OPS3060-BF16-CORRECTNESS-SMOKE-R3-20260910
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/OPS3060-BF16-CORRECTNESS-SMOKE-R3-20260910.md`：**
remote: i-1.gpushare.com:27460
workspace: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/OPS3060-BF16-CORRECTNESS-SMOKE-R3-20260910.md`：**
BF16 Qwen3.5-4B correctness is PASS at the minimum viable Mamba state-cache setting
(`max_mamba_cache_size=5`) with CUDA graphs and HiCache disabled. BF16 is not a production
capacity profile on the 12GB card: it consumes 8.62GB for weights before runtime pools,
leaving only 2.99GB. No BF16 capacity or performance sweep was run.


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/OPS3060-BF16-CORRECTNESS-SMOKE-R3-20260910.md` → `.memory/phase2-hicache-design/work/OPS3060-BF16-CORRECTNESS-SMOKE-R3-20260910.md`; SHA256 `f8a05ab35cd03ba7bdd320c95f33661ec84a5f1898a9035609a3e43b64716d99`; source state `tracked`
