# P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R121

- **工作标题：** P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R121
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R121.md`：**
- task_id: `P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R121`
- invocation: `ses-p1-controlled-eviction-r121-20260911`
- role: `tester`
- epoch: `2026-09-11`
- status: **not_verified** (verification executed to completion; P1 does NOT close)
Frozen contract verified before starting:
`work/R121-bundle/P1-R121-CONTROLLED-EVICTION-CONTRACT.md` sha256
`2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b` (matches).

## 实际改了什么
在既有、健康的 local RTX 3090 server 上按冻结合同执行 controlled-eviction workload：构建 F1/F2/T、施加压力并 drain，再 replay `[F1,F2,T]`。无产品编辑、instrumentation 或 server 生命周期变更；录制原始 raw/probe/request/state/chain evidence。

## 生成结果与验收
本次首次实现 full durable T、device+host non-resident、SPEC_BUDGET park 与 F1 exactly-once release(epoch 96→97)→T wake。但 P1 **NOT VERIFIED / 不关闭**：host headroom 硬前提失败；T 需要 27,328，初始 host allocable 6,178，reclaim 后仅 24,670，发生两次 alloc_failed 后 timeout recompute，缺 full L2→L1 restore/generation。C1 的 build identity join 亦不完整（park/query replay identity 与 durable build session 不同，且无 finalize）。procedure gap 是 harness 用 request-queue idle 代替 host capacity precondition；P1 需新 run 达到足够 headroom，不能以 C2/C3 成功代替全链。
was revoked twice with `alloc_failed`, and T ended in `restore_recompute
cause=timeout`. The top-level hard precondition **HOST_HEADROOM_SUFFICIENT is
unmet**, so C4 and C5 FAIL and the `l2_to_l1_restore_generation` leg is missing.

### 报告列出的产物/证据
- `phase2-hicache-design/work/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R121.md`：| file | sha256 |
|---|---|
| `raw.log` (server slice from line 2312756) | `2bdca1c2e605ec3463bcdac9501a6e8b52a836a5fe99aac3b908db880b80cca9` |
| `probe.log` (probe slice from line 25948) | `424a1ec95cf9c2cee94d075fd0dbb59ddf7b7d4a083403e2b45225fea1018630` |
| `requests.jsonl` | `f886dfad319738481f05388da8cfada382649448af8701b7bbc7cf9577316b15` |
| `state.jsonl` | `77fb536f8770e2e59c575aabe977566e6f13cf5784678f5b9d42a5f092fb817a` |
| `chain.json` | `1f9dcef8d090d0b8a12aa388d935067c80ed5770eea0ab4249c0496e22325a8a` |
| `condition-evidence.md` | `ec0258851c25b390d9798ea66bf6b9554d47042978441a74d62b192ce26df1cd` |…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R121.md` → `.memory/rh-p1-durable-replay-eviction/P1-SPEC-BUDGET-CONTROLLED-EVICTION-20260911-R121.md`; SHA256 `d0b3dd87dd1b5728d2a43eee5be2815812dea5550baad9c7afb13002c6f7ce02`; source state `tracked`
