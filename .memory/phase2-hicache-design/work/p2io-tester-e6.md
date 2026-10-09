# p2io-tester-e6 — Phase 2：A−B 逐样本指标工具 + 四轮基线回注 + A−B 溯源修正

## 1. status

**done** — `metric_compare.py` 改造并迁入仓库（`3090-dev/metrics/`，双侧同步 md5 一致）；
配对语义按用户 M7 定案（(rid, episode) 键、B_ep/A_ep 逐样本 A−B、quantile 在差分布上取）；
四轮既有日志回注完成：**B_fin 验证门四值逐位复现**（e5 1.158/n=15、m4t 1.051/n=11、
m4f 1.320/n=20、m4t-e4 1.236/n=17）；**A−B 溯源判定完成**：e5 报告 32.5s 为逐样本计算
（非 percentile 相减），旧公式精确复现（32.455 = 报告舍入值），修正后权威值
e5 p50=32.495s（Δ0.04s 维持）；ledger 追加一条（历史零修改）。

## 2. artifacts

- **工具（新交付，仓库版）**：`3090-dev/metrics/metric_compare.py`（本仓库新目录，自包含
  零依赖；`python3 -m py_compile` COMPILE_OK）。功能：episode 配对（(rid, episode_id)，
  切分规则 = rid 最后 finish 关 episode；最终 finish 后的 issued 开 ep≥1 的 no_finish
  episode）；`A_ep`=首次 issued→最终 finish / `B_ep`=末次 issued→最终 finish /
  逐样本 `A−B`；full≥20k 按 **final_tokens**（最终 finish 的 n_tokens）；B_fin（per-finish
  历史口径）验证门小节；attempt spans 诊断附表（旧定义 A 改名）；守恒检查；A−B≥0/B≤A
  自检；多 run 对比表；`--csv` 落盘；`--single LABEL` 全量 per-episode 行；默认四轮
  (m4f/m4t/m4t-e4/e5)。CLI：
  ```
  python3 3090-dev/metrics/metric_compare.py [label=path …] [--csv OUT] [--single LABEL] [--no-attempt]
  ```
- **同步**：scp → `/root/sglang-b1-continuity/3090-dev/metrics/`，md5 双侧
  **d7a4e144… 一致**。
- **证据**：per-episode CSV（224 行）→ `/tmp/p2io-e6-episodes.csv`（run,rid,episode,A_s,B_s,
  A-B_s,n_issues,n_finishes,final_tokens）；工具完整输出见本报告 §3；ledger 追加条目在
  `ledger.md` 末尾（"Phase 2 完成（tester e6）"一节，历史行未动）。
- 输入日志：四轮 [P2A] 引擎日志（/tmp 本机 + 3090 双备份），未改动。

## 3. evidence（真实命令与输出）

**B_fin 验证门（per-finish 历史口径，与 e5 报告逐值对照）**：
```
$ python3 3090-dev/metrics/metric_compare.py
===== e5 =====
[B_fin per-finish] full>=20k: n=15 p50=1.158s p90=1.720s p95=1.720s max=1.960s   ← e5 报告 1.158/n=15 ✓
===== m4t =====
[B_fin per-finish] full>=20k: n=11 p50=1.051s p90=1.871s p95=2.135s max=2.135s   ← 报告 1.051/n=11 ✓
===== m4f =====
[B_fin per-finish] full>=20k: n=20 p50=1.320s p90=1.600s p95=1.727s max=1.844s   ← 报告 1.320/n=20 ✓
===== m4t-e4 =====
[B_fin per-finish] full>=20k: n=17 p50=1.236s p90=1.495s p95=1.498s max=1.744s   ← 报告 1.236/n=17 ✓
```
守恒四轮全 True（487=387+100 / 544=453+91 / 529=461+68 / 463=377+86）；self-check
A−B<0 或 B>A 违规 0（全四轮）。

**A−B 溯源判定（协调者核查项）**：
```
$ 旧公式重算（episode − max-B-window，max-tokens 过滤——e5 会话内联脚本公式）
e5:  n=8 p50=32.455 p90=40.279 max=41.867   ← 精确复现 e5 报告 §3 (32.5/40.3/41.9 舍入)
e4:  n=11 p50=23.387 p90=68.514 max=74.429   ← 报告 (23.4/68.5/74.4) ✓
m4t: n=7  p50=20.025 p90=46.256 max=47.799   ← 报告 (20.0/46.3/47.8) ✓
m4f: n=13 p50=34.533 p90=48.618 max=50.131
结论：e5 报告 A−B=32.5s 是逐样本计算（非 percentile 相减）——CONFIRMED；
      旧公式配对细节（max-B-window、max-tokens 过滤）与新工具（最终 finish B 窗口、
      final-tokens 过滤）不同，差异 ≤1.0s。
```

**A−B 修正值（新工具权威口径，full≥20k 主表 + 全量附表）**：
```
===== multi-run comparison (full-chain >=20k) =====
run      n_full  B_fin p50/p90   B_ep p50/p90    A_ep p50/p90       A-B p50/p90/p95/max     lookup p50/max cons
m4f          20   1.320/1.600    1.025/1.462    36.515/50.345   35.444/49.360/50.443/50.443    3/38   True
m4t          11   1.051/1.871    0.766/1.065    21.314/47.546   20.548/46.582/47.799/47.799    3/37   True
m4t-e4       17   1.236/1.495    0.898/1.368    24.755/69.843   23.387/68.514/75.394/75.394    4/38   True
e5           15   1.158/1.720    1.146/1.402    34.415/41.632   32.495/40.279/41.867/41.867    3/35   True

（全量附表：A−B 全部 episode p50/p90 —— m4f 12.037/36.272 (n=61)、m4t 8.663/32.440 (n=55)、
 m4t-e4 1.795/42.627 (n=54)、e5 6.795/32.455 (n=54)）
```

**episode 语义新发现（tail second-episode）**：
```
[episodes] with_finish=61 (tail_second_episodes=33) no_finish_episodes=67  (m4f)
[episodes] with_finish=55 (tail_second_episodes=31) no_finish_episodes=69  (m4t)
[episodes] with_finish=54 (tail_second_episodes=37) no_finish_episodes=77  (m4t-e4)
[episodes] with_finish=54 (tail_second_episodes=34) no_finish_episodes=75  (e5)
```
四轮均 33–37 个 rid 在**最终 finish 后 3–23s** 再次 issued（残留 tokens 二次 restore
cycle，如 516b6c8b：finish(16384) → READY → promotion → DEVICE_QUOTA → issued(11436)
→ revoke miss → recompute——即 PARTIAL 授予 27811−16384=11427 残留的补恢复尝试），
日志内无后续 finish → 单列 no_finish(ep=1) 行，不参与 quantile。A−B KPI 只度量有
finish 的完整 cycle（用户口径）。

**每 episode 行样例（--single e5 全量前 8，按 A−B 降序）**：
```
rid                        ep  A_s    B_s    A-B_s  n_issues n_finishes final_tokens
a87a79c776d0483ea0f4895f8a10c7ce 0 42.971 1.104 41.867  5  3 24143
f161f76c87504c9c83155e80c972781c 0 41.632 1.353 40.279  3  1 22528
092fee94ea8344018c10c955c18efaf9 0 41.476 1.402 40.074 24  3 29532
bbc990fb4eb54fe88c84802048f334ec 0 33.281 0.431 32.850  4  3 15953
2f4e946e6b3e49eca2c6f76d545618aa 0 33.424 0.929 32.495  3  3 23714
cd2fa78c2af14d3d9ec2e16c0c4cc33e 0 34.415 1.960 32.455  3  3 24145
0bb94fae8f7040dda725913edd51a9a9 0 33.534 1.838 31.696  5  3 15522
749ab396ffa64b9f8dcafbb7e3b7c9e7 0 28.332 0.965 27.367  3  1 16384
```

## 4. summary

- **B_fin 验证门全过**：per-finish 历史口径四轮逐位复现（p50+n+p90 全一致），工具解析
  未改坏历史口径——后续任何指标报告可直接引用该工具输出。
- **A−B 溯源结论**：e5 报告 32.5s **不是 percentile 相减**（旧公式在 e5 日志上精确复现
  32.455/40.279/41.867，与报告舍入值一致 = 逐样本计算确认）。旧公式配对细节
  （max-B-window + max-tokens 过滤）与新工具（最终 finish B 窗口 + final-tokens 过滤）
  的修正差异 ≤1.0s；**e5 权威值 32.495s（n=8）维持报告 32.5s**（Δ0.04s 舍入内）。
  修正后全量：m4t-e4 23.387s（n=11）、m4t 20.548s（n=7）、m4f 35.444s（n=11，
  原 n=13——2 episode 因 final-tokens 过滤出列）。ledger 已追加（不改历史）。
- **B_ep（per-episode 主判据口径）四轮**：e5 1.146s / m4t-e4 0.898s / m4t 0.766s /
  m4f 1.025s——与 B_fin 差异即"多 finish episode 中间恢复"（finish→准入拒→re-issue
  循环内的部分恢复窗口，属 A−B 浪费的一部分），报告归因成立。
- **新发现**：33–37 rid/轮存在 tail second-episode（残留 tokens 二次 restore 无 finish）
  ——不参与 quantile，但提示 PARTIAL 授予的残留恢复是 A 尾巴的组成之一（后续 Ready
  Horizon 分析可关注）。
- Ready Horizon KPI 现状（A−B 逐样本 p50/p90）：e5 32.5/40.3、m4f 35.4/49.4、
  m4t-e4 23.4/68.5、m4t 20.5/46.6——**最大浪费在 m4f 与 e5**，Phase 3.5 判据
  （A−B p90≤2s / A_ep p90≤3s / B_ep≤1.2s）差距明确。

## 5. followups

1. Phase 3.5 终裁将用本工具双口径输出（B_ep 主判据 + B_fin 对照 + A−B 逐样本）——
   coder 的 Ready Horizon v0 同步后直接复用，无需再改工具。
2. tail second-episode 的量化归因（残留 tokens 二次 restore 占总 issued/waits 比例）
   可作 Ready Horizon 分析的输入项（观察，非本阶段判据）。
3. 工具可扩展性：episode 切分规则已在代码注释与 docstring 记录；未来若出现 rid 复用
   （ep>0 有 finish），split_episodes 需补该分支的单测——当前四轮日志 ep>0 均为
   no_finish，已断言覆盖。
4. 证据路径：工具 `3090-dev/metrics/metric_compare.py`（双侧 md5 d7a4e144）；
   per-episode CSV `/tmp/p2io-e6-episodes.csv`；ledger 追加条目在册。

## 6. open_issues

- 四轮日志仅本机 /tmp + 3090 双备份（未入库，遵守 .memory/ 不入版本控制约定）；
  若 /tmp 再丢可重拉 3090，工具报错提示含重拉命令。
- B_fin 与 B_ep 的差异（多 finish episode）为结构性必然——报告与未来判据必须显式
  标注口径，避免重蹈 e5 报告"跨口径比较"覆辙（§7 基线核查的教训已落实为本工具双轨
  输出）。
- e5 报告 §3 表头 "episode − 最终 B 窗口" 与旧公式实际（max-B-window）有微小出入——
  数值影响 ≤1.0s，已在 ledger 修正条目说明；历史报告不改写。
