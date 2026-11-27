# Frontier

## gemma4-humming-w4a16
- T012 Humming W4A16 GEMM — ACTIVE (weight/correctness gate PASS; C-8 A/B pending)
  - frontier: CT-loader + Humming post-load gate **PASS**. Unchanged CT loader/`Gemma4.load_weights` put byte-identical packed INT4 words and BF16 group scales on all 253 Text Core WNA16 layers in both arms (253/253 per-parameter SHA256 matches, Marlin arm as reference); checkpoint coverage reconciles exactly (235 exact layers + 18 shared-KV `qkv_proj` layers whose checkpoint carries only `q_proj`, +6,881,280 packed words = the k/v slots, scales at 1:4); no Text Core WNA16 tensor missing; Humming keeps only `weight`/`weight_scale` resident. Converted GEMM vs FP32 reference 2.4–3.7% of output mean (Marlin 1.4–3.6%). Humming arm: 8,608 Humming GEMMs, 2,024 during graph capture (253×8 buckets), 0 Marlin; separate replay check shows `void humming<...>` in a replayed graph. Greedy: 1-token and 32-token graph probes identical, 3/4 128-token decodes identical (511/512 tokens); the single divergence is a position where the model's own prefill path and decode path disagree in both backends. Next: original C-8 L1-only Marlin/Humming A/B, then conditional three-tier validation; keep only on stable net benefit.
  - task: `control/gemma4-humming-w4a16/tasks/T012-humming-w4a16-gemm.md`
  - evidence: `control/gemma4-humming-w4a16/runs/T012-CTLOADER-HUMMING-QUALIFICATION.md`

## gemma4-rtx3090-throughput-scheduling
- T007/T008/T009 Gemma4 RTX3090 Throughput and HiCache Restore Scheduling — ACTIVE
  - frontier: ≥600 TPS remains unmet at **587.94** official TPS (r6, 90.57% duty, 348.34 s bench), 12.06 (2.05%) short; history 560.58 (frozen baseline) → 570.88 (r3) → 587.94 (r6). r6 is fully valid: 800/800, 0 failed, exact 800-payload multiset, 0 sanity failures / exceptions / OOM, **no pool-invariant failure**, L1=9,533,440 and newly-prefilled=1,013,761 identical to the frozen baseline. r5 is a superseded non-result: it ended with a new leak report over-credited by 7 Full tokens; RCA = the patch's SWA-component Branch-3 Full-only release overlapping the caller's dead-prefix duplicate release (fixed by restoring `return prefix_len`). Window attribution shows the targeted mask-index class fell from 1,025 calls / 14.83 s to 832 / 1.82 s per 120 s (explains the +17 TPS); remaining non-forward time is extend-path inter-kernel bubbles (~17.8 s of a 20.34 s gap total) plus 688 FRONTIER `WAIT_CAPACITY` parkings at ~41% pool occupancy. Next target is therefore extend-path launch reduction or the FRONTIER admission decision, each needing its own measured A/B. An idle-time FRONTIER release was then implemented and **falsified**: it fired 0 times in `…-acceptance-r8` (585.82 TPS / 90.85% duty, identical tier counters, exact payloads), so it was reverted and r8 now serves as the 0.36% reproducibility datapoint. Since the frozen launch pays one scheduler iteration per decode step (`num_continuous_decode_steps=1`, no single-batch overlap, no prefill delayer), ≥600 needs ≈92.4% duty versus the achieved 90.6%; closing it requires an extend-path launch/batch-granularity change with its own A/B. Prefill CUDA graph (breakable, existing implementation) is now measured on the same C-8 workload: **594.23 TPS / 90.69% duty** (r10, 5 buckets, 0.71 GB capture, 800/800, exact payloads, counters identical), up from 587.94; short-window A/B shows extend device −7.7% / +3.7% output tok/s with identical token ids on a replayed 1024-token prefill. Gate still unmet by 0.96%: graph memory is the binding constraint (6 buckets = 0.72 GB OOMs the frozen pool), so reaching 600 needs extend-path fusion or a KV trade that this task forbids. Final convergence round (frozen `8b607f6756`): upstream mechanisms verified fully inherited (shared output buffer, global graph pool, capture/replay borrow scopes); `SGLANG_ENABLE_GRAPH_POOL_BORROW=1` = 593.52 vs 594.23 → no gain; 3584 bucket covers one batch and was not added; graph-on correctness re-validated (160 alternating bucket replays, real L3 restore 19,999 tokens, H2D guard present, not tripped). **Direction closed; best 594.23 TPS, ≥600 not reached.** Evidence: `runs/T009-PREFILL-CUDA-GRAPH-20261126.md` and `runs/T009-C8-R5-R6-20261126.md`. Focused suite on final source: 160 passed / 18 subtests; Unified action/load-back 20 passed / 17 skipped.
  - task: control/gemma4-rtx3090-throughput-scheduling/tasks/T009-eliminate-scheduler-cuda-sync.md


## gemma4-rtx3090-long-context-tiers (T010)
- T010 long-context three-tier cache — ACTIVE
  - frontier: 36.5K-context, 96-session workload (working set 3.5M vs L1+L2 2.32M): three tiers **112.51 TPS / 1310.6 s**, L1-only **78.66 TPS / 1874.5 s** → **+43% TPS / −30% wall**; L1 3.44M, L2 687,524 (valid restores), **L3 0 restores** (522 prefetches → 436 miss, 77 partial granted 5,000/15,511) with 3.26M tokens written to L3 and never read; extend 1107 s of which 510 s is eviction; duty 93.4%. L3 capacity hypothesis **falsified** (64 GiB cell A2: no self-eviction, same result). **Correction:** the `source=l3` counter is a match-time authority artifact — prefetch-restored spans are staged in host memory and counted as `l2`; cell A2 grants sum to ~830K tokens vs `l2`=714,896 with 723 `extent_read`s, so the third tier is *used*. Residual = 6.6M re-prefilled tokens + ~0.5 s/K-token eviction (working set 51% larger than L1+L2). Next: widen what one restore returns (anchor-based), justified as widening, not as repairing a dead tier. Evidence: `control/gemma4-rtx3090-throughput-scheduling/runs/T010-LONG-CONTEXT-TIERS-20261126.md`.
  - task: control/gemma4-rtx3090-throughput-scheduling/tasks/T010-long-context-three-tier.md


## gemma4-g1-e5m2-postbos-numerical-closure
- T004-bos-e5m2-and-numerical-closure Gemma4 E5M2数值专项 — DONE
  - frontier: 用户确认接受约0.91pp GSM8K损失并关闭数值专项；既有E5M2/eager/Decode Graph证据保留，不再扩充数值对照。
  - task: control/gemma4-w4a16-3090-performance-capacity/tasks/T004-bos-e5m2-and-numerical-closure.md


## Deferred Gemma4 qualifications
- T001-deterministic-tier-lifecycle — DEFERRED
  - frontier: 保留既有压力/生命周期结果；不再要求 139264-token 压力认证、独立逐层级/Frontier 认证或作为 T006 前置条件。仅当真实服务负载暴露与其直接相关的具体错误时恢复。
  - task: control/gemma4-g1-hicache-tier-lifecycle-20261119/tasks/T001-deterministic-tier-lifecycle.md
- T005-e5m2-production-readiness — DEFERRED
  - frontier: 保留既有 E5M2 图形/并发/HiCache 历史证据；不再执行独立认证矩阵或将旧资格门作为 T006 前置条件。当前必要的真实负载 cache correctness 归入 T006。
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

**FROZEN 2026-11-25**: T007 performance acceptance passed (median ~550 TPS, 77-78% duty, 800/800, zero sanity failures, real L3 restore re-validated). Configuration and code frozen at `c24c421daf`; no further optimisation, no new experiments, no repeated correctness certification. Complete phase diff for architecture review in `runs/G5-L3-PERFORMANCE-CODE-REVIEW.md` §6.

## T010-GPU-HARDWARE-PROFILING — 2026-11-27 (source freeze `a76206a5fb`)

Hardware-resource profiling of Gemma4 E4B on the RTX 3090 at production config, delivered as
`control/gemma4-rtx3090-throughput-scheduling/runs/T010-GPU-HARDWARE-PROFILING-20261127.md`.
T010's tier result is preserved; anchor restore, eviction work and L3 sizing are frozen.

Measured: 7 forward shapes (extend 1024/1280/4096, 32K chunked prefill, decode b8/b16/b32) in one
Nsight Systems capture with GPU sampling metrics, plus the existing C-8 120 s window and the A/B/C
load records. Class results: short extend 86.4% SMs Active / 46.1% Tensor / 58.0% DRAM read,
90.5% duty; 32K extend 96.6% / 42.4% / 41.5%, 99.8% duty; decode 61.9% / 11.4% / 46.7% read with
only 1.3% DRAM write. Operator budget (C-8): attention 47.0%, Marlin GEMM 42.2%, norms 2.7%,
activation 1.2%, RoPE 0.4%.

**Tooling limitation, recorded not worked around:** Nsight Compute cannot serialise kernels inside
this scheduler process (every filter on `Marlin`/`_fwd_kernel` fails with
`Failed to profile … in process <scheduler>`; NVTX include matches nothing even in a minimal repro),
so per-kernel pipeline mix, achieved occupancy, stall reasons, hardware L1/L2 hit rates and
per-kernel DRAM bytes are explicitly NOT COLLECTED in the report.
