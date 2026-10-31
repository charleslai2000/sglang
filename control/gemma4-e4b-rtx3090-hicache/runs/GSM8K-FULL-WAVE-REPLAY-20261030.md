# GSM8K 全量 Wave 复测 — 2026-10-30

## 判定

**评分复核更正：**最初runner仅移除逗号，遗漏lm-eval末尾句点归一化，误判SGLang doc1044预测 `1.`。逐题使用lm-eval 0.4.13 `exact_match_hf_evaluate` 交叉核验后修正；vLLM计分无差异，IDs/生成文本未改。

当前固定Fork的全量 BF16/W4A16 Wave 得分 **1070/1319（81.12%）**，vLLM 得分 **1064/1319（80.67%）**。历史两项SGLang分数为：无 `Question:` stop 的 **1076/1319（81.58%）**，修正 stop 后的 **896/1319（67.93%）**。因此旧的约12.96pp跨引擎差距在本次同IDs、同stop、同Wave条件下**不重现**；当前Fork-vLLM差仅6题/0.45pp。新Fork与旧无stop配对22题评分翻转（14旧对新错、8旧错新对），与旧修正stop run则306题翻转（66旧对新错、240旧错新对）。历史低分的具体原因 **UNKNOWN**；新证据显示运行条件/协议路径存在差异，但不足以精确归因。这**不构成生产数学修复证据**。G1仍FAILED / NOT ACCEPTED，直到冻结数值guard通过/获正式处置。

| 配对 | 两边都对 | 两边都错 | 左侧仅对 | 右侧仅对 |
|---|---:|---:|---:|---:|
| 新SGLang vs 新vLLM | 1051 | 236 | SGLang 19 | vLLM 13 |
| 历史无stop SGLang vs 新SGLang | 1062 | 235 | 历史 14 | 新 8 |
| 历史修正stop SGLang vs 新SGLang | 830 | 183 | 历史 66 | 新 240 |
| 历史无stop SGLang vs 新vLLM | 1053 | 232 | 历史 23 | 新 11 |
| 历史修正stop SGLang vs 新vLLM | 832 | 191 | 历史 64 | 新 232 |

新SGLang/vLLM逐题完整输出IDs相同 **967/1319**；首个生成token不同22题，中位公共输出前缀87 token。逐题请求和ID映射均唯一、稳定；无相邻请求污染迹象。不过两新引擎运行在不同实现/调度器，且vLLM为eager、Fork为decode CUDA Graph，分歧本身不能归因具体算子。

## 固定输入与执行

- 直接复用已有 `/data/sglang-hicache/gemma4/runs/20261026T-gsm8k-g1-final-bos/bf16/samples.jsonl` 中1319条prompt文本/答案及本地已pin test split；没有重建/下载数据集。顺序按doc_id 0..1318，固定83个16请求wave（最后wave 7条）。
- Prompt token IDs重建为 `[BOS=2] + tokenizer.encode(prompt, add_special_tokens=False)`；与已审计128题fixture的128/128 IDs逐位相同；新SGLang与vLLM两边1319/1319 IDs相同，prompt echo通过。
- 两边均 greedy temperature0/top-p1，BF16 activation/compute、BF16 KV、同W4A16 checkpoint，`max_tokens=512`，stops `Question:`, `</s>`, `<|im_end|>`, `<eos>`；各引擎按16请求波次运行。SGLang当前Fork默认decode graph最高bs16、Radix cache disabled；vLLM `max_num_seqs=16`、`max_num_batched_tokens=16384`、eager（无CUDA Graph）、无prefix cache、chunked prefill disabled。checkpoint revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`，模型SHA256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`。
- Fork源码SHA `3c9b25e808f1258578102c424f50f3e322e228d3`；vLLM源码SHA `c722f3a5368a9eed2b90c1a14b8eaf17acba3e93`；vLLM版本 `0.32.1rc1.dev326+gc722f3a53`；SGLang torch `2.13.0+cu129`，vLLM版本环境记录于run日志。两个环境均实际启动RTX3090模型、加载Marlin W4A16和Triton attention，并完成全量请求。两次执行后GPU为0%/1MiB，无服务进程残留。
- 评分沿用lm-eval GSM8K `strict-match` 首个 `#### number` 及HF exact-match归一化，并逐题用lm-eval 0.4.13官方scorer交叉校验。最终official正确数为Fork 1070/1319，vLLM 1064/1319；两边1319/1319输入匹配，Fork 1318 stop结束/1 length结束，vLLM 1315 stop结束/4 length结束。

## 历史运行差异的最强证据

当前新SGLang与历史无stop运行评分几乎相同（22/1319翻转），而与历史corrected-stop run有306/1319题评分不同，且新vLLM同样贴近旧无stop分数（34翻转）而远离旧stop run（296翻转）。这把差异定位到**运行条件/协议路径**而非Fork独有问题。最直接已知配置区别是无stop与corrected-stop运行的Question generation boundary；但是旧样本保存文本在Question边界之前也不同，故不能把全部变化归结为后缀裁切。历史运行的请求Wave/RID/Forward记录不足，无法裁定是否还有调度、采样、worker环境因素。

日志将SGLang worker seed设为 `666360643`；兼容vLLM runner在每个16题wave内使用同seed，runner记录并验证数值request ID/顺序。历史旧corrected-stop SGLang也用该seed，但分数/输出与新Wave不一致，意味着seed本身不能固定住不同batch/调度与执行路径的确定性。源树静态比较发现真实Fork/vLLM Gemma4实现不同，但本次全量分差不重现，没有证据将历史分数关联到某一计算差异。

## 产物和哈希

根目录 `/data/sglang-hicache/gemma4/runs/20261030T-g1-full-wave-replay-r5/`。每个引擎目录含1319逐题JSONL（prompt IDs、输出IDs、doc ID、request顺序/RID、文本、stop/finish、评分）、frozen prompts、manifest、summary、server/GPU日志。

- shared frozen prompt JSONL SHA256 `50f37d5bd95fe18af628502b58275613d1942664a4a4123341846e275092b53e`。
- Fork results SHA256 `e7f04d19f904b73c8a2411d5a2baf1f46604c9beaff26c027d4d3e6db17bf759`；vLLM results SHA256 `afb8ef8a0313003d78a9f6986ad21075c3b6f9f1e93dbf01d29b69208bc5191b`。`paired-summary.json`的正确数已按官方scorer更新。
- 机器可读逐题摘要 `paired-summary.json`；完整run manifest和实际server启动参数在两引擎各自目录。文件均位于 `/data`，不纳入Git。

本报告和可复用执行脚本是本次唯一源码树改动。没有生产修复、Oracle/guard/阈值改动，也未重新运行已关闭的算子实验。
