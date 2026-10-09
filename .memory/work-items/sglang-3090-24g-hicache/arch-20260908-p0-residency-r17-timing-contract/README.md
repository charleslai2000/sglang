# ARCH-20260908-P0-RESIDENCY-R17-TIMING-CONTRACT

- **工作标题：** ARCH-20260908-P0-RESIDENCY-R17-TIMING-CONTRACT
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
基于 r17 residency 调试证据，为 P0.1 定义严格的 readiness-to-residency 生命周期，解决祖先节点错误进入 pending、组件值仍在时误判、触发依赖轮询及释放队列/发布时序未闭合等问题，并给出可审计的确定性与 live 验收条件。

## 实际改了什么
只读架构审查；报告明确唯一写入是本备忘录。没有修改产品/测试/vehicle 源码、远端主机、live process 或 evidence bundle。文中所列代码路径、r17 实现缺陷及测试产物清单均为分析对象或后续建议，不是本工作改动。

## 生成结果与验收
交付 P0.1 readiness-to-residency 契约建议：仅已注册的精确非 root 最终 build 节点可进入 residency 生命周期；生命周期按 `BUILD_CREATED → DETACH_SEALED → DURABILITY_READY → FREES_COMPLETE → QUEUES_EMPTY → RESIDENCY_PUBLISHED → WARM_VISIBLE` 有序推进；组件 device/host 值、精确 free token 和 release queue 状态均须满足，且 reconcile 应由状态转换事件触发。报告同时限定单次 release、诊断有界、额外 warm-hit 组件 fail-closed，并要求 deterministic gate 后再进行指定 live run。结论是供 orchestrator 接受/修订的架构建议，不授权实现，也不等于 gate 接受或运行时通过。

### 报告列出的验收证据（建议）
报告要求未来 tester 的 immutable bundle 包括 source/config/trace digest、identity lifecycle、diagnostic bounds、pending snapshots、component blockers、queue transitions、build/warm、barrier waits、reducer result 与 verdict；当前架构工作没有生成这些运行证据。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/ARCH-20260908-P0-RESIDENCY-R17-TIMING-CONTRACT.md` → `.memory/phase2-hicache-design/work/ARCH-20260908-P0-RESIDENCY-R17-TIMING-CONTRACT.md`; SHA256 `f23c53d596d586ac5b7224e3a8c7664a9664d5df7fc61aa95d2c8c6be43e8529`; source state `tracked`
