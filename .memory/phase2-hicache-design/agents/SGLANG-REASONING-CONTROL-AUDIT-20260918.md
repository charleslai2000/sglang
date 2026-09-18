# SGLang Reasoning-Control Audit (M2 live + M1 static)

**Task:** Independent, read-only audit for the owner: do the externally-exposed reasoning-control
parameters (`reasoning_effort`, `enable_thinking`, `chat_template_kwargs`) actually take effect,
and does the same conclusion apply to the previous Qwen3.5 arm (M1)?

**Auditor role:** `debugger-deep` (diagnostic/investigative). Read-only w.r.t. server, product
source, tests, config. No restarts, no signals, no port/state changes. Only new scratch files
written under `/tmp/opencode/SGLANG-REASONING-CONTROL-20260918/` plus this artifact.

## Scope

- Served code/tree (frozen, read-only): `/opt/sglang/local-prod-v1.2.1-candidate`
  - `src/python/sglang/srt/entrypoints/openai/{protocol.py,serving_chat.py,serving_tokenize.py}`
  - `src/python/sglang/srt/parser/{reasoning_parser.py,template_detection.py,template_manager.py}`
  - `src/python/sglang/srt/managers/{schedule_batch.py,scheduler_components/batch_result_processor.py}`
- Live service: `:30000`, M2 = `/data/models/omnicoder-9b-gptq-int4` (OmniCoder-9B GPTQ INT4),
  launched with `--reasoning-parser qwen3 --tool-call-parser qwen3_coder`.
- M2 chat template: `/data/models/omnicoder-9b-gptq-int4/chat_template.jinja` (static).
- M1 chat template (static only; M1 not served): `/data/models/qwen35-9b-w4a16/chat_template.jinja`.
- Runtime parameter-acceptance matrix bounded to 21 `/v1/chat/completions` + 13 `/v1/tokenize`
  requests, `temperature=0`, `max_tokens=512`. No measurement study duplicated.

## Result (one paragraph)

The prior conclusion "no API control exists" was **wrong**. Both M2 and M1 use the **same,
byte-identical** Qwen3.5 chat template that implements exactly one effective toggle:
**`enable_thinking`** (strict boolean `false` disables reasoning; anything else, including
unset, enables it). The correct placement is **inside `chat_template_kwargs`** —
`"chat_template_kwargs": {"enable_thinking": false}` — which was proven effective both at the
tokenizer/render level and end-to-end (`reasoning_tokens` 174 → 0, `completion_tokens` 177 → 2,
`reasoning_content: null`, `content: "4"`). Top-level `enable_thinking` is **silently dropped by
pydantic** (`ChatCompletionRequest` has no `extra="allow"`), which explains the prior agent's
"ignored" observation. Top-level `reasoning_effort` works **only for `"none"`** (it is translated
into `chat_template_kwargs.enable_thinking=false`); all other effort tiers (`minimal/low/medium/
high/xhigh/max`, floats) are **inert** because the template contains no effort-tier variable.
`stop` sequences are **truncation-only**, not a control. For M1, the static evidence is
**byte-identical** to M2 (same template hash, same detected toggle, same parser), so the same
control surface is expected; **runtime verification on M1 still requires a separate GPU window**
and was not attempted.

## Evidence

### A. Served-code revision / integrity (FACT)

- Served interpreter: `/opt/sglang/local-prod-v1.2.1-candidate/env/bin/python`.
- Live process PID 1764114, `PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python`.
- `sglang.__file__` imported by that interpreter resolves to
  `/opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/__init__.py`.
- `identity.json`: `SOURCE_COMMIT=b2bbd6ea28`, `TREE_HASH=5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950`.
- Upstream version file: `0.5.20.dev22+g9c9e7b7c7` (commit id `g9c9e7b7c7`).
- Every audited file hash matches `manifest/TREE-SHA256.txt` exactly (live vs manifest):

```
7b05e6ab1d09a71ce253040c9cd62ea7c55a52020b44cf9b76d91c8df9e23240  src/python/sglang/srt/entrypoints/openai/serving_chat.py
a7cf91c1db5d076b9ad647248351f10b0249153998b974ed4d00610306b01653  src/python/sglang/srt/entrypoints/openai/protocol.py
f608772b59a98eb62f1e7ee5ea1f17b16a0ca4e2c325c77cbed8ef4594ca15f4  src/python/sglang/srt/parser/reasoning_parser.py
041cb3b9030154f39bd30e80ccf95bbe3b5014d6baa9e2132599bad5d636d2e5  src/python/sglang/srt/parser/template_detection.py
2c7de852332f68d9ca5e535f42633372aa86e5bd69406ec8a102f43b17855b32  src/python/sglang/srt/parser/template_manager.py
```

Manifest lookup for the same five files returned the identical hashes
(`grep -E "...serving_chat.py|...protocol.py|..." manifest/TREE-SHA256.txt`).

### B. Section 1 — SGLang plumbing trace (static, file:line)

All paths are under `/opt/sglang/local-prod-v1.2.1-candidate/`.

**1. Request body parsing.**

- `src/python/sglang/srt/entrypoints/openai/protocol.py:823` — `class ChatCompletionRequest(BaseModel):`
  This model does **not** set `model_config = ConfigDict(extra="allow")`. The only
  `extra="allow"` model in this file is `TokenizeRequest` at `protocol.py:1447`. Therefore any
  unknown top-level body key on `/v1/chat/completions` is **silently ignored** (pydantic default
  `extra="ignore"`). This is the root cause of the prior "top-level `enable_thinking` ignored"
  observation.
- `protocol.py:869-881` — typed top-level `reasoning_effort`:
  ```python
  reasoning_effort: ReasoningEffortType = Field(
      default=None,
      description="Constrains effort on reasoning for reasoning models. "
      "Accepts string levels ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max') or a "
      "float in [0.0, 0.99] for fine-grained control. "
      ...
  ```
- `protocol.py:793-808` — `ReasoningEffortTier` literal set and `ReasoningEffortType` union (tier
  strings + constrained float `[0.0, 0.99]`).
- `protocol.py:910` — `chat_template_kwargs: Optional[Dict] = None`.
- `protocol.py:976-981` — `validate_reasoning_effort_type` (rejects boolean).
- `protocol.py:1025-1038` — **the only place top-level `reasoning_effort` is turned into a
  template toggle**:
  ```python
  effort = values.get("reasoning_effort")
  if effort is not None:
      thinking = effort != "none"

  if thinking is not None:
      ctk = values.get("chat_template_kwargs")
      if not isinstance(ctk, dict):
          ctk = {}
      # different models check different keys:
      # - "thinking" for deepseek-v3, kimi_k2
      # - "enable_thinking" for qwen3, glm45, nemotron_3, interns1
      ctk.setdefault("thinking", thinking)
      ctk.setdefault("enable_thinking", thinking)
      values["chat_template_kwargs"] = ctk
  ```
  Note: `reasoning={"enabled": false}` does **not** reach here as `thinking=False` — see Defects.
- `protocol.py:983-1023` — `normalize_reasoning_inputs` handles the nested `reasoning` object:
  `reasoning={"effort": "none"}` becomes top-level `reasoning_effort="none"`. But
  `reasoning={"enabled": false}` only ever sets `thinking=True` when truthy
  (`if enabled: thinking = True`), so a false `enabled` is a no-op.

**2. Merge / template-kwargs construction.**

- `src/python/sglang/srt/entrypoints/openai/serving_chat.py:966-982` —
  `_convert_to_internal_request` **pops** `reasoning_effort` out of `chat_template_kwargs`:
  ```python
  reasoning_effort = (
      request.chat_template_kwargs.pop("reasoning_effort", None)
      if request.chat_template_kwargs
      else None
  )
  ...
  if reasoning_effort is not None:
      request.reasoning_effort = reasoning_effort
  ```
  This runs **after** the pydantic validators, so `chat_template_kwargs.reasoning_effort` never
  triggers the `enable_thinking` materialization at `protocol.py:1025-1038`.
- `serving_chat.py:1004-1012` — `_process_messages(request, ...)` is called from inside
  `_convert_to_internal_request`.
- `serving_chat.py:1100-1108` — `_process_messages` merges server defaults:
  ```python
  if self.default_chat_template_kwargs:
      ctk = dict(request.chat_template_kwargs or {})
      for k, v in self.default_chat_template_kwargs.items():
          ctk.setdefault(k, v)
      request.chat_template_kwargs = ctk
  ```
- `serving_chat.py:1119` — `thinking_mode = self._get_reasoning_from_request(request)`.
- `serving_chat.py:1357-1361` — extra kwargs for Jinja rendering:
  ```python
  extra_template_kwargs = {}
  if request.reasoning_effort is not None:
      extra_template_kwargs["reasoning_effort"] = request.reasoning_effort
  if request.chat_template_kwargs:
      extra_template_kwargs.update(request.chat_template_kwargs)
  ```
  `reasoning_effort` is passed to Jinja but the template never references it, so it is inert.
- `serving_chat.py:1386-1393` — actual render:
  ```python
  rendered_prompt = self.tokenizer_manager.tokenizer.apply_chat_template(
      openai_compatible_messages,
      tokenize=False,
      add_generation_prompt=True,
      tools=tools,
      return_dict=False,
      **extra_template_kwargs,
  )
  ```
  So `chat_template_kwargs` **is** spread into `apply_chat_template`; the server plumbing is
  correct. The effectiveness limit is the template's variable set, not the plumbing.
- `serving_chat.py:1224-1229` — only the Kimi/`thinking` custom-encoding path reads the key
  `"thinking"`; the default Qwen3.5 path reaches the template with raw ctk.
- `serving_chat.py:1363-1373` — `rc.effort_kwarg` handling only exists for templates that declare
  an effort kwarg. Detected config for both models has `effort_kwarg=None`, so this branch is dead.

**3. Toggle resolution (server side).**

- `serving_chat.py:2430-2506` — `_get_reasoning_from_request`. For detected config
  `toggle_param="enable_thinking", default_enabled=True` (`config.default_enabled` at 2498):
  ```python
  if config.default_enabled:
      return (
          not request.chat_template_kwargs
          or request.chat_template_kwargs.get(config.toggle_param) is not False
      )
  ```
  This controls `require_reasoning` (`serving_chat.py:1202`, `1078`) — i.e. whether the server
  *counts/parses* reasoning — and **mirrors** the template toggle. It does not itself change the
  prompt.
- `serving_chat.py:2340-2356` — `_get_reasoning_toggle_param` returns
  `template_manager.reasoning_config.toggle_param` (`enable_thinking` here).

**4. `qwen3` reasoning parser behavior.**

- `src/python/sglang/srt/parser/reasoning_parser.py:355-399` — `Qwen3Detector` splits on
  `<think>` / `</think>`, `thinks_internally=True`, `reasoning_default="enable_thinking"`.
- `reasoning_parser.py:1978-2008` — `ReasoningParser.__init__` reads
  `request.chat_template_kwargs`; only `thinking_mode == "enabled"` (minimax-m3) and
  `force_nonempty_content` are consulted. **No Qwen3.5 reasoning-control parameter affects the
  parser**; it only splits already-generated text.
- `serving_chat.py:1898-1918` (non-stream) — `parser.parse_non_stream(text)` is invoked with
  `force_reasoning = template_manager.force_reasoning or self._get_reasoning_from_request(request)`.
  `force_reasoning` here is `False` for this template (`detect_reasoning_pattern` returns
  `force_reasoning=False`; startup log confirms), so the parser split is governed by whether
  `<think>` appears in the text.
- Token accounting: `managers/scheduler_components/batch_result_processor.py:1201-1208` only counts
  reasoning tokens when `req.require_reasoning` is true; `managers/schedule_batch.py:1942-1961`
  counts tokens up to the `</think>` id sequence. So `usage.reasoning_tokens` is a reliable proxy
  for "the template emitted thinking".

**5. Where a parameter is accepted then silently dropped (FACT).**

- Top-level `enable_thinking` (and any unknown top-level key): dropped by pydantic at parse
  (`ChatCompletionRequest` has no `extra="allow"`; `protocol.py:823`).
- `chat_template_kwargs.reasoning_effort`: popped at `serving_chat.py:971-972` and assigned to
  `request.reasoning_effort` after validators, so it never materializes the enable_thinking toggle.
- `chat_template_kwargs.thinking=false`: forwarded to Jinja (`serving_chat.py:1361`) but the
  template never reads `thinking`.
- Unknown ctk keys (`thinking_budget`, `preserve_thinking`, ...): forwarded to Jinja; template
  ignores them. Request still returns HTTP 200.

### C. Section 2 — The two models' chat templates (static, FACT)

- Both files are the **same bytes**:
  ```
  sha256  a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715  /data/models/omnicoder-9b-gptq-int4/chat_template.jinja
  sha256  a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715  /data/models/qwen35-9b-w4a16/chat_template.jinja
  diff ...  -> IDENTICAL
  ```
- Neither `tokenizer_config.json` embeds a `chat_template` key; the server loads the Jinja file
  from disk (`server.console.log`: `Using default HuggingFace chat template with detected content
  format: openai`). The live tokenizer's `chat_template` hashes to the same
  `a4aee8af...` for both model dirs.
- The template declares **only one** control variable, `enable_thinking`, at lines 147-153:
  ```jinja
  {%- if add_generation_prompt %}
      {{- '<|im_start|>assistant\n' }}
      {%- if enable_thinking is defined and enable_thinking is false %}
          {{- '<think>\n\n</think>\n\n' }}
      {%- else %}
          {{- '<think>\n' }}
      {%- endif %}
  {%- endif %}
  ```
- **DEFAULT when unset:** reasoning ON. `enable_thinking` undefined → `else` branch →
  `<think>\n` (prefilled thinking). This matches the detected
  `ReasoningToggleConfig(toggle_param='enable_thinking', default_enabled=True, special_case=None, effort_kwarg=None)`
  and the live startup log.
  ```
  [2026-09-18 10:09:17] Auto-detected template features: reasoning_config=ReasoningToggleConfig(toggle_param='enable_thinking', default_enabled=True, special_case=None, effort_kwarg=None), reasoning_parser=qwen3, tool_call_parser=qwen3_coder
  ```
- Static scan for other control names: `reasoning_effort`, `thinking_budget`,
  `preserve_thinking`, `low_effort`, `thinking_effort` are **absent** from both templates;
  only the string `thinking` appears (as part of `enable_thinking` and the `<think>` tokens).
- **Honored control names (both models):** `enable_thinking` — and only the strict boolean
  `false` disables (template uses Jinja identity test `is false`).
- **Ignored control names (both models):** `reasoning_effort`, `thinking`, `thinking_budget`,
  `preserve_thinking`, `thinking_effort`, and every other key.
- M1 also previously ran with `--reasoning-parser qwen3 --tool-call-parser qwen3_coder`
  (`M1-argv.txt`), identical parser wiring to M2.

### D. Section 3 — Runtime parameter × placement acceptance (M2, live)

All requests: `POST http://127.0.0.1:30000/v1/chat/completions`, body base
`{"model":"/data/models/omnicoder-9b-gptq-int4","messages":[{"role":"user","content":"What is 2+2? Answer with just the number."}],"temperature":0,"max_tokens":512}`,
plus the "extra" fragment below. Baseline (`00_baseline.json`): HTTP 200,
`completion_tokens=177`, `reasoning_tokens=174`, `content="\n\n4"`, `reasoning_content` present.
`reasoning_tokens=0` + `reasoning_content:null` = reasoning disabled. Raw responses saved under
`/tmp/opencode/SGLANG-REASONING-CONTROL-20260918/` (names in the inventory below).

| # | placement / extra body | HTTP | completion | reasoning | verdict |
|---|---|---|---|---|---|
| 00 | baseline (none) | 200 | 177 | 174 | baseline (thinking ON) |
| 01 | top-level `"enable_thinking": false` | 200 | 177 | 174 | **IGNORED** (silently dropped) |
| 02 | `chat_template_kwargs:{"enable_thinking": false}` | 200 | 2 | 0 | **HONORED** |
| 03 | top-level `"reasoning_effort":"low"` | 200 | 177 | 174 | **INERT** |
| 04 | top-level `"reasoning_effort":"high"` | 200 | 177 | 174 | **INERT** |
| 05 | top-level `"reasoning_effort":"none"` | 200 | 2 | 0 | **HONORED** (maps to enable_thinking=false) |
| 06 | ctk `"reasoning_effort":"low"` | 200 | 177 | 174 | **INERT** (popped, post-validation) |
| 07 | ctk `"enable_thinking": true` | 200 | 177 | 174 | accepted, no change (already ON) |
| 08 | ctk `"thinking": false` | 200 | 177 | 174 | **IGNORED** (template doesn't read `thinking`) |
| 09 | top-level `"reasoning_effort":"bogus"` | 400 | — | — | **REJECTED** |
| 10 | top-level `"enable_thinking":"false"` (string) | 200 | 177 | 174 | **IGNORED** (dropped field) |
| 11 | `"reasoning":{"effort":"none"}` | 200 | 2 | 0 | **HONORED** |
| 12 | `"reasoning":{"enabled": false}` | 200 | 177 | 174 | **IGNORED / no-op** |
| 13 | ctk `"reasoning_effort":"none"` | 200 | 177 | 174 | **INERT** (placement inconsistency) |
| 14 | top-level `"reasoning_effort":"minimal"` | 200 | 177 | 174 | **INERT** |
| 15 | top-level `"reasoning_effort": 0.0` | 200 | 177 | 174 | **INERT** |
| 16 | ctk `{"enable_thinking":false}` + `stop:["<think>"]` | 200 | 2 | 0 | HONORED toggle (stop irrelevant) |
| 17 | `stop:["Thinking Process:"]` only | 200 | 3 | 3 | **TRUNCATION-ONLY** (`content:""`) |
| 18 | ctk `{"thinking_budget":1,"preserve_thinking":false}` | 200 | 177 | 174 | **IGNORED** (unknown keys) |
| 19 | ctk `"enable_thinking":"false"` (string) | 200 | 177 | 174 | **IGNORED** (strict `is false`) |
| 20 | ctk `"enable_thinking": 0` (int) | 200 | 177 | 174 | **IGNORED** (strict `is false`) |
| 21 | baseline repeat | 200 | 177 | 174 | deterministic baseline |

Raw response excerpts (verbatim):

- `cc_02_ctk_enable_false.json`:
  ```json
  {"id":"45daa951a22045408c8ae210ed0dd5d9","object":"chat.completion","created":1789727710,"model":"/data/models/omnicoder-9b-gptq-int4","choices":[{"index":0,"message":{"role":"assistant","content":"4","reasoning_content":null,"tool_calls":null},"logprobs":null,"finish_reason":"stop","matched_stop":248046}],"usage":{"prompt_tokens":25,"total_tokens":27,"completion_tokens":2,"prompt_tokens_details":null,"reasoning_tokens":0},"metadata":{"weight_version":"default","weight_versions":[{"version":"default","start":0,"end":2}]}}
  ```
- `cc_05_top_effort_none.json` / `cc_11_reasoning_effort_none_obj.json` message:
  `{"role": "assistant", "content": "4", "reasoning_content": null, "tool_calls": null}`.
- `cc_17_stop_truncation.json`:
  ```json
  {"id":"8c143aea739d4299959ecf74b6cb3fa8","object":"chat.completion",...,"choices":[{"index":0,"message":{"role":"assistant","content":"","reasoning_content":null,"tool_calls":null},"logprobs":null,"finish_reason":"stop","matched_stop":"Thinking Process:"}],"usage":{"prompt_tokens":23,"total_tokens":26,"completion_tokens":3,...,"reasoning_tokens":3},...}
  ```
- `cc_09_top_effort_bogus.json` (verbatim 400 body):
  ```json
  {"object":"error","message":"2 validation errors:\n  {'type': 'literal_error', 'loc': ('body', 'reasoning_effort', \"literal['none','minimal','low','medium','high','xhigh','max']\"), 'msg': \"Input should be 'none', 'minimal', 'low', 'medium', 'high', 'xhigh' or 'max'\", 'input': 'bogus', ...}\n  {'type': 'float_parsing', ...}\n\n  File \"/opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/entrypoints/http_server.py\", line 1725, in openai_v1_chat_completions...","type":"Bad Request","param":null,"code":400}
  ```

**Read-only render-level confirmation via `/v1/tokenize`** (these do not generate text; they run
the same `_process_messages`/`apply_chat_template` code at `serving_tokenize.py:87-115`):

- Default (no kwargs): `{"tokens":[...248068,198],"count":17,...}` —
  decoded tail `248068 198` = `<think>\n`.
- ctk `enable_thinking=false`: `{"tokens":[...248068,271,248069,271],"count":19,...}` —
  decoded tail `<think>\n\n</think>\n\n` (thinking closed / disabled). **Direct render proof.**
- top-level `enable_thinking=false` (both `false` and `true`): identical to default (17 tokens) —
  confirms pydantic drop.
- top-level `reasoning_effort` in `low`/`high`: identical to default (17 tokens) — inert.
- top-level `reasoning_effort":"none"`: identical to ctk false (19 tokens) — materialization works.
- ctk `reasoning_effort":"low"` / ctk `thinking:false` / ctk `thinking_budget:1`: identical to
  default (17 tokens) — inert.
- `/v1/tokenize` rejects `chat_template_kwargs` non-dict (400) and `reasoning_effort:"bogus"` (400).

Token-ID decode used: `248068='<think>'`, `248069='</think>'`, `271='\n\n'` (from the served
tokenizer). All tokenize raw responses are in `tok_*.json`.

### E. Negative self-checks (real output)

1. **Malformed body negative control** — `cc_21_baseline_repeat.json` was first written by a
   shell-construction bug (trailing comma); the server correctly rejected it, proving my harness
   surfaces non-200s rather than silently reporting baseline:
   ```json
   {"object":"error","message":"1 validation error:\n  {'type': 'json_invalid', 'loc': ('body', 162), 'msg': 'JSON decode error', ... 'trailing comma is not allowed' ...}","type":"Bad Request","param":null,"code":400}
   ```
   It was then re-run from the saved `req_00_baseline.json` and returned 200 / 174 reasoning.
2. **Deliberately bad ctk type** → HTTP 400 `dict_type` (not a silent pass-through).
3. **Deliberately bad `reasoning_effort`** → HTTP 400 `literal_error` (not silently coerced).
4. **Model identity check** — `/get_model_info` returns
   `"model_path":"/data/models/omnicoder-9b-gptq-int4"`, `"reasoning_parser":"qwen3"`,
   `"tool_call_parser":"qwen3_coder"`, `"model_type":"qwen3_5"`.
5. **Served-contract integrity** — audited file hashes matched the frozen manifest byte-for-byte.

## Which parameters actually work

**EFFECTIVE (change model behavior):**

- `chat_template_kwargs: {"enable_thinking": false}` — boolean `false` only. Proven at render
  level (`/v1/tokenize` changes the prefill from `<think>\n` to `<think>\n\n</think>\n\n`) and
  end-to-end (`reasoning_tokens` 174 → 0, `completion_tokens` 177 → 2, `content:"4"`,
  `reasoning_content:null`). Works identically for M2 (runtime) and, per static template evidence,
  M1.
- `reasoning_effort: "none"` (top-level) — effective **only** because protocol.py:1025-1038
  translates it to `chat_template_kwargs.enable_thinking=false`. Verified end-to-end.
- `reasoning: {"effort": "none"}` (nested object) — same translation as above. Verified.

**INERT (accepted, HTTP 200, no behavioral change):**

- Top-level `enable_thinking` (any value) — silently dropped by pydantic.
- Top-level `reasoning_effort` in `{minimal, low, medium, high, xhigh, max}` or float `[0.0,0.99]`
  — accepted; no effort-tier variable exists in the template.
- `chat_template_kwargs.reasoning_effort` (any value) — popped after validation; even `"none"`
  does nothing here (placement inconsistency vs top-level).
- `chat_template_kwargs.thinking: false` — template does not read `thinking`.
- `chat_template_kwargs.enable_thinking` given a non-boolean (`"false"`, `0`) — Jinja identity
  test `is false` fails.
- Unknown ctk keys (`thinking_budget`, `preserve_thinking`, ...) — forwarded to Jinja, ignored.
- `reasoning: {"enabled": false}` — no-op; the code only ever sets `thinking=True` from a truthy
  `enabled`.

**TRUNCATION-ONLY (not a control):**

- `stop: ["Thinking Process:"]` (or `<think>`) cuts generation mid-stream; returns empty/partial
  `content` with `finish_reason:"stop"` and `matched_stop`. It does not disable reasoning; it just
  stops the model after it has already begun thinking. Verified (`cc_17`: completion 3,
  reasoning 3, content `""`, `matched_stop:"Thinking Process:"`).

**REJECTED (HTTP 400):**

- `reasoning_effort` outside the literal tier set and not numeric (`"bogus"`).
- `chat_template_kwargs` not a dict.

## M1 (Qwen3.5-9B W4A16) — static verdict, runtime pending

- M1 template is **byte-identical** to M2 (same sha256 `a4aee8af...`, same 7756 bytes, `diff`
  reports identical). It contains only `enable_thinking`; default is reasoning ON.
- The served-code detection result for M1 (run through the frozen tree's tokenizer/detection
  stack, CPU-only) is identical:
  `force_reasoning=False, ReasoningToggleConfig(toggle_param='enable_thinking', default_enabled=True, effort_kwarg=None), reasoning_parser=qwen3, tool_call_parser=qwen3_coder`.
- M1's last launch argv used the same `--reasoning-parser qwen3 --tool-call-parser qwen3_coder`.
- **STATIC INFERENCE (not runtime fact):** M1 should honor exactly
  `chat_template_kwargs.enable_thinking=false` and `reasoning_effort:"none"`, and should be inert
  on the same parameter set as M2. **Runtime verification requires a separate GPU window** (M1 is
  not served); it was not attempted and must not be inferred as measured.

## FACTS vs INFERENCE

- **FACT:** M2 `chat_template_kwargs.enable_thinking=false` disables reasoning (render + e2e).
- **FACT:** M2 top-level `enable_thinking` is silently dropped (pydantic + runtime).
- **FACT:** M2 top-level `reasoning_effort` is honored only for `"none"`; all other tiers are inert.
- **FACT:** M2 ctk `reasoning_effort`, ctk `thinking`, non-boolean `enable_thinking`, unknown ctk
  keys, and `reasoning.enabled=false` are inert.
- **FACT:** M2 `stop` is truncation-only.
- **FACT:** M1 and M2 chat templates are byte-identical; M1's static detection is identical.
- **INFERENCE:** M1 will exhibit the same effective/inert map at runtime. Needs a GPU window.
- **UNKNOWN:** Nothing about M1 runtime behavior can be asserted beyond the static identity.

## Defects / blockers

1. **Top-level `enable_thinking` is silently dropped** — `ChatCompletionRequest`
   (`protocol.py:823`) lacks `extra="allow"`, so an OpenAI-style top-level thinking flag is
   accepted with HTTP 200 and ignored. This produced the prior agent's incorrect "no API control
   exists" conclusion. The correct placement is `chat_template_kwargs`.
2. **`reasoning_effort` is not a real effort control on Qwen3.5** — only `"none"` has an effect,
   via translation to the on/off toggle. Every graded tier is accepted and inert; there is no
   `effort_kwarg` in either template's detected config.
3. **Placement inconsistency** — `reasoning_effort:"none"` at top level works, but
   `chat_template_kwargs.reasoning_effort:"none"` does not (popped after validation). Operators
   could reasonably expect both to behave the same.
4. **`reasoning: {"enabled": false}` is a no-op** — there is no code path that translates a false
   `enabled` into `enable_thinking=false`; only `effort:"none"` disables.
5. **Non-boolean ctk `enable_thinking` is silently ignored** — strings like `"false"` and `0`
   pass validation and leave reasoning ON with no warning.
6. **`reasoning_tokens` accounting depends on `require_reasoning`** which mirrors the template
   toggle; a template that emits `<think>` while the toggle says off would still be counted
   inconsistently. Not triggered by the current template.

None of these are blockers to the owner's question; the effective control exists and is proven.

## Remaining claims / exclusions

- Excluded: streaming (`stream:true`) path behavior beyond static reading; only non-streaming
  `/v1/chat/completions` was exercised.
- Excluded: `/v1/responses` and the Anthropic surface (static code exists at
  `serving_responses.py:764-788`, `anthropic/serving.py:624-632`; not tested).
- Excluded: any actual measurement study of token savings across a corpus (belongs to a separate
  task; not duplicated).
- Excluded: M1 runtime; requires a GPU window.
- Excluded: server restart/config/code change of any kind (read-only mandate).
- `temperature=0` and a single fixed prompt were used for the acceptance matrix; determinism is
  evidenced by baseline repeats (00 vs 21, both 177/174).

## Exact commands / requests used

Integrity / identity (read-only):
```bash
sha256sum /opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/entrypoints/openai/serving_chat.py \
  /opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/entrypoints/openai/protocol.py \
  /opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/parser/reasoning_parser.py \
  /opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/parser/template_detection.py \
  /opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/parser/template_manager.py
grep -E "openai/serving_chat.py|openai/protocol.py|parser/reasoning_parser.py|parser/template_detection.py|parser/template_manager.py" \
  /opt/sglang/local-prod-v1.2.1-candidate/manifest/TREE-SHA256.txt
tr '\0' '\n' < /proc/1764114/environ | grep -E "^PYTHONPATH|^SGLANG_RUN_ID"
curl -s --max-time 10 http://127.0.0.1:30000/get_model_info
sha256sum /data/models/omnicoder-9b-gptq-int4/chat_template.jinja /data/models/qwen35-9b-w4a16/chat_template.jinja
diff /data/models/omnicoder-9b-gptq-int4/chat_template.jinja /data/models/qwen35-9b-w4a16/chat_template.jinja
grep -nE "enable_thinking|reasoning_effort|thinking_budget|preserve_thinking|thinking|budget" \
  /data/models/omnicoder-9b-gptq-int4/chat_template.jinja
```

Static detection (CPU-only, read-only import through the frozen tree):
```bash
CUDA_VISIBLE_DEVICES=999 PYTHONDONTWRITEBYTECODE=1 \
/opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -c "
import hashlib
from sglang.srt.utils.hf_transformers_utils import get_tokenizer
from sglang.srt.parser.template_detection import detect_reasoning_pattern, build_detection_context, REASONING_PARSER_RULES, TOOL_CALL_PARSER_RULES, match_rules
for p in ['/data/models/omnicoder-9b-gptq-int4','/data/models/qwen35-9b-w4a16']:
    tok = get_tokenizer(p, trust_remote_code=False)
    t = tok.chat_template
    print(p, hashlib.sha256((t or '').encode()).hexdigest())
    fr, rc = detect_reasoning_pattern(t)
    ctx = build_detection_context(t, tok, rc, fr)
    print('force=',fr,'cfg=',rc,'rp=',match_rules(ctx,REASONING_PARSER_RULES,'r'),'tcp=',match_rules(ctx,TOOL_CALL_PARSER_RULES,'t'))
"
```

Chat completions (the shell function sets `name`, `extra`; raw body base quoted verbatim):
```bash
BASE='{"model":"/data/models/omnicoder-9b-gptq-int4","messages":[{"role":"user","content":"What is 2+2? Answer with just the number."}],"temperature":0,"max_tokens":512'
curl -s --max-time 120 http://127.0.0.1:30000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d "$BASE,\"chat_template_kwargs\":{\"enable_thinking\":false}}" \
  -o cc_02_ctk_enable_false.json -w 'HTTP_STATUS=%{http_code}\n'
```
(The 21 `cc_*` variants and their exact `extra` fragments are tabulated in Section D; request
bodies that were re-used are saved as `req_*.json`.)

Tokenize render checks:
```bash
curl -s --max-time 30 http://127.0.0.1:30000/v1/tokenize -H 'Content-Type: application/json' \
  -d '{"model":"/data/models/omnicoder-9b-gptq-int4","messages":[{"role":"user","content":"What is 2+2?"}],"chat_template_kwargs":{"enable_thinking":false}}'
```

## Scratch artifact inventory (all under `/tmp/opencode/SGLANG-REASONING-CONTROL-20260918/`)

- `00_baseline.json` — baseline completion (174 reasoning).
- `cc_01_top_enable_false.json` … `cc_21_baseline_repeat.json` — 21 chat-completion responses
  matching the Section D table (note `cc_21` initially holds the 400 malformed-body negative
  check, then was overwritten by the valid re-run).
- `cc_09_top_effort_bogus.json` — 400 rejection body.
- `cc_22_malformed_body_negative.json` — 400 malformed-JSON negative self-check body
  (reproduced and preserved).
- `tok_default.json`, `tok_ctk_false.json`, `tok_ctk_enable_false.json`, `tok_ctk_enable_true.json`,
  `tok_top_enable_false.json`, `tok_top_enable_true.json`, `tok_top_effort_low.json`,
  `tok_top_effort_high.json`, `tok_top_effort_none.json`, `tok_ctk_effort_low.json`,
  `tok_ctk_thinking_false.json`, `tok_ctk_bogus.json` — `/v1/tokenize` render evidence.
- `req_00_baseline.json`, `req_01_top_enable_false.json`, `req_02_ctk_enable_false.json`,
  `req_04_top_effort_high.json`, `req_05_top_effort_none.json`, `req_13_ctk_effort_none.json` —
  saved request bodies.
- `MATRIX.tsv` — machine-readable summary of the `cc_*` matrix.
- `M1-previous-launch-argv.txt`, `M2-current-launch-argv.txt` — launch commands.
- `M2-startup-template-detection.log` — server console lines proving template + detection.

## Changed-artifact list

- **Created (scratch):** all files listed in the inventory above under
  `/tmp/opencode/SGLANG-REASONING-CONTROL-20260918/`.
- **Created (authoritative handoff):** this file
  `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/SGLANG-REASONING-CONTROL-AUDIT-20260918.md`.
- **Not modified:** server process/state, port 30000 config, product source, tests, config, git,
  the ledger, or any other memory file.

Terminal state: DONE
