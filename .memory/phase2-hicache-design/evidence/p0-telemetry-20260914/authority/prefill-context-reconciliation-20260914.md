# Prefill context reconciliation (2026-09-14)

**Task:** `LOCAL-PERF-PREFILL-CONTEXT-RECONCILIATION-20260914`  
**Status:** read-only architecture recommendation; no performance claim  
**Boundary:** no GPU/server execution, lock acquisition, or source/model/cache/spec modification. Existing run artifacts remain authoritative and unchanged for what they actually record.

## Decision for orchestrator acceptance

Adopt token-exact prefill cells under the unchanged canonical serving profile. Replace the ambiguous cell identity `prefill-i<N>-c<C>` for future runs with `prefill-it<N>-ot32-c<C>`, where `it` means the **fully chat-templated input token count** and `ot` means requested output tokens.

The required corrected cells are:

| Spec cell | New cell ID | Required templated input | Requested output | Concurrency |
|---|---|---:|---:|---:|
| 2K/C1 | `prefill-it2048-ot32-c1` | 2,048 tokens | 32 tokens | 1 |
| 2K/C4 | `prefill-it2048-ot32-c4` | 2,048 tokens/request | 32 tokens/request | 4 |
| 8K/C1 | `prefill-it8192-ot32-c1` | 8,192 tokens | 32 tokens | 1 |
| 8K/C4 | `prefill-it8192-ot32-c4` | 8,192 tokens/request | 32 tokens/request | 4 |
| 32K/C1 | `prefill-it32768-ot32-c1` | 32,768 tokens | 32 tokens | 1 |
| 32K/C4 | `prefill-it32768-ot32-c4` | 32,768 tokens/request | 32 tokens/request | 4 |
| 64K/C1 | `prefill-it65536-ot32-c1` | 65,536 tokens | 32 tokens | 1 |
| 64K/C4 | `prefill-it65536-ot32-c4` | 65,536 tokens/request | 32 tokens/request | 4 |

The v2 64K cells are therefore **not N/A** and must not be replaced by a 196K cell. A separately named capacity-edge cell could use at most 196,210 templated input tokens with output 32 under the observed canonical capacity, but that is not required by PERFORMANCE-BASELINE-SPEC-v2 and is not proposed for the current baseline.

## Observed facts

### Label and prompt construction

1. `perf_harness.py:31-40` passes the numeric `--input` value to `range(length)` and emits that many whitespace-separated strings of the form `w0` through `w996`. It does not construct characters or tokenizer tokens to the requested length.
2. The old `65536` input therefore means **65,536 generated `wN` corpus items** (word-like whitespace-separated units), not 65,536 characters and not 65,536 tokens. Including the fixed instruction, the inspected request has 65,561 whitespace-separated fields and 320,594 characters.
3. The same harness comment says the text is tokenizer-independent and that exact prompt tokens are measured only from server usage. Consequently, `input_budget` and the `2K/8K/32K/64K` IDs were not enforced token budgets.
4. Local, read-only tokenization with the model tokenizer and the recorded chat request shape reproduced the server counts exactly:
   - old `2048` item input -> 8,027 templated tokens/request;
   - old `8192` item input -> 31,837 templated tokens/request;
   - old `32768` item input -> 127,498 templated tokens/request;
   - old `65536` item input -> 254,940 templated tokens/request.
5. The 64K response and server log both report `Input length (254940 tokens) exceeds ... (196238 tokens)`. This is tokenization expansion of the `wNNN` corpus plus fixed/chat-template framing, not a model-generated-token count.

### Chat-template contribution

The request uses one user message, `chat_template_kwargs.enable_thinking=false`, and `add_generation_prompt` on the server path. `chat_template.jinja` wraps the content with user/assistant control text and adds an empty think block. This framing is included in the reproduced 254,940 and 127,498 counts. It is small relative to the repeated corpus; the dominant expansion is that each textual `wNNN` item commonly tokenizes into multiple tokens. Exact accounting must nevertheless occur after the final marker and complete chat template are applied.

### Canonical context and memory limits

1. Model `config.json` and `tokenizer_config.json` both declare 262,144 as the model/tokenizer context limit.
2. Both retained canonical argv files contain only the model, host/port, `--mem-fraction-static 0.8`, and `--disable-prefill-cuda-graph`; no context, total-token, prefill-token, or auto-truncation override is present.
3. The retained server log resolves:
   - `context_len=262144`;
   - allocated/effective token capacity `max_total_num_tokens=196244`;
   - `max_prefill_tokens=16384`;
   - `chunked_prefill_size=2048`.
4. Source ownership explains the admission number: `tp_worker.py:get_worker_info()` computes `max_req_len=min(context_len-1,effective_max_total_num_tokens-1)=196243` and exports `max_req_input_len=max_req_len-5=196238`. `validate_input_length()` rejects an input whose length is greater than or equal to that boundary; the user-facing message prints 196,238.
5. `max_prefill_tokens=16384` is a scheduler batch/chunk budget, not the whole-request context ceiling; retained successful requests of 127,498 prompt tokens demonstrate chunked prefill across that budget.
6. For a requested output of 32, the scheduler's page/reserve formula preserves all 32 requested output tokens through a maximum templated input of **196,210 tokens** with page size 1: `196244 - 196210 - 1(page) - 1(strict reserve) = 32`. This is below the independent input-rejection boundary of 196,238 and the model context limit. Thus 196,210 is the exact observed canonical capacity-edge input budget for the input-196210/output-32 combination, not the v2 64K input.

### 32K/C4 context

The old 32K label also represented 32,768 generated `wN` items, yielding 127,498 templated tokens/request. It did not partially fail because of context length:

- canonical run retained 32K/C4 warmup and repeat 1 with exit 0 and semantic pass;
- the missing-run retained repeats 2 and 3 with exit 0, 20/20 HTTP 200, and 20/20 semantic-valid responses in each repeat;
- C1 retained all three measured repeats;
- 127,498 is below the 196,238 input-admission boundary.

The original run was incomplete at 32K/C4 after repeat 1, but the retained evidence does not attribute that incompleteness to a context rejection. The continuation completed the two missing repeats. These old results remain evidence for a **127,498-token workload**, not for a token-exact 32K workload.

## Specification comparison

PERFORMANCE-BASELINE-SPEC-v2 requires “2K, 8K, 32K, 64K input plus 32 output at C1 and C4” and requires manifests to freeze prompt/output budgets. In performance-model terminology and in the same specification's metric formulas, input accounting is in tokens. The old harness used generated corpus-item counts while naming the field `input_budget`; this violates comparability and budget identity even where requests passed.

The minimal matrix correction is a workload/input-contract correction, not a serving-profile correction:

- retain all old runs unchanged and label them legacy word-item-generated workloads;
- create future token-exact cells with unambiguous IDs;
- keep the canonical argv unchanged;
- do not use `--allow-auto-truncate`, because silent truncation would destroy cell identity;
- do not raise `--mem-fraction-static`, set `--max-total-tokens`, or select another context profile;
- do not mark 64K N/A, because 65,536 + 32 fits the observed canonical constraints;
- do not substitute 196,210 for the required 64K cell, because that would be a different capacity-edge workload.

## Input construction interface

For every request, construct content only after the final marker is known, apply the exact recorded chat template with `enable_thinking=false` and generation prompt enabled, and measure token IDs with the frozen model tokenizer. Add deterministic filler whose token increment is known under that tokenizer, then verify the final fully templated token count equals the cell's `it` value. The read-only probe established that repeated `" x"` contributes exactly one token per repetition for the current tokenizer/template; marker-dependent fixed overhead must be measured per final request rather than assumed constant.

Do not send raw tokenizer IDs through a different API in the same matrix: that would change the interface from the canonical OpenAI chat path and bypass template behavior. Do not rely only on preflight tokenization: retain server `usage.prompt_tokens` as the execution-time acceptance check when a future authorized run occurs.

## Acceptance criteria for a future authorized run

1. Cell ID parses as `prefill-it<INPUT>-ot32-c<CONCURRENCY>` and no ambiguous `i<INPUT>` ID is used for new token-exact evidence.
2. Each request's locally recorded fully templated input count equals exactly `<INPUT>` after its final unique marker is substituted.
3. Server `usage.prompt_tokens` equals `<INPUT>` for every successful request; any mismatch invalidates the affected cell rather than being averaged or relabeled.
4. Requested completion budget remains 32, auto-truncation remains disabled, and retained effective argv/profile is byte-for-byte equivalent except for run identity/port representation where applicable.
5. Semantic, repeat, request-count, telemetry-unavailability, artifact identity, and hash gates continue to follow PERFORMANCE-BASELINE-SPEC-v2. This reconciliation does not waive any existing gate.
6. Existing `prefill-i*` artifacts are preserved and are not used as token-exact 2K/8K/32K/64K claims.

## Rejected alternatives

- **64K = N/A:** rejected; true 65,536-token input plus 32 output is below all observed canonical limits.
- **Rename old 64K to 254,940 tokens and accept it:** rejected; it was rejected by admission and produced no semantic-valid workload evidence.
- **Reduce the required 64K cell to 196,210:** rejected; that is larger, not reduced relative to token-exact 64K, and changes the specified workload meaning.
- **Use a separate larger-context serving profile:** rejected for this baseline by scope and unnecessary for 64K; it would create a distinct run identity/profile.
- **Enable auto-truncate:** rejected; actual input would cease to equal declared input and requests could differ after marker/template expansion.
- **Change `max_prefill_tokens` to exceed 64K:** rejected; it controls chunk scheduling and is not the request-length blocker.

## Risks, uncertainty, and reversibility

- The 196,210 edge value is derived from the retained effective capacity and inspected source revision; a future startup with different memory availability or source bytes must recompute it. This does not affect the fixed 65,536-token recommendation, provided preflight confirms it remains within the future effective budget.
- Token counts are tokenizer/template/marker dependent. Freezing only corpus text is insufficient; freeze tokenizer identity, template hash, final rendered request accounting, and server usage.
- The exact reason the first run stopped after 32K/C4 repeat 1 is not established by the bounded evidence. It is unnecessary to the context conclusion because the retained repeat succeeded and the continuation completed the missing repeats.
- The recommendation is reversible: it adds a new, explicit workload namespace while preserving all old artifacts and profiles. It does not approve execution or a spec amendment; orchestrator acceptance is required.
