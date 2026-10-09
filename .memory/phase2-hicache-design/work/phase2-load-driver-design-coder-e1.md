# phase2-load-driver-design-coder-e1 — ③④ 驱动设计与实现（用户纠正后口径）

- Agent: coder
- Epoch: 1
- Date: 2026-09-07
- Scope: 设计并实现实验③（capacity curve）与实验④（parked-session scale）两个 24052 测试驱动；纯测试 harness 资产，零产品代码改动、零 push。② 由 tester 并行在 24052 跑，本任务未接触 GPU run。
- 依据：`phase2-cap-scout-e1.md`（事实基线，未重复侦察）+ 本任务 dispatch 载明的用户纠正口径。

---

## status: done

## artifacts

| 文件 | 说明 |
|------|------|
| `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/3090-dev/gate3_capacity.py` | 实验③：N∈{4,6,8} × 50-80K 并发 capacity curve 驱动（420 行） |
| `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/3090-dev/gate3_parked.py` | 实验④：100-1000 parked-session + 随机 resume 驱动（635 行） |
| `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-load-driver-design-coder-e1.md` | 本报告 |

## summary

### ③ 驱动 `gate3_capacity.py`

**参数（全部 CLI 可调）**：
`--agents 4|6|8`、`--tier 50k|80k`（对应 50000/80000 token 历史）、`--warm-repeats`（每 agent warm 轮数）、`--cold-max-new/--warm-max-new`（completion 长度）、`--stagger`（COLD 错峰秒）、`--client-max-time`、`--snapshot-interval`（gauge 采样）、`--evidence-dir`、`--dry-run`、`--served`。

**流程**：
1. 每 agent 线程（`--agents` 个，错峰启动）COLD 发整段 50K/80K 历史（`build_history_prompt` 复用 gate2_warmctx 式 tokenizer 精确截档 + 每 session 唯一 marker 前缀 → 独立 radix 分支）。
2. 线程自由运行 warm 轮：历史 + 上轮 assistant 回复 + 短新 delta（~几十 token），无 barrier（TCP backpressure 天然并发控制）。
3. 每请求记录 engine 计数器 delta（prefill_effective_tokens 的 input/device_hit/host_hit/storage_hit mode）作独立交叉验证。

**输出 schema**（runs.csv / join.log 行，兼容 gate2_analyze／gate2_load／gate2_warmctx 口径）：
`agent_id, turn, turn_kind(cold|warm), round, ts_start, ts_end, ttft_s, wall_s, http, finished, finish_reason, rid, rc, history_tokens, prompt_len, completion_tokens, cached_tokens, cached_device, cached_host, cached_storage, prefill_input_delta, prefill_devicehit_delta, prefill_hosthit_delta, prefill_storagehit_delta, output_field, output_sha16`。

### ④ 驱动 `gate3_parked.py`（用户纠正口径实现）

**参数**：`--sessions 100|500|1000`、`--build-tier 50k|80k`、`--rounds`、`--active`（默认 8 = 引擎 c8；可调节点）、`--park-min/--park-max`（秒级随机 park 窗口）、`--pick-lam`（turn 级 cooldown 均值）、`--obey-ac`（客户端并发封顶）、`--idle-wait`、`--round-gap/--build-gap`、`--build-client-max/--client-max-time`、`--snapshot-interval/--coarse-interval`（双速率采样）、`--l3-backend-dir`（L3 extent 物理足迹）、`--seed`、`--dry-run`。

**parked 语义（严格按用户裁决，无 scheduler WAIT / 无 pause_generation）**：
- build 阶段顺序 COLD 预填 S 个 50-80K session 前缀（0 基 session id，与 resume 同 seed → 同一 radix 分支）。
- turn 循环：`Sched.pick(now, turns)` 从**到期集合**（never-run 优先，其次按 park 窗口 + turn cooldown 到期）中选 ≤ active 个 session → 各发 1 个 WARM 形 turn（历史 + 上轮 assistant + delta）→ 完成后立即 retire（离开 active set，GPU 缓存足迹靠其他 active session 的自然 LRU/驱逐逐出到 Host/L3；历史保持可达）。
- 再到期条件 = **墙钟 park 窗口已过**（`now - retired_at >= park_window`，窗口每次 retire 随机 `uniform(park_min,park_max)`）**且 turn cooldown 已过**（`turns_so_far - turn_count >= eligible_in_turns`，服从 `pick_lam` 的几何分布 = "错过了其他 session 忙的几十轮"）。
- 从不去调任何 pause/wait 端点；不人为制造 headroom 缺口。

**输出 schema**：build 与 resume 行同表。build 行 `turn=0, turn_kind=build`；resume 行 `turn_kind=resume, round, turn(1..), age_at_wake_s`（= 距**上一轮结束**的秒数，即该 session 真实 parked 时长），另带 per-request `cached_device/host/storage`、`history_tokens`、`prefill_*_delta`。
配套 `runs.csv`、`mid-run-metrics.txt`（双速率 gauge 采样）、`turns/{build,turn}/s<id>/t<turn>.*` 工件、`verdict.json`（sessions/active/rounds/requests_total/requests_ok/busy_retries/run_dir）。

**与引擎 / metrics 对接（全部现成口径，无新埋点）**：
- 引擎：普通 `/v1/chat/completions` SSE（stream:true），`common.run_client_inproc`（in-process SSE 客户端，已在 24052 `/root/p2-0/common.py`）。
- 每请求 cache-hit 源：SSE 体内 `cached_tokens_details{device,host,storage}` + `usage.prompt_tokens`。
- 计数器交叉验证：`/metrics` 的 `sglang:prefill_effective_tokens_total`（labels mode∈{input,device_hit,host_hit,storage_hit}）请求窗口 delta。
- Host（L2）占用：gauge `sglang:hicache_host_used_tokens` / `hicache_host_total_tokens`、子池 `hicache_kv_host_usable_tokens` / `hicache_mamba_host_usable_tokens`。
- 池水位：`kv_used/evictable/available`、`mamba_used/evictable/available`、`max_total_num_tokens`、`num_running_reqs`、`num_queue_reqs`。
- L3 extent 物理足迹：`--l3-backend-dir` 指向引擎存储目录，用 `os.stat().st_blocks×512` 读 `hicache.data*` 的**物理**占用（extent 文件 sparse，`ls -l` 逻辑字节无意义——源码佐证 `extent_file_backend.py:245-246 _data_path=hicache.data{suffix}`、`p2io-scout-backend-e1.md:124` 单文件预分配 sparse）。
- recycle/GC：`evicted_tokens_total`、`hicache_backup_tokens_total`、`load_back_tokens_total`、`backuped_tokens_total`（L3 host→storage 写）。驱动侧已记录 session-id/turn/时间戳以关联全部上述量。

### 与 scout 断言（无现成驱动）的对照确认
- scout Q4：**无现成③驱动**（4/6/8 × 50-80K 并发）→ 本 epoch 造出 `gate3_capacity.py`。
- scout Q5：**无现成④驱动**（100-1000 parked + 随机 wakeup；暂停端点只有全局引擎级 `/pause_generation`）→ 本 epoch 造出 `gate3_parked.py`，且严格未用 scheduler WAIT/pause 端点——按用户纠正口径，parked = turn 完成后自然离开 active set + 自然驱逐，靠 `--park-min/--park-max` 秒级窗口 + `--pick-lam` turn 级 cooldown 实现随机 resume。
- 观测口径（scout Q3）：确认全用现成 Prometheus gauge/counter，无新计数器、无 TTL 修改。

## evidence（所有命令实跑，结果已观察）

1. `python3 -m py_compile gate3_capacity.py gate3_parked.py` → `[1] py_compile OK`（两文件均通过）。
2. `python3 gate3_capacity.py --dry-run --agents 4 --tier 50k` → `DRY_RUN_OK agents=4 tiers=[('50k',50000,...),('80k',80000,...)] warm_repeats=3`（tokenizer-unavailable 提示为正常——本地 dev 无 transformers，真卡 24052 conda env 有；dry-run 其余逻辑通过）。
3. `python3 gate3_parked.py --dry-run --sessions 50 --active 4 --rounds 2 --park-min 5 --park-max 20 --pick-lam 2.0` → `DRY_RUN_OK ... schedule_pick_ok=True`。
4. Sched 单元不变量测试（纯逻辑，无引擎）：
   - active 封顶：100 轮/214 turns 从未超过 active=4；
   - 无饥饿：30 sessions / active=4 / 200 turns 全部被选到；
   - park cooldown 尊重：turn 级 `cooldown_violations=0`；
   - 200 sessions / active=8 长 churn：全部播种、max_turns≤12 无 runaway。
5. `common.extract_sglext` SSE 解析测试：合成 body → `cached_tokens_details{device,host,storage}` 与 `usage.prompt_tokens` 正确读出。
6. 两驱动 mock e2e（stub HTTP 传输 + 模拟引擎 SSE）：
   - capacity：3 agents × (1 cold + 2 warm) = 9 行，cached_device=64030 all，history_tokens≥50000 all；
   - parked：4 builds + 8 resumes（4 rounds, active=2），build/resume session id 对齐（0 基，同一 radix 分支），`age_at_wake_s` 正确填值，`history_tokens≥50000` all；
   - 最终合并跑：`FINAL_MOCK_E2E_OK capacity_rows=9 parked_rows=8 busy=0`。

### 验证中发现并修复的驱动自身 bug（均已回写）
- **B1**：`run_builds` session id 1 基 vs `Sched`/`run_rounds` 0 基 → build 与 resume 使用**不同**历史前缀（radix 不共享，resume 必全 miss）。改为统一 0 基。
- **B2**：`Sched.due()` 完全未用 `now` → `--park-min/--park-max`（秒级随机 park 窗口）为死参数；改为墙钟窗口 AND turn cooldown 双条件到期。
- **B3**：`hist_cache.get(sid, (None,None)) or build(...)` 元组恒真 → resume 历史永为 None（且对引擎发 `content:None` 必 4xx）。改为 `if sid not in hist_cache`。
- **B4**：stale 字段 `parked_at[sid]`（重命名为 `retired_at` 后残留引用）→ AttributeError；已清理。

## followups（下游验证，非本任务范围）
- 24052 真卡 run：@tester 负责。③ 建议档位：`--agents 4|6|8 --tier 64k --warm-repeats 3 --stagger 2 --evidence-dir /root/evidence-capacity-<n>`（64K=64030 ∈ 50-80K 已有基线）；④ 建议：`--sessions 100|500|1000 --build-tier 64k --rounds 60 --active 8 --park-min 30 --park-max 300 --pick-lam 1.0 --obey-ac --l3-backend-dir <引擎存储目录> --evidence-dir /root/evidence-parked-<s>`。
- 引擎按 ② 定稿配置（pool64 + graph bs8 + FP8 KV + c8；驱动 dtype-agnostic，不改引擎参数）。L3 extent dir：runner 端 `/data/l3/<namespace>`（warmctx 先例），`--l3-backend-dir` 传该路径。
- 分析脚本：前置实验的 `warmctx_analyze.py`/`gate2_analyze.py` 口径对 ③ runs.csv 基本直接可用；④ 的 session-age vs resume latency 关联 + Host/L3 occupancy 需新分析段（建议 tester 或后续 coder epoch 造 `gate3_parked_analyze.py`，本轮不造）。

## open_issues
1. 本地 dev 缺 `transformers`，tokenizer 截档的最终 token 数（50K/80K 精确档）需 24052 上首次 dry-run 或小规模 build 确认（warmctx-e1.md 已证 64K=64030 / 128K=128155，本驱动同构建函数，风险低）。
2. `--obey-ac` 默认 False（CLI 传才开启）——如需客户端并发封顶须显式传；编造 headroom 缺口不在本驱动任何路径（符合用户纠正口径）。
3. ④ 的 1000-session + 80K 档位 build 阶段是纯顺序 COLD，耗时会由真卡容量决定（128K 先例 47s/一次；50-80K × 1000 约 hours 级）——run 前需配足 `--build-client-max`（默认 1500s）与磁盘空间（extent 物理写）。