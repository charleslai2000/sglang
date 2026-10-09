# phase2-p1-fix-tester-e1 — restore eligibility / admission re-arm churn 系统级集成验证（P1）

```text
status: done
artifacts:
  - 24052 引擎 P1 四文件同步: /root/sglang-b1-continuity/python/sglang/srt/
      managers/scheduler_components/hicache_restore.py
      managers/schedule_batch.py
      managers/scheduler.py
      managers/scheduler_components/ready_horizon.py
    (= 本地 opt repo commit 74246bb90f 同文件; 基线备份 .bak-preP1 四份,
     逐字节 == cc718c3c2e, 已核验)
  - 远程 P1 单元测试: 3090-dev/test_hicache_restore.py (84 passed) /
      test_hicache_restore_scheduler_feed.py (13 passed) /
      test_ready_horizon_unit.py (60 passed) / test_ready_horizon_partition.py (18 passed)
  - 远程 stress 证据: /root/evidence-gate3-p1fix/ (metrics-final / join.log /
      runs.csv / t38c-probe.log / gpu-util.csv / verdict.json) +
      /root/engine-gate3-p1fix.log
  - 本地分析副本: /tmp/p1check/{p0-engine.log,p1-engine.log,evid-p1/}
  - 本报告
evidence:
  - PASS Gate 逐条通过, 见 §3
  - churn 对比基线 (P0-fix run) 见 §4
  - forward recompute / device-hit 容量 re-arm / l3_publish_epoch 观测见 §5
summary: P1 成功消除 miss 驱动 churn; 发现一个非 P1 目标的 too_short 重算 churn, 见 §6
followups:
  - (open) too_short 驱动 DEVICE_QUOTA churn (307 次, 现为 P1 余量最大来源):
      restore length=15 反复 too_short→re-WAIT。独立于 P1 miss 门, 建议回 coder/architect 评估
  - (open) l3_publish_epoch 0.8/s 全局前移 → miss 门在实际负载退化为 epoch-only 判据,
      且 epoch 随并发写 ACK 前移, 可能过放 re-probe (architect open issue 1 部分成立)
open_issues:
  - too_short 重算 churn (见 §6) —— 产品缺陷候选, 建议 coder/architect 评估
  - l3_publish_epoch 静止性: 非静止 (0.8/s), 但"无关链写回 bump 导致门放行过多"未闭合
```

## 0. 环境与代码前置（均核实）

- 机: 175.155.64.171:24052 (root), RTX 3090 24G; GPU 起始 0%/15MiB 空闲; /data 起始 15% (160G free)。
- 引擎 repo: 实为 `/root/sglang-b1-continuity` (editable install 映射, 非 git)。
- **代码同步核查 (P1 纯增量确认)**:
  - 将 deployed 四文件与本地 opt **基线 cc718c3c2e** 逐字节 diff → **四文件全部 IDENTICAL to baseline**。
  - 本地 HEAD (74246bb90f) 相对基线的 python/sglang/srt 变更 = **恰好 P1 四文件** (schedule_batch/scheduler/hicache_restore/ready_horizon, 122 insertions), 无其它。
  - ⇒ HEAD→deployed delta = 纯 P1 增量, 无任何额外差异。按授权同步四文件 + 两个 P1 测试文件。
  - 备份: 四文件基线副本 .bak-preP1 (位置正确, 已核验 == cc718c3c2e); P0 备份 .bak-preP0 保留未动。
- 同步后远程单元测试 (sglang-patch env, CUDA_HOME=.../nvidia/cu13):
  - test_hicache_restore.py: **84 passed**
  - test_hicache_restore_scheduler_feed.py: **13 passed**
  - test_ready_horizon_unit.py: **60 passed** (注: deployed 旧版缺 host_release 字段导致 32 error, 同步本地新测试文件后 60 OK)
  - test_ready_horizon_partition.py: **18 passed**
- 门函数在 deployed 模块复核: `miss_rearm_allowed` 同 epoch 同 gen → False (block); epoch 前移 / gen 变 → True; sticky MISS + rearm_allowed=False → NONE (不 WAIT); rearm=True → WAIT_CAPACITY。**逻辑正确且已 live**。
- 并发: 无 gate3 lock / 无残留引擎; 未动 22151; 只 24052。

## 1. stress 配置（复刻 P0 触发 churn 的配置）

- 驱动: `gate3_ab.sh --tag p1fix --agents 8 --launch /root/direct-launch-gate1-rhon.sh --rt 400 --budget 1800 --cmax 900 --max-size 200G --file-size 30G`
- 引擎: RH ON, write_back, L3 extent, MAX_SIZE=200G FILE_SIZE=30G, max_total_tokens=65536, hicache_ratio=1.5, 与 P0-fix run 一致。
- 结果: **COMPLETE rc=0**, 引擎存活满 1819.6s (verdict elapsed_s), 无崩溃, 无重启, 562 请求。

## 2. 是否消除 P1 目标 churn（miss 驱动 re-arm）

**是——miss 驱动 churn 基本消除。** 关键对比 (同一负载配置, P0-fix run 为 pre-P1 基线):

| 指标 | P0-fix (pre-P1) | P1 | 变化 |
|---|---|---|---|
| revoked:miss (definitive miss) | 2222 | 1159 | -48% |
| DEVICE_QUOTA WAIT | 1752 | 649 | -63% |
| 全部 WAIT_CAPACITY | 2010 | 929 | -54% |
| 紧循环 (<100ms 连续 DEVICE_QUOTA) | 523 | 223 | -57% |
| 受影响 rids | 471 | 240 | -49% |

- **P0 最差 offender (f53af88c)**: 68 次 `revoked:miss` —— churn 是 **miss 驱动** (P1 目标)。
- **P1 最差 offender (d1a84264)**: 68 次 `too_short` + **仅 1 次** `revoked:miss` —— miss 驱动 churn 消失。
- P1 全部 228~253 次 sticky-miss→WAIT[DEVICE_QUOTA] 转移: 经日志 epoch (prefetch_revoke 的 storage_generation == tree_core.l3_publish_epoch, 见 unified_radix_cache.py:3339) 追踪, 每次 re-arm 后的 restore 均落到**更高 epoch** (如 50→55→67→71)。未观察到同 epoch 同 generation 的 no-progress re-arm 循环。
- 本负载下 `session_generation` 恒 None (radix_native_session 未启用 → 门退化为 epoch-only), 故门判据 = epoch 前移。epoch 前移本身反映并发写 ACK 的 durability 推进。

## 3. PASS Gate 逐条

| Gate | P1 run | 判定 |
|---|---|---|
| 无崩溃 | 0 Scheduler exception, 满 1819.6s 存活 | **PASS** |
| correctness | 562/562 HTTP 200, finished=True, output_sha16 全非空 | **PASS** |
| 无 OOM | 0 真实 OOM (74 处匹配均为 libtorchcodec 启动 benign traceback) | **PASS** |
| 无 zero-progress | GPU avg 96.3% max 100%; last restore_success 12:41:27 (run 末 12:42:26) | **PASS** |
| 无 HTTP error | 0 非 200 | **PASS** |
| host→L3 与 restore progress | backuped_tokens=6,156,448; prefetched=1,062,478; restore_success=97; storage_hit 52 req | **PASS** |
| device-hit 容量 re-arm 不误伤 | device_hit>0 444 req; FRONTIER=215 PREFETCH_BUDGET=65 仍在 (Fix A 领域) | **PASS** |
| churn 消除 (miss 驱动) | 见 §2 | **PASS** |

## 4. 结论: P1 是否解除生产 churn 阻塞

**是, 部分解除 + 暴露一个独立新 churn。**
- P1 **解除了 miss 驱动的病态 churn** (revoked:miss 减半, 最差 offender 从 68 次 miss → 1 次 miss), 这是 dispatch 的核心目标, 达成。
- 但剩余 223 个紧 DEVICE_QUOTA 循环仍在, 其驱动从 miss 变为 **too_short 重算** (见 §6)。这是**非 P1 目标路径**, P1 未消除, 也不应被 P1 miss 门拦截 (它是 recompute 侧问题)。
- 生产 churn 的"阻塞性"方面 (miss 死循环无前进) 已解除: 所有 churn 请求均完成 (HTTP 200, wall 35-44s, 中位 22.6s)。

## 5. 专项观测

### 5.1 forward recompute 前进
miss 后请求走 forward recompute/admit 完成: 全部 562 完成; churn 请求 (f5e7, 97bda0, bbb3, d1a84, 92e2) 均 HTTP 200 finished=True, wall 35-44s。无饿死, 无零进度。

### 5.2 device-hit 容量 re-arm 不误伤 (Fix A)
444 req device_hit>0 正常; FRONTIER(215) 与 PREFETCH_BUDGET(65) 容量 re-arm 活跃; 有 storage_hit=30711 的请求正常完成。P1 miss 门未拦截纯容量/有效物材 re-arm。

### 5.3 l3_publish_epoch 静止性 (architect open issue 1)
- **非静止**: 全 run 0→1467 (401 个观测值), 速率 ~0.8/s。
- 意义: miss 门在本负载 = epoch-only 判据 (generation 恒 None), epoch 0.8/s 前移 → 门在秒级时间窗内即放行 re-probe。每次 re-arm 后确实落到更高 epoch (durability 在推进), 所以放行不是"无物材空转"。
- **未闭合**: 是否"无关链写回 bump 导致门放行过多 re-probe"仍未证伪 —— epoch 前移既可能来自本请求链的 durability, 也可能来自并发其它链的写 ACK。需 cache 侧区分 (建议 architect/更深诊断, 超出本验证边界)。

## 6. 新发现产品缺陷候选 (too_short 重算 churn)

- **现象**: 请求 restore 长度缩至 15 (prefetch_threshold=256 之下) 后, 反复 `RESTORING→restore_retry(capacity)→too_short(requested=15,granted=0)→WAIT_CAPACITY(DEVICE_QUOTA)` 紧循环 (16ms 间隔), 单请求最多 68 次, 期间 0 次 READY。
- **P1 影响**: P1 引入后 too_short 从 241 → 307 (+27%), 现为 churn 余量最大来源。
- **性质**: 非 miss 驱动, 是 recompute 侧恢复长度不足阈值导致的重复 re-arm。P1 miss 门不应也**不会**拦它 (状态非 MISS_RECOMPUTE 时 rearm_allowed=True)。
- **阻塞性**: 不阻塞 forward progress (请求最终 HTTP 200 完成), 但浪费调度/恢复周期, 是生产 churn 的剩余主体。
- **归因建议**: 此路径非 P1 范围; 属 restore length 判定 + 容量唤醒的组合。建议回 coder/architect 评估是否值得修 (可能涉及 prefetch_threshold 对 15-token 残段的处理, 或 DEVICE_QUOTA 唤醒条件)。

## 7. limitations

- miss 驱动 churn 的"同 epoch no-progress"判定基于日志中 prefetch_revoke 的 epoch 采样 + 门函数 live 复核, 非对 re-arm 时刻真实 l3_publish_epoch 的直接观测 (日志不打印该时刻值); 结论对"是否存在同 epoch 空转"是强证据, 对 epoch 放行的精确归因 (本链 vs 无关链) 未闭合。
- run 时长 1819.6s (满预算), 未做超长 soak; 晚期回归未覆盖。
- 只跑了一个配置 (P0-fix 复刻); 未做 RH OFF / 纯容量无 miss 的对照。

## 8. 环境最终状态

- 代码: 24052 引擎已含 P1 (四文件 = 74246bb90f; 基线备份 .bak-preP1 四份, 已核验 == cc718c3c2e); P0 保留。
- /data: 15% (160G free), 本实验命名空间 /data/l3/p2io-gate3-p1fix 已清理 (find -delete, 28G→4K)。
- GPU: idle 0%/15MiB; 无残留引擎/lock。未动 22151 与他 worker 数据。
