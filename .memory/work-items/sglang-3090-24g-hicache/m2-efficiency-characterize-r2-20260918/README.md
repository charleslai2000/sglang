# M2-EFFICIENCY-CHARACTERIZE-R2-20260918

- **工作标题：** M2-EFFICIENCY-CHARACTERIZE-R2-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M2-EFFICIENCY-CHARACTERIZE-R2-20260918.md`：**
Characterize the EFFICIENCY of M2 (OmniCoder-9B GPTQ INT4 on single RTX 3090 24GiB) using provided real measurement data without live server invocation.

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** The ~78 tok/s decode is

**`phase2-hicache-design/agents/M2-EFFICIENCY-CHARACTERIZE-R2-20260918.md`：**
- **Decode capability:** ~80 tok/s (pre-Swan), ~78 tok/s median (post-Swan). Roofline-valid for INT4 9B.
- **Real bottleneck:** Queue-starvation + long prefill, NOT decode. With max-running=8, 23k inputs, and 0% cache, the 8 slots are constantly contested.
- **Tail:** The 3x-to-30x variance in E2E stems from queue depth + prefill overhead, not decode slowdown.
- **Missing:** The true cause of 0% cache hit rate; precise queue dynamics; partition vs total resource usage.
---

### 报告列出的产物/证据
- `phase2-hicache-design/agents/M2-EFFICIENCY-CHARACTERIZE-R2-20260918.md`：| Metric | Value | Source |
|--------|-------|--------|
| Requests | 254 | Provided |
| end-to-end mean | 6651 ms | Provided |
| TTFT mean | 1152 ms | Provided |
| TTFT / E2E ratio | 17.4% | Computed |
| decode TPS (mean) | 78.45 tok/s (TTFT-only) | Provided |
| decode TPS (aggregate) | 73.95 tok/s | Provided |
| median input | 23,503 tokens | Provided |
| Output tokens | 104,037 | Provided |
| Cache hit rate | 0.0% | Provided |
| GPU memory | 19.1/24 GiB | Provided |
| max-running-requests | 8 | Provided |
---

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-EFFICIENCY-CHARACTERIZE-R2-20260918.md` → `.memory/phase2-hicache-design/agents/M2-EFFICIENCY-CHARACTERIZE-R2-20260918.md`; SHA256 `681d819b9732d9260de31c8d291199e36768c285257cad1c53c216f745da4b37`; source state `tracked`
