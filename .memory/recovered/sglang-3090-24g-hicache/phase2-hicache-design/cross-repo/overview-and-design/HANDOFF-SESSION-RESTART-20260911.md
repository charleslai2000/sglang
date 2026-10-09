# Session restart handoff — SGLang HiCache/RH

## 目标

继续 `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt` 的
`.memory/phase2-hicache-design/` 工作。主线：correctness → causal live A/B →
measurement → optimization → production gate。

## 当前基线

- Branch: `3060-12g-qwen35-4b`
- HEAD: `4f41f5bab562b99562f30c67540eb05344d13637`
- Worktree intentionally dirty；不要清理、reset 或覆盖既有修改。
- 远程 RTX 3060 12G 实验实例已获用户授权，仅限实验验证；3090 和生产环境未授权。
- 每个新执行都必须使用 fresh Task ID。

## 当前状态

- **P0-A RH regression：NOT_VERIFIED / blocked**。
- 已完成远程源码同步、备份和 SHA256 校验。
- 已执行 dependency-complete 3060 P0-A 回归，但仍有失败。
- 最新任务摘要：focused RH 5 failures；budget focused 2/9 passed；restore-feed
  43/46 passed；full RH 16/55 passed。详细报告未可靠落盘，不能把这些摘要当作完整证据。
- durable R3 报告：`work/P0-A-RH-REGRESSION-RECONCILED-20260911-R3.md`，记录
  164 passed / 17 failed。
- 已做测试 fixture 修复并经 reviewer APPROVE，但修复后重跑仍未通过。
- 失败症状包括 `host_release`、`_prefetch_kvcache`、`pop_host_alloc_failure`、
  `speculative_release_epoch` fixture/API 不一致，以及预期 `r1` 未产生。
- 本机缺 pytest/orjson；不要用本机失败替代远程依赖完整验证。

## 已完成的关键任务报告

优先阅读：

1. `context.md`
2. `plan.md`
3. `ledger.md`
4. `work/P0-A-RH-REGRESSION-RECONCILED-20260911-R3.md`
5. `work/P0-A-FIX-FIXTURES-20260911.md`
6. `work/P0-A-FIX-FIXTURES-REVIEW-20260911.md`
7. `work/P0-A-REMOTE-SOURCE-RECONCILE-20260911.md`
8. `work/P0-B-HOST-ALLOC-LIVENESS-SCOUT-20260911.md`

## 下一步（不要跳过）

1. 新建 fresh Task ID，继续 triage/fix P0-A fixtures/API contract；先审查当前
   dirty diff，不修改产品实现，除非有独立证据证明是产品回归。
2. 将测试变更同步到远程 3060 12G 实验实例，做可回滚备份和 hash 校验。
3. 重跑 P0-A focused + full RH regression，并把完整命令、stdout/stderr、退出码、
   测试计数持久化到 `.memory/.../work/`。
4. P0-A 完整通过前，不执行或宣称 P1 acceptance。
5. P0-B 是硬 liveness gate：
   `not allocable → park → real allocability change → wake → successful restore`。

## 固定验收边界

P1 必须闭合同一 identity 的因果链：

`SPEC_BUDGET park → reservation/release epoch transition → RH wake → L3→L2
stage → Host-ready → admission → L2→L1 restore → generation`

同时验证：`cached_tokens > 0`、`recompute(full-prefix)=0`、`hybrid_discard=0`，
identity 至少包含 `RID/session/node/build/generation`。

`query_storage_hit_length` 当前只量不改。FP8 KV quality 独立，但阻塞最终 quality
sign-off。TTFT <1s 当前只是 optimization target；最终生产门按 L1 hit、L2 restore、
RH 已 stage 到 Host-ready 的 L3 request 分场景要求 P95<1s，cold L3 不纳入该门。

## OpenCode transcript 备注

完整 session/subagent transcript 不在项目 `.memory` 中，而在：

- `/home/dev-codex/.local/share/opencode/opencode.db`
- `/home/dev-codex/.local/share/opencode/tool-output/`
- `/home/dev-codex/.local/share/opencode/log/opencode.log`

child session 通过 `session.parent_id` 关联，但数据库检查显示没有复制 parent 的
message/part；child 主要收到自己的 role/system 配置和显式 dispatch。不要把 child
cache read 解释为 parent transcript 自动继承。

## 不要做的事

- 不要 reset/clean dirty worktree。
- 不要把窄 gate PASS 当作 terminal acceptance。
- 不要跳过 P0-A/P0-B/P0-C 进入 P1/P2。
- 不要修改 `query_storage_hit_length` 以改善指标。
- 不要触碰 3090 或生产环境。
- 不要把未落盘的 agent 返回摘要当作完整 durable evidence。
