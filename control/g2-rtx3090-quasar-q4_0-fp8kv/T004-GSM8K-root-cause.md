# T004 — G2 GSM8K 质量审计与当前裁决

## 当前决定

**当前修正 HEAD-shadow BF16 RoPE 质量门 GO；E5M2 仍 NOT ACCEPTED。** 本文件第 6 节记录修正后 1,319 题实测 1,091/1,319 (82.714%)。以下旧审计保留其历史运行语境；历史 BF16 398/1,319 (30.17%)、E5M2 379/1,319 (28.73%) 不再代表修正后 BF16。禁止据此外推 E5M2 或推进未授权的容量/性能工作。

## 1. 现有 BF16 逐题审计

工件：`/data/sglang-hicache/g2-quasar-runs/20261106T093500Z-quasar-gsm8k-g1protocol-bf16/eval/results.jsonl`；SHA256 `002ea777f449f195fe1a3c74b77bddbb7769b91b053542e5bc158d8729e368a1`。

- `finish_reason=length`: **833/1,319 (63.15%)**；`stop`: 486。
- 截断组内 232 题 scorer 已识别正确 `####` 答案；其余 601 未被判对。截断组有 647 条 `####` marker；**0** 条在错误的首个 marker 之后又输出一个等于 gold 的 marker（first-answer strict protocol 下不属漏提取）。
- 未截断组 **166/486 (34.16%)** 正确。
- 全集 1,122 有 marker；197 题无 marker。724 个不正确输出含 marker 但首答案错误，197 个因无 marker 被判 invalid。样例 doc 0 反复生成 `The number of eggs she sells is 16.` 到 cap；doc 2 反复复述错误利润计算；doc 1 给出数学答案2.5而不是目标3；doc 70 正确数值 `####900` 无空格且内容本身错误（gold 7425）。doc 6 在 cap 前已正确输出 `#### 260`，后续只重复无关句子，照样被首答案 scorer 正确计分。可见问题主要是生成循环、错误推理和截断，不是单一 extractor 漏答案。
- 按 `####\s+number` 放宽空白重算现有结果，BF16仍398，未恢复任何题。对首 marker 后缀再搜 gold，截断组0个答案被藏在错误首marker之后。

典型原始 prompt/completion/评分在相应逐题 JSONL，例 doc 0/1/2/6/70。截断确实是 major symptom，但不能解释未截断只有34.16%的表现；没有“可提取答案被 parser 丢弃”证据。

## 2. 协议与身份核对

- 数据集test SHA256 `752adc99f23132275139f1f7be57126b08735a55daf0c56859ee6df70abafbac`，1319题；prompt/targets/5-shot文本顺序来自历史G1 samples及`gsm8k_official.yaml` (num_fewshot=5)。
- 冻结G1协议：显式BOS ID 2；greedy temperature0/top-p1，adapter每请求seed1234；`Question:`、`</s>`、`<|im_end|>` stops；max_new_tokens512；lm-eval0.4.13 first `#### (-?[0-9.,]+)` strict-match。当前有效复测使用pinned Gemma tokenizer显式 `[BOS]+encode(text,no-specials)`，所有1319 prompt IDs被服务逐条echo精确确认；stop、seed、cap、温度及extractor一致。另按whitespace-tolerant正则重算未改变分数。
- 先前首轮（BF16 398、E5M2 385）协议无效：遗漏显式BOS、额外`<eos>` stop、无request seed且server seeds不等。已保留但不参与裁决。
- 当前checkpoint是单一QUASAR GGUF SHA256 `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`，由GGUF同时构造tokenizer；服务日志确认GGUF quant及BF16 compute、BF16 KV实际torch.bfloat16 / E5M2实际torch.float8_e5m2。模型文件及GGUF tokenizer没有替换成HF tokenizer目录。
- 历史1,070/1,319 (81.12%)是**另一个** Google QAT W4A16 checkpoint SHA `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`。其历史full-wave runner在同一个本地tree上用显式BOS的逐题ID、Greedy/seed、1,319题，results `/data/sglang-hicache/gemma4/runs/20261030T-g1-full-wave-replay-r5/sglang/results.jsonl`；该结果是权重不同的context，不能要求Q4_0同分，也不能把差值视为Q4_0缺陷证据。历史 67.93% 另是W4A16 corrected-stop结果，也非当前GGUF oracle。
- 当前G2模型本身无HF Q4_0 logits oracle。修改 extractor 或从W4A16准确率外推不能修复模型生成质量。

## 3. 有界 llama.cpp 同 GGUF 对照及未决根因

现已用官方 GSM8K 仓库恢复 1,319 道 test 问题。恢复文件 SHA256 `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14`，与先前冻结文件哈希 `752adc99...` 不同，故只用于题目文本恢复，不冒充原始固定数据工件。原 G1 5-shot 样本/fixture 已在 `/data` 清理中删除，无法恢复精确 few-shot prompt；以下运行因此是 **zero-shot探索性对照**，不与全量 G1-protocol SGLang 分数作因果或同 protocol 比较。

CPU llama.cpp 对照使用 `llama-completion -no-cnv`、temperature 0、top-k 1、seed 1234、256 token cap、同一个 QUASAR Q4_0 GGUF。二进制 SHA256 `1c2c3930a5711488cd844d4442a85c5ec9b47ad05a90cd072a553ff201bd0043`；模型 SHA 与已知值一致。14 道已审计代表题全部真实运行完成（合计约296秒），输出及stderr保存在 `/tmp/quasar-llamacpp-gsm8k-zero-shot.jsonl`。zero-shot输入使用 `Question: <question>\nAnswer:`，与5-shot G1输入不同；llama.cpp tokenization路径亦未与SGLang服务逐token校验。生成的 `####` marker并不稳定（仅2/14原始输出包含 marker），且存在续写重复问题；这些文本只能作为同模型 CPU路径探索性证据，不能据此量化/确认 SGLang 的路径差异。

**根因仍未锁定。** 已完成的对照排除了“尚未运行 llama.cpp”这一缺项，但没有形成严格同prompt token级 A/B。因为必要的原始 few-shot fixture 已被清理，当前可继续工作是从保留的旧控制脚本/检查点产物重建原始 5-shot prompt，逐题哈希核对；若无法精确重建，则应如实止于探索性结果，不以新构造 prompt 补造等价性。不得重开无边界层级归因。

## 4. 有效 paired GSM8K 与 Needle

G1-protocol全量工件：
- BF16 `/data/sglang-hicache/g2-quasar-runs/20261106T093500Z-quasar-gsm8k-g1protocol-bf16/eval/`，398/1319；result SHA如上。
- E5M2 `/data/sglang-hicache/g2-quasar-runs/20261106T093500Z-quasar-gsm8k-g1protocol-e5m2/eval/`，379/1319；result SHA `33948ead6de4fe0ceafa7ad27b888a984e40da026567a5bf13994fb5daa93aca`。
- paired `/data/sglang-hicache/g2-quasar-runs/20261106T093500Z-quasar-gsm8k-g1protocol/paired.json`：both-correct316、both-wrong858、BF16-only82、E5M2-only63，差−1.4405pp；20,000次paired bootstrap 95% CI [−3.1842,+0.3791]pp。输出不同1126/1319。BF16/E5M2分别833/845 cap hits；不应将两臂接近当通过。
- `quality-audit.json`按逐题重算：未截断BF16 166/486、E5M2 164/474；截断中已score正确232/833、215/845。
- 被审计的低分不是首次BOS/stop误配所致：纠正协议后BF16仍398。E5M2相对有效BF16点估计−1.44pp，但CI跨0且BF16基线NO-GO，故这不是独立有效的量化伤害/接受结论。

新定义单针（不是历史fixture复现）四个服务运行均正确，16,384/32,768 token ID数及服务echo精确匹配；证据 `/data/sglang-hicache/g2-quasar-runs/20261106T181000Z-quasar-needle-final/{bf16,e5m2}/needle-{16384,32768}.json`。仅为检索sanity，不豁免GSM8K质量异常。

## 5. 工程与当时结论

以下记录的是2026-11-06旧全量服务：使用私有HEAD Extend kernel overlay，以避开共享dirty kernel的`BF16_KV_COMPUTE` NameError；未修改生产默认KV策略。旧服务后停止、GPU 1MiB、exclusive lock释放。相关评测实现/分析脚本在G2目录未跟踪状态；未擅自commit/push共享dirty文件。该次质量裁决已由第6节2026-11-10修正RoPE的独立全量实测更新。

## 6. RoPE 配置修复与完整 BF16 质量验收（2026-11-10）

### 修复身份与语义

- 修复 commit `3bf30274a281775b4eb813c08a85414b96821df2`：`python/sglang/srt/configs/gemma4_gguf.py` 从 Gemma4 GGUF `rope_freqs.weight` mask 验证 active-prefix + identity-tail 模式，推断 full-attention `partial_rotary_factor`；单测 `test/registered/unit/models/test_gemma4_gguf_rope_config.py` 8 项通过。仅以上两文件纳入提交；远端 `origin/3090-gemma4-e4b-hicache` SHA 与本地 HEAD 相同。提交前后共享工作树其他 dirty/untracked 路径均保留。
- 冻结 GGUF SHA 仍为 `7d6269096c9acbce4422fd1aa3a249436b01288868961e48ca9bb2541997f669`。实际配置为 42 层：35 SWA / 7 full-attention；SWA 保持 default RoPE、theta 10,000、head_dim 256，构造的生产 RotaryEmbedding 对 128 个 angle 全部非零。Full-attention 为 proportional RoPE、theta 1,000,000、head_dim 512、factor 0.25，生产 `Gemma4RotaryEmbedding` 报告 64 active angle pairs / 192 identity pairs；Transformers proportional inverse-frequency tensor 长度 256，64 个非零，其余 192 个为零。
- pinned llama.cpp revision `b49650adb31f2e49a0d76113aeb1792134fd8413` 的 `src/models/gemma4.cpp` 只给 non-SWA 层绑定 `rope_freqs.weight`，并将同一 mask 传入 Q、K 的 `ggml_rope_ext`；factor 0.25 等价于前 64 个频率按 1e6 base 旋转、其余通道恒等。先前同输入 component 对照显示 corrected Q/K RoPE 接近该 pinned 实现，full-attention/SWA 配置分离。该文件只作用于 `Gemma4GGUFTextConfig`，普通 HF Gemma4 和其他架构走各自 builder；普通模型行为由代码路径隔离，而非对所有模型的实测兼容性声明。

### Full-set 输入身份

GSM8K test Parquet `ee7b8da9e381df27b9e3f7758a159ab2bdaa4dbaa910546cbbc47e0cb44e4f59` 解析为官方 1,319 rows，并规范化为 test JSONL SHA `752adc99f23132275139f1f7be57126b08735a55daf0c56859ee6df70abafbac`，与历史 G1 frozen test hash **完全一致**；训练集 7,473 rows 的 normalized SHA 为 `6043ef64147b59871f4fd3adf669c306fe0a4c27e5a5c4bfb761f3f084895a13`。使用历史 lm-eval seed 1234 单一 RNG、ascending doc_id、每题 random.sample 5 个 train exemplars、保存 tokenizer 显式 BOS=2 并对文本 no-specials encode。新建 1,319 输入 fixture SHA `2e64e8865f9e314eadb3320593a23e65ebc3f01daf6d2f4662c35983df5c3f86`，prompt token IDs 总体串联 SHA `f74eeaa3dd3b0e715da4f0a440aad19b79e91e01ff35a154518a378f5d9755a7`。对照留存的 frozen 14 prompts，14/14 的 prompt 文本及 token-ID hashes 均完全相同；其余 1,305 题按同一确定性规则重建。故测试题、顺序、目标完全同历史基线，抽样/编码协议由留存样本验证；原始 1,319 条 G1 prompt fixture 已丢失，因此除 14 个 hash 外，其他题的历史 prompt 不能逐条 byte-compare。

### 修正后真实 BF16/A8 运行

运行使用同一 QUASAR GGUF/tokenizer，TP1 BF16 compute + BF16 KV、HEAD-shadow服务、Triton eager、chunked prefill 2048、context 8192、greedy top-k1/temp0、每 request seed1234、512 cap、历史 stop 列表和历史 first-`####` scorer。服务实际生成完全部 1,319 请求，prompts/results 均按 doc_id 0..1318 顺序；逐题 `prompt_sha256` 与 `prompt_ids_sha256` 均匹配 fixture，prompt token 数与输入 ID 长度全部一致。模型加载日志/元数据与运行配置确认 Gemma4 GGUF、BF16 compute/KV、Triton eager。运行中此前同设置 1104-token QKV EXTEND 的 capture 直接记录 `mmq_a8`，但本轮全量运行自身没有 kernel-level dispatch trace；故全量结论限定为该 HEAD-shadow 配置，而不以日志外证据声称每个矩阵皆 A8。

**全量结果：1,091/1,319 = 82.714%**，较历史同 QUASAR BF16 398/1,319 = 30.174% 高 693 题，即 **+52.540 pp**。测试集规范 hash 与历史完全一致；历史 14 个留存 prompt 的文本和 token-ID hash 14/14 一致。旧完整 1,319 prompt fixture 已不可恢复，因此其余题不能逐条 byte-compare；当前 five-shot 重建采用同一已记录的 seed/order/BOS 规则，任务集/目标/评分和留存对照相符。历史 G1 使用 private Extend kernel overlay，当前是已推送修复的 HEAD-shadow；这一 serving-tree 差异未被本次隔离。故这是当前 HEAD-shadow 路径完整资格结果，不是历史 overlay 的逐位复现或差距的单因素归因。

全量原始输出 `/data/sglang-hicache/g2-quasar-runs/20261110T-g2-rope-bf16-quality/results.jsonl` SHA-256 `3e0cdfdce5d2a2c864c6f4ab7f83b4ebe71982306ebf2fafe943601b1a32a8e4`；输入 fixture SHA-256 `2e64e8865f9e314eadb3320593a23e65ebc3f01daf6d2f4662c35983df5c3f86`；serving model metadata `/model-info.json` 保存副本，SHA-256 `25c5dcaa2b988170fdc924e0c07c23032710990725fcf39d8c5da92d295899df`；服务日志 SHA-256 `0124cb752a722d1c7f14b115b1df7af4d7ffe04392275121a759c2a3d90de736`。

结果类别（有重叠项）：`finish_reason=length` 8/1,319 (0.61%)，其中 2 题 strict-last `####` 答案仍正确、6 题无 marker 且错误；`Question:` stop 1,311。按连续相同 4-gram 至少 8 次定义 repetition_flag 的输出 42/1,319 (3.18%)，其中 25 答案正确、17错误；重复 flag 与 cap 可重叠。无 `####` 16 (均错误)，有 marker 但 strict-last 答案错误 212；总错误 228，其中非 cap 正常 stop 错误 222。没有多 marker、跨题 `Question:` 泄漏。对全部1,319条使用历史 `gsm8k-strict-last` filter + lm-eval exact-match scorer 重算，1,319/1,319 与逐条结果一致。

修正后的 frozen-14 子集为 9/14，复现既有 bounded intervention；完整集达到并大幅超过历史同权重分数。当前集合没有多 marker，first 与历史 strict-last marker 提取等价；权威重算使用历史 strict-last extractor + lm-eval exact-match scorer。**最终状态：当前已推送 HEAD-shadow BF16 RoPE 修复质量门 GO；E5M2 仍 NOT ACCEPTED。** 本项不授权/不代表 E5M2、FP8、capacity 或 performance 接受；历史 private-overlay 质量结果尚未用新修复重跑。完成后服务已停止、GPU 独占锁释放，GPU 为 1 MiB / 0%。