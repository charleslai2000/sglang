Status: DONE
Work area: experiments + ops
Objective: 以固定上游 gpu-unlock `af28cbbfd3d922a659227ecfb7369adfd924cf03` 对 RTX3090 Guest BDF `0000:00:10.0` 部署解锁，完成 Stock/Unlocked GEMM A/B验收。
Inputs: 已完成T001审计/构建；用户授权Guest sudo安装、启动配置修改与重启，并确认宿主独立console、VM stop/start及宿主断电冷启动恢复可用。
Completion: 固定版本正式安装；仅指定BDF于udev前解锁，冷启动后driver/CUDA健康；同协议三精度真实GEMM，数值与Stock一致；保存回滚资产和结果。并行dirty worktree不切换/提交。
Result: 使用现有固定版本包安装`gpu-unlock-dkms`和`gpu-unlock-firmware` 1.0.0；包SHA256分别`c2e22ddd58569eb8e9fc65c910a7ce73990000bb27476391fab867aa1cae994f`和`0cca79547492c173d23fb1c55437ef6a701ac76c92b408d3993817ae7bb656d7`。源码HEAD仍固定`af28cbbfd3d922a659227ecfb7369adfd924cf03`。已签名DKMS模块适配运行内核6.8.0-147-generic。根据正式生成镜像实际检查发现默认modules.d仅保证打包、不保证udev前加载；补充本地init-top hook及明确udev prereq，在镜像`/data/sglang-hicache/gpu-unlock/installed-check/`确认`000-gpu-unlock`位于udev前（ORDER第7/9行），加载参数严格白名单`0000:00:10.0`，且必须cmdline有精确`gpu_unlock.targets=0000:00:10.0`才加载；早期模块及五项固件文件存在。更新实际默认GRUB cmdline及initramfs后，仅重启Guest一次。

重启后`/proc/cmdline`含精确target；dmesg 07:54:24 `pci 0000:00:10.0: gpu_unlock: unlocked`；NVIDIA 580.178.04随后绑定该BDF；nvidia-smi/torch CUDA正常（SM86、CUDA runtime12.9），独立CUDA matmul成功。GPU PL始终350W。模块日志报告signature/required key missing、taint，但模块继续工作、解锁成功；Secure Boot EFI vars不可用，未更改Secure Boot。该签名告警如后续环境启用强制签名需单独排查，本轮无NVRM/Xid/AER错误。

复用Stock脚本`/data/sglang-hicache/gpu-unlock/bench_gemm.py`，相同N8192、seed20261025、输入和strict FP32 reference、warmup5、15 GPU-event iterations/repeat、5 repeats、FP32 accumulation，持有项目GPU exclusive flock。结果位于`/data/sglang-hicache/gpu-unlock/unlocked-gemm-20261025T0810Z/`，摘要`ab-summary.json`。Stock→Unlocked medians：FP16 69.638→110.766 TFLOPS (1.591x,+59.06%)；BF16 70.929→114.883 (1.620x,+61.97%)；TF32 37.941→62.023 (1.635x,+63.47%)。每种精度Stock与Unlocked output SHA逐位一致、重复间一致；输入X/Y及FP32 reference SHA均相同，rel-L2与Stock逐项一致：FP16 .000358795、BF16 .002868459、TF32 .000293877。Unlocked温度45C、运行时约120.8W、SM 1905MHz/MEM 9501MHz；收尾38C、0%/1MiB，无GPU进程。完整结果SHA `d9f1740c02d0351e3c23986c6dc92525584d82d2916087c28fd387854a037403`；A/B摘要SHA `222fc0733451aaf7db38f03cd10be96a56435a490be5a8277e0310ff5ae8df84`。Stock结果SHA `38179e5a32fa56fee50c58d7e74ca2500492179b121b49466c0976d910ddeee4`。

回滚资产在`/data/sglang-hicache/gpu-unlock/deployed-backup/`：Stock kernel 6.8.0-146 initrd、unlocked kernel 6.8.0-147 initrd、Grub cfg、GRUB专用片段、模块目标配置、udev前hook及checksums，`sha256sum -c`通过。另有原始predeployment GRUB/initrd备份`boot-backup-20261025T0635Z/`。没有重复warm reboot或host power cycle。

GPU Unlock证据与简短摘要已选择性提交到`3090-24g-hicache`。原并行Gemma checkout 未切换，未提交其中任何工作。另有Falcon独立服务复测，索引见`evidence/falcon-service-20261025.md`；不是Stock/Unlocked Falcon因果对照。
Remaining: GPU unlock部署、boot日志、驱动/CUDA健康和GEMM A/B均PASS。未做Falcon性能/Falcon correctness，不在本任务验收范围。Git evidence未提交/推送（branch ownership冲突；无任务证据文件需提交）。签名告警为已观察警告，不影响当前成功，不执行未经要求的额外reboot；如未来Secure Boot强制签名需另行处理。
