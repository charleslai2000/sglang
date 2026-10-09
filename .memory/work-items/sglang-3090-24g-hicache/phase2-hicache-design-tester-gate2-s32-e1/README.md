# phase2-hicache-design-tester-gate2-s32-e1

- **工作标题：** phase2-hicache-design-tester-gate2-s32-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-tester-gate2-s32-e1.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-tester-gate2-s32-e1.md`：**
**诚实结论：本轮并未真正测到 pool saturation cliff，因为池从未饱和。**
- pool=32 已配置并确认（engine log `max_mamba_cache_size: 32`，ssm_state 1.55GB），但 gate2 K=8 负载（8×4=32 distinct chain 的**假设**）并没有把设备 mamba 池压到满——`mamba_evictable` 峰值仅 22/32（69%），末态 available=27。**agents×4 的"32 distinct"并不等于"32 个同时在设备池存活的 checkpoint"**；实际并发存活远低于假设。
- 在此 69% fill 下：L0 exact-restore=0.9683（≥0.95）、recycle=0、无全冷 0-hit 断崖；class-A（storage>0 revoked:miss）16/54 ≈ 30%，与 106-pool K8 的 33% 量级一致——**没有随池缩小而放大成 cliff 的证据**，但也不能就此断言"无 cliff"。
- **因此"pool 接近 100% 是否出现结构性 cliff"仍未在真饱和下被回答。** 需要真正把 fill 压到 ~1.0 的负载（更多并发存活 checkpoint，而非只靠 distinct 链数假设），否则 32-slot 与 106-slot 都在~70% fill 下测得，无法区分池尺寸效应。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-tester-gate2-s32-e1.md`：- Remote run: `/root/evidence-gate2-s32k8/run-20260904-173540/` (verdict.json, runs.csv, mid-run-metrics.txt, metrics-final.txt) + `/root/engine-gate2-s32k8.log`；status `GATE2_s32k8_COMPLETE rc=0`（17:32:59→17:41:27，~8min）。
- Config confirmed in engine log: `Mamba Cache is allocated. max_mamba_cache_size: 32, conv_state size: 0.04GB, ssm_state size: 1.55GB`；ExtentFileBackend 64G/96G（slots=1430）。
- 注意：先前 tester 首次派发在分析阶段因 API 502 中断；orchestrator 从原始 remote 日志补完分析并出本报告。run 本身完整、无重跑。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-tester-gate2-s32-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-tester-gate2-s32-e1.md`; SHA256 `22a5c237a41416c66153214dc370cc6c4e6594abd961ac375c5c11b057f6e4e0`; source state `tracked`
