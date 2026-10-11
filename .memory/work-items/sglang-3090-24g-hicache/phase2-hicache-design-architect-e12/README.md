# phase2-hicache-design-architect-e12

- **工作标题：** phase2-hicache-design-architect-e12
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-architect-e12.md`：**
done — 只读设计完成（未修改任何引擎文件）。设计交付物
`/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-promotion-admission.md`（新文件，
因 p2-1-design.md 已有 §8 埋点/§9/§10，追加同名节会冲突）。核心决策：budget 检查并入既有
WAIT_CAPACITY[DEVICE_QUOTA]（零新状态）；检查点位于 load_back 入口（锁之前）+ _load_back_transfers
精确门（evict_for_alloc 之前）；reservation 计数器绑定 _OngoingLoadBack、ack 归还；唤醒复用每 pass
T11 谓词重读；margin 初始 2048（算术证明 0 不串行化 2×16K）。所有引用真实（file:line，当前工作树）。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
没有识别到明确的 Result/Conclusion；不能据报告存在或状态字段推定结果。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-architect-e12.md`：- 设计文档（交付物）: `/home/charles/Workspaces/homenet/server/gpu/3090-dev/p2-0/p2-promotion-admission.md`
  （§0 定稿语义逐条映射 / §1 不变量 / §2 现状核查 / §3 机制 / §4 交互 / §5 改动面 / §6 验证 /
  §7 Test B 顺序 / §8 风险 / §9 开放问题）
- 本报告: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-architect-e12.md`
- 引用基线: `p2-1-design.md`（M1/M2 定稿，§2 状态机 / §4 结构）、architect e11 报告（崩溃机制 /
  prefetch 预算先例）、tester e22（Test A K=16 现场）、当前工作树代码（M1b 已实现）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-architect-e12.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-architect-e12.md`; SHA256 `7bab7738c3ed33c46be8abda80f143a72e23700f729626ebf6cdba8c00aba3a3`; source state `tracked`
