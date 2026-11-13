# 当前状态

## 已确认
- 固定模型、revision、venv、AOT bootstrap、服务参数及64-token来源均可复用。GPU RTX3090 `0000:00:10.0`，350W；当前空闲且Falcon独占锁空闲。
- 已从T005 fixture确定性生成1K/4K/8K/16K token-ID fixture，保存于`/data/sglang-hicache/falcon-prefill-ab/fixtures/`。服务支持直接`input_ids`及`cache_salt`；可通过`--disable-radix-cache`关掉服务Radix prefix cache。
- 已由离线 tokenizer round-trip 验证固定IDs转文本再编码无损。准备了 `one_batch`复用脚本、独立`ModelRunner.extend` runner、服务端顺序请求/零缓存驱动、ReqTimeStats关联器和报告模板；Python/shell语法、CLI选项通过检查，未在GPU上验证。服务驱动要求精确prompt token数和响应`cached_tokens=0`；启用metrics/time-stats日志以分离scheduler queue与forward。
- Stock切换路径当前未满足安全可验证条件：`/boot/grub/grub.cfg`所有普通/recovery入口均含unlock参数且timeout=0；当前6.8.0-147 initrd、Stock备份6.8.0-146 initrd和恢复备份147 initrd均含`gpu_unlock.ko`及init-top hook。移除参数本身不可证明Stock，亦无现成、已验证的Guest临时Stock启动及自动恢复流程。
- 未改系统启动配置、未重启；未运行GPU测量或服务。工作区并行Gemma dirty内容保持未动。

## 决定性前沿
持锁先做独立runner smoke并测Unlocked全矩阵。真实服务逐请求验证prompt/cached token及队列/forward时间。Stock仍需可自动恢复的Guest单次启动方法，且重启后GEMM确证Stock才可测；现有Guest sudo/重启授权不等于猜测性GRUB/initramfs变更。

## 结果
暂无Prefill实测，无Stock/Unlocked表，无性能收益结论。