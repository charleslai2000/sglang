# phase2-p0-fix-tester-e1 — build_backup_spec assert 修复（P0）GPU 集成验证

```text
status: done
artifacts:
  - 24052 引擎统一化代码同步: /root/sglang-b1-continuity/python/sglang/srt/mem_cache/unified_radix_cache.py
    (= 本地 opt repo commit cc718c3c2e 的同文件; 原文件备份为 unified_radix_cache.py.bak-preP0)
  - 远程 P0 unit 测试: /root/sglang-b1-continuity/3090-dev/test_backup_spec_assert_fix.py (5/5 通过)
  - 远程 stress 证据: /root/evidence-gate3-rhfix-p0fix/ (metrics-final / join.log / runs.csv / t38c-probe.log / gpu-util.csv / verdict.json)
  - 远程引擎日志: /root/engine-gate3-rhfix-p0fix.log
  - 本报告: .memory/phase2-hicache-design/work/phase2-p0-fix-tester-e1.md
evidence:
  - PASS Gate 逐条通过, 见下 §3
  - 新计数器来源确定性归因 (3 场景), 见下 §4
  - str-fx2 基线对照 (原崩溃) 见下 §5
summary: 见下
followups:
  - 可选: 对同一代码在更长 soak (如 2h) 下复跑以确认无晚期回归 (本 1834s run 已满预算, 无崩溃)
  - 可选: 把 P0 两个计数器暴露到 /metrics (当前为内部计数, 不可从外部观测), 以便长期观测
open_issues:
  - 4 处 "KV subtree dropped without backup due to host memory pressure" 为 write_back
    host 压力下的既有 eviction 行为 (hicache_dropped_tokens_total kv host_pressure=63890 对应),
    非 silent drop / 非 P0 崩溃路径; 在 str-fx2 基线亦有 144 次同类 drop, 非本修复引入
```

## 0. 环境与代码前置（均核实通过）

- 机: 175.155.64.171:24052 (root), RTX 3090 24G; GPU 起始 0%/15MiB 空闲; /data 起始 15% (160G free)。
- 引擎 repo: 实为 `/root/sglang-b1-continuity` (editable install 映射, 非 git), **非 dispatch 所称 `sglang-3090-24g-opt`**。
- **代码状态核查**: 24052 已部署引擎**不含** P0 守卫计数器
  (`grep _storage_gap_skipped_d2h_count` 在 4 份 deployed 副本全为 0), 且**无该 commit**。
  - 本地 `sglang-3090-24g-opt` repo 有 commit `cc718c3c2e` (P0 修复, 只改 unified_radix_cache.py)。
  - 将 deployed 的 unified_radix_cache.py 与本地 opt 同文件 diff: **仅 3 处 P0 修复 hunk (纯增量)**, 其余逐字节一致
    (unified_tree_core.py / scheduler.py 亦与本地 opt 一致; ready_horizon/hicache_restore 路径名不同但属 Fix A/B, 均已应用:
    DEVICE_QUOTA_MAX_TIMEOUTS=2, host_release 存在 —— 与 str-fx2 "fixed" 配置一致)。
  - 按任务授权 "若不在需同步/应用": 已把本地 opt 的 unified_radix_cache.py 同步到 24052
    (备份原文件为 .bak-preP0; 新 md5=102f08d1a4648829174f846e621f99f8 = 本地 opt 一致)。
- 同步后:
  - `python 3090-dev/test_backup_spec_assert_fix.py` → **5/5 OK** (在 deployed patched 模块上跑通)。
  - 导入检查: `_storage_gap_skipped_d2h_count += 1` / `_storage_gap_skipped_nokv_count += 1` /
    `get_component_device_value` 均在 `write_backup_storage` 中确认存在。
- 并发: 无其它 gate3 lock / 无残留引擎; 未动 22151; 只 24052。

## 1. stress 配置（完全复刻 str-fx2 崩溃配置）

- 驱动: `/root/gate3_ab.sh --tag rhfix-p0fix --agents 8 --launch /root/direct-launch-gate1-rhon.sh --rt 400 --budget 1800 --cmax 900 --max-size 200G --file-size 30G`
- 引擎: RH ON (`--enable-ready-horizon`), `write_back`, L3 extent backend,
  MAX_SIZE=200G FILE_SIZE=30G, max_total_tokens=65536, hicache_ratio=1.5, 全与 str-fx2 一致。
- 结果: **COMPLETE rc=0**, 引擎存活满 1834.6s (verdict elapsed_s), 无崩溃, 无重启。

## 2. 是否复现原 assert

**未复现**。修复前 str-fx2 在同一配置下于 +1239s 崩溃
(`engine-gate3-rhfix-str-fx2.log:115925` `Scheduler hit an exception` → `unified_tree_core.py:2037 assert device_value is not None`)。
本 P0 修复 run 满预算 1834s, `build_backup_spec` / `assert device_value is not None` / `Scheduler hit an exception` 出现次数 = **0**。

## 3. PASS Gate 逐条（P0-fix run vs str-fx2 崩溃 run）

| Gate | P0-fix run | str-fx2 (原崩溃) | 判定 |
|---|---|---|---|
| build_backup_spec assert = 0 | 0 (Scheduler exception=0) | 1 (崩溃) | **PASS** |
| backup-path 继续 progress | restore_success 118, **最后 +1831s (11:47:01, run 11:47:49 结束)** | restore_success 59, +1003s 后停滞 | **PASS** |
| host→L3 backup 正常 ACK | backuped_tokens_total=6,129,228 (extent); extent_write=9786; prefetched=1,156,135 | extent_write=5364 | **PASS** |
| 无 subtree silent drop | forced_drop=0; restore_recompute=0; 无 silent drop | forced_drop=125; recompute 缺失 (崩溃) | **PASS** |
| correctness | 568/568 HTTP 200, finished=True, output_sha16 全非空 | 3232 请求含 2863 崩溃后失败 | **PASS** |
| OOM | 0 (无 CUDA out of memory / RuntimeError; grep "OOM" 为 headroom 误匹配) | - | **PASS** |
| zero-progress | t38c 持续写链到 ts 1788666461.9 (~run 末); GPU avg 96.75% | - | **PASS** |
| HTTP error | 0 (全部 200) | 2863 connection refused | **PASS** |

- 补充: 4 处 "KV subtree dropped without backup due to host memory pressure" (11:18-11:20) 为
  write_back host 压力下的既有 eviction 行为, 对应 `hicache_dropped_tokens_total kv host_pressure=63890`;
  str-fx2 基线同配置有 144 次同类 drop → **非本修复引入, 非 silent drop**。

## 4. 新计数器来源分析（确定性归因, 驱动真实 deployed 模块）

用 stub sink 驱动真实 `write_backup_storage` gap-fill (同 coder unit 方法, 在 24052 patched 模块上跑):

| 场景 | gap 节点状态 | D->H | L3 | d2h_skip | nokv_skip | 结论 |
|---|---|---|---|---|---|---|
| S1 device-present | device有/host无, unbacked | 进 D->H | 随后 L3 | 0 | 0 | 原合法路径, 不回归 |
| S2 host-only | device无/host有 | 跳过 D->H | 由 host 直写 L3 | 0 | 0 | 守卫不触发, 正确路由 |
| S3 both-absent | device无/host无 (forced-miss tombstone/hollow) | 跳过 | 跳过 | **1** | **1** | **正是 pre-fix 崩溃态, 被两守卫拦截+计数** |

→ 守卫拦截的正是 architect e3 判定的崩溃链节点 (both-absent), 来源 = storage-gap 中
device+host 双缺的 forced-miss/hollow 节点; device-present 正常 D->H 与 host-only 正常
storage-write 路径均不误伤。

## 5. 结论

**P0 解除 P1/Fix A stress 阻塞。** 在完全复刻 str-fx2 (RH ON + 纯容量耗尽 + write-back + L3 extent)
的配置下, P0 修复 run 满 1800s 预算存活、无 build_backup_spec assert、backup-path 持续
progress (restore_success 活跃到 run 末)、host→L3 ACK 正常 (6.13M tokens)、forced_drop=0、
568/568 请求成功、无 OOM / zero-progress / HTTP error。原崩溃 (str-fx2, assert + 硬冻结 +
2863 请求失败) 未复现。守卫语义经确定性 3 场景归因确认只拦截预期 both-absent 路径。

## 6. 环境最终状态

- 代码: 24052 引擎已含 P0 修复 (unified_radix_cache.py = 本地 opt cc718c3c2e; 原文件备份 .bak-preP0)。
- /data: 15% (160G free), 我的命名空间已清理 (仅本实验自建数据); GPU: idle 0%/15MiB;
  无残留引擎/lock。未动 22151 与他 worker 数据。

## 7. limitations

- P0 计数器为内部计数, 未暴露到 /metrics, 故 stress 运行中无法从外部直接读数值;
  来源归因通过确定性 harness (真实模块 + stub sink) 完成。
- run 时长 1834s (满预算), 未做超长 soak; 晚期 (数小时) 回归未覆盖, 见 followups。
