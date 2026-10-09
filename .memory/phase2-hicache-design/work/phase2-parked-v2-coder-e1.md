# phase2-parked-v2-coder-e1 — ④ parked 驱动两语义（fit/oversub）+ Gate A/B/C 对齐 + 退化曲线分析（gate3_parked.py v2 + gate3_parked_analyze.py）

- Agent: coder
- Epoch: 1
- Date: 2026-09-07
- 依据：dispatch（parked-v2）+ 用户 4 硬 Gate 权威裁决（ledger.md:2488-2536）+ architect e5 spec（work/phase2-cap-e5-architect-e1.md）+ reviewer 核验（work/phase2-cap-reviewer-e1.md）。纯测试 drive 修改，零产品代码、零 push。

---

## status: done

## artifacts

| 文件 | 说明 |
|------|------|
| `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/3090-dev/gate3_parked.py` | ④ parked 驱动 v2（两语义 + park 梯 + build-workers + Gate A/B/C 输出） |

原 635 行 → 现 ~1010 行；全部新增均为此文件。

| 文件 | 说明 |
|------|------|
| `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/3090-dev/gate3_parked_analyze.py` | ④ 分析脚本（新）：Gate B 分桶 / Gate C engine-join / oversub 退化矩阵 + 归因复核（~660 行） |
| `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-parked-v2-coder-e1.md` | 本报告 |

## summary

### 1. 两语义 CLI（用户裁决 / ledger:2473-2475 权威）

- `--mode fit`：L3-fit 正式容量测试（S 默认 100）；完整驻留语义 + Gate A/B 正式判定；expect Host/L3 高命中、recycle 最小。
- `--mode oversub`：L3 oversubscription STRESS（S 默认 500；500/1000）；**明确非"完整驻留验证"**；**允许并记录 extent recycle**；输出随超配比例的退化曲线。
- **~7** `--sessions`（默认随 mode 解析）、`--build-tier`（默认 55k，choice 含 50k|55k|64k|80k，修掉原 default=64k 非法）`、`--rh on|off`（Gate C 双臂）、`--park-ladder`、`--build-workers`、`--park-min/max`（uniform 档）、其余既有。

**禁宣称护栏（写入 verdict.json `semantic_caveats` + FORBIDDEN CLAIM 注释）**：
- oversub：`oversubscription_stress_curve` / `recycle_allowed_recorded_not_fault` / `no_claim_l3_full_park_Sx55K`。
- fit：`l3_fit_formal_capacity_test_S100`。

### 2. 新列 / 新输出文件

**runs.csv / join.log 新增列**：
| 列 | 口径 |
|---|---|
| `hit_parent_mux` | Gate B 分层标签：`GPU-resident` / `Host-ready` / `RH-staged` / `Host-ready-STAGED` / `L3-on-demand` / `miss`（classify_hit_parent，用 SSE cached_tokens_details device/host/storage + `--rh` + 该 session 是否有过 storage hit 交叉判定） |
| `rh_synced` | 1 当 parent ∈ {RH-staged, Host-ready-STAGED}（Gate C 结构参考，不作裁决） |
| `rh_flag` | 本 run 的 `--rh on/off` |
| `cohort` | 该 session 的 park 梯 cohort（HOT/MID/COLD；uniform 模式为 None；**injection bias only，analyze 按 age_at_wake_s 实测回读归类**，spec §2/OD4） |

**新输出文件（写于 run_dir）**：
- `recompute_attribution.csv`：Gate A 每次 full-history recompute 一行：
  `event, session_id, turn, ts, reason, prior_l3, hit_sum, ttft_s, evidence_ref`。
  `ts` = recompute 墙钟 epoch 秒（供 analyze 与 engine `extent_recycle` ts 时序复核）。
  driver 初判 reason 恒 `state_machine`（provisional，见 §4）；**不再用全局 eviction_observed 旗标**（reviewer D3：L2 写回/backup 增长不是"该 session L3 entry 被 recycle"的证据）。
- `verdict.json`：新增 `mode / rh / semantic_caveats / build_tier` 字段，标题行打印 frame=oversub-stress / l3-fit。
- `mid-run-metrics.txt`：coarse 采样行新增 `eviction_observed`（best-effort 全局诊断，仅供报告，不参与归因）。

### 3. park 梯（Gate B 四层制造，spec §6.2 #1 / P0）

```
--park-ladder "HOT:0-30@5,MID:120-300@30,COLD:600-2400@65"
```
- `parse_park_ladder` 解析；fit 默认 = `FIT_PARK_LADDER`（HOT=5/MID=30/COLD=65，共 100）；oversub 保持 uniform 30-300（不需梯，spec §4.2）。
- `Sched` 加 `ladder` 参数：`__init__` 按 session id 段分配 cohort；`_park_seconds(sid)` 用 cohort 带 `uniform(lo,hi)`；`cohort_of(sid)` 暴露给行打标。
- 仍守不变量：active 封顶、无饥饿、cooldown 尊重（验证见下）。

### 4. **--build-workers N**（并发 COLD build，spec §6.2 #2 / P0）

- `run_builds` 拆成 `_build_one`（单 session build）+ `--build-workers` 线程池（默认 0 = 顺序）。
- S≥500 硬依赖：顺序 500/1000×55K ≈ 2h/4h 不可行；8 worker ≈ 20/40min（spec §4.2）。
- 保留 `--build-gap`（每 worker 各自 sleep，天然错峰防瞬时同前缀驻留）。build 行仍写 join.log（session 0 基，与 resume 对齐）。

### 5. fit 判定按 Gate A+B（用户 4 Gate / ledger:2522-2535）

`gate3_parked_analyze.py --run-dir <fit-cell> --fit` 输出：
- Gate A：`avoidable_historical_recompute`（state_machine+other+never_built 合计，**=0 才合格**）；`avoidable_historical_recompute_frac`；storage_hit_session 稳定。
- Gate B fit：TTFT p50/p95/p99；>30s/>60s=0；storage-hit/session 稳定；recycle=0（`evicted_tokens_delta` + extent_recycle=0）。
- Gate C：ready-before-admission rate（engine 事件，见 §7）。
- 按 spec e5 §4.4/§3.4 语义，随 run 守卫：OFF/ON 双臂并列（同 seed/同 park 梯），`--rh` 只是打标，真正 toggle 在 launcher（`--enable-ready-horizon`），这是 dependency。

### 6. oversub 退化曲线 / Gate A attribution（spec §4.3-4.4）

`gate3_parked_analyze.py --family <evidence-dir> [--engine-logs S500=/path.log,...] [--csv out.csv]` 对每个 S 输出一行：
`L3_residency / recompute_frac / TTFT p50/p95/p99 / >30s%/>60s% / turns/hr / recycle_events / recycle_B / state_machine_attr / cap_evict_attr`。
- **归因闭环**：driver 初判 provisional `state_machine` → analyze 用 engine `[P3] evt=extent_recycle` 每事件复核；当该事件 `ts_recycle < recompute.ts` → flip 成 `capacity_evicted`（`recheck_attribution`）。**oversub 终判：remaining_state_machine==0**（=每一次 full recompute 都能解释为容量淘汰）；否则列出 state_machine 事件逐条报异常。
- 禁宣称 → `--family` 输出头部硬编码 oversubscription 框架句；CSV 列已含 cap/state-machine 分列。

### 7. gate3_parked_analyze.py 扩展（reviewer 新增两项）

1. **Gate C engine-join**（`parse_engine_events` / `gate_c_engine_join`）：解析引擎日志 `evt=restore_ready / ready_stage / admission / restore_state / restore_recompute`（行级正则，无跨距模式），按 rid 对齐，算 `Host-ready-before-admission rate`（分母=该臂 `ready_stage result=issued` 的 rid；分子=其中 `restore_ready`/`restore_state=READY` ts ≤ `admission` ts+grace(1s)）。≥95% 才合格。
2. **per-event 归因复核**（`recheck_attribution`）：用 `extent_recycle` 事件 ts < recompute ts 的每事件证据，把 provisional `state_machine` → `capacity_evicted`；state_machine=0 才合格。

**依赖边界（report 里必须标注）**：
- Gate C join 的前提 = 24052 引擎 `P2A/P3 trace` 事件默认发射、事件 rid 与驱动 SSE rid 可 join——**须 tester 在 24052 smoke boot 验证**（spec §3.1 假定 1/2/3；OD1）。不可 join → analyze 输出 `GateC: NOT_FULLY_VERIFIED`（rate=None 时判据降级）。
- RH toggle（`--enable-ready-horizon`）= **launcher 侧**；driver`--rh` 只打标/分臂，不发明引擎开关（spec §6.2 #4，标注 dependency）。
- **FILE_SIZE 两档**：fit ≥120G / oversub 30G 由 **launcher 档位**表达，driver v2 **不表达**（spec §6.2 #6 / §4.1）；报告标注 devops 须按档传。（本任务不涉及 launcher。）

### 对 architect e5 §6 dependency 清单（P0/P1/P2）落地状态

| spec §6 依赖 | driver/analyze 落地 | 状态 |
|---|---|---|
| 1 fit/oversub mode + caveats | gate3_parked.py v2 | ✅ 已具备（spec §6.1 已确认） |
| 2 `--rh on\|off` | v2 | ✅ 已具备 |
| 3 55k tier（default） | v2 BUILD_TIERS 含 55k，default=55k | ✅ 已具备（含 default 修复） |
| 4 classify_hit_parent 六类 | v2 | ✅ 已具备 |
| 5 recompute attribution 初判 | v2 | ✅ 已具备（改为 provisional state_machine，见 §4/D3） |
| 6 eviction_observed coarse sampler | v2（仅全局诊断，不参与归因） | ✅ 已具备（reviewer D3：不再打 capacity_evicted 依据） |
| 7 L3 物理足迹 st_blocks×512 | v2 | ✅ 已具备 |
| 8 FIT/OVERSUB 常量 | v2 | ✅ 已具备 |
| **park 梯（spec §6.2 #1）** | `--park-ladder` + Sched.ladder | ✅ **本轮补**（cohort 分配 / cohort_of / 行打标） |
| **`--build-workers`（spec §6.2 #2）** | run_builds 并发线程池 | ✅ **本轮补** |
| **gate3_parked_analyze.py** | 新建：Gate B 分桶 / Gate C engine-join / oversub 矩阵 + 归因复核 | ✅ **本轮补** |
| tester：engine-ready join 先验（spec §6.2 #3） | — | ⏳ **tester 24052 smoke boot 验证**（P0） |
| tester：RH toggle launcher（spec §6.2 #4） | — | ⏳ **tester + devops launcher**（P1） |
| launcher FILE_SIZE 两档（spec §6.2 #6） | — | ⏳ **devops launcher**（P1） |
| S=1000 RH ON（spec §6.2 P2） | — | ⏳ 可选（tester / orchestrator） |

### 与 architect 协议 §④ 判定字段对齐表（fit 模式）

| §④.3 判据 → 最终收购（ledger:2531-2535） | 驱动/分析承担字段 |
|---|---|
| resume TTFT p50≤5s / p95≤30s / >60s≤1% → **Gate B：p95≤5s / p99≤10s / >30s=0 / >60s=0** | runs.csv `ttft_s` + analyze p50/p95/p99 + gt30s/gt60s |
| turns/hour ≥80% ∨ 日程 | analyze `turns_per_hour`（verdict ts_start/ts_end） |
| recompute ≤5% → **Gate A：avoidable historical recompute=0%** | attribution + analyze `avoidable_historical_recompute_frac` |
| recycle-GC | analyze `evicted_delta/backuped_delta/load_back_delta` + extent_recycle(engine-log) |
| 0 OOM / 100% finished | runs.csv http/finished + GPU util（tester） |

## evidence（所有命令实跑，结果已观察）

1. `python3 -m py_compile gate3_parked.py gate3_parked_analyze.py` → OK（两文件）。
2. dry-run 全矩阵 OK：
   - `--mode fit --sessions 100 --rh on` → `DRY_RUN_OK mode=fit rh=on sessions=100 ... tier=55k`
   - `--mode oversub --sessions 500|1000 --rh on|off` → OK
   - `--mode fit --park-ladder "HOT:0-30@5,MID:120-300@30,COLD:600-2400@65" --build-workers 8` → OK
   - 缺省 `--sessions` / `--mode` 自动解析：`--sessions 50`→fit、`--sessions 600`→oversub；`--mode fit --sessions 500`→WARN fit>L3-fit-anchor；`--mode oversub --sessions 100`→WARN oversub<500。
3. Sched 不变量（含 ladder）：
   - uniform：30 sessions/active4/200 轮 → peak≤4、30/30 全选、cooldown_violations=0。
   - ladder long-churn：100 sessions/active8/FIT_PARK_LADDER → peak=8、100/100 全选、cooldown_violations=0。
   - cohort 分配：HOT=5/MID=30/COLD=65；`HOT window=27.3s`、`COLD window=2039.7s`；due 时序正确（HOT 31s 到期、COLD 599s 不到期、2401s 到期）。
4. `classify_hit_parent` 单元：device→GPU-resident、host+rh off→Host-ready、host+rh on+无 stor→Host-ready-STAGED、host+rh on+stor→RH-staged、storage→L3-on-demand、全 0→miss。
5. mock e2e（stub 传输 + FakeToken）：
   - oversub S=5/active2/rounds6：builds=5、resumes=11、hit_parent_mux 四类齐（GPU 2/Host 3/RH-staged 0/L3 3/miss 3）、attribution=3（初判 state_machine）、verdict caveats 含 `no_claim_l3_full_park_Sx55K`。
   - fit S=3/active2/rounds4：全 Host-ready、attribution=0（fit 无 full recompute）、verdict `l3_fit_formal_capacity_test_S100`。
   - fit + build-workers=3 + compact ladder：6 sessions 并发 build 全成、cohort 打标 {HOT,MID,COLD} 齐。
6. 测试中修复驱动自身 1 个 bug：resume 打印行 `(sx or {}).get("cached_tokens_details", {}).get("device")` 在 `cached_tokens_details=None`（真实引擎 possible）时 AttributeError → 改用 `(sx or {}).get("cached_tokens_details") or {}`。
7. analyze：
   - 单 cell（fit）`--fit` → Gate A avoid=0 / TTFT p50/p95/p99 / storage_hit_sessions 正常输出。
   - 单 cell（oversub）→ 表格 + `attribution_recheck`（no engine log）。
   - cross-S `--family + --csv` → 行级曲线 CSV 生成。
   - engine-log 解析：`extent_recycle` 3 事件/bytes 合并正确；`parse_engine_events` ready_stage/restore_ready/admission/restore_recompute 全部解析。
   - Gate C join：r100 ready≤admission → rate=1.0；r101 restore_state=READY≤admission → 也 ok；r102（未预测）→ 不在分母。
   - **归因复核闭环**：provisional 2×state_machine，engine recycle ts < recompute ts → `flipped=2 / remaining_state_machine=0`；recompute ts < recycle ts → 保持 state_machine（正确）。
   - 修复 analyze 自身 bug：attribution CSV `ts` 为 str → `recheck_attribution` 内 `float()` 强转（否则 `'<' not supported`）。

## followups（下游验证，非本任务范围）

- **tester（24052）**：
  1. smoke boot 验证 Gate C engine-ready join 可用性（`restore_ready`/`admission`/`ready_stage` 发射 + rid 可 join）——**P0，Gate C 前置**。
  2. RH toggle（`--enable-ready-horizon`）在目标部署生效（ON 臂 log 见 ready_stage/ready_pool；OFF 无）。
  3. 跑 S=100 fit RH OFF / ON（Stage 2/3，spec §5），S=500/1000 oversub RH OFF（Stage 4），S=1000 RH ON 可选（P2）。
- **devops**：launcher 两档 FILE_SIZE——fit ≥120G（0 recycle 前提）/ oversub 30G（cursor-wrap 密集，退化曲线有足够点）；`--enable-ready-horizon` toggle；`/data` free 校验（spec §4.1 / §1.1）。
- **orchestrator / architect**：OD1（Gate C join 不可用时是否接受 NOT_FULLY_VERIFIED 降级）、OD2（RH 是否纳入正式验收）、OD3（S=1000 ON 成本）、OD4（梯子 cohort 以 age 实测回读为准——analyze 已按 age_at_wake_s 输出桶，tester 报告时可再交叉）。

## open_issues

1. **55k 档位**：driver 已含 55k（default）；55K→实际 token 数（预期 ≈55000-55101，mock 中 build 截档 55101）须 tester 在 24052 首次实跑 dry-run/小规模 build 确认（warmctx 64K=64030 先例，风险低）。
2. **l3-backend-dir 默认**：物理足迹采样默认 off（None），须 tester 传 `<fresh namespace>`（spec §1.2）。
3. **Gate C engine-join 可用性** = 唯一未在 24052 验证的结构性前提（spec §3.1 / OD1）；不可 join 时 analyze 自动降级 NOT_FULLY_VERIFIED，但结论以 tester 验证为准。
4. **RH toggle** = launcher 侧能力（driver 只分臂打标），须 tester 确认引擎可复现 OFF/ON 双启动。
5. **oversub S=1000 与 build-workers**：1000×55k 并发 build 仍 ~40min；若 launcher FILE_SIZE=30G 且 L3 写 backlog 大，build 期可能已首 recycle（spec §4 预期，非 fault）。
6. **FILE_SIZE 两档** 由 launcher 表达，driver 不内置；若 tester 未按档配 → fit 0-recycle 前提可能被 BUILD 期 recycle 破坏（spec §1.4 Step 1 有"停、放大重跑"规则）。

## 依赖边界（driver/analyze 与引擎/launcher 的接缝，如实标注）

- 驱动**不读**引擎事件（慢速文件日志），Gate C/归因复核全部落在 analyze 的 engine-log 解析；driver 只产原始行 + provisional 归因。
- 驱动 `--rh` 与引擎 `--enable-ready-horizon` 是**两层开关**：driver 打标/分臂，engine toggle 在 launcher。误把 driver `--rh on` 当引擎已开 RH 是错的——tester 必须合验。
- L3 物理足迹（st_blocks）是稀疏 extent 的物理占用（`ls -l` 逻辑字节无效），analyze 取 coarse `l3_physical` 序列 min/max/last。