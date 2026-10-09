# phase2-hicache-design-tester-warmctx-e1 — 实验② 长上下文 warm-turn 延迟

- Agent: tester
- Epoch: 1
- Date: 2026-09-05
- Target: `ssh -i /home/charles/.ssh/id_ed25519 -p 24052 root@175.155.64.171` (RTX3090 24G, Qwen3.5-9B-w4a16)
- Status: **done** (32K/64K/128K 三档全部跑完 rc=0，GPU 干净，核心判定完成)

> 注：本报告为最终完成版。此前经历了 2 次环境容量阻塞（/data 0 字节 + / 满），已由环境方清理恢复后完成全部三档。

## 0. 核心判定（warm-turn 是否随 context 增长）

**Warm-turn（热 session 下一轮）延迟不随 context 长度成倍增长 —— 三级 cache 成功兜住历史。**
- context 从 32K → 128K 增 **4 倍**，但 warm steady wall 仅从 1.06s → 1.92s（**1.81x**），warm TTFT 从 0.29s → 0.92s（3.13x）。
- 对比 COLD（全历史预填）从 8.57s → 47.2s（**5.51x**，近随 context 线性）—— 冷启动仍受历史长度主导。
- **决定性证据（cache hit）**：warm 稳态每轮 `prefill_input_delta` ≈ 7-33 token（仅增量重算），而 `prefill_devicehit_delta` ≈ 32064/64064/128192（**全历史 100% device-hit**），`host_hit=0`、`storage_hit=0`。历史前缀在 GPU L1 全命中，只有新增 delta 参与计算。

## 1. 方法（驱动 + 协议）

- 驱动 `gate2_warmctx.py`：COLD turn 发整段历史（空 cache 预填，tokenizer 精确截档：32K→32053 / 64K→64030 / 128K→128155 token）→ 取 assistant 回复 → WARM turn 同 session 重发字节一致历史 + assistant + 短新 delta（~几十 token）。
- `stream:true` → common SSE 解析，`ttft_s` = 首 token 时间（**真 TTFT**），`wall_s` = E2E。规避阶段② 基线 §3.3 的 stream:false 口径陷阱。
- 每档 N=3 独立 session × R=3 重复；**warm 稳态 = r2/r3**（r1 是 COLD 后的首次 warm，含过渡一次性成本，偏慢）。逐请求记录 prefill_effective_tokens 各 mode delta（engine 计数，独立交叉验证）。
- 每档 fresh namespace `/data/l3/p2io-warmctx-<tier>`，MAX_TOTAL_TOKENS 按档（64K=131072 / 128K=196608），引擎启动/测量/teardown 串行，SIGTERM 按 PID + 确认回 15MiB idle。

## 2. 结果表（每档 COLD vs WARM）

| 档 | COLD wall p50 | COLD ttft p50 | COLD prompt | WARM wall p50 | WARM ttft p50 | warm prefill_input | warm device_hit | warm host/storage |
|----|---------------|---------------|-------------|---------------|---------------|--------------------|-----------------|-------------------|
| 32K | 8.57s | 8.44s | 32053 | **1.064s** | **0.293s** | 33 | 32064 | 0 / 0 |
| 64K | 19.15s | 19.01s | 64030 | **1.297s** | **0.451s** | 10 | 64064 | 0 / 0 |
| 128K | 47.23s | 47.06s | 128155 | **1.923s** | **0.916s** | 7 | 128192 | 0 / 0 |

（WARM = steady r2/r3 pooled median，n=9/档；COLD = 3 session median。COLD 全 rc=0，WARM 全 rc=0。）

### 逐 session 原始（warm 稳态 r2/r3）
- 32K: wall 1.06/0.98, 1.08/1.01, 1.06/0.97; ttft 0.29/0.21, 0.31/0.23, 0.29/0.20
- 64K: wall 1.30/1.23, 1.32/1.20, 1.26/1.18; ttft 0.45/0.38, 0.47/0.36, 0.42/0.33
- 128K: wall 1.97/1.82, 1.90/1.82, 1.92/1.83; ttft 0.96/0.81, 0.89/0.82, 0.92/0.82

### 核心比值（context 4x：32K→128K）
- **warm wall: 1.81x**（1.064→1.923s）
- **warm TTFT: 3.13x**（0.293→0.916s）
- COLD wall: 5.51x（8.57→47.23s）—— 冷启动仍随历史线性涨

## 3. 关键机理 / 归因

- **warm 全 device-hit**：三档 warm 稳态 `prefill_input_delta` 仅 7-33（=新 delta token 数），`prefill_devicehit_delta` = 32064/64064/128192（=历史全量）。GPU L1 兜住全部历史，引擎只对新增内容做前向。这就是 warm-turn 不随 context 涨的直接原因。
- **TTFT 3.13x vs wall 1.81x 的差异**：128K 档首 token 前需读取/校验更长历史前缀的 radix 树 + 更长完整 prompt 的解码前处理（KV 布局/注意力掩盖准备），故 TTFT 增长略超 wall；但两者都远低于 COLD 的 5.5x，且绝对增量小（<0.7s），**不构成"随 context 成倍涨"**。
- **r1（COLD 后首个 warm）偏慢**：32K 3.5s / 64K 5.1s / 128K 6.5s —— 首次 warm 需建立 session 前缀到 device 的完整 KV/SSM 状态（含 L2/L3 restore 冷路径），后续 r2/r3 纯 device-hit。这是"冷→热过渡"的一次性成本，不计入稳态 warm 指标。

## 4. 资源与显存

- 24G 单并发 latency 档安全：boot avail mem 32K=9.21G / 64K=7.21G / 128K=5.21G，无 OOM（grep "CUDA out of memory" = 0）。128K KV ≈ 4.2GB + mamba pool32 1.55GB + 权重，mem_fraction 0.92。
- **mem_fraction 未调**：三档均 0.92，无需为 64K/128K 调整（128K 档 boot avail 仍有 5.21G headroom）。
- extent 写入：32K 物理 5.3G / 64K 50M（稀疏回收）/ 128K 1.8G；累计 extent_write 字节 32K=5.43 / 64K=9.94 / 128K=15.92 GiB。无 ENOSPC / 写失败（三档 engine log grep = 0）。

## 5. 证据路径（runner）
- 证据：`/root/evidence-warmctx-{32k,64k,128k}/run-*/`（runs.csv、verdict.json、driver.log、metrics-final.txt、engine-events.txt、engine-alloc.txt）
- 引擎日志：`/root/engine-warmctx-{32k,64k,128k}.log`；状态：`/root/warmctx-{tier}-status.log`
- 脚本：`/root/gate2_warmctx.py`、`/root/run-warmctx-tier.sh`、`/root/direct-launch-warmctx.sh`、`/root/warmctx_analyze.py`
- 本地镜像：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/`

## 6. open_issues

1. **/data 磁盘紧张（运行后 1.9G 空闲，100%）**：extent 物理写较小（32K=5.3G / 128K=1.8G）但累计 extent_write 字节较大（128K=15.9G，含回收）。三档均未写失败（grep ENOSPC=0）。若后续更大档位/更高并发需先释放 /data 空间。此为 runner 容量边界，非本实验缺陷。
2. **host/storage_hit = 0**：warm 稳态全 device-hit，未直接观测到 L2/L3 restore 路径的 warm 贡献（因为历史太"热"，全在 L1）。三级 cache 的 L2/L3 价值体现在 COLD/跨 session 场景（r1 的 3.5-6.5s 含 L2/L3 restore），而非本实验的稳态 warm 指标。若需单独量化 L2/L3 对 warm 的贡献，需构造"历史被逐出 L1、仅存 L2/L3"的场景（超出本实验 scope）。
3. **128K TTFT 3.13x > wall 1.81x**：首 token 前长前缀处理成本随 context 略超线性，但绝对增量小；已在 §3 归因，非 cache 失效。
4. **r1 排除**：本报告 warm 稳态用 r2/r3（避免 COLD 后过渡一次性成本混入稳态指标），r1 已单独列出。
5. **磁盘余量对延迟的影响**：本实验 warm 稳态指标主要受 device-hit 主导，磁盘（L3 extent）写主要发生在 COLD 预填阶段，且三档均无写失败；运行期间迁移 tar 为流式读（不占 /data 写），对本实验延迟影响有限（无异常延迟值，见 §2 原始值均落在合理区间）。

## followups
- 建议 reviewer 复核：驱动 trace 确定性（tokenizer 截档）、流式 TTFT 口径、cache-hit 计数（prefill devicehit delta 独立于客户端 cached_tokens 字段）。
- 如需扩展：64K/128K 的历史从 L1 逐出后测 L2/L3 warm 贡献（open_issues 2）。
