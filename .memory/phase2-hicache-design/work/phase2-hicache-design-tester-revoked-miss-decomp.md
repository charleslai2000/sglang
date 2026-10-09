# phase2-hicache-design-tester-revoked-miss-decomp (Step ①: full-miss 明细拆分)

## status
done

## artifacts
- 本分析：从既有 64G 三档 engine log + runs.csv 零成本拆分（无新 run、未动 3090 配置）。
- 证据源：remote `/root/engine-gate2-b64k{4,8,16}.log` + `/root/evidence-gate2-b64k{4,8,16}/run-*/runs.csv`。

## evidence — restore_disposition reason 精确计数（engine log）

| reason | K4 | K8 | K16 |
|---|---|---|---|
| revoked:miss | 94 | 231 | 913 |
| revoked:alloc | 0 | 2 | 2 |
| shortfall | 3 | 82 | 130 |
| too_short | 6 | 155 | 23 |
| denied_rate_limit | 0 | 54 | 103 |
| hybrid_discard | 0 | 19 | 17 |

（前一轮 grep `reason=revoked` 匹配到 `revoked:miss`/`revoked:alloc` 前缀，故 233/94 为 `revoked:miss`。）

## evidence — revoked:miss 按 hit 类拆分（rid 匹配 runs.csv，精确）

| 类 | 语义 | K4 | K8 | K16 |
|---|---|---|---|---|
| **A: storage>0** | L3 已有数据但 restore 仍 RECOMPUTE → **真 sidecar/storage shortfall** | 1 (2%) | **19 (33%)** | 29 (16%) |
| **B: device/host partial (s=0)** | 无 L3，仅 device/host 部分覆盖 | 35 (87%) | 26 (45%) | 74 (43%) |
| **C: full cold-miss (d0/h0/s0)** | 全冷 miss | 4 (10%) | 12 (21%) | 69 (40%) |

（revoked:miss 日志行数 > runs.csv 匹配行数：部分 rid 为 HEALTH_CHECK 或未进 runs.csv，不影响类占比结论。）

## summary
用户裁决的"只有真正 storage/sidecar shortfall 才值得追"对应 **类 A**。拆分结果：
- **类 A 非零且显著**：K8 33%（19/57）、K16 16%（29/172）。典型模式 `d9/h0/s30xxx` / `d9/h0/s24xxx` / `d9/h0/s34xxx` —— device 有 9 个 token、**storage_hit>0**（L3 确实读回了 KV），但 restore 仍 `revoked:miss` 落到 RECOMPUTE。这是"L3 数据在、但 restore 链在 mamba sidecar / TRAILING 处断掉"的强信号 —— 与 ledger 2026-09-04 coder-restore-hit0-e1 的 **C 次因（KV 幸存但 batch_exists_v2 mamba TRAILING boundary=0 折叠）** 高度吻合，且现在**独立于 L3 容量**（recycle=0 时仍出现）。
- **类 B（device/host partial）最大**：K8 45% / K16 43% —— 这是 12-turn agent 负载的正常形态（KV 部分在 device/host、前缀未满整链），属 load-shape，非 defect。
- **类 C（全冷 miss）**：K4 10% / K16 40% —— K16 因 GC 回收升高的 cold-miss 由容量解释；K4 的低冷 miss 正常。
- **结论**：只剩 **类 A（storage>0 但 restore 断）** 值得继续追，对应 mamba sidecar restore / TRAILING 折叠边界。这正是 32-slot saturation run 将重点观测的对象（在 fill→1.0、recycle=0 下看类 A 是否放大成 cliff）。

## followups
1. 类 A 的具体断点：下一个 run（32-slot saturation）里对 `d9/h0/s>0` 的 revoked:miss 行加 sidecar_hits / batch_exists_v2 明细，定位是 KV 段还是 mamba TRAILING 段断。
2. 若 32-slot saturation 下类 A 随 fill→1.0 放大 → 坐实 mamba pool saturation cliff（门2 正题）。

## open_issues
- revoked:miss 日志行数（94/231/913）与 runs.csv 匹配行数（40/57/172）不一致，因部分 rid 非 agent 请求（HEALTH_CHECK 等）；占比按匹配行计，方向性结论不受影响。
- 类 A 判定依赖 runs.csv 的 storage_hit>0 字段；单 rid 存在 d9/s>0 但 engine 仍 revoked:miss，确证"读回部分成功但未达 usable restore"。
