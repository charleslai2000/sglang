# G2 当前计划

## 已确立
QUASAR GGUF 42层、hidden2560、vocab262144、tied；BF16 Q-only loader fix已推送。固定4K BF16/E5M2完整logits差relL2 `.291054`、P99 `3.013479`、max `4.937507`，top-1=`128870/236187`；BF16 top1-top2 margin `.059046`，E5M2 margin `3.239758`。同prompt/HEAD/chunk的独立Forward并非同一数值轨迹，禁止直接当逐算子因果链。

## L4 因果定位
L4 position4095 Q相同，effective SWA window完整为positions3584–4095，不读prefix cache；跨run的512行current K/V中各505行不同。production Triton replay各自精确复现live，固定Q并交叉替换完整current K/V可精确重现live Attention差relL2 `.008345655`、max `.03125`；切换BF16/E5M2 prefix pool则在该query下无影响。结论：观察到的L4差异由上游生成的current K/V跨run差异解释，不是该位置读取FP8 prefix或已确认production bug。证据JSON `g2-4k-layer4-window-replay-20261105.json`。

## L17与数值裁决
L17 position4095生产重放精确；固定run内Q/current K/V仅切换prefix cache格式的Attention delta relL2 `.009277/.011253`，为真实局部precision effect，尚无suffix传播到logits的反事实。独立run完整logits top-1翻转不能归因于该效应。必须先实现Attention-output substitute并通过no-op exact logits identity，再测真实后续层/LM head关键logits与margin。当前无通过该no-op的suffix证据；FP8 E5M2保持 **NOT ACCEPTED**，容量/性能不启动，无生产缺陷/修复确认。

## 已完成
- T002数值定位结案：L4差异来自跨run current K/V；L17固定upstream cache反事实确认局部E5M2效应。详见`T002-numerical-verdict.md`。
- T003真实kernel A/B/C suffix反事实结案：BF16 compute on E5M2 cache不恢复BF16 Attention输出/logits/greedy token。详见`T003-L17-ABC-results.md`。
- E5M2仍 **NOT ACCEPTED**；当时无Owner阈值，容量/性能尚未启动。后续授权下的描述性表征见T006。

## 当前裁决

- 已推送修复 `3bf30274a281775b4eb813c08a85414b96821df2` 将 GGUF full-attention partial RoPE 从错误的 1.0 推断为 0.25；8 个单测通过。
- 修复后真实 BF16/BF16-KV TP1 HEAD-shadow GSM8K 全量 **1,091/1,319 (82.714%)**，严格 scorer 1,319/1,319 复核一致；相对历史同模型 BF16 398/1,319 高 693 题。该历史对比受 private Extend overlay 与旧 prompt fixture 不完整限制，不作单因素归因。详情见 `tasks/T005-rope-fix-full-quality.md`、`T004-GSM8K-root-cause.md`。
- 修复后真实 E5M2 HEAD-shadow 全量为 **1,098/1,319 (83.245%)**，与匹配 BF16 1,091/1,319 配对后差 +7 题/+0.531 pp；40 BF16-only 与 47 E5M2-only，20k paired bootstrap 95% CI [−0.834,+1.895] pp。未显示总分系统性回退，但区间仍涵盖轻微伤害，且无 Owner 质量阈值，因此 E5M2 仍 **NOT ACCEPTED**。完整哈希及真实服务证据见 T006 和 `experiments/g2-gsm8k-root-cause-20261107/postrope-e5m2-capacity-performance-20261111.md`。
- 用户授权的容量/吞吐表征已完成：E5M2 Full/SWA pool 在 max-running 1 为 1,117,828/4,738 槽，在 max-running 16 为 1,093,791/14,353 槽；64-in/32-out 合成请求聚合 TPS c1/c4/c8/c16 大致 9/33.5/不稳定/115。c8 波次有明显双峰，不能视作稳定点；这些仅描述性测量，不构成产品性能/质量接受。早期无效启动尝试均已排除；成功运行退出状态和有效产物见详细报告。无确认的生产 KV 缺陷，不改共享 dirty 源码。服务退出，GPU 1 MiB/0%，GPU 锁已释放。

本 Goal 当前无活动 Task。T006 `tasks/T006-post-rope-e5m2-qualification.md` 已完成：修复后 E5M2 配对质量及授权容量/吞吐描述性表征已记录；E5M2 产品接受仍待 Owner 阈值，不作 GO。详情见 `experiments/g2-gsm8k-root-cause-20261107/postrope-e5m2-capacity-performance-20261111.md`。服务退出、GPU锁释放；共享 dirty 源码未改。
