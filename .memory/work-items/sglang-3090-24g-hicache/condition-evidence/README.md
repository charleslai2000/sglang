# condition-evidence

- **工作标题：** condition-evidence
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 6
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/R120-bundle/condition-evidence.md`：**
Task `P1-SPEC-BUDGET-FULLCHAIN-20260911-R120`. Frozen acceptance
`R120-bundle/P1-ACCEPTANCE-CONDITIONS.md` sha256
`b5ffa106be7863a2baedd528249eb6bccb63469619af73970a4c477813c27822` (verified).
Server PID 48746 / scheduler 48806, health 200, read-only. All `raw.log:N`
refs are the frozen server-log slice (server line = raw line + 2051151);
`probe.log:N` refs are the frozen `/tmp/t38c-probe.log` slice beyond byte
`33890204`.
Workload actually run (one clean line, no decoys):

**`phase2-hicache-design/work/R121-bundle/condition-evidence.md`：**
- Task: `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R121`
- Invocation: `ses-p1-controlled-eviction-r121-20260911`
- Contract: `P1-R121-CONTROLLED-EVICTION-CONTRACT.md`, sha256
`2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b` (VERIFIED match)
- Frozen bundle: `raw.log` (offset 2312756, wall 2026-09-12 00:28:40..00:34:09),
`probe.log` (offset 25948), `requests.jsonl`, `state.jsonl` (hashes in `manifest.json`)
- Measurement window: raw line 103819 / server line 2416575 / wall 2026-09-12 00:32:50.
Identity: `rid=r121-p3-R-T`, `session_id=r121-s-R-p3`, `session_generation=60`,

**`phase2-hicache-design/work/R122-bundle/condition-evidence.md`：**
- Task: `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R122`
- Invocation: `ses-p1-controlled-eviction-r122-20260911`
- Contract: `P1-R121-CONTROLLED-EVICTION-CONTRACT.md`, sha256
`2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b` (VERIFIED match)
- Frozen bundle: `raw.log` (server offsets 2583017..2761501), `probe.log`
(bytes 46280601..49583265), `requests.jsonl`, `state.jsonl`,
`gate_evidence.jsonl` (hashes in `manifest.json`)
- Measurement window: raw line 53626 / server line 2636642 / wall 2026-09-12

**`phase2-hicache-design/work/R123-bundle/condition-evidence.md`：**
- Verdict: **NOT_VERIFIED** (frozen chain not exhibited on this bundle).
- Bundle: `work/R123-bundle/` (this directory). Window server-log slice in `raw.log`
(server lines 3084733..3222416, 137684 lines, sha256 in `sha256sums.txt`).
- Bindings: R121 contract `2ac86b5a...`, R122 addendum `92ad1c29...`, v2 correction
`cbd1cf57...`, R123 temporal contract `P1-R123-TEMPORAL-WAKE-GATE-CONTRACT.md`.
- Gate basis: v2 (`host_allocable := free_after_reclaim`; L2 `mem_pool_host` via
`host_alloc.v1`). v1 device-pool gate invalidated.
- Read-only w.r.t. server/product; server PID 48746 not restarted; no profile change;

**`phase2-hicache-design/work/R124-bundle/condition-evidence.md`：**
All references are to `/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r124.log`
(`raw.log` is the verbatim slice `[769, 393328]`, offset = server line - 768) unless
noted as `probe` (`/tmp/t38c-probe.log`, run slice in `probe.log`).

**`phase2-hicache-design/work/R125-bundle/condition-evidence.md`：**
- Task: `P1-DURABLE-PREFIX-REPLAY-20260912-R125`
- Binding contract: `P1-R125-DURABLE-PREFIX-REPLAY-CONTRACT.md`,
sha256 `f78a2fc698de375de612ace8c023e4a6518a6781c155c2f5e92b66dd521f3c1f` (VERIFIED)
- Base contracts VERIFIED: R121 `2ac86b5a…b3b`, R123 `bf7b09ee…1e1f8`,
R124 correction `c57905ff…3cd2`.
- Server: PID `3082643`, scheduler child `3086752`, port 30000, health 200.
Fix present: `python/sglang/srt/managers/scheduler.py` sha256
`892efc25e2a9ef7c5ebb4afa09cf6914182b1467981d14cd76c53eea5d8de9d7` (VERIFIED).

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** NOT_VERIFIED

**`phase2-hicache-design/work/R120-bundle/condition-evidence.md`：**
**NOT_VERIFIED.** All five conditions are unmet. Primary decisive unmet
condition: **C2/C3 — no SPEC_BUDGET park** (T device-resident → declined
`too_short`; F1 replay prefetch 2047 « 39321 → budget never exhausted), with
**C1** (neither build fully L3-durable without eviction pressure) as the
upstream cause and **C5** (live host allocable 28672 < 70529) as an independent
environmental block.

**`phase2-hicache-design/work/R121-bundle/condition-evidence.md`：**
Top-level hard precondition unmet: **HOST_HEADROOM_SUFFICIENT = FAIL**.
Consequently C4 (full restore gate) and C5 (host headroom) FAIL and the
`l2_to_l1_restore_generation` leg of the chain is not produced. C1, C2, C3 PASS.

**`phase2-hicache-design/work/R122-bundle/condition-evidence.md`：**
The mandated drain gate was implemented and run, but it did **not** actually
enforce the precondition: it passed on a 16-minute-stale host `evictable`
reading (telemetry coalescing), opening the window on a saturated host. The
fresh in-window `host_alloc.v1` snapshot gives host allocable **2786** tokens
against `F1_required=41472`. T was also never evicted from device/host
(`device_hit_tokens=2048`, `host_hit_tokens=22080`), so it never parked on
SPEC_BUDGET and the R121 chain was not reproduced. C1 is not evaluable; C2–C5
FAIL.

**`phase2-hicache-design/work/R125-bundle/condition-evidence.md`：**
Gate 0 (identity) PASS; Gate 1 (no premature consumption) PASS on run 1;
**Gate 2 NON-EVIDENCE** (at T's grant both blocked domains' generations
advanced, so the old all-generations rule would also have granted);
Gate 3: the durable boundary was fully fetched (`kv_fetched==D_req`) but the
literal Gate 3 predicates `disposition==FULL` and
`restore_success.n_tokens==D_req` were not met (PARTIAL/`shortfall` from the
11-token durable-boundary-external tail; success `n_tokens = D_req-2`).
The P1 fix is therefore **not runtime-exercised** by this experiment.


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `4f41f5bab562b99562f30c67540eb05344d13637`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R120-bundle/condition-evidence.md` → `.memory/phase2-hicache-design/work/R120-bundle/condition-evidence.md`; SHA256 `8a12c98c9bb703c70c2d1cb78d7a7f5149152054d7b741c9a3a74b4c947ae525`; source state `tracked`
- `phase2-hicache-design/work/R121-bundle/condition-evidence.md` → `.memory/phase2-hicache-design/work/R121-bundle/condition-evidence.md`; SHA256 `ec0258851c25b390d9798ea66bf6b9554d47042978441a74d62b192ce26df1cd`; source state `tracked`
- `phase2-hicache-design/work/R122-bundle/condition-evidence.md` → `.memory/phase2-hicache-design/work/R122-bundle/condition-evidence.md`; SHA256 `c64a2a16eebdd336b0b14408f574ee7bf67450483d2d2e016417d56824d9cb5f`; source state `tracked`
- `phase2-hicache-design/work/R123-bundle/condition-evidence.md` → `.memory/phase2-hicache-design/work/R123-bundle/condition-evidence.md`; SHA256 `72615eb8ec3e66cfb452e21297a1f4b42cc8ce10a026ac308deb63fe4bbd6286`; source state `tracked`
- `phase2-hicache-design/work/R124-bundle/condition-evidence.md` → `.memory/phase2-hicache-design/work/R124-bundle/condition-evidence.md`; SHA256 `351d9692a0738a4af33f28f1c5c19b3f08895189bff3532d9b0516b8968217fc`; source state `tracked`
- `phase2-hicache-design/work/R125-bundle/condition-evidence.md` → `.memory/phase2-hicache-design/work/R125-bundle/condition-evidence.md`; SHA256 `6a872b72390152b80a60e06edfb69ac522ff9e6bfde247ca547d6426f8d353f0`; source state `tracked`
