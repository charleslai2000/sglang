Status: DONE
Work area: experiments
Objective: 使用真实独立请求验证 RTX3090 上 Gemma4 QUASAR BF16 compute + E5M2 KV 的 c32、平均驻留上下文 32K 和持续 Decode；失败时定位限制并测量实用替代负载。
Inputs: 已验收的 QUASAR 模型 SHA `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`、HEAD attention overlay SHA `69a9f59d6817b3947feb38639d47c690e82947ead0e9af50a0200f02a4b34d4e`、SM86 AOT SHA `22c9f5eb84e5e494df31f814aeffe5ba0aafb266fca2b56c99cfb5a3c1dea4c2`；GPU 独占锁 `/tmp/f1-r16b-gpu-exclusive.lock`。
Completion: 真实服务、无共享前缀独立请求、服务端 active decode 证明、池容量/峰值显存/延迟/吞吐、失败边界、证据 hash、GPU/端口/锁清理、精确提交和远端 SHA 核验。
Result: 目标 c32×32K sustained decode 未达到。Full/SWA pool 为 1,068,151/24,609 slots；32 个请求最终各收 32 输出块，但 1,322s 时唯一 decode batch 只有 running=16、0.71 tok/s。Prefill 中 SWA 多次 0.99–1.00，出现 pool-full retraction。16×32K 最终每请求收 64 outputs 但仅一条 decode batch，724s、0.74 tok/s。已证实成功点：c32×8K×512，32/32 active decode，12/13 rows running=32，median 283.41 tok/s；c16×16K×256，16/16 active decode，median 148.305 tok/s。两成功点 GPU sampled peak 22,384/22,104 MiB；报告 `experiments/g2-quasar-e5m2-longctx/LONGCTX-RESULTS-20261111.md`。原始 Full/SWA 关停导致的异宽 store fallback 和临时 JIT schema 试验均无效且已从正式 runner 撤销。无逐 kernel trace；成功点不是最大 OOM/容量边界。
Remaining: 无。
