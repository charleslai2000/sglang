# REASONING-EFFORT-POLICY-IMPL-20260918

Task: Fix the fake graded `reasoning_effort` for M1/M2 into a real, model-specific reasoning
policy for the Qwen3.5 family, using a narrow policy plus the existing SGLang thinking-budget
infrastructure. This is a runtime policy, NOT a native model capability and NOT a claim that the
weights were trained to obey it.

- Date: 2026-09-18
- Role: `debugger-deep` under an explicit owner-authorized edit grant limited to the write domain below
- Tree edited: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`
- Served tree (`/opt/sglang/local-prod-v1.2.1-candidate`) was read-only reference and is byte-unchanged
- Terminal state: **DONE**

## Scope

Authorized write domain (smallest set, each genuinely on the effort/policy/budget path):

| File | Status | Why |
|---|---|---|
| `python/sglang/srt/parser/qwen35_reasoning_policy.py` | new | The narrow Qwen3.5 policy resolver (tier -> enable_thinking + steering + max_thinking_tokens). |
| `python/sglang/srt/sampling/custom_logit_processor.py` | modified | Added `Qwen35ThinkingBudgetLogitProcessor` (real Qwen3.5 ids 248068/248069) beside the existing processors; no framework change. |
| `python/sglang/srt/entrypoints/openai/serving_chat.py` | modified | Wiring: resolve policy, merge steering, set template toggle, route the budget through the existing mechanism. |
| `python/sglang/srt/environ.py` | modified | `SGLANG_QWEN35_EFFORT_POLICY` (provisional, configurable ladder). |
| `test/registered/unit/parser/test_qwen35_reasoning_policy.py` | new | Deterministic CPU tests (policy, processor, serving wiring, real M1/M2 render). |

Explicitly NOT touched: `/opt/**`, `/data/**`, git history/commits, the running server/port 30000,
`mem_cache/**` (another agent owns it; its pre-existing modifications are untouched), `.memory/**`
other than this artifact, the ledger, protocol.py (no change needed), and no final budget decision.

## Required work, step 1 — the real production call chain (repo tree, exact file:line)

**A. `reasoning_effort` from HTTP request to rendered prompt**

1. `python/sglang/srt/entrypoints/openai/protocol.py:823` `class ChatCompletionRequest` — field
   declared at `:869`; `ReasoningEffortTier` at `:793`; float union at `:803`.
2. `protocol.py:1025-1038` — the ONLY generic materialization: `thinking = effort != "none"`, then
   `ctk.setdefault("thinking"/"enable_thinking", thinking)`. This is why every graded tier collapsed
   to identical behaviour. **Unchanged** by this task (the new policy runs downstream and is narrow).
3. `protocol.py:976-981` rejects boolean; `:983-1023` normalizes nested `reasoning={...}`.
4. `serving_chat.py:971-982` — pops `chat_template_kwargs.reasoning_effort` into
   `request.reasoning_effort` (post-validation).
5. `serving_chat.py:1144-1146` (**new**) — `_resolve_qwen35_policy` (`:2550`) /
   `_apply_qwen35_policy_to_request` (`:2603`).
6. `serving_chat.py:1144` — policy applied before `_get_reasoning_from_request`
   (`serving_chat.py:2469`) reads the toggle, so `require_reasoning` sees `enable_thinking`.
7. `serving_chat.py:1271-1273` (**new**) — `_merge_qwen35_steering` (`:2628`) merges the steering
   prompt into the first system message.
8. `serving_chat.py:1358-1361` — forwards `reasoning_effort` + ctk into
   `apply_chat_template` (`:1386-1393`). Generic `effort_kwarg` branch at `:1363-1373` stays dead
   for this model (`effort_kwarg=None`), as before.

**B. `max_thinking_tokens` -> `thinking_budget` -> logit processor**

1. `io_struct.py:302` — `GenerateReqInput.max_thinking_tokens`.
2. `tokenizer_manager.py:781-789` — rejects it unless `--enable-strict-thinking`.
3. `tokenizer_manager.py:1357-1361` — maps it to `custom_params["thinking_budget"]`.
4. `schedule_batch.py:938-942` — injects `__req__` into `custom_params`.
5. `sampling_batch_info.py:143-176` — selects processors only when
   `get_exec().features.enable_custom_logit_processor` and some request supplied one.
6. `layers/sampler.py:782-799` — applies the processor with `custom_params`.
7. `sampling/custom_logit_processor.py:71-120` — `ThinkingBudgetLogitProcessor` forces newline then
   `</think>` when the budget is hit, i.e. the normal answer transition.
   **New** subclass at `:139` uses Qwen3.5 ids.
8. `serving_chat.py:1013-1029` (**new**) — `_plan_qwen35_budget` (`:2652`) picks strict vs processor
   vs none, and `:1110` passes `max_thinking_tokens` into `GenerateReqInput`.

**C. Chat template + reasoning parser actually used by M1 and M2**

- Template file (both models, byte-identical): `/data/models/{qwen35-9b-w4a16,omnicoder-9b-gptq-int4}/chat_template.jinja`
  sha256 `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715` (read-only; NOT modified).
  The only control is `enable_thinking` at lines 147-153 (`<think>\n\n</think>\n\n` when false).
- Parser: `qwen3` (`python/sglang/srt/parser/reasoning_parser.py:355-399`, `Qwen3Detector`).
- Detection: `parser/template_detection.py` -> `ReasoningToggleConfig(toggle_param='enable_thinking',
  default_enabled=True, effort_kwarg=None)`.
- Token ids (verified with the real tokenizers, `AutoTokenizer`, CPU):
  `<think>` -> `[248068]`, `</think>` -> `[248069]`, `\n` -> `[198]`. Qwen3's 151667/151668 are NOT
  think markers on this model and are NOT used.

## Required work, steps 2-5 — the narrow policy and budget

- Input: `reasoning_effort`. Output: `enable_thinking` (bool), `steering` (str), `max_thinking_tokens`
  (Optional[int]).
- `none` -> thinking OFF (binding) and no steering and no budget. Other tiers -> thinking ON.
- It is NO LONGER possible for different graded tiers to produce an identical prompt+budget:
  each graded tier has a distinct `(steering, budget)` pair.
- Qwen3.8-style steering (RUNTIME POLICY, NOT native behaviour):
  - low/minimal: "Keep your reasoning concise and focused; avoid unnecessary elaboration."
  - medium: neutral / default (empty steering).
  - high/xhigh/max: "Reason carefully and thoroughly: check your work, consider alternative
    approaches, and verify your assumptions before giving the final answer."
- Budget reuses the existing `ThinkingBudgetLogitProcessor` via the new Qwen3.5 subclass; when the
  budget is reached it forces `\n` then `</think>`, transitioning to the answer rather than
  truncating the whole generation. On a launch with neither `--enable-strict-thinking` nor
  `--enable-custom-logit-processor`, the prompt-level policy still applies and the budget is not
  attached (no fail-closed 400); that condition is warned once per process.

### Effective policy per effort tier (provisional; token counts are EXPERIMENTAL)

| effort | enable_thinking | steering | max_thinking_tokens |
|---|---|---|---|
| `none` | false | — | — |
| float `0.0` | false | — | — |
| `minimal` | true | low/concise | 256 |
| `low` | true | low/concise | 512 |
| `medium` | true | neutral (empty) | 2048 |
| `high` | true | thorough/verify | 8192 |
| `xhigh` | true | thorough/verify | 8192 |
| `max` | true | thorough/verify | 16384 |
| unset | no policy (default template behaviour, unchanged) | — | — |
| float `(0,0.34)` / `[0.34,0.67)` / `[0.67,1.0)` | true | low / neutral / thorough | 512 / 2048 / 8192 |

`SGLANG_QWEN35_EFFORT_POLICY` (JSON) overrides these; unknown keys are ignored. The final
production ladder is deliberately NOT decided here.

## Required work, step 6 — deterministic verification

Environment for all commands:
`/opt/sglang/local-prod-v1/env/bin/python`, `CUDA_VISIBLE_DEVICES=999`, `PYTHONDONTWRITEBYTECODE=1`.
CPU-only, no server, no GPU.

### FAIL-BEFORE (new module temporarily removed; reversible move, then restored)

```
$ pytest test/registered/unit/parser/test_qwen35_reasoning_policy.py -q -p no:cacheprovider
==================================== ERRORS ====================================
___ ERROR collecting registered/unit/parser/test_qwen35_reasoning_policy.py ____
ImportError while importing test module '.../test_qwen35_reasoning_policy.py'.
test/registered/unit/parser/test_qwen35_reasoning_policy.py:28: in <module>
    from sglang.srt.parser.qwen35_reasoning_policy import (
E   ModuleNotFoundError: No module named 'sglang.srt.parser.qwen35_reasoning_policy'
17 warnings, 1 error in 17.75s
EXIT=2
```
Module restored; final sha256 recorded below.

### PASS-AFTER — policy test file (33 tests, includes real M1/M2 renders)

```
$ pytest test/registered/unit/parser/test_qwen35_reasoning_policy.py -q -p no:cacheprovider
33 passed, 21 warnings, 8 subtests passed in 25.56s
```
All 33 verbose results (excerpt of the last lines):
```
test_...::TestRealQwen35TemplateRender::test_real_think_token_ids PASSED
test_...::TestRealQwen35TemplateRender::test_none_closes_think_block_and_graded_tiers_differ PASSED
test_...::TestRealQwen35TemplateRender::test_tools_render_and_budget_is_separate_from_tool_markup PASSED
test_...::TestRealQwen35TemplateRender::test_legacy_graded_tiers_were_byte_identical PASSED
============= 33 passed, 21 warnings, 8 subtests passed =============
```
The real-model tests only run when `/data/models/qwen35-9b-w4a16` and
`/data/models/omnicoder-9b-gptq-int4` exist; here they ran (8 subtests = 4 per model, and the
subtests passed).

### Existing regression suites (verbatim)

```
$ pytest test/registered/unit/sampling/test_custom_logit_processor.py -q -p no:cacheprovider
35 passed, 17 warnings in 17.37s

$ pytest test/registered/unit/entrypoints/openai/test_serving_chat.py -q -p no:cacheprovider
114 passed, 43 warnings, 61 subtests passed in 17.26s
```

Combined targeted run (9 suites in the effort/budget/serving/template paths):
```
$ pytest test/registered/unit/parser/test_qwen35_reasoning_policy.py \
    test/registered/unit/sampling/test_custom_logit_processor.py \
    test/registered/unit/entrypoints/openai/test_serving_chat.py \
    test/registered/unit/entrypoints/openai/test_protocol.py \
    test/registered/unit/entrypoints/openai/test_serving_responses.py \
    test/registered/unit/constrained/test_grammar_manager.py \
    test/registered/unit/constrained/test_reasoner_grammar_backend.py \
    test/registered/unit/test_environ.py \
    test/registered/unit/parser/test_template_manager.py -q -p no:cacheprovider
384 passed, 55 warnings, 151 subtests passed in 78.99s (0:01:18)
```

Runtime-context/ratchet suites:
```
$ pytest test/registered/unit/test_environ.py test/registered/unit/test_global_config_read_ratchet.py \
    test/registered/unit/test_publish_precedes_bag_reads.py \
    test/registered/unit/test_supplied_instance_exposure_ratchet.py \
    test/registered/unit/test_legacy_global_ratchet.py -q -p no:cacheprovider
19 passed, 17 warnings, 2 subtests passed in 34.24s
```

`py_compile` on every changed file + the new test:
```
$ python -m py_compile python/sglang/srt/parser/qwen35_reasoning_policy.py \
    python/sglang/srt/sampling/custom_logit_processor.py \
    python/sglang/srt/entrypoints/openai/serving_chat.py \
    python/sglang/srt/environ.py \
    test/registered/unit/parser/test_qwen35_reasoning_policy.py
PY_COMPILE_ALL_OK exit=0
```

### Real-template probes (offline, both M1 and M2)

**Legacy fake behaviour (forwarding only `reasoning_effort` to `apply_chat_template`):**
```
$ python /tmp/opencode/REASONING-EFFORT-POLICY-IMPL-20260918/legacy_fake_probe.py
M1 unique= 1 all_identical= True  none_differs= False
M2 unique= 1 all_identical= True  none_differs= False
```
All six graded tiers render the identical prompt sha256 `a5b037bd82a312839e7ce27bc28f55b52278f2cf4dee32e5957720bca2c0d00b`
for both models. (`none` is also identical here because this probe bypasses the protocol
materialization; in the real served path `protocol.py:1025-1038` already handled `none`.)

**Policy behaviour (tier -> enable_thinking + steering + budget, then render):**
```
$ python /tmp/opencode/REASONING-EFFORT-POLICY-IMPL-20260918/policy_render_probe.py
M1 unique= 4  low/med/high distinct= True  none!=high= True
M2 unique= 4  low/med/high distinct= True  none!=high= True
```
(The 4 unique renders are none / low / medium / high; minimal==low, xhigh==high, max==high in
prompt text by design, distinguished by budget. This is intentional: budget, not synonyms, is the
gradation for those aliases.)

### Negative self-check (real output, non-Qwen3.5 families inert)

```
model_type='qwen3': policy=None
model_type='llama': policy=None
model_type='nemotron_3': policy=None
model_type='mistral': policy=None
model_type='gpt_oss': policy=None
qwen3_5 with non-enable_thinking toggle: None
Q35 ids: 248068 248069
Q3  ids: 151667 151668
wrong-id match Q35==Q3: False
toggle param: enable_thinking
```

### Real config-leaf resolution (production correctness, not mock)

```
enable_strict_thinking -> False
enable_custom_logit_processor -> False
defaults are False: True True
```

### Required check coverage (owner step 6)

| Requirement | Result | Evidence |
|---|---|---|
| `none` really disables thinking | VERIFIED offline (render + resolver + serving kwarg) | `test_none_disables_thinking`; real render `none` contains `<think>\n\n</think>`; probe `none!=high=True` |
| low/medium/high differ genuinely in prompt and/or budget | VERIFIED | resolver test; serving `repr(messages)+budget` distinct; real probe 4 unique renders |
| on budget exhaustion the model still produces a final answer | VERIFIED at logit-processor level; NOT run through model weights | processor test forces `\n` then `</think>` (answer transition), post-transition tokens untouched |
| tool calling not broken by the budget transition | VERIFIED at render + processor level | real-template tools test asserts `get_weather` + `<tool_call>` render; processor test shows post-`</think>` no-op |
| wrong Qwen3 token ids not used | VERIFIED | processor ids 248068/248069; assertions `!=` 151667/151668; real tokenizer ids match |
| other families unaffected | VERIFIED | negative self-check all `policy=None`; `test_other_family_untouched` shows ctk unchanged |

## Required work, step 7 — what was NOT verified

- **The LIVE served behaviour of the new policy on :30000 is NOT verified.** No server restart was
  performed (forbidden). The live server is still the old code and still exhibits the old inert
  tiers.
- The budget's end-to-end effect on real generation (does the model actually answer once
  `</think>` is forced at token N?) is NOT verified — that is the follow-up calibration's job.
- On the current live launch neither budget flag is set, so the budget cannot be enforced there
  even after deploying this code; only the prompt-level policy (steering + toggle) would apply.
  That is a deliberate no-fail-closed choice, but it means deploying this code alone does not by
  itself enforce token budgets.
- `/v1/responses` and the Anthropic surface get the prompt-level policy through `_process_messages`
  but do not route a budget (they build their own generation requests). Not tested, marked as
  out-of-scope for this narrow fix.
- Streaming, multi-turn reasoning history, and float-effort calibration against real outputs were
  not exercised.
- M1 runtime remains unverified (M1 is not served); M1 coverage here is static/render-level only.
- `black`/`ruff`/`isort` are NOT installed in the offline interpreter (`No module named ...`), so
  formatting was kept to 88 columns manually (all new/changed lines checked <=88).

## Evidence discipline

Real `sha256sum` BEFORE -> AFTER for each changed file (hashes are the real output):

| File | BEFORE | AFTER |
|---|---|---|
| `serving_chat.py` | `7b05e6ab1d09a71ce253040c9cd62ea7c55a52020b44cf9b76d91c8df9e23240` | `7069e941fe3525a9fae230989fcbddf1c14c4f80711cf43a97f3295adbe713f2` |
| `custom_logit_processor.py` | `e0e0ab65e2ded8975a9d161a52c92cb61f2a8a02a6af485b37912cad1171e23d` | `2106810601b65f488d5b4972d7628e1aae201713cb8cd370ba909255d1bf8693` |
| `environ.py` | (git HEAD) | `dd97145e844a61ce00654daf915b291a69d6f7c90730b74ff184fa595e8779dd` |
| `qwen35_reasoning_policy.py` | ABSENT | `968bea87d50db29351a2156187fa2c782fa76e5ed896abeb92b4f1f8a452e22d` |
| `test_qwen35_reasoning_policy.py` | ABSENT | `8bec7cf80b56bb3d99ccb534fbb03a271a0de77bc5ebe6b433fdad82a12cf4e5` |

Real `git diff --numstat` for the modified files:
```
181	0	python/sglang/srt/entrypoints/openai/serving_chat.py
6	0	python/sglang/srt/environ.py
14	0	python/sglang/srt/sampling/custom_logit_processor.py
```
Scoped `git status --short`:
```
 M python/sglang/srt/entrypoints/openai/serving_chat.py
 M python/sglang/srt/environ.py
 M python/sglang/srt/sampling/custom_logit_processor.py
?? python/sglang/srt/parser/qwen35_reasoning_policy.py
?? test/registered/unit/parser/test_qwen35_reasoning_policy.py
```

Live server unaffected (read-only probe):
```
$ curl -s --max-time 8 http://127.0.0.1:30000/health -o /dev/null -w "health_http=%{http_code}\n"
health_http=200
LISTEN 0 2048 0.0.0.0:30000 ... users:(("python",pid=1764114,fd=68))
```
Served frozen file unchanged: `/opt/.../serving_chat.py` still `7b05e6ab...` (== pre-change repo hash).
`mem_cache/**` pre-existing modifications were not touched by this task.

## FACTS vs INFERENCE

- **FACT:** before the fix, real M1/M2 templates produced one identical prompt for all six graded
  tiers (probe + hashes above).
- **FACT:** the new resolver maps tiers to distinct `(steering, budget)` and the real templates now
  render distinct prompts for none/low/medium/high.
- **FACT:** the new processor uses 248068/248069 and transitions to `</think>` rather than
  truncating.
- **FACT:** the policy is inert for qwen3/llama/nemotron/mistral/gpt_oss and for a Qwen3.5 model
  whose template lacks `enable_thinking`.
- **FACT:** the live served behaviour is unchanged (old code on :30000); the budget route requires
  one of the two existing launch flags.
- **INFERENCE (marked):** because the prompt now carries different steering and the budget maps to
  the existing enforcement path, deploying this on a flagged launch is expected to produce graded
  reasoning. Real weight-level behaviour is a follow-up calibration claim, not established here.

## Defects / blockers

1. **No launch path enforces the budget by default.** `--enable-strict-thinking` and
   `--enable-custom-logit-processor` are both off in the current deployment. The code intentionally
   degrades to prompt-level policy rather than 400; a follow-up must choose/enable a mechanism.
2. **`protocol.py:869-881` advertisement is still generic.** The description ("'high' is the most
   effort", float fine-grained control) is now TRUE only for models declaring this policy; for other
   families it remains a generic contract. Fixing the advertisement is a separate, broader
   contract change and was out of this narrow scope.
3. **`/v1/responses` budget not routed** (prompt-level policy only). Marked out of scope.
4. **`SGLANG_QWEN35_EFFORT_POLICY` is not added to `docs/docs/references/environment_variables.mdx`**
   because docs are outside the authorized write domain. No test gates that file (grep found none),
   so no suite breaks; a follow-up should document it.

None of these block the assigned deliverable.

## Remaining claims / exclusions

- Excluded: live generation, GPU, server restart/config, weight/training changes (a STOP condition;
  not hit — no weights or training were touched).
- Excluded: final production budget ladder (configurable and provisional by design).
- Excluded: M1 runtime (M1 not served).
- Excluded: streaming, `/v1/responses`, Anthropic, multi-turn history, float calibration.
- Method note: one self-inflicted probe (`git checkout HEAD -- serving_chat.py`) reverted the file
  mid-task; it was observed (`numstat 0`, hash back to HEAD, 0 `qwen35` matches) and all edits were
  reapplied and re-verified against the final hashes above. Recorded here for honesty.

## Changed-artifact list

- Modified: `python/sglang/srt/entrypoints/openai/serving_chat.py`,
  `python/sglang/srt/sampling/custom_logit_processor.py`, `python/sglang/srt/environ.py`.
- Created: `python/sglang/srt/parser/qwen35_reasoning_policy.py`,
  `test/registered/unit/parser/test_qwen35_reasoning_policy.py`.
- Scratch (not durable product state): `/tmp/opencode/REASONING-EFFORT-POLICY-IMPL-20260918/`.
- This artifact is the single authoritative handoff.

## Single suggested next step (no big benchmark)

Run one narrow workload calibration on a flagged launch (e.g. `--enable-custom-logit-processor`)
against M2 with the `low` and `high` tiers on one fixed overthinking prompt class (trivial arithmetic
+ constrained-code, which previously over-deliberated), recording `reasoning_tokens`,
`completion_tokens`, `finish_reason`, and content non-empty. Use it to pick provisional
`max_thinking_tokens` values for the ladder. No full benchmark.

Terminal state: DONE
