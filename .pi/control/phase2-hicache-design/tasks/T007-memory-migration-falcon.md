# T007 — Falcon `.memory` 归属边界整理

Status: DONE
Work area: control
Objective: 确认 Falcon `.memory` 内容不并入 3090 authority，并将 durable 结论归入 Falcon 自有 control 体系。
Inputs: Falcon worktree 的 `.memory` 与已有 `control/G001..G004`。
Completion: Falcon 专属源码/测试/结论保持独立；共享旧 HiCache runtime artifacts 不作为 Falcon source authority。
Result:
- Falcon `.memory` 中未发现 Falcon-specific production `.py/.cu/.h/.rs` source；发现的是共享旧实验 harness、报告和 raw outputs。
- Falcon 现有 `control/G001-falcon-h1-phase1`、`G002-phase2a-mamba-lazy`、`G003-phase2b-hicache`、`G004-falcon-h1-decode-saturation` 已覆盖 Falcon 的阶段结论和脚本。
- Falcon worktree 的控制目录仍含大量 raw run artifacts；这些需按 Falcon 自有清理规则后续清理，不能迁入 3090 branch。
Remaining: Falcon branch dirty capture/清理仍是 source consolidation 后续任务。
