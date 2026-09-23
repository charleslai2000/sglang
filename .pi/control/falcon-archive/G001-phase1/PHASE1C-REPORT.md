# Phase 1C — mixed-GPTQ root-cause proof + narrow loader/model compatibility fix

## VERDICT: BLOCKED

Static C1–C5 completed. C6 GPU reload remains blocked because the RTX 3090 is
owned by an active M4 workload. No GPU process was touched.

## Root-cause proof

### Parameter topology before fix

`FalconH1HybridAttentionDecoderLayer` passed the global `quant_config` into all
three linear families:

```python
QKVParallelLinear(..., quant_config=quant_config)
RowParallelLinear(..., quant_config=quant_config)
FalconH1MLP(..., quant_config=quant_config)
```

`LinearBase.__init__` calls `quant_config.get_quant_method(self, prefix=prefix)`.
The GPTQ-Marlin method creates packed quantized parameters through its scheme,
not a normal BF16 `weight` parameter. Therefore the pre-fix attention topology
was quantized whenever the global model config selected GPTQ-Marlin.

At layer 0, the intended checkpoint topology is:

```text
attention q_proj/k_proj/v_proj/o_proj: BF16 `weight`
FFN gate/up/down: GPTQ `qweight`, `qzeros`, `scales`, `g_idx`
Mamba weights/state parameters: non-GPTQ, checkpoint dtypes
```

The pre-fix model instead constructed `qkv_proj` and `o_proj` using the global
GPTQ-Marlin quantization method, creating a topology incompatible with the
checkpoint's BF16 attention weights.

### Exact q_proj -> failure trace

For original checkpoint name:

```text
model.layers.0.self_attn.q_proj.weight
```

The loader first removes `.self_attn`:

```text
model.layers.0.q_proj.weight
```

It then iterates:

```python
("qkv_proj", "q_proj", "q")
("qkv_proj", "k_proj", "k")
("qkv_proj", "v_proj", "v")
```

The first candidate is:

```text
model.layers.0.qkv_proj.weight
```

Because pre-fix GPTQ-Marlin attention does not expose the expected BF16
`qkv_proj.weight` topology, the candidate is absent from `params_dict`, and the
loop continues. The code mutates `name` in place. The next mapping sees `v_proj`
in the already-mutated candidate and produces:

```text
model.layers.0.qkqkv_proj.weight
```

The fallback lookup then raises:

```text
KeyError: 'model.layers.0.qkqkv_proj.weight'
```

This establishes:

- **PRIMARY root cause:** global GPTQ quantization was propagated into BF16
  attention `qkv_proj`/`o_proj`, creating the wrong parameter topology.
- **SECONDARY symptom:** in-place `name` mutation across mapping iterations turns
  the initial missing `qkv_proj.weight` candidate into `qkqkv_proj.weight`.

The secondary mutation alone would not make the quantized attention topology
correct; it is not sufficient as the final fix.

### FFN evidence

The official checkpoint has exactly 132 `qweight` tensors: 44 layers × 3 FFN
projections. The previous artifact inspection found matching `qzeros`, `scales`,
and `g_idx` tensors for all 132 modules. The FFN continues to receive the
global GPTQ config after the fix.

## Fork vs upstream

- Git tag `v0.5.18` contains the same Falcon-H1 loader and the same global
  `quant_config` propagation into attention and FFN.
- `upstream/main` was fetched at `95521da18d`; its Falcon-H1 loader still has
  the same in-place mapping mutation and the same loader structure.
- No exact upstream fix for this mixed BF16-attention/GPTQ-FFN checkpoint was
  found in the compared `v0.5.18`/current-main code.
- The issue is therefore present in the shared upstream code path, not a
  regression introduced uniquely by this branch. This branch's HEAD is aligned
  with the affected implementation for the relevant files.
- No broad SGLang upgrade or unrelated upstream change was used.

## Patch and rationale

Modified only:

```text
python/sglang/srt/models/falcon_h1.py
```

Changes:

1. `QKVParallelLinear(..., quant_config=None)` so attention Q/K/V remains
   unquantized BF16 topology.
2. `RowParallelLinear(..., quant_config=None)` so attention output remains
   unquantized BF16 topology.
3. `FalconH1MLP(..., quant_config=quant_config)` unchanged, preserving GPTQ-
   Marlin for all FFN gate/up/down projections.
4. Loader mapping now uses `original_name` plus a per-iteration
   `candidate_name`; mapping attempts no longer mutate the name used by later
   mappings. This is a defensive fix for the independently observed secondary
   symptom.

No checkpoint, quantize config, global GPTQ subsystem, or other model was
modified.

Patch evidence:

```text
control/G001-falcon-h1-phase1/phase1c.patch
SHA256 9511514b08fd81b0f6236581415fa223d0933f4895e50da084ae37b3cd28ecbb
```

## Topology after fix

Expected from the code-level construction:

```text
Attention qkv_proj: unquantized LinearBase / BF16 `weight`
Attention o_proj:   unquantized LinearBase / BF16 `weight`
FFN gate_up/down:   GPTQ-Marlin packed scheme
Mamba:              unchanged
```

## Checkpoint tensor coverage

Static artifact coverage remains:

```text
expected quantized projection modules: 132
checkpoint qweight tensors: 132
checkpoint qzeros/scales/g_idx coverage: 132 corresponding modules
unquantized attention q/k/v/o: 44 × 4 families
```

The loader regression test verifies all three independent Q/K/V names resolve to
one fused `qkv_proj` with shard IDs `q`, `k`, `v`, with no `qkqkv_proj` and no
silent drop. Full post-load runtime loaded/skipped/missing/unexpected counts are
pending C6 because the GPU is unavailable.

## Regression tests

Added:

```text
test/registered/unit/test_falcon_h1_mixed_gptq.py
```

Tests:

1. AST topology test: attention calls use `quant_config=None`; FFN retains the
   global `quant_config`.
2. CPU-only loader mapping test: independent Q/K/V names stack into fused QKV,
   use shard IDs `q/k/v`, and never produce `qkqkv_proj`.

Execution:

```text
2 tests passed
py_compile passed
git diff --check passed
```

The test file was run directly because this checkout does not expose the
`test.registered` package as an importable package under the ordinary unittest
module path.

## GPU load result

C6 completed after a fresh ownership check:

```text
GPU UUID: GPU-2e3ed202-3655-d919-0a64-259209bc6587
before load: 1 MiB / 24576 MiB, 0% utilization
no compute workload and no 30170 listener
```

The patched server loaded successfully:

```text
weight load: SUCCESS
model: FalconH1ForCausalLM
quant: gptq, bits=4
weight load elapsed: 14.67 s
peak observed allocation: 20964 MiB / 24576 MiB during warmup
```

The service completed CUDA graph warmup and reached:

```text
The server is fired up and ready to roll!
```

The health endpoint returned:

```text
HTTP/1.1 200 OK
```

A single deterministic request was executed successfully:

```text
POST /generate: 200 OK
prompt_tokens: 10
completion_tokens: 32
finish_reason: length
```

Observed output was syntactically valid but not semantically correct for the
question (`Explain why the sky is blue...` returned a counting sequence). This
is recorded as a correctness anomaly, not a loader failure. The temporary
server was then terminated cleanly and the GPU returned to:

```text
1 MiB / 24576 MiB
```

Run log:

```text
control/G001-falcon-h1-phase1/runs/phase1c-20260921-r1/server.log
```

## Context metadata discrepancy and C6 accounting

The local official GPTQ files were directly inspected:

```text
/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4/config.json
/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4/quantize_config.json
```

They report:

```text
GPTQ config max_position_embeddings = 8192
quant_method = gptq
bits = 4
group_size = 128
desc_act = true
sym = true
lm_head = false
```

The Phase 1 C6 command used:

```text
--context-length 32768
SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1
```

The official BF16 Falcon-H1-7B-Instruct reference value supplied for comparison
is `max_position_embeddings = 262144`. No local BF16 checkpoint was found under
`/data/models` during this check. The 32768 setting is an override and is **not**
interpreted as official GPTQ-Int4 native 32K support.

Exact C6 accounting:

```text
Mamba states = 80
conv state = 0.07 GiB
SSM state = 5.22 GiB
approximately 66.8 MiB/state
effective max_running_requests = 16
approximately 5 state slots/running request
KV tokens = 141879
K = 2.98 GiB
V = 2.98 GiB
```

The 5-slot/request value is code-derived. In
`python/sglang/srt/mem_cache/kv_cache_configurator.py`, normal overlap with the
observed Mamba extra buffer uses:

```text
MAMBA_CACHE_SIZE_MAX_RUNNING_REQUESTS_RATIO = 3
MAMBA_CACHE_V2_ADDITIONAL_RATIO_OVERLAP = 2
_calculate_mamba_ratio() = 3 + 2 = 5
mamba_cap = 80 // 5 = 16
```

No Mamba policy, state multiplier, CUDA graph config, KV dtype, HiCache, or
checkpoint config was modified.

The service reached ready, `/health` returned 200, and one deterministic request
returned HTTP 200. The output was a counting sequence rather than a semantic
answer, so correctness remains ANOMALY. The process was subsequently terminated
before the follow-up no-reload smoke/concurrency request was received. Thus the
following remain pending and are explicitly not claimed:

```text
short-context correctness smoke set
c=1,2,4,8,16 concurrency probe
>8192 sentinel execution smoke
```

## Phase 1 C6 follow-up on the authorized persistent GPU window

The user clarified that the GPU is authorized indefinitely. A new C6 process was
therefore started and remains running on `127.0.0.1:30170`; it was not stopped
or reloaded after readiness.

Readiness:

```text
GET /health -> HTTP 200 OK
GET /model_info -> model_type falcon_h1, architecture FalconH1ForCausalLM
```

Deterministic short requests all returned HTTP 200, but semantic correctness did
not pass. Examples included arithmetic, France-capital, exact-token, and chat
prompts; outputs were unrelated code/math/text fragments. This is a runtime
request PASS but a semantic correctness FAIL/ANOMALY.

Concurrency probe, same persistent process:

```text
c=1: 1/1 HTTP success
c=2: 2/2 HTTP success
c=4: 4/4 HTTP success
c=8: 8/8 HTTP success
c=16: 16/16 HTTP success
```

These requests were short and completed without queue-error evidence. This probe
confirms transport/service capacity through c=16 only; it does not claim semantic
correctness and does not search for c>16 active capacity.

A >8192 smoke was executed using a 68,249-character input, producing an observed
11,020-token prompt and an HTTP-successful response in 13.96 seconds:

```text
execution beyond 8192: PASS
input tokens: 11020
completion tokens: 8
```

The response text was empty after detokenization for this sentinel case, so the
sentinel semantic check itself did not pass. The result proves only that SGLang
plus the explicit context override executed an input beyond 8192; it does not
prove GPTQ-Int4 32K quality or BF16 equivalence.

The server remains running under the authorized GPU window. No Mamba policy,
state-slot multiplier, CUDA graph config, KV dtype, HiCache, or checkpoint
config was changed.

## Actual quant/kernel path and runtime accounting

From the earlier Phase 1B attempt before the load failure:

```text
GPTQ-Marlin conversion was selected
```

The following remain unconfirmed after the fix and require C6:

```text
loaded GPU memory
KV dtype and capacity
Mamba strategy and slot ratio
max_mamba_cache_size
effective max_running_requests
CUDA graph range
health/correctness smoke
```

## Known context-length discrepancy

The checkpoint declares `max_position_embeddings=8192`, while the Phase 1 frozen
cap is 32768. The existing environment override
`SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1` is required to pass argument
resolution and must remain explicitly recorded during C6. The checkpoint config
was not modified.

## Runtime modifications

A narrow Falcon-H1 compatibility patch is currently present in the worktree;
no installed runtime or running service was modified. No GPU process was
modified.

## Remaining anomalies / next frontier

- C6 GPU reload is blocked by active M4 ownership.
- Full runtime weight coverage and successful model load are not yet proven.
- No concurrency, HiCache, or performance work was started.
