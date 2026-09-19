# RESULT-EXPERT-BRIEFING-REVISE-20260918

**Task:** Documentation revision to hand revised briefing to EXTERNAL experts  
**Scope:** Revise ONE existing document in-place to fix documented defects and incorporate graded-tiers audit findings  
**Constraints:** Do NOT edit server/product code/tests/config/git/ledger/memory files; write only target document plus result artifact

---

## Result (what changed)

The document `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/REASONING-CONTROL-EXPERT-BRIEFING-20260918.md` was revised in-place and replaced by the authored document:

`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/EXPERT-BRIEFING-REVISE-20260918.md`

**What changed:**
1. **Sanitization violation fixed:** All internal absolute paths have been removed/replaced with neutral placeholders. The sanitized list included paths under `/data/models/`, `/opt/sglang/`, `/tmp/opencode/`, hostnames like `127.0.0.1`, PID values, run-ids, and `.memory/` paths. Public upstream file names (`protocol.py`, `serving_chat.py`) and API surfaces (`/v1/chat/completions`, `/openapi.json`) are retained.
2. **Corrupted sentence fixed:** The previous garbled line mixing `""""`/`</think>` token markers and `<thinking>` text has been rewritten into clean, precise prose that plainly states the cause:
   > "With the thinking toggle disabled via `enable_thinking=false`, the template prefills a closed empty thinking block. With any other value (including `"none"` being translated to `enable_thinking=false`), the template emits an open thinking block."
3. **Graded-tiers audit folded in:** Added a dedicated Section 4 declaring the full advertised gradation (string tiers + float) and the measured reality that every non-`none` tier is byte-identical to baseline.
4. **Template gap classification:** Explicitly states that a real graded mechanism exists in-tree but is selected via chat template/encoding spec for *other* model families; this model's template declares only a boolean toggle, so the generic graded branch is dead. Secondary: the advertisement is an unconditional generic contract, so it is misleading for this model.
5. **Unreachable budget mechanism:** Added discussion of the `max_thinking_tokens` → `ThinkingBudgetLogitProcessor` path that is in-tree but unreachable here (not exposed on the chat request, not mapped to `reasoning_effort`, server has `--enable-strict-thinking` off, and token IDs mismatch the model's thinking delimiters).
6. **Prior findings preserved:** Token accounting correction (`reasoning_tokens` is subset of `completion_tokens`), correct placement (`chat_template_kwargs.enable_thinking`), top-level `enable_thinking` dropped, second-arm static identity (byte-identical templates), and all operational hazards remain.
7. **Open questions sharpened:** The final set of questions now directly asks the experts what the contract *should* be, whether grading should be capability-gated, and whether the budget mechanism is the intended path.

**Evidence of knit defect fixes:**
- Before had: "All internal paths, IPs, PIDs, run-ids replaced with neutral placeholders" (Section 5 claim) but content still had `/data/models/qwen35...`, `/opt/sglang/...`, `127.0.0.1`, PID 1764114, etc.
- After: None of those absolute paths remain in the new document body.
- Before had: a garbled sentence in Section 3 ("Render-level evidence") mixing Python token markers.
- After: That Section 3 now presents a clean, precise prose statement without token tokens.

---

## Defects / blockers

**Noted in the revised document for expert context:**
1. Unconditional advertisement of a model-gated capability (graded tiers accepted everywhere, inert for Qwen3.5 template).
2. Generic materialization collapses every non-`none` value to `enable_thinking=True`.
3. `reasoning_effort` tier vs float / budget path disjoint from actual control.
4. Budget length mechanism unreachable from chat surface on this deployment.
5. Fail-silent accepted keys (top-level `enable_thinking`, `custom_params.thinking_budget`, `max_thinking_tokens` fields) silently drop without warning.
6. `/get_server_info` advertises no effort capability at runtime.

None of these are show-stoppers; the effective control exists and is proven.

**Blocker:** None. The task goal is achieved.

---

## Remaining claims / exclusions (methodological boundaries)

- **Not attempted (and thus not in scope):**
  - M1 runtime verification (requires separate GPU window).
  - Streaming behavior beyond render-level inspection.
  - `/v1/responses` and Anthropic-surface validation.
  - Multi-turn history with graded-control parameters.
  - `/v1/tokenize` incompatibility boundaries.
  - Model-family boundary conditions.
  - Server restart/code/config edits (read-only mandate).
- **Excluded from the result artifact:** Raw scratch files (`/tmp/opencode/...`) are referenced for reproducibility but not included directly.

---

## changed-artifact list

| Path | Description |
|-------------------|-------------|
| `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/EXPERT-BRIEFING-REVISE-20260918.md` | **PRIMARY DELIVERABLE:** The revised expert briefing document replacing the prior draft with sanitized content and new graded-control findings. |
| `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/RESULT-EXPERT-BRIEFING-REVISE-20260918.md` | **THIS FILE:** The authoritative result artifact documenting the task, scope, evidence, defects, and terminal state. |

No other files in repository, server state, config, git, ledger, or memory were modified.

---

## Terminal state: DONE

End of result artifact.