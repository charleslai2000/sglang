# Durable efficiency sweep (`tools/perf/`)

可复用的基础性能评估 harness，用于对 M2/M3/M4（以及重跑 M1）执行**同一套**评估。
它把 M1/M2 实际使用的两个 scratch 脚本忠实固化进仓库：

- `/tmp/opencode/F39-CAMPAIGN-20260918/efficiency_sweep.py`（主脚本）
- `/tmp/opencode/M2-RCA-20260918/sweep.py`（F39 派生，唯一新增 `RCA_FLUSH=1`：
  每个 distinct level 前 `POST /flush_cache`）

指标口径在 F39/M2-RCA 原定义上做**加法式**修订（C1–C4，owner 口径 ledger §127）：
新增 TTFT/TTFC 拆分、thinking 策略冻结入 manifest、microbenchmark 标记与
agent-like 档、cache 状态结果字段；**不删除、不改名**任何既有字段。出处见
`.memory/phase2-hicache-design/agents/PERF-METRIC-SUITE-RECON-20260918.md`（`D. 指标定义`）。

R2 追加修订（owner 派单；ledger §128 不存在，以派单文本为准）：见下方
「R2 修订 A：`first_output_s` 只认模型输出」与「R2 修订 B：思考预算与
final-answer allowance 分离」。仍是**加法式**，旧字段/旧消费者不受影响。

## R2 修订 A：`first_output_ms`（`first_output_s`）只认「模型输出 delta」

`first_output_s` 与毫秒别名 `first_output_ms` 是**基础性能 TTFT**。判定由显式函数
`is_model_output_delta(delta) -> bool` 完成（`efficiency_sweep.py`）。逐字边界：

**计入（任一非空即算模型输出）**

| delta 字段 | 说明 |
| --- | --- |
| `reasoning_content` | thinking/reasoning 流 |
| `reasoning` | 兼容别名 |
| `content` | 最终回答流 |
| `tool_calls` | 工具调用流 |

**排除（不计时）**

| 情形 | 说明 |
| --- | --- |
| lifecycle SSE | `response.created`、`response.in_progress`、任何以 `response.` 开头的 `type`、`event: ping`/`keepalive`/`heartbeat` 等心跳帧 |
| 空 delta `{}` | 无任何字段 |
| 仅 role delta | 例如首个 assistant chunk `{"role":"assistant","content":""}`（`content=""`） |
| `[DONE]` | 流结束标记 |
| usage-only chunk | 只有 `usage`、无 `choices` 的帧（`include_usage`） |

`first_content_s`（**TTFC**）仍**只认** `content`，**不得**计入 reasoning。因此
reasoning-only 流的 `first_content_s`/`ttft_s` 保持 `None`，而 `first_output_s`
已置位——两者之差即 thinking 阶段对可见答案的延迟。

> `ttft_*`（legacy）= TTFC，`ttft_output_*` = R2 口径的基础 TTFT。输出 JSON 的
> `manifest.ttft_field_semantics` 逐字记录该边界。

## 指标定义（与 F39/M2-RCA 兼容并做加法）

| 指标 | 定义 | 出处 |
| --- | --- | --- |
| `ttft_output_*` | **基础性能 TTFT**：客户端收到**首个真实模型输出 delta**（`content`/`reasoning_content`/`tool_calls`；排除 lifecycle/空/role-only/usage-only/`[DONE]`，见 `is_model_output_delta`）的时刻减发送时刻 | 本文件「R2 修订 A」（C1 新增） |
| `ttfc_*` | **TTFC**：客户端收到**首个最终 content delta** 的时刻减发送时刻（要求 `stream: true`） | `efficiency_sweep.py`（recon `:93`） |
| `ttft_*`（legacy） | **= TTFC**，仅为向后兼容保留，字段语义在 `manifest.ttft_field_semantics` 显式标注；新代码请用 `ttfc_*` | 同 TTFC |
| `n_ttfc` | 计数：参与 TTFC 统计的请求数（仅 reasoning、无 final content 的请求**不计入**） | C1 新增 |
| `n_reasoning_only` | 计数：`finish_reason=length` 且最终 `content` 为空的请求（预算被 thinking 吃光） | R2 B 新增 |
| `n_truncated` | 计数：`finish_reason=length` 且最终 `content` 非空的请求（最终答案被截断） | R2 B 新增 |
| `warning` | 非 `None` 时表示该 level 有预算耗尽；stdout 同时打印 `WARNING ...` | R2 B 新增 |
| decode TPS | `completion_tokens / (dur_s - ttft_s)`，逐请求后取 p50/p90 | `efficiency_sweep.py:154`（recon `:94`） |
| aggregate TPS | `total_out_tokens / max(per-request dur_s)` | `efficiency_sweep.py:169`（recon `:95`） |
| `prompt_tokens_p50` | 每 level 的 `usage.prompt_tokens` 中位数（C4） | `efficiency_sweep.py:123`（recon `:96`） |
| `cached_tokens_p50` / `cached_tokens_mean` | 每 level 的 `usage.prompt_tokens_details.cached_tokens` 中位/均值（C4） | 同 cache 命中（recon `:96`） |
| `newly_prefilled_tokens_p50` | `prompt_tokens - cached_tokens` 的中位数（C4） | C4 新增 |
| `hit_rate_mean` | `cached_tokens / prompt_tokens` 的均值（C4） | C4 新增 |
| prompt/completion tokens | OpenAI `usage.prompt_tokens` / `usage.completion_tokens` | `efficiency_sweep.py:121-122` |

> **TTFT 语义拆分（C1/R2-A）**：`ttft_output_*` 是基础性能口径（首个真实模型
> 输出即计时，含 thinking/reasoning，但排除 lifecycle/空/role-only/usage-only
> 帧）；`ttfc_*` 是最终答案口径。旧 `ttft_*` 等于 TTFC，保留以避免破坏既有
> 消费者（如 `scorecard.py` 只读字段子集）。所有输出 JSON 的 `manifest` 都会带
> `ttft_field_semantics` 说明。

## R2 修订 B：思考预算与 final-answer allowance 分离

SGLang 对 chat 请求只有**一个总上限**（`protocol.py:855` `max_tokens` 已弃用 /
`:860-863` `max_completion_tokens` **同时覆盖 reasoning + 可见输出**），因此客户端
必须显式区分「思考预算」与「最终答案配额」，否则会静默截断：

- `--out-tokens <n>`：**final-answer allowance**（最终答案配额），写入 manifest 的
  `max_output_tokens`；legacy 键 `max_tokens` 仍等于它。
- `--thinking-budget <n>`：思考/reasoning 预算，经 `custom_params={"thinking_budget": n}`
  发送（服务端读取点：`constrained/grammar_manager.py:117-129`、
  `sampling/custom_logit_processor.py:85,107,118`）。默认 `None` = 用服务端策略。
- `--max-tokens-total <n>`：实际发送到线路的单次总上限 `max_tokens`；默认 =
  `--out-tokens`。manifest 的 `max_tokens_total_relation` 明说它是**合并上限**。

**agent-like fail-closed**：当 `--thinking-budget` 给出且
`--workload-kind agent-like` 时，必须满足

```text
max_tokens_total >= thinking_budget + out_tokens
```

否则 harness **在发出任何请求之前**打印 `FAIL-CLOSED: ...` 到 stderr 并
`exit 2`，绝不静默截断。micro 档维持现状（不强制该不等式）。

**预算耗尽检测**：每 level 新增 `n_reasoning_only`（`finish_reason=length` 且
`content` 空，即思考吃光预算、从未产出答案）与 `n_truncated`（`finish_reason=length`
且 `content` 非空，即答案被截断）。任一 `>0` 时该 level 的 `warning` 非 `None`
且 stdout/stderr 打印 `WARNING BUDGET EXHAUSTION: ...`。此时该 level 的
`ttfc_*`/`decode_tps` 不是有效的最终答案测量。

**effective policy 冻结**：manifest 的 `effective_policy` 记录
`reasoning_effort`/`thinking`/`thinking_budget`/`max_output_tokens`/`max_tokens_total`、
解析后的 `resolved_tier` 与 `resolved_budget_from_ladder`、`server_refs`（file:line 来源，
如 `parser/qwen35_reasoning_policy.py:86-122`、`serving_chat.py:2653-2695`）。客户端无法
观测服务端最终生效策略时，`effective_source=unknown`，**绝不伪造数值**；能由请求形态
与本地策略模块解析时标 `effective_source=assumed`。

`aggregate_tps` 与规范 `PERFORMANCE-BASELINE-SPEC-v2` 的
`aggregate_output_tps = output_tokens / wall_time` **不同**；F39 使用
`total_out / max(per-request dur)` 并自述该列**只可作相对量**读取
（recon `:95`，`agents/F39-M2-WINDOW-CAMPAIGN-20260918.md:350-353`）。本 harness
保持 F39 口径，**不**改成规范口径。

## 默认协议（与 F39 一致）

- `--levels 1,2,4,8`，`--count-per-level 16`
- **workload kind（C3）**：`--workload-kind micro`（默认）沿用 `--out-tokens 64`
  的 legacy microbenchmark 协议；`--workload-kind agent-like` 使用真实长前缀
  （`--prefix-tokens`，默认 2048）、正常 EOS（`ignore_eos=false`）、典型输出
  `--out-tokens 256`（可 512）。
  - micro 结果**不具 agent 代表性**，manifest 的 `workload_kind_note` 会显式提示。
- 生成参数：`temperature=0.0`、`stream=true`、`stream_options.include_usage=true`；
  `ignore_eos` 由 workload kind 决定（micro=true，agent-like=false）。
- reasoning/thinking 策略（C2）：`--reasoning-effort <none|low|medium|high|...>`、
  `--thinking <on|off>` 逐请求发送并写入 manifest；不传则维持 legacy 形态
  （不发送 `reasoning_effort`、沿用既有 thinking 默认）。**同一次跨角色比较必须
  使用相同策略**，manifest 会冻结该值以供核验。R2 B 另加 `--thinking-budget`
  与总上限 `--max-tokens-total`，见「R2 修订 B」。
- `--seed`：可选采样 seed，仅记录在 manifest（给出时才发送）。
- 两个 case：
  - `distinct`（`distinct-noreuse`）：每个 index 唯一长 prompt，真冷；
  - `shared`（`shared-prefix-reuse`）：复用同一长前缀；测量批前先发 1 个
    warm-up 请求以填充 radix cache（`efficiency_sweep.py:133-135`）。
- **cache 状态（C4）**：`--cache-state {cold-distinct,warm-shared,warm-distinct}`
  是**显式的 operator 声明**，写入 manifest 与每个 level。未给出时按 case 推导
  （distinct→cold-distinct，shared→warm-shared）。**`--flush` 只表示“发过
  flush 机制”，不等于冷**；需要冷态请在命令行显式声明 `--cache-state`。
  > agent-like 档所有请求复用**同一** prefix，因此 case 推导的 `distinct` 默认
  > 在 agent-like 下可能不等于真实冷态；跑 agent-like 时应**显式**传
  > `--cache-state warm-shared`（或真实状态），不要依赖 case 推导。
- `--flush`（默认关）：开启后每个 **distinct** level 前 `POST /flush_cache`，
  对应 M2-RCA 的 `RCA_FLUSH=1`。
- `--max-running-requests` 仅写入 output config，不驱动负载。
- 输出 JSON 结构保持与 `efficiency-{m1,m2}.json` 兼容：`config` + `levels[]`，
  并新增顶层 `manifest`（C2）。新增 level 字段均为加法，旧消费者仍可读。

## 用法

```bash
# 对某个角色跑评估（示例：M3，GGUF 路径作为 --model）
python3 tools/perf/efficiency_sweep.py \
  --tag m3 \
  --url http://127.0.0.1:30000/v1/chat/completions \
  --model /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf

# M4
python3 tools/perf/efficiency_sweep.py \
  --tag m4 \
  --url http://127.0.0.1:30000/v1/chat/completions \
  --model /data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf

# 只跑一个 case、开 flush、自定义 levels 与输出
python3 tools/perf/efficiency_sweep.py \
  --tag m2-rca --url http://127.0.0.1:30000/v1/chat/completions \
  --model omnicoder-9b-gptq-int4 --mode distinct --flush \
  --levels 1,2,4,8 --count-per-level 16 --outfile /tmp/opencode/efficiency-m2-rca.json

# agent-like 档（真实长前缀 + 正常 EOS + reasoning 策略冻结）
python3 tools/perf/efficiency_sweep.py \
  --tag m3-agent --url http://127.0.0.1:30000/v1/chat/completions \
  --model /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --workload-kind agent-like --prefix-tokens 2048 --out-tokens 256 \
  --reasoning-effort medium --thinking on \
  --thinking-budget 2048 --max-tokens-total 4096 \
  --cache-state warm-shared --seed 42 \
  --server-argv "sglang serve --model ... --enable-radix-cache"

# 结构一致性自检（只读，不发请求；接受 legacy 19 / R1 33 / R2 36 字段）
python3 tools/perf/efficiency_sweep.py --self-check efficiency-m2.json
```

退出码：所有 level `n_err == 0` 时为 0；任一请求失败时为 1；agent-like 的
思考预算/总上限不满足 `max_tokens_total >= thinking_budget + out_tokens` 时为 2
（fail-closed，发出任何请求之前）。连接/协议错误按请求记入 `n_err`（fail-closed），
不会静默重试或挂死。若需把该角色与 F39 的 `efficiency-{m1,m2}.json` 对比，请使用
相同 `--levels`/`--count-per-level`/`--out-tokens` 并保持相同 case 与 flush 设定。

## manifest（C2，跨角色可比性的冻结快照）

每次运行都会把下列字段写入输出 JSON 顶层的 `manifest` 段**并打印到 stdout**
（前缀 `MANIFEST `）：`model`、`server_argv`、`reasoning_effort`、`thinking`、
`max_tokens`（= final-answer allowance）、`ignore_eos`、`mode`、`levels`、
`count_per_level`、`prompt_chars`、`seed`、`workload_kind`、`cache_state`/
`cache_states`、`url`、`generated_utc`，以及 `ttft_field_semantics`/
`workload_kind_note` 口径说明。

R2 追加的冻结字段：`thinking_budget`、`max_output_tokens`、`max_tokens_total`、
`max_tokens_total_relation`、`effective_policy`（含 `resolved_tier`、
`resolved_budget_from_ladder`、`server_refs`）、`effective_source`
（`assumed`|`unknown`）。比较两个角色的结果前，先核对 manifest 的
workload/reasoning/thinking-budget/cache 四项是否一致。

## 可比性声明

- **aggregate TPS 为相对量**（F39 口径），只在同一 harness、同一 levels 下比较。
- **M1/M2 为不同模型、不同配置，不可直接 apples-to-apples**
  （recon `:105`；`agents/F39-M2-WINDOW-CAMPAIGN-20260918.md:135-139`）。
  M1=`qwen35-9b-w4a16`，M2=`omnicoder-9b-gptq-int4`。跨角色比较前必须记录
  server argv（`--server-argv`）与模型身份。
- F39/M2-RCA 每 cell 16 请求，低于 `P2B0-EXECUTION-CONTRACT-20260912.md` 的
  `>=40`（recon `:108`），因此结果只够做相对比较；需要规范性结论时应增大
  `--count-per-level`。
- 本 harness 只用既有 HTTP 端点与响应字段，**不新增观测机制**。
