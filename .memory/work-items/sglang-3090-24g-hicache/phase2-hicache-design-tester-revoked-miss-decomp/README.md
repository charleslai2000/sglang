# phase2-hicache-design-tester-revoked-miss-decomp

- **工作标题：** phase2-hicache-design-tester-revoked-miss-decomp
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-tester-revoked-miss-decomp.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-tester-revoked-miss-decomp.md`：**
用户裁决的"只有真正 storage/sidecar shortfall 才值得追"对应 **类 A**。拆分结果：
- **类 A 非零且显著**：K8 33%（19/57）、K16 16%（29/172）。典型模式 `d9/h0/s30xxx` / `d9/h0/s24xxx` / `d9/h0/s34xxx` —— device 有 9 个 token、**storage_hit>0**（L3 确实读回了 KV），但 restore 仍 `revoked:miss` 落到 RECOMPUTE。这是"L3 数据在、但 restore 链在 mamba sidecar / TRAILING 处断掉"的强信号 —— 与 ledger 2026-09-04 coder-restore-hit0-e1 的 **C 次因（KV 幸存但 batch_exists_v2 mamba TRAILING boundary=0 折叠）** 高度吻合，且现在**独立于 L3 容量**（recycle=0 时仍出现）。
- **类 B（device/host partial）最大**：K8 45% / K16 43% —— 这是 12-turn agent 负载的正常形态（KV 部分在 device/host、前缀未满整链），属 load-shape，非 defect。
- **类 C（全冷 miss）**：K4 10% / K16 40% —— K16 因 GC 回收升高的 cold-miss 由容量解释；K4 的低冷 miss 正常。
- **结论**：只剩 **类 A（storage>0 但 restore 断）** 值得继续追，对应 mamba sidecar restore / TRAILING 折叠边界。这正是 32-slot saturation run 将重点观测的对象（在 fill→1.0、recycle=0 下看类 A 是否放大成 cliff）。

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-tester-revoked-miss-decomp.md`：- 本分析：从既有 64G 三档 engine log + runs.csv 零成本拆分（无新 run、未动 3090 配置）。
- 证据源：remote `/root/engine-gate2-b64k{4,8,16}.log` + `/root/evidence-gate2-b64k{4,8,16}/run-*/runs.csv`。

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-tester-revoked-miss-decomp.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-tester-revoked-miss-decomp.md`; SHA256 `768a13b90dfce81e4badac27cde72fc70483010dad33f11dfb4bca4357756772`; source state `tracked`
