# HiCache 生产部署报告（RTX 3090 新卡 22151）— devops prod-deploy e1

## status
blocked

## artifacts
- 目标机: root@175.155.64.171:22151 (pytorch-8802, RTX 3090 24GB, /data 295G)
- 冻结启动脚本: `/root/direct-launch-gate1.sh`（未改动，模式 644 未加执行位，经 `bash` 调用）
- 启动日志: `/root/prod-deploy/launch-prod-160G.log`
- L3 extent 目录已建: `/data/l3/hicache-prod`
- admin key 已就位: `/opt/sglang/l3-admin-key`（从 24052 复制，md5=ae50d85fe2ebd3cc8c12982a2406b579 与参考机一致）
- 报告文件: `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-devops-prod-deploy-e1.md`

## evidence

### L3 size 决策（依据 ledger 冻结基线，未改其他冻结配置）
- 冻结基线: pool64 / CUDA Graph ON (cuda-graph-max-bs 8) / max-running-requests 8 (c8) / 无 RH 参数 (RH OFF) / extent L3 backend — 均保持。
- 生产 L3 max_size 建议 **160G**，依据 ledger 2026-09-05 冻结条目（第 1207 行）:
  - /data 可用 258G（295G total, 25G used）。
  - 冻结逻辑: "模型在系统盘 + 数据盘专用于 HiCache → 数据盘 258G 空闲 → L3=160G，保留 ~98G"。
  - 依据 24052 实验基线 extent 90GB 之上按容量放大，160G 远大于 90G，符合用户"生产用更大 L3"裁决，同时保留 98G 余量防 GC/回卷打满盘。
  - 单卡 24G HBM、模型 11G、c8：extent 160G 足够覆盖 mamba 大页 + KV 页工作集且无磁盘压力（大块随机写 1.7-1.9GB/s / 27K IOPS 已实测够用）。

### 启动尝试（L3=160G, extent）
- 命令（经 bash 调用，未改脚本）:
  `env L3_BACKEND=extent STORAGE_DIR=/data/l3/hicache-prod MAX_SIZE=160G MIN_FREE=10G SGLANG_PORT=8024 bash /root/direct-launch-gate1.sh`
- 结果: 启动即崩溃。`launch_server.py → server_args.resolve_once → _apply_inkling_prefill_cuda_graph_default → ModelConfig.from_server_args → AutoConfig.from_pretrained` 抛 `ValueError`:
  ```
  ValueError: Unrecognized model in /root/models/Qwen3.5-9B-w4a16.
  Should have a `model_type` key in its config.json.
  ```
- 进程已退出（`pgrep -af launch_server` = none），GPU 空闲（15 MiB），无孤儿进程。
- 端口 8024 未监听。

### 根因：模型目录不完整（22151 vs 24052 对比）
`/root/models/Qwen3.5-9B-w4a16/` 对比：

| 文件 | 22151 | 24052 | 一致? |
|---|---|---|---|
| config.json | **缺失** | 16K (model_type=qwen3_5) | NO — 崩溃直接原因 |
| model.safetensors | 10.95G, md5=5e6de91c | 10.95G, md5=5e6de91c | YES（与派发声明一致）|
| model_mtp.safetensors | 95MB, md5=9276a22c | 486MB, md5=50767e13 | **NO（大小+md5 均不同）** |
| tokenizer.json | 19M | 19M | YES |
| chat_template.jinja | 7.7K | 7.7K | YES |
| .gitattributes / README / configuration.json / generation_config.json / model.safetensors.index.json / processor_config.json / recipe.yaml / tokenizer_config.json | 缺失 | 存在 | NO（不影响启动，但目录不完整）|

- 约束遵守：未修改 `/root/models` 下任何文件；未修改冻结脚本。

## summary
生产部署**未启动成功**。冻结脚本与参考机一致、admin key 已就位、L3=160G 容量决策已确认（ledger 冻结基线），但 22151 的模型目录 `Qwen3.5-9B-w4a16` 不完整——缺少 `config.json`（含 `model_type`），`AutoConfig.from_pretrained` 直接抛错；`model_mtp.safetensors` 亦与参考机不一致（95MB vs 486MB）。属于模型完整性问题，非部署参数问题。按派发约束（不改 /root/models）不代传/修复，如实 blocked。

## followups
1. **补齐模型元数据**：从 24052 传输 `config.json`、`model_mtp.safetensors`（486MB 版本）、`model.safetensors.index.json`、`generation_config.json`、`tokenizer_config.json`、`processor_config.json` 等到 22151，并校验 md5（model_mtp 应为 `50767e13...`）。决策/执行源由 orchestrator 定（devops 不代下载/传输，遵守"不改 /root/models"约束——除非用户明确授权）。
2. 模型补齐后重跑本部署（脚本/配置均已就绪，L3=160G 决策已定）。

## open_issues
- 22151 模型目录不完整（缺 config.json 等元数据；model_mtp 版本不符）——生产部署的阻塞项。
- 是否由 orchestrator 授权 devops 执行 24052→22151 的模型元数据补传（若授权，属 authorized scope，可续做）。
