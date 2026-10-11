# p2io-tester-e7

- **工作标题：** p2io-tester-e7
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-tester-e7.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-tester-e7.md`：**
**判据逐条（9 条）**：
| # | 判据 | e7 实测 | 对照 e5 | verdict |
|---|---|---|---|---|
| 1 | B_ep ≤1.2s 无回归（B_fin 亦报） | B_ep full n=5 p50=1.382s；B_fin full n=22 p50=1.176s p90=1.777s max=3.294s | B_fin 1.158/1.720 (n=15)；B_ep 1.146 | **FAIL（边际）**：B_fin 口径无回归（+0.018s，读路径正常）；B_ep +0.236s 超 1.2s 门，n=5 样本过小 |
| 2 | 守恒/0 crash/0 OOM/0 backup fail/sha16 无新分歧 | 守恒 True；crash 0；OOM 0；backup fail 0；**sha16 6 个全新家族值** | e5：分歧全在已知家族 | **FAIL（sha16 子项）**：6 新值含 2 个 4-run 稳定 tag 被打破，a1-t12-restore 输出与 a1-t1-grow 相同（异常身份）；其余子项 PASS |
| 3 | A−B 逐样本 p90 ≤2s | full n=5 p50=13.371s p90=21.910s；all-ep p90=53.700s | 32.495/40.279 | **FAIL**（数值优于 e5 但 >2s 门 10×；且 full-chain 样本崩塌 15→5） |
| 4 | A p90 ≤3s | full p90=22.611s；all-ep p90=53.795s max=146.969s | A(issued) p90=10.66s | **FAIL** |
| 5 | ready_pool ≥2 稳态 | frac>=2 = 1/136 = 0.7%；time>=2 = 0.0%；size dist {0:68,1:67,2:1} | — | **FAIL**（watermark=[2,4] 稳态从未形成） |
| 6 | PREFETCH_BUDGET WAIT 驻留 p90 秒级 | **0.561s**（n=4732，max=18.181s） | 29.264s | **PASS**（唯一显著胜利：29.3s→0.56s） |
| 7 | READY→准入间隔≈0；READY 先于非 READY 样本>0 | 36 次 READY→准入（22 有后续 finish，样本存在）；但 162/198 READY 转入 WAIT_CAPACITY（82% 被拒，间隔 p50=0.01s/p90=6.77s）；准入间隔不可直接测（prefill 批日志无 rid） | — | **FAIL**：READY 未转化为准入，M4 分区无真实池可重排；子项 2 数值满足但机制未生效 |
| 8 | 投机 eviction = 0 | horizon 路径 0 evict（`ready_horizon.py` 无 evict 调用，M2 静默 decline）；系统级 hollow_evict 12 / forced_drop 6 | 4/2 | **PASS（直接）+ 注意**：间接驱逐升高（spin 流量推高设备压力），非 horizon 直接调用 |
| 9 | lookup/rid 主体 ≤2–3 | p50=9 p95=70 max=1289（92 rid，51% ≤9） | p50=3 p95=7 max=35 | **FAIL** |…（节选；见来源报告）

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-tester-e7.md`：- 实验 run-20260901-094745（3090，driver rc=0）：
  - 引擎日志 `/tmp/p2io-e7/engine-p2io-m4t-e7.log`（5.4MB / 37876 行，含 [P3] 事件）
  - 证据 `/tmp/p2io-e7/evidence/`（agent-1..8.json / runs.csv / mid-run-metrics.txt）
  - fd/io 前后对照 `p2io-m4t-e7-fd-before/after.txt`、`-io-before/after.txt`
- 对比基线 e5：`/tmp/p2io-e5/engine-p2io-m4t-e5.log`（+ evidence）
- 分析工具：`3090-dev/metrics/metric_compare.py`（双口径）、`/tmp/p2io-e4/analyze_p2a.py`、`/tmp/p2io-e4/p3_analyze.py`、本会话内联解析脚本（事件流直析）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-tester-e7.md` → `.memory/phase2-hicache-design/work/p2io-tester-e7.md`; SHA256 `088e4b2305ea18e40d68b3b6769955619c7c3669bc300874142e6a50fec9361e`; source state `tracked`
