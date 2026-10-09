# SOAK_EVIDENCE_INDEX.md — Phase-2 2h soak 证据索引

本文件索引 Phase-2 production candidate（tag 3090-hicache-phase2-pc1 /
commit 9c9e7b7c7c）的最终 2h soak 证据：远程/本地路径、verdict.json 摘要、
7 项 Gate 判定摘要、相关报告文件清单。

## 1. 运行摘要（soak-final，2026-09-07）

```text
驱动命令（24052）:
  gate3_ab.sh --tag soak-final --agents 8 --launch /root/direct-launch-gate1-rhon.sh
              --rt 400 --budget 7200 --cmax 900 --max-size 200G --file-size 30G
运行窗口: 12:39:42 启动 → 12:42:13 engine healthy → 12:42:14 driver 启动 → 14:42:44
          driver finished rc=0 → 14:43:07 engine SIGTERMed → 14:43:08 COMPLETE rc=0
elapsed:  7229.9s (120.5 min, ≥2h 完整)
请求:     2349 (round2 566 的 ~4.15x, 匹配 4x 时长)
引擎配置: RH ON, write_back, L3 extent, MAX_SIZE=200G FILE_SIZE=30G,
          max_total_tokens=65536, hicache_ratio=1.5, page_size=1
```

## 2. 证据文件清单

### 远程（24052，root）—— 权威原始证据

| 路径 | 内容 | 大小 |
|---|---|---|
| `/root/evidence-gate3-soak-final/` | 实验命名空间证据目录 | — |
| └ `run-20260907-124214/runs.csv` | 逐请求 runs（743,104 B） | 726 KB |
| └ `run-20260907-124214/verdict.json` | 运行裁决（244 B） | 244 B |
| └ `run-20260907-124214/join.log` | 请求 join 日志（10,254,262 B） | 9.8 MB |
| └ `run-20260907-124214/mid-run-metrics.txt` | 中段指标（7,412,835 B） | 7.1 MB |
| └ `run-20260907-124214/turns/` | turns 分目录 | — |
| └ `gpu-util.csv` | nvidia-smi 采样 1442 行（29,948 B） | 29 KB |
| └ `engine-events-recycle.txt` | 引擎事件（11,123,418 B） | 10.6 MB |
| └ `engine-events-head.txt` | 事件头 2000 行（265,757 B） | 260 KB |
| └ `metrics-final.txt`（89,511 B）/ `boot-metrics.txt`（63,413 B） | 指标快照 | — |
| └ `engine-alloc.txt` / `t38c-probe.log`（26,407,717 B） | 分配/t38c 探针 | 25 MB |
| └ `driver.log`（92 B） | driver 退出 rc=0 | 92 B |
| `/root/engine-gate3-soak-final.log` | 引擎完整日志（65,747,968 B = **65.7 MB**） | 65.7 MB |
| `/root/analyze_*.py` | 分析脚本 30+ 个（analyze_soak_latency / analyze_compare_soak / analyze_hourly_soak / analyze_rm_intermediate / analyze_dq60 / analyze_tooshort_soak / analyze_final_summary 等） | — |

### 本地（本机）

| 路径 | 内容 |
|---|---|
| `/tmp/soak-final-evidence/runs.csv` | 与远程 `run-.../runs.csv` **md5 逐字节相同**（262e1327155ff625a2f2758026928ecf） |
| `/tmp/soak-final-evidence/verdict.json` | 与远程 `run-.../verdict.json` **md5 逐字节相同**（acb1318cdb8fcacf22b1fc0d2084453c） |

## 3. verdict.json 摘要（本地与本归档均附带结构）

```json
{
 "status": "done",
 "agents": 8,
 "write_turns": 4,
 "read_turns": 400,
 "requests_total": 2349,
 "run_dir": "/root/evidence-gate3-soak-final/run-20260907-124214",
 "ts_start": 1788756134.115,
 "ts_end": 1788763364.054,
 "elapsed_s": 7229.9
}
```

## 4. 7 项 Soak Gate 判定摘要（soak-tester-e1，全 PASS）

| Gate | 判定 | 关键硬数据 |
|---|---|---|
| item 1 — 60s HOL cliff = 0 | **PASS** | frontier_wait max 3.3s（477 次，p99 2369ms）；timeout 66 散布 52 min；TTFT exact-60 仅 2 |
| item 2 — no-material 60s 空等 = 0 | **PASS** | no_material=2（boot 冷启动，无 wait）；no_material∩restore_success=0 |
| item 3 — 13ms 级 miss/too_short tight churn | **PASS（机制判定）** | empty-spin=1（噪声级）；revoked:miss tight<1s=228 中 **228/228 全含真实 RESTORING+recompute+prefetch** 中间态（合法同锚 re-probe）；too_short tight<1s=17 全 sub-threshold 孤立单发；revoked:miss/req 2.964→2.786→**2.584** 连续回落 |
| item 4 — restore_success / storage_hit 持续 | **PASS** | restore_success 301 总（**逐小时 154/147 稳定**）；storage_hit turns 52→72；restore tokens 2,045,035 |
| item 5 — 无 assert/crash/OOM/HTTP error | **PASS** | http200=2349/2349；OOM/MemoryError/BackendError/Scheduler exception=0；62 处 Traceback 全为 torchcodec 启动 benign |
| item 6 — forward progress 持续 | **PASS** | 完成间隙 >60s=**0**，max 18.7s（冷启动）；末请求 14:42:44，run 末 14:43:08 |
| item 7 — 无周期 ~60s 峰 | **PASS** | inter-arrival + DQ-wait gap **均无 57-63/117-123 周期**；TTFT p50 19.1 p90 34.5 p99 83.0 |

> 透明提示：item 3 为机制判定（合法中间态）而非"计数器全 0"。原始计数器
> `revoked:miss tight<1s=228 / too_short tight<1s=17 / empty-spin=1` 非 0，
> 全部有真实 RESTORING/recompute/prefetch 中间事件支撑。若生产候选判读要求
> 字面全 0，需用户裁决。详见 `phase2-soak-tester-e1.md` item 3 与 §5 limitations。

## 5. 相关报告文件清单（.memory/phase2-hicache-design/work/）

| 文件 | 内容 |
|---|---|
| `phase2-soak-tester-e1.md` | **2h soak 主报告**（7 Gate 逐项 + 硬数据 + claim 判定） |
| `phase2-round2-tester-e1.md` | point-3 durable_coverage 收紧（9c9e7b7c7c）6 点复测（点3 FAIL 判定 + 升级裁决） |
| `phase2-p4-tester-e1.md` | P4 DEVICE_QUOTA current-suffix gate（920003bf07）6 点复测 |
| `phase2-peranchor-tester-e1.md` | per-anchor（183001f860）P1 deterministic workload 6 点验证 |
| `phase2-hicache-design-tester-gate3-soak-e1.md` | Gate-3 早期 baseline soak（RH OFF，64G/96G，2026-09-04） |
| `phase2-hicache-design-orchestrator-gate3-closeout-e1.md` | Gate-3 收口裁决 |
| `phase2-push-devops-e1.md` | tag/commit push 记录（含 tag 对象 SHA 验证） |

## 6. 复核方式（证据完整性自检）

- 本地副本 md5 对照远程（§2 本地行）：`md5sum /tmp/soak-final-evidence/*` 与
  `ssh root@175.155.64.171 -p 24052 'md5sum /root/evidence-gate3-soak-final/run-20260907-124214/runs.csv verdict.json'`
  应逐字节一致。本次归档已核对（runs 262e1327… / verdict acb1318c…）。
- 部署 md5 复核：`md5sum /root/sglang-b1-continuity/python/sglang/srt/managers/scheduler.py`
  = 495b8851…（== 9c9e7b7c7c），test = 465b6c68…。本次归档全新核对通过。

## 7. 历史对照（同一 gate3_ab 负载）

| 指标 | P4 | round2 | soak（2h） |
|---|---|---|---|
| revoked:miss /req | 2.964 | 2.786 | **2.584** |
| too_short /req | 0.096 | 0.071 | 0.100 |
| restore_success /req | 0.137 | 0.141 | 0.128（逐小时稳定） |
| HTTP 200 | 100% | 100% | **100%** |
| GPU avg | 95.0% | 95.0% | **97.8%** |