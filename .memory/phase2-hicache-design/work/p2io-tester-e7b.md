# p2io-tester-e7b — P3 3.5 round 2（e14 M3 causal negative-cache 重做）M4T 同配置复测

## status
done — **第一硬门全绿，后续门 2/8 通过、6 项 FAIL/未达标**；裁决：**第一门（spin 根除）PASS——M3 重做消除每 rid 1289 次 spin 是确证的；整体 FAIL 因为 A−B/ready_pool/full-chain 目标未达**

## artifacts
- 实验 run-20260901-115548（3090，driver rc=0）：证据 `/tmp/p2io-e7b/`（agent-1..8.json / verdict.json / runs.csv）+ 引擎日志 `/tmp/p2io-e7b/engine-p2io-m4t-e7b.log`（6736 行）
- 对比基线：e5 `/tmp/p2io-e5/`、e7 `/tmp/p2io-e7/`
- 分析工具：`3090-dev/metrics/metric_compare.py` 双口径、`/tmp/p2io-e4/analyze_p2a.py`、会话内联解析
- 部署验证：e14 5 文件 md5 双侧一致（ready_horizon 0b31644e / scheduler 351d42a0 / hicache_restore afe9f27a / unified_radix 140f2e73 / unified_tree a2ee7d10）；`.bak-e14-20260901/` 已隔离 5 旧版；`unified_radix_cache.py.tmp` 为 8-30 历史残留（非 .py 不导入）

## evidence

### 0. 实验事实
- 96/96 turns，0 failed，4 downgraded，elapsed 583.4s；GPU 15 MiB 归零、残留仅系统服务（supervisord/fail2ban/jupyter）、dmesg OOM=0

### 1. 第一硬门（M3 spin 根除）—— PASS
```
issued/rid:  n_rids=93 p50=4 p90=10 p95=12 max=30
             dist={1:20, 2:8, 3:9, 4:10, 5:11, 6:11, 7:5, 8:5, 9:1, 10:5, 12:3, 13:1, 14:2, 16:1, 30:1}
total issued = 481   (e5 ~463, e7 2852)
revoke=345  recompute=348  io_finished=136  ready_stage=162
conservation: 481 == 345 + 136 -> True
```
- **max=30 且可解释**：max rid 34ef383f 的 30 次 issue 中仅 6 次 revoke（miss），**24 次是 io_finished/finalize（真实恢复轮次，mode=cache，跨 94s 累计恢复多 level 前缀）**；最终 RECOMPUTE 因 prefetch_length=34812 只拿到 976 tokens（hybrid_discard）——超长链 L3 未覆盖，非空转。issue 间隔 median 1.77s（e7 spin 是 ~141/s）
- **ready_stage 162 次 vs issued 481**：M3 重做后的 epoch 门（event-driven + 5s 安全 reconcile）实际限速生效；不再有 e4f681ed 类 1145 次 ready_stage/1 次 issue 的假尝试

### 2. 后续门逐条
| # | 判据 | e7b 实测 | 对照 e5/e7 | verdict |
|---|---|---|---|---|
| 3 | ready_pool ≥2 稳态 ≥50% | **size 分布 {0:56, 1:56}，无 size≥2 事件**（watermark=[2,4] 从未触发） | e7 {0:68,1:67,2:1} | **FAIL**（M4 稳定分区仍未形成） |
| 4 | A p90 ≤3s；A−B p90 ≤2s | A_ep all-ep p90=45.129s max=93.569s；full p90=70.669；A−B full p50=21.026 p90=69.292 | e7 A p90 53.8 / A−B 21.9 | **FAIL**（full-chain 样本 n=3 太小不可比） |
| 5 | B_ep/B_fin ≤1.2s 不回退 | B_fin full n=9 p50=1.289 p90=1.796 max=1.968；B_ep full n=3 p50=1.224 | e5 1.158/1.720；e7 1.176/1.777 | **FAIL（边际）**：B_fin +0.13s vs e5、+0.11s vs e7，仍 ≤1.8s 内但超 1.2s 门 |
| 6 | PREFETCH_BUDGET 驻留 ≈0.56s | **p50=0.561s**（n=51，p90=4.236，p95=6.269，max=54.913） | e7 p50=0.007s（受 spin 干扰）；e5 1.300s | **PASS**（M1 未回退，p50 与 e5 同量级更优） |
| 7 | spec eviction = 0 | horizon 路径 0 evict；系统级 hollow_evict+forced_drop=13 | e7 18，e5 6 | **PASS（直接）** |
| 8 | full-chain 完成数恢复 ≥15 | **full≥20k = 3**（no_finish_episodes=58） | e7 5，e5 15 | **FAIL**（比 e7 更差） |
| 9 | ready_stage attempted vs issued 日志区分 | **生效**：`evt=ready_stage ... result=issued state=RESTORING ready=N headroom=N`（含 result 字段） | e7 无 result | **PASS**（观测改进在位） |
| 10 | 守恒/0 崩溃/0 OOM/0 backup fail；sha16 新门 | 守恒 True；crash 0；OOM 0；backup fail 0；**sha16：e7b 4 个 payload 出现从未见过的值，均属 fresh-compute 家族（e8 规律），无跨身份换位/无仅 restore 专属新值** | — | **PASS**（sha16 新语义门满足） |

### 3. 双口径指标表（metric_compare.py）
```
run      n_full  B_fin p50/p90   B_ep p50/p90     A_ep p50/p90          A-B p50/p90/p95/max   lookup p50/max cons
e5           15    1.158/1.720    1.146/1.402    34.415/41.632   32.495/40.279/41.867/41.867           3/35 True
e7           22    1.176/1.777    1.382/1.796    14.553/22.611   13.371/21.910/21.910/21.910           9/1289 True
e7b           9    1.289/1.796    1.224/1.377    21.588/70.669   21.026/69.292/69.292/69.292           4/30 True
```

### 4. WAIT 驻留（e7b）
```
DEVICE_QUOTA: n=285 p50=3.012s p90=7.328s max=40.760s
FRONTIER:     n=46  p50=0.449s p90=0.566s max=0.633s
PREFETCH_BUDGET: n=51 p50=0.561s p90=4.236s max=54.913s
```

## summary
**第一硬门（M3 spin 根除）PASS 确证**：issued 2852→481（6×→1.04×基线）、每 rid max 1289→30（且 max 可解释为真实恢复轮次而非 spin）、lookup p50 9→4、restore_recompute 2660→348、ready_stage 6703→162（含 e4f681ed 类 1145 假尝试消失）、守恒 481=345+136。M3 causal negative-cache（e14）的 epoch 门+decline 语义根除了 e7 的逐 pass 重试空转——这是本轮最重要的正面结果。

**后续门 2/8 通过**（PREFETCH_BUDGET 驻留 0.561s、spec eviction=0、日志区分、sha16 新门），**6 项未达标**：ready_pool 从未 ≥2（M4 稳定分区没形成）、A/A−B p90 仍几十秒级（full-chain n=3 太稀）、B_fin 边际超 1.2s、full-chain 完成数 3（比 e7 5 更差）、lookup p50=4（略超 ≤2-3 但远好于 e7 9）。

**整体 FAIL**——spin 是根除了，但 M3 重做只消除了"重复 issue"这一病症，**没有让 ready_pool/全链完成/时延改善**：A−B 主表的 n_full 从 e7 的 5 掉到 3，等于"样本崩塌"依旧。机制推测（供裁决）：M3 门把 speculative prefetch 的**总量与时机**收得太紧（ready_stage 162 但全部 size≤1，从不攒到 watermark_high=4 的预算），READY 池从未真正堆起来——e14 修了 spin，却牺牲了地平线应有的吞吐填充。

## followups
1. **M4 分区失效（coder，下一优先）**：ready_pool 恒 ≤1 且 112 次日志都在 size 0/1 抖动——需要检查 ready_horizon 的 refill_plan 预算是否被 headroom 公式卡死（M1 里 host_headroom = available + ready_resident，而 ready_resident 在 pool 空时 =0，可能永远填不满 watermark_high=4）。位置：`ready_horizon.py refill_plan / _ready_host_headroom`。
2. **full-chain 完成崩塌（coder）**：n_full 5→3 比 e7 更差——M3 收紧后 speculative 覆盖不足，L3 温链恢复时差仍大（A−B p50 21s）。建议检查 prefetch 阈值/时序是否与 M3 门冲突。
3. **B_fin 边际回归（coder）**：1.289 vs e5 1.158（+11%），n=9 偏小，需多轮确认是否为 M3 门引入的读取路径延迟。
4. **观测留存**：ready_stage result 字段（attempted vs issued 区分）e14 已生效——后续所有 P3 复测应保留此字段作标准。

## open_issues
- A−B 主表 n=3 统计不可靠（全链完成样本太少）；下一轮复测需先解决 n_full 崩塌才能让 A/A−B 门可判。
- ready_pool watermark 语义：watermark=[2,4] 在本轮从未达 2——不是"池形成后被消耗"，而是"池从未形成"，归因 M1 预算而非 M4 分区，需引擎侧日志确认。
- sha16 新语义门（payload→家族 multiset）已用于本轮；e8 建议的放宽断言（compare_sha16.py）尚未落地，本次按语义门人工判定 PASS。
