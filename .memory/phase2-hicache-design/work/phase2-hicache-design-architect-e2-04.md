# phase2-hicache-design-architect-e2-04 — p2-0-04 归因测量设计

## status
done

## artifacts
- `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/attribution-design.md`（交付物，已落盘；
  只写文档，未 commit 未 push）

## evidence
- 直读确认（本 agent，2026-08-30）：cache_controller.py:1197-1215（prefetch_rate_limited 门）、
  620-621（prefetch_capacity_limit=0.5×host pool）、1217-1240（_storage_hit_query 部分命中 break
  1235-1236）、984-987（pb_load_submit 无 rid）、869-870（load_back_tokens_total 单位=tokens）；
  unified_radix_cache.py:123-131（b15 发射器）、139-150（t38c /tmp/t38c-on 门控）、652-655、
  1469-1571（load_back 全有全无链）、1751-1753（query 静默限流）、1837-1846（issue 限流 t38c
  rid 级）、1963/2101/2194/2275/2358（occupied 增减）、2021-2024（pc_l3_host）、2104-2112
  （prefetch success/dropped info 行）、2414-2437（**host 压力部分分配变体 ②b，本设计新发现**）、
  2476-2503（drain 相位 t38c）、2893-2895（pb_load_done 无 rid）、2928-2977（init_load_back +
  pa_lb_init 2936-2938）；schedule_policy.py:1320-1330（prefill 调用无 mem_quota + 失败静默）；
  decode_hicache_mixin.py:207-228（decode 调用 + warning 216-226）；schedule_batch.py:1260-1266
  （needs_host_load_back）；server_args.py:852-856（page_size default None → 6734 解析）；
  metrics_collector.py:898-911/1871-1875/1890-1896/2103-2115/348-365/274-279（01 已验 + 本设计引用）
- 转引（01/02 已验证）：metric-availability.md R7/R12a/R12b、log-field-inventory.md §1.5/§2/§3/§6、
  tester e1:456（drvC run-1：input_delta=21005 / load_back 4,480 tokens / 异 sha16）、
  fetched-hicache-upstream.md:63-91（#32724 预算语义）

## summary

### 三机制触发条件摘要（mem_quota 门 inert，归因对象按勘察修正）
- **① L3→H 预算门**（cache_controller.py:1212-1213）：`prefetch_tokens_occupied ≥ 0.5×host pool`
  （冻结配置 ≈24,576 tokens）时静默拒绝。触发形态：高并发重访集中占满预算 → L3 查询静默返回 0
  （1751-1753）→ 无 pa_lb_init、无 prefetch → 全 span 重算；或 prefetch 启动被拒（1837-1846）
  → paced retry（scheduler.py:2912-2940，debug 不可见）→ 期间 device 匹配被驱逐 → recompute。
- **② L3 部分命中截断**（cache_controller.py:1235-1236，page 粒度 break）：L3 连续前缀被 churn
  部分覆盖 → prefetch 只交付部分 → pa_lb_init(部分) → 恢复部分 → 余量重算。drvC run-1 落此域
  （4,480/21,005 ≈ 0.213，H→D 段全有全无故部分恢复只可能源于此段）。
- **②b host 压力部分分配（本设计新发现变体，unified_radix_cache.py:2419-2428）**：cache 模式
  host alloc 失败 → 页对齐缩短前缀（2435-2436）→ 下游签名与 ② 相同；b15 面不可分，仅 t38c
  pc_l3_host（2021-2024）可拆。
- **③ H→D avail/evict 门**（unified_radix_cache.py:1535-1542 + 1554-1556，全有全无）：device 满 +
  locked 高 → 整体 return False → 恢复 0 → host_hit_length 全量重算。decode 模式有 warning
  （decode_hicache_mixin.py:216-226，rid 级）；prefill 模式静默。

### 测量变量表行数
34 行（G0 run 级骨架 15 + G1 per-rid 探针 7 + G2 引擎日志 5 + G3 driver 侧 3 + G4 可选 t38c 4）；
每行映射已验证源（file:line / 探针 evt / gauge），单位统一 tokens。

### partial-restore 判定公式
- per-rid：`E_r = pa_lb_init.host_hit_length`；`A_r = Σ pb_load_done.n_tokens`（窗口
  W=[t_init, t_init+5s]，07 校准）；`tol = max(0.05·E_r, 2·PAGE)`；full ⇔ E_r−A_r ≤ tol；
  partial ⇔ 0 < A_r < E_r−tol（仅②/②b）；H→D 全拒 ⇔ 窗口内无 pb_load_submit。
- run 级（plan 公式精确化）：`compression_ratio = A_run/E_run`（A_run=Δload_back_tokens_total，
  E_run=Σ host_hit_length）；`recompute_fraction = R_run/(R_run+S_run)`（R=Δmode=input，
  S=Δmode=storage_hit）；回退事件 ⇔ ratio < 0.95 且 R_run ≥ max(1,000, 0.05·(R+S))。
- 强度带：<0.05 全拒 / 0.05-0.30 强压缩（drvC=0.213 校准落此带）/ 0.30-0.95 中度 / ≥0.95 全量。

### 事件分类规则
A 正常恢复（pa_lb_init(H)→pb(≈H)，确证）；B 部分恢复后回退（pa_lb_init(H<D_r)→pb(≈H)，
R_r≈D_r−H，确证；②/②b 并类）；C 配额拒绝 H→D 型（pa_lb_init(H)→无 pb_load_submit，decode
确证 / prefill 高度可能）；D 配额拒绝 L3→H 型（无 pa_lb_init 无 success 行 + occupied= 饱和，
默认证据不足，t38c 可升确证）。局限：D 弱签名需排除阈值拒/L3 真无页/aux 拒绝；②+③ 叠加归 C
记 mechanism="②→③"；prefill C 恒高度可能；聚合级四类可稳定区分，per-req 受 pb_* 无 rid 限制。

### 探针缺口清单（P2-1 登记，均引擎改动 P2-0 外）
N1 pb_load_submit/done 无 rid（984-987/2893-2895）；N2 pa_lb_init 无 mem_quota 值且 mem_quota
恒 None（2936-2938/161-168）；N3 prefill 失败无日志（schedule_policy.py:1320-1330）；N4 预算门
拒绝无计数（cache_controller.py:1212）；N5 prefetch_tokens_occupied 未导出 /metrics；N6 prefetch
时长探针（L3→H wait，01 D2）；N7 ②/②b 拆分字段。另：t38c 门（/tmp/t38c-on touch，零引擎改动）
可 rid 级确证 D 类并拆 ②/②b —— 实验侧开关，需 tester 确认，默认不启用。

## followups
- p2-0-10 按 §6 事件表 schema（run_id|K|rid|class|mechanism|conf|ts|E_r|A_r|D_r|R_r|refs）执行；
  分析顺序：run 级公式圈问题 run → 事件链逐 rid 分类 → 频次/严重度分桶 → 机制归因。
- 07 首跑实证项（§7 决策点）：窗口 W、page_size resolved 值、prefetch_capacity_limit 实际值、
  buffer_only 模式确认（若实际 buffer_only 需切换 ① 判据为 1207-1210）、occupied= 日志行形态。

## open_issues
1. t38c 启用与否（零引擎改动；D 类频次高时中期启用，对 08/09 生效）。
2. drvC 型先例的机制归属（② vs ②b）在 P2-0 内不强行拆分（b15 面同签名），报告注明。
3. K=1 基线若出现 D 类 → 预算值推导异常（620-621 与 host pool 大小回查）。
