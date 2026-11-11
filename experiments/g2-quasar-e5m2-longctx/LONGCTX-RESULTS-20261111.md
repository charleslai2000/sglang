# Gemma4 QUASAR BF16 + E5M2 KV：单卡并发长上下文实测

## 结论
- RTX 3090 上目标 **32 路独立请求 × 32K context + 持续 Decode 未达成**。这一构型开始排队 Prefill，最长控制运行 1,322 秒后 32 个客户端请求最终都收到了 32 个流块，但服务端只记录 **1 个 Decode batch、active=16**；没有 c32 decode 证据。32×32K 的容量池初始化成功不等于实际承载。
- 本轮实测成功上限点：**32×8K、每请求 Decode 512 tokens**；另有 **16×16K、每请求 Decode 256 tokens**。成功点不是最大边界/OOM，也不代表 SLO 或产品接受。
- 32K 的限制不是纯 Full KV token 槽数不足：日志显示 32K run 的 Full pool 1,068,151 slots、SWA 24,609 slots，而 32K×32 理论输入约 1,048,576 Full tokens；实际调度在 prefill 阶段受 **SWA 池近满与逐请求 chunked-prefill headroom** 影响，排队/重试使等待极长。16×32K 同样在 724 秒只记录一个 active=16 decode batch（0.74 tok/s），因此仅请求完成不构成“持续”吞吐证据。
- 可复现实测的吞吐：32×8K final run 的服务端 decode batch median/max **283.41/286.14 aggregate output tok/s**，12/13 decode rows 显示 running=32，32/32 客户端各收齐 512 输出块；16×16K 的服务端 decode median/max **148.305/150.54 tok/s**，6/6 batch running=16，16/16 各收齐 256 输出块。数值为单次描述性 run。

## 固定路径与配置
- QUASAR GGUF SHA-256 `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`；BF16 compute、E5M2 KV、TP1、Triton attention、关闭 radix cache 和 CUDA graphs；复用 HEAD overlay SHA-256 `69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e` 与 SM86 AOT binary SHA-256 `22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2`。
- 客户端以同步 barrier 提交独立随机 token ID 请求，禁用 radix cache；成功 run fixture 32/32 或 16/16 prompt hash 全部不同。服务端 Prefill 均报告 `#cached-token: 0`。
- 独占 GPU 锁 `/tmp/f1-r16b-gpu-exclusive.lock`；所有正式 run 由 runner 获取。最终 1 MiB / 0%、测试端口无监听、锁可用。

## 实测成功点

| 并发 × prompt | 输出/请求 | Full/SWA slots | GPU 峰值 | 完成/服务端证据 | 时延 | Prefill | Decode |
|---|---:|---:|---:|---|---|---|---|
| 32×8,192 (`20261111T-g2-quasar-longctx-c32-8k-512-final`) | 512 | 1,068,151 / 24,609 | **22,384 MiB** (`nvidia-smi` 250 ms samples) | 32/32；32 个唯一 prompt；13 decode batch，peak running=32，12 行 running=32 | 全量 client wall 410.22s；TTFT min/median/max 11.84/131.11/244.11s；最长请求 410.14s | 218 chunk batch、376,854 logged new tokens、加权 batch input throughput 1,126.94 tok/s；无缓存 token | 服务端 batch throughput median/max 283.41/286.14 aggregate tok/s |
| 16×16,384 (`20261111T-g2-quasar-longctx-c16-16k-final`) | 256 | 1,093,791 / 14,353 | **22,104 MiB** (250 ms samples) | 16/16；16 个唯一 prompt；6 decode batch，6 行 running=16 | 全量 wall 384.76s；TTFT min/median/max 42.15/163.69/281.06s；最长请求 384.71s | 274 batch、344,070 logged new tokens、加权 batch input throughput 1,082.18 tok/s；无缓存 token | 服务端 batch throughput median/max 148.305/150.54 aggregate tok/s |

“加权 batch input throughput”按逐批日志 `input throughput × new_tokens` 汇总，不等同端到端输入 tokens / 客户端墙钟；decode throughput 是 SGLang batch 日志值，不是设备 profiler kernel 时间。GPU memory samples 监视期间采样；peak 不是分项显存归因。

## 32K 失败与容量线索

### 32×32K
`20261111T-g2-quasar-longctx-c32-32k-shape-contract/`，context length 33,312、max-running=32、chunk=2,048。Full/SWA pools **1,068,151 / 24,609** slots，服务启动时 available GPU memory 2.54 GB。客户端全部 32 个请求各收到 32 output chunks，但 client wall 1,322.28s；服务端有 740 prefill batches，最多 running=31。SWA usage 多次 **0.99–1.00**，发生 pool full/retraction；最后仅一个 Decode batch，running=16、reported gen throughput=0.71 tok/s。其余 16 路未同时进入 decode，故目标不通过。该 run 未达到 GPU OOM；不能声称真实最大上下文/容量边界。

### 16×32K
`20261111T-g2-quasar-longctx-c16-32k-final/`，pool slots 1,093,791 / 14,353，available GPU 2.46 GB；16/16 每个请求各收到 64 chunks，但耗时 724.13s，服务端仅一条 decode batch、running=16、0.74 tok/s。它只证明请求最终完成，不证明稳定的持续 decode；不是可用持续服务点。

### 无效的 pool 强制合并尝试
曾临时启动 `--disable-hybrid-swa-memory`。32K 的 2048-token chunk 在 `_set_kv_buffer_impl` 报 batch-size-specialized JIT mismatch；缩小 chunk 后又由 naive fallback 报 K shape `[N,2,256]` 与 cache `[N,2,512]` 不匹配。该尝试违反 Gemma4 Full/SWA 不同 head width 的 cache contract，未产生有效请求结果；参数已从正式 runner 撤销，不纳入可行路径或容量结论。

## 未采用的失败/无效运行
- 原始 c32×32K 第一次约 10 分钟超时，客户端未完成、没有 decode；观察到最多 running=16 / queue=16，SWA 接近满。仅作失败/调试证据。
- 禁用 SWA 与 chunk-size 收敛实验的服务由独立 shape/cache/JIT 错误崩溃；不可用。
- 逐层 QKV tracing 临时运行仅加载权重，没有正式请求；中止/超时后确认 GPU 与端口清理，不作为测量。
- 前序 c32×8K ×128 run 只观察到 3 个 decode batch，输出短，不足以验证“持续”；本结果以新 c32×8K ×512 run 为准。

## 遥测与解释限制
- 无逐 kernel dispatch trace、无 NCU；prefill batch logs 是 batch 输入吞吐采样，非 isolated per-request prefill latency。client `first_chunk_s` 是单请求从提交到首个 SSE chunk；响应块数由 harness 记录，固定 `max_new_tokens`，不等价 profiler 计出的 token wall-time。
- 测试均使用同步发起的独立随机 token ID，非真实自然语言长对话分布；没有质量评估，也没有目标 context 输出内容语义验收。
- c32×32K run 最终 16 active decode 暴露调度/池边界，但没有用更低请求数或分块调度做二分寻找精确最大值；成功 32×8K 及16×16K 只是最高已演示负载点，不声明全局最大值。
- GPU 峰值是 250 ms 轮询观测；其他内存/短暂 spike 可能采样间发生。

## 产物
Runner、client driver 和 log analyzer 位于本目录；控制状态见 `control/g2-quasar-e5m2-longctx/`。正式 run 目录分别为上表路径；每个 run 的 `artifact-sha256.txt` 冻结模型/fixture/config/service-log/server decode/prefill analysis 与 GPU samples。
