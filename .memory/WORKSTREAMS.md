# SGLang 工作综合（跨仓工作项）

本文件是**工作综合**，不是文件目录：从多个仓库的 handoff、closure、ledger 和 review 中提炼目标、已证结论、当前边界、代码关联及接续点。原始记录与大型附件分别按其工作项留存；逐文件来源分支、commit、SHA 和存储位置以 `archive/MANIFEST.tsv` 为准。

## 来源快照与解释边界

下列分支/commit 是本次归集记录对应的本地来源快照（当前查询值），不是执行实验时的 target commit，也不证明历史报告结论对应当前代码：

| 来源 | branch @ collection | HEAD @ collection | 材料性质 |
|---|---|---|---|
| `sglang-3090-24g-hicache` | `3090-24g-hicache` | `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d` | HiCache 主线、生产/发布工具、subagent 协议 smoke；含大量本机 `.memory` |
| `sglang-3090-24g-opt` | `3090-24g-opt` | `ad749d6f283b7d6c59a8df928304325eda90e98b` | RH / HOST_ALLOC、P0/P1/P2、Extent L3、3090 profile 与本地生产交接；与 hicache 同名材料是不同 snapshot |
| `sglang-qwen3-27b-iq3s` | `qwen3-27b-iq3s` | `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2` | G3/MMQ、Qwen IQ3/SM86、性能/环境/依赖、worktree migration；许多材料源 HEAD 未跟踪且仅本地存在 |

**时间差提醒**：同一仓材料内部存在 2026-09-07 至 2026-09-18 的多个 epoch；其 branch/HEAD/runtime 指纹各自适用。下面凡写“完成/blocked”均是对应历史报告裁决，不是当前服务状态。不得据历史 handoff 启停服务、占 GPU、推送/部署或判断当前代码状态。

---

## 工作项 1：RH durable-prefix 生命周期与 HOST_ALLOC wake liveness

**目的**：证明 durable prefix 经 nonresident/park/release/wake 后，在 admission 前完整恢复 KV+Mamba，避免重复 prefill；并修复 HOST_ALLOC 在 capacity 已满足但某 generation 未变化时可能错误持续等待的 liveness 条件。

**综合结论（各自 epoch 的裁决）**：
- `sglang-3090-24g-opt` 的 `P1-CLOSURE-VERIFIED-20260912.md` 将 P1 判为 **VERIFIED/CLOSED**：R125 + R126 共 4 次固定 build 的 live causal chain；durable-boundary restore 为 KV `27328/27328`、Mamba `1/1`、all-or-nothing，durable-prefix recompute=0、hybrid_discard=0。
- 新 capacity-satisfied / generation-unchanged clause 被 18 个 unit tests 与冻结的真实 R121 event replay 覆盖；**该新 clause 本身没有在 live workload 中成为决定 grant 的分支**，closure 明确列为 non-blocking residual，不得夸大。
- 较早的 2026-09-11 index（同一仓旧 epoch）曾记 P0-B overall NOT_VERIFIED、P1 prepared only；该结论被后续 2026-09-12 closure 更新。应按具体 artifact epoch 引用，而不能把不同阶段状态混写。
- `sglang-3090-24g-hicache` 2026-09-18 最终 handoff 转为 **EVIDENCED BLOCKED / owner 终止**：工作线出现 sweep 自动化抢占共享生产 GPU 的严重操作错误；该线自己的自动杀逻辑造成生产服务被反复杀掉。它要求生产优先、单一 GPU 窗口所有者、测试窗口经该次 owner 批准、禁止自动杀占卡者。该 handoff 记录当时生产 DOWN/未达 VERIFIED DONE；不是当前状态。

**代码关联**：`python/sglang/srt/managers/scheduler.py`（P1 closure 记录 fix SHA256 `892efc25e2a9ef7c5ebb4afa09cf6914182b1467981d14cd76c53eea5d8de9d7`，其历史 target repo/commit见该 artifact）；`python/sglang/srt/mem_cache/hiradix_cache.py`、`hybrid_cache/`、`schedule_batch.py`、`mamba_radix_cache.py`；测试 `test_hicache_host_allocability.py`、ready-horizon、scheduler-feed、drain-reentry、storage-regression。

**依赖/来源**：P1 closure 来源 `sglang-3090-24g-opt`，报告当时写 branch `3060-12g-qwen35-4b` / HEAD `4f41f5...`（已并入 opt 历史，非当下 branch）；后续 HiCache handoff 来源另一仓/epoch。详情见该 closure 中 R125/R126/R121 及完整 SHA 表。

**接续边界**：若恢复这条工作，先核实当前 scheduler/test tree、历史 closure 对应 commit、最新 owner 授权与真实环境身份；P1 CLOSED 不等于 production acceptance，也不授权产品改动或 GPU 实验。

证据：`phase2-hicache-design/work/P1-CLOSURE-VERIFIED-20260912.md`（原仓 opt）；HiCache 源交接 `phase2-hicache-design/HANDOFF-20260918-FINAL.md`。

---

## 工作项 2：L3 Extent backend 与 HiCache 性能路径

**目的**：把 legacy one-file-per-token-page、查询时扫描百万级文件的 FileBackend 路径，替换/验证为 extent block IO + RAM authoritative index，并量化 cache 查询、L3→L2 staging 与端到端负载。

**综合结论（E0–E4 epoch）**：
- R129 使用 `--hicache-storage-backend file`，metadata cache 默认关闭，因 `page_size=1` 每页一文件，查询走 `os.scandir`；closure 把 17.777 s/query 定性为 legacy FileBackend scalability failure，而非 RH 缺陷或有效生产 baseline。
- E0–E4 将已有 `ExtentFileBackend` 作为部署选择验证；报告记录 77/77 unit、真实 v1-write→v2-query hit；E4 的 Q3 p50 17.777 s→2.616 ms（miss path 2.392 ms），Q2 16.567 s→304 ms（E4b warm n=32 为 445 ms），59-request wall 514 s→47.3 s cold-ish / 19.1 s warm，0 bad requests。此为各自冻结 profile/workload 下的历史数据，不是当前生产对比。
- E-phase closure 的正式裁决 VERIFIED；当时唯一生产硬门为 G1：Extent index restart rebuild/persistent compact metadata manifest/checkpoint + append-only delta/WAL。它是非豁免产品更改，必须先有授权和完整机制审查；没有 restart-live PASS。G2 deployment sizing 当时已解决；G3 `get_stats()` 限制、G4 per-rank file、G5 on-disk integrity 均按报告分级，不能重新包装成已实现。
- 2026-09-17 生产交接另记新候选树已含 native/GIL-free L3 writer并以显式 commit 冻结，但 Gate A/F1 harness 当时存在误判问题，`PRODUCTION BLOCKED` 与 2026-09-17 Session Close 的 GREEN 又处在不同运行 epoch/树。**这两份报告不能合并成一个持续有效的生产状态**；要判断任一 epoch，必须按各自 manifest、serving tree、run namespace 和 artifact identity 对齐。

**代码关联**：`python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`、`extent_allocator.py`、`backend_factory.py`、`hicache_storage.py`、`environ.py`；native writer 相关 `rust/l3wal`；测试 `test_extent_file_backend_unit.py`、SIGKILL/reopen 和 grouped KV+Mamba corpus。

**依赖/来源**：E0–E4 closure 来自 opt snapshot；E0/E1/E2/E4 artifacts 和测试日志 hash 列在 closure。HiCache 生产交接另在 hicache source。历史 opt context 明确其 baseline branch/HEAD 已过时；不得用早期 context 的 SHA 当目前代码身份。

**接续边界**：任何 G1 metadata persistence/rebuild、checksum 或 live production campaign 都需核查当前代码和独立授权；不能拿旧 E4 性能数字代替当前实现验证。

证据：`hicache-l3-extent-storage/RH-PRESSURE-SUMMARY-20260912.md`（当前整理目录中另有 E-phase closure；原始权威路径见 Manifest）；源 closure `phase2-hicache-design/work/E-PHASE-CLOSURE-20260912.md`（opt）。

---

## 工作项 3：3090 本地生产候选、launcher freeze 与运行安全

**目的**：让被冻结的 serving tree 与明确 source commit 一致，修复 freeze/launcher/lifecycle 工具链，建立可审计的生产模型/端口/GPU 服务边界。

**综合结论（按交接 epoch 分开）**：
- 2026-09-17 Session Close 报告记录：从显式 commit 冻结 `local-prod-v1.2.1-candidate`，served Python commit `b2bbd6ea28`，lifecycle commit `8c8cdcea03`；128K/C8 profile，Narrow smoke 10/10，包含真实运算、chat/tool-call、超长 prompt 拒绝与存活检查；当时 verdict GREEN、DEV down。此为有时间戳的历史状态，不是当前服务检查。
- 紧邻的 2026-09-17 Production Priority handoff 记录另一个更早时点：旧 scratch candidate 缺 native writer、Gate A harness invalid、生产 blocked；并记录后续修复项。它解释了候选身份/Harness 的问题来源，但其旧服务状态被后一份 session-close 在较晚 epoch 更新。
- 2026-09-18 SESSION 2/FNAL 又记录了不同的 owner 裁决、M2 发布、Qwen detector、M3/M4，以及测试 sweep 与生产互杀事故；9/18 FINAL 终止时状态是 EVIDENCED BLOCKED，且要求先解决生产/GPU ownership 再继续。不能把 9/17 GREEN 沿用到 9/18。
- `switch-codex` 已确认不在当时主机；`qquestion` 确实由 `qwen3_coder_detector.py` 路径 surface 未声明工具；工具调用孤儿片段可产生 `tool_index=-1` 的历史问题，detector hardening 被指定合并到 M2 发布，但 9/18 最终 handoff 明确代码尚未落地/发布未完成。不能宣称该修复已上线。

**代码关联**：`3090-dev/tools/freeze/{bin,pysrc,templates,pins}`、`3090-dev/tools/prod-service/`、`3090-dev/gates/production/`；SGLang `python/sglang/srt/function_call/qwen3_coder_detector.py`、对应 `test_function_call_parser.py`；运行树的行为必须按 freeze manifest/PYTHONPATH 身份判断，不能只看 workspace 源码。

**依赖/来源**：hicache 分支与 opt 工作仓在 2026-09-17/18 的工作树/冻结树处于多 epoch。具体 commit、tree hash、launcher hash 和 loaded binary hash只引用相应 handoff 的 manifest；这里列的短 commit 仅便于定位，不代替完整 SHA。

**接续边界**：当前生产健康/端口/GPU owner 未由本归集任务探测；禁止根据历史 report 执行 start/stop/kill、部署或冻结操作。任何窗口需新鲜授权、身份检查与单一 GPU owner。

证据：`phase2-hicache-design/HANDOFF-20260917-SESSION-CLOSE.md`、`HANDOFF-20260917-PRODUCTION-PRIORITY.md`、`HANDOFF-20260918-SESSION-2.md`、`HANDOFF-20260918-FINAL.md`。

---

## 工作项 4：G3/MMQ — Qwen IQ3_S 基线、runner OOM 与隔离性能对照

**目的**：在未优化的 IQ3_S v1 上冻结 Profile A（生产 C1/C4/C5）和临时性能 Profile B（真 C16 + prefill），修复 benchmark runner 对 GGUF 的 OOM，取得可重复 baseline 后才实现 MMQ，并以逐字节相同命令/profile 复测。

**综合结论**：
- 协议层已冻结：合成固定长度采用 `random-ids --tokenize-prompt`、seed 42、ratio 1.0 并在 manifest 注明兼容语义；ShareGPT 只作为独立 pinned realistic 层，不纳入核心 MMQ gate；Profile B prefill 为 C1/20 prompts、2K/8K/32K ×32 output ×3；B admission 看服务器 `max_running_requests >=16`，不能拿客户端 concurrency 替代。
- Production-A 最初被 GGUF 读取 OOM 阻断：`check_chat_template` 让普通 AutoTokenizer 把约 11.77 GB GGUF 当 JSON 整读，导致约 42.6 GB RSS、rc=137。修复约束为仅处理 GGUF 分支、快速跳过或 sidecar tokenizer，并要求双端源码一致、低内存验证。
- G3 handoff 中修复任务当时需核实报告/双端实际差异，Production-A 正式矩阵需在 runner settle 与 smoke review 后重跑；B 必须串行于 A 并独占 GPU；MMQ implementation 只能在 baseline review 后派发。
- Qwen 资料的来源 HEAD 没有跟踪 `.memory` 文件；这批很多是 local-only 证据/运行记录。不能推断其远程已保存，也不能拿运行报告的 PASS 推断当前模型/server 仍可用。

**代码关联**：`python/sglang/benchmark/serving.py`（`check_chat_template`）；MMQ 目标/SM86 kernel/build 记录；Qwen 27B IQ3 的 model/runtime/cache profile 及 kernel identity reports。具体文件及 target commit 以每份报告及 `archive/MANIFEST.tsv` 为准。

**依赖/来源**：`sglang-qwen3-27b-iq3s` 分支 `qwen3-27b-iq3s`，收集 HEAD `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`；G3 handoff 内实验仓曾报告不同 branch/HEAD（如本地 `dac6db1...`、远端无 Git archive），故应按 artifact 报告中的实际 target 复验。

**接续边界**：先核对来源仓当前状态、runner patch、Profile A/B 的真实 raw artifacts 和服务指纹；没有独立终审的完整 baseline，不要开始/宣称 MMQ 对比已完成。GPU/远端实验要沿用原仓 AGENTS 授权边界，现归集不产生新授权。

证据：`g3-baseline-20260907/HANDOFF-CONTINUE.md`、`plan.md`、`context.md`、`work/G3-RUNNER-OOM-DIAG-20260907.md`、`G3-RUNNER-OOM-FIX-SETTLE-20260907.md`。

---

## 工作项 5：G3 IQ3/SM86 kernel build 与本地环境恢复

**目的**：在目标 SM86 环境准备隔离 kernel/toolchain，确定 SGL-kernel build 对 IQ3_S 的加速/兼容性，保持 artifacts 与生产 serving profile 隔离。

**综合结论**：报告族覆盖 no-copy layout、依赖补齐、PEP668 恢复、SM86 isolated build/identity、local smoke 及恢复状态；材料之间多为逐次尝试和纠偏，不应把任一 `BUILD`/`SMOKE` 记录当成整条工作完成。可确定的是：每条尝试都有独立报告，必须以最新 `G3-IQ3-RESUME-STATE`/SM86 identity 与 pause summary 综合；原始 handoff 仍要求先 settle runner OOM 与 Profile A，再进入 B/MMQ，且不允许未授权下载/模型重量改动。

**代码/工件关联**：Qwen IQ3 project 的 build scripts, `sgl-kernel` packaging and identity records, `python/sglang/benchmark/serving.py` runner; 证据为 `work/G3-IQ3-*`、`G3-SM86-*`、`G3-SGL-KERNEL-*` 报告。源仓报告不自动等于可复现 build；按记录的 compiler/toolkit/target arch/artifact hashes 重验。

**接续边界**：检查依赖和构建环境之前先读该仓 `AGENTS.md`；避免重用其它 session 的 GPU、共享 venv 或下载路径。此摘要不裁定 build 当前有效性。

证据：`g3-iq3-kernel-build/` 与 `g3-baseline-20260907/work/G3-IQ3-RESUME-STATE-20260909.md`、`G3-IQ3-SM86-PAUSE-SUMMARY-20260908.md`。

---

## 工作项 6：Qwen G3 serving 性能矩阵与本地依赖/运行环境

**目的**：测量 production profile 与 performance-only profile 的 latency/throughput/prefill，按真实服务观测 concurrency，并独立收敛模型、tokenizer、python dependencies 与 toolchain prerequisites。

**综合结论**：
- Profile A/B 的目标、长度、重复数、缓存 flush、dataset binding 和 admission 规则见 G3 plan；B 不能覆盖/挤掉 A，也不能将不同服务/profile 的数据混在一起。
- 2026-09-14 opt handoff 报告了一条不同的 Qwen3.5-9B 本机候选基线：B0 GROUP_COMMIT、B1 profile/source、B1-C structural/semantic、B2 current-byte requalification 当时 PASS；B2 旧 reviewed-byte 的 per-file exact match 仍 insufficient evidence。
- B3 性能只部分完成（handoff 明示）；P0 telemetry 当时 CHANGES_REQUIRED，故 B4 freeze/canary 禁止。不能把 Qwen 27B G3 profile 和 Qwen3.5-9B local-prod baseline 当成同一模型/任务。
- 依赖/环境报告族由 local-only retry 组成；报告存在不代表共享运行环境现在可用。优先读对应 final reconcile/rebuild report，按环境身份逐项核验，不逐份重跑旧安装尝试。

**代码关联**：Qwen3.5 model loader `python/sglang/srt/models/qwen3_5_text.py`；benchmark serving runner；storage GROUP_COMMIT / Extent backend tests；模型路径、venv、CUDA profile 见 opt 的 9B handoff（敏感运行主机细节不在本综合中重复）。

**依赖/来源**：`sglang-3090-24g-opt` 的 `HANDOFF-20260914-LOCAL-PROD-BASELINE-v1.md` 写明当时 production-source identity commit `993ef8e5c3a6448aff2e752cf66cc45deadab59a`，opt work branch 当时 `34bd2ed49f2b2e6fef504019bfe3840eb30ac061`（后续又推进）；仅用于找历史 artifact，不是当前 source identity。

**接续边界**：先把 27B G3 与 9B B0–B4 两条 profile 线分开，再确认各自数据集 hash、tokenizer、runner bytes、模型身份和 telemetry review；历史 PASS 不代替当前 profile freeze。

证据：`sglang-3090-24g-opt/.memory/phase2-hicache-design/HANDOFF-20260914-LOCAL-PROD-BASELINE-v1.md`、Qwen G3 handoff/plan。

---

## 工作项 7：Subagent dispatch 协议与角色/模型审计

**目的**：对 19 个 specialist role 做 bounded smoke，验证每个 dispatch 的 artifact protocol，并独立审计 variant/模型选择、通信完整性和记忆文件写入规约。

**综合结论**：协议 smoke ledger 给出 **VERIFIED DONE**：19/19 role dispatch 有终端 artifact，含两份专门审计，总 21/21 reconciled；各角色配置 variant 均匹配其 agent config，未观察到 fallback/substitution。审计边界也明确：dispatch API 没有 model/variant 参数，所以 orchestrator 未显式选择它们；provider-side target identity 和 wire-level reasoning_effort 未建立，不能排除上游替换。ledger 中一条 public-tier 证据 basis 未能复现，已保留为 unresolved，而非改写成已证实。

**关联代码/系统**：本仓 `.pi`/OpenCode orchestration and role agent configuration、dispatch tool/session DB/artifacts；该 smoke project 没有 SGLang 产品代码改动（其 ledger 明确 `No project subject`）。

**来源**：hicache snapshot 的 `.memory/protocol-subagent-smoke-20260917/ledger.md` 及 `agents/` artifacts；以原 ledger 最终 audit section 和角色 artifacts 为准。

**接续边界**：这是 dispatch protocol validation，不是 SGLang 模型性能/推理质量验证。

---

## 工作项 8：Worktree migration / 本地状态治理

**目的**：审核 Qwen worktree retirement/migration，防止 branch/ref/working tree 生命周期操作丢失未提交状态。

**综合结论**：来源仅有三份 audit/retire/verify 记录，且都为 qwen memory local-only。这里未独立重放当前 worktree/ref 操作，故不声称现时仓状态与历史报告一致；任何实际 retire/recovery 必须重验当前 refs、worktree list、status 和 object availability。

**关联对象**：Git worktree metadata、branch refs、Qwen project checkout；无产品代码。

**证据**：`g3-worktree-migration/`（本目录中的综合已提炼主题）；原记录 `worktree-migration-20260907/work/{audit,retire,verify}.md`。

---

## 快速接手原则

1. 先读本文件对应工作项的权威 handoff/closure，不要把 raw artifact 当结论。
2. 从 Manifest 用 `source_repo + source_head + source_path` 找到完全对应的来源版本；源本地-only 项须接受无法从 Git checkout 自动恢复这一限制。
3. 按 epoch 把事实分层：设计/单测、frozen replay、实验 live run、生产 service 不能互相替代。
4. 任何 GPU、生产服务、远端 host、freeze/deploy 操作都需要核查**当前**授权和身份；这些历史材料只记录当时范围，不提供新的授权。
5. `.memory/data/` 是本地忽略数据区；提交不包含其 payload，迁移工作区需先确保获准备份。
