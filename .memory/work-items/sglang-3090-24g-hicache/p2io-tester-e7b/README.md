# p2io-tester-e7b

- **工作标题：** p2io-tester-e7b
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/p2io-tester-e7b.md`：**
done — **第一硬门全绿，后续门 2/8 通过、6 项 FAIL/未达标**；裁决：**第一门（spin 根除）PASS——M3 重做消除每 rid 1289 次 spin 是确证的；整体 FAIL 因为 A−B/ready_pool/full-chain 目标未达**

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/p2io-tester-e7b.md`：**
**第一硬门（M3 spin 根除）PASS 确证**：issued 2852→481（6×→1.04×基线）、每 rid max 1289→30（且 max 可解释为真实恢复轮次而非 spin）、lookup p50 9→4、restore_recompute 2660→348、ready_stage 6703→162（含 e4f681ed 类 1145 假尝试消失）、守恒 481=345+136。M3 causal negative-cache（e14）的 epoch 门+decline 语义根除了 e7 的逐 pass 重试空转——这是本轮最重要的正面结果。
**后续门 2/8 通过**（PREFETCH_BUDGET 驻留 0.561s、spec eviction=0、日志区分、sha16 新门），**6 项未达标**：ready_pool 从未 ≥2（M4 稳定分区没形成）、A/A−B p90 仍几十秒级（full-chain n=3 太稀）、B_fin 边际超 1.2s、full-chain 完成数 3（比 e7 5 更差）、lookup p50=4（略超 ≤2-3 但远好于 e7 9）。
**整体 FAIL**——spin 是根除了，但 M3 重做只消除了"重复 issue"这一病症，**没有让 ready_pool/全链完成/时延改善**：A−B 主表的 n_full 从 e7 的 5 掉到 3，等于"样本崩塌"依旧。机制推测（供裁决）：M3 门把 speculative prefetch 的**总量与时机**收得太紧（ready_stage 162 但全部 size≤1，从不攒到 watermark_high=4 的预算），READY 池从未真正堆起来——e14 修了 spin，却牺牲了地平线应有的吞吐填充。

### 报告列出的产物/证据
- `phase2-hicache-design/work/p2io-tester-e7b.md`：- 实验 run-20260901-115548（3090，driver rc=0）：证据 `/tmp/p2io-e7b/`（agent-1..8.json / verdict.json / runs.csv）+ 引擎日志 `/tmp/p2io-e7b/engine-p2io-m4t-e7b.log`（6736 行）
- 对比基线：e5 `/tmp/p2io-e5/`、e7 `/tmp/p2io-e7/`
- 分析工具：`3090-dev/metrics/metric_compare.py` 双口径、`/tmp/p2io-e4/analyze_p2a.py`、会话内联解析
- 部署验证：e14 5 文件 md5 双侧一致（ready_horizon 0b31644e / scheduler 351d42a0 / hicache_restore afe9f27a / unified_radix 140f2e73 / unified_tree a2ee7d10）；`.bak-e14-20260901/` 已隔离 5 旧版；`unified_radix_cache.py.tmp` 为 8-30 历史残留（非 .py 不导入）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/p2io-tester-e7b.md` → `.memory/phase2-hicache-design/work/p2io-tester-e7b.md`; SHA256 `cf81a6cd982f87c7be129fa087ede9aca317057df36bcaad7dd0b95b4191783e`; source state `tracked`
