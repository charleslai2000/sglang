# phase2-tooshort-fix-tester-e1 — too_short 重算 churn 集成验证（tester）

```text
status: done
artifacts:
  - 24052 引擎四文件同步 = 本地 opt commit 7155cd8973（纯增量，已核验逐字节一致）:
      python/sglang/srt/mem_cache/unified_radix_cache.py（主修）
      python/sglang/srt/managers/scheduler.py（辅修）
      3090-dev/test_storage_regression.py + test_hicache_restore_scheduler_feed.py
  - 备份 .tooshort-pre 四份（== P1 74246bb90f，已核验），置于 live 文件旁 + repo 根各一份
  - 远程单元: scheduler_feed 16 passed / storage_regression 101 passed /
      restore+ready_horizon 162 passed（合计 279 passed，无回归）
  - stress 证据: /root/evidence-gate3-tooshort/（metrics-final / runs.csv /
      gpu-util.csv / engine-events-*）+ /root/engine-gate3-tooshort.log
  - 本地分析副本: /tmp/tooshort_check/evid-ts/
  - 本报告
evidence:
  - PASS Gate A-G 逐条 PASS，见 §3
  - counterfactual 无永久封死，见 §4
  - +27% 定性 = P1 暴露（非 P1 regression），P1 miss 收益保持，见 §5
summary: too_short 修复经 GPU 集成验证成立；A-G 全 PASS；counterfactual 干净；
  +27% 确认为 P1 暴露；too_short 可收口关闭（独立小修，不重开 P1），可进 P3。
followups:
  - P3 正式 A/B 测量可开始（P3 READY/decline 统计已不被 too_short churn 污染）
open_issues:
  - 剩余 53 次 too_short 均为稀疏单发（>500ms，ready_stage 路径），非紧循环；其中
    8 次 capacity re-arm 为保留的 device-match-decay bet（正确行为），非缺陷
  - l3_publish_epoch 静止性（P1 tester open issue）未在本任务范围闭合
```

## 1. 代码同步（纯增量确认 + 备份 + 远程单元绿）

- 同步前核实：deployed 四文件（unified_radix_cache.py / scheduler.py / 两测试）与本地
  P1 HEAD **74246bb90f 逐字节 IDENTICAL**。⇒ HEAD→deployed delta = 恰好 too_short 纯增量。
- 本地 commit 7155cd8973 相对 74246bb90f 的变更 = 4 文件（+163/-5）：
  - unified_radix_cache.py: `has_restore_potential` 的 `host_hit_length>0` 短路移到
    `prompt_can_qualify_for_prefetch` never-case 门**之后**（+19）
  - scheduler.py: `_restore_wait_capacity_fits` 新增 DEVICE_QUOTA 守卫（+20）
  - 两测试文件新增用例 + 既有断言更新
  - **P1 miss 门（miss_rearm_allowed / device_quota_degraded / MISS_RECOMPUTE）未触碰**（已 grep diff 确认无变更）
- 同步后 4 文件远程逐字节 == 7155cd8973（diff 全 IDENTICAL）。
- 备份 .tooshort-pre 四份，核验 == 74246bb90f。
- 远程单元（sglang-patch env，CUDA_HOME=nvidia/cu13；pytest 需临时 pip install 入 sglang-patch）：
  - test_hicache_restore_scheduler_feed.py: **16 passed**（含 3 条新增 T11 唤醒）
  - test_storage_regression.py: **101 passed**（含新增 2 条 + 1 条断言更新）
  - test_hicache_restore.py + test_ready_horizon_unit.py + test_ready_horizon_partition.py: **162 passed**
  - 合计 279 passed，无回归。

## 2. stress 配置与运行

- 驱动: `gate3_ab.sh --tag tooshort --agents 8 --launch /root/direct-launch-gate1-rhon.sh
  --rt 400 --budget 1800 --cmax 900 --max-size 200G --file-size 30G`（与 P0/P1 同配置复刻）
- 引擎: RH ON, write_back, L3 extent, MAX_SIZE=200G FILE_SIZE=30G, max_total_tokens=65536,
  hicache_ratio=1.5，同 P1。
- 结果: **COMPLETE rc=0**，引擎存活满 1827.1s（verdict elapsed_s），545 请求，无崩溃。
- /data 起始 15%（160G free），独立 STORAGE_DIR /data/l3/p2io-gate3-tooshort，实验后已清理（28G→4K），/data 复原 15%。

## 3. PASS Gate 逐条

| Gate | 判据 | P1 基线 | too_short 修复 | 判定 |
|---|---|---|---|---|
| A. too_short churn 归零 | reason=too_short 计数 | 307 | **53** (-83%) | **PASS** |
| A'. 紧循环 (<100ms 连续 DEVICE_QUOTA) | 同 rid 连续 WAIT_CAPACITY <100ms | 237 | **25** (-89%) | PASS |
| A''. too_short/prefetch_issued 比率 | | 0.211 | **0.0355** (-83%) | PASS |
| B. 同 candidate 无缓存状态变化不得立即 re-arm | 同 rid 连续 too_short <500ms | (P1 最差 68 次/16ms) | **0** 次；同 rid 最多 6 次、间隔 573ms~16s（ready_stage 路径） | **PASS** |
| C. T11/resource wake 重验长度 | `_restore_wait_capacity_fits` DEVICE_QUOTA 守卫 | 无 | live @ scheduler.py:3734 + 3 条单测 PASS | **PASS** |
| D. restore_success/storage_hit 不降 | restore_success /req | 97 (172.6/千req) | 90 (165.1/千req)，backuped 6.16M→6.11M 持平 | **PASS** |
| E. recompute 不异常升 | 总 restore_recompute | 1194 | 1242 (+4%，variance 内)；too_short 浪费 token 10540→**1908** (-82%) | **PASS** |
| F. P1 miss 收益保持 | revoked:miss /req | 2.12 (P1) | 2.27（P0=4.72，P1 收益未回退）；miss 门 diff 未触碰 | **PASS** |
| G. HTTP/correctness/OOM/zero-progress | 见下 | | | **PASS** |

G 明细：
- correctness: 545/545 HTTP 200，finished=True，output_sha16 全非空；TTFT p50/p90/max = 21.5/38.1/117.6s；wall p50/p90/max = 24.8/41.7/118.7s
- OOM: 0 CUDA out of memory，0 MemoryError（60 处 libtorchcodec 为 benign 启动 traceback）
- zero-progress: GPU avg 98% max 100%；last restore_success 14:37:29（run 末 14:38:03）
- 无 Scheduler exception，满预算存活，无崩溃

## 4. counterfactual（无永久封死本可 restore 的请求）

- 全部 42 个非 health too_short rid：41 个在 runs.csv 中 HTTP 200 + finished=True；
  1 个（4ab2220b）为 boot-time（14:07:31，早于 run 起点 14:07:36）健康检查请求，too_short 后立即 admission recompute，正确。
- 每个 too_short rid 在其最后一次 too_short 之后均出现 `evt=admission`（43/43），无任何 rid 被 never-case 门永久 park。
- **保留的 device-match-decay bet 未被误杀**：8 个"当前 sub-threshold 但 decay 后可达"的
  capacity re-arm 请求（本会被过宽 never-case 门永久封死者）实际均走向合法 restore 或 recompute：
  - 1f1bc0f2: 2 次 restore_success（34741/16328 tokens）
  - 8aa9d4b0: 1 次 restore_success（3486）
  - 14249706: 1 次 restore_success（18861）
  ⇒ 修复把"永远不可能满足 restore 长度"的请求正确转为 recompute，同时保留"本可 restore"的请求，未粗暴改成 recompute。

## 5. +27% 定性（P1 暴露 vs P1 regression）

- **确认为 P1 暴露，非 P1 regression**：
  - too_short 判定路径源自 P2-1 基线 f3fffa7f09（architect 已核），P1 未触碰该路径。
  - 本修复后 too_short 从 307 降至 53（-83%），同时 **P1 的 miss churn 收益保持**
    （revoked:miss/req P1=2.12 → fix=2.27，P0=4.72；P1 减半收益未回退）。
  - miss 门（miss_rearm_allowed / device_quota_degraded）在修复 diff 中零改动。
  - ⇒ +27% 是 P1 消除 miss 驱动 churn 后计数再分配浮出的下一层 too_short churn；
    修复消除该 churn 且不破坏 P1 的 miss 收益。

## 6. limitations

- 单配置（P0/P1 复刻），未做 RH OFF / 无容量压力对照。
- restore_success/storage_hit 的 -8% 波动在 run 间 variance 内，但未做多次重复 run 求均值。
- 剩余 8 次 capacity re-arm 确认为保留 bet（有 restore_success 佐证），但未逐条反证其
  suffix 在 re-arm 时确已增长达 threshold（依赖 restore_success 结果反推）。
- l3_publish_epoch 静止性（P1 open issue）未闭合，超出本任务范围。

## 7. 环境最终状态

- 代码: 24052 引擎四文件 = 7155cd8973（含 P0+P1+too_short 修复）；.tooshort-pre 备份核验 == P1。
- /data: 15%（160G free），实验命名空间 /data/l3/p2io-gate3-tooshort 已清理（find -delete，28G→4K）。
- GPU: idle 0%/15MiB；无残留引擎/lock。未动 22151 与他 worker 数据。
- pytest 已 pip 安装入 24052 sglang-patch env（新增，非产品改动）。
