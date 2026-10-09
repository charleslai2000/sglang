# phase2-tooshort-architect-e1 — too_short recompute churn 架构裁决

```text
status: done
artifacts:
  - 本报告（read-only 架构裁决，不实现）
evidence:
  - 代码证据（repo /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt,
    HEAD=74246bb90f 含 P1；基线 cc718c3c2e）见 §Root cause 文件:行
  - P1 tester 观测：work/phase2-p1-fix-tester-e1.md §6（241→307 too_short；
    最差 offender d1a84264 = 68 次 too_short + 仅 1 次 revoked:miss）
  - git 历史：too_short 判定路径源自 P2-1 基线 f3fffa7f09，P1 未触碰
summary:
  Conclusion
  Current Architecture
  Problem / Forces
  Proposed Architecture
  Alternatives
  Migration / Impact
  Open Decisions
followups:
  - 修复实现交由 coder（本报告仅裁决）；先解决 open decision 1（device-match-decay bet 保留与否）
open_issues:
  - open decision 1/2/3 见 §Open Decisions
```

## Conclusion（一页裁决）

**真缺陷（低严重度），值得修，独立小修，置于 P3 正式测量之前。**

- 根因是**唤醒谓词缺口**，不是 too_short 判定本身错误：WAIT[DEVICE_QUOTA] 的容量唤醒（T11）只重验容量，不重验 restore suffix 是否仍 ≥ prefetch_threshold(256)，于是对"永久 sub-threshold 残段"的请求反复唤醒→re-issue→declined_too_short→re-WAIT（16ms 紧循环，单请求 ≤68 次）。
- 属**既有暴露**，非 P1 回归：too_short/declined_too_short 路径在 P2-1 基线 f3fffa7f09 已存在，P1 的 miss 门（scheduler.py:4522-4570）不触碰该路径；+27% 是 P1 消除 miss 驱动 churn 后的**计数再分配**（这些请求此前被 miss churn 吸收，现以 too_short churn 形态浮出）。
- 不阻塞 forward progress（请求最终 HTTP 200，wall 35-44s），是正确性/liveness 之外的**周期浪费**。但它是当前 churn 余量最大来源，修复局部、低风险、成本低，值得做。
- 推荐修复方向：**主修=准入侧不再为"永久 sub-threshold 残段"park WAIT**（把 `has_restore_potential` 的 `host_hit_length>0` 短路也纳入 `prompt_can_qualify_for_prefetch` 的 never-case 门），**辅修=T11 唤醒谓词重验 suffix**（纵深防御）。不降 prefetch_threshold。
- 归属：**独立 P**，置于 P3 正式 A/B 测量之前（P3 的 READY/decline 统计被此 churn 污染，先清干净再测）。

## Current Architecture

too_short 判定与唤醒链（本地 opt 路径，HEAD=74246bb90f）：

1. **too_short 判定（storage 侧，唯一来源）** — `unified_radix_cache.py:2551-2564`
   `prefetch_from_storage()`：`prefetch_length = len(prefetch_key)`（= device-match+host-hit 之外的新增后缀，page_aligned），
   `if prefetch_length < self.prefetch_threshold(256): → return "declined_too_short"`，**granted=0**（不做任何部分 restore）。

2. **re-issue 腿（scheduler 侧）** — `scheduler.py:3038-3055`
   `_prefetch_kvcache()` 对 outcome==declined_too_short：仅在
   `self._restore_potential_for(req) and too_short_wait_armed(poll_interval)` 时 apply `DENIED_SHORT`；
   `too_short_wait_armed` = `poll_interval > 0`（M2 默认 0 → False，首次 decline 即 terminal recompute）。

3. **re-issue leg 的 too_short 终局** — `hicache_restore.py:123-131`
   DENIED_SHORT 落在 RESTORING → `NONE + ADMIT_RECOMPUTE`（terminal，立即 recompute）。

4. **容量唤醒（T11）** — `scheduler.py:3193-3210` + `_restore_wait_capacity_fits`（scheduler.py:3692-3756）
   `capacity_wake_applies`（hicache_restore.py:439-444）把 DEVICE_QUOTA 列为"可测"，
   唤醒谓词**只查容量**（charge < available_and_evictable），**不查 suffix 是否仍 ≥ threshold**。

5. **准入 re-arm（T6）** — `scheduler.py:4522-4572`
   NO_TOKEN 且 `_restore_potential_for(req)` → WAIT[DEVICE_QUOTA]。
   `_restore_potential_for`（scheduler.py:3758-3767）→ `has_restore_potential`（unified_radix_cache.py:3113-3137）：
   **`if host_hit_length > 0: return True` 短路**，先于 `prompt_can_qualify_for_prefetch` 门
   （该门只在 host_hit_length==0 时生效，unified_radix_cache.py:3127-3130）。

6. **P1 miss 门** — scheduler.py:4557-4570 `miss_rearm_allowed`，仅对 MISS_RECOMPUTE 态生效，
   不触碰 too_short/DEVICE_QUOTA 路径。

## Problem / Forces

- **restore length 为何缩到 15**：`_prefetch_kvcache` 的 suffix = `full_untruncated_fill_ids[matched_len:match_end]`，
  matched_len = prefix_indices + host_hit_length（scheduler.py:3013）。host/device 命中吸收了几乎整个 prompt，
  只剩 15-token 尾段需要 L3。15 < 256 → 永不能成为 storage prefetch。
- **granted=0 语义**：storage prefetch 整体拒绝，不做部分 restore；这 15 个 token 的恢复只能走 recompute，L3 帮不上。
- **为何 re-arm 不前进**：`has_restore_potential` 因 `host_hit_length>0` 短路返回 True →
  准入侧把这类请求 park 进 WAIT[DEVICE_QUOTA]；T11 容量唤醒只验容量 → 反复 re-issue 一个必然 too_short 的 prefetch →
  每次 declined_too_short（re-issue leg）→ 依 poll 进 REVALIDATE 或保持 RESTORING → 再被 T6/T11 拉回 WAIT。
  容量一有空就唤醒，但 suffix 永远 sub-threshold，永不 READY → 空转。
- **为什么 P1 miss 门不拦**：P1 门只在 MISS_RECOMPUTE 态、基于 L3 publish epoch/generation 判据（scheduler.py:4557）。
  too_short 是 recompute 侧（suffix<阈值），非 miss，状态不在 MISS_RECOMPUTE，故 rearm_allowed 默认 True。
- **严重度**：低。正确性/无饿死/无 OOM 均 PASS（请求完成）。纯调度/恢复周期浪费，但为当前最大 churn 源。

## Proposed Architecture（推荐修复方向，不实现）

最小充分的结构变更 = **让"永久 sub-threshold 残段"不进入 WAIT，也不被唤醒**：

- **主修（准入侧）**：`has_restore_potential`/`_restore_potential_for` 把 `host_hit_length>0` 的短路
  也纳入 never-case 门——当**当前 suffix 与理论最大 suffix 都 < prefetch_threshold**（`prompt_can_qualify_for_prefetch`
  的 never-case，unified_radix_cache.py:3111）时，即使 host 有物材也不 park WAIT[DEVICE_QUOTA]，直接 recompute 尾段。
  这与 P1/Fix B 已建立的"re-arm 前判据"模式一致（不 armed 一个只会 re-issue 必败 prefetch 的 WAIT）。
- **辅修（唤醒侧，纵深防御）**：T11 `_restore_wait_capacity_fits` 对 DEVICE_QUOTA waiter 加一条——
  当前 restore suffix 已 sub-threshold 且不可增长时不再唤醒（直接释放 recompute 或留给 T13）。
  成本低，纯谓词收紧。

**trade-off**：见 §Alternatives。

## Alternatives

- **A. 降 prefetch_threshold（如 256→64）**：减少 too_short，但让更多短段进 L3 往返，整体 L3 效率下降、IO 变多，
  与 prefetch_threshold 存在理由（不为此类 15-token 段做存储查询）相悖。**不推荐**。
- **B. 修 DEVICE_QUOTA 唤醒条件（替代/并行的辅修）**：只堵唤醒端、不堵准入端——请求仍会 park 一次 WAIT 并空耗 T13，
  改善有限。**可与主修并用**，但单用不足。
- **C. 保留 device-match-decay REVALIDATE bet（需判别）**：WAIT[REVALIDATE] 的语义是"device match 可能 decay 后暴露更长 suffix"。
  若一律把 sub-threshold 释放，会误杀该 bet。**推荐保留 never-case 判别**：只释放"当前和理论最大都 < 阈值"的请求，
  对"当前 < 阈值但 decay 后可达"的保留 REVALIDATE。这是 open decision 1。

**推荐**：主修（准入侧 never-case 门）+ 辅修（T11 唤醒重验），保留 device-match-decay bet。

## Migration / Impact

- 改动面：`unified_radix_cache.py`（has_restore_potential / prompt_can_qualify_for_prefetch 语义）
  + `scheduler.py`（_restore_wait_capacity_fits 或 _prefetch_kvcache 判定）。纯 predicate 收紧，无新抽象、无状态机改动。
- 不影响已确认基线（RH 等）；与 P1/Fix A/Fix B 正交。
- 预期收益：消除 too_short 驱动紧循环（P1 后最大 churn 源），P3 READY/decline 统计干净。
- 风险：若 never-case 门误判（把 decay 后可恢复的请求释放），损失一次本可省的重算——需 open decision 1 定判别粒度。

## Open Decisions

1. **device-match-decay REVALIDATE bet 的保留粒度**：只释放"当前+理论最大都 sub-threshold"，还是对当前 sub-threshold 一律释放？
   决定主修是否误杀该 bet。**需用户/架构决策**。
2. **辅修（T11 唤醒重验）是否实施**，还是仅靠准入侧主修。推荐两者都做（低成本纵深防御）。
3. **优先级确认**：是否在 P3 正式 A/B 测量前插入此独立修复（推荐），还是并入某批量 churn 修复。
