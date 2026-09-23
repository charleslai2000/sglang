# 3090-dev — RTX 3090 24G HiCache 实验脚本资产

本目录是 RTX 3090 24G HiCache 三级缓存实验的**可复现脚本资产**，随冻结基线分支
`3090-24g-hicache` 提交。生产环境若出现异常，可据此重放实验、对照基线。

- 目标硬件：RTX 3090 24G（实验机 175.155.64.171:24052）
- 模型：Qwen3.5-9B-w4a16（GPTQ 4-bit，32 层中 24 层 Mamba）
- 引擎：SGLang + HiCache 3-tier cache（GPU L1 / Host L2 / L3 NVMe extent）

## Phase-2 主线实验（正式驱动/分析脚本，含于冻结基线 commit）

| 文件 | 用途 |
|------|------|
| `gate2-run.sh` / `gate2-run2.sh` | Gate-2 L3 restore 复现驱动（launch + 负载） |
| `gate2_analyze.py` | Gate-2 结果分析（exact-restore / full-miss 统计） |
| `gate2_load.py` | Gate-2 负载生成 |
| `metrics/` | 指标对比工具 |
| `test_capacity_model_unit.py` | 容量模型单测 |
| `test_drain_reentry.py` | drain 重入回归测试 |
| `test_fbe_flush_before_evict.py` | flush-before-evict 不变量测试 |
| `test_hicache_restore.py` / `test_hicache_restore_scheduler_feed.py` | L3 restore + scheduler feed 测试 |
| `test_prefetch_budget_split_unit.py` | prefetch 预算拆分单测 |
| `test_ready_horizon_unit.py` / `test_ready_horizon_partition.py` | RH（Ready Horizon）状态机单测 |
| `test_storage_regression.py` | storage 回归测试 |
| `test_writeback_reserve_unit.py` | writeback reserve 单测 |

## P2-IO 阶段实验（复现探针，2026-08-30~09-02）

`p2io_*.py` 系列是 P2-IO（extent-based L3 storage backend）阶段的复现/取证探针，
用于定位 extent 读写、live/shape、mamba 写路径等机制问题。命名规则：
`p2io_e<epoch>_<hypothesis>.py`，例如：

- `p2io_e24_*`：e24 epoch 的 commit/growth/mamba 写路径探针
- `p2io_e25_*`：divergence / live_shape / narrow_cases 探针
- `p2io_e26_closed_loop.py`：闭环复现
- `p2io_e27_chain_compare.py`：链路对比
- `p2io_e28_*`：barekey / boundary / decisive / hybrid / live_path / mamba_split /
  mamba_writepath / tile_check 系列决定性实验
- `p2io_e7p_*`：recompute_quant / three_cases
- `p2io_refhash.py`：引用哈希工具
- `p2io-directed-readback.py` / `p2io-directed-readback-v1.py`：定向回读实验

## 取证数据

- `evidence/`（gate2-k4 / k8 / k16）：Gate-2 各 batch 档的取证输出

## 生产部署（22151 实录）

生产部署问题记录与修复脚本，随本基线分支归档（部署实录见 `prod-deploy-issues.md`）。

| 文件 | 用途 |
|------|------|
| `prod-deploy-issues.md` | 22151 生产部署问题记录（问题/现象/根因/修复/教训，4 项） |
| `prod-deploy/relaunch-e1.sh` | Option B 重启脚本：env 层路径覆盖到 `sglang-patch` 后启动冻结脚本（零装包、冻结脚本零改动） |

生产机与参考机：
- 生产机：`root@175.155.64.171:22151`（RTX 3090 24GB）
- 参考机：`root@175.155.64.171:24052`（RTX 3090 24GB，实验）
- 冻结基线：pool64 / CUDA Graph ON（cuda-graph-max-bs 8）/ c8（max-running 8）/ RH OFF /
  extent L3 backend / **L3=160G** / min_free 10G / 端口 8024

### 5 hard gates 验证要点

| Gate | 验证内容 | 通过判据 |
|------|---------|---------|
| gate1 | 启动 | 无致命错误；CUDA 分配成功（模型 10.36GB / Mamba 5.02GB / KV / host 8.24GB）；ExtentFileBackend 160G/10G 生效；`/health` 200 |
| gate2 | warm prefill | 单条 warm prefill 200 OK（17 prompt / 32 completion tokens） |
| gate3 | GPU L1 hit | 同 session 前缀复用 → `device_hit` 增量 960 |
| gate4 | Host L2 / L3 extent restore | 8 个独立 ~30K-token session 压过 device+host 容量 → 最旧 session 从 L3 恢复，`storage_hit` 增量 30331；`extent_write` 378 次写 14G |
| gate5 | c8 decode 吞吐 | 2048 decode / 3.24s = **631.4 tok/s**，0 错误（基线 p64-c8 = 596.5，+5.9%，短窗口噪声，待长窗口复核） |

### 22151 特定部署要求

- conda env 名：`sglang-patch`（冻结脚本 `/root/direct-launch-gate1.sh` 硬编码 `sglang-dev`，
  22151 无此 env——**必须用 `prod-deploy/relaunch-e1.sh` 的 env 覆盖启动**，否则 HiCache
  原生哈希扩展编译失败：`openssl/sha.h not found`）。
- 模型目录须完整：整个 `Qwen3.5-9B-w4a16/` 目录文件齐全 + 逐文件 md5 一致（仅校验
  `model.safetensors` 不够，缺 `config.json` 会启动即 crash）。
- 部署日志：`/root/prod-deploy/relaunch-e1.log`；解析后 env：`/root/prod-deploy/relaunch-e1.env`

## 运行说明

- 全部脚本在目标机（3090 实验机）的 `sglang-patch` conda 环境下运行：
  `source /root/miniconda3/etc/profile.d/conda.sh && conda activate sglang-patch`
- 引擎启动见 `direct-launch-gate1.sh`（/root，含全部 HiCache 参数），
  生产基线 = pool64 + CUDA Graph ON + conc8 + RH OFF。
- 本目录脚本不自动拉取模型/数据，需目标机已有 `/root/models/Qwen3.5-9B-w4a16/`。

## 版本控制边界

- `.memory/` 为运行时工作数据（任务计划/报告），**不入版本控制**（ARTIFACTS v5.2）。
- 本目录只收**可复现实验脚本 + 配置 + 说明**，一次性调试过程不入库。
