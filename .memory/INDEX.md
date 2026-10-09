# SGLang 工作线主题索引

本页索引 `/home/dev-codex/workspaces/3rdparty` 下 SGLang 相关仓库的原始工作记录。文件路径均相对于仓库根；仓库分支/commit 快照见 [REPOS.md](REPOS.md)。先读 [README.md](README.md) 了解状态语义和边界。

## 快速路由

| 需要查找 | 项目 / 目的 | 入口材料 | 关联代码 / 产物 | 状态与注意事项 |
|---|---|---|---|---|
| HiCache / Radix Hybrid（RH）跨层缓存正确性和恢复 | `sglang-3090-24g-hicache`：P0/P1 生命周期、durable prefix 预恢复、admission 后避免重复 prefill | `.memory/phase2-hicache-design/context.md`、`HANDOFF-2026-09-10-48H-SUMMARY.md`、`HANDOFF-2026-09-18-FINAL.md`、`HANDOFF-2026-09-18-SESSION-2.md`、`work/INDEX-20260911.md`、`work/P1-CLOSURE-VERIFIED-20260912.md` | `python/sglang/srt/managers/scheduler.py`、`python/sglang/srt/mem_cache/hiradix_cache.py`、`python/sglang/srt/mem_cache/hybrid_cache/`、`test/registered/unit/mem_cache/`；R121/R125/R126 等冻结包在 `work/` | context 本身提醒历史 branch/HEAD 字段过时。闭环状态必须按对应 closure/review 原文与代码 commit 复核；不要把某个窄 gate PASS 扩大为 production acceptance。 |
| Host allocation / SPEC_BUDGET / Mamba 混合状态 | `sglang-3090-24g-hicache` 与历史 `sglang-3090-24g-opt` snapshots：park/wake/release、capacity epoch、Mamba restore | `phase2-hicache-design/context.md`、`plan-rh-durability.md`、`work/PLAN-20260908-RH-DURABILITY.md`、`work/P0-A-FAILURE-TRIAGE-20260911.md`、`work/P0-A-RH-REGRESSION-FIXED-20260911.md`、`work/DEBUG-20260909-HOST-ALLOC-WAKE.md`、`work/DEBUG-20260909-MAMBA-FILE-MISMATCH.md` | `python/sglang/srt/managers/scheduler.py`、`schedule_batch.py`、`mem_cache/mamba_radix_cache.py`、相关 `test/registered/unit/managers/` 和 `test/registered/unit/mem_cache/` | 记录跨环境执行及旧 runtime provenance；以每个 report 内的 target SHA、run ID、frozen artifact 为准。 |
| HiCache L3 文件后端 / Extent backend / IO 证据 | 主要在 `sglang-3090-24g-hicache`，另有 `sglang-3090-24g-opt` 同名但时间点不同的子集 | `phase2-hicache-design/plan-p2io.md`、`plan-rh-durability.md`、`work/E0-BACKEND-IDENTITY-AUDIT-20260912.md`、`work/E1-EXTENT-L3-ARCHITECTURE-FREEZE-20260912.md`、`work/E2-EXTENT-DEPLOYMENT-20260912.md`、`work/E4-EXTENT-PERFORMANCE-20260912.md`、`work/E-PHASE-CLOSURE-20260912.md` | `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`、`extent_allocator.py`、`test/registered/unit/mem_cache/test_extent_file_backend_unit.py` | context 记录了当时的用户 ruling 和 open gate；需检查最新 epoch。运行报告不可替代当前代码审查。 |
| HiCache 性能基线、telemetry 与 benchmark 口径 | `sglang-3090-24g-hicache`；`opt` 快照含部分相同文档/旧材料 | `phase2-hicache-design/evidence/p0-telemetry-20260914/README.md`、`authority/PERFORMANCE-BASELINE-SPEC-v2.md`、`authority/P0-TELEMETRY-DESIGN-20260914.md`、`review/REVIEW.md`、`work/TEST3060-DECODE-CONCURRENCY-SWEEP-20260910.md`、`work/OPS3060-DECODE-CONCURRENCY-SWEEP-R2-20260910.md` | `python/sglang/srt/observability/`、scheduler telemetry、`3090-dev/tools/perf/`、相关测试 | 先确认测试对象、served tree、commit pin 和测量定义一致；旧数据可作为历史证据，不自动视为当前基线。 |
| Gate-A / F1、冻结树与生产服务脚手架 | `sglang-3090-24g-hicache`（生产工具记录较集中） | `work/OPS-CLOSURE-AND-GATEA-BASELINE-20260917.md`、`work/F1-ROOT-CAUSE-REPORT-20260916.md`、`work/GATE-HARNESS-AUDIT-VERDICT-20260917.md`、`work/VERIFY-GATEA-AND-TREE-20260917.md`、`work/PRODUCTION-COMMIT-RECONCILIATION-20260917.md` | `3090-dev/tools/freeze/`、`3090-dev/gates/production/`、`3090-dev/tools/prod-service/` | 这是部署/生产敏感主题；本索引不复制 host/env/token/私有绝对路径或 production 状态细节。报告的审批和执行结论须按原始授权/证据核验。 |
| M1/M2 冻结发布、Qwen3-Coder、GGUF/模型身份与 reasoning control | `sglang-3090-24g-hicache` 中 2026-09-17/18 `agents/` 与 M2 campaign | `agents/M2-FROZEN-LAUNCHER-ARCH-DESIGN-20260918.md`、`agents/M2-FROZEN-LAUNCHER-IMPLEMENT-R3-20260918.md`、`agents/M2-RELEASE-STAGE2-20260918.md`、`agents/MLINE-IDENTITY-RECON-20260918.md`、`agents/GGUF-GATE-M4M3-20260918.md`、`agents/REASONING-EFFORT-POLICY-IMPL-20260918.md` | `3090-dev/tools/freeze/`、`python/sglang/srt/configs/qwen3_5.py`、`serving_chat.py`、`parser/`、`function_call/qwen3_coder_detector.py` | 多个阶段报告中间结论可能已被 R2/R3/终审覆盖；查看同主题最新 adjudication 和 commit roster。 |
| 2026-09-17/18 生产恢复/启动和服务状态记录 | `sglang-3090-24g-hicache` | `agents/P0-PROD-LIVENESS-CHECK-20260918.md`、`agents/PROD-RESTORE-20260918-R3.md`、`agents/P7-PROD-START-FINAL-20260918.md`、`agents/P9-KILL-OWN-SWEEP-AND-START-PROD-20260918.md`、`agents/HOST-GPU-SERVICE-STATE-20260918.md` | 部署脚本在 `3090-dev/deploy/` 与 `3090-dev/tools/prod-service/` | 这些是带时间戳的操作报告，不是当前服务在线状态；不据此执行启停或推断现状。 |
| v0.5.19 semantic integration / U3 | `sglang-3090-24g-hicache` 的 2026-09-13 handoff；`sglang-v0519-integration-20260913` 是独立且当前有大量暂存改动的 worktree | `.memory/phase2-hicache-design/HANDOFF-20260913.md`、`work/WORK-INVENTORY-20260914.md`、`work/RECONCILIATION-STEP1-RECON-20260917.md`、`work/PRODUCTION-COMMIT-RECONCILIATION-20260917.md`、`work/SOURCE-AUTHORITY-CORRECTION-20260917.md` | 集成 worktree 的 source tree、语义 merge / regression corpus | 集成仓当前工作区有 1154 个 staged entries + 8 个 unstaged changes；只读，不清理、不 checkout、不覆盖。 |
| Qwen3.8-27B GSQ-RCO IQ3_S：G3/MMQ 基线、tokenizer/runner OOM 修复、profile 对照 | `sglang-qwen3-27b-iq3s`：先保存未优化基线，再隔离 MMQ 实现并同命令复测 | `.memory/g3-baseline-20260907/context.md`、`plan.md`、`ledger.md`、`HANDOFF-CONTINUE.md`、仓库根 `AGENTS.md`、`HANDOFF-G3-2026-09-07.md`、`CODEX_HANDOFF.md` | 六文件功能提交 `4d3068316e`：`python/sglang/benchmark/serving.py`、`python/sglang/srt/entrypoints/openai/{protocol,serving_chat,serving_completions}.py`、`python/sglang/srt/sampling/custom_logit_processor.py`、对应 sampling 测试 | 当前新分支 `qwen3-27b-iq3s` 已推送；提交 SHA `4d3068316e21d4c5a2b86ad0e0efdff7f05850c2`。pytest 当时不可用；py_compile 和 diff check 通过。源 `.memory` 多数是本地 untracked raw evidence，不代表远程可获取。 |
| Qwen G3 原始运行/遥测/依赖/产物 | `sglang-qwen3-27b-iq3s/.memory/g3-baseline-20260907/work/raw/` | 由 handoff/ledger 中的 RUN_ID、Profile A/B、C1/C4/C8/C16 记录定位 | Qwen runner、benchmark、服务快照和指标文件 | 本地-only 大量文件；索引只导航，不复制原始 telemetry/环境快照或暗示它们已提交。引用具体 run 前在源工作树验证文件实际存在并检查 `.gitignore`/tracked 状态。 |
| 2060/5090 专项 HiCache 与 release checkpoint | `sglang-2060-6g-hicache`、`sglang-5090-32-hicache`、`sglang-v0519-integration-20260913` | 各仓库 commit/log/branch；README/提交说明 | 需按具体任务从代码与提交历史继续补充 | 当前未发现 `.memory`。此处仅保留仓库入口；后续若发现重要历史任务，再依具体 commit 建档，不虚构缺失的工作目的。 |
| Worktree 迁移与本地状态治理 | `sglang-qwen3-27b-iq3s` | `.memory/worktree-migration-20260907/work/{audit,retire,verify}.md` | linked worktree / branch 操作 | 记录是本地归档，结合当前 refs/status 验证，不照搬历史操作指示。 |

## 逐文件目录

需要按路径查某份报告、raw bundle 或来源文件状态时，使用 [catalog/README.md](catalog/README.md)：`catalog/{hicache,opt,qwen}-files.md` 是逐路径 Git/file catalogue，`catalog/{hicache,opt,qwen}-docs.md` 是非 raw Markdown/text 标题提示目录，`catalog/hicache-work-groups.md` 按 R 编号 bundle/工作子目录归组。清单区分 source HEAD 中 tracked 与仅本地存在的 local-only 项，并尽可能记录 blob OID；其生成时快照不自动更新。

## 按 repo 的原始目录导航

### `sglang-3090-24g-hicache`

- 主入口：`.memory/phase2-hicache-design/context.md`、`plan.md`、`ledger.md`、`authority.yaml`、`HANDOFF-*`、`WORK-INVENTORY-*`。
- RH/P0/P1/P2/P3 工作项：`.memory/phase2-hicache-design/work/`；该目录有大量日期化 `ARCH/COD/DEBUG/OPS/REV/TEST/REVIEW/P0/P1/P2/Rxxx` 报告。
- 专项输出：`evidence/p0-telemetry-20260914/`、`agents/`、`escalations/`、`archive/phase2-pc1/`。
- Agent/harness smoke：`.memory/protocol-subagent-smoke-20260917/ledger.md` 和 `agents/`。
- 外部参考缓存：`.memory/cache/external/sglang/`（仅作引用，不视为项目本地实测）。

### `sglang-3090-24g-opt`

- 主入口：`.memory/phase2-hicache-design/context.md`、`plan.md`、`ledger.md`、`authority.yaml`、`HANDOFF-*`、`WORK-INVENTORY-*`。
- 重要工作项：`.memory/phase2-hicache-design/work/INDEX-20260911.md`、P0/P1/RH/E-phase 闭环文件及 `Rxxx-bundle/`。
- 与 `hicache` 共享/相似的路径要比较 blob/hash；此仓快照 HEAD `ad749d6f…` 与 hicache `b864ffe3…` 不等价，不能用一个仓的路径推断另一个版本内容。

### `sglang-qwen3-27b-iq3s`

- 项目治理：仓库根 `AGENTS.md`；用户接手入口 `HANDOFF-G3-2026-09-07.md`、`CODEX_HANDOFF.md`。
- 实验任务总线：`.memory/g3-baseline-20260907/{context.md,plan.md,ledger.md,HANDOFF-CONTINUE.md}`。
- 文档报告：`.memory/g3-baseline-20260907/work/G3-*.md`。
- raw 运行证据：`.memory/g3-baseline-20260907/work/raw/`，逐 run 目录名含日期/任务类型；查找时按 ledger/handoff 的 `RUN_ID` 定位。
- worktree 迁移：`.memory/worktree-migration-20260907/work/{audit,retire,verify}.md`。
