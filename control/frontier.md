# Frontier

## queued-prefetch-host-ready
- T002-falcon-rhba1-acceptance Falcon T004 pipeline time, high-pressure efficiency and correctness — ACTIVE
  - frontier: `T004-L0-ONOFF-FIXTURE-20261020.md` freezes one valid high-pressure L0 ON/OFF pair and complete A/B/C/D ledger. Each arm's four measured RIDs hit 2,048 FULL KV + MAMBA pages; A decodes 1,024 outputs. B/C/D produce one token each; Prefill batching differs (ON shared batch-3; OFF batch-1 plus batch-2), so no net performance claim. Busy Union is not GPU-exclusive time; timestamped Host-ready and H2D→dependent-kernel edge remain NOT_CAPTURED/NOT_VERIFIED. Next: obtain/freeze authorized same-revision Falcon no-cache oracle/tolerance, run long multi-round FULL+MAMBA correctness, and additional sufficiently matched long-output performance repetitions if still in authorized scope. Preserve dirty files and GPU lock. Physical-media attribution, correctness acceptance and performance benefit remain open.
  - task: queued-prefetch-host-ready/tasks/T002-falcon-rhba1-acceptance.md

## falcon-h1-3090-online-hicache
- T001-online-forward-and-hicache-loss Falcon 在线GPU损失与HiCache有效恢复 — ACTIVE
  - frontier: c8/c16 Decode Graph-to-step与窗口指标已写入A–E。R15 node 26首次barrier早于Host ACK，记录无detach、队列空；这不能证明ACK后detach路径失败。dirty MAMBA/tree-core leaf-membership patch仍是候选且定向test受sgl_kernel依赖阻塞。核查eviction/ownership后复用R7C/R11验证当前主线L2→L3；不进行GPU操作，待资源协调。
  - task: control/falcon-h1-3090-online-hicache/tasks/T001-online-forward-and-hicache-loss.md

## falcon-h1-3090-hicache
- T001-mainline-gpu-ncu-and-c16-stall 当前主线 GPU/NCU 计量与 c16 stall 收敛 — ACTIVE
  - frontier: NCU/TPS矩阵和报告已取得；报告明确Prefill Attention、精确graph node ID、当前主线逐request scheduler timeline及阶段kernel wall-time贡献仍UNKNOWN。Task记录捕获源HEAD `6f612b0…`，当前HEAD已推进至 `592a9ef…`，旧工作树/stage已不在；继续做source ownership/证据闭合和是否可接受结果的裁定，禁止从当前dirty tree重构历史commit。GPU闲置。
  - task: control/falcon-h1-3090-hicache/tasks/T001-mainline-gpu-ncu-and-c16-stall.md
- T002-mainline-hicache-restore 当前主线 HiCache 恢复与分层计量 — READY
  - frontier: 审核复用R7C identity/correctness驱动，在当前主线证明FULL+MAMBA Host-source H→D；后续独立L3 read-back，未过保持NOT_QUALIFIED。
  - task: control/falcon-h1-3090-hicache/tasks/T002-mainline-hicache-restore.md

## falcon-h1-3090-hicache-cache
- T001-l2-l3-recovery-and-accounting 分层恢复与账本 — ACTIVE
  - frontier: 冷进程 Storage→Host→GPU PASS (`T003-L3R-20261015T0900Z/RESULTS.md`)。同进程受控容量实测KV Host usable=2,417/MAMBA=14；目标node26/hash正常Device detach FULL1,791+MAMBA1，随后MAMBA Host LRU detach，释放FULL Host1,792+MAMBA1。Storage恢复RID `8abb6cc8509a468fb6ef9dabc896cc86` 输出[10553]，命中Storage1,791+Device1+Host0；H2D op4同步完成359,411,712B/34.98ms。末尾1 Device token是终端sentinel/祖先，不是合法Host-only leaf；停止追加压力，不能宣称Storage全量1792。ComponentType回归定向19 passed/2 skipped；dirty文件含无关改动，未提交。剩余：冻结长/多轮logits与MAMBA-state正确性、完整分层账本、正常容量A/B、选择性提交；无性能收益结论。
  - task: control/falcon-h1-3090-hicache-cache/tasks/T001-l2-l3-recovery-and-accounting.md
- T002-gpu-per-step-timeline GPU Per-Step Timeline 与 GA102 metrics — ACTIVE
  - frontier: FPM计数器/iteration身份修复及回归已通过18 tests；Scheduler动态NVTX step range已实现，但Nsight capture按完整message匹配，动态range前缀不触发。找出fixed outer range capture或已验证等价方法后先短验同库含NVTX+CUDA+Metrics，再连续采c8/c16；GPU已清理、两个systemd服务继续disabled，不重采NCU/TPS。
  - task: control/falcon-h1-3090-hicache-cache/T002-gpu-per-step-timeline/tasks/T001-per-step-gpu-metrics-and-join.md

## falcon-h1-3090-r17-metrics
- T001 Scheduler NCU 与 Prefill/Decode GPU 计量 — READY
  - frontier: 隔离`/tmp/sglang-r17`仅为历史来源；执行当前工作树时遵循新目标`falcon-h1-3090-hicache`的授权，不把历史NCU数据当当前主线结果。
  - task: control/falcon-h1-3090-r17-metrics/tasks/T001-scheduler-ncu-and-gpu-phase-metrics.md
- T002 HiCache L1/L2/L3 恢复时延与备份账本 — READY
  - frontier: 复用R7C/R11，仅在隔离R17目标授权内继续；当前主线cache恢复授权与证据由`falcon-h1-3090-hicache/T002`管理。
  - task: control/falcon-h1-3090-r17-metrics/tasks/T002-l2-l3-restore-and-byte-accounting.md
- T003 代表性并发与分层性能对照 — DEFERRED
  - frontier: 复用历史合格点；仅当当前目标定义的对应cache正确性门通过后开展新比较。
  - task: control/falcon-h1-3090-r17-metrics/tasks/T003-representative-cache-performance-matrix.md
  - unblock/reopen: GPU phase/counter seam与L1/L2正确性通过；Disk仅在L3读回与恢复PASS后开启。
