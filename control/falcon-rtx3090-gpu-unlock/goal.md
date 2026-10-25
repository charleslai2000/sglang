# RTX3090 GPU Unlock 受控性能验证

## 目标与边界
评估 Zagitta/gpu-unlock 对本机 RTX3090 的 BF16/FP16/TF32、Falcon Prefill/Decode 实际影响；仅在维护/重启授权、源码审查、构建测试和可靠回滚均满足后安装启用。独立于已结案 T005。

## 禁止事项
不刷写VBIOS、不升级驱动、不改Secure Boot/功率限制、不混改SGLang或Kernel；不得自动修改启动配置或重启。目标PCI BDF必须精确指定。启动恢复不可靠则不安装。

## 完成条件
形成同配置Stock/Unlocked GEMM及Falcon Prefill 1K/4K、Decode c8/c32实测表，含输出/数值一致性、温度功率时钟错误与HiCache状态；安装版本commit/hash、构建/项目测试、回滚验证和是否建议保持启用的结论。未获维护授权不得进入启动配置更改和重启阶段。

## 后续实测关联（非解锁因果对照）
Falcon 独立真实服务实测位于 `/data/sglang-hicache/falcon-unlocked-20261025/runs/20261025T094033Z/`，模型 revision `52036ae497a2c0c253e17f98cc8652f2f7082ae3`。该复测不是 Stock/Unlocked 配对，不据此归因解锁收益。
