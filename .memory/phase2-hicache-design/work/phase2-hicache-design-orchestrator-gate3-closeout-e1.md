# phase2-hicache-design-orchestrator-gate3-closeout-e1 — Gate-3 收口（Run A 基线 + Run B Ready Horizon）
status: done
epoch: 1
task: gate3-baseline-soak 收口（Run B RH-ON 完成 + 四维测量 + A/B 对比 + class-A + correctness）

## 0. 说明
用户误杀 Gate-3 tester agent 后，orchestrator 直接接管收口（ledger 2026-09-04 已记）。
Run A（RH OFF）与 Run B（RH ON）两轮均已 2h 完整跑完 rc=0。
本报告为 Gate-3 最终收口结论，覆盖 e1 报告中缺失的 Run B（RH-ON）+ A/B 对比。

## 1. 运行产物（远程 3090 175.155.64.171）
- Run A: /root/evidence-gate3-soak/run-20260904-185337/  (18:53→20:54, 2499 req, RH OFF)
- Run B: /root/evidence-gate3-rhon/run-20260904-211848/  (21:16→23:20, 2127 req, RH ON)
- 引擎日志: /root/engine-gate3-soak.log / /root/engine-gate3-rhon.log（各 ~90-110MB）
- 配置核对（server_args）：两轮均 max_mamba_cache_size=None(=106 默认)、64G/96G extent、
  write_back、hicache_ratio=1.5、max_running=8、K=8 同批负载；唯一差异 = enable_ready_horizon
  False/True。GPU util 采样均在。

## 2. 四维测量

### 2.1 GPU utilization（nvidia-smi 5s 采样）
| 指标 | Run A (RH OFF) | Run B (RH ON) |
|---|---|---|
| n | 1445 | 1448 |
| mean / median | 96.8% / 100% | 97.6% / 100% |
| p90 | 100% | 100% |
| 采样 <90% | 6.4% | 3.9% |
| 采样 <50% | 1.2% | 0.8% |
两轮 GPU 均高饱和（均值 96.8/97.6，中位 100%）。空闲 dips 仅出现在开机关机边界。
**Ready Horizon 对 GPU util 无可见收益** —— 基线已跑满，无可隐藏的 idle。

### 2.2 L3 restore 延迟（load_back_duration histogram，秒）
| 分位 | Run A | Run B |
|---|---|---|
| p50 | ~0.02-0.05s | 同形 |
| p99 | <0.5s | 同形 |
| count | 1735 restores | 1725 restores |
| tokens | 3712 | 3462 |
成功 restore 的 load_back 延迟集中在 10-200ms（histogram p50 在 0.02-0.05 桶，
p99 <0.5s）——**远非假设中的 0.8s 最坏情况**。A/B 两轮 histogram 形态完全一致
（RH 不改变成功-restore 延迟）。

### 2.3 correctness
| 项 | Run A | Run B |
|---|---|---|
| CUDA OOM（严格模式） | 0 | 0 |
| forced_drop_to_miss | 13（reason=no_durable_backup） | 2 |
| host_pressure dropped | KV 453,698 + mamba 96 | KV 8 + mamba 8 |
| restore_loadback_fail | 10 | 0 |
| traceback/异常 | 62 行（boot FFmpeg 良性告警） | 同 |
| zero-progress / HTTP 错误 / 未完成 | 0 | 0 |

### 2.4 class-A（storage>0 但 restore 未成功）
以 restore_success rid 集合 vs runs.csv storage>0 行精确对齐：
- Run A: storage>0 行 627 条，全部有对应 restore_success → **class-A = 0**
- Run B: storage>0 行 1 条 → class-A ≈ 0
Step① 中 K8 33% 的 class-A 在 Gate-3 两轮均未再现（每 storage 行都能 restore 成功）。
待复核：Step① 的 class-A 判定口径（device 9/host 0/storage>0 但仍 revoked:miss）与
本精确对齐口径（storage>0 行是否出现在 restore_success）有差异——差异点是"行级结果 vs
事件级结果"。建议下一轮采样在 revoke 事件上直接带 storage_hit/restore_result 字段。

## 3. Run A/B 核心差异（决定性发现）

### 3.1 RH-ON 下 L3 读路径整体失效
Run B（RH ON）storage_hit≈16K tokens（0.04%），restore_success=2，restore_ready=3，
prefetch_revoke 全部 storage_hit=0 / storage_generation=0，revoked:miss=9302 全部
RECOMPUTE。从 21:18:49 第 1 个 restore 到 23:19 全程一致 —— **不是渐进迁移，是整条
L3 restore 链在 RH 开启时从不成功**。

### 3.2 写路径未停（L3 仍写入，只是读不回来）
| 事件 | Run A | Run B |
|---|---|---|
| extent_write | 39068（kv 27553/mamba 11515） | 37135（kv 24564/mamba 12571） |
| extent_recycle (GC) | 6454 / 323GB | **36984 / 1.85TB** |
| restore_recompute | 5556（survivability=host 5490） | 9347（host 9257） |
Run B 写盘照常、GC 更激进（36984 回收，是 A 的 5.7 倍），但读侧 restore 全部失败 →
storage 内基本无存活数据，多数 extent 生命周期 = 写→无 read→被 0.9 watermark LRU 回收。

### 3.3 聚合指标瀑布
| 指标 | Run A | Run B |
|---|---|---|
| aggregate hit | 0.7845 | 0.6672 |
| device / host / storage 占比 | 37.9 / 26.4 / 14.2% | 43.5 / 23.2 / 0.04% |
| L0 exact-checkpoint restore ratio | 0.8627 | 0.7876 |
| L1 | 0.7540 | 0.5512 |
| restore 行数 | 925 | 785 |
| 平均 running requests | 1.6 | 1.2 |

## 4. 归因（ready_horizon 机制问题）
证据链示 Ready Horizon 开启后，lingering restore 被 RH 前台调度抢占/取消并判
revoked:miss，且该行为从 run 首请求即开始（非容量/压力渐进）。GC（36984）和
host survivability（9257）是**结果**而非原因（storage 读不回 → 无数据可 restore
→ 全部命中 host → 写 0.9 水位被回收）。

具体断点（推测，需 coder 在 Ready Horizon 路径上核 override 策略）：
ready_stage probe 显示 result=issue 后下一个事件即 prefetch_revoke(storage_hit=0,
storage_generation=0) —— prefetch 发出但立即被 revoke，且 revoke 时 storage 无命中、
generation 归零。这指向 RH 的"restore 被新调度决策替代"路径：restore 未完成即被替换为
recompute，或 restore 与 ready 条件互斥。

附加观察：run B 的 restore_recompute 中 final_storage_survivability=host 9257 条 ——
在 RH 的"确保 ready"逻辑下，资源挤占后 KV 落回 host，STORAGE 从未被当作可恢复来源。

## 5. 结论（Gate-3 判定）
### 稳定基线（Run A，RH OFF）—— 可判定
- GPU util 96.8%、0 OOM、0 HTTP 错误、0 zero-progress、2h 不间断 —— 稳定性 PASS。
- host cache 饱和下的 host_pressure drop（453K KV tokens）为次要问题（老病，非本轮新）。 
- **Gate-3 baseline（RH OFF）稳定性 PASS**。

### Ready Horizon（Run B，RH ON）—— 不通过 / 有缺陷
- RH 开启后 L3 读路径整体失效（几乎 0 restore 成功），aggregate hit 掉 12 点，
  L0 exact ratio 掉 8 点。
- 这不是"RH 是否隐藏 0.8s 延迟"的问题——是 RH 直接让 L3 restore 链失效。
- GPU util 差异可忽略（96.8→97.6），无收益需要隐藏。

## 6. 后续动作（建议，待用户裁决）
1. **Ready Horizon 缺陷需先定位**（RH 下 restore 全部 revoked:miss 的机制断点），
   否则 RH 在 3090 上不可用。属于新 bug 分支，独立于性能 sweep。
2. 性能 sweep（用户已批准的独立任务，矩阵 32/64/106/160 × Graph OFF/ON）：
   **建议加一个 AX 对照**: 32-pool × Graph ON 且拟用 RH OFF 配置跑（因 RH ON 当前有缺陷）。
   其余按用户矩阵原样执行。
3. e1 report 中"Run B 未运行"的 open_issue 已由本轮闭环（Run B 已跑、已分析、已归因）。
4. host_pressure 453K 的 KV backup drop 是否追根因 → 留给用户裁决（Gate-3 PASS 不依赖它）。

## 7. open_issues
- Ready Horizon restore 失效的精确机制断点（代码层）——需 coder 排查，建议新 task。
- class-A 事件级口径复核（Step① vs 本轮对齐口径差异）。
- /data 磁盘：两轮 96G extent + GC 高频写，务必在下轮 sweep 前检查剩余空间。
