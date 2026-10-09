# p2io-tester-e7c — READY 池填不起来因果账（现有 e7b 日志纯分析，run-20260901-115548）

## status
done — **结论：NO_L3_FULL 主导**（L3 无完整长链 + 链从未在 RH 期间补齐，recompute 92% never-hit）；NO_HEADROOM 为次要约束；CAUSAL_BLOCKED 不可见但非主因。**需补 decline 分类埋点才能最终定案**（见建议）。

## artifacts
- 数据源：`/tmp/p2io-e7b/engine-p2io-m4t-e7b.log`（6736 行，e14 M3 重做后 run-20260901-115548）
- 事件总账：restore_state=1361 / prefetch_issued=481 / prefetch_revoke=345 / restore_recompute=348 / restore_retry=323 / ready_stage=162 / io_finished=136 / ready_pool=112 / frontier_wait=46 / frontier_wake=33 / restore_ready=136
- 分析：会话内联脚本（行级正则，无跨距）

## evidence

### 1. 四类 breakdown
| 类 | 实测 | 定义/备注 |
|---|---|---|
| **ISSUED** | **ready_stage result=issued = 159**（162 行中 3 行 WAIT_CAPACITY），52 个 rid | 全量 issued；ready_stage state= RESTORING 159 / WAIT_CAPACITY 3 |
| **NO_L3_FULL（近似）** | 93 rid 首次 prefetch：**FULL=10（10.8%）PARTIAL=48（51.6%）NOHIT=35（37.6%）**；recompute 78 rid 中 **ever-full=3 ever-partial=3 never-hit=72（92.3%）** | 从 prefetch_issued/revoke storage_hit vs requested 统计。**部分 rid（48）有 host 残留 hit 但 < requested，为 partial** |
| **NO_HEADROOM** | **不可见（无否定埋点）**；替代指标 = ready_stage headroom 分布 min=0 p25=906 p50=1750 p75=6192 p90=14112 max=42784；**staging 时 headroom≥全链(20910)仅 6.8%**；issue 长度 p50=27811 远超 headroom p50=1750 | 明确标注：无 NO_HEADROOM 事件计数，仅 headroom 值画像 |
| **CAUSAL_BLOCKED** | **不可见**（negative-cache/epoch gate 抑制的候选无日志）；仅见 frontier_wait=46 wake=33（frontier 门 13 个未醒） | 需补埋点 |

### 2. 两个分母
- **分母 2**：storage_hit==requested 的 rid 数 = **10**（93 个发过 prefetch 的 rid 中），full 率 **10.8%**
- **分母 1**：理论可 stage rid 数近似 = **93**（发起过 prefetch 的 rid 总数，无 waiting-queue 快照——标注近似）

### 3. full-prefix availability 三时点（按 rid 追踪 storage_hit 变化）
```
rids with >=1 hit event = 75
  improved (L3 在 RH 活动期间补齐): 2  (2.7%)
  stuck (首次 hit == 末次 hit，链从未 materialize): 73  (97.3%)
  dropped: 0
```
- **enqueue**（首次 prefetch_issued）：已有 91% rid 非 full（93 中 85 非 full）
- **before execution**：storage_hit 未随重试增长（stuck 73 个）
- **after RH activity**：improve 仅 2——RH **既没有找到完整链，也没有破坏完整链生态**（无人为把它降级/变 partial；若 RH 破坏，应有 improve 无 / dropped > 0 或首时点 full 而后变 partial——实际 dropped=0）

### 4. ready_pool 时序
- 112 次事件：**size0=56 / size1=56，无 size≥2**（watermark=[2,4] 从未触发）
- 0→1 触发 55 次、1→0 回落 55 次——每次只到 size1 就回落，**从不累计到 budget**；size1 连续驻留 run 几乎全为 1（仅一个 run=2）
- 直接证据：池从无 2，稳态 ≥2 不可能（e7b 报告判 criterion 3 FAIL 的依据）

### 5. headroom 与 prefetch_capacity_limit
- staging 时 headroom≥capacity~21392 的仅 **6.8%**（11/162）；issue length p50=27811（L2/L3 超长链 27811/43513 tokens）
- **staging 时 issue length ≤ headroom 的仅 3.1%**（5/162）——几乎所有被 stage 的链长都超过当时 headroom
- 但这是"链太长 headroom 装不下整条"而非"headroom 阻塞 ISSUE"：ready_stage 全 result=issued 无条件否定

## summary
**因果账判定：NO_L3_FULL 主导。**

决定性证据链：
1. **L3 无完整链是根本**：93 个候选 rid 仅 10 个首次 full（10.8%），48 partial、35 nohit；最终 recompute 的 78 rid 里 **72 个（92%）从未拿到 storage_hit==requested**——链在 L3 根本未完整存在。
2. **RH 不是破坏者**：三时点 73/75 stuck + improve 仅 2 + dropped 0——RH 活动期间链既没被补齐也没被降级，完整链生态的"缺失"是入队时就存在的（首次 prefetch 已非 full），非 RH 造成。
3. **headroom 是次要约束，非第一原因**：ready_stage 全 issued（无 headroom 阻塞），headroom 小只限制了单次能 stage 的链长（issue p50=27811 > headroom p50=1750），导致 partial（48 rid），但真正卡死的是 L3 里这些超长链没有完整数据。
4. **CAUSAL_BLOCKED 不可见**，但推理上非主因：即使取消 epoch/negative-cache 抑制，被 stage 的 candidate 也多为 partial（51%），full 率不升——M3 门不是"池填不起来"的原因。

**NOT**：NO_HEADROOM 单独主导（headroom 未阻止 ISSUE）；NO_L3_FULL + NO_HEADROOM 两者都不主导时才有 CAUSAL_BLOCKED 空间——此处 NO_L3_FULL 明确主导，headroom 掺和限制规模层面。

## followups
1. **需补 decline 分类埋点重跑才能最终定案**：现有日志把 NO_HEADROOM / CAUSAL_BLOCKED 完全吞掉，无法区分"因 headroom 放弃 staging"与"被 epoch/negative-cache 抑制"。建议在 ready_horizon.py 的 staging/refill 决策点加 `ready_stage result=declined reason=NO_L3|NO_HEADROOM|CAUSAL_BLOCKED` 日志（同 result=issued 风格），重跑 M4T，则可定量三者的贡献。
2. **本账已证明的主结论可先行**：无论埋点结果，**L3 完整长链缺失（NO_L3_FULL）是首要靶——不是 READY 池策略问题**。下一步引擎侧应查为何这些长链（L2/L3，27811-43513 tokens）从未被完整持久化到 L3（write-through 不全？eviction 剥离 sidecar？backup 分片未合并？），而非在 READY 池水位上打转。
3. headroom 覆盖 6.8% 提示：即便 L3 补齐，headroom 也不足以装 20910-token 全链单次 stage——若 L3 完整链出现，headroom 公式（M1）会让 93% 的 stage 因长度>headroom 而 partial。此点与 NO_L3_FULL 叠加，二者都需引擎侧验证。

## open_issues
- CAUSAL_BLOCKED/NO_HEADROOM 定量缺埋点——需代码改动 + 重跑才能定案（本任务纯日志分析，未满足此条件）。
- 分母 1（93）为近似（无 waiting-queue 快照），full-prefix 真实候选上限可能略高。
- 本账基于 e14 重做后单 run；e14 前的 e7（spin 生态）三时点 profile 不同，不并入此因果账。