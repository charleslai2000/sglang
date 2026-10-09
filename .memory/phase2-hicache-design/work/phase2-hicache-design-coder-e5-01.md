# P2-1 Step 1 (M1a) — 增量计费准入实现（coder e5-01）

## status

**done** — M1a 按设计 §5 改动 1/2 落地（`_device_charge` helper + 双门同用 + AddReqResult.RESTORE_DENIED 扩展）。
**关键发现（需专家裁决）**：设计 §1/§2.4 的前提"计费 = 全长 total_tokens、不区分已 resident 前缀"与
本树代码事实不符——现行公式 `cand_extend_input_len = len(full_untruncated_fill_ids) − len(prefix_indices)`
（上游 #27616，563c3418a7f 引入）**已经**减掉 device 前缀。M1a 落地后 charge 语义与落地前逐位一致
（见 summary 的对比证明），落地 = 提取 helper + 双门显式化 + max(0,·) 兜底 + torch-free 回归；
设计公式若按字面套在现变量上会**二次减除、欠计费（超卖风险）**——本实现按设计自身 invariant 证明
自洽的语义落地（helper 入参 = 全长，内部减 prefix_indices）。未 commit 未 push。

## artifacts

| 文件:行 | 改动 | 语义 |
|---|---|---|
| `python/sglang/srt/managers/schedule_policy.py:857-874` | 新增 `PrefillAdder._device_charge(req, full_input_len, max_new) -> int` | 设计 §2.4/§4.4 公式的显式化：`max(0, full_input_len − len(req.prefix_indices)) + max_new + page_size + mamba_gap`。只减 device 前缀（已 resident、锁内、不参与 available+evictable）；host/storage 全额计费（load_back 后变 resident）；mamba_gap 经 `_mamba_gap_budget_for_req` 折入（`_mamba_slot_cost>0 且 req.mamba_pool_idx is None` 才计）；max(0,·) 兜底 retraction 边缘（prefix > input 时现状会以负 charge 漏过门） |
| `python/sglang/srt/managers/schedule_policy.py:1270-1275` | `total_tokens` 改用 `_device_charge(req, len(req.full_untruncated_fill_ids), max_new)` | 门 1（rem_total_tokens）与锁内复查门 2（rem_total_tokens_lock）共用的同一 total_tokens 值，双门同改（设计 §5 改动 1） |
| `python/sglang/srt/managers/schedule_policy.py:524-527` | `AddReqResult` 增 `RESTORE_DENIED = auto()` | 设计 §5 改动 2（M1b T7 的返回码）；当前无任何路径返回（注释明示），M1b 的 scheduler 分支消费 |
| `3090-dev/test_storage_regression.py` | stubenv 扩展 + 新类 `IncrementalBillingAdmissionTests`（9 测试） | 公式级 6 测（首访型=全长计费、只减 device 前缀、全命中=仅 decode、负 span 兜底、mamba_gap 两态、与落地前公式逐位等价表）+ 门级 2 测（门 1 增量准入、门 2 锁内复查同用增量 charge，`_SteppedAllocator` 模拟两次读间预算收缩）+ invariant 1 测（Σ(charge+device_hit) ≤ pool，2 重访并发通过而首访被拒的 width-2 形态不超卖） |

## evidence

1. 本机 `python3 -m py_compile`（schedule_policy.py + test_storage_regression.py）：`exit=0`。
2. 本机 torch-free 回归：`test_storage_regression.py` **Ran 20 tests / OK**（既有 11 + 新增 9）；
   `test_drain_reentry.py` **Ran 7 tests / OK**。
3. **RED→GREEN**：把门公式临时改回设计所认为的"全长计费"（`len(full)+max_new+page`）→ 新门级测试
   2 失败（gate1/gate2 均 NO_TOKEN 预期 CONTINUE）；恢复后 20/20 全绿——证明测试确实守卫增量语义。
4. 部署 3090 `/root/sglang-b1-continuity/`（scp 2 文件）双侧 md5 逐文件一致：
   - `python/sglang/srt/managers/schedule_policy.py`：`54b0a0e6abdcad255ceb03b49a5c9345`（双侧）
   - `3090-dev/test_storage_regression.py`：`83c9fc121d44b3741225896a4a22047c`（双侧）
5. 远端 `/root/miniconda3/envs/sglang-patch/bin/python -m py_compile`（Python 3.10.21）：`REMOTE_PY_COMPILE_OK`。
6. 远端真实 torch（2.13.0+cu130）+ 真实安装包路径（`schedule_policy.__file__` = 部署路径）回归：
   `test_storage_regression.py` **20/20 OK**、`test_drain_reentry.py` **7/7 OK**。
   首跑 9 error（`ValueError: config namespace 'parallel' not published`）→ setUp 仿上游
   `test_prefill_adder.py` 加 `set_global_server_args_for_scheduler(ServerArgs(model_path="dummy"))`
   （仅 torch 路径）后全绿；重传后 md5 双侧一致。
7. 3090 引擎未启动：`nvidia-smi` 15 MiB 空闲、`No running processes found`、无 sglang 引擎进程。
8. git diff 审查：schedule_policy.py 仅 M1a 三处（helper/门/enum）叠加于既有 P2A 计数器之上，
   无无关改动；test_storage_regression.py 为新增文件（e4 起未跟踪），本次仅扩展 stubenv + 新测试类。

## summary

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
  `len(prefix_indices)`，partial-hit 会欠计费（charge = L − 2d），破坏设计自身 invariant 证明
  （该证明只对"charge 不含 device_hit"成立）——**禁止按字面实施**；3. "重访型 charge 变小"的
  机制（K=32 run2 width=2 帧）在现状代码中即已存在，M1a 的 K=1/K=2 双 turn 验证点应能直接观测。
- 设计 §4.4 参数名 `cand_extend_input_len` 与本树同名变量语义冲突（后者已减前缀），实现改为
  `full_input_len` 并注释；行为按设计公式意图（=其 invariant 证明自洽的唯一读法）。

## followups

- 专家裁决项（open_issues 1-3）：设计前提勘误确认；是否仍保留 M1a 为独立 Step（行为零变化，
  仅显式化+回归面）还是并入 M1b 批次；RESTORE_DENIED 是否随 M1b 再落（本步按设计 §6 先行）。
- tester 侧：K=1 基线回归（rs3 型恢复 99.8% 不回归——本步零行为变化，预期全绿）+ K=8 观察
  deny 次数/width（重访型增量 gate 在现状即生效，`evt=prefill_deny_summary` 30s 聚合行可量化）。
- 下一步 Step 2 (M1b) 的 T6 判据（restore_potential + WAIT[DEVICE_QUOTA]）按设计 §2.5 使用本 helper
  的增量 charge 作为容量谓词——helper 已是 PrefillAdder 方法，M1b 直接复用。

## open_issues

1. **设计前提勘误**（§1"全长计费"= 误读）：已按"公式意图"落地（行为零变化），请裁决是否接受
   该解读（唯一与设计 invariant 证明自洽的解读），以及"设计字面公式=二次减除"是否需要设计修订。
2. `_device_charge` 参数名偏离设计 §4.4 签名（`cand_extend_input_len` → `full_input_len`）：
   语义必要（同名现变量已减前缀，沿用会造成二次减除），列入待裁决。
3. `RESTORE_DENIED` 枚举成员当前无返回路径（M1b T7 才使用）——设计 §6 把改动 2 列入 Step 1，
   已按设计先行落地并注释；若裁决"惰性落"，删除 3 行即可（测试不依赖它）。
4. 上游 #27616（563c3418a7f）即增量计费源头——本步等于把既有上游行为显式化为设计形态；
   若后续要"重访型进一步放宽"，那是新机制（如 §2.4 chunk 级/门 2 后 load-back 后再复查），超出 M1a。
5. torch 路径 setUp 依赖 `set_global_server_args_for_scheduler`（上游测试同款先例）；若远端
   server_args.py 未来移除该 shim，测试需改走 `runtime_context.publish(role=...)`。
