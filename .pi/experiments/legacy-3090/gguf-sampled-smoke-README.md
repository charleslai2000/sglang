# GGUF sampled-contract smoke gate (`gguf-sampled-smoke`)

Gate for the two GGUF candidates on the single RTX 3090, re-scoped by the owner
on 2026-09-17. It answers one question per model: **is the model correct under
its own frozen sampling contract?**

## Why this gate exists

The earlier gate scored the `>=512-token coherence` criterion under **greedy**
decoding and failed M3/M4. That was the wrong instrument: both GGUF files carry
the model-native decoding contract in GGUF metadata `general.sampling.*`:

| model | file | arch | tensors | `temp` | `top_p` | `top_k` | `min_p` | `penalty_repeat` |
|---|---|---|---|---|---|---|---|---|
| M3 | `Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf` | `qwen35` | 851 | 1.0 | 0.949999988 | 20 | 0.0 | — |
| M4 | `swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf` | `qwen35` | 866 (15 `blk.64.*` MTP unmapped) | 1.0 | 0.949999988 | 20 | 0.0 | 1.0 |

A previous "sampled decoding does NOT fix M3/M4" result used
`temperature=0.7, top_p=0.8, top_k=20` — **not** this contract. Owner re-scope:

* `>=512-token greedy coherence` is **demoted to diagnostic evidence**;
* the long-form correctness gate is `>=512-token chat generation under the
  frozen explicit SAMPLED contract`.

## Contract (explicit on every request, no implicit `generation_config`)

Endpoint: **`/v1/chat/completions` only.** Raw `/generate` text completion on a
chat model is prompt-format misuse, and streaming-concat is a known artifact —
neither is used.

Every request pins: `temperature`, `top_p`, `top_k`, `min_p`, `seed`,
`max_tokens`, and `chat_template_kwargs: {"enable_thinking": false}`.

Exact gating body (produced and asserted by `--cpu-smoke`):

```json
{
  "model": "default",
  "messages": [{"role": "user", "content": "<gate prompt>"}],
  "temperature": 1.0,
  "top_p": 0.95,
  "top_k": 20,
  "min_p": 0.0,
  "seed": 20260916,
  "repetition_penalty": 1.0,
  "max_tokens": 640,
  "chat_template_kwargs": {"enable_thinking": false}
}
```

`repetition_penalty` is the SGLang request field for GGUF's `penalty_repeat`;
it is pinned explicitly on both models (1.0 is neutral, and it is what M4's
metadata carries).

## Arms

| arm | artifact key | gating | contract |
|---|---|---|---|
| **SAMPLED** | `step5_coherence` | **YES** | temp 1.0, top_p 0.95, top_k 20, min_p 0.0, seed 20260916, max_tokens 640, thinking off |
| greedy | `step5a_greedy_diagnostic` | no | temp 0.0, top_p 1.0, top_k -1, min_p 0.0, seed 20260916, max_tokens 640, thinking off |
| thinking-ON | `step5b_thinking_probe` | no | gating contract + `enable_thinking: true` |

## Pass criteria (per model, reported separately)

| # | criterion | rule |
|---|---|---|
| 1 | finite logits | 0 non-finite logprob values on both probes (`p1`, `p2`) |
| 2 | short deterministic semantics | chat `51`, chat `Paris`, code compiles, tool call `get_weather(city=Paris)` |
| 3 | CUDA graph capture + replay | capture lines > 0, 0 graph-error lines, concurrent decode batches HTTP 200 |
| 4 | fp8 KV | `KV Cache is allocated. dtype: torch.float8_e4m3fn` |
| 5 | no quant/kernel fallback | 0 `falling back|fallback|not support` and 0 `NotImplementedError` lines |
| 6 | **sampled >=512-token coherence** | usage.completion_tokens >= 512 **and** `content_loop_w4 <= 0.27` **and** no U+FFFD **and** >= 30 alpha words **and** content not empty |

Criterion 6 is evaluated on the **content channel only** (`content_loop_w4`),
which is where a repetition loop is user-visible. A response whose text sits
entirely in `reasoning_content` with empty content **fails** (see
`reject_all_reasoning_empty_content` in `COHERENCE_GATE`).

The loop metric is **word-level 4-gram repeat fraction** preserved verbatim from
the prior audited harness, so numbers stay comparable to the earlier evidence.
Owner bounds: `COHERENT <= 0.27`, `DEGENERATE >= 0.51`, between is
`BORDERLINE`. The `--cpu-smoke` step proves this metric is bit-identical to both
the in-repo reference copy and the **live** prior harness module.

Run order is fixed: **M4 first** (shared-GGUF-runtime control, Q3_K_M), **M3
second** (IQ3-specific risk). An M3 failure is only interpreted after the shared
path has its own verdict.

## Source identity (parameterized, not hash-pinned)

The validated GGUF norm inverse-fold is committed to the authoritative branch
`3090-24g-opt`; this gate does not hardcode a pre-fix source hash.
`source_identity_preflight()` asserts structurally that:

1. `sglang` resolves inside `GGUF_GATE_SRC`;
2. `sglang.srt.models.qwen3_5_text` **is** that tree's file;
3. `_gguf_fold_absolute_norms` and `_gemma_norm_param_names` exist; and
4. the fold call is actually wired inside `Qwen3_5ForCausalLM.load_weights`.

The observed module sha256 is recorded in `report.json`. Set
`GGUF_GATE_MODULE_SHA256` to also enforce an exact revision.

## Running it

```bash
# No GPU, no server: verify the contract + metric wiring.
/opt/sglang/local-prod-v1/env/bin/python server_harness_sampled.py --cpu-smoke

# Full gate (touches the GPU; do this only when the GPU is free).
bash run_sampled_smoke.sh
```

GPU invocation actually used (`GPU_UNTOUCHED` until you run this):

```bash
cd 3090-dev/gates/gguf-sampled-smoke
bash run_sampled_smoke.sh
```

which resolves to, in order:

```bash
$PY server_harness_sampled.py --cpu-smoke      # offline, no CUDA
$PY server_harness_sampled.py m4               # control, port 30165
$PY server_harness_sampled.py m3               # IQ3 risk, port 30165
```

### Environment knobs

| var | default | meaning |
|---|---|---|
| `GGUF_GATE_SRC` | repo `python/` tree | source tree under test |
| `GGUF_GATE_PY` | `/opt/sglang/local-prod-v1/env/bin/python` | interpreter |
| `GGUF_GATE_PORT` | `30165` | experiment port (**never** 30000) |
| `GGUF_GATE_RUNROOT` | `/mnt/data/nerun-dev/gguf-sampled-smoke-20260917/runs` | artifacts |
| `GGUF_GATE_MODULE_SHA256` | unset | optional exact module pin |

### Safety

* GPU access is serialized by the canonical flock `/tmp/opencode/gpu-3090.lock`
  with bounded backoff; an incumbent is never signalled or killed.
* The CUDA ordinal is resolved from UUID `GPU-2e3ed202-…-259209bc6587`
  (NVML index and CUDA ordinal are inverted on this host), not from the index.
* Port `30000` is never bound; `301xx` are the experiment ports.
* `/opt/sglang` and `/var/log/sglang` are read-only inputs.

## Files

| file | role |
|---|---|
| `server_harness_sampled.py` | the gate (derived from the audited prior harness) |
| `run_sampled_smoke.sh` | sequential driver: cpu-smoke -> M4 -> M3 |
| `README.md` | this document |
| `llamacpp-discriminator.md` | CPU-only llama.cpp neutrality control |
| `cpu_smoke.out.json` | recorded CPU-smoke evidence |
