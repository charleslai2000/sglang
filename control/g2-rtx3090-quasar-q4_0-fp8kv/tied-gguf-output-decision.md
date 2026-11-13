# Tied Q6_K 输出头源码核验

## 已确认事实
- 固定 archive 无 `output.weight`；native config 为 `tie_word_embeddings=True`，`token_embd.weight` 是 Q6_K，逻辑形状 `[262144, 2560]`。
- Qwen `3fa3b78197` 的 tied 配置会把 `VocabParallelEmbedding` 对象用作 `lm_head`。`GGUFEmbeddingMethod` 继承 `GGUFLinearMethod.apply`，而 `LogitsProcessor` 的 GGUF 分支会调用 quant method 的 `apply`。这表明现有方法有投影入口；但仍需实测 tied embedding 的 packed 参数属性/布局是否符合 `apply` 的要求，以及当前 Gemma4 name/load/tie 路由是否正确。源码静态审查不能据此判为支持或不支持。
- Gemma4 当前 `build_gemma4_name_map` 不含 `output.weight`，loader 却用 `get_gguf_extra_tensor_names()` 的映射目标 `lm_head.weight` 推断 tied；由于 map 无该条目，缺失 output tensor 不会产生这个目标，native config 虽当前已设置 tied，但 loader 判定本身不能证明 tied。更重要的是，Gemma4 `load_weights` 将量化 iterator 产生的 `model.embed_tokens.qweight` 路由到单个 tied embedding 参数名；PP helper 只识别 dense `.weight` 名。要在独立 PP head 或量化 projection path 中可靠复用 packed tensor，需要显式 route qweight 与 qweight_type。
- 本次检查固定 QUASAR archive 时未发现 `ffn_*_exps` 或 router/expert 张量；此前关于固定目标包含 MoE expert 张量的描述不准确，已撤销。其 config 重建字段仍需结合实际参数 inventory 审计，但这不构成当前确认的阻断。
- `3fa3b78197` 和 `4501e59f88` 均属于已 fetch 的本仓库 `origin/3090-24g-opt` 历史；`4501e59` 的 Gemma-style GGUF norm fold只针对目标参数的 GemmaRMSNorm module contract。当前 Gemma4 用的是另一 runtime norm 类，不能机械应用这项 Qwen 补丁。

## 当前状态
无证据证明 tied Q6_K LM head 需要新算子，也无证据证明 Gemma4 的权重绑定、packed 布局和真实 logits 投影已经正确。继续当前模型初始化、完整权重加载与 BF16 生成实测；在实际运行中定位并修复问题，不将静态猜测作为架构阻断。BF16 仍 NOT_RUN / NOT ACCEPTED；取得真实生成及对照结果前不得推进 FP8、容量或性能验收。
