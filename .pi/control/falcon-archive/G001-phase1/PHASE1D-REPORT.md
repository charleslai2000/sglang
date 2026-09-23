# Phase 1D/1E — Falcon-H1 GPTQ-Int4 semantic correctness root-cause isolation

## VERDICT: NARROWED

Runtime and loading are proven, but semantic correctness is not. The decisive
current evidence excludes a simple tokenizer/chat-template explanation and
leaves the same-checkpoint reference and numerical backend branches blocked by
the local Transformers dependencies.

No model or kernel fix was made in Phase 1D. No performance optimization,
HiCache, Mamba policy, context optimization, speculative decoding, or unrelated
cleanup was performed.

## 0. Preserved evidence

### Branch identity

```text
git commit: f0075794b20a5b23d8b1b6cae417a8e10f2ae863
branch: falcon-h1-7b
```

Current source changes relative to that commit:

```text
M python/sglang/srt/models/falcon_h1.py
?? test/registered/unit/test_falcon_h1_mixed_gptq.py
```

The control/report artifacts are also untracked under
`control/G001-falcon-h1-phase1/` and `control/frontier.md`.

The complete Falcon-H1 source diff is preserved in the command evidence and
consists of exactly these four logical changes:

1. `QKVParallelLinear(..., quant_config=None)`.
2. `RowParallelLinear(..., quant_config=None)`.
3. Loader mapping uses immutable `original_name` plus per-iteration
   `candidate_name`, rather than mutating the name across mapping probes.
4. CPU-only regression test added at
   `test/registered/unit/test_falcon_h1_mixed_gptq.py`.

No checkpoint/config file was modified.

### Exact C6 command

```text
CUDA_VISIBLE_DEVICES=0 \
SGLANG_MAMBA_SSM_DTYPE=bfloat16 \
SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1 \
PYTHONPATH=/home/ubuntu/workspaces/3rdparty/sglang-falcon-h1-7b/python \
/home/ubuntu/venv/bin/python -u -m sglang.launch_server \
  --model-path /data/models/Falcon-H1-7B-Instruct-GPTQ-Int4 \
  --host 127.0.0.1 --port 30170 \
  --context-length 32768 --mamba-ssm-dtype bfloat16
```

The Phase 1D C6 r2 process completed warmup, passed health and all requested
HTTP probes, and was stopped only after the preservation and tokenizer evidence
was collected so the same-GPU reference attempt could be made.

### Why `qkqkv_proj` disappeared

The earlier error was:

```text
KeyError: model.layers.0.qkqkv_proj.weight
```

It disappeared through two source changes working together:

- Attention qkv/o is now constructed unquantized (`quant_config=None`), matching
the checkpoint's BF16 attention `weight` tensors. This restores the expected
`model.layers.N.qkv_proj.weight` target topology.
- Loader mapping no longer mutates `name` across mapping iterations. A failed
candidate for `q_proj` cannot become `qkqkv_proj` when the next `v_proj` mapping
is probed.

The first change fixes the primary topology mismatch; the second removes the
secondary malformed-name symptom. This was verified by successful GPTQ-Marlin
weight load in C6 r1/r2 with no `qkqkv_proj` error.

## 1. Official request reproduction

The OpenAI-compatible request was:

```json
{
  "model": "/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4",
  "messages": [{"role":"user","content":"What is the capital of France?"}],
  "temperature": 0,
  "max_tokens": 16
}
```

Result:

```text
HTTP 200
prompt_tokens: 17
completion_tokens: 16
output: "nner = (int) (Math.random() * "
```

The raw `/generate` completion with the same question at both temperature 0
and 0.1 returned the same unrelated code fragment:

```text
"- **Input:** `python script.py --input_file"
```

The exact raw outputs are preserved at:

```text
runs/phase1c-20260921-r2/official-messages.json
runs/phase1c-20260921-r2/official-completion-temp-0.json
runs/phase1c-20260921-r2/official-completion-temp-0.1.json
```

## 2. Tokenizer/chat-template equivalence

Direct local Transformers tokenizer call:

```python
tokenizer.apply_chat_template(
    [{"role":"user","content":"What is the capital of France?"}],
    add_generation_prompt=True,
    tokenize=True,
)
```

Produced rendered prompt:

```text
<|begin_of_text|><|im_start|>user
What is the capital of France?<|im_end|>
<|im_start|>assistant
```

Produced input IDs:

```text
[17, 227, 4305, 1221, 7287, 1412, 1302, 12034, 1352, 15013, 1066,
 228, 1221, 227, 1660, 35036, 1221]
```

Artifact:

```text
runs/phase1c-20260921-r2/tokenizer-chat-template.json
```

The exact same 17 IDs were sent directly to SGLang using `input_ids`; SGLang
reported `prompt_tokens: 17` and generated:

```text
"nner = (int) (Math.random() * "
```

Artifact:

```text
runs/phase1c-20260921-r2/exact-hf-chat-input-ids.json
```

The OpenAI chat endpoint also rendered a 17-token prompt. Therefore:

```text
same tokenizer-derived prompt length: YES
same input IDs for direct A/B: YES
same BOS: ID 17 (<|begin_of_text|>)
same chat template path: YES for the model's OpenAI chat request
```

A `messages` object sent to the raw `/generate` endpoint was rejected because
that endpoint accepts `text`, `input_ids`, or `input_embeds`; it is not evidence
of a tokenizer mismatch.

**A tokenizer/chat-template-only root cause is substantially excluded.**

## 3. Same-checkpoint Transformers reference

The same local GPTQ checkpoint was tested with the installed Transformers 5.12.1.
Dependency inventory:

```text
transformers: installed (5.12.1)
auto_gptq: absent
gptqmodel: absent
optimum: absent
accelerate: absent
```

Attempt 1 using `device_map="auto"` was blocked before model load:

```text
ValueError: ... requires accelerate
```

Attempt 2 without `device_map` reached GPTQ dispatch and was blocked with:

```text
[transformers] act_group_aware has been auto-disabled as it is not compatible
with desc_act = True
ImportError: Loading a GPTQ quantized model requires optimum
```

Thus the preferred same-checkpoint reference is **BLOCKED**, not PASS or FAIL.
No package was installed or upgraded, and no environment modification was made.

The dedicated reference script prepared and saved all three official chat-template
inputs before loading:

```text
control/G001-falcon-h1-phase1/scripts/phase1d_hf_reference.py
runs/phase1d-hf-gptq-reference/inputs.json
```

The complete load traceback is preserved at:

```text
runs/phase1d-hf-gptq-reference/result.json
runs/phase1d-hf-gptq-reference/stderr.log
```

Exact blocker:

```text
ImportError: Loading a GPTQ quantized model requires optimum
```

Transformers also emitted:

```text
act_group_aware has been auto-disabled as it is not compatible with desc_act=True
```

No HF model object was created, so no first generated token, first-step top-10
logits, or decoded HF continuation exists. This is an environment/backend
unsupported seam, not a semantic result. SGLang raw output token IDs and
 decoded strings remain preserved in the C6 JSON artifacts.

## 4. BF16 control

Not run. The reference GPTQ path is blocked by missing `optimum`/`accelerate`,
and no local official BF16 Falcon-H1 checkpoint was found under `/data/models`.
The BF16 control is therefore not needed to establish the tokenizer A/B result
and remains pending only if an authorized, dependency-complete reference path is
provided.

## 5. SGLang path isolation

Not run because the required same-checkpoint reference branch is blocked. No
CUDA-graph-off reload and no Marlin/non-Marlin A/B was started. This avoids
creating an unsupported or confounded comparison before a valid reference
exists.

The C6 r2 server log did establish the normal path:

```text
GPTQ-Marlin selected
weight load succeeded
CUDA graph warmup completed
health succeeded
```

This proves load/runtime health, not numerical correctness.

## 6. Weight-loading audit status

Static source evidence proves the key topology correction and Q/K/V mapping
regression test passes:

```text
2 CPU-only tests passed
```

C6 dynamic load proves all checkpoint shards loaded into
`FalconH1ForCausalLM` without the former malformed-name exception. However,
Phase 1D did not yet instrument every layer-0/middle/last packed tensor's
post-load values, so the following remain unproven:

```text
exact qweight/qzeros/scales/g_idx runtime value equality
act-order scale/shard association
middle/last layer packed mapping
per-shard permutation correctness
```

These require a valid reference or an explicit loader audit instrument and are
not inferred from HTTP success.

## 7. Earliest numerical divergence

Not measured. The current server API evidence is at final decoded output only;
no hidden-state/logit dump was enabled in the preserved launch. Since the same
17 input IDs reproduce the failure, the next valid step is a reference/backend
A/B or a purpose-built numerical dump, not optimization.

## Decision

Current isolation:

```text
A tokenizer/chat template: substantially excluded
B checkpoint/quantized weights: unresolved (reference blocked)
C Falcon-H1 implementation: unresolved
D GPTQ-Marlin loader/mapping: unresolved after topology fix
E GPTQ-Marlin GEMM/kernel: unresolved
F CUDA graph/scheduling: unresolved
```

The semantic anomaly is reproducible with exact HF-derived input IDs and is not
caused merely by omitting the chat template. The strongest current narrowing is
that the fault lies after tokenization, within the checkpoint interpretation,
Falcon-H1 implementation, GPTQ-Marlin loading/kernel, or scheduling path.

## Artifacts

```text
control/G001-falcon-h1-phase1/PHASE1D-REPORT.md
control/G001-falcon-h1-phase1/C6-ACCOUNTING.md
control/G001-falcon-h1-phase1/runs/phase1c-20260921-r2/server.log
control/G001-falcon-h1-phase1/runs/phase1c-20260921-r2/tokenizer-chat-template.json
control/G001-falcon-h1-phase1/runs/phase1c-20260921-r2/exact-hf-chat-input-ids.json
control/G001-falcon-h1-phase1/runs/phase1c-20260921-r2/official-messages.json
control/G001-falcon-h1-phase1/runs/phase1c-20260921-r2/official-completion-temp-0.json
control/G001-falcon-h1-phase1/runs/phase1c-20260921-r2/official-completion-temp-0.1.json
control/G001-falcon-h1-phase1/runs/phase1c-20260921-r2/short-correctness.jsonl
control/G001-falcon-h1-phase1/runs/phase1c-20260921-r2/concurrency-probe.jsonl
control/G001-falcon-h1-phase1/runs/phase1c-20260921-r2/over-8k-sentinel.json
```

The C6 service is currently stopped after the user-authorized transition to the
same-checkpoint reference attempt. GPU was released cleanly.

## Reference environment unblock attempt

An isolated environment was created at:

```text
/tmp/falcon-h1-hf-ref
```

The host `python3 -m venv --system-site-packages` did not expose the separate
`/home/ubuntu/venv` site-packages, so the isolated venv received a `.pth` file
pointing only at the existing site-packages directory. The original SGLang
venv was not modified.

Recorded reference baseline:

```text
Python 3.12.3
torch 2.13.0+cu129
CUDA reported by torch: 12.9
transformers 5.12.1
```

The requested dry-run was executed:

```text
transformers==5.12.1
optimum==2.3.0
accelerate
gptqmodel==7.5.0
```

It was blocked by a hard resolver conflict before installation:

```text
gptqmodel 7.5.0 depends on transformers>=5.14.0
requested transformers==5.12.1
```

pip result:

```text
ERROR: Cannot install gptqmodel==7.5.0, optimum==2.3.0 and
transformers==5.12.1 because these package versions have conflicting
dependencies.
```

No packages were installed, no Torch/CUDA package was changed, Transformers was
not upgraded or downgraded, and AutoGPTQ was not installed.

The exact dry-run record is:

```text
runs/phase1d-hf-gptq-reference/reference-env-dry-run.txt
```

Per the Phase 1D stop rule, the same-checkpoint reference remains BLOCKED at an
unsupported dependency seam. No SGLang fix or A/B reload was started.

## Official upstream SGLang v0.5.20 reference attempt

The fork audit was completed before starting the reference. The current fork is
at `f0075794b20a5b23d8b1b6cae417a8e10f2ae863`; its merge-base with the official
v0.5.20 peeled commit `94602c9c2b7cbdb8efd5c52802dac6a1c180089e` is
`b644771e07e39c8a5997a230f4e87175364c020b`. The current working tree has only
the previously documented Falcon-H1 source modification plus test/control
artifacts; no new source modification was made for this reference.

The exact official v0.5.20 wheel was installed in the independent environment
`/tmp/sglang-upstream-0520`, with `PYTHONPATH` explicitly empty. Its SGLang
module resolved to that environment, not to the fork. Torch/CUDA was reused from
the existing authorized installation: Torch 2.13.0+cu129, CUDA 12.9.

The checkpoint topology audit confirms:

```text
layer 0/middle/last self_attn.q_proj.weight  BF16 weight
layer 0/middle/last self_attn.k_proj.weight  BF16 weight
layer 0/middle/last self_attn.v_proj.weight  BF16 weight
layer 0/middle/last self_attn.o_proj.weight  BF16 weight
layer 0/middle/last mamba.*                  BF16/non-GPTQ tensors
layer 0/middle/last feed_forward.gate_proj.* GPTQ qweight/qzeros/scales/g_idx
layer 0/middle/last feed_forward.up_proj.*   GPTQ qweight/qzeros/scales/g_idx
layer 0/middle/last feed_forward.down_proj.* GPTQ qweight/qzeros/scales/g_idx
```

### `qkqkv_proj` origin

The malformed name was not present in the checkpoint. It was introduced by the
fork's pre-fix loader mapping: the loop mutated `name` in place while probing
`qkv_proj <- q_proj/k_proj/v_proj`. After a failed candidate, the next probe
operated on the already-rewritten name, producing `qkqkv_proj`. The current fork
eliminates this secondary symptom with immutable `original_name` and a fresh
`candidate_name` for each mapping attempt. It also prevents the primary topology
mismatch by constructing attention QKV and O with `quant_config=None`; FFN keeps
the global GPTQ config.

The corresponding upstream/fork source comparison is saved in
`runs/phase1d-upstream-reference-fork-diff.txt`. The upstream v0.5.20 Falcon-H1
loader has the same `qkv_proj <- q_proj/k_proj/v_proj` mapping shape but does not
contain the current fork's immutable-name defensive fix or the explicit
unquantized attention override. This identifies the previous local patch as the
source of the successful fork load, but does not yet provide a semantic A/B.

### Upstream runtime result

Launch parameters were deliberately held to the checkpoint declaration:

```text
--context-length 8192
--mamba-ssm-dtype bfloat16
HiCache OFF
speculative OFF
CUDA graph disabled for this semantic reference
```

Upstream selected GPTQ-Marlin before loading:

```text
The model is convertible to gptq_marlin during runtime. Using gptq_marlin kernel.
Attention backend defaulted to flashinfer.
```

Startup then blocked before model loading and before any HTTP endpoint became
available. The isolated environment required `flashinfer-python==0.6.18` and
`sglang-kernel==0.4.7`; after those were installed, the official kernel wheel
failed on this SM86/CUDA 12.9 host:

```text
ImportError: [sgl_kernel] CRITICAL: Could not load any common_ops library
Expected variant: SM86
found: SM100 common_ops
ImportError: libnvrtc.so.13: cannot open shared object file
```

The installed Torch runtime is CUDA 12.9, while the selected official wheel's
common-ops path requires an unavailable CUDA 13 runtime on this host. No model
class, mixed-topology runtime mapping, input IDs, output IDs, or semantic result
was produced.

```text
UPSTREAM REFERENCE: BLOCKED
GPTQ load: NOT REACHED
GPTQ semantic: NOT EVALUATED
BF16 control: NOT RUN
VERDICT: official upstream reference itself blocked by SM86/CUDA runtime seam
```

Per the requested stop rule, no BF16 control, no GPTQ A/B, no performance work,
and no source fix was started. Full launch identity and logs are in
`runs/phase1d-upstream-sglang-0520/`.

## Phase 1F result: BF16 graph isolation

The required 2x2 first branch was completed before any source modification.
The BF16 checkpoint `/tmp/falcon-h1-bf16` was run with context 8192,
`mamba_ssm_dtype=bfloat16`, batch 1, exact existing token IDs, and CUDA graphs
enabled. Graph capture completed for both prefill and decode.

The first France request reached prefill and returned HTTP 200, but the next
requests caused a scheduler crash during prefill graph replay:

```text
AcceleratorError: CUDA error: an illegal memory access was encountered
Fail when using backend: breakable for prefill runner.
```

The traceback identifies the failing graph path as:

```text
prefill_cuda_graph_runner.execute
  -> FalconH1ForCausalLM.forward
  -> replay_layer_forward
  -> unified_attention_with_output
  -> output[:real_query_num_tokens].view(ret.shape).copy_(ret)
```

The BF16 graph-on configuration therefore fails independently of GPTQ-Marlin.
This is a decisive branch result:

```text
BF16 eager: PASS
BF16 graph: FAIL (prefill graph replay illegal memory access)
GPTQ eager: PASS
GPTQ graph: FAIL (previous Phase 1E result)
```

The primary root-cause domain is now Falcon-H1/hybrid model CUDA graph
integration, specifically the prefill breakable graph path or its interaction
with unified attention output buffers. GPTQ-Marlin is no longer the primary
explanation for the graph-on failure.

Per the requested STOP condition, F2 prefill/decode separation, F3 decode
minimization, F4 first-token logits boundary, F5 Mamba state audit, F6 GPTQ
micro-A/B, and repair were not started. No source patch was made.

```text
VERDICT: ROOT CAUSE ISOLATED to BF16 Falcon-H1 prefill CUDA graph path
PATCH: none
```

Artifact:

```text
runs/phase1f-bf16-graph-on/server.log
runs/phase1f-bf16-graph-on/server.pid
```

## Phase 1G result: safe prefill fallback

Phase 1G first tested the phase split explicitly using the supported parser
flags `--cuda-graph-backend-prefill` and `--cuda-graph-backend-decode`.

Resolved configuration was verified in `server_args=` and capture logs:

```text
prefill: disabled
decode: full
```

With this split, both models were semantically correct for the canonical cases:

```text
BF16: France PASS; 2+3 PASS; sentinel PASS
GPTQ: France PASS; 2+3 PASS; sentinel PASS
```

The BF16 and GPTQ servers both captured decode graphs, and their logs showed
`cuda graph: True` on decode. BF16 additionally completed the requested c=1,
c=2, and c=4 matrix and ten deterministic prompts without corruption. GPTQ
completed the canonical cases and decode-graph capture; its first matrix script
was interrupted by an external orderly server shutdown before artifact
serialization, but the server log contains successful eager-prefill and
CUDA-graph decode requests for all three canonical cases.

The requested `tc_piecewise` experiment was attempted on BF16. It did not
produce a semantic result: the tc_piecewise capture path failed during graph
compilation/capture in the Falcon-H1 Mamba Triton path, with a PyTorch Dynamo
graph-break failure around `mamba_chunk_scan_combined`/`_chunk_cumsum_fwd`, and
the process was killed. Thus tc_piecewise is not selected.

The narrow source patch is in `python/sglang/srt/server_args.py`. During
`_apply_cuda_graph_compatibility`, when the architecture is exactly
`FalconH1ForCausalLM` and no explicit prefill backend was supplied, it now:

```text
disables only Phase.PREFILL
leaves Phase.DECODE unchanged (default full)
emits a WARNING naming the fallback and the override flag
```

An explicit user setting remains authoritative because the lock check precedes
the fallback. This is not a whole-model CUDA-graph disable.

A focused source-regression test was added at
`test/registered/unit/test_falcon_h1_cuda_graph_policy.py`. `py_compile` and
`git diff --check` pass. The pytest command could not run because the current
`/home/ubuntu/venv` has no pytest module; this is an environment verification
blocker, not a source test failure.

```text
VERDICT: SAFE-FALLBACK
BF16 prefill-disabled + decode-graph: PASS
GPTQ prefill-disabled + decode-graph: PASS for canonical cases
BF16 tc_piecewise: BLOCKED/FAIL during capture compilation
GPTQ tc_piecewise: NOT RUN after BF16 failure
breakable prefill: known FAIL
PATCH: architecture-level Falcon-H1 prefill disable, decode graph retained
```

No performance, HiCache, Mamba slot, 32K, or throughput work was performed.

Artifacts:

```text
runs/phase1g-bf16-prefill-off-decode-on/server.log
runs/phase1g-bf16-prefill-off-decode-on/semantic.json
runs/phase1g-bf16-prefill-off-decode-on/matrix-c1-c2-c4-10.json
runs/phase1g-gptq-prefill-off-decode-on/server.log
runs/phase1g-gptq-prefill-off-decode-on/semantic.json
runs/phase1g-bf16-tc-piecewise/server.log
```

## Phase 1E result: BF16 control and CUDA-graph isolation

The official BF16 checkpoint was downloaded to `/tmp/falcon-h1-bf16` without
modifying the GPTQ checkpoint. The current fork was run with context 8192,
`mamba_ssm_dtype=bfloat16`, batch 1, and CUDA graphs disabled. The exact token
IDs from the existing `inputs.json` artifact were used.

BF16 results were semantic PASS for all three cases:

```text
France:     The capital of France is Paris. ...
2+3:        5
sentinel:   FALCON_SENTINEL_7B
```

The same current fork and exact token IDs were then run against the GPTQ
checkpoint at context 8192 with CUDA graphs disabled. GPTQ-Marlin loaded and all
three cases were also semantic PASS:

```text
France:     The capital of France is Paris. ...
2+3:        5<|im_end|>\n
sentinel:   FALCON_SENTINEL_7B<|im_end|>\n
```

Ten additional deterministic prompts were coherent and correct enough for the
requested semantic gate (arithmetic, factual, completion, and exact-repeat
cases); see `runs/phase1e-gptq/ten-prompts.json`.

A final GPTQ run enabled CUDA graphs, leaving all other variables unchanged.
Startup and graph capture completed, but the exact same three cases failed:

```text
France:     nner = (int) (Math.random() *
2+3:        sixteen <|pad|> tokens, output IDs all 0
sentinel:   unrelated multi-step reasoning text
```

This is a decisive graph-only semantic regression. BF16 CUDA-graph-off PASS
excludes a basic tokenizer, Falcon-H1 architecture, Attention, Mamba, or basic
logits-path failure. GPTQ CUDA-graph-off PASS excludes an always-on GPTQ-Marlin
semantic failure for this checkpoint and configuration. The first decisive
numerical/runtime divergence is therefore narrowed to CUDA graph capture/replay
interaction in the hybrid Falcon-H1 execution. It is not yet proven to be
GPTQ-Marlin arithmetic, so the requested low-level single-linear A/B was not
started after this stronger stop condition. No source patch was made.

```text
VERDICT: NARROWED
BF16 control: PASS
GPTQ CUDA graph OFF: PASS
GPTQ CUDA graph ON: FAIL
first divergence: CUDA graph capture/replay
```

Artifacts:

```text
runs/phase1e-bf16/server.log
runs/phase1e-bf16/semantic-cases.json
runs/phase1e-gptq/server.log
runs/phase1e-gptq/semantic-cases.json
runs/phase1e-gptq/ten-prompts.json
runs/phase1e-gptq-graph-on/server.log
runs/phase1e-gptq-graph-on/semantic-cases.json
runs/phase1e-summary.txt
```

## Corrected isolated reference environment attempt

The constraint was corrected: the reference venv was allowed to use
Transformers 5.14.0 while the production SGLang environment remained untouched.

Dry-run with:

```text
transformers==5.14.0
gptqmodel==7.5.0
accelerate
```

completed without replacing Torch/CUDA. The packages were installed only in
`/tmp/falcon-h1-hf-ref` (Torch was intentionally reused from the existing
site-packages path as authorized).

Verified module paths:

```text
torch 2.13.0+cu129
  /home/ubuntu/venv/lib/python3.12/site-packages/torch/__init__.py
transformers 5.14.0
  /tmp/falcon-h1-hf-ref/lib/python3.12/site-packages/transformers/__init__.py
gptqmodel 7.5.0
  /tmp/falcon-h1-hf-ref/lib/python3.12/site-packages/gptqmodel/__init__.py
accelerate 1.15.0
```

`GPTQModel.load(..., device='cuda:0', backend='auto')` reached kernel selection:

```text
candidates: MarlinLinear, ExllamaV2Linear, TritonV2Linear, TorchLinear
per-module: MarlinLinear=352, TorchLinear=44
selected: MarlinLinear
```

It then failed before inference in GPTQModel's strict checkpoint validation:

```text
ValueError: Missing required quantized weights in checkpoint ...
```

The missing list covers every layer's:

```text
model.layers.N.mamba.in_proj.qweight
model.layers.N.mamba.out_proj.qweight
model.layers.N.self_attn.q_proj.qweight
model.layers.N.self_attn.k_proj.qweight
model.layers.N.self_attn.v_proj.qweight
model.layers.N.self_attn.o_proj.qweight
```

These tensors are intentionally BF16/non-GPTQ in the official mixed topology;
they are not absent from the checkpoint. GPTQModel 7.5.0's direct loader expects
all these linear modules to be quantized and rejects the mixed BF16-attention /
BF16-Mamba + GPTQ-FFN checkpoint before inference.

Therefore:

```text
REFERENCE ENV: PASS (isolated dependencies installed)
GPTQMODEL AUTO: load BLOCKED at mixed-topology validation
GPTQMODEL MARLIN: not run
semantic: not evaluated
```

No GPTQModel source was changed, no checkpoint was changed, and no production
SGLang environment was changed. The exact environment record is:

```text
runs/phase1d-hf-gptq-reference/reference-env-installed.txt
runs/phase1d-hf-gptq-reference/pip-freeze.txt
runs/phase1d-hf-gptq-reference/gptqmodel-auto-result.json
runs/phase1d-hf-gptq-reference/gptqmodel-auto.stderr.log
```
