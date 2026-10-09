# phase2-hicache-design-tester-gate2-redesign-e1 (D2)

## status
done

## artifacts

Gate-2 重测设计稿（D2）。**纯设计——不重跑、不改生产代码、不动 3090。** 产出 = 本文档（六节）。所有数值来自已归档证据（gate1-l3restore / gate2-saturation / gate2-fbe-rerun / coder-restore-hit0）+ 本机只读核对（extent 后端源码、launch 脚本、analyzer）。

已在设计前本机只读核实的硬事实（非新运行）：
- `extent_file_backend.py`：`_gc_evict` 水位 = `used_bytes > max_size×eviction_ratio`（默认 0.9）；`_max_size_bytes` 读 `extra["max_size"]` / `SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE`（:220-222）；file_size 默认 64G、extent 默认 64M → slots = file_size//extent_size = 1024（:271-275）。
- **file_size 与 extent_size 都是 launch-config 可配**（`SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE` / `_EXTENT_SIZE`，:194-209），非代码常量 —— 所以地址空间上限可经 launch env 上调（属配置变更，非生产代码修改）。
- `launch-l3-3090.sh:89` `MAX_SIZE="${MAX_SIZE:-20G}"`，注释 "40G does not fit the 46G-free disk budget"——**该预算注释已过时**（/data 已清理，180G free）。
- analyzer 缺陷确认：`gate2_analyze.py:377` `full_miss(<100)` 用 `usable<100` 计数，而 `_row_from_artifacts`/join 在 missing-sglext 行 `device/host/storage` 为 None 被 `not isinstance` 跳过 → full_miss 恒 0，误导。**设计稿只订正口径，不改代码。**

## evidence

本阶段证据 = 已归档报告 + 本机只读源码核对（上面 artifacts 节）。无 3090 运行。

关键既有数字（引用，非新测）：
- gate1 链 ≈ KV ~490MB + mamba 51.5MB ≈ **541.5MB/链**（gate1 实测 KV 133374 页 4.37GB / mamba 71 次 3.66GB 总量量级；任务给定 490+51.5）。
- gate1 累计逻辑写 ~8GB < 20G → **0 recycle** → restore 全命中（restore-hit0-e1 §evidence）。
- gate2 累计逻辑写 ~232GB（kv 126.9G + mamba 105.6G）≈ 20G 的 11.6× → **6144 次 extent_recycle** → 958/958 durable 链 restore kv_hit_pages=0（restore-hit0-e1）。
- mamba 池 106 槽，gate2 全档 evictable 峰值 32-34/106，**从未饱和**；饱和的是 L3 20G 预算（gate2-saturation 跨档表）。
- /data 清理后 180G free（ledger 2026-09-04 D1 授权）；extent 文件 64G 稀疏、1024 槽。

## summary

### 1. 约束容量模型（写→query 保真需求 × L3）

**定义**：令链字节 `C` ≈ 541.5MB（KV 490MB + mamba 51.5MB）。L3 水位 GC 在 `used > max_size×0.9` 时回收 LRU 槽。因此"写入后到 query 前链不被回收"的充分条件是**同时存活的链数 N 满足 live 字节 < 水位**：

```
N × C  <  max_size × 0.9
N       <  max_size × 0.9 / C
```

| MAX_SIZE | 水位(×0.9) | 可存活链 N | 能否支撑 mamba 池压力 |
|---|---|---|---|
| 20G（现状） | 18G | ~34 | 否（=gate2 实测 32-34 即 recycle 起点）|
| 40G | 36G | ~68 | 部分（68/106 池）|
| 64G（=默认 file） | 57.6G | ~108 | **是（106/106 边缘）** |
| 70G+file_size↑ | 63G+ | ~118+ | 是（带余量，需 file_size 上调）|

**写→query 保真需求的物理表达式**：一个在 t_w 写入、t_q 查询的链要存活，其占的槽必须是 [t_w, t_q] 窗口内 GC 的 LRU 幸存者。水位模型下，只要全窗口累计存活链数 < 水位对应 N，就 **0 recycle、全幸存**（gate1 实证）。

### 106-slot 真饱和在本机是否物理可达 —— 诚实回答

**可达，但需两个条件同时满足（当前都不满足）：**
1. **L3 ≥ ~57.4GB live**（106 链 × 541.5MB = 57.4GB），即 `max_size×0.9 ≥ 57.4G` → **MAX_SIZE ≥ ~64G**。当前 20G → 需 3.2×。180G free 磁盘放得下（文件稀疏，真实占用=live 字节）。
2. **负载要产出 ≥106 个同时存活的 DISTINCT 链**（设备 mamba 池 106 槽 ≈ 106 个 checkpoint）。当前 gate2 驱动 `write_chain_spec` 每 session 只写 L0..L3 = 4 条 distinct 链，K 档只产出 K×4 distinct、且设备池 LRU 只实时存活 ~32-34 → **驱动也达不到 106**。

因此：**MAX_SIZE 20G 下 106/106 绝对不可达；MAX_SIZE≥64G + 106-distinct 链负载下可达（但 64G 在 57.4G/57.6G 水位边缘，建议 70G+file_size↑ 或精确 106 链控制）。** 这是本设计把"可达性"做成显式裁决项（见 open_issues ②）而非含糊过去的理由。

**替代：缩小 mamba 池使饱和在当前预算下可达。** 若 `max_mamba_cache_size` 106→32（launch 配置，非代码），32 链 × 541.5MB = 17.3GB < 18G 水位 → **20G 预算内真 32/32 池饱和可达**，只需 K=8×4 的轻负载。这把 gate-2 意图（mamba 池压力）在最小资源下真实压满。

### 2. 负载重设计选项（3+，各带 trade-off + 适用判据）

**选项 A — 负载局部性收窄（写后尽快复核，写→query 累计写量 < L3 预算）**
- 结构：write→immediately-verify 交替，单链写后立即同链 restore，live 窗口 ≤N（如 ≤30 链），使写→query 间累计存活字节恒 < 水位 → 0 recycle。
- trade-off：干净隔离 L3 容量与 restore 保真（能在 20G 下测 restore 正确性），但**不测 L3 长窗驻留、不测池压力**（live 集小 → 池不饱和）。
- 适用判据：当用户接受"gate-2 只验 restore 保真、不验池饱和"时；最快、最省。
- 用途：作为 Phase 0 的保真基线（见 §4）。

**选项 B — 饱和度口径重定（真 106 不可达/太重时的替代度量）**
- 结构：不改绝对饱和目标，改测**池压力退化曲线**与**命中平直性**：
  - 压力序列：mamba evictable/used/available vs pool fill 分数（`evictable/pool_size`）；
  - eviction events/窗口：`hicache_dropped{pool=mamba}`、`extent_recycle`/窗口（t38c `evt=extent_recycle`）；
  - 命中退化曲线：L0 exact-restore ratio vs pool fill 分数。
- 判据：**命中随 fill 升高应平直（无 cliff）**；在机器可及的各 fill 档（如 fill 分数 0→0.3→0.6→0.9）L0 exact-restore ≥0.95 即过。
- trade-off：不压到 106/106，但把"是否 cliff"与负载形状、绝对容量解耦；对 12-turn agent_driver 负载形状免疫。
- 适用判据：当用户认为"真 106 饱和不值得 3.2× L3 + 重负载"时。

**选项 C — L3 尺寸与验证判据（直接修根因）**
- 结构：MAX_SIZE 升档（40G / 64G / 70G+file_size）+ 断言 `extent_recycle→~0` + `kv_hit_pages>0` + L0 exact-restore ≥0.95。
- trade-off：最直接命中根因（预算 vs 负载不匹配），代价是更大的 L3 + 相应负载。40G 档配合现驱动即可验证"提预算是否消 cliff"。
- 适用判据：作为 Phase 0 首选（§4 Step 1），也是任何后续饱和路径的必做前置。

### 3. 验收口径钉死

- **主判据 = exact same-chain restore ratio（phase-B L0-restore 行）**，非原始 aggregate。依据：12-turn agent_driver 形状把原始 aggregate 天花板压 ~0.83（零 eviction 也到不了 0.95，gate2-saturation followup #3）——必须用 exact-restore 行隔离 residency 与 load-shape。
- **full-miss 定义（订正 analyzer 缺陷）**：一行 restore 为 genuine full-miss ⟺ 全部成立：
  - missing-sglext（或 `usable==0`）且 `prompt_len>1000`；
  - ttft 显著长（recompute 签名，实测 15-231s）；
  - 引擎日志 `restore_disposition ... RECOMPUTE granted=0 reason=revoked:miss`（且 `restore_recompute cause=miss`）。
  - **缺陷**：`gate2_analyze.py` 的 `full_miss(<100)` 用 `usable<100` 计数、missing-sglext 行被 `not isinstance` 提前跳过 → 恒 0。**设计口径改为显式计 missing-sglext 行（pl>1000 + revoked:miss）**，不再依赖 `full_miss(<100)`。
- **各 K 档通过线**（以 L0 exact-restore 为主）：
  - 每档（K=4/8/16 或 fill 档）`L0 exact-restore ratio ≥ 0.95`；
  - 每档 genuine full-miss ≤ 容忍（建议 0，或 ≤1 且非系统性）；
  - **跨档无 cliff**：L0 ratio 随压力不显著下降（Δ≤2pp 或平直）。
  - 原始 aggregate 仅作环境/负载形状参考，不作门。

### 4. 可执行计划（获批后照跑；现不执行）

**Phase 0 — 预算修复验证（最便宜，先做）**
- config：`MAX_SIZE=40G`（/data 180G free，安全；watermark 36G 支撑 ~68 链 live）。
- 负载：沿用现 gate2 驱动（K=4/8/16，write 4 / read 8）。现驱动 live 集 ~34 链 × 541MB ≈ 18.4GB < 36G → 预期 **0 recycle**。
- run 清单：`gate2-run2.sh --tag budget40k{4,8,16}`，fresh namespace `/data/l3/p2io-gate2-b40-*`。
- 判据：`extent_recycle` 计数 → ~0；`kv_hit_pages>0`（storage_hit>0 行出现）；L0 exact-restore 上升。**验证根因修复**。

**Phase 1a — 真 106 池饱和（若用户裁决走真饱和）**
- config：`MAX_SIZE=64G`（保持默认 64G file）+ 负载升级产出 ≥106 distinct 链（K≥27×4，或多 level）。
- 判据：fill 分数达 ~1.0（evictable≈pool）；L0 exact-restore ≥0.95；recycle→~0（边缘需精确 106 链或 file_size↑）。
- 代价：3.2× L3、重负载、长 run。

**Phase 1b — 池压力退化曲线（若用户接受替代口径）**
- config：`MAX_SIZE=40G`，驱动分档递增 distinct 链数（如 16/32/48/64 → fill 0.15→0.3→0.45→0.6）。
- 判据：L0 exact-restore vs fill 分数平直；无 cliff；每档 ≥0.95。

**Phase 1c — 缩小池真饱和（最省，配置变更）**
- config：`max_mamba_cache_size=32` + `MAX_SIZE=20G`（现状预算）+ K=8×4 distinct 链。
- 判据：fill≈1.0（32/32），L0 exact-restore ≥0.95，recycle→~0。
- 注意：改的是被测产品配置（池尺寸），非默认 106；机制（池压力→restore）在 32 槽档同样真实压满。

**工具修正（仅 analyzer，同 Phase 0 一并）**：`full_miss` 改为显式计 missing-sglext + pl>1000 + revoked:miss；加 `pool_fill_fraction`、`extent_recycle/窗口`、`L0_restore_vs_fill` 输出。**现不写，获批后改**。

### 5. 范围外（明确不设计不实现）
- **D3**：GC 淘汰策略保护 anchor / mamba TRAILING cliff（51.5MB mamba 单 extent 被 LRU 先回收即整链归零）——**明确不设计不实现**，留作产品裁决/后续 gate。
- **引擎代码零改动**：只动 launch config（MAX_SIZE/file_size/max_mamba_cache_size）与测试脚本/analyzer。
- **FBE 保留不撤**（已修 write-side durability 缺口，42%→33% full-miss 已证部分有效）。

### 6. 开放裁决项（给用户/专家）

1. **≥95% 是否只算 exact-restore 行**：原始 aggregate 被 12-turn 负载形状压到 ~0.83 天花板，≥95% 只在 exact same-chain restore 行可达。→ 请确认主判据 = L0 exact-restore（本设计默认如此）。
2. **106-slot 真饱和不可达时接受什么替代口径**：物理上 106/106 需 MAX_SIZE≥64G + ≥106 distinct 链负载。若太重，接受选项 B（fill 分数 + 命中退化曲线平直性）还是选项 A（保真优先、不压池）？
3. **是否缩小 max_mamba_cache_size 使饱和物理可达**：106→32 可在 20G 预算内真 32/32 饱和（最省）。但测的是非默认池尺寸——是否接受以 32 槽档作为"池压力"的代理验证？
4. **MAX_SIZE 档位**：40G（安全，~68 链）还是 64G（=默认 file，~108 链，106 饱和边缘）？是否允许 file_size↑（128G）换取余量？

## followups

1. **Phase 0 优先级**：MAX_SIZE 20G→40G 重测是验证"根因=预算不匹配"的最便宜一击，建议获批后最先执行；若 40G 下 recycle→0 且 L0 restore 显著上升，则根因闭环再确认。
2. **analyzer 缺陷**：`full_miss(<100)` missing-sglext 跳过缺陷在 Phase 0 落地时一并修正（只改分析口径，不改生产代码）。
3. **gate3+（产品侧）**：GC 保护近期 restore/durable anchor、mamba TRAILING cliff、FBE firing 计数（pool 是否真压到 host mamba LRU）——均范围外，留后续。
4. **restore-side L3 读回缺陷**：FBE 后遗留 33% full-miss（K16 L0 16/48）根因曾定位 restore 查回 0；**若 Phase 0（40G、0 recycle）下 L0 exact-restore 仍 <95%，则该 restore-side 缺陷独立于容量，需按 upstream-maintenance §3 借 main（候选 #37503）处理**——这是 Phase 0 的判定分叉点。

## open_issues

- 106-slot 真饱和"物理可达但需双条件（MAX_SIZE≥64G + ≥106 distinct 链）"——reachability 已给诚实结论，最终选哪条路需用户/专家裁决（见 §6 ②③④）。
- 现值链字节 541.5MB（KV 490 + mamba 51.5）来自 gate1 量级 + 任务给定；如需更精确可后续从证据日志按链核对（本轮不改）。
- 环境：本机未动 3090（无 run、无启停、无生产代码改）。设计仅此文档。
