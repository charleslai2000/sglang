# P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R122

- **工作标题：** P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R122
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R122.md`：**
- Invocation: `ses-p1-controlled-eviction-r122-20260911`
- Contract (frozen, unmodified): `R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md`
sha256 `2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b`
— VERIFIED match before starting.
- Server: PID 48746 / scheduler 48806, `http://127.0.0.1:30000`, health 200
before and after. No server control, no repo edits, no product instrumentation.

## 实际改了什么
在健康既有 server 上执行约 50 requests、16 min bounded run；无 repo edits、instrumentation 或 server control。新增/运行 R122 bundle driver 和 gate artifacts（报告及 work/R122-bundle 文件）。冻结 R121 contract 未改，另依据 user-ratified R122 addendum 运行。

## 生成结果与验收
**NOT_VERIFIED**，且 R122 harness/profile gate 缺陷：Gate A 使用 stale host evictable，误报 allocable 43,936，fresh snapshot 实为 2,786，低于 F1 所需 41,472；报告发现 addendum 的 `full_free+full_evictable` 实际测 device pool，而 HOST_ALLOC 阻塞的是 L2 host pool，且现有只读接口没有 fresh host-evictable。T 先以 host hit 被调度，未被驱逐，导致无 storage query/D_req、无 SPEC_BUDGET park/release→wake；T 不是 non-device-resident，F1 也仅 partial。C1–C5 均未通过/建立，顺序 Gate A/B 未展示。无新产品 defect 证据；不作无意义 rerun，待裁定 gate pool、fresh host read-only source 与 R121-faithful recipe 授权。

### 报告列出的产物/证据
- `phase2-hicache-design/work/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R122.md`：`work/R122-bundle/`: `raw.log`, `probe.log`, `watch.log`, `requests.jsonl`,
`state.jsonl`, `gate_evidence.jsonl`, `chain.json`, `manifest.json`
(`p0b.raw-bundle.v3`), `baseline-offsets.txt`, `condition-evidence.md`,
`driver122.py`, `driver122_gate.py`.
sha256 (full list in `R122-bundle/sha256sums.txt`):
- `raw.log` `790cabec10968d9de3bf19125492b0c0f204c8e4fd650ac20c0abbd3b41bb8c2`
  (21,039,644 B)
- `probe.log` `67b5133a885c1e6b78a183998bff55cb7960b8a59095a61793035d1e2fc23614`
  (3,302,664 B)
- `chain.json` `a6e8a824e3a70f8ae8358d878c5480edb0b05ad85839a8d8ea9106b942bef015`
- `condition-evidence.md` `c64a2a16eebdd336b0b14408f574ee7bf67450483d2d2e016417d56824d9cb5f`…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R122.md` → `.memory/rh-p1-durable-replay-eviction/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R122.md`; SHA256 `c8a6f444eeb732b4f1095931fe392f52303f40be7ba643df0af87845170406bc`; source state `tracked`
