# Phase 1 C6 accounting and context metadata

## Context metadata

Local official GPTQ checkpoint files were read directly:

```text
/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4/config.json
/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4/quantize_config.json
```

Observed GPTQ config:

```text
max_position_embeddings = 8192
quant_method = gptq
bits = 4
group_size = 128
desc_act = true
sym = true
lm_head = false
checkpoint_format = gptq
```

Phase 1 C6 server command used:

```text
--context-length 32768
SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1
```

Required interpretation:

```text
This is an override allowing execution with a requested 32768 context.
It does not establish official GPTQ-Int4 native 32K support.
```

The official BF16 Falcon-H1-7B-Instruct reference value required by Phase 1 is
`max_position_embeddings = 262144`. No separate local BF16 checkpoint was found
under `/data/models` during this check, so that BF16 value is recorded as the
reference comparison, not as a locally inspected artifact.

## Observed C6 allocation

From `runs/phase1c-20260921-r1/server.log`:

```text
Mamba max_mamba_cache_size = 80 states
Mamba conv state = 0.07 GiB
Mamba SSM state = 5.22 GiB
KV dtype = torch.bfloat16
KV tokens = 141879
KV K = 2.98 GiB
KV V = 2.98 GiB
effective max_running_requests = 16
```

Derived values:

```text
5.22 GiB / 80 = 66.8 MiB/state (approximately)
80 / 16 = 5 state slots/running request
```

The five-slot multiplier is code-derived, not inferred only from the log:

```text
python/sglang/srt/mem_cache/kv_cache_configurator.py
MAMBA_CACHE_SIZE_MAX_RUNNING_REQUESTS_RATIO = 3
MAMBA_CACHE_V2_ADDITIONAL_RATIO_OVERLAP = 2
```

With radix cache enabled, normal overlap schedule, and the observed extra
buffer, `_calculate_mamba_ratio()` returns `3 + 2 = 5`. The cap is then:

```python
mamba_cap = max_mamba_cache_size // ratio
          = 80 // 5
          = 16
```

No Mamba policy, state-slot multiplier, CUDA graph config, KV dtype, HiCache,
or checkpoint config was changed.

## C6 readiness and correctness

The original C6 process completed CUDA graph warmup and logged:

```text
The server is fired up and ready to roll!
```

At that point:

```text
GET /health -> HTTP 200 OK
```

A simple deterministic completion returned HTTP 200 with 10 prompt tokens and
32 completion tokens. Its output was a counting sequence, not a semantic answer
to the prompt, so it is transport/runtime PASS but correctness ANOMALY.

## Persistent C6 follow-up

Under the user's indefinite GPU authorization, a new C6 server was started on
`127.0.0.1:30170` and remains running. It was not stopped after warmup.

```text
/health = HTTP 200
/model_info = FalconH1ForCausalLM / falcon_h1
```

Short deterministic completion/chat and three additional short correctness
smokes all returned HTTP 200, but their decoded outputs were unrelated to the
requested arithmetic, factual, or exact-token answers. Therefore transport and
runtime execution pass, while semantic correctness is FAIL/ANOMALY.

Same-process concurrency probe:

```text
c=1: 1/1 HTTP success
c=2: 2/2 HTTP success
c=4: 4/4 HTTP success
c=8: 8/8 HTTP success
c=16: 16/16 HTTP success
```

This does not claim semantic correctness or active capacity above 16.

The >8192 execution smoke used a 68,249-character prompt, observed as 11,020
input tokens, and returned HTTP success in 13.96 seconds with 8 completion
tokens. The decoded sentinel response was empty, so sentinel semantic PASS was
not established. The result proves only execution beyond 8192 under the explicit
override, not native GPTQ-Int4 32K quality or BF16 equivalence.

The persistent C6 server remains running. No Mamba policy, state-slot
multiplier, CUDA graph config, KV dtype, HiCache, or checkpoint config was
changed.
