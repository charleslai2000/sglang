# RTX3090 GPU Unlock 验收结论

## 结果
目标Guest RTX3090 `0000:00:10.0` 已在固定上游`af28cbbfd3d922a659227ecfb7369adfd924cf03`下部署并成功解锁。唯一一次Guest重启后内核日志报告`pci 0000:00:10.0: gpu_unlock: unlocked`；Driver 580.178.04正常绑定，CUDA 12.9 runtime可运行，GPU PL 350W不变。

## GEMM A/B
匹配N8192、seed20261025、FP32 accumulation/reference、warmup5、15次/event repeat、5 repeats。Stock→Unlocked medians：FP16 69.638→110.766 TFLOPS（1.591x）；BF16 70.929→114.883（1.620x）；TF32 37.941→62.023（1.635x）。三种输出SHA分别完全相同于Stock，rel-L2不变；输入与FP32 reference hashes一致。证据及启动日志见`/data/sglang-hicache/gpu-unlock/`，T002 task有摘要和hash。

## 启动与安全
正式initramfs经展开确认精确BDF hook在udev前加载，启动目标参数仅`0000:00:10.0`。NVIDIA模块正常后续绑定。日志有DKMS模块signature/key missing taint警告，但无Xid/NVRM/AER错误，当前GPU idle 0%/1MiB，CUDA smoke PASS。回滚镜像和Grub/initramfs配置及校验文件在`/data/sglang-hicache/gpu-unlock/deployed-backup/`及`boot-backup-20261025T0635Z/`。

## Falcon 服务复测关联
独立真实 Falcon 服务复测证据位于`control/falcon-rtx3090-gpu-unlock/evidence/falcon-service-20261025.md`，详细记录在`control/falcon-rtx3090-t005/runs/T005-FALCON-UNLOCKED-SERVICE-20261025.md`。c8 448.868±13.415、c32 777.280±0.926 output tok/s；与历史 T005 仅近似比较，不是解锁因果A/B。

## Git状态
证据提交到`3090-24g-hicache`；并行Gemma分支未切换或改动。Falcon模型级结果是独立复测，不属于GEMM解锁的因果收益验收。