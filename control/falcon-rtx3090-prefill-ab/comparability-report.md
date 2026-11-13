# Falcon Prefill 计时口径对照（历史 T002 / 本次 Unlocked）

## 结论
两组 Falcon Prefill 数值不能构成 GPU Unlock 的 Stock/Unlocked A/B，也不可据此计算 Prefill 加速比。历史 T002 的 Prefill 采用启动中的 SGLang 服务 `/generate` 请求并取服务 TTFT/首 token 路径和 client wall；本次 `one_batch` 数值采用独立 `ModelRunner.extend()` 同步前向 wall interval，不含服务队列/tokenizer/HTTP，计时对象不同。更重要的是，T002 中列出的 1K/4K Event/CUPTI 实测来自 **2026-10-20 B0**，即已部署 GPU Unlock 之后；并非此前历史 Stock 状态。真正 Stock GEMM仅验证矩阵乘性能，不包含 Falcon。

## 原始数据核对

| 数据点 | Prefill 输入 | 计时口径 | 实测结果 | 状态/限制 |
|---|---:|---|---:|---|
| T002/本地 T005 B0，2026-10-20 | 1K | 独立 Prefill Event/CUPTI（T002摘要） | 285.822 / 285.312 ms | GPU Unlock已部署；当前checkout dirty B0；非Stock |
| T002/本地 T005 B0，2026-10-20 | 4K | 独立 Prefill Event/CUPTI（T002摘要） | 1,113.026 / 1,112.497 ms | 同上；该记录没有本轮runner的完整逐次配置可逐项证明同一 |
| 本次独立 runner，2026-10-25 | 1K, BS1 | `one_batch.latency_test_run_once()`：host `perf_counter` 包围 `ModelRunner.extend()`，前后设备同步 | 5 次：median 205.442 ms，mean 205.461 ms，SD 0.521 ms；4,984 tok/s | 真正独立forward；prefill专用CUDA Graph disabled |
| 本次独立 runner，2026-10-25 | 4K, BS1 | 同上 | 5 次：median 769.820 ms，mean 769.786 ms，SD 0.770 ms；5,321 tok/s | 同上 |
| 本次独立 runner，2026-10-25 | 8K, BS1 | 同上 | 5 次：median 1,588.132 ms，mean 1,587.991 ms，SD 1.208 ms；5,158 tok/s | 固定完整输入通过runner；服务context=8192不能接收8K+decode请求 |
| 本次独立 runner，2026-10-25 | 1K, BS4 | 同上 | 5 次：median 766.714 ms；5,342 aggregate tok/s | 每次实际输入4,096 tokens |
| 本次真实服务，2026-10-25 | 1K / 4K, BS1 | response scheduler `prefill_finished_time-forward_entry_time`，另记录queue；客户端发固定 input_ids | 1K median forward 205.480 ms；4K median 817.781 ms | 每组5请求，prompt token精确，cached_tokens=0；TTFT字段未返回(null) |
| Stock启动后短GEMM | n=8192 | GPU Events，5 warmup、15 iters/repeat、3 repeats | FP16 111.433、BF16 117.129、TF32 62.400 TFLOPS | 尽管cmdline无targets/无解锁事件，性能显示仍是Unlocked；未运行Stock Prefill |

独立 runner 原始逐次数据：`/data/sglang-hicache/falcon-prefill-ab/runs/unlocked-20261025/bench/{b1-1024,b1-4096,b1-8192,b4-1024}/bench.jsonl`。真实服务响应及配置：同 run 下 `service/prefill-{1024,4096}.raw.json`、`service/server-info.json`、`service/server.log`。哈希清单在 `/data/sglang-hicache/falcon-prefill-ab/runs/SHA256SUMS`。

## 配置/负载可比性

- 模型ID和revision相同：Falcon-H1-7B-Instruct-GPTQ-Int4 / `52036ae497a2c0c253e17f98cc8652f2f7082ae3`；AOT SM86 kernel及venv相同。模型分片哈希保存在本次 `model-sha256.txt`；T002身份详见 `control/falcon-rtx3090-t005/runs/20261020T122034Z-ordinary-c8-probe/B0-SUMMARY.md` 与其 `model-identity.json`。
- 独立runner与服务都使用TP1、GPTQ Marlin、FlashInfer attention、Triton Mamba、Mamba cache 83、static memory fraction .90、chunked prefill 2048、prefill CUDA Graph disabled。T002历史B0是服务配置，normal overlap scheduling，且请求形状为64 input/256 output并发吞吐；其独立prefill矩阵虽然是Prefill测试，但其逐次结果摘要未保存启动命令，无法证明与本次所有flags完全一致。
- 本次 runner实际使用fixture token IDs先无损decode为文本，再由one_batch tokenizer重编码；提示日志显示TokenizersBackend warning。真实HTTP服务直接传 `input_ids`，确认prompt_tokens准确和缓存零命中。
- 本次 runner配置 `context_length=16384` 并设置允许覆盖模型推导出的8192上下文，以尝试16K；启动日志明确警告可能有错误/CUDA风险。16K不是有效测量：KV pool后只剩约320MiB，Marlin measured forward申请768MiB失败。BS4 4K同样未跑成功。服务仍设context 8192，因此8K input无法再容纳生成token而被拒。
- T002 Event/CUPTI不是同一个时钟/仪器：`Event`是CUDA event elapsed time；CUPTI是工具关联值；本次one_batch则是host monotonic wall around synchronized full extend。T002摘要给出的两种值数值接近，但不可将其等同于本次wall latency，也不可用比值表达解锁收益。
- 独立runner不是端到端 TTFT。真实服务响应本次 `ttft` key为null；不要从prefill forward+queue自行冒称TTFT。T002服务B0 c1的server TTFT median约183.9ms，是64-token+256-output不同请求下的值，不是1K/4K Prefill TTFT。

## T002身份与状态判定

T002 GEMM正式验收是匹配的Stock/Unlocked GEMM A/B：N8192、seed20261025、strict FP32 reference、warmup5、15 GPU-event iteration/repeat、5 repeats。它得出Stock→Unlocked FP16 69.638→110.766、BF16 70.929→114.883、TF32 37.941→62.023 TFLOPS。其 Falcon 1K/4K独立 Prefill Event/CUPTI 数字记录于 `control/falcon-rtx3090-t005/plan.md` 的“T002 reusable CUPTI seven-shape matrix”条目。该Prefill矩阵不是Stock和Unlocked双状态成对测量；不能把T002 GEMM Stock值与T002 Prefill值拼成因果对照。

本次Stock启动曾成功移除cmdline target但GEMM测得111.433/117.129 TFLOPS，证明设备状态没有回到历史Stock性能区间。该次结果存于`/data/sglang-hicache/falcon-prefill-ab/runs/stock-20261025/gemm/result.json`。随后Guest重新进入默认targets启动；当前启动日志为`gpu_unlock: unlock failed (-114)`，而CUDA/GEMM仍正常（FP16 110.297、BF16 115.935、TF32 62.438 TFLOPS）。故启动配置恢复但本次重启并未重新成功执行解锁事务；这是GPU固件/状态恢复问题，不影响此处历史benchmark口径判断。

## 正式结论

本次 Unlocked 独立runner测得1K/4K/8K forward latency约205/770/1,588ms；历史T002 B0摘要列有1K/4K Event/CUPTI约286/1,113ms。两者数值有明显差异，但工作树/日期/计时路径与配置记录均不足以解释或归因该差异；更不能归因GPU unlock。**没有Stock Prefill样本，没有可计算的Stock/Unlocked Prefill speedup；不输出加速比结论。**

本次one_batch启用profile参数却没有生成可用trace，故没有kernel时间归属证据；此报告不从源码静态猜测kernel贡献。