# p2-0-01 指标可得性勘察 — coder e1 报告

## status
**done** — 12 项指标可得性矩阵完成，17 条 grep 验证命令实际执行全部命中，交付
metric-availability.md。只读勘察（未修改任何引擎/工具文件），仅新增交付文档 + 本报告。

## artifacts
- **新建** `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/metric-availability.md`
  —— 12 行可用性矩阵（R1-R12）+ 专项核实 4 项 + 验证命令汇总 V1-V17 + P2-1 依赖登记
  D1-D6 + open issues。任务唯一交付物。
- 本报告 `phase2-hicache-design-coder-e1-01.md`。

## evidence

矩阵要点：**direct 8 行**（agent-turns/s、per-agent p95、active width、restore-served、
recompute-served、H→D wait、device free、device evictable）/ **derived 2 行**（device
locked、restore quota compressed 事件签名）/ **absent 2 行**（slot refill gap、L3→H
wait）。quota denied 计数器 direct 但覆盖面有限（预算门拒绝静默）。

抽查 17 条 grep（V1-V17）实际执行，命中数与预期一致，代表例：
- `grep -c -F "prefill_effective_tokens_total" metrics_collector.py` = 4（注册 898-911
  + 递增 1272-1288，mode=input/storage_hit 实证）
- `grep -c -F "load_back_duration_seconds" metrics_collector.py` = 4；observe 点 2 处
  （unified_radix_cache.py:2921、hiradix_cache.py:1137，CUDA event 实测）
- `grep -c -F '"evt": "pa_lb_init"' unified_radix_cache.py` = 1（2936，字段 evt/rid/
  host_hit_length/ts-ms）；`"evt": "pb_load_done"` = 1（2893，字段 evt/n_tokens/
  n_pending/ts-ms）
- `grep -rn -E "\brefill\b"` mem_cache/+scheduler.py → 仅 unified_tree_core.py:1832,1835
  无关日志，确认无 refill 度量
- `grep -rn -F "prefetch success"` 全仓库仅 docstring；`prefetch_tokens_occupied` 在
  observability/ 零引用（内部字段未导出）

专项核实结论：
1. **slot refill gap**：缺定义（absent）。候选派生 kv_used_tokens 谷宽 gauge 齐全且
   同周期（pool_stats_observer.py:136-138），但分辨率受引擎更新周期限制
   （decode_log_interval 默认 40 迭代 ≈ 秒级）。
2. **L3→H wait**：不可得（absent）。无时长直方图（StorageMetrics 1849-1853 无
   duration）；prefetch 完成行 debug 级（hiradix_cache.py:1673）、无开始行 → 日志
   派生否决；t38sb "HiCache prefetch success" 行**不在本 checkout**（部署差异，
   07 实测）；t38c 探针仅 issue 相位。登记 P2-1（D2）。
3. **device locked**：派生可行，公式 = max_total_num_tokens − kv_available −
   kv_evictable − kv_used（不变式残差，metrics_collector.py:93-95；四 gauge 同周期）。
   计划原文 "free=total−used" 公式修正（会混入 evictable+locked）。mamba 池无总容量
   gauge → mamba locked 缺口（D5）。
4. **restore quota compressed**：探针字段**足以区分**三态（正常/部分恢复回退/配额
   拒绝）：pa_lb_init(host_hit_length) + pb_load_done(n_tokens) + driver per-req
   input_delta 配对；但 pa_lb_init 无 mem_quota 字段 → 压缩 quota 精确值不可得
   （D4）。"无 pb_load_done" 需窗口判定（07 实证）。

不可得项清单：R4 slot refill gap（缺定义，候选派生待 07 实证）、R7 L3→H wait（无
时长指标+日志不可派生 → P2-1 D2）、R12a 预算门拒绝率（静默路径 → P2-1 D3）、R11
mamba locked（无总容量 gauge → P2-1 D5）。

## summary
12 行矩阵逐项落在四类来源（/metrics、引擎日志、b15 探针、driver 产物）上：8 行
direct 由注册点+递增点+driver 解析链三重证据支撑；2 行 derived 给出修正后公式与
同周期保证；2 行 absent 给出缺失原因与 P2-1 依赖登记（D1/D2）。勘察最重要的新发现：
① 本 checkout 无 t38sb 观察到的 "HiCache prefetch success" 日志行（部署差异，07 需
实测引擎实际日志形态）；② prefetch 预算门（prefetch_rate_limited）拒绝路径静默
（cache_controller.py:1212 → hiradix_cache.py:1499 return 0 无任何可观测输出）；
③ pa_lb_init 探针缺 mem_quota 字段但 host_hit_length 够分类用；④ mamba 池总容量
gauge 缺失。

## followups
- p2-0-03（driver 设计）：R1/R2 的 join.log agent_id 扩展 schema；采样节奏设计需考虑
  gauge 更新周期（decode_log_interval=40）。
- p2-0-06（collect_metrics）：记录每次 /metrics 快照时刻 + 引擎更新周期；按 R4 分辨率
  限制设计 kv_used_tokens 时序列。
- p2-0-07（首跑实证）：① 引擎日志实际 prefetch 行形态（D6）；② pb_load_done 窗口
  大小；③ host_memory_mode 对 R12b 分类的影响；④ locked 派生语义对照
  available_and_evictable_str；⑤ mid-run 指标快照里四 gauge 同周期验证。

## open_issues
- 本 checkout 与部署引擎容器代码不一致的疑问（"HiCache prefetch success" 行来源），
  本文按本 checkout 默认配置判定，07 以实际引擎日志为准，若部署代码与 checkout 不同
  需向 orchestrator 报告差异面。
- 引擎侧无 gauge 导出 `prefetch_tokens_occupied`/occupancy_ratio（上游 #32724 语义的
  预算不可直接读），quota denied 只能覆盖 aux-alloc 失败路径。
- 本任务只读完成，未执行任何引擎代码改动；无测试/编译动作（纯文档勘察，无代码）。
