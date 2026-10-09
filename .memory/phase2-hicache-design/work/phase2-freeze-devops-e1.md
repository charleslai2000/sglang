# phase2-freeze-devops-e1 — 冻结并归档 Phase-2 环境（tag 3090-hicache-phase2-pc1 一键复现）

- epoch: e1
- agent: devops-executor
- date: 2026-09-07
- task: phase2-freeze-devops-e1

## status: done

Phase-2 production candidate（tag `3090-hicache-phase2-pc1` / commit `9c9e7b7c7c`）
在 24052 实验机的可复现基准已完整归档：启动参数、依赖版本快照、测试脚本基线、
2h soak 证据索引、一键复现 launcher。零产品代码改动、零 push、零 git 写操作。
归档同时落本地 `.memory/` 与 24052 `/root/phase2-pc1-archive/`（均授权），未动
`/root/backup/`。

## artifacts

### 归档目录（本地）
`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/archive/phase2-pc1/`

| 文件 | 内容 | md5 |
|---|---|---|
| `launcher-phase2-pc1.sh` | 一键复现 launcher（bash -n 通过） | `f0ed9d048fbfb2354f1716d199b40d1f` |
| `ENGINE_SYNC.md` | 引擎同步 md5/备份/五 commit 栈/同步方法 | `237c25511860cd5968e0c7cd86ed8b6e` |
| `TESTS.md` | 5 目标套件 md5 + 运行命令 + 323 passed 基线 + drain_reentry 说明 | `c7a04c95fccc760288d36335ce4f6a80` |
| `SOAK_EVIDENCE_INDEX.md` | 2h soak 证据清单/verdict/7 Gate/报告清单 | `7033b6517150d92639ea592b759b91e6` |

### 归档目录（24052）
`/root/phase2-pc1-archive/`（root@175.155.64.171:24052）—— 同上 4 文件，md5 与本地
**逐字节一致**（bash -n 远程也通过）。

### 本 epoch 报告
`/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-freeze-devops-e1.md`（本文件）

## evidence

### 1. 启动参数收集（从既存报告 + 24052 实读脚本）

- 主运行（soak-final，来自 phase2-soak-tester-e1.md §1 + 24052 实读）：
  `gate3_ab.sh --tag soak-final --agents 8 --launch /root/direct-launch-gate1-rhon.sh --rt 400 --budget 7200 --cmax 900 --max-size 200G --file-size 30G`
- 24052 实读确认：
  - `/root/gate3_ab.sh`（4866 B，2026-09-05）：支持 `--max-size`/`--file-size`
    环境（MAX_SIZE_ENV / SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE）；MAX_SIZE 默认 128G、
    FILE_SIZE 默认 192G，本 run 覆盖为 200G/30G；其余 flag 表达式已在 launcher 注释逐条对照。
  - `/root/direct-launch-gate1-rhon.sh`（2456 B）：RH ON wrapper，engine 固定参数
    MAX_SIZE/FILE_SIZE、max_total_tokens=65536、hicache_ratio=1.5、write_back、
    L3 extent、page_size=1、pool64、CUDA Graph ON、conc 8。
- launcher 参数来源表（launcher 内注释 + 本归档）：`--max-size`→SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE
  + extra-config max_size；`--file-size`→SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE；
  `--agents/--rt/--budget/--cmax`→gate2_load.py 对应参数。
- launcher 标注 "此 launcher 复现实验环境，非生产"，零发明参数，全部复制/引用既有蓝本。

### 2. 依赖版本快照（24052 实测，非推断）

- python：3.10.21（sglang-patch env，/root/miniconda3/envs/sglang-patch/bin/python）
- sglang：`0.0.0.dev0`（editable，Location=/root/sglang-b1-continuity/python）
- torch：`2.13.0+cu130`（import torch 实测）
- 关键依赖（pip list）：numpy 2.2.6 / transformers 5.12.1 / flashinfer-python 0.6.17 /
  triton 3.7.1 / outlines 0.1.11 / safetensors 0.8.0 / uvicorn 0.52.4
- CUDA：nvcc build `cuda_12.8.r12.8`（sglang-patch）；GPU NVIDIA RTX 3090 24G,
  driver 580.173.02
- 模型：/root/models/Qwen3.5-9B-w4a16（GPTQ 4-bit）
- L3 admin key：/opt/sglang/l3-admin-key（存在）
- 引擎 repo：/root/sglang-b1-continuity（editable install，非 git，手工同步）

### 3. 引擎部署 md5 核验（24052 实读 == 9c9e7b7c7c）

| 文件 | 24052 部署 md5 | 9c9e7b7c7c blob md5 | 一致 |
|---|---|---|---|
| scheduler.py（/root/sglang-b1-continuity/python/sglang/srt/managers/） | `495b88515cc2e932c57448359443604d` | `495b88515cc2e932c57448359443604d` | ✓ |
| test_hicache_restore_scheduler_feed.py（3090-dev/） | `465b6c68ce813b0522200ac96fea0828` | `465b6c68ce813b0522200ac96fea0828` | ✓ |

- 备份 `.bak-round2-pre` 实读：scheduler `e1b749956459edb599ee956812334b40` / test
  `c94a55db82859913a8ff836f6c9a12dc`（== 920003bf07），保留。
- 关键方法在 commit blob 复核：`_miss_rearm_decision` :3991，`_miss_rearm_durable_coverage`
  :4039（被 :4036 调用，调用点 :4849）—— ENGINE_SYNC.md 已记录。
- 本地 5 目标测试套件 md5 == 24052 部署（本次全新复核）：
  test_hicache_restore 56f95383 / scheduler_feed 465b6c68 / warmtree_hol b1d61fda /
  ready_horizon_unit b6e65276 / storage_regression 500609d2。
- test_p3_warmtree_hol.py 为本地 git 未跟踪工作树文件（push 报告声明不 push），部署以 md5 为准。

### 4. 测试基线（24052 实测）

- 5 目标套件 round2（9c9e7b7c7c）：**323 passed**（基线 314→323，净 +9 为新增用例）。
- test_drain_reentry：5 failed / 25 passed —— BASE 预存在 mock 缺陷
  （unified_radix_cache.py:2241 `_FakeTreeCore` 缺 get_component_device_value，
  AttributeError），与本次改动无关（peranchor/P4/round2 三轮一致）。
- 运行命令（TESTS.md 记录）：
  `PYTHONPATH=python /root/miniconda3/envs/sglang-patch/bin/python -m pytest 3090-dev/<file>.py`，
  前置 `CUDA_HOME=/root/miniconda3` + `PATH=/root/miniconda3/bin:$PATH`（deep_ep 需 nvcc）。
- 24052 sglang-patch env 有 pytest 9.1.1（实测）。

### 5. Soak 证据索引（SOAK_EVIDENCE_INDEX.md 摘要）

- 远程：/root/evidence-gate3-soak-final/（run-20260907-124214/runs.csv 743,104 B、
  verdict.json、join.log、mid-run-metrics.txt、turns/、gpu-util.csv 1442 采样、
  engine-events-recycle.txt 11MB、engine-events-head.txt、metrics-final、
  boot-metrics、t38c-probe.log 26MB）+ /root/engine-gate3-soak-final.log（65.7MB）
  + /root/analyze_*.py 30+ 分析脚本。
- 本地：/tmp/soak-final-evidence/{runs.csv, verdict.json} —— md5 与远程
  **逐字节一致**（runs 262e1327… / verdict acb1318c…）。
- verdict.json：status=done, agents=8, write_turns=4, read_turns=400,
  requests_total=2349, elapsed_s=7229.9, run_dir=…/run-20260907-124214。
- 7 项 Soak Gate 全 PASS（soak-tester-e1）：item1 frontier_wait max 3.3s 无 60s cliff；
  item2 no_material=2(boot) 无空等；item3 empty-spin=1，228/228 revoked:miss tight 全含真实
  中间态（机制判定 PASS，原始计数器 228/17/1 透明列出待用户复核）；item4 restore_success
  逐小时 154/147 稳定；item5 2349/2349 HTTP 200 0 OOM；item6 完成间隙>60s=0；item7
  无 57-63/117-123 周期，p99=83s。

### 6. 完整性核验结果

- launcher `bash -n`：本地与远程均通过（SYNTAX_OK）。
- 归档 4 文件本地与 24052 远程 md5 逐字节一致（见 artifacts 表）。
- 归档目录 Read 确认（ls -laR 列出 4 文件）。
- 引擎部署 md5 与 9c9e7b7c7c blob 一致（§3）。

## summary

Phase-2 production candidate 环境已完整冻结并归档到本地 `.memory/phase2-hicache-design/archive/phase2-pc1/`
与 24052 `/root/phase2-pc1-archive/`，含一键复现 launcher、引擎同步说明、测试基线、
soak 证据索引与依赖版本快照。全部参数/md5/基线均从 24052 实测收集或从既有报告如实
引用，零臆造。任务零产品代码修改、零 push、零 git 写操作，未动 /root/backup/。

## followups

- （非阻塞）若需在任何新环境复现，先在目标机就位依赖（sglang-patch env、模型、
  admin key、引擎 repo），再运行 launcher；launcher 内 md5 预检会拒绝非 candidate 引擎。
- （非阻塞）test_p3_warmtree_hol.py 为未跟踪文件；若希望纳入版本控制需单独处置
  （超出本任务 scope，未执行）。

## open_issues

- 无阻塞项。item 3 原始计数器非 0 的严格判读已透明记录于 SOAK_EVIDENCE_INDEX.md 与
  phase2-soak-tester-e1.md（属既有裁决，非本归档引入）。

## material_exit_status

- 全部本地命令 exit 0；远程 ssh/scp 全部成功；bash -n 通过；md5 全一致。
