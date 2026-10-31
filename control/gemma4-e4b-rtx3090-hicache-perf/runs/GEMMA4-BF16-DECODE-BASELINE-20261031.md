# Gemma4 RTX 3090 BF16 Decode baseline — 2026-10-31

## 目的与边界

固定 checkpoint W4A16、BF16 KV、TP=1、Triton attention、decode CUDA Graph、Radix cache OFF，对 64-token 输入/256-token 输出测 c1–c32；另测真实模型 Decode Graph Forward batch1/2/4/8/16。性能对照不表示 Gemma G1 数值验收通过；G1仍 FAILED / NOT ACCEPTED。无 FP8 KV、HiCache 或实验优化。

服务run身份：manifest记录branch HEAD=`2def6026adc559cd8c427b7d182c93c2d860a402`，checkpoint SHA/配置见下；运行环境Python 3.12、PyTorch 2.13.0+cu129、Transformers 5.12.1、CUDA Toolkit 12.9、driver 580.178.04，SGLang报告加载`Gemma4ForConditionalGeneration`、compressed-tensors W4A16。源码运行身份审计：当前dirty checkout中Gemma模型(`gemma4_causal.py`、`gemma4_mm.py`)、ModelRunner、Decode CUDA Graph、Triton attention、compressed-tensors核心实现均无tracked staged/unstaged diff。存在独立未跟踪`python/sglang/srt/observability/t004_timeline.py`，以及其他控制目录dirty/untracked内容。首轮没有保存逐模块`__file__`/文件hash或完整导入清单，所以HEAD和此次源码diff检查不能追溯证明当时进程实际import的每个文件均等同HEAD；仅可报告核心tracked性能路径未发现dirty差异，不宣称运行源码完全与HEAD一致。首轮运行在summary字段修正前执行，原始证据保留。

## 在线服务矩阵

首次完整服务波次原始工件：`/data/sglang-hicache/gemma4/runs/20261031T062559Z-gemma4-bf16-decode-baseline/`。每档1预热+3测量波，测量轮各请求成功且精确生成256 tokens；不同request使用唯一fixture，Radix cache关闭。吞吐为每波输出token总数/该波并发客户端wall，表中是三波mean ± sample SD。延迟使用最近秩P50/P95，所有request pooled，因每档样本数为3C，分位数精度有限。

| 客户端C | 请求数 | 服务聚合输出 tok/s mean ± SD | Prefill完成−dispatch P50/P95 ms* | TPOT P50/P95 ms | 服务端E2E P50/P95 s | 客户端wall P50/P95 s |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 122.51 ± 0.16 | 121.4 / 121.8 | 6.23 / 6.24 | 2.087 / 2.088 | 2.090 / 2.091 |
| 2 | 6 | 191.71 ± 18.05 | 467.0 / 484.5 | 7.37 / 7.44 | 2.800 / 2.831 | 2.807 / 2.838 |
| 4 | 12 | 354.84 ± 2.65 | 475.2 / 492.9 | 7.60 / 7.60 | 2.878 / 2.892 | 2.889 / 2.901 |
| 8 | 24 | 674.13 ± 7.98 | 497.4 / 515.1 | 7.91 / 8.14 | 2.994 / 3.062 | 3.015 / 3.076 |
| 16 | 48 | 1272.94 ± 10.85 | 499.4 / 509.5 | 8.45 / 8.60 | 3.172 / 3.210 | 3.200 / 3.237 |
| 24 | 72 | 1030.16 ± 10.40 | 495.5 / 3440.1 | 8.38 / 8.65 | 3.205 / 5.954 | 3.241 / 5.994 |
| 32 | 96 | 1620.71 ± 2.06 | 258.5 / 2688.2 | 7.38 / 7.39 | 2.577 / 5.012 | 2.599 / 5.047 |

\* **精确TTFT未测得**：SGLang非流式响应未提供真实first-token timestamp。该列只是`prefill_finished_time - api_server_dispatch_finish_ts`的Prefill完成延迟代理，不能替代TTFT；queue时间不在该值内。TPOT=`1/decode_throughput`。在线实际GPU Forward时间也未采集；这些请求/E2E指标不等于在线Forward时间。

c24吞吐下降是有效测量结果；保留该值，不据此推测调度器根因或修改scheduler。其它并发档结果也按原始测量保留。c32吞吐数值超过c16并非32个同时GPU请求的表现：本轮固定`max_running_requests=16`，请求客户端虽为32，SGLang调度时单次active batch最高16；长排队尾部见dispatch前后端到端P95（C32 server E2E约5.01s，C24约5.95s）。C2变异较大（SD 18 tok/s），该点需保守看待。

`server.log`中解码ScheduleBatch实际分布为batch 1/2/4/8/16分别25/26/26/50/103次，全部记录`cuda graph=True`。这是Scheduler解码batch证据；首轮**未**开逐replay ShapeKey日志，因此不声称其持有每次Graph key。Graph实现可接受图形状上限16，客户端C24/C32不等于GPU batch24/32。

GPU 500ms采样333点，平均利用率46.65%，峰值100%，峰值显存22,933 MiB；服务退出后GPU为0%/1 MiB。该利用率与采样不足以断定具体算子/显存/功耗瓶颈。没有Nsight或硬件counter证据；容量边界和请求排队是高并发尾延迟的直接观察，不作根因外推。

## 独立真实ModelRunner Decode Graph Forward

工件目录：`/data/sglang-hicache/gemma4/runs/20261031T-gemma4-offline-decode-batches/`。加载 pinned W4A16模型，BF16 KV、TP1、Triton，SGLang `ModelRunner`真实graph；64-token前缀prefill后使用生产`ForwardBatch`，warmup后CUDA Event计Forward窗口。b1/2/4/8/16均记录对应`ShapeKey(size=N)`且判定为graph replay，每点25个计时样本。该结果是隔离runner microbenchmark，不含HTTP/API、Scheduler的排队与调度开销，不是在线服务单request latency。

| Decode batch | CUDA Event P50/P95/mean ms | mean下的batch×1000/Forward ms tok/s |
|---:|---:|---:|
| 1 | 7.895 / 8.010 / 7.816 | 127.9 |
| 2 | 7.781 / 8.035 / 7.834 | 255.3 |
| 4 | 8.335 / 8.501 / 8.264 | 484.0 |
| 8 | 8.338 / 8.447 / 8.317 | 961.8 |
| 16 | 8.439 / 8.897 / 8.583 | 1864.0 |

此处tok/s为按事件延迟计算的Forward aggregate，不包含sampling、scheduler或HTTP。batch16 Forward事件约8.58ms，而c16端到端吞吐约1273tok/s，差异反映请求生命周期中还有Prefill/采样/调度/空隙；不应相减当作严格开销分解。需要注意：真实`ModelRunner.alloc_memory_pool()`在本分支并未返回`HybridReqToTokenPool`（运行时类型断言失败），适配用简单`ChunkCache`并显式映射SWA/Mamba池；这是从同一ModelRunner和生产`ForwardBatch`执行的真实Graph Forward，但cache/scheduler所有权与服务并不完全相同。时间可作为隔离Graph Forward实测，不作与Falcon CUDA Event直接性能对照，也不冒充完整服务Forward计量。修正资源释放后的batch1回归值已替代旧版本结果；正式逐batch数据已重新跑齐。

## Falcon T005冻结对照与可比性

冻结Falcon T005的clean B0 `control/falcon-rtx3090-t005/runs/20261020T122034Z-ordinary-c8-probe/B0-SUMMARY.md`：c1 72.04±0.25、c8 431.35±0.12、c16 710.28±0.85、c24 725.01±0.10、c32 726.14±1.07 tok/s；另有后续解锁clean服务结果c8 448.87±13.41、c32 777.28±0.93 tok/s（`control/falcon-rtx3090-t005/runs/T005-FALCON-UNLOCKED-SERVICE-20261025.md`）。Gemma按同为64in/256out、greedy、服务wall吞吐口径与clean B0吞吐作尺度对照：Gemma c1 +70%、c8 +56%、c16 +79%；Gemma c24 +42%、c32 +123%相对B0，但超高并发末两点置信度只基于单服务生命周期内三轮，并受不同模型/运行时/活跃请求上限/吞吐波动影响。两套结果非同模型、非严格匹配source/checkpoint/launcher/capture协议的因果A/B；仅为吞吐尺度参照。Gemma单独Decode Graph Forward与Falcon T002 CUPTI测量不混用。

既有Gemma G32 Prefill（`runs/G32-PREFILL-BASELINE-20261023.md`）和C16容量证据（`runs/G1-C16-CAPACITY-20261023.md`）仅复用，不重做。

## 工件、身份、复跑与开放缺口

- 模型revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`；checkpoint SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`。源码HEAD `2def6026adc559cd8c427b7d182c93c2d860a402`。
- 原服务工件SHA-256：manifest `02991d72ac6074da2ebe2ee21e2f190bd0b85b1606900d5aca8d309bcc35e20b`；fixture `fff2b72fdb66d758fb2aca246aa95f88db05f554c76c83b2c7f9d81d273a8e62`；request raw `552eb4e5ae2fd8e9b96f5100480bac46eeaf037581ce5f9564eaa54c101e6372`；原始summary `447cac41b59fc66e8c9edee00153af41292ca190bd49cf8e3f5a9bd2b2d552d7`；GPU samples `c0dd1baa6dab913219f459a63ea80f3cd942216b8ee45faddbeec17d1c13bb16`；server log `db9e7f8917961ef00f3b2ddcd527f0d35007509648b1e8e7dfa14fe9fdeae395`。
- Decode Graph b1/b2/b4/b8/b16 JSON SHA-256：`0241361a18cab04d0ae39da54e892240055b1d9588a41281db5bcf84eea82802` / `d87fc45d5a25b8d075699b84601cb6adb849e59a18dc23d4183d5ec446b2c8c7` / `a538aea7d8d11398a16b49badba740ae2776370cbb9cc419dfb084caf1e91e1b` / `4c54a1ae6896e441aa6a22ad0f11453f990e1e0c24f9859fde3fa86a48c23791` / `4152af27102feab9fb2b7817d0f9961216bcc8f0d3076af13e7fd0fdb9c1d194`。这组artifact对应最终runner/cache清理代码运行。
- 复跑/分析入口：`runs/run-gemma4-service-benchmark.sh`、`service_benchmark.py`、`summarize_gemma4_baseline.py`、`offline_decode_forward.py`、`derive_baseline_tables.py`。在线TPS矩阵已完成且状态MEASURED；用户明确不因缺少`/model_info`或逐replay ShapeKey而重跑完整矩阵，未启动任何新GPU实验。
- `/model_info`与逐replay ShapeKey未落盘；精确TTFT、在线实际Forward时间均**未测得**。隔离Forward是真实ModelRunner Graph实测，但KV/request pool不完全等价服务，不扩大解释范围。
- 生产数学、数值Oracle、阈值与调度器均未修改。性能文档/脚本可选择性提交；其他dirty/untracked与预暂存共享文件必须保留且不得混入。
