# T003 L17 A/B/C 数值结果

## 配对条件与重放锚点

固定 T002 BF16 upstream capture（层17，query position 4095，Q `[2048,8,512]`，current K/V `[2048,2,512]`）。两套 cache capture 的逻辑索引、物理 slot IDs 一致；BF16 prefix 转 E5M2 后与捕获 E5M2 K/V 字节逐元素相同。K/V descale=`1.0`，softmax scale=`1.0`；无窗口截断，causal，page size 1。三臂使用同一现有 HEAD 两阶段 `extend_attention_fwd` kernel，通过 T002 已验证的真实 suffix Attention 注入机制完成整段 4K forward。

- A：BF16 prefix cache + BF16 operand 路径。与 frozen BF16 live L17 Attention **逐元素相同**；suffix logits 与 frozen BF16 baseline **逐元素相同**。
- B：捕获的 E5M2 prefix 原始 cache + E5M2 operand 路径。与 T002 同 BF16 upstream 的 reverse-cache counterfactual Attention **逐元素相同**；suffix logits 与 T002 reverse-cache logits 一致（top1 236761）。
- C：与 B 完全相同 FP8 bytes，在相同物理 slots 一次性解码、乘各自 captured scale（本例均1.0）并 round 到独立 BF16 pool；运行既有 BF16 kernel，kernel scale 参数置1，未再次量化或重复应用 scale。C cache pool 与 B 独立；原始 FP8 pool 未修改。

完整数值：`/data/sglang-hicache/g2-quasar-runs/g2-layer17-abc-precision.json`、`g2-layer17-abc-suffix-metrics.json`、`g2-layer17-abc-suffix-pairwise.json`。三臂 raw attention 结果另存于 `g2-layer17-bf16-{A,B,C}.attention.pt`；服务运行工件目录由 metrics JSON 列出。

## L17 Attention 输出

| Pair | relL2 | P99 abs | Max abs | changed |
|---|---:|---:|---:|---:|
| A vs B | 0.0092772031 | 0.015625 | 0.0234375 | 3342 |
| B vs C | 0.0068593388 | 0.01171875 | 0.0234375 | 3033 |
| A vs C | 0.0063851913 | 0.01171875 | 0.0224609375 | 2929 |

## 完整 Forward suffix logits 与贪心结果

所有实际注入 Attention tensor 均与离线 A/B/C replay **逐元素相同**。A suffix 与 frozen BF16 baseline exact。

| Arm | Final top-1 / logit | top-2 / logit | Margin | 与 A 的 logits relL2 / max abs | served token |
|---|---|---|---:|---:|---:|
| A | 128870 / 7.08258057 | 236761 / 7.02353477 | 0.05904579 | 0 / 0 | 128870 |
| B | 236761 / 7.40628147 | 128870 / 7.34755993 | 0.05872154 | 0.10537908 / 2.39436722 | 236761 |
| C | 107 / 6.84605455 | 236761 / 6.69776630 | 0.14828825 | 0.05361957 / 1.13378572 | 107 |

其他 pairwise suffix logits：B vs C relL2 `0.14041951`, max abs `2.26386070`; A vs C 如上。C 相对 B 的 token top-1 又变为 token 107，并非恢复 A 的 greedy token。

## 因果解释与限制

- A/B 锁定 BF16 upstream 与 kernel 参数，首先 exact-replay 已验证的 live/counterfactual；这对测得 L17 的 E5M2 cache representation 局部总效应。
- B/C 的压缩 cache 数值/字节相同，仅将 B 的 E5M2 operand 路径换为一次正确反量化的独立 BF16 cache + 原有 BF16 kernel。因此 B/C 差值支持：低精度运算 operand 路径会额外改变 L17 输出，且单层 Attention 输出变化可经真实 suffix 改变全部 262144 logits 和 top-1。
- C 没有向 A 收敛到 exact；A/C residual 表示量化压缩后的 cache 值损失，以及 C 的 BF16 舍入/既有 BF16 kernel数值路径差异。不能把 A/C residual 纯粹等同于“仅存储量化误差”，也不能宣称 C 全局精度恢复。C 最终 top-1 (107) 不等于 A (128870) 或 B (236761)，说明该局部高敏感位置 intervention 仍非整体模型质量指标。
- 独立真实服务中 no-op L17 Attention 与既有 BF16 upstream live 输出相同，A/B/C 实际注入张量逐元素等于离线 replay；L17 本层以外的真实服务数值轨迹及完整 A/B/C 同一运行态无法同时冻结。Suffix logits 是固定模型/请求上的单位置干预结果，不能外推为广泛任务准确度。
- 三个 capture 的生产默认 kv dtype 均为 BF16（suffix运行只注入 Attention 输出）；B/C 是在真实 BF16 服务的 Attention output seam 做数学反事实注入，不能称为完整E5M2-KV服务结果。
- 无生产源码被修改；real service overlay 从 HEAD 独立加载两阶段kernel。未测试容量/性能或其它position/layer。E5M2 仍 **NOT ACCEPTED**。
