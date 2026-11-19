# Frontier

## gemma4-g1-e5m2-postbos-numerical-closure
- T004-bos-e5m2-and-numerical-closure Gemma4 E5M2数值专项 — DONE
  - frontier: 用户确认接受约0.91pp GSM8K损失并关闭数值专项；既有E5M2/eager/Decode Graph证据保留，不再扩充数值对照。
  - task: control/gemma4-w4a16-3090-performance-capacity/tasks/T004-bos-e5m2-and-numerical-closure.md

## gemma4-g1-hicache-tier-lifecycle-20261119
- T001-deterministic-tier-lifecycle Gemma4 deterministic HiCache L1/L2/L3 lifecycle and Frontier recovery — ACTIVE
  - frontier: Authorized pressure is max-total 139264 / HiCache 8 decimal GB / fresh Extent 32 GiB (startup-only Host Full/SWA 186012/148810 > GPU 139264/111411). Offline runner/wrapper edits now preserve one service, gate per-RID source/Extent/ready/Decode, require a real Radix trace, and order Frontier records; 7 CPU evidence tests, syntax, fixture and diff checks pass. No generation workload has run. Next finish offline phase/cleanup validation, then resource checks and bounded pressure qualification; keep production C32 separate.
  - task: control/gemma4-g1-hicache-tier-lifecycle-20261119/tasks/T001-deterministic-tier-lifecycle.md

## gemma4-g1-prod-e5m2
- T005-e5m2-production-readiness Gemma4 W4A16 + E5M2 KV修正生产就绪验收 — ACTIVE
  - frontier: 2026-11-17 核验成功C32逐请求source：shared prefix 63,488 tokens均L1 device（host=0/storage=0）；789-event Trace见67 backup commits/131 TreeCore splits，但无host eviction，L3 `restore_backup`仅durability write，非GPU restore。idle sanity PASS并不满足分层恢复门。原失败source HEAD d7e092a，当前checkout db185be；成功runtime来自editable `/home/ubuntu/workspaces/3rdparty/sglang`，SOURCE_HEAD 4f41f5b且137 dirty paths、缓存核心有550行净改动；失败worktree已丢失，成功run source digest与当前文件不匹配。成功runtime包含后续生产变更7d4186945d/22eddb20f0，不能称差异只有diagnostics。P0-A仍历史NO-GO，P0-B未证实恢复。下一步若继续必须冻结runtime身份，真实触发Host压力/eviction、L2与L3 request-source restore→GPU→decode、Frontier waiter恢复，并保留C32 idle sanity；GO/NO-GO报告`runs/G1-P0-REAL-LIFECYCLE-20261117.md`。
  - task: control/gemma4-w4a16-3090-performance-capacity/tasks/T005-e5m2-production-readiness.md

## gemma4-w4a16-g1-baseline-restoration
- T003-g1-gsm8k-baseline-restoration Gemma4 W4A16 BF16-KV GSM8K正确率基线恢复 — ACTIVE
  - frontier: Gemma BOS(2)漏加修复后，全量同checkpoint/backend/scorer BF16-KV GSM8K为1,079/1,319 (81.804%)，较原始高183题；逐题审计通过。全量vLLM对照为1,068/1,319，SGLang/vLLM token IDs一致950/1,319 (72.0%)；低分根因恢复PASS，跨引擎数值/逐token一致性NOT ACCEPTED，369题生成有差异且未取完整对齐logits。E5M2及N512/513/514独立守卫不变。
  - task: control/gemma4-w4a16-3090-performance-capacity/tasks/T003-g1-gsm8k-baseline-restoration.md

## queued-prefetch-host-ready
- T002-falcon-rhba1-acceptance Falcon T004 pipeline time, high-pressure efficiency and correctness — ACTIVE
  - frontier: Commit `3d90660dc28bc538e42b038654e8dc14bf43c96b` freezes one valid high-pressure L0 ON/OFF pair, complete A/B/C/D ledger and control status; pushed to origin at the same SHA. Four measured RIDs per arm hit 2,048 FULL KV + MAMBA pages; A decodes 1,024 outputs. B/C/D produce one token each; Prefill batching differs (ON shared batch-3; OFF batch-1 plus batch-2), so no net performance claim. Busy Union is not GPU-exclusive time; timestamped Host-ready and H2D→dependent-kernel edge remain NOT_CAPTURED/NOT_VERIFIED. Next: obtain/freeze authorized same-revision Falcon no-cache oracle/tolerance, run long multi-round FULL+MAMBA correctness, and additional sufficiently matched long-output performance repetitions if still authorized. **T005 carry-over requiring T004 integration:** worker can crash on optional `prefetch_issue_mono_ns=None`; None-preserving guard and regression handoff in `runs/T004-FALCON-20261016/T004-WORKER-OPTIONAL-TIMESTAMP-HANDOFF-20261020.md`. Integrate guard with existing dirty telemetry consumer and regression before production use; it is not committed/pushed or production PASS. Preserve 52 tracked dirty paths and 5,241 untracked entries; GPU lock required. Physical-media attribution, correctness acceptance and performance benefit remain open.
  - task: queued-prefetch-host-ready/tasks/T002-falcon-rhba1-acceptance.md

## falcon-rtx3090-t005 (performance research closed: MEASURED / NO_OPTIMIZATION_ACCEPTED)
- Frozen c8/c32 RTX3090 clean and online hardware measurements completed: c8 435.65±1.97 tok/s, c32 732.93±2.72 with active batch≤16, Mamba 83 slots, KV 45,736 tokens. Ratio7 REJECT; Lazy not adopted; 985.1 tok/s unmet. Online Scheduler NVTX step/kernel union differs from T002 complete-forward CUDA Event and is not full Decode Graph duration or an absolute performance ceiling. No further T005 profiling/tuning. Evidence/control commits pushed: `9da9238a3111aec525e4341acc19081cb24a85d1`, `49f8fa9c4d0d3c6735746ca3931d4973945c9678`, `86cd57fa20c9e626b6de2e8fc1e76786c70580ec`; origin verified. Worker correction is handed to T004 at `queued-prefetch-host-ready/runs/T004-FALCON-20261016/T004-WORKER-OPTIONAL-TIMESTAMP-HANDOFF-20261020.md`, remains dirty/uncommitted and is not production PASS. T004 owns integration with its existing telemetry consumer and regression.

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
