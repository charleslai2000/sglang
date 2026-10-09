# phase2-p2-fixa-tester-e1 — Fix A 独立验证（容量 release epoch / host_release 唤醒）

```text
status: done
artifacts:
  - 24052 引擎（/root/sglang-b1-continuity, editable install）已含 Fix A/P0/P1，
    只读验证，未改产品实现
  - 场景① fixa1: /root/evidence-gate3-fixa1/ + /root/engine-gate3-fixa1.log（341 请求, rc=0）
  - 场景② fixa2: /root/evidence-gate3-fixa2/ + /root/engine-gate3-fixa2.log（342 请求, rc=0）
  - Fix A 确定性探针: /root/probe_fixa.py（在 deployed ready_horizon 模块上 7 断言全过）
  - 本报告
evidence:
  - Fix A live 确认（§1）
  - 场景① 冻结 headroom + miss churn（§2）
  - 场景② 容量 release + 有效物材（§3）
  - 机制被锻炼 + 无互相掩盖（§4）
  - PASS Gate 逐条（§5）
  - 强化标准 baseline 对比 + wake-storm（§6）
  - 结论（§7）
summary: Fix A 独立验证 PASS；机制被真实锻炼（host 容量真实释放→waiter 恢复），
  无 wake-storm，P1 miss 门不误伤有效物材/容量，两场景无互相掩盖
followups:
  - host_release 计数器/NO_HEADROOM park 无运行时日志/指标暴露，只能靠
    host_used 时序列推断释放事件 + 确定性探针证明订阅逻辑。建议 coder 暴露
    host_release epoch 与 NO_HEADROOM park 计数到 /metrics，便于长期观测
  - 本验证 fixa1/fixa2 为同配置重复（1200s），未做超过 30min 的 soak；
    2h soak 验证可另行派发
open_issues:
  - 无（本 Fix A 独立验证范围内）
```

## 0. 环境与代码前置（均核实）

- 机: 175.155.64.171:24052 (root), RTX 3090 24G；模型 /root/models/Qwen3.5-9B-w4a16；
  env sglang-patch；/data 起始 15% (160G free)；GPU 起始 idle 0%/15MiB；无残留引擎/锁。
- 引擎 repo: `/root/sglang-b1-continuity`（editable install 映射，非 git）。

## 1. Fix A 是否 live 确认（代码级）

deployed `ready_horizon.py` md5 = `040f917f...` **与本地 opt HEAD (74246bb90f, 含 Fix A e0e83b11a1) 逐字节一致**。
`hicache_restore.py` md5 亦与本地一致。`scheduler.py` 与本地 HEAD 仅差一处 **+20 行独立 P（too_short 防御），
Fix A host_release 代码块逐字节一致**——该 P 差异与 Fix A 正交，不影响本验证。

deployed 关键 Fix A 行确认：
- `ready_horizon.py:283-293`：`subscribed_epoch(NO_HEADROOM) -> "host_release"`（原 host_headroom）。
- `ready_horizon.py:325-333`：host_release 分支，`cur > entry.epoch_cursor` → 清 park（单调，不受 transient level 影响）。
- `ready_horizon.py:501`：`epoch_event` 在 `cur.host_release > prev.host_release` 时触发（M3 refill gate）。
- `scheduler.py:3546-3552`：`available = cc.mem_pool_host.available_size()`，若 `available > last_level` → `host_release += 1`（monotonic bump）。
- P1 门（`MISS_RECOMPUTE` / `miss_rearm_allowed`）与 P0 守卫亦在 deployed（md5/行确认）。

**结论：Fix A live。**

## 2. 场景① 冻结 headroom + 无 release + miss churn（fixa1）

配置：`gate3_ab.sh --tag fixa1 --agents 8 --launch direct-launch-gate1-rhon.sh --rt 400 --budget 1200 --cmax 900 --max-size 200G --file-size 30G`（RH ON，与 P1 同负载）。
结果：**COMPLETE rc=0**，341/341 HTTP 200 + finished=True。

- **headroom 冻结确认**：`ready_stage` 事件 headroom 最小值 = 0（13 次打到 0），host 工作集压满。
- **miss churn 存在**：`revoked_full_miss` 762 / `prefetch_revoke` 787 / `MISS_RECOMPUTE` 787 / `restore_recompute` 795。
- **有效物材不被 P1 miss 门误伤**：device_hit>0 = 260 请求全部完成；host_hit>0=113；
  `WAIT_CAPACITY` 416（DEVICE_QUOTA）+ 103（FRONTIER）+ 40（PREFETCH_BUDGET）——纯容量/有效物材正常 re-arm 等容量。
- **恢复**：restore_success=54 活跃到 run 末（last +13:21:56，run 13:24 结束）；restore_ready=180；
  0 rid 最后停在 WAIT_CAPACITY；WAIT→recover 最大 stall 60.6s（=一次 T13 timeout 边界后恢复）。
- **无崩溃/OOM**：scheduler_exception=0，CUDA OOM=0；GPU util avg 92.6% max 100%。
- **无 wake-storm**：ready_stage same-rid <1s 共 37 对，其中 **declined→declined 仅 1**，其余全部 issued→issued（合法 staged 前进）。
- extent recycle 2358，distinct generation=10（健康 cursor-wrap，无 thrash）。

**场景① 判定**：冻结 headroom + 高 miss churn 下，纯容量/有效物材请求不被 P1 miss 门误伤，全部完成，restore 持续 progress。PASS。

## 3. 场景② 容量 release + 有效物材（fixa2）

同配置（fixa2）。结果：**COMPLETE rc=0**，342/342 HTTP 200 + finished=True。

- **容量真实释放**（host_release epoch 的 ground truth）：`hicache_host_used_tokens` 时序列（244 采样，
  total=98305）出现 **75 次 distinct release 事件**（used 单步降 >500），如 98136→56921、98305→94135 等——
  即 `available_size()` 增长 → `host_release` bump 的真实触发。
- **被容量阻塞的 restore 在 release 后恢复**：20 个 `ready_stage result=declined`（headroom 门）中，
  5 个随后 `restore_success` / `restore_ready`（0eea6221, 0bf17287, b68f1997, c6ee6d2f(MISS_RECOMPUTE), e1e9620b→ready）——
  即真实观察 NO_HEADROOM/WAIT 门 → host 释放 → waiter 恢复 的状态链（declined ready_stage → 后续 restore_success/READY）。
- **有效物材不被误伤**：device_hit>0=258 全部完成；host_hit>0=107；storage_hit>0=27。
- **恢复**：restore_success=61 活跃到 run 末（last +13:49:26，run 13:51 结束）；restore_ready=206；
  0 rid 最后停在 WAIT_CAPACITY；WAIT→recover 最大 stall 60.6s。
- **无崩溃/OOM**：scheduler_exception=0，CUDA OOM=0；GPU util 高。
- **无 wake-storm**：ready_stage same-rid <1s 共 62 对，**declined→declined = 0**，全部 issued→issued。
- extent recycle 2387，distinct generation=10（健康）。

**场景② 判定**：容量真实释放（host_release bump 触发）→ 被阻塞 restore 被唤醒并完成，无 wake-storm，无互相掩盖。PASS。

## 4. 机制被锻炼 + 无互相掩盖（强化标准核心）

**机制被真实锻炼的证据链（Fix A 目标状态转换）**：
1. host 容量压满（ready_stage headroom 打到 0，场景①13次/场景②6次）；
2. host 工作集真实释放（`hicache_host_used_tokens` 时序列 75 次 drop，场景②）；
3. `_ready_horizon_epochs` 观测 available 增长 → `host_release += 1`（deployed 代码确认，§1）；
4. NO_HEADROOM park 订阅 host_release，release 前移 → `entry_cleared` → waiter 重新评估；
5. 恢复为 restore_success / restore_ready（场景② 5 个 declined rid 实际观察到 success/ready）。

由于 `host_release` 计数器与 `_park_ready_decline` 在运行时**无日志/指标暴露**（deployed 只存内部 state），
第 3/4 步在运行期不可直接观测。因此用**确定性探针在 deployed `ReadyHorizonPolicy` 上证明**订阅逻辑（§4.1）。

### 4.1 deployed 模块确定性探针（/root/probe_fixa.py，7 断言全过）
- `subscribed_epoch(NO_HEADROOM) == "host_release"`（原 host_headroom）。
- level=0 + release 同 → 不 cleared（transient level 不再误触发）。
- **level 升到 100 + release 同 → 仍不 cleared**（B-run 冻结形状：Fix A 忽略 transient level）。
- **release 前移 → cleared**（Fix A 唤醒）。
- `epoch_event` 在 release 前移时 True；level-only 变化时 False（refill 自身流量非事件）。
- fuse 窗口内同 release 重 park → 不 cleared（防 wake-storm 的 debounce）。
- identity（generation）变化 → cleared。

**探针在 exact deployed ready_horizon 模块上证明 Fix A 订阅/唤醒/debounce 语义全部正确。**

### 4.2 无互相掩盖
- **场景① miss 不伪装成容量阻塞**：miss 驱动路径（MISS_RECOMPUTE 787）与容量 WAIT（DEVICE_QUOTA 416）
  是分离状态转移；miss 后走 forward recompute，容量 WAIT 走 re-arm——`restore_state` 转移统计
  （RESTORING→MISS_RECOMPUTE 787 vs WAIT→RESTORING 551）证实两门各自独立放行。
- **场景② 容量阻塞不伪装成 miss**：declined ready_stage 多为 WAIT_CAPACITY（headroom 门），
  仅 1 例 MISS_RECOMPUTE，且随后 restore_success/ready；device-hit 请求全部完成，无被 P1 miss 门拦截。
- P1 门= cache 证据 epoch（l3_publish/generation），Fix A 门= 容量 release epoch（host_release），二者正交（代码级确认 §1）。

## 5. PASS Gate 逐条

| Gate | fixa1 | fixa2 | 判定 |
|---|---|---|---|
| 无崩溃 | 0 Scheduler exception | 0 Scheduler exception | **PASS** |
| correctness | 341/341 HTTP 200 finished | 342/342 HTTP 200 finished | **PASS** |
| 无 OOM | 0 CUDA OOM | 0 CUDA OOM | **PASS** |
| 无 zero-progress | restore_success 活跃到 run 末；GPU avg 92.6% max 100% | restore_ready last +13:50:45 (run 末) | **PASS** |
| 无 HTTP error | 0 非 200 | 0 非 200 | **PASS** |
| restore/容量 progress | 54 success / 180 ready | 61 success / 206 ready | **PASS** |
| 容量 release 后恢复 | 0 rid 停 WAIT，max stall 60.6s | 0 rid 停 WAIT，max stall 60.6s | **PASS** |
| P1 门不误伤有效物材 | device_hit 260 全完成 | device_hit 258 全完成 | **PASS** |
| 无 wake-storm | declined→declined <1s = 1 | declined→declined <1s = 0 | **PASS** |
| 无互相掩盖 | §4.2 | §4.2 | **PASS** |

## 6. 强化标准：baseline 对比 + 机制锻炼 + wake-storm

| 指标 | 原始 B 冻结基线 (ab-a-on, 满盘) | clean 基线 bl2-on (pre-FixA) | Fix A fixa1 | Fix A fixa2 |
|---|---|---|---|---|
| restore_success | 21（+121s 冻） | 270（活） | 54（活到末） | 61（活到末） |
| recompute | 9,128 | 1,724 | 795 | 867 |
| DEVICE_QUOTA WAIT | 6,351 | 1,876 | 416 | 476 |
| extent distinct gen | 36,124（thrash） | 5 | 10 | 10 |
| TTFT p50/p95 | - | 16.2/45.7 | 22.3/58.0 | 22.2/53.5 |
| 0 rid 永久 WAIT | 冻结 | - | 0 | 0 |
| wake-storm (declined→declined <1s) | - | - | 1 | 0 |

- **waiter 滞留**：两场景 0 rid 永久滞留 WAIT；max stall 60.6s（单次 T13 边界后恢复）。无永久冻结。
- **restore_success**：Fix A 下活跃到 run 末（无冻结），与 clean 基线方向一致（量低于 bl2 因 run 时长短、请求少 341-342 vs 627）。
- **recompute / DQ WAIT**：Fix A 远低于原始 B 冻结基线（795 vs 9128；416 vs 6351），与 clean 基线同量级——无 recompute storm。
- **TTFT**：fixa1/fixa2 p50 22.2-22.3 / p95 53.5-58.0，与 clean 基线 bl2 (16.2/45.7) 同量级，无退化到原始 B 慢尾。
- **wake-storm**：declined→declined <1s 在 fixa1=1 / fixa2=0（未异常上升），全部快速对为 issued→issued（合法前进），**无 wake storm**。
- **机制被锻炼**：host 容量真实释放（75 次 release 事件，场景②）+ declined waiter 实际恢复（场景② 5 rid）+ deployed 探针证明订阅/唤醒语义 → **Fix A 机制确实被锻炼，非仅总体指标**。
- **progress 改善**：Fix A 下无永久冻结、restore 持续 progress、所有请求完成——**wake 对应真实 progress 改善，非空转**。

**硬性 PASS 条件满足**：Fix A 增加 wake 且伴随 progress（restore_success/ready 活跃到末），未产生 wake-storm，未无对应 progress 的空转。

## 7. 结论

**Fix A 独立验证 PASS。**
- Fix A live（deployed ready_horizon/scheduler 与本地 opt 一致，host_release 逻辑完整）。
- 场景①（冻结 headroom + miss churn）：纯容量/有效物材不被 P1 miss 门误伤，全部完成。
- 场景②（容量 release + 有效物材）：host 真实释放（75 次 release）→ waiter 恢复（5 rid 观察），被容量阻塞 restore 完成。
- 无互相掩盖；PASS Gate 全过；强化标准（机制锻炼 + baseline 对比 + 无 wake-storm）满足。

## 8. limitations

- `host_release` 计数器与 NO_HEADROOM park 无运行时日志/指标暴露：运行期第 3/4 步（bump/clear）只能由
  host_used 时序列 + deployed 探针推断，不能直接打印真实 host_release 数值。探针在 deployed 模块上
  证明语义，但非对真实 run 内部计数器的直接观测。
- fixa1/fixa2 为同配置重复，各 ~20min；未做 >30min soak（可另行派发）。
- 与 clean 基线 bl2-on 的对比跨不同 run 批次（run 时长/请求量不同，bl2 627 vs 本 341-342），
  指标同量级比较，非严格同负载 A/B；但原始 B 冻结基线对比是决定性的（Fix A 无冻结/无 storm/无慢尾）。

## 9. 环境最终状态

- 24052 引擎代码未改（只读验证）；22151 未动（本机无 22151 引擎）；只 24052。
- /data: 15% (160G free)（本实验自建 /data/l3/p2io-gate3-fixa1/fixa2 已 find -delete 清空）。
- GPU: idle 0%/15MiB；无残留引擎/锁。
- 分析脚本保留 /root/probe_fixa.py（自建，非产品代码）。
