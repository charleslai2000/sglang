# phase2-hicache-design-coder-e5-01

- **工作标题：** phase2-hicache-design-coder-e5-01
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-coder-e5-01.md`：**
**done** — M1a 按设计 §5 改动 1/2 落地（`_device_charge` helper + 双门同用 + AddReqResult.RESTORE_DENIED 扩展）。
**关键发现（需专家裁决）**：设计 §1/§2.4 的前提"计费 = 全长 total_tokens、不区分已 resident 前缀"与
本树代码事实不符——现行公式 `cand_extend_input_len = len(full_untruncated_fill_ids) − len(prefix_indices)`
（上游 #27616，563c3418a7f 引入）**已经**减掉 device 前缀。M1a 落地后 charge 语义与落地前逐位一致
（见 summary 的对比证明），落地 = 提取 helper + 双门显式化 + max(0,·) 兜底 + torch-free 回归；
设计公式若按字面套在现变量上会**二次减除、欠计费（超卖风险）**——本实现按设计自身 invariant 证明
自洽的语义落地（helper 入参 = 全长，内部减 prefix_indices）。未 commit 未 push。

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-coder-e5-01.md`：**
**落地前后对比（首访型不变的证明）**：
- 落地前：`total_tokens = (L − d) + max_new + page + gap`（L=全长，d=len(prefix_indices)）。
- 落地后：`_device_charge` 输出 `max(0, L − d) + max_new + page + gap`；d ≤ L 时逐位一致（等价表测试
  `test_charge_equivalent_to_legacy_formula` 8 组 (full, prefix) 对钉死）；首访型 d=0 → charge = L +
  max_new + page + gap 与现状完全一致（`test_first_visit_charge_equals_full_billing`，27877 实测数值）。
- 唯一行为差异 = max(0,·) 兜底：d > L（retraction 边缘）时现状以负 charge 漏过门，落地后按
  max_new+page+gap 计（严格更安全，且设计公式自带该 guard）。
- invariant 成立性：门保证 Σcharge ≤ available+evictable；device 前缀 ∈ used（locked）→
  Σresident = Σcharge + Σdevice_hit ≤ pool（`test_invariant_sum_resident_le_pool` 模拟 2 重访并发
  通过、首访被拒、Σresident=24256 ≤ 32768）。
**发现（重要，待裁决）**：设计 §1 断言"计费 = 全长、不区分已 resident 前缀（过度保守）"与代码不符——
`cand_extend_input_len` 自上游 #27616 起即已减 `prefix_indices`（git blame 563c3418a7f 证实；本树
HEAD 与 3090 部署树同式）。归因报告 §1.1 的公式渲染（标注"全长，非 chunk"）同样误读。因此：
1. M1a 无行为变化可落地，落地=显式化+测试（本实现）；2. 设计公式若按字面用现变量二次减除

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-coder-e5-01.md`：| 文件:行 | 改动 | 语义 |
|---|---|---|
| `python/sglang/srt/managers/schedule_policy.py:857-874` | 新增 `PrefillAdder._device_charge(req, full_input_len, max_new) -> int` | 设计 §2.4/§4.4 公式的显式化：`max(0, full_input_len − len(req.prefix_indices)) + max_new + page_size + mamba_gap`。只减 device 前缀（已 resident、锁内、不参与 available+evictable）；host/storage 全额计费（load_back 后变 resident）；mamba_gap 经 `_mamba_gap_budget_for_req` 折入（`_mamba_slot_cost>0 且 req.mamba_pool_idx is None` 才计）；max(0,·) 兜底 retraction 边缘（prefix > input 时现状会以负 charge 漏过门） |…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-coder-e5-01.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-coder-e5-01.md`; SHA256 `8652cb860bba4c51273c95d3e397480897c7377f447dd4723ac307678d5588f3`; source state `tracked`
