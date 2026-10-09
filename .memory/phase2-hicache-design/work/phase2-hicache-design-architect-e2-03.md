# phase2-hicache-design architect e2-03（p2-0-03 N-agent 负载 driver 设计）

## status
done

## artifacts
- 交付物：`/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/driver-design.md`
  （已落盘，未 commit 未 push；p2-0-05 实现与 p2-0-06 解析的唯一依据）
- 本报告：`phase2-hicache-design-architect-e2-03.md`

## evidence
- plan.md p2-0-03 行 + Context Boundary 03 + Missing Information 5-10（已逐一结算：
  MI5 执行身份 root、MI6 冻结参数沿用 launch 默认、MI7 K=1 新 driver 重跑、
  MI8 只记录不判、MI9 64 = 线程模型+RAM 核算、MI10 payload 复用策略见 §1.4）
- 01 产出 metric-availability.md（12 指标矩阵 + D1-D6；R7 状态变更见下）
- 02 产出 log-field-inventory.md（探针 7 事件、mem_quota 链 inert 结论、
  "HiCache prefetch %s" 格式串 = info 级 unified_radix_cache.py:2104-2112）
- fetched-hicache-upstream.md（#32724 FCFS finalization lag、write_back 逐出落盘语义）
- micro_qwen35.py 全读（1365 行）→ 9 个复用点映射（§4.3）
- gen_qwen35_payloads.py 全读（322 行）→ 前缀嵌套实证
  （prefixes[(s,k)] = blocks[(s,0..k)] 累积，L0⊂L1⊂L2⊂L3；blocks[0]=17,400 为
  同 session 公共前缀）
- 本机 meta.json 实测：L0-V1 service 20,911 / L1 27,854 / L2 34,855 / L3 43,556 /
  BB1 20,953 / BB2 27,854 / BB3 34,855
- tester e1 报告 340-465：t38rs3/t38sb 实证 host_total=49,153、device=32,768（evict
  48-52K 全轮转反推）、restore TTFT 21.3s、input_delta=47、三流水交错模式、drvC
  run-1 full recompute 先例（input_delta=21005 / load_back 4,480 页）

## summary

### 结论
K=1/8/16/32/64 全部可行，单 driver 进程 + K 线程 + 进程内 HTTP client；
不重生成 payload（486 池 + 模式化复用）；L2/L3 payload 冷不可行（> 32,768 池）→
R3 降级规则为必须；L3→H wait 由 01 判定的 absent 升为 derived（探针 + info 级
引擎日志配对，D6 关闭、D2 降级为可选）。

### 4 个 K 可行性表摘要（device 32,768 / host 49,152 / 31G RAM / mamba host 8.2G 固定）
| K | agents/session | turns | distinct payload（复用） | 引擎队列 | 墙钟预算 | 结论 |
|---|---|---|---|---|---|---|
| 8 | S1..S8 ×1 | 12 | 96（唯一） | ≤8（≈0） | 60 min | 可行，恢复多命中域（~9 链 8G < 20G） |
| 16 | S1..S16 ×1 | 12 | 192（全部 L 池） | ≤16（≤8） | 90 min | 可行，L3 压力起点（~17 链 ≈ 20G 临界） |
| 32 | ×2 | 12 | 192（复用 1.6×） | ≤32（≤24） | 120 min | 可行，L3 轮转域，R3 生效 |
| 64 | ×4 | 12 | 192（复用 3.2×） | ≤64（≤56） | 180 min | 可行：硬占用 15-17.5 GiB < 31 GiB（引擎 13-15 + driver 0.4-0.5 + OS 1-2），余量 ~13G 页缓存；client 超时放大至 1,200s |

请求级硬边界：L0 (20,911)/L1 (27,854) 冷恒可行；L2 (34,855)/L3 (43,556) 冷不可行，
条件可行阈值 2,087/10,788 前缀命中（session 基础前缀 17,400 即可满足）；
max-running-requests=8 → 引擎队列即背压。

### 进程/线程决策
单 driver 进程 + K agent 线程 + 1 metrics 采样线程 + join 写锁；请求路径改进程内
流式 SSE（替换 udg_client_l3 curl 子进程——64 子进程 ≈ 4-5 GiB 不可行）。64 进程
模型 ≈ 27 GiB 硬占用 → 否决。RAM：driver 0.4-0.5 GiB（K=64）。

### join.log schema 要点（06 唯一依据）
v2 行新增：agent_id / turn / turn_kind(grow|restore|downgrade) / phase
(warmup|steady|drain) / session / level / variant / ts_sched / new_tokens_est；
v1 全部字段保留（ts_start/ts_end/rid/三档 hit/delta 字典）。**并发归因注记**：
K≥8 时 per-turn 计数器 delta 叠加其他请求 → per-request 精确量一律用 sglext
（new_tokens_est），计数器仅 run 级交叉。新增 mid-run-metrics.txt（JSONL，
--snapshot-interval 5s）承载 R3/R4/R8-R12 的 gauge/直方图时序。

### micro_qwen35 复用映射数
9 个复用点（BASE/端口 :99；metrics 机制 :177-235；extract_sglext :238-291；
payload_est_tokens :313-323；write_join_row :489-519；docker_cat+read_probe_events
:403-444；evidence 状态组装 :1153-1169；parse_args :901-989；verdict/runs.csv/
END-BANNER :1301-1337）+ 1 改造点（run_client :337-341 → 进程内 client）+
1 弃用（状态机 :562-896，P2-0 只记录不判）。

### 其他要点
- 轨迹：agent = session 家族（L0⊂L1⊂L2⊂L3 前缀嵌套实证）→ agentic loop 语义天然
  成立；12-turn 模板 = 3 变体环（L0→L1→L2→L3）+ 3 restore 环间；规则 R1-R5
  （R3 降级 = L2/L3/BB3 前查同 session cached_tokens ≥ 阈值，否则降 L0-V1）。
- K=1 基线 = 同一 driver --agents 1 session S1（= P session，链基有效），记录路径
  与 K≥8 全统一，不复用 Phase-1 证据。
- b15 配合：L3→H wait 派生链 = "HiCache prefetch success req=X"（info 日志）→
  pa_lb_init(rid,ms) → pb_load_done(ms)；driver 只记 rid + 全 run 探针窗口读取，
  不读引擎日志。01 R7 absent → derived（D6 关闭、D2 降级可选）。
- 07 首跑必须先验：L2 冷请求的引擎行为（挂起 vs 拒绝）决定 R3 必要性强度。

## followups
- p2-0-05：按 driver-design.md §2.2 轨迹规则 + §6 schema 实现 agent_driver.py；
  K=2 smoke 判据含 join.log agent_id 行（schema v2）。
- p2-0-06：按 §6 join.log v2 + mid-run-metrics.jsonl + §7 探针/日志配对解析；
  遵守 §6.1 并发归因注记（per-request 用 sglext 派生量）。
- p2-0-07：首跑补实证三项——device_total=32,768 / host_total=49,153 实测确认、
  L2 冷请求引擎行为、mid-run gauge 实际更新周期秒数（01 open issue 3）。
- p2-0-09：free -m 采样序列 + 必要时 --turns 8 降载（设计内建回退）。

## open_issues
1. --stagger 默认 1s vs 0（同步风暴）：07 试 1s，09 首 run 可试 0。
2. L2/L3 冷不可行的引擎行为未实证（挂起/拒绝/分块）——R3 必要性强度的前提，
   07 首跑验证；若引擎拒绝而非挂起，R3 可放宽。
3. K=1 基线用 S1（P）——链基可比性已论证（尾 46 语义不变），待 tester 执行确认。
4. R7 秒级派生依赖引擎日志 asctime（SGLANG_LOG_MS 未冻结启用）；亚秒精度仍需
   P2-1 探针（D2 降级为可选，不阻塞 P2-0）。
5. in-process client 选型（urllib vs httpx）由 05 定，schema 不受影响。
