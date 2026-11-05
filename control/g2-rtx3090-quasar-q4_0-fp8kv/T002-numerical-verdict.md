# T002 最终数值调查裁决

**Verdict: E5M2 NOT ACCEPTED；本4K case数值 gate NO-GO。** 不是已确认实现bug的结论；完整logits/token差异和真实suffix反事实成立，但项目文件没有规定可判定全模型质量的任务阈值，故仍需用户裁决接受标准。不得启动容量/性能测试。

## 运行对照与混杂审计

BF16基线：`g2-4k-full17-bfloat16-20261104T234010Z`；E5M2基线：`g2-4k-full17-fp8_e5m2-20261105T000655Z`。同模型文件路径，GGUF SHA256 `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`；model_identity记录同source HEAD `b3b337f5882ef495c0c803441eae65c0cdf3aaf6`。同tokenizer/model，BF16 model dtype、context 4608、chunked prefill 2048、Triton backend、page size1、prefill/decode CUDA graph disabled、deterministic inference false，temperature0/top_p1/top_k1/max_tokens1。两侧final EXTEND token IDs SHA256均为`3d6604257fe438aa8867f8200322d69a6cb7c254c573793fe13a8d3ef9407b3b`，position范围2048–4095，末token236187。唯有配置上的预期主要差异为`kv_cache_dtype=bfloat16` vs `fp8_e5m2`。

重要保留：实际启动`random_seed`不同（BF16 18439608；E5M2 343913761）；运行工件也没有证明两次GPU allocation/物理slot布局和所有随机数消费者完全同态。因此只能将配对结果称为**相同模型/fixture/主执行配置下、KV模式为主要受控变量的实测总效应估计**，不能声称除KV dtype外所有内部执行状态逐值相同。没有证据显示seed影响此无采样的确定性prefill logits；无需据此推翻现有结论，但随机seed差异是剩余外部可见混杂风险。没有再做定向补测：重复E5M2 final chunk保持相同input-ID hash、top1=236187/top2=128870、logits逐元素完全相同（`g2-4k-full17-fp8_e5m2-20261104T235403Z`与`...20261105T000655Z`）；不同seed未改变该侧结果。BF16短/生成重复证据见已有T001/T002记录，不重复其运行。

## 数值证据及含义

### 配对完整4K：KV模式总效应估计

Final sampler logits BF16 vs E5M2：relL2 `.291054`，P99 abs `3.013479`，max abs `4.937507`。BF16 top1=`128870` logit `7.082581`，top2=`236761` logit `7.023535`，margin `.0590458`。E5M2 top1=`236187` logit `8.739378`，top2=`128870` logit `5.499620`，margin `3.239758`。这是端到端配置对照的总差异，不是cache-only单因子分解。

### L4：current K/V 条件直接影响

Position4095 SWA窗口为`[3584,4095]`，不读取prefix。固定Q、交换两次运行的完整窗口current K/V，production kernel精确复现观察到的Attention差relL2 `.008345655`、max `.03125`；只交换prefix pool没有影响。故L4该位置跨run差异由current K/V操作数不同解释，不是该位置读取FP8 prefix。它是上游数值轨迹差异，不是cache-format单点效应，也不外推所有层。

### L17：cache-format条件效应及真实suffix传播

调用链`Gemma4Attention → RadixAttention → TritonAttnBackend.forward_extend → extend_attention_fwd`；按真实同次capture及完整production参数的two-stage replay，BF16/E5M2同cache输出均逐元素重现position4095 live。替换同次upstream Attention输出的no-op在两侧均使最终完整logits逐元素复现基线（relL2/max/nonzero=0）。reverse臂固定该forward的Q/current K/V/metadata，仅prefix cache bytes/关联格式改变，使用独立临时pool；实际注入tensor与反事实输出逐元素相同。

- BF16 upstream：换成E5M2 prefix，Attention relL2 `.0092772`/max `.0234375`；沿suffix后logits相对BF16 baseline relL2 `.1053791`/max `2.394367`，top1从128870变为236761，margin `.0587215`。
- E5M2 upstream：换回BF16 prefix，Attention relL2 `.0112956`/max `.03125`；沿suffix后logits相对E5M2 baseline relL2 `.1406416`/max `2.525362`，top1仍236187、top2成为106，margin `1.279818`。

这是只针对L17 position4095、固定各自upstream的cache-format条件效应。不可把两次reverse logits的relL2相加，不能宣称解释完整BF16/E5M2总差异或一般化到所有cache token/layer。

## 数值门与实现裁决

- **已证实cache模式影响：** 同配置实测完整4K logits/token有显著差异；L17 cache格式单点扰动经真实suffix传播，至少在BF16 upstream会翻top1；E5M2 upstream下明显改变排名/margin但本次单点不翻top1。
- **实现缺陷：** 已查L4/L17指定路径并完成正确生产kernel replay与反事实核验；尚未发现足以解释这些数据的production Attention实现缺陷。此前不正确的离线L17 replay已由真实路径capture/replay替代，不再作为证据。
- **模型任务质量：** 没有经授权/定义的acceptance tolerance、任务级质量语料或要求的精度门。故不能判定模型任务质量PASS；当前明确为**NO-GO / NOT ACCEPTED**，将数值质量阈值作为用户裁决条件，而不自行杜撰阈值，也不因缺少全层误差分解继续无限调查。

证据索引：L4 `/data/sglang-hicache/g2-quasar-runs/g2-4k-layer4-window-replay-20261105.json`；真实L17 reverse suffix `/data/sglang-hicache/g2-quasar-runs/g2-layer17-intervention-logits.json`；L17 live-path replay `/data/sglang-hicache/g2-quasar-runs/g2-layer17-live-path-replay.json`；capture和driver见任务T002记录。
