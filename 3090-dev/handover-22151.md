# Handover — 22151 HiCache Production Environment

> 交接日期：2026-09-06
> 交接机器：`root@175.155.64.171:22151`（免密 ed25519；或 sshpass -p 'K0@dx'）
> 用途：HiCache 3-tier cache 生产部署 + 新模型测试环境
> 关联基线：`3090-dev/prod-deploy-issues.md`（部署问题记录）、`3090-dev/README.md`（实验脚本资产）、Fix A/B 在 `3090-24g-opt` 分支

## 1. 环境概况

| 项 | 值 |
|---|---|
| 机型 | RTX 3090 24576 MiB（CUDA 13.0） |
| conda env | `sglang-patch`（python 3.10.21，torch 2.13.0+cu130，triton 3.7.1，flashinfer-python 0.6.17） |
| sglang 源码 | `/root/sglang-b1-continuity/python/sglang`（editable install） |
| 模型 | `/root/models/Qwen3.5-9B-w4a16/`（GPTQ w4a16, model_type=qwen3_5, 含 model_mtp 486MB） |
| L3 存储 | `/data/l3/hicache-prod`，extent 160G / min_free 10G |
| 服务端口 | 8024（0.0.0.0 监听） |
| /data 盘 | 295G，extent 数据文件已在写（68.7G apparent） |

## 2. 服务状态（交接时刻实测）

- **launch PID 16604 运行中**，/health 200，8024 LISTEN 0.0.0.0
- GPU 占用 ~20.2GB / 24.5GB，利用率 19%
- 启动方式：`/root/prod-deploy/relaunch-e1.sh`（Option B 路径覆盖，见 §4）
- 启动日志：`/root/prod-deploy/relaunch-e1.log`

## 3. 冻结基线配置（生产）—— 勿改

```
pool64   : --mem-fraction-static 0.92
Graph ON : --cuda-graph-max-bs 8
c8       : --max-running-requests 8
RH OFF   : 无 --enable-ready-horizon
extent   : --hicache-storage-backend extent, max_size=160G, min_free=10G
写策略 write_back / prefetch wait_complete / hicache-ratio 1.5 / promo-margin 2048
max-total-tokens 65536 / kv-cache-dtype bf16 / mamba-ssm-dtype float32
attention flashinfer / linear-attn triton / tp1
```

## 4. ⚠️ 关键启动要求（22151 特有，务必遵守）

`/root/direct-launch-gate1.sh` **写死了 `sglang-dev` 路径**，但 22151 **只有 `sglang-patch` env**。直接跑必崩：
- `hash_binding.cpp: openssl/sha.h not found` → hicache_hash_cpp 编译失败 → ENGINE_EXIT_STATUS=137
- **必须用 `/root/prod-deploy/relaunch-e1.sh` 启动**（env 层覆盖 CUDA_HOME/CPLUS_INCLUDE_PATH/LIBRARY_PATH/LD_LIBRARY_PATH/PATH 指向 sglang-patch），冻结脚本零改动
- flashinfer 首次 JIT 编译需 ninja：relaunch 脚本已把 `sglang-patch/bin` 前置进 PATH

## 5. 5 hard gates 验证（已跑通，方法见下）

| gate | 结果 | 证据 |
|---|---|---|
| gate1 启动 | ✅ | 无致命错误，CUDA 分配成功，/health 200 |
| gate2 warm prefill | ✅ | 200 OK, 17 prompt/32 completion |
| gate3 GPU L1 hit | ✅ | device_hit Δ=960 |
| gate4 storage/L3 hit | ✅ | **8x30K-token 独立 session 压满 device+host 后 storage_hit Δ=30331**（权威验证，`gate4_run.log` 23:52） |
| gate5 c8 吞吐 | ✅ | 631.4 tok/s（2048 decode/3.24s，0 错误；短窗口，建议长窗复核） |

⚠️ **gate4 验证方法陷阱**：快速单请求探测会得到 storage_hit=0 假阴性（`gate_run.log` 23:47 FAIL）——必须用 8 个独立 session 各 ~30K token 压过 device(65536)+host(98305) 再 restore 最旧 session，storage_hit 才有值。验证脚本已在 `/root/prod-deploy/prod_gate_runner.py` / `prod_gate4.py`。

## 6. 测试工具就位

- gate 驱动：`/root/prod-deploy/prod_gate_runner.py`（gate2/3/5）、`/root/prod-deploy/prod_gate4.py`（gate4 压测）
- 磁盘基准：`/root/prod-deploy/fio_run.sh`、`fio_l3.sh`
- admin key：`/opt/sglang/l3-admin-key`
- 本机→22151:8024 网络放行**未确认**（交接前 gate 测试均在 22151 本机 curl 执行）；外部客户端访问需先确认可达性

## 7. 已知问题 / 注意

- 日志有 ~60 处 torchcodec/libavutil 共享库 Traceback，均无害启动探测，非服务错误
- gate5 631.4 tok/s 为 3.24s 短窗，建议长稳态窗复核（±5% 阈值内）
- 24052 是实验机（勿部署生产）；22151 是生产机（勿跑破坏性实验）
- Fix A/B（RH 状态机修复）在 `sglang-3090-24g-opt` 分支，未合入本环境——本环境是 RH OFF 冻结基线
