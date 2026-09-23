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
- E001 C6.4R deterministic L3 fixture and restart restore — BLOCKED
  - frontier: runs 005–012观察到extent写入但无指定target的live-key证据；source-native第二backend recovery被exclusive namespace flock拒绝，需先设计并contract-test安全的同进程只读allocator查询接口，再运行新fixture
  - task: experiments/E001-c64r-deterministic-l3-restart/experiment.md
  - unblock/reopen: 建立不会并发打开/写入root的同进程read-only runtime allocator probe，并通过canonical ExtentFileBackend正常关闭、跨进程恢复的contract test

其他已迁移 Goal：无 active/deferred frontier。
