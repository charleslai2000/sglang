# Current frontier

phase2-hicache-design
- T003 性能评估 — BLOCKED
  - frontier: 使用修正后的同一 harness 补齐 M4 全部档位，才能形成权威对照表
  - task: phase2-hicache-design/tasks/T003-performance-evaluation.md
  - unblock/reopen: 新授权并完成完整 M4 sweep
- T004 正确性与生产就绪 — BLOCKED
  - frontier: M3/M4 correctness gate 仍未通过，不能宣称生产就绪
  - task: phase2-hicache-design/tasks/T004-correctness-and-production-readiness.md
  - unblock/reopen: 修复并重跑 correctness gate

c64r-deterministic-l3-restart
- E001 C6.4R deterministic L3 fixture and restart restore — READY
  - frontier: capacity已解除；用新root按frozen production contract生成并验证exact live key后执行graceful restart/replay
  - task: experiments/E001-c64r-deterministic-l3-restart/experiment.md
  - unblock/reopen: —

其他已迁移 Goal：无 active/deferred frontier。
