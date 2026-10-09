# P0-B-LIVE-CHAIN-20260911-R109

- **工作标题：** P0-B-LIVE-CHAIN-20260911-R109
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P0-B-LIVE-CHAIN-20260911-R109.md`：**
- Task ID: `P0-B-LIVE-CHAIN-20260911-R109`
- Invocation: `ses-p0b-live-chain-r109-20260911` (fresh)
- Role: `tester`
- Epoch: `2026-09-11`
- ENTRY: `ACCEPT`
- Repo (read-only): `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
(HEAD `4f41f5bab5`; not modified)

## 实际改了什么
tester 对既有 local 3090 server 只用 public HTTP、读取 log；不启动/停止/重启/配置服务器，不碰 GPU/lock，不改 repo/test/report。预算 7 POST、3 GET、约 5–6 分钟，远低于上限。

## 生成结果与验收
实际触达 L3-resident positive full KV hit（46,848 tokens）→ HOST_ALLOC 不可分配→ park→真实 allocability 变化→wake grant→accepted all-or-nothing KV+Mamba finalize→READY，target HTTP 200。但冻结 reducer exit 1、**7/11 predicates，最终 NOT_VERIFIED**，不可称 P0-B PASS。未满足项：缺 `durability_barrier` 正向 durability 证据（trace marker 禁止新增）；Mamba generation 89→105 但中间无连续 `host_allocability_change` edges；仅一个 waiter、没有已释放 predecessor；首次 wake retry 成功、没有 oracle 要求的 post-wake retry attempt lineage。negative safety predicate 通过，无 crop/miss/recompute/partial/discard。Raw bundle/hash 在报告内。

## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab5`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P0-B-LIVE-CHAIN-20260911-R109.md` → `.memory/rh-p0b-harness-durability/P0-B-LIVE-CHAIN-20260911-R109.md`; SHA256 `d16c5d27e64cba6c305b76a02af3663b50ed085c13da8b9363322ee03b1b7e8d`; source state `tracked`
