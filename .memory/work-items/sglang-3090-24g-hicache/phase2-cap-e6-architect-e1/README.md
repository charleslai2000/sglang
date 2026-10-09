# phase2-cap-e6-architect-e1

- **工作标题：** phase2-cap-e6-architect-e1
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-cap-e6-architect-e1.md`：**
- Agent: architect
- Epoch: 1
- Date: 2026-09-07
- Scope: **纯设计/数学**。按 tester e3 实测（T=10.78 GiB）+ orchestrator 裁决（hicache_ratio 1.5→1.3）重推 ② ratio sweep 档表、r* 推荐、boot-verify 检查表、与 Gate D 衔接、重标定记录。不跑 GPU、不改产品代码、不写驱动。
- 触发规则：协议 §②.1/§②.4"偏差 >10% → 重标定再推档"（protocol-e1:157,285）+ ledger:2554-2558 裁决。
---

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-cap-e6-architect-e1.md`：**
1. **② 的更新回答**：在 T=10.78 GiB、hicache_ratio=1.3 下，扫 `--mamba-full-memory-ratio`，**满足 KV 池 ≥499,200（480K+4%）∧ mamba slots≥51（c8 实测需求）∧ c8 活性不降 的 ratio 区间 = [0.30, 0.43]，推荐 r*=0.43**（非整 0.05 档，落在判据带内，允许）。r*=0.43 → **KV 池 ≈501,851 tokens（480K×1.046，+4.6% 裕量）**、**mamba ≈66 slots**、c8 活性安全、**total host ≈14.91GB（预算 16.7，余 ~1.79GB）boot 可行**。
2. 原协议 r*=0.33（区间 [0.30,0.45]）基于 T=9.45 GiB 假设，重标定后**已失效**：r=0.33 实测池 ≈536K 远超目标带且 mamba 仅 55 slots（仍 ≥51 可用，但偏离"最大留白给 mamba"的经济性）；r=0.44 以上 KV 池跌破 499K 阈值。**r* 上移是 T 实测更大的必然结果**（T↑ → 同 r 下 KV 池更大 → 达阈值的 r 可更高）。
3. **host 墙已解除**：ratio 1.3 下 total host ≈14.91GB < 预算 16.7GB（裕量 1.79GB）→ 全档 boot 可行（含 C0 控制档，原先 1.5 下 C0 失败）。host 池为 **ratio-invariant**（=1.383×device sum 恒 14.91GB），故不改变 ② 判定（device 侧 verdicts 不受影响，ledger:2554）。
4. **③ ④ 衔接**：③④ 继承 r*=0.43 的 engine 配置（KV≈502K、mamba≈66、graph bs8、c8、RH OFF、L3 200G、memory-computed 池）；L2 host 池 ≈1.3×device KV ≈ 652K tokens，**覆盖 active working set 440-480K 的 1.36-1.48×，L2 余量充足**支撑 ③④ 的 host-ready/restore 实验。
---

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-cap-e6-architect-e1.md`：- 本报告：`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-cap-e6-architect-e1.md`
- 已读输入：`work/phase2-cap-e3-tester-e1.md`（实测锚点）、`work/phase2-cap-protocol-architect-e1.md`（原协议/标定规则）、`ledger.md:1587-1591`（host-RAM 墙 478K 先例 + 显式 size 下 ratio NO-OP）、`ledger.md:2488-2536`（4 Gate 权威版）、`ledger.md:2545-2558`（e3 阻断 + orchestrator 裁决选 A）…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-cap-e6-architect-e1.md` → `.memory/phase2-hicache-design/work/phase2-cap-e6-architect-e1.md`; SHA256 `d5d980f298fd0bf1889c104d46dd7a6f15c4dc895fff448144e4b25ec998bbe8`; source state `tracked`
