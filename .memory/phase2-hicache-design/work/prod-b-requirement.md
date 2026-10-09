# Phase-2 生产验证要求书（B 线）— 22151 真实生产 workload

> 来源：用户 2026-09-07 正式收口裁决 —— Phase-2 状态机修复收口，主线切换为"容量与生产性能优化"。
> 本文 = orchestrator 向生产侧（负责 22151 的环境角色）交付的**执行要求书**。执行方按此推进，进度/证据回报过来。

## 0. 背景与边界（必须遵守）

- Phase-2 状态机修复**已收口**：周期性 HOL / miss / too_short 状态机长尾已修复（2h L3 ON soak 7/7 PASS）。
- **措辞铁律**：不得写"所有 60–100s latency 归零"。当前已知残余（容量压力下有界长尾，非状态机 bug）：p99≈83s、66 次 restore_recompute timeout、26 次 DQ≥55s wait。
- **禁止修改 restore 状态机**，除非出现新的 correctness/progress 证据（此后一切现象先归因容量与性能，不改状态机代码）。
- 22151 **暂不恢复旧生产 profile**（以本要求书配置为准）。

## 1. 部署目标

- 机：**22151**（175.155.64.171:22151，pytorch-8802，RTX 3090 24G，/data 300G）。
- 代码：**branch 3090-24g-opt HEAD = 9c9e7b7c7c**（Phase-2 production candidate；push 完成后再打 tag `3090-hicache-phase2-pc1`，从 tag 拉取部署）。
- 配置（用户定项）：**FP8 KV + pool64 + graph bs8 + L3 ON**。
- 模型：Qwen3.5-9B（w4a16 权重，与 22151 既有部署一致）+ **FP8 KV cache**。
- 并发：真实 Claude 7–8 subagent workload（生产目标 20 subagent 并发是远期容量目标，本线按真实 7–8 验证）。

## 2. 配置明细（逐项对照，含待核实项）

| 项 | 值 | 状态 |
|---|---|---|
| kv_cache_dtype | **fp8_e4m3**（3090 已验证档；mxfp8 为 MX 卡档，勿用于 3090） | 代码支持已核实（server_args/kv_cache_dtype.py） |
| mamba pool | **64**（沿用生产冻结 pool64；5 slots/req → ~12.8 conc 上限） | 既有基线 |
| CUDA graph | **ON**，batch size 8（"graph bs8"） | ⚠️ 需生产侧核实 graph 参数语义与既有 conc8/c8 脚本差异，核实后执行 |
| L3 | **ON**（extent write_back 三层缓存） | 与 soak 同配置 |
| Ready Horizon | 沿用生产基线 **RH OFF**（生产冻结；RH 为 deferred known issue，本次不变） | ⚠️ 若生产侧有不同指示请回报，否则按 RH OFF |
| 访问 | 保留既有 CCR 接入 | 不可降级 |

## 3. 部署步骤（执行方）

1. push 后拉起 tag `3090-hicache-phase2-pc1` 对应代码（等同 9c9e7b7c7c）。
2. 备份 22151 当前生产配置/启动脚本（可回退路径）。
3. 按 §2 落配置启动引擎；验证：引擎 healthy、L3 extent 挂载、FP8 kv 生效（engine log / metrics 确认）、GPU 内存 footer 正常。
4. 接 CCR 接入，跑真实 Claude 7–8 subagent workload。
5. 全程采集指标（§4），run 结束后出判定（§5）。

## 4. 验收指标（重点清单，用户给定）

| 指标 | 说明 |
|---|---|
| TTFT p50 / p95 / p99 | 含 p99 绝对值与周期性检测（对照 soak：p50 19.1 / p90 34.5 / p95 43.4 / p99 83.0，无 =60s 周期峰） |
| >30s / >60s 请求比例 | 明确占比与散布（不聚集 = 无 HOL cliff） |
| DEVICE_QUOTA wait | 频次 / 时长 / 是否有紧循环（对照 soak 685 池竞争量级） |
| restore_recompute timeout | 计数与时间分布（对照 soak 66 散布 52 min） |
| storage_hit / restore_success | 逐小时切分，防中段塌陷（对照 soak hourly 154/147） |
| GPU util | 平均值与空窗（对照 soak 97.8%） |
| aggregate TPS | 总体吞吐 |
| correctness 四项 | OOM / HTTP error / assert / zero-progress = 0 |

## 5. 判定

- **PASS 判据**：TTFT p95/p99 无周期 ≈60s 峰；>60s 请求为散布非聚集；DV/DEVICE_QUOTA 无 13ms 级紧循环；无 assert/crash/OOM/HTTP error/zero-progress；storage_hit/restore_success 逐小时稳定；forward progress 持续。
- **有界长尾容忍**：p99≈83s、数十次 timeout、数十次 DQ≥55s 在容量压力下为**可容忍有界长尾**（已被裁决非状态机 bug），不因出现即 FAIL；若显著恶化（如 >60s 请求聚集、restore_success 塌陷），**先归因容量/配置**，产出证据，申请下一步（sizing 优化 = A 线），**不改状态机**。
- 结论分级：PASS / PASS-有条件（附残余清单）/ FAIL（附证据与容量归因）。

## 6. 回报要求

- 回报此要求书的执行窗口、配置核实结果（⚠️ 项）、§4 全指标、§5 判定、残余清单、环境回退路径是否完整。
- 涉及任何状态机代码改动的提议 = STOP，报回 orchestrator（本轮禁止，除非新 correctness/progress 证据）。

## 7. 与 A 线（容量 sizing）的关系

- B 线 = 真实工作负载验证当前 candidate；A 线 = FP8+pool64+graph bs8 下 mamba ratio / total KV 400–480K sizing 探索。
- 两者在"FP8 KV"上是同一配置族；A 线产生的 sizing 优化（减少 DEVICE_QUOTA / restore pressure）若胜出，可回注 B 线复验。B 线先跑。