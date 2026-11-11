# G2 QUASAR E5M2 vs BF16 实际收益 A/B

## 目标
基于已完成的冻结 1,319 题配对结果，不重跑质量集；在 RTX3090 上对同模型、同服务配置、同 c1/c4/c16 请求工作负载做 BF16/E5M2 KV 显存分配、实际并发承载与吞吐 A/B，供 Owner 裁决。

## 约束
只改 KV dtype；复用已核验 HEAD kernel overlay（源码必须等于发布 HEAD blob）及固定 SM86 AOT binary；取得 `/tmp/f1-r16b-gpu-exclusive.lock` 后运行。保留共享 dirty 文件，不 broad-stage；仅提交本轮独立 harness、报告和控制记录。不得设定 Owner 质量阈值或重复 1,319 题质量评测。

## 完成
同条件两臂的分配槽、实际成功并发请求容量、吞吐结果及 SHA 对照；揭示 overlay 和运行源码身份/不可复现限制；有限文件安全提交并核验远端状态。质量结论沿用 `T006`，E5M2 接受权归 Owner。