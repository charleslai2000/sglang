# Task: Independent verification + correction of M2 thinking-effort measurement

- **Date:** 2026-09-18
- **Role:** `debugger-deep` (non-worker; read-only wrt server and product tree)
- **Target:** M2 = `/data/models/omnicoder-9b-gptq-int4` served on `127.0.0.1:30000` (SGLang)
- **Prior artifact under review:** `.memory/phase2-hicache-design/agents/M2-THINKING-EFFORT-20260918.md`
- **Terminal verdict:** **DONE**

---

## Scope

1. Verify the prior agent's raw evidence in `/tmp/opencode/M2-THINKING-20260918/` against its claimed numbers.
2. Independently measure M2 thinking effort on a fixed 5-class prompt set at `temperature=0, max_tokens=2048`.
3. Resolve the token-accounting question (`reasoning_tokens` subset vs additional).
4. Find and exercise the correct control path (`chat_template_kwargs.enable_thinking`, `reasoning_effort`).
5. Confirm the service identity on `:30000`.
6. Report honest practical overhead.

**Hard limits honoured:** server touched only via `POST /v1/chat/completions` and `GET /health`, `/v1/models`, `/get_server_info`. No restart/signal/config change. No product-tree edits. **25 completions total**, one bounded run (all batches under 20 min). All scratch confined to `/tmp/opencode/M2-THINKING-VERIFY-20260918/`.

---

## Result (short)

- The prior agent's **per-prompt raw numbers are real and match its raw JSON exactly** (all 5 base prompts, 0 mismatches). Its raw evidence files all exist.
- The prior agent's **interpretation is wrong on three material points**:
  1. **Token double-count** — it added `reasoning_tokens` to `completion_tokens`. `reasoning_tokens` is a **SUBSET** of `completion_tokens`. Honest total is `prompt_tokens + completion_tokens`; this is confirmed by every one of 25 raw responses and by SGLang source.
  2. **"No API control exists" is FALSE.** The correct path is `chat_template_kwargs: {"enable_thinking": false}`, which **genuinely disables thinking** (`reasoning_tokens = 0`, `reasoning_content = null`), and `reasoning_effort: "none"` does the same. The prior agent almost certainly sent `enable_thinking` at the top level (where SGLang ignores it).
  3. **Coding is not "efficient."** With a constrained prompt ("Output only the code") M2 over-deliberates unboundedly: at `max_tokens` 2048 **and** 8192, `completion_tokens == reasoning_tokens == limit`, `content == ""`, `finish_reason == "length"`. The prior agent's low coding ratio came from *unconstrained* prompts (reproduced here), where the model happened to choose a short answer.
- **M2 is systematically overthinking on every class tested**, worst on trivial/extraction/math where **~98% of generated tokens are reasoning**.
- **Control is real and production-usable**: `chat_template_kwargs.enable_thinking=false` yields correct answers with **94–99% fewer completion tokens** and ~7–30× less latency.

---

## Evidence

### E0. Service identity on `:30000` (independent, read-only)

Listener (from `ss -ltnp`):

```
LISTEN 0 2048 0.0.0.0:30000 0.0.0.0:*  users:(("python",pid=1764114,fd=68))
```

Process (from `ps`):

```
1764114 ... -m sglang.launch_server --model-path /data/models/omnicoder-9b-gptq-int4 --host 0.0.0.0 --port 30000
        --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 262144 --context-length 131072
        --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3
        --attention-backend flashinfer ... --reasoning-parser qwen3 --tool-call-parser qwen3_coder ...
```

`GET /health` → `HTTP=200` (file `ev_health.txt`).

`GET /v1/models` (file `ev_models.json`):

```json
{"object":"list","data":[{"id":"/data/models/omnicoder-9b-gptq-int4","object":"model","created":1789727599,"owned_by":"sglang","root":"/data/models/omnicoder-9b-gptq-int4","parent":null,"max_model_len":131072}]}
```

`GET /get_server_info` (selected; file `ev_server_info.txt`):

```json
{
  "model_path": "/data/models/omnicoder-9b-gptq-int4",
  "served_model_name": "/data/models/omnicoder-9b-gptq-int4",
  "reasoning_parser": "qwen3",
  "tool_call_parser": "qwen3_coder",
  "context_length": 131072,
  "max_total_num_tokens": 262144,
  "max_running_requests": 8,
  "version": "0.5.20.dev22+g9c9e7b7c7"
}
```

**FACT:** `:30000` is M2, launched exactly as the dispatch stated (qwen3 reasoning parser, qwen3_coder tool parser, L3/HiCache not present in argv).

### E1. Prior raw evidence — directory listing method and file verification

Method: `ls -la` (directory read). No glob was relied on for absence. The directory contains **11 files**: 9 JSON + `results.md` + `table.md`. Every raw JSON file the prior artifact named exists.

Re-derivation script: `/tmp/opencode/M2-THINKING-VERIFY-20260918/parse_prior.py` (raw output `parse_prior.out`):

```
file | prompt_tokens | completion_tokens | reasoning_tokens | total_tokens | finish_reason | matched_stop | content_len | reasoning_len | reasoning_is_subset | arith_prompt_plus_completion
prompt_01_trivial.json    | 23 | 177  | 174 | 200 | stop | 248046 | 3    | 557  | True | 200
prompt_02_extraction.json | 23 | 429  | 403 | 452 | stop | 248046 | 46   | 1209 | True | 452
prompt_03_reverse.json    | 20 | 459  | 107 | 479 | stop | 248046 | 1352 | 443  | True | 479
prompt_04_cycle.json      | 23 | 1067 | 174 | 1090| stop | 248046 | 3169 | 719  | True | 1090
prompt_05_reasoning.json  | 32 | 555  | 498 | 587 | stop | 248046 | 161  | 1351 | True | 587
prompt_01_suppressed.json | 23 | 3    | 3   | 26  | stop | "Thinking Process:" | 0 | 0 | True | 26
prompt_01_suppressed2.json| 54 | 247  | 244 | 301 | stop | 248046 | 3   | 781  | True | 301
prompt_01_suppressed3.json| 39 | 249  | 246 | 288 | stop | 248046 | 3   | 784  | True | 288
prompt_05_suppressed.json | 55 | 309  | 304 | 364 | stop | 248046 | 5   | 1068 | True | 364

BASE count: 5
SUM completion_tokens: 2687
SUM reasoning_tokens : 1356
SUM prompt_tokens    : 121
Every base reasoning<=completion and total==prompt+completion: True
```

`final_arith.out` (prior table vs raw): each of the 5 base claims matches raw exactly — `MATCH=True` for all five, zero mismatches.

**Negative self-check on the directory method:** my first consolidation glob `[AB]_*` **missed** all `B1..B8` files (they begin with `B` + digit, not `B_`), producing a table with 10 rows instead of 17. I detected the omission by comparing the row set to the file listing and fixed the pattern. The corrected run (`consolidate.out`) has 17 rows. This is recorded as a real method defect that I caught, per "a glob miss is NOT absence."

### E2. Independent measurement — fixed decoding `temperature=0, max_tokens=2048`

Harness: `measure.py` (batch A+B), `aux_probe.py`, `verify2.py`, `verify3.py`. Consolidated: `consolidate.out` / `consolidated.json`.

Full table (content_chars / reasoning_chars are character lengths; `reasoning/completion` is the fraction of generated tokens spent thinking):

| tag | prompt | completion | reasoning | total | finish | content_chars | reasoning_chars | reasoning/completion | total==p+c | reason<=compl |
|---|---|---|---|---|---|---|---|---|---|---|
| A_P1_trivial | 23 | 177 | 174 | 200 | stop | 3 | 557 | 0.983 | True | True |
| A_P2_extraction | 33 | 759 | 744 | 792 | stop | 28 | 2469 | 0.980 | True | True |
| A_P3_coding_simple | 25 | 2048 | 2048 | 2073 | length | 0 | 7925 | 1.000 | True | True |
| A_P4_coding_hard | 29 | 2048 | 2048 | 2077 | length | 0 | 8703 | 1.000 | True | True |
| A_P5_math | 38 | 299 | 294 | 337 | stop | 5 | 808 | 0.983 | True | True |
| B1_ctk_enable_thinking_false_P1 | 25 | 2 | 0 | 27 | stop | 1 | 0 | 0.0 | True | True |
| B2_reasoning_effort_none_P1 | 25 | 2 | 0 | 27 | stop | 1 | 0 | 0.0 | True | True |
| B3_reasoning_effort_low_P1 | 23 | 177 | 174 | 200 | stop | 3 | 557 | 0.983 | True | True |
| B4_toplevel_enable_thinking_false_P1 | 23 | 177 | 174 | 200 | stop | 3 | 557 | 0.983 | True | True |
| B5_stop_seq_P1 | 23 | 3 | 3 | 26 | stop | 0 | 0 | 1.000 | True | True |
| B6_reasoning_effort_none_P5 | 40 | 4 | 0 | 44 | stop | 3 | 0 | 0.0 | True | True |
| B7_ctk_enable_thinking_false_P5 | 40 | 4 | 0 | 44 | stop | 3 | 0 | 0.0 | True | True |
| C1_repeat_P1_baseline | 23 | 177 | 174 | 200 | stop | 3 | 557 | 0.983 | True | True |
| C2_P3_max8192 | 25 | 8192 | 8192 | 8217 | length | 0 | 31712 | 1.000 | True | True |
| C3_P4_max8192 | 29 | 8192 | 8192 | 8221 | length | 0 | 28464 | 1.000 | True | True |
| C4_P3_ctk_false | 27 | 23 | 0 | 50 | stop | 67 | 0 | 0.0 | True | True |
| C5_P4_ctk_false | 31 | 108 | 0 | 139 | stop | 434 | 0 | 0.0 | True | True |
| D1_P2_extraction_ctk_false | 35 | 14 | 0 | 49 | stop | 26 | 0 | 0.0 | True | True |
| D2_P3_effort_none | 27 | 23 | 0 | 50 | stop | 67 | 0 | 0.0 | True | True |
| D3_ctk_thinking_false_only_P1 | 23 | 177 | 174 | 200 | stop | 3 | 557 | 0.983 | True | True |
| D4_ctk_both_false_P1 | 25 | 2 | 0 | 27 | stop | 1 | 0 | 0.0 | True | True |
| E1_P3_unconstrained | 20 | 445 | 107 | 465 | stop | 1244 | 443 | 0.240 | True | True |
| E2_P4_unconstrained | 24 | 889 | 156 | 913 | stop | 2565 | 654 | 0.175 | True | True |
| E3_P2_unconstrained | 24 | 974 | 948 | 998 | stop | 46 | 3162 | 0.973 | True | True |

**ALL rows observable `total==prompt+completion`: True. ALL rows `reasoning<=completion`: True.**

Prompts used (verbatim):
- P1_trivial: `What is 2+2? Answer with just the number.`
- P2_extraction: `Extract name and age as JSON from this text: name=Ada, age=36. Output JSON only.`
- P3_coding_simple: `Write a Python function that reverses a string. Output only the code.`
- P4_coding_hard: `Write a Python function that detects a cycle in a singly linked list. Output only the code.`
- P5_math: `A train travels at 60 km/h for 2.5 hours. How far does it travel? Answer with just the number.`
- Unconstrained variants (E1/E2/E3) drop the "Output only ..." constraint to test whether the prior coding numbers came from that wording.

Determinism control: `A_P1_trivial.json` and `C1_repeat_P1_baseline.json` are byte-identical in `reasoning_content`, `content`, and usage (verified in `measure.out` follow-up check: `reasoning identical: True`, `content identical: True`). At `temperature=0` the model output is reproducible, so single-sample measurements are valid for this task.

Wall-clock latency (from `summary.json`):
- trivial baseline 2.312 s → disabled 0.132 s
- extraction baseline 9.405 s → disabled 0.346 s
- math baseline 3.705 s → disabled 0.256 s
- coding (constrained) baseline 24.7 s (truncated, no answer) → disabled 0.385 s / 1.411 s with answers
- stop-sequence truncation 0.250 s with **empty content**

### E3. Token accounting — explicit resolution

**FACT (source, project tree read-only):**
- `python/sglang/srt/managers/tokenizer_manager.py:3247` — `meta_info["completion_tokens"] = len(output_ids)` (all generated tokens).
- `python/sglang/srt/managers/schedule_batch.py:1942-1961` — `update_reasoning_tokens()` increments a counter as tokens are generated until the `</think>` matcher completes; it is a running prefix count, bounded by total generated tokens.
- `python/sglang/srt/entrypoints/openai/usage_processor.py:120-125` — `total_tokens = prompt_tokens + completion_tokens`; `reasoning_tokens` is passed through separately, **not added**.
- `python/sglang/test/kits/reasoning_kit.py:72-73` — the project's own test asserts `reasoning_tokens < completion_tokens` (thinking) and `== 0` (non-thinking).

**FACT (observed):** in all 25 responses, `total_tokens == prompt_tokens + completion_tokens` exactly, and `reasoning_tokens <= completion_tokens`. Example raw (prior + my own agree):

```json
"usage":{"prompt_tokens":23,"total_tokens":200,"completion_tokens":177,"prompt_tokens_details":null,"reasoning_tokens":174}
```

**CONCLUSION:** `reasoning_tokens` is a **SUBSET** of `completion_tokens`. It is the count of generated tokens up to and including `</think>`; the remainder of `completion_tokens` is the answer (`content`) plus format tokens. The honest total token cost is `prompt_tokens + completion_tokens`. Adding `reasoning_tokens` again (as the prior artifact did) double-counts.

**Honest thinking overhead:**
- Trivial: 174/177 = **98.3% of generated tokens are thinking**; reasoning is 174/200 = **87.0% of the whole request cost**. Disabled cost is 27 tokens, so honest overhead is `200 − 27 = 173` tokens ≈ **7.4×**.
- Extraction (constrained): 744/759 = **98.0%**; disabled 49 tokens → overhead 743 ≈ **16.2×**.
- Math: 294/299 = **98.3%**; disabled 44 tokens → overhead 293 ≈ **7.7×**.
- Mean reasoning share over the three answerable classes = **98.2%**.

(For P1, `content="\n\n4"` is 3 characters = 2 tokens `[271, 19]`, confirmed with the served tokenizer. So the prior artifact's "174 reasoning tokens / 2 completion tokens ≈ 87×" used the answer-only denominator, not the actual completion; it is not a token-accounting statement and should not be quoted as one.)

### E4. Correct control path (the prior agent tested the wrong place)

Model template read from `/data/models/omnicoder-9b-gptq-int4/chat_template.jinja` lines 147-153:

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

Rendered template proof (`render_template.py` / `render_template.out`, exact reprs):

```
render()                       -> ...'<|im_start|>assistant\n<think>\n'
render(enable_thinking=False)  -> ...'<|im_start|>assistant\n<think>\n\n</think>\n\n'
baseline endswith '<think>\n': True
toggle  endswith '</think>':   True
```

When disabled, the template prefills a closed empty think block, so the parser attributes zero tokens to reasoning.

Server-side detection (read-only, `detect_reasoning_pattern` from the served template):

```
force_reasoning = False
reasoning_config = ReasoningToggleConfig(toggle_param='enable_thinking', default_enabled=True, special_case=None, effort_kwarg=None)
```

**Verbatim request that WORKS** (raw response file `B1_ctk_enable_thinking_false_P1.json`):

```json
{"model": "/data/models/omnicoder-9b-gptq-int4",
 "messages": [{"role":"user","content":"What is 2+2? Answer with just the number."}],
 "temperature": 0, "max_tokens": 2048,
 "chat_template_kwargs": {"enable_thinking": false}}
```

Response (verbatim, trimmed to the decision-relevant fields):

```json
{"id":"8dac98e247e7431eb12632f8368e5ed5","object":"chat.completion","model":"/data/models/omnicoder-9b-gptq-int4",
 "choices":[{"index":0,"message":{"role":"assistant","content":"4","reasoning_content":null,"tool_calls":null},
 "finish_reason":"stop","matched_stop":248046}],
 "usage":{"prompt_tokens":25,"total_tokens":27,"completion_tokens":2,"prompt_tokens_details":null,"reasoning_tokens":0}}
```

`reasoning_effort: "none"` produces the identical effect (`B2_reasoning_effort_none_P1.json`, usage `{prompt:25,total:27,completion:2,reasoning:0}`; `content:"4"`). Both keys are set by SGLang's protocol normalizer when a caller uses `reasoning_effort:"none"` (`protocol.py:1029-1038`).

**Effective vs ineffective controls (all measured):**

| Control | Result | Evidence |
|---|---|---|
| `chat_template_kwargs:{"enable_thinking":false}` | **WORKS** — reasoning 174→0, completion 177→2, content "4" | `B1`, `B7`, `D1`, `C4`, `C5`, `D2` |
| `reasoning_effort:"none"` | **WORKS** — same as above | `B2`, `B6`, `D2` |
| `reasoning_effort:"low"` | **IGNORED** — byte-identical to baseline (reasoning 174) | `B3` |
| top-level `"enable_thinking":false` | **IGNORED** — baseline unchanged (reasoning 174) | `B4` |
| `chat_template_kwargs:{"thinking":false}` (wrong key) | **IGNORED** — baseline unchanged; template only reads `enable_thinking` | `D3` |
| `stop:["Thinking Process:"]` | **TRUNCATES ONLY** — reasoning 174→3, `content:""` (empty), `matched_stop:"Thinking Process:"`; not usable | `B5` |

`reasoning_effort` acceptance is validated (negative self-check `B8_negative_invalid_effort.json`, HTTP **400**), verbatim server error:

```
2 validation errors:
  {'type': 'literal_error', 'loc': ('body', 'reasoning_effort', "literal['none','minimal','low','medium','high','xhigh','max']"),
   'msg': "Input should be 'none', 'minimal', 'low', 'medium', 'high', 'xhigh' or 'max'", 'input': 'banana',
   'ctx': {'expected': "'none', 'minimal', 'low', 'medium', 'high', 'xhigh' or 'max'"}}
  {'type': 'float_parsing', 'loc': ('body', 'reasoning_effort', 'constrained-float'),
   'msg': 'Input should be a valid number, unable to parse string as a number', 'input': 'banana'}
```

The strong contrast is decisive: `reasoning_effort:"none"` → 0 reasoning; `reasoning_effort:"banana"` → 400. The field is parsed and honored; there is no effort *tier* below "none" because the template declares `effort_kwarg=None`.

**Three-way distinction requested:**
- (i) **Real control that reduces reasoning:** `chat_template_kwargs.enable_thinking=false` and `reasoning_effort="none"` — genuine, answer preserved.
- (ii) **`stop` sequences that merely cut generation:** confirmed `B5`; returns empty `content`, unusable in production.
- (iii) No control: **not applicable** — control exists.

### E5. New finding the prior artifact missed — constrained coding is a reasoning spiral

The prior agent used unconstrained coding prompts and concluded coding is "efficient" (ratios 0.23 / 0.16). I reproduced that with E1/E2 (0.240 / 0.175). But with the explicit constraint "Output only the code," M2 does **not** emit code at all:

```json
{"tag":"A_P3_coding_simple","completion_tokens":2048,"reasoning_tokens":2048,"finish_reason":"length","content_len":0}
{"tag":"A_P4_coding_hard",  "completion_tokens":2048,"reasoning_tokens":2048,"finish_reason":"length","content_len":0}
{"tag":"C2_P3_max8192",     "completion_tokens":8192,"reasoning_tokens":8192,"finish_reason":"length","content_len":0}
{"tag":"C3_P4_max8192",     "completion_tokens":8192,"reasoning_tokens":8192,"finish_reason":"length","content_len":0}
```

At 8192 tokens the `reasoning_content` is 31,712 / 28,464 chars and still no answer. With `enable_thinking=false`, both prompts answer correctly in 23 / 108 completion tokens (`C4`, `C5`):

```
C4_P3_ctk_false content:
```python
def reverse_string(s: str) -> str:
    return s[::-1]
```

C5_P4_ctk_false content:
```python
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

def has_cycle(head: ListNode) -> bool:
    ...
```
```

**FACT:** for constrained-output coding, baseline is unusable (no content, length-capped); the toggle fixes it. **INFERENCE (marked):** the "code output only" constraint appears to trigger the spiral; with only 2 prompts per condition I cannot claim a robust prompt-constraint law — see exclusions.

### E6. Is M2 systematically overthinking?

**FACT / verdict: YES, on every class measured.**
- Trivial, extraction, math: **~98% of generated tokens are reasoning**; 7–16× total token overhead vs the disabled control.
- Coding (constrained): pathological — consumes the entire budget as reasoning with zero answer; not merely "overthinking" but non-terminating.
- Coding (unconstrained): reasoning share drops to 17–24% and answers appear, so severity is prompt-dependent, not class-intrinsic.

### E7. Honest practical overhead for everyday worker traffic

If worker traffic is sent **without** the toggle, per request:
- trivial: +173 tokens, ~2.31 s vs ~0.13 s
- extraction: +743 tokens, ~9.41 s vs ~0.35 s
- math: +293 tokens, ~3.71 s vs ~0.26 s
- coding with "output only" constraint: truncated, **no answer delivered** (hazard)

With `chat_template_kwargs:{"enable_thinking":false}` (or `reasoning_effort:"none"`): thinking is eliminated, answers are correct, and **94–99% of completion tokens are removed**. There is no need to accept the overhead.

---

## Corrections to the prior artifact

1. **Token double-count (material).** Prior line 169: `"23 prompt + 177 completion + 174 reasoning = 351 tokens"`.
   - Correct: `total_tokens = 23 + 177 = 200`. `reasoning_tokens=174` is inside `completion_tokens`. (Also, 23+177+174 = 374, so even the stated 351 was arithmetically wrong.)
2. **"No API-based thinking control" (material, false).** Prior lines 14, 102-103, 152-153, 181. `enable_thinking` **is** honored — but via `chat_template_kwargs`, not top-level. `reasoning_effort:"none"` is also honored. Evidence: `B1`, `B2`, `B6`, `B7`, `D1`, `D2`.
3. **"Stop sequences WORK" conflated with suppression (material).** Prior lines 78, 149. `stop` produced `reasoning_tokens:3` with `content:""`; that is truncation, not reasoning reduction, and is not production-usable. Real reduction is `enable_thinking=false` → 0 reasoning with a valid answer.
4. **Self-contradictory aggregate (material).** Prior line 12: `"74% of completion spans generate significant reasoning_tokens (>400/177 ratio = 2.34x overhead on trivial)"`. 400/177 = 2.26, and the sentence mixes extraction (403) with trivial (177). Prior line 174-175 also mixes incompatible denominators ("17,550 reasoning tokens waste", "~189 total tokens vs 177 base = 12 token overhead").
5. **Coding characterization incomplete (material).** Prior lines 57, 63, 137-138 call coding "efficient / LOW thinking ratio." True only for unconstrained prompts. Constrained-output coding is the worst case (zero content, full budget consumed as reasoning).
6. **Aggregate totals were numerically right (not a correction):** `SUM completion_tokens=2687`, `SUM reasoning_tokens=1356`, `SUM reasoning_characters=4279`, mean ratio 0.64 all recompute correctly from raw. Their error is that these are reasoning *subset* sums, not additive cost. In particular `1356/2687 = 50.4%` of generated tokens were reasoning across the prior 5 prompts; the artifact's own "average think_ratio 0.64" is the unweighted mean of per-prompt ratios, a different (and misleading) statistic.
7. **EOF injection/leak.** The prior artifact ends with a literal malformed `<tool_call>` / `<function=bash>` fragment (lines 219-220). This is a tool-call leak into the authored document, evidence of an incomplete tool invocation. It does not by itself invalidate the measurements, but it corroborates that the artifact was not cleanly finalized.
8. **File-inventory accuracy:** all 9 claimed JSON files exist; directory listing also contains `results.md` (2 lines, effectively empty) and `table.md` (a scratch print, not the artifact table). No claimed file was missing. This part of the prior record is accurate.

---

## Defects / blockers

1. **M2 baseline is unusable for constrained-output coding** without the toggle: full token budget consumed as reasoning, `finish_reason="length"`, empty `content`. Confirmed at 2048 and 8192. Production hazard, not just overhead.
2. **No per-tier `reasoning_effort` gradation for this model.** `effort_kwarg=None`; `"none"` is the only effective value; `"low"` is silently equivalent to default-on. Callers who set `"low"` get no savings.
3. **Top-level `enable_thinking` silently ignored** (HTTP 200, no warning in the response). Easy to misconfigure — this is the exact trap the prior agent fell into.
4. **No control over the *amount* of thinking** once enabled; only on/off. The model has no soft thinking-budget knob.
5. `results.md` and `table.md` in the prior evidence dir are stale/incomplete scratch, not results.

## Remaining claims / exclusions

- **Excluded:** only 5 base prompts + a small set of controls; not a statistically representative corpus. The "98%" figure is per-prompt and consistent across 3 classes, but class-level generalization is **INFERENCE**.
- **Excluded:** `reasoning_effort` values `minimal/medium/high/xhigh/max` were not exercised end-to-end. Source (`protocol.py:1025-1038`) shows any value except `"none"` maps to `enable_thinking=True`, so I claim only `"none"` is effective — marked as source-backed inference.
- **Excluded:** streaming usage, tool-calling paths, multi-turn/history thinking, and `response_format` were not tested (prior agent claimed `response_format` was ignored; I did not independently verify that and do not adopt it).
- **Not independently verified:** the prior artifact's character-count columns beyond the base 5 (I verified the base 5 exactly).
- **No claim about M1 or other models.**
- The prompt class labels in the prior `table.md` are stored in a transposed/awkward order; I did not rely on `table.md`.

## Changed-artifact list

- **Created (scratch only):** `/tmp/opencode/M2-THINKING-VERIFY-20260918/` — 25 raw response JSON files (`A_*`, `B*`, `C*`, `D*`, `E*`), `summary.json`, `aux_summary.json`, `verify2_summary.json`, `verify3_summary.json`, `consolidated.json`, scripts (`parse_prior.py`, `measure.py`, `aux_probe.py`, `verify2.py`, `verify3.py`, `consolidate.py`, `render_template.py`, `final_arith.py`) and their `.out` logs, `ev_*` files. No files written outside this scratch dir.
- **Created (authoritative handoff):** this file only —
  `.memory/phase2-hicache-design/agents/M2-THINKING-VERIFY-20260918.md`
- **No product source, tests, config, ledger, or server state was modified.** (`git status` shows only pre-existing changes from other agents; nothing added by this task outside `.memory/.../agents/`.)

## Raw evidence file reference (all under `/tmp/opencode/M2-THINKING-VERIFY-20260918/`)

- Baseline: `A_P1_trivial.json`, `A_P2_extraction.json`, `A_P3_coding_simple.json`, `A_P4_coding_hard.json`, `A_P5_math.json`
- Controls: `B1_ctk_enable_thinking_false_P1.json`, `B2_reasoning_effort_none_P1.json`, `B3_reasoning_effort_low_P1.json`, `B4_toplevel_enable_thinking_false_P1.json`, `B5_stop_seq_P1.json`, `B6_reasoning_effort_none_P5.json`, `B7_ctk_enable_thinking_false_P5.json`, `B8_negative_invalid_effort.json`
- Determinism / budget / coding controls: `C1_repeat_P1_baseline.json`, `C2_P3_max8192.json`, `C3_P4_max8192.json`, `C4_P3_ctk_false.json`, `C5_P4_ctk_false.json`
- Key hypothesis: `D1_P2_extraction_ctk_false.json`, `D2_P3_effort_none.json`, `D3_ctk_thinking_false_only_P1.json`, `D4_ctk_both_false_P1.json`
- Unconstrained replays of prior coding/extraction: `E1_P3_unconstrained.json`, `E2_P4_unconstrained.json`, `E3_P2_unconstrained.json`
- Consolidated/derived: `consolidate.out`, `consolidated.json`, `parse_prior.out`, `render_template.out`, `final_arith.out`, `measure.out`, `aux_probe.out`, `verify2.out`, `verify3.out`, `summary.json`
- Service/GET evidence: `ev_health.txt`, `ev_models.json`, `ev_server_info.txt`

**Prior evidence dir verified in place (unmodified):** `/tmp/opencode/M2-THINKING-20260918/` (11 files).

---

**Terminal state: DONE**
