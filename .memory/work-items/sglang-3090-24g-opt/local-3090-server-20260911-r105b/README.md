# LOCAL-3090-SERVER-20260911-R105b

- **工作标题：** LOCAL-3090-SERVER-20260911-R105b
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/LOCAL-3090-SERVER-20260911-R105b.md`：**
- **Task ID:** LOCAL-3090-SERVER-20260911-R105b
- **Invocation:** ses-local-3090-server-r105b-20260911 (fresh invocation of logical task R105)
- **Role:** devops-executor
- **Epoch:** 2026-09-11
- **Machine:** pc01 (this host), boot 2026-09-11 20:49, report written ~21:16
- **Status: blocked**

## 实际改了什么
仅本机 RTX 3090 上进行有界启动/排障尝试；没有仓库源码修改。为尝试适配 R60 profile，显式禁用 prefill/decode CUDA graphs，并把 `max-mamba-cache-size` 降为 53；按 GPU lock 启动测试后停止卡死服务，未留下运行实例。

## 生成结果与验收
最终 **BLOCKED**：R60 graph 配置重复卡在首次 CUDA graph capture；全禁 graph 后发现 host memory 申请 15.20GB 超出可用 7.85GB；将 Mamba cap 改为 53 可完成 startup，但 warmup/forward 仍死锁，`/health` 持续 503、模型信息 200、generation 75s timeout、GPU 0% utilization。所有进程最后停止。该尝试不证明 profile serviceable，也非用户冻结原 profile 下成功运行；只记录历史原因链与参数偏离，未改产品代码。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/LOCAL-3090-SERVER-20260911-R105b.md` → `.memory/rh-p0c-runtime-provenance/LOCAL-3090-SERVER-20260911-R105b.md`; SHA256 `843fd18c1dc641cad47c7284415ececa6e4d48ee04269ce728db293df64cb97d`; source state `tracked`
