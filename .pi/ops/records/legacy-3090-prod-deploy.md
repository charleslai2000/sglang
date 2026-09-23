# HiCache 生产部署问题记录（22151 部署实录）

本文件记录 HiCache 三级缓存（GPU L1 / Host L2 / L3 NVMe extent）在 **RTX 3090 生产机 22151**
首次部署时遇到的全部真实问题（现象 / 根因 / 修复 / 教训），与部署脚本
`prod-deploy/relaunch-e1.sh` 配套归档，随冻结基线分支 `3090-24g-hicache` 提交。

- 目标机：`root@175.155.64.171:22151`（RTX 3090 24GB，生产）
- 参考机：`root@175.155.64.171:24052`（RTX 3090 24GB，实验）
- 模型：`Qwen3.5-9B-w4a16`（GPTQ 4-bit，`model_type=qwen3_5`，`Qwen3_5ForConditionalGeneration`）
- 冻结基线配置：pool64（mem-fraction 0.92）/ CUDA Graph ON（cuda-graph-max-bs 8）/ c8（max-running 8）/
  RH OFF / extent L3 backend，**L3=160G**（`/data` 258G 可用，保留 ~98G）/ min_free 10G / 端口 8024

> 部署最终结果：5 hard gates 全过，三级缓存真实工作（GPU L1 hit、Host L2、L3 extent restore 均验证）。
> 完整部署报告见 `.memory/phase2-hicache-design/work/phase2-hicache-design-devops-prod-deploy-22151-e1.md`。

---

## 问题 1：模型目录不完整导致启动 crash

### 现象

启动即崩溃，`launch_server.py` 链路在 `ModelConfig.from_server_args → AutoConfig.from_pretrained`
处抛 `ValueError`：

```
ValueError: Unrecognized model in /root/models/Qwen3.5-9B-w4a16.
Should have a `model_type` key in its config.json.
```

### 根因

22151 的模型目录 `/root/models/Qwen3.5-9B-w4a16/` 不完整，与参考机 24052 对比缺失/不符：

| 文件 | 22151 | 24052 | 一致? |
|---|---|---|---|
| config.json | **缺失**（含 `model_type`） | 16K（`model_type=qwen3_5`） | NO — crash 直接原因 |
| model.safetensors | 10.95G, md5=5e6de91c | 10.95G, md5=5e6de91c | YES |
| model_mtp.safetensors | 95MB, md5=9276a22c | 486MB, md5=50767e13 | **NO（大小+md5 均不同）** |
| tokenizer.json | 19M | 19M | YES |
| chat_template.jinja | 7.7K | 7.7K | YES |
| 其余元数据（config/generation_config/tokenizer_config/processor_config/index.json 等 9 个） | 缺失 | 存在 | NO |

迁移时仅校验了 `model.safetensors` 的 md5 一致，未校验整个模型目录文件齐全与逐文件 md5。

### 修复

从 24052 经**直连免密 tar 流**一次性补齐 10 个文件到 22151（9 个缺失元数据 + 覆盖替换
不完整的 `model_mtp.safetensors`），未触碰 `model.safetensors`。传输后逐文件 md5 与源侧比对全部一致：

- 补齐：`config.json` / `model.safetensors.index.json` / `generation_config.json` /
  `tokenizer_config.json` / `processor_config.json` / `README.md` / `.gitattributes` /
  `recipe.yaml` / `configuration.json`
- 替换：`model_mtp.safetensors` 95MB→486MB（md5=`50767e137d5a8a4885c065fcd0f29e81`）
- `model.safetensors` 未动（md5=`5e6de91cf0e7f52575f37033683c6ef2`）
- 补齐后目录清单与 24052 完全一致（13 个文件），`config.json` 含 `"model_type": "qwen3_5"`

### 教训

**只校验 model.safetensors 的 md5 不够，必须校验整个模型目录文件齐全 + 每个文件 md5 一致。**
模型迁移/补齐后，应做目录清单比对 + 逐文件 md5 校验，而非抽查单个大权重文件。

---

## 问题 2：flashinfer JIT 编译找不到 ninja

### 现象

prefill CUDA graph capture 阶段，flashinfer JIT build 报 ninja 找不到。

### 根因

启动时 `PATH` 是系统默认路径（`/usr/local/sbin` 等），不含 conda env 的 `bin`；
而 ninja 位于 `/root/miniconda3/envs/sglang-patch/bin/ninja`（env 内也有 ninja 模块 1.13.2）。

### 修复

启动前将 conda env 的 `bin` 前置到 `PATH`：

```bash
export PATH=/root/miniconda3/envs/sglang-patch/bin:$PATH
```

（`relaunch-e1.sh` 中已包含此项。）

### 教训

conda env 内依赖的可执行文件（如 ninja、编译器）不会被系统默认 `PATH` 覆盖到；
启动前必须把目标 conda env 的 `bin` 前置进 `PATH`，否则 JIT 类工具链会失败。

---

## 问题 3：HiCache 原生哈希扩展编译失败（openssl/sha.h not found）← 最关键

### 现象

HiCache 原生哈希 C++ 扩展编译失败：

```
hash_binding.cpp:5:10: fatal error: openssl/sha.h: No such file or directory
RuntimeError: Failed to load HiCache native hash extension
```

随后进程崩溃（`ENGINE_EXIT_STATUS=137`，SIGKILL）。

### 根因

启动脚本 `/root/direct-launch-gate1.sh`（第 7-10 行）**写死了 `sglang-dev` 路径**——
`CUDA_HOME` / `CPLUS_INCLUDE_PATH` / `LIBRARY_PATH` / `LD_LIBRARY_PATH` 全部指向
`/root/miniconda3/envs/sglang-dev/...`。但 22151 上只有 `sglang-patch` env，**没有 `sglang-dev`**。

于是 `CPLUS_INCLUDE_PATH` 指向不存在的目录 → `openssl/sha.h` 找不到 →
`hicache_hash_cpp` 编译失败 → 崩溃。24052 能跑，是因为它存在 `sglang-dev` env。

### 修复（Option B，零装包、冻结脚本零改动）

用 **env 层路径覆盖**指向 `sglang-patch`，冻结脚本一字不改。覆盖：
`CUDA_HOME` / `CPLUS_INCLUDE_PATH` / `LIBRARY_PATH` / `LD_LIBRARY_PATH` / `PATH`
全部指向 `sglang-patch`（脚本第 10 行虽再次前插 `sglang-dev/lib`，但会把我们预置的
`LD_LIBRARY_PATH` 追加在其后，最终解析为 `sglang-patch/lib:cu13/lib`，编译正确）。

完整脚本见 `prod-deploy/relaunch-e1.sh`。

### 教训

**部署脚本里硬编码的 conda env 路径名（`sglang-dev` vs `sglang-patch`）必须与实际目标机
env 名一致。** 跨机部署时 env 名差异是隐藏炸弹——脚本看起来"没问题"，但因路径名不匹配
导致编译/链接失败且报错极具误导性（`openssl/sha.h not found`）。路径差异要记入 runbook；
冻结脚本不能假设目标机 env 名与开发机相同。

---

## 问题 4（环境警示，非本部署）：24052 `/data` 100% 满

### 现象

24052 的 `/data` 数据盘使用率达到 100%（满）。

### 根因

extent backend 无 hole-punch，evict（回收）不释放物理块，导致 extent 文件只增不减，
最终打满磁盘。此为环境水位警示，非本次 22151 部署本身的问题。

### 教训

后续 extent 实验需保证磁盘安全水位（保留足够余量，防止 GC / 回卷把盘打满）。
本部署在 22151 上 L3=160G 且 `/data` 可用 258G、保留 ~98G，即为防打满的容量决策。

---

## 附录：部署脚本与启动方式

- 冻结启动脚本：`/root/direct-launch-gate1.sh`（未改动，经 `bash` 调用）
- 归档修复脚本：`prod-deploy/relaunch-e1.sh`（本目录，env 层路径覆盖后启动冻结脚本）
- 部署日志：`/root/prod-deploy/relaunch-e1.log`
- 解析后 env 记录：`/root/prod-deploy/relaunch-e1.env`

> 22151 特定需求：启动前必须确认 conda env 名为 `sglang-patch`（脚本默认硬编码 `sglang-dev`），
> 并用 `relaunch-e1.sh` 的 env 覆盖启动；若目标机 env 名不同，需相应调整覆盖路径。
