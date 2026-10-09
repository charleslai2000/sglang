# phase2-hicache-design-architect-e9 — P2-IO 第一阶段设计（page-size sweep + ExtentFileBackend + 经济模型）

## status

done — P2-IO 三部分设计文档落盘；只读设计完成（未实现 backend、未写引擎代码）。
任务边界更新（协调人消息）已吸收：用户裁决"本机专用 NVMe，不优化 HiCacheFile，直接做
自定义 L3 backend"；经济模型保留为 P2-IO-1 完成后的决策层输入（Part 3）。

## artifacts

- 设计文档: `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-io-design.md`
  （Part 1: P2-IO-0 page-size sweep / Part 2: P2-IO-1 ExtentFileBackend / Part 3: 经济模型）
- 本报告: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-architect-e9.md`

## evidence（标定数据来源）

| 数据 | 值 | 证据 |
|---|---|---|
| L3 纯 IO | 3-16s（p50 11,267ms / max 16,011ms，n=4；20910 页，0.5-0.8ms/页） | tester-e8.md:25,64 |
| l3_to_h_wait | 13.8s（29 对均值） | tester-e11.md:36 |
| h_to_d_wait | 0.064-0.073s | tester-e16.md:22 / e17:29 / e11:36 |
| prefill 吞吐 | ~3.4K t/s（4.24M/1,241s ≈ 8.0M/2,369s） | attribution-report-phase2a.md §1.3 |
| K=8 终判 | recompute 675,678 / restore 626,260 / p95 128.7s / wake 85% | tester-e17.md:23-41 |
| 官方 timeout 公式 | min(30, 2 + 0.1×tokens/1024)；本地统一路径默认 base=1.0/per_ki=0.25 | fetched-hicache-upstream.md:36-43；hybrid_cache_controller.py:225-229 |
| M1b T13 | WAIT 超时 60s（已实现） | scheduler.py:3043-3048；server_args.py:2840 |
| page-size 默认 | CUDA 默认 1 | overrides.py:2668 |
| mamba 约束 | page_size=1 断言仅当 extra_buffer 关；grid=lcm(64,ps) 四档恒 64 | mamba_component.py:67-75；runtime_context.py:1639-1644 |
| v2 接口/动态后端 | batch_exists_v2/get_v2/set_v2 + module_path/class_name 加载 | hicache_storage.py:167-220；backend_factory.py:114-141 |

## summary

### 结论（分三部分）

**Part 1 (P2-IO-0 sweep)**：纯引擎参数（--page-size ∈ {1,16,32,64}）K=8 短测，验证
64× 粒度下降。代码级兼容性核完：mamba 侧车四档均可加载（extra_buffer 开 →
page_size=1 断言不触发；chunk=max(64,ps)、grid=lcm 恒 64、track_interval 256 % ps = 0 全过）；
**ps=64 为边界精确对齐档，ps=16/32 的 mamba 段内切片语义需 sweep 实测（风险 R1，签名判据兜底）**。
预期 ps=64 延迟 0.3-0.5s（下限 ~0.21s 带宽）；判据组 = 签名 0 + CHAIN_GAP + 优雅退场 +
prefetch lifecycle 延迟表 + 文件数 ↓64×。sweep 顺带产出 M1 标定（每 page 字节：
launch 注释 128KB/token 保守估计 vs 经验 640MB/20,911 ≈ 31KB/token）。

**Part 2 (P2-IO-1 ExtentFileBackend)**：单预分配大文件 hicache.data + RAM 索引
(key → {extent_id, offset, length, generation})；batch_set_v2 连续 keys 聚合成 extent
一次 IO（字节双限 8-64MB 候选，协调人 65KB/page×128=8MB 估算与实测 31KB/token 不符 →
按字节双限而非纯页数）；batch_get_v2 按 extent 分组一次读再页切片；batch_exists_v2
纯 RAM O(1)（顺带消除 P2-0a H1 查询争用）；allocator = append/round-robin +
generation + lazy GC，无 WAL/B-tree（L3 是 cache）；v2 接口 + 动态后端挂载（引擎核心
零改动）；continuity invariant 原样保留——ACK 对象从"一页文件"变"一个 extent 中一批
连续页"，batch_set_v2 整体成功才推进 storage_persisted frontier（drain 2551 不动）。
评估框架 = 五维表（延迟/IOPS/元数据/复杂度/v2 兼容），对照基线 = ps=64 + HiCacheFile
（sweep 胜出项）；验收线 = 20911-token 链 restore p50 ≤ 0.6s、单链 IO ≤ 32 次、
O(extents) 元数据。

**Part 3 (经济模型)**：T_restore(L,H) = (L−H·ps)·t_page(ps)/ps + t_hd + t_fix vs
T_recompute(L) = L/P_prefill；break-even 页数阈值
L*_pages = (t_hd+t_fix) / (1/P_prefill − t_page(ps)/ps)，分母 ≤ 0 即永不恢复。

**数值实例（头号数字）**：
- ps=1 现状（t_page 0.5-0.8ms）：0.294 − 0.65 < 0 → **L* = ∞，全链 restore 经济上
  从不划算**（T_restore ≈ 13.6s ≫ T_recompute ≈ 6.15s @ 20,911 tokens）——与官方
  timeout policy（20,911 tokens → 4.04s 截断）方向一致；
- ps=64（t_page ≈ 0.65-1.0ms/page）：L* ≈ **320 token ≈ 5 页**——超过 ~5 页的任何
  恢复都划算；e17 部分恢复（均值 7.4K token/次）全落划算区；
- 决策点三处：D1 WAIT 进入前（T6/T7 deny 处，不进 WAIT 直接 recompute）、D2 T11/wake
  重试时（用最新 storage_hit_count 重算）、D3 T13 动态 deadline =
  min(60s, 经济 deadline, SLO deadline)——60s 保留为绝对上限（不违反"不要缩短
  timeout 掩盖"裁决：这是按模型预算，非拍脑袋缩短）。
- 静态阈值（v1，离线标定常量）vs 动态（v2，EWMA t_page + 设备负载）；建议静态上线 +
  预测-实际日志，积累后转动态。
- 测量缺口：G1 批级 IO 时长（引擎埋点，P2-IO-0 前置）、G2 collect_metrics 三项
  missing（实验侧）、G3 每页字节（实验侧）、G4 D1 决策点 rid 级日志（随 P2-IO-2 埋点）、
  G5/G6 实验侧。**引擎改动仅 G1+G4 两处埋点**。
- 实验设计：E1 现有基线（e17 1i）；E2 决策层开关对照（K=8×2，p95 下降、recompute
  上升 ≤ 模型预测）；E3 人为高低 L3 成本对照（ps=1 高成本 vs ps=64/extent 低成本，
  验证模型预测翻转）；E4 预测-实际归因（MAPE < 30%）。

### 待确认项（T1-T7，见设计文档 §4）

T1 sweep 的 G1 埋点先行裁决；T2 ps=16/32 mamba 段内切片实测；T3 每 page 字节；
T4 NVMe 带宽核验；T5 e17 13 次 rate-limit→60s 超时的 WAIT 时长明细；T6 G2 工具修复
归属；T7 #28653 本地复验（当前 ~63 万文件/20G 已近百万量级边缘）。

## followups

1. P2-IO-0 sweep 执行（tester）：4 档 × K=8，判据组见设计 1.4；产出延迟表 + M1 标定。
2. sweep 结果 → Part 2 B1（extent 字节预算）与 Part 3 参数定稿。
3. P2-IO-1 实现（coder）前拍板 B1-B5 开放项（设计 §2.9）。
4. P2-IO-2 决策层实现（coder）：D1/D2/D3 + G4 埋点 + E2-E4 实验（tester）。
5. 协调人确认 T1/T5 后 sweep 可开跑（T1 决定是否需先行埋点）。

## open_issues

- 65KB/page（协调人 extent 估算）与实测 31KB/token 的量级差：设计已改为字节双限，
  具体值待 M1 标定——不影响结构设计，只影响默认值。
- 动态阈值（v2）是否值得做：建议先静态 + 日志积累，由 E4 误差分析裁决。
- mamba 侧车在 ps=16/32 的段内切片语义是 sweep 前唯一未闭合的兼容性风险（R1）。
