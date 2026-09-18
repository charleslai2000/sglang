# REASONING-EFFORT-TIERS-AUDIT-20260918

- **Task:** Focused re-review of the **graded `reasoning_effort` tiers (分档)** advertised by the served SGLang deployment — does a real grading mechanism exist anywhere, why do the advertised tiers not take effect, and what is the smallest repair direction?
- **Role:** `debugger-deep` (non-worker; read-only wrt server and product code; bounded read-only requests only)
- **Target (live):** `/data/models/omnicoder-9b-gptq-int4` served by SGLang on `127.0.0.1:30000` (M2, Qwen3.5-derived, `model_type=qwen3_5`, `architectures=[Qwen3_5ForConditionalGeneration]`)
- **Served tree:** `/opt/sglang/local-prod-v1.2.1-candidate` (frozen, read-only)
- **Prior baseline built upon (not redone):** `.memory/phase2-hicache-design/agents/M2-THINKING-VERIFY-20260918.md`, `.memory/phase2-hicache-design/agents/SGLANG-REASONING-CONTROL-AUDIT-20260918.md`
- **Result artifact path (this file):** `.memory/phase2-hicache-design/agents/REASONING-EFFORT-TIERS-AUDIT-20260918.md`
- **Terminal state: DONE**

---

## Scope

1. Where `reasoning_effort` (and related effort/budget/thinking keys) is declared, advertised, read, normalized, translated, forwarded, or silently dropped in the served code.
2. Whether an intended graded path exists but is unwired — template variables, parser, sampler/scheduler.
3. Bounded runtime confirmation on `:30000`: do any advertised tiers or floats change anything at all?
4. One primary classification (A–E) + smallest repair direction (not implemented).
5. Two-arm consistency (M1 static; runtime explicitly pending).

**Hard limits honoured:** no product/server/git/ledger modification; no restart/stop/signal; port 30000 touched only via bounded read-only `POST /v1/chat/completions` and `/v1/tokenize`; **21 completions** and **11 tokenize renders**, all `temperature=0`, `max_tokens<=512`, total wall time ~90 s; all scratch under `/tmp/opencode/REASONING-EFFORT-TIERS-20260918/`.

---

## Result (short)

**A real graded-effort mechanism EXISTS in the served code — but only for OTHER model families, and it is selected by the chat template / chat-encoding spec, not by the API surface.** The served `protocol.py` advertises `reasoning_effort` as string tiers plus a fine-grained float `[0.0, 0.99]` **unconditionally for every model** (`protocol.py:793-808, 869-881`, and served `/openapi.json`). For the served Qwen3.5 model, the value is correctly parsed, normalized, and **forwarded into `apply_chat_template`**, but the model's template (`chat_template.jinja:149`) references **only `enable_thinking`** and never `reasoning_effort`, `thinking_budget`, `low_effort`, or any graded variable. Detected config is `ReasoningToggleConfig(toggle_param='enable_thinking', default_enabled=True, special_case=None, effort_kwarg=None)`, so the one generic graded branch (`serving_chat.py:1364-1373`) is dead. **Runtime result: every advertised tier (`minimal/low/medium/high/xhigh/max`) and every float (`0.0`, `0.25`, `0.99`) is byte-for-byte identical to baseline** (same full `content` SHA, same full `reasoning_content` SHA, same 177 completion / 174 reasoning tokens), and the render-level `/v1/tokenize` prefill is token-identical. Only `"none"` changes anything, by collapsing to the existing on/off toggle. A genuine length-budget mechanism (`max_thinking_tokens` → `custom_params.thinking_budget` → `ThinkingBudgetLogitProcessor`) also exists in-tree, but it is **not exposed on the chat request, not connected to `reasoning_effort`, disabled on this server (`--enable-strict-thinking` absent), and its `Qwen3ThinkingBudgetLogitProcessor` uses token IDs (151667/151668) that do not match this model's `<think>`/`</think>` (248068/248069).** Verdict: **inert graded control / template gap**, not merely an on/off switch.

---

## Evidence

### E0. Served revision / identity (FACT)

```
$ cat /opt/sglang/local-prod-v1.2.1-candidate/manifest/identity-pins.json
{
  "SOURCE_COMMIT": "b2bbd6ea28",
  "TREE_HASH": "5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950",
  "identity": "LOCAL-PROD-v1.2.1",
  ...
}
```

`GET /get_server_info` (`ev_server_info.json`, HTTP 200) selected fields:

```json
{
  "model_path": "/data/models/omnicoder-9b-gptq-int4",
  "reasoning_parser": "qwen3",
  "tool_call_parser": "qwen3_coder",
  "enable_strict_thinking": false,
  "enable_custom_logit_processor": false,
  "version": "0.5.20.dev22+g9c9e7b7c7"
}
```

`/get_server_info` has **507 keys and contains no `reasoning_effort` key** and no capability/effort-tier advertisement field (checked programmatically). The only thinking-related keys are `strip_thinking_cache`, `enable_strict_thinking`, `speculative_ngram_external_sam_budget`.

Audited file hashes match `manifest/TREE-SHA256.txt` byte-for-byte:

```
a7cf91c1db5d076b9ad647248351f10b0249153998b974ed4d00610306b01653  src/python/sglang/srt/entrypoints/openai/protocol.py
7b05e6ab1d09a71ce253040c9cd62ea7c55a52020b44cf9b76d91c8df9e23240  src/python/sglang/srt/entrypoints/openai/serving_chat.py
041cb3b9030154f39bd30e80ccf95bbe3b5014d6baa9e2132599bad5d636d2e5  src/python/sglang/srt/parser/template_detection.py
e0e0ab65e2ded8975a9d161a52c92cb61f2a8a02a6af485b37912cad1171e23d  src/python/sglang/srt/sampling/custom_logit_processor.py
9f9d38028008c7f6afe9dc58508ab9e84eb981462beff79e8f874283f69ddf46  src/python/sglang/srt/managers/tokenizer_manager.py
```

---

### E1. Section 1 — What is advertised, and where it is consumed

**Advertised contract (server code, served at runtime):**

- `protocol.py:791-808` — the type declaration and an inline comment that explicitly frames the float as an SGLang extension:
  ```python
  # OpenAI-spec string tiers for reasoning effort (current Responses/Chat API):
  # none/minimal/low/medium/high/xhigh/max. Used as-is by /v1/responses.
  ReasoningEffortTier = Literal[
      "none", "minimal", "low", "medium", "high", "xhigh", "max"
  ]
  ...
  # Chat Completions and /v1/tokenize additionally accept a fine-grained float in
  # [0.0, 0.99] as an sglang extension (not part of the OpenAI schema, so the
  # /v1/responses surface deliberately keeps the string tiers only). Single-sourced
  # so these surfaces cannot drift apart.
  ReasoningEffortType = Optional[
      Union[
          ReasoningEffortTier,
          Annotated[float, Field(ge=0.0, le=0.99, allow_inf_nan=False)],
      ]
  ]
  ```
- `protocol.py:869-881` — the field description served to callers:
  ```python
  reasoning_effort: ReasoningEffortType = Field(
      default=None,
      description="Constrains effort on reasoning for reasoning models. "
      "Accepts string levels ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max') or a "
      "float in [0.0, 0.99] for fine-grained control. "
      "'none' disables reasoning entirely, 'low' is the least effort, 'high' is the most effort. "
      "Reducing reasoning effort can result in faster responses and fewer tokens used on reasoning "
      "in a response. 'none' defaults thinking and enable_thinking to false in "
      "chat_template_kwargs (unless explicitly overridden). Not supported in the harmony path."
      "'max' is an sglang extension to the OpenAI schema for "
      "models that expose a maximum-effort tier above 'high'; models that don't "
      "support it treat it the same as 'high'.",
  )
  ```
- **Served live** in `GET /openapi.json` (`ev_openapi.json`) as the `ChatCompletionRequest.reasoning_effort` schema, verbatim:
  ```json
  {
    "anyOf": [
      {"type": "string", "enum": ["none","minimal","low","medium","high","xhigh","max"]},
      {"type": "number", "maximum": 0.99, "minimum": 0.0},
      {"type": "null"}
    ],
    "title": "Reasoning Effort",
    "description": "Constrains effort on reasoning for reasoning models. Accepts string levels ... or a float in [0.0, 0.99] for fine-grained control. ... 'max' is an sglang extension ... models that don't support it treat it the same as 'high'."
  }
  ```
- `/v1/responses` advertises only the string tiers by design; `/v1/tokenize` also accepts `reasoning_effort` (`protocol.py:1456`).

**Every place `reasoning_effort` is read / translated / forwarded / dropped (served tree):**

| Site | Behaviour |
|---|---|
| `protocol.py:976-981` | Rejects boolean effort. |
| `protocol.py:983-1023` | Nested `reasoning={"effort": ...}` → top-level; only truthy `enabled` sets `thinking=True` (false `enabled` is a no-op). |
| `protocol.py:1025-1038` | **The only generic materialization:** `thinking = (effort != "none")`, then sets ctk `thinking`/`enable_thinking` via `setdefault`. Any non-`none` value (including every tier and every float) becomes `enable_thinking=True`. |
| `serving_chat.py:966-982` | Pops `chat_template_kwargs.reasoning_effort` into `request.reasoning_effort` **after validators**, so ctk placement skips the materialization. |
| `serving_chat.py:1100-1111` | Mirrors default-chat-template-kwargs effort into `request.reasoning_effort`. |
| `serving_chat.py:1357-1361` | **Forwards** `{"reasoning_effort": <value>}` into `apply_chat_template` kwargs, then merges ctk. |
| `serving_chat.py:1363-1373` | Generic graded branch — **only active if `rc.effort_kwarg is not None`**; sets `effort_kwarg=True` for `"low"` and warns for `medium/high/max`. Dead for this model. |
| `serving_chat.py:2430-2506` | `_get_reasoning_from_request`: for this config returns on/off only (`enable_thinking is not False`). No gradation. |
| `serving_chat.py:505-546` | **Inkling** float path — real gradation, gated by `chat_encoding_spec == "inkling"`. |
| `serving_chat.py:547-575` | **Kimi K3** sets `template_kwargs["thinking_effort"]` for `low/high/max`, gated by `chat_encoding_spec == "kimi_k3"`. |
| `serving_chat.py:638-684` | `_parse_inkling_reasoning_effort` consumes a float/tier → Inkling 0.0–0.99. |
| `serving_chat.py:1294-1318` | **dsv4** consumes `reasoning_effort` into `encoding_dsv4.encode_messages` prompt templates. |
| `harmony_utils.py:74-85` | gpt-oss/harmony consumes tiers into a system message effort. |
| `serving_responses.py:1280-1298` | `/v1/responses` + harmony consumes effort. |

**Registration / advertisement on API surfaces:** `reasoning_effort` is advertised purely by the generic request schema (`protocol.py` + generated `/openapi.json`). `/get_server_info` does **not** advertise any effort capability. `--reasoning-parser` is advertised via dynamic `DetectorMap` choices (`server_args.py:9999-10007`); the `qwen3` parser is advertised and wired, but it consumes no effort/budget (see E3).

---

### E2. Section 2 — Is there a real grading path anywhere?

**Yes — but model-gated, not generic; none is reachable for the served Qwen3.5 template.**

1. **Generic template-variable grading exists but requires a template that declares it.**
   `template_detection.py:66-70` defines `effort_kwarg: Optional[str] = None`; `template_detection.py:178-187` sets `effort_kwarg="low_effort"` only for the **nemotron_3 super** rule (requires `low_effort` + `truncate_history_thinking`); `template_detection.py:161-165` defines a **mistral** `special_case`. `serving_chat.py:1364-1366` then does `extra_template_kwargs.setdefault(rc.effort_kwarg, True)` for `"low"`. For the served model `rc.effort_kwarg is None`, so this is dead.

2. **Model-specific graded paths exist** (Inkling float, Kimi K3 `thinking_effort`, dsv4 prompt profile, harmony system effort) — all selected by `chat_encoding_spec` / `tool_call_parser` / model architecture, **not** by a generic capability check. `resolve_chat_encoding_spec` (`chat_encoding.py:113-150`) returns `None` for `Qwen3_5ForConditionalGeneration` with a chat template, so none of these apply.

3. **A genuine thinking-length budget mechanism exists** (`ThinkingBudgetLogitProcessor`):
   - `io_struct.py:302` — `max_thinking_tokens: Optional[int]`.
   - `tokenizer_manager.py:781-789` — **raises unless the server was launched with `--enable-strict-thinking`**.
   - `tokenizer_manager.py:1357-1361` — maps `max_thinking_tokens` → `custom_params["thinking_budget"]`.
   - `custom_logit_processor.py:71-152` — `ThinkingBudgetLogitProcessor` and subclasses (GLM, **Qwen3**, DeepSeek-R1, Inkling); the processor forces `</think>` after N tokens.
   - `grammar_manager.py:117-129,170-177,287` — applies the budget to the strict-thinking grammar object.
   - **Reachability today:** `custom_params` **is** an accepted chat-request field (`protocol.py:922`, forwarded at `protocol.py:1120`). But (a) the served argv has **no `--enable-strict-thinking`**, so `max_thinking_tokens` is not reachable; (b) `enable_custom_logit_processor=false`, so supplying a processor is 400; (c) **there is no code path mapping `reasoning_effort` → `max_thinking_tokens`** (`grep` returns no such mapping); (d) the only enabled path for `custom_params` (`elif self._enable_strict_thinking:` at `grammar_manager.py:171`) is off. Even if forced, `Qwen3ThinkingBudgetLogitProcessor.THINKING_START/END_TOKEN_ID = 151667/151668` (`custom_logit_processor.py:134-135`) do not match this model's `<think>`/`</think>` token IDs, verified with the served tokenizer:
     ```
     248068 -> '<think>'
     248069 -> '</think>'
     151667 -> '็ม'          # not a think marker on this model
     151668 -> 'خبار'
     200008 -> ' ярко'
     200010 -> 'ществи'
     198    -> '\n'
     ```
     So the Qwen3 budget processor is a **no-op on this model even if enabled**.

4. **Template variables (served model)** — `chat_template.jinja` references exactly one control variable:
   ```jinja
   147: {%- if add_generation_prompt %}
   148:     {{- '<|im_start|>assistant\n' }}
   149:     {%- if enable_thinking is defined and enable_thinking is false %}
   150:         {{- '<think>\n\n</think>\n\n' }}
   151:     {%- else %}
   152:         {{- '<think>\n' }}
   153:     {%- endif %}
   154: {%- endif %}
   ```
   `grep -nE "reasoning_effort|thinking_budget|max_thinking|low_effort|thinking_effort|effort|budget"` over the full file returns **only** the `enable_thinking` line 149. `tokenizer_config.json` embeds **no** `chat_template` key (815 bytes of tokenizer metadata only); the server loads the Jinja file from disk. **Definitive: the template is a boolean toggle and nothing more.** This is "template does not declare any graded variable" — **not** "declares it but nothing passes it."

5. **Reasoning parser (`qwen3`)** is purely a `<think>`/`</think>` splitter:
   - `reasoning_parser.py:355-399` — `Qwen3Detector.__init__` accepts only `stream_reasoning`, `force_reasoning`, `continue_final_message`, `previous_content`, `force_nonempty_content`; no effort/budget parameter.
   - `reasoning_parser.py:1978-2008` — request kwargs consumed are only `thinking_mode` (minimax-m3) and `force_nonempty_content`; no Qwen3.5 effort.
   - The only `reasoning_effort` mentions in the parser are documentation strings for unrelated detectors (`reasoning_parser.py:937-938`).

6. **Float `[0.0, 0.99]` consumption:** the only numeric consumers are Inkling (`serving_chat.py:638-684`, `inkling_renderer.py:250-257`) and dsv4 profile prompt selection. Neither is reachable for this model. The generic path treats a float as `effort != "none"` → `enable_thinking=True` (`protocol.py:1027`), i.e. **the float is consumed by no reachable code and is discarded.**

7. **Tests** confirm the intended model-gating: `test_serving_chat.py:3029-3076` covers `effort_kwarg="low_effort"` (nemotron) only; `test_serving_chat.py:3540-3653` covers Inkling floats; `test_template_manager.py:680-684` uses a template that explicitly declares `reasoning_effort`. There is **no test asserting graded behavior for a template without an effort variable**, consistent with "no-op when absent".

---

### E3. Section 3 — Runtime confirmation on the live arm (bounded, `temperature=0`)

Harness: `probe.py` (21 completions across 3 request shapes + 11 render-level tokenize calls), `compare.py` (byte-identity + range negative), `render_probe.py` (CPU render). Raw responses under `/tmp/opencode/REASONING-EFFORT-TIERS-20260918/raw/`, summaries in `completions_summary.json` / `tokenize_summary.json`, console logs `probe.out` / `compare.out` / `render_probe.out`.

Base P1: `What is 2+2? Answer with just the number.` — `{"model":"/data/models/omnicoder-9b-gptq-int4","temperature":0,"max_tokens":512, <extra>}`.

#### Advertised-tier table

| Tier / value | Request placement | HTTP | completion / reasoning | reasoning_content SHA (8) | Verdict |
|---|---|---|---|---|---|
| (baseline, no control) | — | 200 | 177 / 174 | `dd763cff` | reasoning ON |
| `none` | top-level | 200 | 2 / 0 | `e3b0c442` (empty) | **HONORED — on/off only** |
| `minimal` | top-level | 200 | 177 / 174 | `dd763cff` | **INERT** (byte-identical) |
| `low` | top-level | 200 | 177 / 174 | `dd763cff` | **INERT** |
| `medium` | top-level | 200 | 177 / 174 | `dd763cff` | **INERT** |
| `high` | top-level | 200 | 177 / 174 | `dd763cff` | **INERT** |
| `xhigh` | top-level | 200 | 177 / 174 | `dd763cff` | **INERT** |
| `max` | top-level | 200 | 177 / 174 | `dd763cff` | **INERT** |
| `0.0` (float) | top-level | 200 | 177 / 174 | `dd763cff` | **INERT** |
| `0.25` (float) | top-level | 200 | 177 / 174 | `dd763cff` | **INERT** |
| `0.99` (float) | top-level | 200 | 177 / 174 | `dd763cff` | **INERT** |
| ctk `enable_thinking=false` (positive control) | `chat_template_kwargs` | 200 | 2 / 0 | `e3b0c442` | **HONORED** |
| `custom_params={"thinking_budget":5}` | top-level | 200 | 177 / 174 | `dd763cff` | **INERT** (silently ignored) |
| `max_thinking_tokens=5` | top-level | 200 | 177 / 174 | `dd763cff` | **INERT** (field dropped: no `extra="allow"`) |
| ctk `{"thinking_budget":5}` | `chat_template_kwargs` | 200 | 177 / 174 | `dd763cff` | **INERT** |

Content SHA was identical (`3e9114b6`) for **all 12** graded/budget variants and differed only for the positive control. Cross-check on P5 (`A train travels...`): baseline 299/294, `reasoning_effort="high"` 299/294 — complete response SHA-identical; positive control 4/0. Negative checks in E4.

Verbatim baseline vs `high` (raw files `raw/cc_00_baseline_P1.json`, `raw/cc_effort_high_P1.json`): the two responses differ **only** in `id`/`created`; `content` (`"\n\n4"`), the entire `reasoning_content`, `finish_reason`, `matched_stop`, and `usage` are identical:

```json
"usage": {"prompt_tokens": 23, "total_tokens": 200, "completion_tokens": 177,
          "prompt_tokens_details": null, "reasoning_tokens": 174}
```

Verbatim honored `none` (`raw/cc_effort_none_P1.json`):

```json
{"choices":[{"index":0,"message":{"role":"assistant","content":"4","reasoning_content":null,"tool_calls":null},
 "finish_reason":"stop","matched_stop":248046}],
 "usage":{"prompt_tokens":25,"total_tokens":27,"completion_tokens":2,"prompt_tokens_details":null,"reasoning_tokens":0}}
```

#### Render-level proof (`/v1/tokenize`, no generation)

`/v1/tokenize` runs the same `_process_messages`/`apply_chat_template` path. Every graded tier/float produced the **identical 17-token prefill** as default; only `none` / ctk `enable_thinking=false` changed it to a closed empty think block:

```
TOK_default       http=200 count=17 tail=[198, 248045, 74455, 198, 248068, 198]   # ...<think>\n
TOK_effort_minimal http=200 count=17 tail=[198, 248045, 74455, 198, 248068, 198]  # identical to default
TOK_effort_low     ... count=17 ... identical
TOK_effort_medium  ... count=17 ... identical
TOK_effort_high    ... count=17 ... identical
TOK_effort_xhigh   ... count=17 ... identical
TOK_effort_max     ... count=17 ... identical
TOK_effort_float_0_0 ... count=17 ... identical
TOK_effort_float_0_99 ... count=17 ... identical
TOK_effort_none    http=200 count=19 tail=[74455, 198, 248068, 271, 248069, 271]  # <think>\n\n</think>\n\n
TOK_ctk_false      http=200 count=19 tail=[74455, 198, 248068, 271, 248069, 271]  # <think>\n\n</think>\n\n
```

#### CPU render probe — the plumbing DOES pass the value; the template ignores it

`render_probe.py` reproduces `serving_chat.py:1357-1393` semantics (`apply_chat_template(..., **extra_template_kwargs)`) for both model dirs:

```
MODEL: /data/models/omnicoder-9b-gptq-int4
chat_template sha256: a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715
template references 'reasoning_effort': False
template references 'thinking_budget': False
template references 'low_effort': False
template references 'enable_thinking': True
  reasoning_effort=minimal  identical_to_baseline=True
  reasoning_effort=low      identical_to_baseline=True
  reasoning_effort=medium   identical_to_baseline=True
  reasoning_effort=high     identical_to_baseline=True
  reasoning_effort=max      identical_to_baseline=True
  reasoning_effort=0.0      identical_to_baseline=True
  reasoning_effort=0.25     identical_to_baseline=True
  reasoning_effort=0.99     identical_to_baseline=True
  enable_thinking=False     identical_to_baseline=False  tail='|im_start|>assistant\n<think>\n\n</think>\n\n'
```

(This distinguishes the two cases required by the task: the template **does not declare** a graded variable, so the value is forwarded and ignored — not "declared but nothing passes it.")

---

### E4. Negative self-checks (real output)

1. **Bogus tier rejected — HTTP 400** (`raw/cc_neg_bogus_P1.json`):
   ```
   {'type': 'literal_error', 'loc': ('body','reasoning_effort', "literal['none','minimal','low','medium','high','xhigh','max']"),
    'msg': "Input should be 'none', 'minimal', 'low', 'medium', 'high', 'xhigh' or 'max'", 'input': 'banana', ...}
   {'type': 'float_parsing', 'loc': ('body','reasoning_effort','constrained-float'), ...}
   ```
2. **Out-of-range float rejected — HTTP 400** (`neg_out_of_range_1_5.json`), proving the numeric range is enforced (not silently coerced):
   ```
   {'type': 'less_than_equal', 'loc': ('body','reasoning_effort','constrained-float'),
    'msg': 'Input should be less than or equal to 0.99', 'input': 1.5, 'ctx': {'le': 0.99}}
   ```
3. **Budget mechanism is gated — HTTP 400** (`neg_custom_logit_processor.json`): supplying a custom processor alongside `custom_params={"thinking_budget":5}` returns
   ```
   "The server is not configured to enable custom logit processor. Please set `--enable-custom-logit-processor` to enable this feature."
   ```
   while `custom_params={"thinking_budget":5}` **alone** returns HTTP 200 and is silently ignored (177/174) — a fail-silent negative.
4. **Positive/negative contrast is decisive:** `"none"` and ctk `enable_thinking=false` → 0 reasoning; every graded tier/float → byte-identical baseline; invalid effort → 400. The field is parsed and enforced at the boundary, then carries no gradation.

---

## Primary classification

**(B) Template gap — the graded mechanism exists upstream in the served code, but this model's chat template lacks the variable.**

Justification and why the alternatives are rejected as *primary*:

- **Not (A) advertised-but-unimplemented in the vaporware sense.** A real grading mechanism exists and is exercised elsewhere in the same tree: the generic `effort_kwarg` branch (`serving_chat.py:1364-1366`, used by nemotron `low_effort`), the Inkling float renderer, Kimi K3 `thinking_effort`, dsv4 effort prompts, and the `ThinkingBudgetLogitProcessor` budget. So grading is implemented — it is simply **not selected for this model**.
- **Not (C) configuration/wiring gap as the primary cause.** The request value **is** parsed, normalized, and forwarded all the way into `apply_chat_template` (E2/E3 render probe). The wire is connected; the endpoint ignores it. The `--enable-strict-thinking`/custom-logit configuration gap is a *separate, independent* defect (it blocks a different, also-unconnected budget mechanism), not the cause of inert tiers.
- **Not (D) intended behavior.** Nothing marks the tiers as deliberately no-op for this model: the server advertises all tiers and the float unconditionally (schema + description + live `/openapi.json`), returns 200 for all of them, and warns only inside the `effort_kwarg`-present branch. There is no model-gating signal to the caller.
- **The qualification (a real, secondary defect):** the advertisement is a **generic, unconditional contract** (`protocol.py:869-881`) that is false for this model. This is an **A-flavoured contract-clarity defect** layered on top of the B root cause. It is not the mechanism question the owner asked, but it is the reason callers believe grading works. Recorded under Defects.

---

## Minimal repair direction (NOT implemented)

Two distinct items, separated as required:

**Smallest change that would make the advertised contract TRUE (contract/advertisement layer):**
Capability-gate the advertisement. In `protocol.py` (and therefore generated `/openapi.json`), describe/suppress the graded tiers and the `[0.0, 0.99]` float when the resolved `ReasoningToggleConfig.effort_kwarg is None` **and** no model-specific effort path (`chat_encoding_spec` / parser) applies — i.e., advertise only `none` and the on/off semantics that actually exist. This is the smallest change that removes the false promise without touching model behavior. It is a server-code/contract edit, requires a restart to take effect, and makes the contract honest rather than making grading work.

**What would be required to make gradation actually FUNCTION (not minimal; larger and partly out of server control):**
The consumer must exist at the **model/template layer**: the `chat_template.jinja` would need a graded branch keyed on a variable the server already forwards (`reasoning_effort` is already passed at `serving_chat.py:1358-1361`) or on a declared effort kwarg, and the model must have been trained to respond to that cue (a bare template conditional cannot synthesize graded behavior the weights were not trained for). If the intent is a hard length budget rather than a soft cue, the smallest functional route is: map `reasoning_effort` → `max_thinking_tokens`, launch with `--enable-strict-thinking` (and `--enable-custom-logit-processor` if the processor route is used), and use a `ThinkingBudgetLogitProcessor` whose start/end token IDs match **this** model (`248068`/`248069`, not the shipped Qwen3 constants `151667`/`151668`). Each of these is a separate authorization/restart and a design decision, not a diagnostic fix, and should be dispatched separately.

**Merely desirable (explicitly NOT the minimum and NOT requested):** accepting top-level `enable_thinking`, reconciling the ctk-vs-top-level `reasoning_effort` placement asymmetry, and making a false `reasoning={"enabled": false}` disable reasoning. These are pre-existing documented defects; none makes the graded tiers functional.

---

## Two-arm consistency

- **FACT (static, this audit):** M1 `/data/models/qwen35-9b-w4a16/chat_template.jinja` and M2 `/data/models/omnicoder-9b-gptq-int4/chat_template.jinja` are **byte-identical** (`sha256 a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715`, `diff` → identical, 7756 bytes). Neither `tokenizer_config.json` embeds a `chat_template`; neither `config.json` contains any reasoning/thinking/effort/budget key; M1's README has no effort mentions.
- **FACT (static, this audit):** detection run through the frozen tree for both arms yields identical results:
  ```
  MODEL /data/models/omnicoder-9b-gptq-int4
    force_reasoning= False
    reasoning_config= ReasoningToggleConfig(toggle_param='enable_thinking', default_enabled=True, special_case=None, effort_kwarg=None)
    reasoning_parser= qwen3   tool_call_parser= qwen3_coder   effort_kwarg= None
  MODEL /data/models/qwen35-9b-w4a16
    force_reasoning= False
    reasoning_config= ReasoningToggleConfig(toggle_param='enable_thinking', default_enabled=True, special_case=None, effort_kwarg=None)
    reasoning_parser= qwen3   tool_call_parser= qwen3_coder   effort_kwarg= None
  ```
  CPU render probe for M1 shows the same inert result for every tier/float and the same `enable_thinking=false` effect.
- **INFERENCE (clearly marked):** because the template, tokenizer config, detection config, and parser wiring are identical, M1's graded `reasoning_effort` tiers are expected to be inert at runtime exactly as M2's are, and `reasoning_effort:"none"` / ctk `enable_thinking=false` are expected to work.
- **EXPLICITLY NOT VERIFIED:** M1 **runtime** behavior. M1 is not served; verifying it requires a separate GPU window. The static identity is strong evidence but is not runtime fact.

---

## Defects / blockers

1. **Unconditional advertisement of a model-gated capability (contract defect, A-flavoured).** `reasoning_effort` tiers + float `[0.0, 0.99]` are advertised on the generic chat schema for every model, but are inert for any model whose template/encoding declares no graded consumer. Callers receive HTTP 200 with byte-identical output and no warning.
2. **The generic materialization collapses every non-`none` value to `enable_thinking=True`** (`protocol.py:1025-1038`). This is the mechanism by which `minimal/low/medium/high/xhigh/max` and all floats become indistinguishable from default.
3. **Budget path is unreachable from the chat surface for this deployment.** `max_thinking_tokens` is not a chat-request field (silently dropped); `custom_params.thinking_budget` is accepted but gated behind `--enable-strict-thinking` (absent) and, for the Qwen3 processor, uses the wrong token IDs for this model.
4. **No mapping from `reasoning_effort` to any budget mechanism.** Confirmed by exhaustive grep; the two mechanisms are disjoint.
5. **`Qwen3ThinkingBudgetLogitProcessor` token constants do not match the served model** (151667/151668 vs 248068/248069) — latent no-op even if the feature were enabled.
6. **Fail-silent accepted keys.** `custom_params={"thinking_budget":5}`, top-level `max_thinking_tokens`, and ctk `thinking_budget` all return HTTP 200 with no effect and no warning.
7. **`/get_server_info` advertises no effort capability**, so operators cannot discover from the runtime what the model actually supports.

None of these are blockers to answering the owner's question; the graded-control status is established.

---

## Remaining claims / exclusions

- **Excluded:** the 5-class measurement corpus of the prior audits was not repeated. Only two representative fixed prompts (trivial arithmetic, math word problem) × fixed `temperature=0`, `max_tokens<=512` were used here; determinism is evidenced by byte-identical baseline repeats across the matrix.
- **Excluded (not tested):** streaming (`stream:true`), `/v1/responses`, the Anthropic surface, tool-calling paths, `response_format`, and multi-turn history. Static reading shows `/v1/responses` advertises only string tiers and harmony/dsv4 consumption is gated by unrelated specs; no runtime claims are made for those surfaces.
- **Excluded:** M1 runtime (requires separate GPU window), as stated.
- **Not attempted:** enabling `--enable-strict-thinking` / `--enable-custom-logit-processor`, launching with a modified template, or any product/server/config edit (read-only mandate).
- **Non-claims:** this audit does not claim that a template-only edit would produce *trained* graded behavior; it claims only which layers lack a consumer. Whether Qwen3.5 weights respond to any graded cue is a model-capability question outside this audit.
- **Method note:** the 21-completion bound was respected; 11 additional `/v1/tokenize` calls are render-only (no generation). Total request count on port 30000 for this task: 32.

---

## Evidence file reference (all under `/tmp/opencode/REASONING-EFFORT-TIERS-20260918/`)

- **Harness/logs:** `probe.py`, `probe.out`, `compare.py`, `compare.out`, `render_probe.py`, `render_probe.out`, `detection_probe.out`
- **Consolidated:** `completions_summary.json` (21 requests with request bodies), `tokenize_summary.json` (11 render probes)
- **Service (read-only GET):** `ev_health.txt`, `ev_models.json`, `ev_server_info.json`, `ev_openapi.json`
- **Raw graded-tier responses:** `raw/cc_00_baseline_P1.json`, `raw/cc_effort_{none,minimal,low,medium,high,xhigh,max}_P1.json`, `raw/cc_effort_float_{0_0,0_25,0_99}_P1.json`, `raw/cc_positive_ctk_false_P1.json`, `raw/cc_00_baseline_P5.json`, `raw/cc_effort_high_P5.json`, `raw/cc_positive_ctk_false_P5.json`
- **Raw budget responses:** `raw/cc_budget_custom_params_P1.json`, `raw/cc_budget_top_max_thinking_P1.json`, `raw/cc_budget_ctk_thinking_budget_P1.json`
- **Raw render probes:** `raw/TOK_default.json`, `raw/TOK_effort_{none,minimal,low,medium,high,xhigh,max}.json`, `raw/TOK_effort_float_{0_0,0_99}.json`, `raw/TOK_ctk_false.json`
- **Negative self-checks:** `raw/cc_neg_bogus_P1.json`, `neg_out_of_range_1_5.json`, `neg_custom_logit_processor.json`, `neg_custom_logit.out`
- **Changed artifacts:** only the scratch files above plus this authoritative handoff. No product source, test, config, git, ledger, or server state was modified.

**Terminal state: DONE**
