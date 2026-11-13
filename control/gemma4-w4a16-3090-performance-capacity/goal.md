# W4A16 RTX 3090 性能与容量复测

## Goal
在现有工作区恢复官方 Gemma 4 E4B W4A16 服务（T004 Q4_0/MMQ opt-in 禁用），复跑可复现的历史性能矩阵，并以 32 个独立并发请求实测 c32 最大可用上下文及成功/失败边界。

## Scope
复用既有 checkpoint、启动参数、runner、fixture 和历史结果；先建立历史/当前配置可比性，再测实际 Decode、Prefill、延迟、显存/KV池与最大上下文。容量请求需各自独立前缀、真实 Prefill 和至少 256-token Decode；区分配置上限、GPU OOM 和调度限制、GPU驻留池及卸载辅助容量。

## Constraints
- 不修改 W4A16 量化算法或引入新子系统；禁用 T004 实验路径，不依赖 T004。
- 使用已存在工作树与工作区，不 reset、checkout或清理 dirty state；WIP基线 `f0ed163f78f2fd2208f61221740680d052a9bfa1` 保存全部项目 dirty files，`.pi/`和空文件`9`是本地排除项。
- GPU测试持有 `/tmp/f1-r16b-gpu-exclusive.lock`；执行前核查GPU/服务/端口，结束后确认进程、显存及锁状态。
- 完整保留服务日志、逐请求结果、GPU samples、launcher与配置身份。不得把不同模型/KV/图配置混成同条件结果；失败和未测事实如实记录。

## Completion
W4A16真实服务可用；历史性能矩阵按可复现原始口径完成并与历史证据逐配置比较；c32容量获得实测成功下限及配置/显存/调度/卸载边界；若首次失败边界未实测，明确标记为右截断而不声称最大值。结果和远端WIP/终结性提交状态有明确说明。