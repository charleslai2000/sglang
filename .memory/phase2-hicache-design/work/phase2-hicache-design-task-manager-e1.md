# task-manager report — P2-0 scheduler baseline 分解（phase2-hicache-design）

- task: phase2-hicache-design
- agent: task-manager
- epoch: 1
- status: done

## status

done（计划已落盘并通过自检）

## artifacts

- plan.md: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/plan.md`
- 交换目录依据：repo 含 `.claude/`（rules/ + skills/）= 项目根（ARTIFACTS v5.2，不查 .git）；
  `.memory/phase2-hicache-design/` 为 orchestrator 本次派发前 09:51 创建的脚手架（含空 work/），
  P2-0 计划按其落盘；期间 09:54 出现的 `fetched-hicache-upstream.md`（上游 HiCache 设计研究，
  P2-1/P2-2/P2-4 参照）已读入并折入 01/03/04 的 reference_files。

## evidence（计划自检结果）

- 上下文已加载：sglang-3090-24g-hicache 分支状态（3090-24g-hicache，HEAD caeadcf492）、
  3090-dev 工具包（micro_qwen35.py 1365 行、launch-l3-3090.sh、chain_check.py、486 payload）、
  backpressure-analysis.md、tester t38sb 报告（三流水 + drvC 病灶）、fetched-hicache-upstream.md。
- 引擎侧 12 项指标可得性已预核实（计划内 01/02 需逐项落证据）：
  - 直接可得：`prefill_effective_tokens_total{mode=storage_hit|input}`（restore/recompute）、
    `load_back_tokens_total` + `load_back_duration_seconds` 直方图（H→D wait）、
    `prefetched_tokens_total`/`prefetch_pgs`/`prefetch_bandwidth`、
    `hicache_prefetch_aux_alloc_failed_tokens_total`（quota denied）、
    `kv_evictable_tokens`/`mamba_evictable_tokens`、`hicache_host_used/total_tokens`、
    `num_running_reqs`；per-req sglext `cached_tokens_details{device,host,storage}`；
    b15 探针 `pa_lb_init`/`pb_load_done`/`pa_evict`/`pa_writing_check`/`pa_batch`。
  - 不可直接得（计划明确标记）：slot refill gap（全量检索无 "refill" 字段，缺定义）、
    L3→H wait（无 prefetch 时长指标，候选=日志时间戳派生）、device locked tokens（派生）、
    restore quota compressed（无计数器，事件签名测量）。
- 计划结构自检：11 个子任务（p2-0-01..11），依赖边全部指向前序 id（DAG 无环）；
  3 个并行组（{01,02} {03,04} {05,06}）文件域不重叠、无共享运行资源；验收判据全部为可验证信号
  （文件存在 / grep 计数 / py_compile exit 0 / 证据目录 + MD5SUMS / 12 指标表落盘）；
  context_budget 全部 ≤M；epoch 边界 8 段，每段含交接报告约定；
  建议 agent 仅 coder/architect/tester，无 FAST-tier。
- P2-0 边界核查：全部子任务零引擎代码改动（engine 目录只读）、无 oracle、参数冻结
  （ratio=1.5 / max-total-tokens=32768 / L3=/data/l3/），证据结构沿用 /root/evidence-* 同构。

## summary

- 子任务数：11（勘察 2 / 设计 2 / 实现 2 / 实验 3 / 分析 1 / 收口 1）。
- 依赖链：01,02 → 03,04 → 05,06 → 07 → 08 → 09 → 10 → 11（批内并行、批间串行）。
- 并行组：Batch1 {01,02} 勘察、Batch2 {03,04} 设计、Batch3 {05,06} 实现；
  07（K=1 基线 + K=8 试点）→ 08（K=16+32）→ 09（K=64，RAM 门控）→ 10（归因）→ 11（基线报告）。
- 角色分配：coder = 01/02（勘察）/ 05/06（工具脚本）；architect = 03/04（设计）/ 10（归因分析）/
  11（基线报告）；tester = 07/08/09（实验执行）。
- 关键风险（现有日志不可得的 4 项）：slot refill gap、L3→H wait、device locked tokens、
  restore quota compressed —— 已在计划"已核实的指标可得性"表与 Missing Information 1-4 明确标记；
  其中 slot refill gap 与 L3→H wait 若勘察/首跑实证仍不可得，登记为 P2-1 依赖（引擎埋点，
  超出 P2-0 边界，不得在本阶段执行）。

## followups

1. 计划 §Missing Information 10 项 → orchestrator 与用户确认（尤以 1/2/5/6/9/10 项为要：
   slot refill gap 定义、L3→H wait 回退、实验执行身份/root 可写性、冻结参数清单完整性、
   64 agents 硬目标与否、payload suffix 复用策略）。
2. Batch 1（01/02）不依赖任何确认项，可立即派发；同批两个 coder 的 epoch 报告需按子任务后缀区分
   （plan.md §Parallel Groups 已注明）。
3. 03 设计须在 join.log 扩展 schema 定稿后供 05/06 并行执行使用（06 不依赖 05 完成，
   只依赖 03 schema）。

## open_issues

- slot refill gap 无任何现成字段，定义本身待专家定稿（计划已给出候选派生方案，未经确认）。
- L3→H wait 的日志时间戳派生可行性需 01/02 勘察 + 07 首跑实证；上游 #32724 语义（含 FCFS
  finalization lag）提示该指标观测值会大于纯 IO 时长。
- /root/evidence-* 当前对 charles 用户不可读：实验子任务执行身份（root）需确认后方可派发 07。
- mem_quota 压缩机制的调用方来源（调度路径未传 mem_quota，Optional 默认）——drvC 现场的确切
  压缩赋值点由 02 定位；若探针字段不足，归因量化退化为事件签名推断并登记 P2-1 依赖。
