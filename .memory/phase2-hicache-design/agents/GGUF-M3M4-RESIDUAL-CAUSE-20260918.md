# GGUF-M3M4-RESIDUAL-CAUSE-20260918

Task: Bounded CPU-first diagnosis of the residual SGLang GGUF incoherence on M3/M4 under
the post-fix working tree (tokenizer id-binding fixed), where llama.cpp (same GGUF, same
prompt, equivalent sampling) is coherent.

Scope: Read-only product source. CPU-only: no GPU, no CUDA, no server start/stop, no port
bind, no process signals. Probes used the already-authorized interpreter
`/opt/sglang/local-prod-v1/env/bin/python` with `PYTHONPATH=<repo>/python`. The CPU-only
llama.cpp build at
`/mnt/data/nerun-dev/llamacpp-discriminator-20260917/llama.cpp/build-cpu/bin/` was run
read-only (no server; `llama-tokenize`, `llama-completion`, `llama-cli`) — no CUDA libs
linked (`ldd` shows none).

Result: DONE. The five sub-questions have direct on-disk/CPU answers, and the residual is
localized to the SGLang qwen35 **forward/weight path** — not to the tokenizer, the chat
template rendering, the reasoning parser, or the stop configuration. A ranked residual set
with one named decisive discriminator is given.

Evidence (all commands CPU-only; raw output pasted):

## E1. `enable_thinking:false` IS honored in the rendered prompt

The served tokenizer built from the real M4 GGUF (`build_gguf_tokenizer`, post-fix file
sha256 `0f3c8fb9…`), rendering the failing `function_csv` probe with the pinned kwargs:

```
$ PYTHONPATH=python /opt/sglang/local-prod-v1/env/bin/python   # build_gguf_tokenizer(M4)
render tail: '... handle missing values by skipping them.<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
ids_tail [198, 248045, 74455, 198, 248068, 271, 248069, 271]  n_ids 55
```
The assistant turn is prefilled with the **pre-closed** think block
(`<think>\n\n</think>\n\n`) which is exactly the template's
`enable_thinking is false` branch:
```
TEMPLATE: {%- if enable_thinking is defined and enable_thinking is false %}
TEMPLATE: {%- if enable_thinking is undefined or enable_thinking is true %}
```
With `enable_thinking=true` the same probe renders `...<|im_start|>assistant\n<think>\n`
(95 ids) — so the toggle changes the prompt as intended. All four turn markers are the
CANONICAL ids 248045/248046/248068/248069; no `[PAD*]` rows.

**Stronger: the exact prompt SGLang actually sent is on disk** in the post-fix per-request
metrics (`/mnt/.../runs/m4/metrics/sglang-request-metrics-20260918_18.log`,
`runs/m3/..._19.log`), under `request_parameters.input_ids`, because the harness sets
`return_prompt_token_ids`/logging. I re-encoded locally and compared:
```
function_csv  served_n 55 local_n 55 EQUAL True
longform_water served_n 52 local_n 52 EQUAL True
explain_tcp   served_n 38 local_n 38 EQUAL True
```
The served ids end `[..., 248046, 198, 248045, 74455, 198, 248068, 271, 248069, 271]`
(canonical `<|im_end|>`, `<|im_start|>assistant\n`, `<think>`, blank, `</think>`). The
server log records
`Auto-detected template features: ... toggle_param='enable_thinking', default_enabled=True`
and `Using default HuggingFace chat template with detected content format: openai`.

⇒ (1) **Yes**, `enable_thinking:false` is honored; the prompt is not pre-closing anything
incorrectly and contains no stray/empty think block beyond the template's intended
pre-closed one.

## E2. Tokenizer equivalence with llama.cpp on the raw probes (rules out the fix)

The raw `/generate` prompts (which carry no chat specials) encode identically under SGLang
and llama.cpp:
```
SGLang build_gguf_tokenizer(M4).encode:
  raw_capital n=5  [760, 6511, 314, 9338, 369]
  raw_arith   n=14 [14162, 25, 3437, 369, 220, 16, 22, 2942, 220, 18, 30, 198, 15666, 25]
  raw_echo    n=10 [37436, 411, 4581, 16629, 25, 23066, 1814, 198, 45241, 25]
llama-tokenize -m M4.gguf --ids  (same files):
  [760, 6511, 314, 9338, 369]
  [14162, 25, 3437, 369, 220, 16, 22, 2942, 220, 18, 30, 198, 15666, 25]
  [37436, 411, 4581, 16629, 25, 23066, 1814, 198, 45241, 25]
```
Renderer-vs-llama.cpp on the full chat text is also id-for-id:
`function_csv [248045,846,...248069,271]` and `chat_capital [248045,846,...248069,271]`
match exactly (both tools).

⇒ The residual reproduces on raw prompts where the special-token fix is not even
exercised, so the tokenizer id-binding fix is **not** the cause of the remaining
incoherence.

## E3. The decisive divergence (same tokens, same greedy, same file) — SGLang loops, llama.cpp is correct

SGLang post-fix raw `/generate` greedy (`temperature=0`) outputs, from the gate's own
`report.json` `step1_finite_logits` (`return_logprob`), and the llama.cpp CPU greedy run on
the byte-identical prompt:

| prompt | SGLang post-fix `/generate` (temp 0) | llama.cpp CPU `llama-completion -no-cnv --temp 0` |
|---|---|---|
| `The capital of France is` | M4 `' France is France is France is France is'` ids `[9338,369,...]`; M3 `' of of of of of of of of'` ids `[314,...]` | M4 `\n Paris.\nThe capital of Germany is Berlin.` ; M3 `\n Paris.\nThe capital of Germany is Berlin.` |
| `Question: What is 17 times 3?\nAnswer:` | M4/M3 `'\nAnswer:\nAnswer:\nAnswer'` ids `[198,15666,25,...]` | M4 ` 51 [end of text]` ; M3 `17 × 3 = 51.\n\nSo the answer is 51.` |

SGLang loops by copying a bigram/mid-phrase out of its own context (`France is`, `of of`,
`Answer:`), which is the signature of a broken context/position/recurrent-state use of the
prompt, while llama.cpp from the same file emits the correct continuation and EOS. The
llama.cpp SGLang-facing discriminator for the chat `function_csv` probe is also coherent
(`m4 loop_w4=0.0552, 301 tok, stop`; `m3 0.1029, 316 tok, stop`).

This divergence reproduces in the **pre-existing** on-disk runs as well, including runs
where the Gemma-norm fold was already active (`/var/log/.../gguf-coherence-control-20260916`,
`/var/log/.../m3-m4-normfix-gate-20260916`), so it is not created by the tokenizer fix or
removed by the norm fold.

## E4. EMPTY_CONTENT is a first-token EOS, not a parser mis-split

Post-fix per-request metrics (`finish_reason` is the engine's own stop record):
```
m4 function_csv  completion=1 finish=stop matched=248046   (content_n_chars 0; content_sha256 = e3b0c442…b855, the empty-string sha)
m4 chat_tool     completion=2 finish=stop matched=248046
m4 chat_arithmetic completion=3 finish=stop matched=248046  -> content 'The answer'
m4 chat_capital  completion=3 finish=stop matched=248046  -> content 'Rome'
m4 explain_tcp   completion=94 finish=stop matched=248046 -> content 'Paragraph 1 Excerpt Excerpt …' (loop_w4 0.9574)
m3 longform_water completion=8 finish=stop matched=248046 -> TOO_SHORT
m3 explain_tcp   completion=7 finish=stop matched=248046 -> TOO_SHORT
```
For `function_csv` the model's **first sampled token is `<|im_end|>` (248046)**, so the
detokenized completion buffer is genuinely empty; there is no `reasoning_content` and no
parser split. I confirmed the `qwen3` parser passes a leading `</think>`-less stream
straight through as content:
```
Qwen3Detector.parse_streaming_increment('</think>') -> normal='</think>' reasoning=''
```
so the parser is not consuming the whole generation; the emptiness is upstream in the
model output. (The separate `thinking_on` diagnostic with `enable_thinking:true` does put
text in `reasoning_content`, as expected; that is a different arm.)

⇒ (2) **EMPTY_CONTENT** = the model emits the turn-end/EOS token `<|im_end|>` (248046) as
its first sampled token, so the content channel is truly empty; the reasoning parser is
not responsible.

## E5. TOO_SHORT stop identity

`stop_token_ids=None`, `ignore_eos=False` in every gated request (from
`request_parameters.sampling_params`), and the engine records `finish_reason =
{"type":"stop","matched":248046}`. There is no request-level `stop` string. GGUF metadata
(`tokenizer.ggml.eos_token_id = 248046`) and `build_gguf_generation_config` set
`eos_token_id=248046` for both files. So the stop that fires is `<|im_end|>` = the GGUF
**eos**, emitted voluntarily by the model within ≤8 tokens.

⇒ (3) **TOO_SHORT** = the model emits eos `<|im_end|>` (248046) after 7–8 tokens; the
matched stop id is 248046, originating from the GGUF eos metadata (no per-request stop ids).
The tokenizer fix did not alter `eos_token_id` semantics: `build_gguf_generation_config`
reads `tokenizer.ggml.eos_token_id`/`eot_token_id` from metadata unchanged; only
`CONTROL`/`USER_DEFINED` classification and the `special` flag were touched.

## E6. Criterion-2 asymmetry: why `chat_code` passes

Observed post-fix `step2_semantic` contents:
```
m4 chat_code content='def add(a, b):\n    return a + b'  extracted same  compile_ok=True
m3 chat_code content='```\n\n```'                        extracted=''     compile_ok=True
m4 chat_arithmetic content='The answer'      (expected 51)
m4 chat_capital   content='Rome'             (expected Paris/paris)
m4 chat_tool      tool_calls=None
m3 chat_arithmetic content='The question asks,'  (expected 51)
m3 chat_capital   content='France'               (expected Paris)
```
`chat_code` is graded **structurally** (the harness extracts the fenced block and calls
`compile()`), while the other three are graded **semantically** by substring/tool-call. M4
happens to emit the exact correct function; M3 emits an empty fenced block and passes
**vacuously** — `compile('', '<model_output>', 'exec')` succeeds, so the M3 `chat_code`
PASS is a grading artifact, not a coherent success. The failing trio fails because the
model now answers incorrectly/shortly (and stops at `<|im_end|>`), consistent with the
same forward divergence in E3.

⇒ (4) `chat_code` passes because its acceptance test is syntactic (and, on M3, vacuously
satisfied by an empty extracted program); `chat_arithmetic`/`chat_capital`/`chat_tool`
fail because they require semantic correctness the model does not produce.

## E7. Why the pre-fix run showed criterion-2 PASS but post-fix FAIL (context, not cause)

With the pre-fix tokenizer (`vocab 248293`, turn markers on the `[PAD*]` rows) the chat
probes ran to the token cap and the expected substring appeared inside a loop, e.g.
(`/var/log/.../m3-m4-normfix-gate-20260916/m4/report.json`):
`chat_arithmetic content='</think>\n51\n\n</think>\n51…'` → `contains_expected=True`.
Post-fix the model stops at `<|im_end|>` after 3 tokens (`'The answer'`, `'Rome'`), so the
substring test fails. The underlying raw-greedy incoherence is unchanged and present in
both (E3). This explains the verdict change without requiring a new defect.

Defects or blockers:

- **D1 (grading defect, in the gate harness, not product source):** M3 `chat_code` PASS is
  vacuous — `extracted=''` and `compile('')` succeeds. The harness should require
  non-empty extracted code.
- **D2 (evidence gap):** the decisive E3 divergence is established from the engine's own
  recorded `output_token_logprobs` (token ids) and independently reproduced llama.cpp text;
  it is **not** established which SGLang tensor transform produces it. Raw greedy logits
  are not exposed by the HTTP API, and no GPU work was authorized.
- No blocker prevented the assigned diagnosis.

Remaining claims or exclusions:

- ESTABLISHED: `enable_thinking:false` is honored; served `input_ids` equal the local
  canonical render; the five canonical markers are canonical post-fix; SGLang and
  llama.cpp tokenize the probes identically.
- ESTABLISHED: EMPTY_CONTENT = first sampled token is eos `<|im_end|>` 248046, content
  truly empty; TOO_SHORT = eos 248046 emitted at 7–8 tokens; no request stop ids.
- ESTABLISHED: `chat_code`'s PASS is syntactic (M3 vacuous); the semantic probes fail on
  content, not format.
- ESTABLISHED: on byte-identical raw prompts under greedy decoding from the same GGUF file,
  SGLang loops while llama.cpp answers correctly and stops. This localizes the residual to
  the SGLang qwen35 forward/weight path, **upstream** of detokenization, the chat template,
  the reasoning parser, and the stop configuration.
- RANKED REMAINING (inference, not proven here):
  1. A GGUF→runtime weight transform/layout defect in the qwen35 port that is **not** the
     Gemma-norm fold and **not** the tokenizer fix (both present during the identical
     E3 loop). Candidates: the GDN fused `attn_qkv`/`attn_gate`/`ssm_*` shard merges and
     `ssm_conv1d` reshape; the full-attention fused-QKV q|gate interleave; `ssm_a`→`A_log`
     or `dt_bias`; or the GGUF-derived config constants (`partial_rotary_factor`,
     `full_attention_interval`, `layer_types`).
  2. An fp8-e4m3 KV numerics issue specific to these 3-bit 27B GGUFs (weaker: the
     coherent control M1 runs with the same fp8 KV, but M1 is a different size/format).
  3. A recurrent-state/cache interaction with `--mamba-radix-cache-strategy extra_buffer`
     (not exercised by the CPU llama.cpp control).
- EXCLUDED: GPU/CUDA/server lifecycle; any product-source edit; any conclusion about the
  full model ranking beyond the cited samples.

## (5) The single decisive discriminator (GPU required — this is the one thing I could not run)

**Experiment:** M4 only, one server, port 30165 (never 30000), reusing the frozen gate
harness request path but with a single probe: raw `/generate`,
`{"text":"The capital of France is","sampling_params":{"temperature":0.0,"max_new_tokens":8},"return_logprob":true}`,
run twice: **(a)** as recorded, `--kv-cache-dtype fp8_e4m3`; **(b)** `--kv-cache-dtype auto`
(bf16 KV), all else identical.

**Read-out:** the returned `output_ids` of the first 3 decode steps. The llama.cpp CPU
reference for this exact prompt is ` Paris.` (first token id `9338` followed by `13`);
the recorded SGLang fp8 output is `[9338, 369, 9338, …]` (` France is France is…`).

- If (b) restores ` Paris.` / id `13` after `9338` ⇒ the cause is in the fp8-KV numeric
  path (ranked candidate 2).
- If (b) still loops identically ⇒ the cause is in the GGUF weight transform/layout or
  config for the qwen35 port (ranked candidate 1), and the next micro-step is to dump the
  loaded runtime values of the GDN and fused-QKV tensors and compare them against the
  dequantized GGUF reference for one layer.

This is one arm of one already-built gate launch and is the cheapest observation that
splits the two remaining causal classes; it cannot be performed CPU-only because the
divergence is only observable through SGLang's GPU forward pass.

Terminal state: DONE
