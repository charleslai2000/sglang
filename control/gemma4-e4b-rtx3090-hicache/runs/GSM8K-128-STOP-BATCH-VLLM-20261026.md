# GSM8K 固定128例 Stop / Batch / vLLM 对照 — 2026-10-26

> **报告勘误（2026-10-26）：**初版跨引擎计分无效。vLLM离线API按request ID字典序排序，原driver错误zip回输入标签。现已按数值request ID修正并GPU复跑，128/128输入身份通过；以下使用修正后的结果。

## Fixture 与执行
- 从已归因 full-run 的 BF16 样本中按 seed `20261026` 固定64翻分和64未翻分案例；保留原5-shot原始prompt、显式BOS及Gemma tokenizer精确 IDs。fixture `/data/sglang-hicache/gemma4/runs/20261026T-gsm8k-stop-onoff-rerun/fixture-128.json`，SHA256 `964107fed3350063ce84ea91de3b61bbe10ff733c685dc3b43566cf1d4d1fb3e`。本次重放的prompt IDs均与fixture一致。
- SGLang Fork分两种调用负载：C1逐条发送；并发Wave每16条用独立HTTP请求同时提交，BF16 KV、相同W4A16 checkpoint、greedy temperature0/top-p1/seed1234、max_tokens512、ignore_eos、无Radix cache。各自Stop OFF (`</s>, <|im_end|>`) / ON (`Question:, </s>, <|im_end|>`)，共512 requests。SGLang返回的Completion token IDs按API保留matched stop token；用于比较生成前缀时须识别Stop匹配位置。
- Fork复现实例的`max_running_requests=16`、CUDA graph max decode batch16；并发wave有效产生多请求Prefill batch。日志计数包含308个batch1、29个batch2、73个batch3、10个batch4 Prefill；真实同一Decode Forward中的样本batch size和对应token历史不能单由HTTP请求波次推定。原全量BF16评测 `server.log` 没有保留Prefill batch行；E5M2原run日志显示1,320条均为`#new-seq:1`。所以并发wave是当前调度压力对照，不是原全量run批量复原。
- vLLM独立环境：`0.32.1rc1.dev326+gc722f3a53`，同一revision/checkpoint、G32 compressed-tensors W4A16、BF16 model/activations、BF16KV兼容默认(`auto`实际config)，Triton attention、Marlin、eager、无prefix cache；同128 input IDs，单个`LLM.generate`批次，`temperature=0, top_p=1, max_tokens=512, stop=[Question:, </s>, <|im_end|>]`。通过真实3090验证模型成功load及完整生成；GPU锁用`/tmp/f1-r16b-gpu-exclusive.lock`，结束后GPU 0%, 1MiB。

## 结果
- C1每例ON/OFF各一轮：126/128 ON请求匹配`Question:`；所有126例Stop前的ON token IDs均精确等于同例OFF token前缀（包括`Question:`两token）；另2例未在512 token内触发该字符串。Stop没有改变单条Greedy请求在命中前的可见token序列。历史12例重放中的3例×3重复以及当前代表案例均稳定，但本128例每条件只跑一次，不能外推为任意执行完全确定。
- 并发16请求wave：126/128 ON请求匹配`Question:`，但其中23例的ON/OFF token序列在Stop token前已分叉，说明调度/计算条件可与Stop效应叠加；其余103例在 Stop marker前序列一致。C1 vs batch16 同策略同prompt：256个比较中139个输出token序列不同，首次token差异中位数83；11个在前三token内分叉。控制案例8的完整采样前logits显示，单请求C1的ON/OFF Stop前全序列逐步logits bitwise相同；并发batch路径同一prompt的ON/OFF第1步logits已不同（最大绝对差0.2455），但该例Top-1仍相同，之后Stop前token仍相同。控制样本58并发条件下ON/OFF在decode step1的输入/历史已不同（token序列首差在第51位）；因此不能把Stop边界后的不同分布简单称为Stop Matcher缺陷。按性能驱动开启了每Decode完整262,144词表logits捕获，外部产物约158GB；只抽取代表RID做过离线对照，未将全量捕获装入内存。
- 注意重复/因果边界：压力条件按固定16请求分波，不是可控锁步batch API；每wave内因prompt长度和输出长度不同，实际scheduler batch会变化。捕获记录的真实Forward batch_size分布为1..16。当前归因支持“C1 ON/OFF一致、并发负载存在计算/调度敏感差异”，但不能将历史81.58→67.93全部归因于batch变化。
- vLLM raw `TokensPrompt`批量输出初版按`request_id`字典序排序（`0,1,10,100...`），原driver zip造成126/128条doc输出标签错配；`prompt_len`字段亦有错误，不能用作身份凭据。初版跨引擎scores/配对全部作废。修正driver以数值request ID排序，逐条比较完整response `prompt_token_ids`与fixture后复跑通过：128/128请求ID唯一、128/128输入IDs精确一致，见外部`vllm-128-numeric-rid-verified/manifest.json`及`results.json`。
- 相同固定prompt、Stop和官方first-#### strict-match下，C1 SGLang 97/128、vLLM 99/128；配对为both-correct 97、both-wrong 29、SGLang-only 0、vLLM-only 2。Wave SGLang 99/128、vLLM 99/128；both-correct 97、both-wrong 27、SGLang-only 2、vLLM-only 2。首个数值答案相同：C1 124/128，wave 122/128。报告样本是定向抽取的64翻分+64控制，分数不代表完整测试集。
- 逐题生成：C1与vLLM的完整output token IDs相同91/128，首次输出token即分叉3例，中位common prefix 91.5；wave与vLLM相同90/128，首token分叉4例，中位prefix 91。绝大多数差异只在后续解释文本，最终首个####相同；评分分歧C1 2题、wave 4题。
- vLLM实际配置：checkpoint相同，BF16 compute，KV auto解析为BF16；G32 compressed-tensors W4A16、Triton attention、Marlin；eager、max_num_seqs=16、batch token cap 2048、无prefix/chunked prefill。SGLang实际BF16 KV、BF16 compute、W4A16 Marlin、Triton attention、无Radix，CUDA Graph decode启用至bs16。不能对齐差异：vLLM eager vs SGLang CUDA Graph decode；各自架构/调度批组成不同。未启用任何确定性Kernel。
- vLLM返回stop文本本身（`include_stop_str_in_output=True`）：Question stop 125例、EOS 3例，长度截断0例。评分只在Question边界之前取first-####；Stop后的标记不纳入答案。
- 128题score是抽样结果，不代表全量；全量已完成的本地有效Stop保护输出仍为BF16 896/1319 (67.93%)、E5M2 892/1319 (67.63%)。既有离线结论保持：旧81.58%是在未阻止下一道Question的输出上的评分，而非相同生成的suffix截断；全部历史翻分样本的保存文本在第一个Question前已不同。当前受控C1证据说明在单请求贪心下Stop ON/OFF到字符串命中处前缀一致；它不能解释历史对全量旧run的不同prefill/batching/sampler环境影响。

## 判定与限制
- 原运行缺`Question:` stop、输出继续生成后续题并触及512上限，确定是81.58%→67.93%协议变更的组成部分；但新增Stop改变了生成历史，不是对旧文本作后缀裁切。固定128例C1 Stop ON/OFF在命中前一致，并发16-wave中ON/OFF有23例于Stop边界前分叉；压力条件下确有Prefill batch大小变化。这是当前batch敏感性证据，不是历史原run schedule的复现，也未证明SGLang特有缺陷。
- 正确按request ID修复配对后，定向128例中vLLM只比SGLang多对2题（C1：97 vs 99；wave：99 vs 99）；两边首个数值答案分别有124/128和122/128相同。存在稳定、可复现的大幅SGLang特有质量退化的证据未观察到；小量逐题差异存在。跨引擎执行仍有vLLM eager与SGLang decode CUDA Graph及batch调度差异，故不将微小分差认定为Fork回归。未启用未经当前模型验证的确定性kernel。
- 不把旧13.65pp跌幅归因于Fork bug：历史runtime token IDs、全部SGLang forward batch组成及旧输出在加stop后的反事实generation缺失，stop-intervention、batch计算路径、采样/logit微差各自贡献无法分解。未重跑完整1,319题；无生产数学/容差修复。

## Git
- Scoped audit report and corrected runner commit: `PENDING`; push: `PENDING`. Only these Gemma report/runner paths may be staged; unrelated production and Falcon dirty state remain excluded.

## Artifact index
- Fixed fixture creator: `control/gemma4-e4b-rtx3090-hicache/runs/prepare_gsm8k_128_fixture.py`
- SGLang replay: `control/gemma4-e4b-rtx3090-hicache/runs/replay_gsm8k_128_controlled.py`
- vLLM replay driver (numeric request-ID ordering and fail-closed identity): `control/gemma4-e4b-rtx3090-hicache/runs/replay_gsm8k_vllm_128.py`
- SGLang results and decode logit captures: `/data/sglang-hicache/gemma4/runs/20261026T-gsm8k-stop-onoff-rerun/controlled/`
- Verified vLLM results/config: `/data/sglang-hicache/gemma4/runs/20261026T-gsm8k-stop-onoff-rerun/vllm-128-numeric-rid-verified/`
