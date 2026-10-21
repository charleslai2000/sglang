# Gemma 4 E4B on RTX 3090 — G0/G1

## Goal
Using the existing SGLang HiCache fork, establish a dedicated `3090-gemma4-e4b-hicache` branch and deliver a real, stable text-generation service on one RTX 3090 24GB using `google/gemma-4-E4B-it-qat-w4a16-ct`, official QAT W4A16 compressed-tensors weights, correct FP8 KV, and CUDA Graph decode. Reuse mature upstream SGLang Gemma 4 implementation; do not reimplement models or infrastructure.

## Scope
- Pin the model revision and runtime/kernel/dependency identities.
- Verify Ampere SM86 W4A16 linear kernels, Gemma 4 PLE, global/SWA attention, and shared-KV semantics.
- Establish numerically trusted fixed-token references and predeclared tolerances; validate FP8 KV prefill/decode/shared layers across batch sizes, SWA boundaries, long context, and continuous decode.
- Validate chat template, streaming, EOS/stop, cancellation, concurrent requests, and CUDA graphs.
- Measure actual GPU memory ledger, physical and usable logical KV capacity, KV bytes per physical slot/token, shared ownership/deduplication, actual request occupancy, stable concurrency, OOM boundary, and C1/C4/C8 with C16/C32/C64 where feasible. Target ~1,059,707 logical tokens and C64 as challenges, never inferred from config or third-party vLLM numbers.
- Diagnose shortfalls and implement necessary safe fixes; no semantic relaxation, disabling required shared state, or fictitious over-allocation.

## Exclusions
No multimodal serving, MTP, L2/L3 HiCache, or renewed Falcon T004/T005 acceptance. Preserve all pre-existing dirty/untracked state. No new worktree, clean checkout, reset, or broad staging. Keep Falcon-specific uncommitted changes out of Gemma commits.

## Completion
On the actual RTX 3090, provide stable and auditable SGLang text generation with the pinned W4A16 checkpoint, correct FP8 KV and working CUDA Graph decode; establish trusted correctness across required edge cases and a real memory/KV/concurrency/performance ledger. Explicitly report whether 1,059,707 tokens and C64 are achieved. Commit and push only validated Gemma-owned changes and evidence. No PARTIAL/NOT_RUN/NOT_VERIFIED result counts as completion.

## Starting baseline
Created in the sole existing worktree from `3090-24g-hicache` at `7a55c24a31e8a282183767f7641f82e4b659e88c`; origin at branch creation matched this SHA. Existing tree had 51 modified, 1 deleted, and 750 untracked status entries, preserved byte-for-byte at status-snapshot level through branch creation. No index changes. The tracked deletion `control/AGENTS.md` is an intentional migration to root `AGENTS.md`, confirmed by Owner; root file contains the control discipline.
