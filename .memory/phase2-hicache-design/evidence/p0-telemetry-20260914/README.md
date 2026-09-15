# P0 telemetry — authoritative inputs (2026-09-14 snapshot)

本目录是 P0 telemetry 修复与终审所依赖的**权威输入副本**，从本机 `/mnt/data`
复制入库，目的是让工作**可在另一台主机上继续**（`/mnt/data` 是本机 NVMe，换机即失效）。

## 内容

| 目录 | 内容 | 原路径 |
|---|---|---|
| `packet/` | `P0-current-correction-packet-17-20260914`（17-file current identity，6 files） | `/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/P0-current-correction-packet-17-20260914/` |
| `authority/` | Expert Gate、P0 设计、性能规范 v2 + erratum、telemetry 可用性、prefill reconciliation | `/mnt/data/cache/performance-baseline-v1/{manifest,manifests}/` |
| `review/` | 最新终审：`CHANGES_REQUIRED`（三项缺陷） | `/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/P0-telemetry-final-review-20260914/` |

## 如何校验 packet 哈希（重要）

`packet/hashes.sha256` 内的路径**相对于 repo 根**，因此必须在 repo 根目录执行：

```bash
cd /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
sha256sum -c .memory/phase2-hicache-design/evidence/p0-telemetry-20260914/packet/hashes.sha256
```

这 17 个文件的对象是**工作树字节**，现已随本分支提交（见下节），因此在任何检出该
分支的主机上都能通过校验。若出现空行/路径不存在，说明不在 repo 根目录执行。

## 这批字节的状态：UNREVIEWED

17 个文件的源码快照位于本分支（`wip/p0-telemetry-current-17`）上，提交信息标注
**未验收**。它们：

- **不是**已验收实现，不构成 `P0 telemetry` 通过；
- 最新独立终审为 `CHANGES_REQUIRED`（见 `review/REVIEW.md`、`review/decision.json`）；
- 在独立 correction-and-revalidate 终审通过前，**禁止**据此解锁
  telemetry-enabled 性能重跑、cache/agent 矩阵、soak/restart、scorecard freeze、B4。

固定身份参考（勿混淆）：

- 冻结生产源 = commit `993ef8e5c3a6448aff2e752cf66cc45deadab59a`，
  tree `75d8d1af8dfef5680085e67767c670554d7163af`，tree manifest `5fe5a694…`；
- 保护 ref = `refs/heads/checkpoint/pre-v0.5.19-20260913` + 同名 tag（均在 `993ef8e5`）。

## 未复制的内容（刻意留在卷上）

`/mnt/data/cache/performance-baseline-v1/` 下的原始运行日志、`*.jsonl` 请求/状态转储、
模型权重与构建产物**未**入库（体积与存储纪律原因），仅保留本文档与规范类记录。
若需要某项原始运行证据，须回到本机 `/mnt/data` 或另行搬运。
