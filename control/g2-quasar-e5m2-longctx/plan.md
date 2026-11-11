# 结论与交付

## 结论
- 目标 c32×32K + sustained decode **未达到**：1,322 秒时服务端只有一条 decode batch 显示 running=16；SWA usage 多次 0.99–1.00，并出现 pool-full retraction。初始化槽数不代表实际并发承载。
- 成功演示点：c32×8K、512 output/request（32/32 active decode rows；server median 283.41 tok/s）；c16×16K、256 output/request（16/16 rows；148.305 tok/s）。这不是 OOM 或最大容量边界。
- Full/SWA 槽数：c32 pool 1,068,151/24,609；c16 pool 1,093,791/14,353。GPU 250ms samples 峰值分别 22,384 MiB、22,104 MiB。
- c16×32K 请求最终各收到 64 outputs，但 724 秒只看到一个 active=16 decode batch；不计为持续服务成功。

## 交付
- 报告：`experiments/g2-quasar-e5m2-longctx/LONGCTX-RESULTS-20261111.md`。
- Harness：本目录 `run_longctx.sh`、`longctx_capacity.py`、`analyze_longctx.py`。
- 成功运行：`/data/sglang-hicache/g2-quasar-runs/20261111T-g2-quasar-longctx-c32-8k-512-final/` 与 `.../20261111T-g2-quasar-longctx-c16-16k-final/`，包含独立 fixture、stream、server batch analysis、250ms GPU samples 和 SHA manifest。
- 复用已验证模型、HEAD overlay、AOT SHA；未重跑质量集。强制合并 Full/SWA 和临时 JIT schema 尝试均未纳入 runner；共享 dirty/untracked 保留。

## 状态
T001 的真实测量、限制和替代负载均完成记录；GPU 为 1 MiB/0%、测试端口无监听、exclusive lock 可用。Goal 自有文件已精确核验并选择性提交/推送，远端 SHA 与本地一致。c32×32K sustained decode 未达成；不能据此声称最大容量或产品通过。
