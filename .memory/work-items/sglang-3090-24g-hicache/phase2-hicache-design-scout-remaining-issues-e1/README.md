# phase2-hicache-design-scout-remaining-issues-e1

- **工作标题：** phase2-hicache-design-scout-remaining-issues-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-scout-remaining-issues-e1.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** .../.memory/phase2-hicache-design/context.md

**`phase2-hicache-design/work/phase2-hicache-design-scout-remaining-issues-e1.md`：**
> 判定口径：仅列真实剩余 OPEN / DEFERRED；凡被 Gate-2(64G)/Gate-3(A/B soak / A' 决定性) 证伪或覆盖的旧问题一律不重开（见 §"被覆盖项"）。类型：OPEN=未闭合缺陷/未决问题；DEFERRED=已量化但推迟的性能优化/配置决策/方法论。
| # | item | 类型 | 当前状态描述 | 证据指向 | 为什么仍成立（未被证伪/覆盖） | 建议下一步 |
|---|---|---|---|---|---|---|
| 1 | RH 容量压力下 READY/DEVICE_QUOTA 恢复冻结 | OPEN（deferred known issue） | RH ON 时首 recycle 后 ready_pool 永久停止、restore 进入 WAIT_CAPACITY(reason=DEVICE_QUOTA) 永不释放 → restore_success→0、storage_hit 冻结（B 218,883 永久停 vs A 线性到 7.08M）；B 36,527 recycle vs A 6,513 | rh-ab-e2 §5/§6.5（B ready_pool per-60s `[4,30,3,0,...]` last=+121.7s；restore_success last=+121.1s；WAIT_CAPACITY 全程 bins）；ledger L1034/L1041-1047；baseline §6；context.md | A' 实验只裁决出"RH 状态机无独立缺陷"，并把 root cause 收敛到"RH+capacity-pressure thrashing feedback"，但**恢复链死锁的具体实现缺陷未闭合**；用户封板明确列为 Deferred known issue（rh-recovery-bug backlog），非覆盖 | 仅当"以后真有必要再修"时按 rh-recovery-bug 建档；当前不阻塞生产（RH=OFF） |
| 2 | RH ON 早 recycle 根因（30.4 vs 81.6 GiB 硬矛盾） | OPEN（deferred，未解释） | RH OFF 首 recycle 81.6 GiB vs RH ON 30.4 GiB，但共同 clean window 内 extent_write 仅多 1.07x（28.7→30.7GB）→ 不能简单归因写放大；RH ON 更早触达容量的机制未闭合 | rh-ab-e2 §4-5（A +314.5s/81.6GiB vs B +126.5s/30.4GiB；共同窗口 extent_write 1.07x）；ledger L1042（"硬矛盾（未解释）"）；baseline §6 | 写放大只解释 7%，大头缺口（81.6/30.4≈2.7x）未解释；Gate-3 早期 5.7x recycle 归因（closeout §3.2）在 A' 共同窗口下被收敛到 1.07x，但**早 recycle 本身仍无完整机制** | 属 rh-recovery-bug / Followup 2（写放大量化），本轮不做；若要闭合需容量充足场景复测以区分"RH 固有写放大" vs "recycle 反馈放大" |…（节选；见来源报告）


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-scout-remaining-issues-e1.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-scout-remaining-issues-e1.md`; SHA256 `8f39237fd495a3f2267b3bfee0c904fc686c7ec84af2ee3145e31ce8a28446aa`; source state `tracked`
