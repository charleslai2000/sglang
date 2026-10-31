# Gemma4 RTX3090 BF16 Decode 性能基线

## 目标
在当前 `3090-gemma4-e4b-hicache` 分支，以固定 W4A16/BF16 KV/CUDA Graph 服务配置测量 64in/256out 的 c1–c32 吞吐、延迟和真实 GPU Decode Forward，并与冻结 Falcon T005 数据作非门槛式对照。

## 约束
仅测量；不修改生产数学、Oracle、数值guard或阈值。不开 FP8 KV、HiCache、实验优化；不重做既有 G32 Prefill/C16 容量实验。保护所有其他dirty/untracked文件。GPU任务必须持有 `/tmp/f1-r16b-gpu-exclusive.lock`；结束清理服务并确认资源空闲。

## 完成
每档至少三次有效测量并留存请求级原始结果、配置和身份；记录服务TPS/TTFT/TPOT/总延迟、显存与利用率、真实active/decode batch及Graph replay；单独测量真实Graph Decode Forward batch1/2/4/8/16及条件允许的32；解释服务/Forward边界与实测瓶颈。形成报告和复跑脚本，精确提交推送Gemma-owned证据并核对远端SHA。该性能里程碑不构成G1数值正确性验收；G1继续FAILED / NOT ACCEPTED。
