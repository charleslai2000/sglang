# GSM8K Prefill logits across engines — 2026-10-27

## Scope and identity

Captured full-vocabulary logits for the final prompt token on identical saved GSM8K prompts, docs 18 and 36. SGLang Eager and Graph ran against the pinned checkpoint with BF16 KV, Triton attention, batch=1, no Radix cache. vLLM ran C1 with `max_num_seqs=1`, eager execution, BF16 compute/automatic KV, Triton attention, no prefix caching. Both use the same pinned checkpoint SHA recorded in `GSM8K-FULL-VLLM-20261027.md`.

Input identity is directly verified: doc 18 has 797 identical token IDs and doc 36 has 928 identical IDs. SGLang capture records the pinned revision/SHA; vLLM worker capture records the exact input and was launched from the same local pinned model directory, while its artifact itself does not carry a checkpoint hash. SGLang Eager/Graph prefill logits are bitwise identical for each prompt. SGLang positions are 1..N; vLLM positions are 0..N-1, matching the per-engine positional convention and each engine's own forward. This offset is a known semantic difference and prevents calling the run position-matched. Both runtimes load compressed-tensors W4A16 through Marlin paths, but no post-load per-parameter effective weight fingerprint exists; weight equivalence is unproven.

## Results

For doc 18, both engines choose token 45917 as top-1; full-logit max/mean absolute difference is 0.52137/0.11640. The SGLang and vLLM top-1 margins are 0.41759 and 0.5. For doc 36, both choose token 38778; max/mean absolute difference is 0.57052/0.14411, with margins 0.96034/1.0. Prefill computations are therefore not numerically identical for either prompt despite same token IDs and equal top-1. An initial combined vLLM attempt failed its request-ID assertion because the vLLM request processor appends an ID suffix; the actual bound RID was checked in the worker artifact and a separate doc36 run captured successfully.

Artifacts:
- SGLang Eager/Graph logits, responses and service logs: `/data/sglang-hicache/gemma4/runs/20261027T-gsm8k-prefill-logit-probe/`
- vLLM doc18 and doc36 raw captures: `/data/sglang-hicache/gemma4/vllm-gemma4/captures/c9a27c6ead6a488e873da5441d8ceda5/raw-logits-79814-138969986644512.pt` and `/data/sglang-hicache/gemma4/vllm-gemma4/captures/50cc833cea294888b0faf4fc3dec3637/raw-logits-80901-127981308436208.pt`; bound worker markers in their respective directories.

## Interpretation

These Prefill captures are not the first cross-engine calculation divergence: positions differ by one and effective quantized weights were not compared. The later doc8 same-history decode comparison is recorded in `GSM8K-DOC8-SAME-HISTORY-20261030.md`; it establishes different Top-1s under different per-engine positions, but not a production semantic defect. No new sample or weight experiment is opened here. Frozen HF N512/514 guard remains FAILED; G1 remains NOT ACCEPTED.
