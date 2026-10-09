# p2-0-06 coder-e3 报告（12 项指标采集/解析脚本实现）

- 任务: phase2-hicache-design / p2-0-06（Batch 3 并行，实现）
- agent: coder（epoch 3，后缀 -06）
- status: done

## 1. status

**done**。两个交付文件已落盘，`py_compile` exit 0，合成自测 13/13 字段非空（验收要求 ≥10）、
14/14 断言通过。未连引擎（按任务边界，真实产物解析归 p2-0-07 tester 端到端验证）；
只写文件，未 commit 未 push。

## 2. artifacts（交付物）

| 文件 | 内容 | 说明 |
|---|---|---|
| `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/metrics_schema.py`（新建，264 行） | 12 项字段表元数据（13 行：quota 项拆 denied/compressed 两个子状态，与 01 矩阵布局一致）、指标名常量、7 探针 evt 清单、04 §3.2 全部公式纯函数（tolerance / compression_ratio / recompute_fraction / partial_restore_present / fallback_recompute_event / compression_band / classify_event）、A/B/C/D 类与机制常量 | 字段表唯一权威源：collect_metrics、p2-0-10 归因、p2-0-11 基线报告读同一张表 |
| `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/collect_metrics.py`（新建，930 行） | 四源解析（join.log v2 JSONL / mid-run-metrics.txt JSONL / 引擎日志 8 签名行级 grep / b15 探针 7 evt）+ 12 字段计算 + 04 归因字段（E_run/A_run/R_run/S_run、compression_ratio、class_counts）+ per-rid 事件表（A/B/C/D + mechanism + conf + refs 行号）+ JSON/CSV 输出 + `--self-test` 合成数据管道自测 | CLI：`--run-dir --engine-log --probe [--out --out-csv --out-events --window-ms --page-size]`；join.log 缺失为唯一硬错误（exit 2），其余源缺失 → 字段 null + D1-D5 原因标记，不硬造，exit 0 |

## 3. evidence（验证）

全部在 `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/` 下执行：

```
$ python3 -m py_compile metrics_schema.py collect_metrics.py
PY_COMPILE_EXIT=0

$ python3 collect_metrics.py --self-test
self-test synthetic artifacts kept at: /tmp/p2b0-collect-selftest-jivp_bo4
  agent_turns_per_s      0.2 ok       p95_round_interval_s  10.0 ok
  active_width           2 ok         slot_refill_gap_s     5 ok
  restore_served_tokens  4480 ok      recompute_served_tokens 8520 ok
  l3_to_h_wait_s         1.2 ok       h_to_d_wait_s         0.2 ok
  device_free_tokens     14250.0 ok   device_evictable_tokens 650.0 ok
  device_locked_tokens   218.0 ok     quota_denied_tokens   10 ok
  quota_compressed_ratio 1.0 ok
  non-null fields: 13/13
self-test PASS: 13/13 non-null, 14/14 checks OK,
  attribution={compression_ratio: 1.0, recompute_fraction: 0.44, band: full,
  class_counts: {A:0, B:1, C:0, D:0}}
SELFTEST_EXIT=0

$ python3 collect_metrics.py --run-dir <synthetic> --engine-log ... --probe ...
  --out report.json --out-csv metrics.csv --out-events events.csv
CLI_EXIT=0（JSON/CSV/事件表三路输出齐全）

$ # 缺失源路径（仅 join.log，无 mid-run / 引擎日志 / 探针）→ 字段 null + 原因，exit 0
$ python3 collect_metrics.py --run-dir /tmp/p2b0-nosrc
slot_refill_gap_s   None  missing  D1: kv_used_tokens series absent (<2 snapshots)
l3_to_h_wait_s      None  missing  D2: no 'HiCache prefetch success' line or no pa_lb_init pair
h_to_d_wait_s       None  missing  load_back_duration_seconds absent ...
device_free/evictable/locked None missing（gauge 缺失各自原因）
quota_denied_tokens None  missing  ...(budget-gate denials unobservable, D3)
quota_compressed_ratio None missing  E_run=0 or probe/counter sources absent (D4)

$ python3 collect_metrics.py --run-dir /tmp/p2b0-empty; echo $?
ERROR: join.log not found in /tmp/p2b0-empty
2（join.log 缺失 = 唯一硬错误）
```

代码质量扫描：无跨距正则（56-regex-safety，仅一处行锚定固定宽度 `LOG_TS_RE`，无有界重复）；
无 TODO/FIXME/XXX；无调试 print（stdout 仅输出 JSON 报告与自测表）；全文件 ASCII。
任意外 cwd 运行验证通过（`python3 /path/p2-0/collect_metrics.py`，sys.path 含脚本目录）。

## 4. summary（合成自测 12 字段非空/缺失明细）

合成样例 = 3 行 join.log v2（2 agents，含 restore 行）+ 4 快照 mid-run-metrics（含
kv_used_tokens 谷 105→110s）+ 2 行引擎日志（prefetch success + Prefill batch）+ 3 探针事件
（pa_lb_init/pb_load_submit/pb_load_done，rid=r-2 关联）。**13/13 字段非空**：

- **非空（13 个）**：agent-turns/s=0.2、p95 round interval=10.0s、active width=2（gauge max，
  设计 K 在 aux）、slot refill gap=5.0s（候选派生谷宽，**待定/D1**）、restore-served=4480
  （Σ join storage_hit，计数器 Δ 交叉在 aux）、recompute-served=8520（Σ join new_tokens_est，
  mode=input Δ=3520 交叉在 attribution）、L3→H wait=1.2s（prefetch success 行 ↔ pa_lb_init
  rid 配对）、H→D wait=0.2s（直方图 sum/count 均值）、device free=14250 / evictable=650 /
  locked=218（max_total−available−evictable−used 逐快照残差均值）、quota denied=10（计数器
  Δ）、quota compressed ratio=1.0（E_run=4480/A_run=4480，band=full）。
- **缺失源时的 null+原因（不硬造）**：D1（slot refill gap 无 kv_used 时序）、D2（L3→H 无
  配对）、R8（直方图未入快照）、R9/R10/R11（gauge 缺失）、R12a（计数器缺失，D3 覆盖说明）、
  R12b（E_run=0，D4）——全部带原因标记，exit 0。
- **事件分类**：合成 restore 行 r-2 → class B（E_r=4480 全交付但 D_r=5000 超出 tol → L3 部分
  交付型回退，04 §4 边界成立）、mechanism 2/2b、conf=confirmed、refs=probe:1;log:1；缺失
  探针时 restore 行自动落 D 类候选（conf=weak，weak 签名语义）。

## 5. 与 04 公式对齐说明（attribution-design §3.2 / §4 逐项落实）

- 公式函数全部按 04 §3.2 原文实现于 metrics_schema.py：`tol = max(0.05·E_r, 2·PAGE)`（PAGE
  默认 1 = 本 checkout CUDA 默认，overrides.py:2666 实测；04 决策点 3 的启动实值待 07 记录）、
  `compression_ratio = A_run/E_run`（E_run≤0 时 None）、`recompute_fraction = R/(R+S)`、
  `0 < A_run < 0.95·E_run`、`comp_ratio < 0.95 且 R_run ≥ max(1000, 0.05(R+S))`。
- A_run 首选 = Δ load_back_tokens_total{pool="kv"}（04 gauge 7），缺失回退 Σ pb_load_done
  （A_run_source 标注）；E_run = Σ pa_lb_init.host_hit_length；窗口 W = 5,000ms 默认
  （--window-ms 可调，07 按 pa→submit Δt 分布校准）。
- per-rid 事件表按 04 §6 schema 输出（rid/class/mechanism/conf/t_pa_lb_init_ms/E_r/A_r/D_r/
  R_r/refs），D 类 = restore 行无 pa_lb_init 且 recompute>0（机制①候选，conf=weak，occupied=
  采样与 budget_limit=0.5×host 池在 aux.occupied_sampling 供升级"高度可能"）；B 类 ②/②b 并类
  （b15 面不可分，04 局限 5）；C 类 decode 模式有 load_back failed 行 → conf 升 confirmed。
- run 级聚合字段（E_run/A_run/R_run/S_run/compression_ratio/recompute_fraction/band/
  partial_restore_present/fallback_recompute_event/class_counts）全部在 report.attribution
  输出，供 p2-0-10 直接取用。

## 6. followups（留给 07 的注意点）

1. **探针文件获取**：本脚本只收本地文件路径；07 需先 `docker exec <c> cat /tmp/b15-probe.log
   > <run>/b15-probe.log`（探针在容器内）再指向它。未提供时 R7/R12b/事件表降级（null+原因），
   exit 0。
2. **mid-run-metrics 直方图**：R8 依赖快照含 load_back_duration_seconds_sum/count/bucket 键
   （micro_qwen35 的 METRIC_CUM/GAUGE 清单不含直方图，05 若未扩展快照则 R8 null）——07 首跑
   核对 05 快照内容，缺则按 null+原因处理（或 05 补录）。
3. **page_size 与 host 池实值**：tol 与 budget_limit 用到 page_size（默认 1）与 host 池
   （gauge 缺失时按 49,152 默认）；07 从引擎启动日志记录实际值后，用 --page-size 覆盖复核。
4. **窗口 W 校准**：aux.r7.pa_to_submit_deltas 输出 pa_lb_init→pb_load_submit Δt 分布（04
   §3.3 口径），aux.r7.pa_to_load_done_deltas 输出 pa_lb_init→pb_load_done（H→D 时长探针侧
   交叉）——均供 07 定稿 W（当前默认 5,000ms）。
5. **locked 语义实证**：R11 负值快照会记入 note（不变式违例数），07 对照 OOM 现场
   available_and_evictable_str 形态实证（01 R11 待办）。
6. **引擎日志 asctime 秒级**：L3→H wait 带 ±1s 分辨率误差（note 内标注）；需毫秒精度时
   SGLANG_LOG_MS=1 属引擎配置变更，P2-0 内不启用，登记 P2-1。

## 7. open_issues

- 05（agent_driver.py 并行实现中）的快照字段集合未定稿时，R8 的真实可用性未知——脚本已做
  双路径（快照含直方图则解析，不含则 null+原因），不阻塞。
- mamba 池 locked 无总容量 gauge（D5）：R11 仅覆盖 full 池，mamba locked 不派生（note 说明）。
- 合成自测的引擎计数 Δ（mode=input 3520）与 join Σ（8520）不一致是快照窗口设计使然
  （首快照在 run 中途），真实 run 的首快照在启动时（Δ≈run 总量）；07 用真实产物核对口径
  （K=1 时两者应一致，t38rs3 先例 input_delta=47）。
