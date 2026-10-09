# phase2-cap-e3-tester-e1

- **工作标题：** phase2-cap-e3-tester-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-cap-e3-tester-e1.md`：**
- Agent: tester
- Epoch: 1
- Date: 2026-09-07
- Target: `ssh -i /home/charles/.ssh/id_ed25519 -p 24052 root@175.155.64.171` (RTX 3090 24G, 31GB host RAM, Qwen3.5-9B-w4a16)
- Repo deploy: `/root/sglang-b1-continuity` @ 9c9e7b7c7c（scheduler md5 495b8851 == 本地 /home/charles/Workspaces/3rdparty/sglang-3090-24g-opt HEAD；kv_cache_configurator 62b040e4 同）
- 任务域：**只做** ② ratio sweep（C0-C4+可选 C5）。**未跑 ③④**；未改产品代码（新增 3 个配置/驱动脚本）。
---

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-cap-e3-tester-e1.md`：- 远程：`/root/evidence-cap-sweep/calib/`（c0-engine.log、c3-engine.log、CALIBRATION.txt、status logs）；`/root/cap_ratio_driver.py`、`/root/direct-launch-cap-ratio.sh`、`/root/cap-ratio-run.sh`
- 本地副本：`work/evidence-cap-sweep-calib/`（同内容）+ 本报告同目录 3 个脚本。
- 源码佐证：`kv_cache_configurator.py:2124-2157`（ratio 预算/分档式）、`:2075-2081`（显式 size 绕过 ratio）、`pool_host/base.py:51-58`（PSUTIL_AV 预算 = available - 10GB 保留）、`pool_host/{base,mamba}.py:84,101`（host=×ratio，超额 raise）、`hybrid_pool_assembler.py:729-733`（mamba host 按 device×ratio）。
- ledger 权威先例：ledger.md:1589-1591（host RAM 31GB 是 KV pool 瓶颈，max 478K，479+ 失败于 available 波动 4.25-4.99GB）。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-cap-e3-tester-e1.md` → `.memory/phase2-hicache-design/work/phase2-cap-e3-tester-e1.md`; SHA256 `a49e9f169b1966801a2ff25ac8006d7b72a73445a75cca5ce0e8c729c4d1bf98`; source state `tracked`
