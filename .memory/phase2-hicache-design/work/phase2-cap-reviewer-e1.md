# phase2-cap-reviewer-e1 — 独立核验 ④ spec ↔ gate3_parked.py v2 驱动一致性

- agent: reviewer
- epoch: e1
- date: 2026-09-07
- task: phase2-cap-reviewer-e1
- note: reviewer 带 harness 约束未落盘，本文件为 orchestrator 依据其返回 envelope 落盘的控制面副本。

## verdict: APPROVE
spec §6 核心主张全部成立：v2 驱动 8 项能力真实在树；park 梯 + `--build-workers` 缺失判定正确；无 spec-claim-error。一处 MEDIUM finding（analyze 未满足 Gate C/归因复核依赖）需上升执行依赖。

## status: done（read-only 核验，未改任何文件，未跑 GPU）

## 1. 能力对照表（spec §6.1「已具备」× 驱动实际，全部 VERIFIED）

| spec §6.1 | 驱动实际 | 状态 |
|---|---|---|
| 1. --mode fit\|oversub + semantic caveats | choices :674；caveats :638-647（oversubscription_stress_curve/recycle_allowed/no_claim_l3_full_park）；auto-resolve :735-748 | 已具备 |
| 2. --rh on\|off 配对档 + verdict rh 字段 | :682；docstring 标明"engine 能否 toggle RH 是 launcher 依赖" :683-688（诚实）；verdict "rh" :653；per-row rh_flag :573 | 已具备 |
| 3. --build-tier 55k（default） | BUILD_TIERS={"50k","55k","64k","80k"} :149-154；default="55k" :689 | 已具备 |
| 4. classify_hit_parent 六类 + hit_parent_mux 列 | :334-348 六类全可达；:569 输出列 | 已具备 |
| 5. recompute 归因（capacity_evicted/state_machine/other） | 检测+打标 :514-547；write_attribution :594-619 | 已具备 |
| 6. eviction_observed coarse sampler | :811-829 counter deltas | 已具备 |
| 7. L3 物理足迹 st_blocks×512 | :299-315 / :312 | 已具备 |
| 8. FIT/OVERSUB 常量 | L3_FIT_SESSIONS=170/FIT=100/OVERSUB=(500,1000) :159-161 | 已具备 |

## 2. 实质 gap

- **D1（spec 已标注缺失，实测确认）**：`--park-ladder` 不在树（Sched._park_seconds 为 uniform(park_min,park_max) :228-231，无 cohort 概念）；`--build-workers` 不在树（run_builds 顺序 for 循环 :387-422）。与 spec §6.2 判定一致。
- **D2（MEDIUM，超出 §6.2 所列两补丁的第三处待建）**：`gate3_parked_analyze.py`（17183 B）在树，但：
  - `parse_extent_recycle` :153-171 仅 aggregate-count extent_recycle/freed_bytes，无 per-event ts join / recompute 复核；
  - 全文无 restore_ready/ready_stage/admission/restore_recompute 解析（Gate C engine-join 缺）；
  - :263-266 / :404-405 / :435-439 直读 driver 的 provisional attribution（state_machine 计数为粗代理）。
  - **影响**：Stage 3（Gate C verdict §3.5）与 Stage 6（oversub 归因闭环 state_machine=0 §4.4）**无法由今日 analyze 产出**。待建（spec §6.2 项5 标"coder 可选/tester 可造"），非门脚本缺陷，但误以为已就绪会带偏 Stage 3/6 结论。
- **D3（LOW，oversub 相关）**：`eviction_observed` 为 per-run 全局布尔（:803/:823），backuped_tokens_total（L2 常规写回）移动即置 True → :530-531 对未真实回收的 session 过度打 capacity_evicted，掩盖真 state_machine。fit 模式无碍（Gate A 判据①按 reason 无关事件计数）；oversub 依赖 D2 的 reconcile 修正。修正同一次解决（D2+D3）。
- **D4（INFO 非缺陷）**：full_history_recompute 为二元事件（hit_sum==0 ∧ prompt_len≥0.9·hist :514-518）；spec 判据②的连续 recompute_tokens=prompt−hits 可由 runs.csv 列计算，无 gap。

## 3. 可执行性结论
- S=100 fit 双臂（RH OFF/ON）**core 测量可行**（driver 已产出 Gate A/B 原始数据）；但须先补 `--park-ladder`（Gate B 分层确定性制造）+ `--build-workers`（fit 也省 ~30min）。
- S=500/1000 oversub：`--build-workers` 为硬依赖（顺序 build 500×55K≈2h / 1000×55K≈4h 不可行）。
- 要产出 spec 全部裁决必须补齐（按 P0）：`--park-ladder`、`--build-workers`、**extend analyze**（Gate C engine-join + §4.4 per-event 归因复核）。
- RH toggle 依赖 launcher（:683-688 标称正确，一致 spec §3.0/§6.2 项4）；engine-ready 事件可用性属 tester 24052 先验，本核验不裁决。

## followups（转交）
- **coder**：park 梯 + --build-workers（P0，确认未实现）；补 analyze 的 Gate C join/归因复核（D2，一次解决 D2+D3）。
- **orchestrator**：知悉 analyze 当前能力边界，Stage 3/6 前置其补齐。