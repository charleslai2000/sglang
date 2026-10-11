# OPS-20260909-RH-ON-RESTART

- **工作标题：** OPS-20260909-RH-ON-RESTART
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/OPS-20260909-RH-ON-RESTART.md`：**
- status: done
- task_id: `D3060-RH-ON-RESTART-20260909`
- orchestration_epoch: `20260909-rh-ab9`
- role: `devops-executor`
- target: `root@i-1.gpushare.com:27460`, RTX 3060

## 实际改了什么
在目标 RTX 3060 主机上只对已识别的 SGLang listener PID 100040 执行有界 TERM，并用原 RH-OFF profile 重启；仅增加 RH-ON 三项参数：enable-ready-horizon、frontier-n=8、speculative-fraction=0.6。受保护 storage 未清理或改动；未修改产品源码/Git 文件，未发 trace workload。

## 生成结果与验收
RH-ON restart **done**：新 PID 102147 在 30000 health 200，解析参数含三项 RH-ON flags，保留 max-running=1 与 wait_complete 等 profile；cache bytes/file count 前后不变，fatal scan 0 matches，GPU 为 RTX 3060 SM86。只准入到后续独立 bounded five-request trace，不代表 RH runtime telemetry/performance 已验收。
RH-ON restart completed and is ready for the identical bounded five-request trace.
The service is healthy as PID `102147`, RH-ON arguments are parsed as required, the
seeded storage baseline is unchanged, and the fatal scan is clean.

### 报告列出的产物/证据
- `phase2-hicache-design/work/OPS-20260909-RH-ON-RESTART.md`：- Before: listener PID `100040`; cache `du -sb` = `23051071488` bytes; regular files
  = `550080`.
- After: listener PID `102147` on `127.0.0.1:30000`; cache `du -sb` =
  `23051071488` bytes; regular files = `550080`.
- Readiness log: `/tmp/sglang3060-rh-on-restart-20260909.log`; readiness marker at
  `2026-09-09 14:38:29`.
- Health verification: `GET /health` returned HTTP `200`.
- `/proc/102147/cmdline` contains the Qwen3.5-4B AWQ model, the complete retained
  RH-OFF profile, and the three RH-ON flags.
- Parsed `server_args` from the launch log:
  ```text
  enable_ready_horizon: True
  ready_horizon_frontier_n: 8
  hicache_prefetch_speculative_fraction: 0.6

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/OPS-20260909-RH-ON-RESTART.md` → `.memory/phase2-hicache-design/work/OPS-20260909-RH-ON-RESTART.md`; SHA256 `f67c8d07630d9f8507795cf491ccab1020954b72b5cb86e05b99a6f1ee10c13c`; source state `tracked`
