# phase2-cap-e2-tester-e1

- **工作标题：** phase2-cap-e2-tester-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-cap-e2-tester-e1.md`：**
- Agent: tester
- Epoch: 1
- Date: 2026-09-07
- Target: `ssh -i /home/charles/.ssh/id_ed25519 -p 24052 root@175.155.64.171` (RTX 3090 24G, Qwen3.5-9B-w4a16)
- Repo deploy: `/root/sglang-b1-continuity`（editable）@ commit 9c9e7b7c7c（scheduler md5 495b8851，与本地 /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt HEAD 相同）
- 任务域：**只做** FP8 KV 可启性 + 容量基线观测；不做 ratio sweep / 50-80K 并发 / parked；不改产品代码
> 运行中收到 orchestrator 判据修正（用户 2026-09-07 权威裁决）：402-480K 目标口径变更 —— **禁止 kv_used+mamba_used 聚合**；业务目标 = **attention KV working set**（c8 下 8 个 ~50-60K active Agent 的 attention KV resident capacity，避免互相 eviction/recompute）。Mamba state 是 per-active-sequence slot，不折算进 400-480K 指标。基线观测**分列输出**（8 项，见 §4），attention KV 为主判据列，mamba 为独立约束列。本报告已按修正后口径撰写。
---

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-cap-e2-tester-e1.md`：**
**FP8 KV on 3090：PASS（可启动、健康、推理正确、数值未崩坏）。**
- 代码层支持面（scout Q1）实测兑现为运行层：`dtype torch.float8_e4m3fn`，**448K tokens KV = 6.84GB（FP8 减半直接实证）**；c8 实跑满 8 running；272/272 HTTP 200 无任何 error；device_hit 2.96M / host_hit 2.85M tokens 表明 FP8 KV 在 flashinfer+triton 路径下 cache/restore 数值正常（恢复前缀可正常继续解码）。
- **容量基线（修正后口径，分列）**：attention KV working set 在 448K 池下实测峰 **341,818 tokens**（p90 216,244），池可用 min 163（未耗尽 → 无 DQ≥55s / 仅 1 次 restore timeout）；mamba 64 slots = 3.12GB 独立列。
- 对 ② ratio sweep 起点（**事实，不推方案**）：本 run 已在 pool64 + FP8 下实测 attention KV working set 达到 **~342K**（8 × 平均 ~43K 长上下文 write 后的残留 resident）；→ "c8 下 8 个 ~50-60K active Agent" 的 400-480K working set 目标 = 需每 agent 更长历史（~50-60K）或更多 resident，当前负载形状（gate2 采 L0-L3 21-44K）落在 342K，**处于 400-480K 目标之下 ~17-29%**。sweep 时若收 max_total_tokens=448K 为 memory-computed 可容纳上限（未观察到 clamp warning），每档 ratio 只需扫 mamba 预算对 working set 的影响，不改变 attention KV 池上限；观察游标 = kv_used（attention KV working set），mamba 列（used/avail/evict + max 64）作约束。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-cap-e2-tester-e1.md`：- 本报告：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-cap-e2-tester-e1.md`
- 启动 wrapper（新增，仅配置层）：runner `/root/direct-launch-cap-fp8.sh`（md5 b97728cd…）；本地副本 `/tmp/direct-launch-cap-fp8.sh`
- 运行驱动（新增，仅配置层）：runner `/root/cap-fp8-run.sh`（md5 02d66e22…）；本地副本 `/tmp/cap-fp8-run.sh`
- 运行证据（runner 保留）：
  - `/root/evidence-cap-fp8-e2t/`（boot-metrics.txt、metrics-final.txt、gpu-util.csv、engine-alloc.txt、engine-events.txt、run-20260907-171921/{runs.csv,mid-run-metrics.txt,verdict.json,join.log}）
  - `/root/engine-cap-fp8-e2t.log`（引擎日志，8.5K 行）
  - `/root/cap-fp8-e2t-status.log`、`/root/cap-fp8-e2t-outer.log`

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `9c9e7b7c7c`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-cap-e2-tester-e1.md` → `.memory/phase2-hicache-design/work/phase2-cap-e2-tester-e1.md`; SHA256 `9c300c8ab56a7a76e9534598e8be287778e7ac66ed48fb06368d0e90e326ec77`; source state `tracked`
