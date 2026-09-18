# QWEN3CODER-SCOPE-ADJUDICATE-20260918

Status: DONE
Terminal state: DONE
Task: Adjudicate scope + EOS behaviour for the `qwen3_coder` detector fix (P1 spec vs P2 reviewer).
Role: architect (read-only analysis + normative adjudication; no implementation).

## Task

Settle the P1-vs-P2 disagreement about the `qwen3_coder` parser fix with LOCAL evidence and produce ONE
normative rule set + minimal write scope. Inputs: (P1) the pre-existing spec `spec-sglang-qwen3coder-fix`
(five defects + I2 "finish() closes the JSON", scope "prefer minimal; may modify `base_format_detector.py`");
(P2) the owner-relayed expert correction (1 production file + 1 test file; do not touch
`function_call_parser.py` or `BaseFormatDetector` unless production does not go through `Qwen3CoderDetector`;
unknown NAME should not produce `-1`; NEW delay-commit/framing requirement; EOS on unclosed `<tool_call>`
must return the segment as ordinary content, NOT repair it into a call).

Deliverables: (A) production-path trace; (B) per-defect local verification incl. exact `-1` attribution;
(C) contract reconciliation for EOS/framing; (D) adjudicated normative rule set + minimal write scope +
acceptance table. Read-only; no source edits; no `/opt` writes; no GPU; no service ops; no git mutation.

## Scope

- IN: reading both local trees (repo + frozen `/opt`), the launcher/config/manifest identity surfaces, the
  P1 spec, the owner/expert messages and ledger records, the opencode session store (read-only SQLite URI),
  and the recorded live-process evidence; CPU-only read-only probes of the detector from the frozen tree.
- OUT: implementing the fix; editing any source/test/config; touching `/opt` (read-only inspection only);
  GPU; service stop/start; git mutation (no commit/checkout/reset/stash); any write other than this artifact.
- Writes: this artifact only. Scratch probe scripts under `/tmp/opencode/qwen3coder-adjudicate-20260918/`
  (allowed by dispatch).

## Result

### R0. Adjudicated write scope (minimal; P2's restriction is CORRECT for this tree)

**Exactly 1 production file + 1 test file:**

1. `python/sglang/srt/function_call/qwen3_coder_detector.py` (repo), later landed into the frozen tree's
   same path under the existing pin procedure (separate authorized landing step; see R7).
2. `test/registered/unit/function_call/test_function_call_parser.py` — extend the existing
   `TestQwen3CoderDetector` (class at :2289). This is the repo's established function-call test file; do
   NOT invent a new hierarchy.

**Do NOT touch** `function_call_parser.py`, `base_format_detector.py`, `template_detection.py`, serving
files, or the frozen tree in this fix task. Justification by evidence (not preference):
- `function_call_parser.py:92` maps `"qwen3_coder" -> Qwen3CoderDetector`; production's explicit flag
  (`--tool-call-parser qwen3_coder`, frozen `launcher/launch.sh:166`) plus a live log line from
  `qwen3_coder_detector.py:91` prove production DOES route through `Qwen3CoderDetector` (R1). P2's stated
  exception condition ("unless tracing proves production does not go through Qwen3CoderDetector") is NOT
  met, so P2's prohibition on base/parser edits STANDS.
- `Qwen3CoderDetector` overrides both `detect_and_parse` and `parse_streaming_increment` and never calls
  `parse_base_json` (verified by source grep and by introspection, probe6). The shared base's
  `tool_indices.get(name, -1)` (`base_format_detector.py:92`) is NOT reachable from `qwen3_coder`; the
  base's shared streaming path is also overridden. The `-1` that P1 found is produced by the detector's own
  use of the inherited `current_tool_id` (R2.iii) and is fixable inside the detector.
- The writing code may manage its own commit-time index and buffer state; no base edit is required.
- Landing into the frozen tree (Q3b) is a *different* authorized procedure (4 pin surfaces, mode 444/555)
  and is NOT part of this fix's write scope; it depends on the fix being frozen first.

**Regression canary that must pass UNCHANGED** (do not edit without a separate adjudication):
`test/registered/unit/entrypoints/openai/test_serving_responses_stream.py::MultiToolCallStreamingOrderTestCase`
(composes cumulative qwen3_coder frames; delay-commit changes when calls appear, and this test verifies
delta ordering / no duplicate item / arguments). If it cannot pass, that is a blocker for the owner — not
authorization to expand scope.

### R1. Which of the five defects survive (against LOCAL bytes)

| # | Defect | Verdict | Note |
|---|---|---|---|
| (i) | duplicate `</function>` emits extra `}` | **CONFIRMED** (streaming only) | non-stream path already tolerates it |
| (ii) | missing `</function>` leaves arg JSON unclosed | **CONFIRMED** (streaming only) | non-stream path already closes; streaming outcome is superseded by the EOS rule R4 |
| (iii) | `-1` on the production path | **CONFIRMED, re-attributed** | comes from detector's own use of inherited `current_tool_id`, NOT from shared `parse_base_json` |
| (iv) | inherited `finish()` is a no-op | **CONFIRMED** | becomes load-bearing: delay-commit REQUIRES an override to release held text at EOS |
| (v) | streaming name extraction swallows text | **CONFIRMED** (also non-stream) | exact observed shape reproduced |

### R2. `-1` attribution (settled with code, not inference)

- The only `-1` source on the `qwen3_coder` path is `self.current_tool_id: int = -1` initialised in
  `BaseFormatDetector.__init__` (`base_format_detector.py:45`), incremented only at `<function=`
  (`qwen3_coder_detector.py:285`), and used in the detector's own emits (`:293, :353, :376, :395, :400`).
  An orphan `<parameter>` / stray `</function>` therefore emits `ToolCallItem(tool_index=-1)`.
- The shared base's `tool_indices.get(name, -1)` (`base_format_detector.py:92`) CAN produce `-1`, but ONLY
  for detectors that call `parse_base_json`. `Qwen3CoderDetector` does not call it and overrides both public
  parse methods, so this path is UNREACHABLE for `qwen3_coder`. P2 hypothesis (b) is REFUTED for the
  production path; the live detector is provably exercised (log warning from `:91`).
- P2's positive claim is CONFIRMED: an unknown tool NAME does not itself yield `-1` (local probe: `cat`,
  `qquestion` get index 0, name passed through). The `-1` requires a parameter/close fragment with no
  preceding `<function=` in the same stream.
- P2 hypothesis (a) "local version/branch differs from upstream" is REFUTED for the framing/index logic:
  frozen `qwen3_coder_detector.py` sha256 `92eeaeaf…8089` == repo `HEAD` blob == `origin/3090-24g-opt`
  (provenance proven, not asserted); the local `main`/`origin/main` blob (`adf38ad6…`) differs only in the
  `_get_arguments_config` schema-properties extraction (11 diff lines), NOT in the index/framing code.

### R3. Framing rule (delay commit) — ADOPTED

**FRAMING (normative):** A `ToolCallItem` MUST NOT be emitted before the complete framing of its call is
observed. For a `<tool_call>` block this means the block must be seen through `</tool_call>`, the
`<function=NAME>` name must be well-formed (non-empty; no `<`, `>`, or whitespace), and every
`<parameter=` value must be terminated (`</parameter>`, the next `<parameter=`, `</function>`, or the
closing `</tool_call>`). Indexes are assigned at commit time and are strictly increasing per committed call
and never negative. The detector composes each committed call's `parameters` internally, so a committed
call is always a complete JSON object (never a partially emitted `{`).

Rationale (local evidence, since the named contract docs are not present — R6):
- The owner's binding framing (ledger `2026-09-18` + owner message): gateway = trust boundary that always
  validates wire invariants; SGLang's duty is to not GENERATE illegal wire states. A complete-JSON,
  non-negative-index call is the only shape committed.
- Owner-relayed expert correction (message `prt_0b1946b4d0016OuagGDQcXCBND`, later in time than P1):
  "当前 streaming 在看到 `<function=name>` 后就已经 emit tool call，早于 `</tool_call>` … 契约要求完整
  framing 后才能成为 structured call … 在这个 detector 内延迟 commit."
- In-repo precedent for exactly this pattern: `test/registered/unit/function_call/test_function_call_parser.py`
  `test_streaming_name_not_emitted_before_end_message` (InklingDetector, :416): "Atomicity: the tool name is
  withheld until the closing marker, so a call that never completes never leaks an orphan name delta."
- Scope cost: none beyond the detector (the commit barrier is local; the serving layer's
  `_process_tool_call_stream` already handles a call appearing complete in one delta — see the
  continuing-vs-opening classification in `serving_responses.py` :2440-2461).
- Observable consequence (accepted): argument deltas for a call are coalesced to the block's closing
  `</tool_call>` instead of streaming byte-by-byte. This is the intended cost of "complete framing".

### R4. Single EOS rule — ADOPTED (this supersedes P1's I2)

**EOS (normative):** On stream end (`finish()`), any text the detector is holding that was NOT committed as
a completely framed call MUST be returned as `normal_text` (ordinary assistant content); no `ToolCallItem`
may be emitted for it. In particular:
- An unclosed `<tool_call>` at EOS (with or without an inner `</function>`) → the held segment is released
  as ordinary content; it is NEVER repaired into a structured call and NEVER dropped.
- A closed `<tool_call>` whose inner framing failed the FRAMING condition (malformed/empty name,
  unterminated parameter) → no call; the affected bytes are released as ordinary content.
- A closed, well-framed block → committed at `</tool_call>` (no repair needed at EOS; a missing
  `</function>` with all parameters terminated does not block commit, see R4.1).
- Corollary: `Qwen3CoderDetector` MUST override `finish()`; the inherited no-op
  (`base_format_detector.py:353-359`) is insufficient and is what defect (iv) is about.

This is the owner-relayed expert's rule ("EOS 遇到未闭合 `<tool_call>` 时，把这一段退回普通 assistant
content"), extended consistently to inner-framing failures. It CONTRADICTS P1 I2: P1's "if `{` was emitted,
`finish()` MUST close it" is NOT adopted. Two reasons: (1) under delay-commit no `{` is ever emitted
unclosed, so I2 has no remaining case; (2) the locally-established contract already treats malformed
argument JSON as a *content fault* that the gateway surfaces fail-open (P1 §5, citing
`impl-gateway-failopen-toolcalls.md` / `design-toolcall-error-contract.md` R1/R3), so "repair the JSON" is
not contract-required to avoid an illegal wire state. The wire invariants that ARE fail-closed are negative
index / item type / ordering (P1 §5) — those are fixed by FRAMING + EOS, not by JSON repair.

#### R4.1 Residual judgment call flagged for the owner (contract silent; not a blocker)

The contract documents are absent locally (R6), and no found statement covers the **closed `<tool_call>`
with a missing inner `</function>`** (parameters terminated). Adjudicated rule: **commit** it with a
complete JSON object, because the outer framing is complete, all argument bytes are present and
unambiguous, and delay-commit means nothing partial was ever on the wire. Rejected alternative: treat it
as content (safer under a maximal reading of "complete framing", but it discards a call whose argument
bytes are fully present and unambiguous, pushing work to the client's repair loop).
Consequences if the owner prefers the alternative: the two rows below marked **[C]** flip from "structured
call" to "content"; no other rule changes and no additional file changes are needed.

### R5. Invariants (P1 I1-I7 kept/amended) + new invariants

| # | Status | Testable statement |
|---|---|---|
| I1 | KEEP | Exactly one well-formed JSON object per committed call; a duplicate `</function>` adds no second `}`. |
| I2 | **AMENDED/SUPERSEDED** | Replaced by R4: never emit a partial call; uncommitted held text is released as content at EOS. No `finish()` JSON repair. |
| I3 | KEEP, strengthened | No `ToolCallItem` with `tool_index < 0`; indexes are assigned at commit, stable per call, strictly increasing across calls. |
| I4 | KEEP | A committed call's NAME is non-empty and contains no `<`, `>`, or whitespace. |
| I5 | KEEP | No call may be emitted with an empty name (`<function=>`, `<function= >`). |
| I6 | KEEP (hard non-goal) | A well-formed but undeclared name is emitted verbatim; no membership validation. |
| I7 | AMENDED | A committed call's `parameters` is always a complete JSON object (empty params → `{}`); whitespace-only is impossible by construction. |
| I8 | NEW | FRAMING: no emission before `</tool_call>` (or `</function>` in the no-`<tool_call>` fallback); commit only per R3. |
| I9 | NEW | EOS: `finish()` releases all uncommitted held text as `normal_text`; no call for it. |

### R6. Contract reconciliation status (the crux), stated honestly

- The six named documents (`design-toolcall-error-contract.md`, `impl-gateway-failopen-toolcalls.md`,
  `impl-toolcall-contract-v2.md`, `diag-malformed-toolcall-args-adjudication.md`,
  `diag-local-qwen-correctness.md`, `scout-qwen3coder-undeclared-tool-semantics.md`) are **NOT present on
  this host**: verified by full-filesystem `find / -xdev …` and by direct-path checks under
  `/home/ubuntu`, `/tmp/opencode`, `/opt/sglang`; they are referenced only inside
  `/tmp/opencode/p1-spec-extract.md`, the opencode session store, and `/tmp/opencode/orchestrator-expert-reasoning.txt`.
  They could not be quoted; their content is known only via P1's citations and the owner/expert messages.
- The quotable local authorities actually used:
  1. Owner (binding division of labour), session part `prt_0b18ef28c001sIjia4MX6OpqjB`:
     "分工先定死：网关作为 trust boundary 永远做 wire invariant 校验；SGLang 那边的责任是'不要生成非法
     wire state'（不是'帮忙校验工具名'）。"
  2. Owner (non-goals), session part `prt_0b1940053001y7UHyeXGEZ1XBc`: no name validation (pass-through
     is required so the client's `NoSuchToolError` → invalid tool → self-correct path runs); no silent
     drop; no template/sampling/model/quant/serving-flag changes.
  3. Owner-relayed expert correction, session part `prt_0b1946b4d0016OuagGDQcXCBND`: complete framing
     required before a structured call; delay commit in the detector; EOS unclosed `<tool_call>` → ordinary
     assistant content; 1 production file + 1 test file; do not touch `function_call_parser.py` or
     `BaseFormatDetector`.
  4. Ledger entries `2026-09-18` recording the owner's binding framing, the spec delivery, the conflict,
     and the owner's guardrail: fix only if still necessary; unit tests only; no restart/test-facility for
     evidence.
- Does the contract require COMPLETE FRAMING before a structured call is emitted? **YES, per (3)** — the
  only directly quotable statement is the owner-relayed expert correction; the named contract document
  itself could not be read locally. This is a citation limitation, not a contradiction.
- For an UNCLOSED `<tool_call>` at EOS: **ordinary assistant content**, per (3). P1's I2 is INCONSISTENT
  with (3) and is therefore superseded; no reconciliation that keeps both is possible for that case (I2
  would emit a structured call; (3) says content).
- For a CLOSED block with missing inner `</function>`: contract silent → R4.1 residual judgment call.
- The one thing I could not settle from evidence alone: the R4.1 sub-case, plus the absence of the named
  contracts (their actual clause text and the gateway predicate `toolCallArgumentsUsable` /
  `invalidToolCallsEvent` could not be read on this host — no `adapters/openai-chat.ts` or gateway source
  exists under any reachable path). Both are flagged; neither blocks the corrective round.

## Evidence

### E1. Production path — YES, production routes to `Qwen3CoderDetector`

- Live process is NOT present at adjudication time (no `sglang.launch_server` in `ps` or `/proc` scan;
  another task may be stopping/starting it). Recorded argv used instead, per dispatch:
  - Frozen launcher `launcher/launch.sh:166`: `--tool-call-parser qwen3_coder` (read directly).
  - Recorded `/proc/1654119/cmdline` (agent artifact `HOST-GPU-SERVICE-STATE-20260918.md:38` and
    `P0-PROD-LIVENESS-CHECK-20260918.md:174`): `--model-path /data/models/qwen35-9b-w4a16 … --reasoning-parser
    qwen3 --tool-call-parser qwen3_coder …`, `PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python`.
- Mapping: frozen `function_call_parser.py:92` `"qwen3_coder": Qwen3CoderDetector` (and `:95`
  `"step3p5": Qwen3CoderDetector`). `FunctionCallParser.__init__` (:107-117) instantiates the mapped class;
  `serving_chat.py:257` reads `tool_call_parser` from the served config; `:407` passes it to the parser.
- Runtime proof: production log `server.console.log:2580`
  `[2026-09-17 21:39:43] Tool 'qquestion' is not defined in the tools list.` — the only emitter of that
  string on the host is `qwen3_coder_detector.py:91` (QQUESTION-HALLUCINATION-HUNT E2).
- Auto-detection is a non-factor here: `template_detection.py:491` `DetectionRule(name="qwen3_coder",
  value="qwen3_coder", predicate=_is_qwen3_coder)` exists, but the explicit CLI flag selects the parser
  directly.
- Frozen tree loads, not the workspace: `identity.json.runtime.editable_binding_caveat` + launcher
  `export PYTHONPATH="$SRC/python"` + recorded `/proc` environ. => Editing only the repo copy is a no-op
  for the running server; the fix must later land into the frozen tree (R7).

### E2. Hashes (both trees, both files + parser)

| file | repo path sha256 | frozen path sha256 | identical? |
|---|---|---|---|
| `qwen3_coder_detector.py` | `3c1a06a1192ed8a53e66217a7782c3c5eea72e47bd6329a458731b567630c517` (working tree; see E6) | `92eeaeaf02ac1c1e966a8b9bbd4393141353ca9177265044fe12e250c0e38089` | NO currently — in-flight edit |
| `qwen3_coder_detector.py` at repo `HEAD` / `origin/3090-24g-opt` | `92eeaeaf…8089` (`git show HEAD:` verified) | `92eeaeaf…8089` | YES |
| `base_format_detector.py` | `0e56a1402b1d27dd92c5299f4bdeed3bc4499660df3c910c473a9691ba23265a` | `0e56a140…265a` | YES |
| `function_call_parser.py` | `7433863decb5eefa92e0e227f723221e219a44d7f17c10c6654b9740f15558f3` | `7433863…58f3` | YES |
| `test_function_call_parser.py` | `bb8363f554fb9eebc2dd92b50cde2745ea0892fb069cce2d7cdf88d2c03fbceb` | `bb8363f5…bceb` | YES |

- Frozen manifest confirms the delivered hashes: `manifest/TREE-SHA256.txt:4516` (detector), `:4480` (base),
  `:4488` (parser), `:14240` (test). This is the P1 target baseline.
- Local `main`/`origin/main` file blob = `adf38ad60548b75559e3e6b8b7b5bd20c8da29984d9b4643623cb874b263af22`;
  diff vs frozen = 11 lines, only in `_get_arguments_config` schema-properties extraction
  (`get_schema_properties` vs `params["properties"]`), NOT index/framing. Version-skew hypothesis refuted
  for the disputed logic.

### E3. Per-defect verification against frozen bytes (probes, CPU-only, PYTHONPATH=frozen)

Probe scripts: `/tmp/opencode/qwen3coder-adjudicate-20260918/probe.py` … `probe6.py`; run with
`CUDA_VISIBLE_DEVICES=999`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=<frozen>/src/python`,
`<frozen>/env/bin/python`. No GPU, no server, no writes outside scratch.

- **(i) CONFIRMED (streaming).** Frozen `qwen3_coder_detector.py:288` is the ONLY reset of
  `json_started` (`self.json_started = False`, inside the `<function=` branch); the `</function>` branch
  `:392-404` sets it True and appends `}` unconditionally on every occurrence:
  ```
  392:            if current_slice.startswith(self.function_end_token):
  393:                if not self.json_started:
  394:                    calls.append(
  395:                        ToolCallItem(tool_index=self.current_tool_id, parameters="{")
  396:                    )
  397:                    self.json_started = True
  398:
  399:                calls.append(
  400:                    ToolCallItem(tool_index=self.current_tool_id, parameters="}")
  401:                )
  402:                self.parsed_pos += len(self.function_end_token)
  ```
  Probe row 2: accumulated `'{"command": "cat /usr/local/bin/switch-codex"}}'` → `JSON FAIL: Extra data`.
  Non-streaming (`detect_and_parse`, regex `(.*?)</function>|<function=(.*)$`) produced valid
  `{"command": "cat /usr/local/bin/switch-codex"}` → not a defect there.

- **(ii) CONFIRMED (streaming).** Closing `}` exists only inside the `</function>` branch above. Probe row 3:
  `'{"command": "ls -la"'` → `JSON FAIL`; `finish()` inherited (see iv) returns empty. Non-streaming
  produced valid JSON (the `|<function=(.*)$` alternative closes the frame) → not a defect there.
  P1's `base_format_detector.py:353-359` quote verified byte-for-byte in both trees.

- **(iii) CONFIRMED, re-attributed.** `base_format_detector.py:45` `self.current_tool_id: int = -1`;
  increment only at detector `:285`; emits at `:293, :353, :376, :395, :400`. Probes: orphan
  `<parameter=command>ls -la</parameter>` inside a closed frame → two `tool_index=-1` items; stray
  `</function>` with no function → `tool_index=-1` `{`/`}`. Introspection (probe6): `initial current_tool_id
  = -1`, `parse_base_json` referenced in detector source = `False`, both public parse methods overridden,
  `finish` override present = `False`. => the base's `tool_indices.get(name, -1)` path is unreachable; the
  detector's own index is the cause. Live corroboration: `Tool 'None' is not defined in the tools list.`
  (server log 21:57:55; `_get_arguments_config(None, …)` warning from `:91`) in the same second as the
  client's `stream error … "upstream response contained invalid tool calls (invalid index)"` (opencode log
  :135332-135333). Attribution of that specific live pair is second-granularity coincidence (INFERRED, not
  request-id-proven); the code+probe proof stands independently.

- **(iv) CONFIRMED.** Frozen `base_format_detector.py:353-359` returns `StreamingParseResult()`; grep of
  all detectors shows `finish` overrides only in `kimik3_detector.py:221`, `muse_glimmer_detector.py:115`,
  `spark25_detector.py:240` — none in `qwen3_coder_detector.py`. Production calls it:
  `serving_chat.py:2566` and `serving_responses.py:2320` (`parse_stream_end()`), gated in chat by
  `flush=finish_reason_type is not None and finish_reason_type != "abort"` (`serving_chat.py:790`).

- **(v) CONFIRMED (both paths).** Streaming `qwen3_coder_detector.py:280-283`:
  ```
  281:                end_angle = current_slice.find(">")
  282:                if end_angle != -1:
  283:                    func_name = current_slice[len(self.tool_call_prefix) : end_angle]
  ```
  If the model omits the tag's `>`, the first `>` may belong to a later tag; probe row 5 reproduced the P1
  observed name byte-for-byte: `'grep -n "enable_thinking" /data/models/jinja\n</parameter'`. Non-streaming
  `:202-203` (`name_end = func_body.index(">"); func_name = func_body[:name_end]`) same class: probe NS
  produced name `'grep -n "x" /p\n</parameter'` around a stray tag. Empty name: `<function=>` yields a call
  with `name=''` in both paths (probes).

### E4. Adjudicated acceptance table (frozen tree, streaming via small chunks + `finish()`; non-stream where noted)

`—` = measured "before" on frozen bytes; "After" = normative under R3/R4 (streaming). Rows marked **[C]**
change the expected value relative to P1 §4; **[K]** keeps P1's expectation (observable result).

| # | Model output shape | Before (measured, frozen) | After (adjudicated) |
|---|---|---|---|
| 1 | clean `<tool_call><function=bash><parameter=command>ls -la</parameter></function></tool_call>` | call idx 0 name `bash`, args `{"command": "ls -la"}`, JSON OK | **[K]** unchanged; committed at `</tool_call>` |
| 2 | duplicate `</function>` (closed frame) | args `{…"}}`, JSON FAIL Extra data, idx 0 | **[K]** exactly one `}`; args `{"command": "cat …"}`, JSON OK, idx 0 |
| 3 | missing `</function>`; stream ends (frame unclosed) | args `{"command": "ls -la"` FAIL | **[C] no call; `finish()` returns the held segment as `normal_text`** (content), never a repaired call |
| 4 | orphan `<parameter>` no `<function>` (closed frame) | `tool_index=-1` items | **[K]** no call with `index < 0`; fragment has no identity → released as content / not a call |
| 5 | malformed `<function=` (missing `>`), frame closed | name swallowed text incl. `</parameter`, idx 0 | **[C] no call with a malformed name; no call emitted for the tag (content release)** — P1's "name = leading token `grep`" is rejected (that would invent a name) |
| 6 | parameter never closed; stream ends | args `""` (only name item) | **[C] no call; `finish()` releases held segment as content** |
| 7 | `<function=bash>` only; stream ends | args `""` (only name item) | **[C] no call; `finish()` releases held segment as content** |
| 8 | stray `<parameter=extra>` after `</function>` (closed frame) | args `{"command": "ls"}, "extra": "x"` FAIL | **[K]** first call commits `{"command":"ls"}` (JSON OK); stray fragment yields no call / no negative index |
| 9 | empty name `<function=></function>` (closed frame) | call name `''`, args `{}` | **[K]** no call with an empty name |
| 10 | undeclared names `cat` / `qquestion` | emitted verbatim, idx 0, JSON OK | **[K]** unchanged (I6 non-goal) |
| 11 | **crux:** complete function inside an UNCLOSED `<tool_call>` (no `</tool_call>`) | call idx 0 name `bash`, args `{"command": "ls -la"}`, JSON OK | **[C] no call; content fallback** — the expert's EOS rule; relies on the client's repair loop |
| 12 | two complete calls | idx 0 and 1, both JSON OK | **[K]** unchanged; both committed |
| 13 | **R4.1 sub-case:** frame closed, `</function>` missing, params terminated | args `{"command": "ls -la"` FAIL | **[C]** commit complete `{"command": "ls -la"}` (JSON OK), idx 0 — commit is at `</tool_call>`, nothing partial was emitted |

Non-streaming (`detect_and_parse`) notes: rows 3/6/7 already return complete valid calls today (regex
tolerance); the minimal non-stream changes are for rows 5/9 (no malformed/empty-name call). Path asymmetry
for unclosed blocks (streaming → content, non-stream → call) is wire-legal on both sides and is a
non-normative implementation note, not a violation.

### E5. Contract/EOS citations actually found (absolute paths, and what was NOT found)

Found:
- `/tmp/opencode/p1-spec-extract.md` (full P1 spec; 411 lines; cites the six documents; its §5 states the
  gateway treats malformed argument JSON as a fail-open CONTENT fault, and that wire invariants
  index/type/ordering are the fail-closed part).
- `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/ledger.md`
  (lines ~8824-9269: qquestion DONE; owner binding division of labour; spec delivery; the P1-vs-expert
  conflict table; owner guardrails).
- `/tmp/opencode/expert-opinion-verbatim.txt` and `/tmp/opencode/orchestrator-expert-reasoning.txt`
  (owner-relayed expert text; not a signed contract).
- `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/QQUESTION-HALLUCINATION-HUNT-20260918.md`
  (live `qquestion`/`Tool 'None'` evidence; emitter uniqueness; pass-through semantics).
- Owner/expert messages in the opencode session store (read-only SQLite URI): parts
  `prt_0b18ef28c001sIjia4MX6OpqjB` (division of labour), `prt_0b1940053001y7UHyeXGEZ1XBc` (non-goals),
  `prt_0b1946b4d0016OuagGDQcXCBND` (expert correction: complete framing / delay commit / EOS content).
- In-repo pattern precedent: `test/registered/unit/function_call/test_function_call_parser.py:416`
  (`test_streaming_name_not_emitted_before_end_message`).

NOT found anywhere reachable (not invented): `design-toolcall-error-contract.md`,
`impl-gateway-failopen-toolcalls.md`, `impl-toolcall-contract-v2.md`,
`diag-malformed-toolcall-args-adjudication.md`, `diag-local-qwen-correctness.md`,
`scout-qwen3coder-undeclared-tool-semantics.md`; also absent: any gateway source (`adapters/openai-chat.ts`,
`bridge.ts`, `toolCallArgumentsUsable`, `invalidToolCallsEvent` implementation). The P1 spec cites them under
`/home/charles/Workspaces/homenet/.memory/sglang-agents-tier-models-20260918/agents/`, which does not exist
on this host (`/home` contains only `ubuntu`). P2's upstream checks are public GitHub URLs, not local files.

### E6. In-flight repo edit by the failed Q3a task (important for the corrective round)

- `git status` (read-only): ` M python/sglang/srt/function_call/qwen3_coder_detector.py` only (plus unrelated
  M/?? entries outside this scope). Working-tree sha `3c1a06a1…`, mtime `2026-09-17 23:00:38`; `HEAD` blob
  is still the pristine `92eeaeaf…`. Nothing has been committed.
- The in-flight diff (git diff) is: (a) duplicate-`}` branch made conditional; (b) a new `else` on the
  `</function>` branch that does `return StreamingParseResult(calls=[], normal_text=current_slice[len(fn_end):])`;
  (c) two unused state attrs `tool_call_completed` / `filename_from_input`. Probe re-run of the repo tree
  confirms it still emits duplicate `}` for row 2 (the `else` returns the wrong suffix and abandons parsing),
  still emits `-1` for orphan params (row 4), still swallows names (row 5), and introduces new
  normal_text leakage (`</t`, `</tool_c` fragments).
- The corrective round MUST NOT inherit this diff; treat the pristine `HEAD` blob (`92eeaeaf…`) as the
  starting baseline and reconcile explicitly (the in-flight work is an input, never authority — per ledger
  2026-09-18 and the dispatch).

### E7. Landing note (not a write authorization)

Production loads the frozen tree, not the repo. Any repo fix is inert for the live server until landed into
`/opt/sglang/local-prod-v1.2.1-candidate/src/python/...` and the four pin surfaces are re-pinned
(`TREE-SHA256.txt`, `identity.json`, `identity-pins.json`, `launcher/launch.sh:29 EXPECTED_SRC_STREAM_SHA256`
= `c7427132…dafbc` today; target file mode 444, `src/` mode 555). The order is fixed by the ledger: adjudicate
(this artifact) -> bounded corrective round in the repo -> landing -> v1.2.2 build -> scheduled switch.
This adjudication does not authorize any landing/restart.

## Defects / blockers

1. **No blocker to the normative adjudication.** The corrective round can proceed on R0-R5.
2. Citation limitation: the six named contract documents and the gateway source are absent on this host
   (E5). The EOS/framing rule therefore rests on the owner-relayed expert correction + the owner's binding
   framing, both quotable locally, not on the contract clause text itself.
3. Residual judgment call (R4.1): the closed-block/missing-`</function>` sub-case is contract-silent;
   adjudicated to commit. If the owner chooses the content alternative, no additional files change.
4. The repo working tree contains a partial, wrong-direction edit (E6) from the failed Q3a task; the
   corrective round must start from the pristine `HEAD` blob and must re-verify the target hash before
   editing.
5. Regression risk to verify (not a blocker): `test_serving_responses_stream.py::MultiToolCallStreamingOrderTestCase`
   under delay-commit. It must pass unchanged; if it does not, that is a blocker for the owner.
6. P1's I2 is superseded (R4). Any corrective artifact that still implements "finish() closes the JSON"
   for unclosed frames is non-conformant with this adjudication.

## Remaining claims / exclusions

ESTABLISHED (local evidence, cited above):
- Production routes to `Qwen3CoderDetector`: YES (flag + mapping + live log emitter + recorded PYTHONPATH).
- Hashes of the four files in both trees; pristine detector baseline `92eeaeaf…8089` == repo `HEAD`;
  base/parser byte-identical across trees; local `main` divergence limited to schema-properties extraction.
- Defects (i)-(v): as per R1/R2 (streaming vs non-streaming distinctions included).
- `-1` attribution: detector's own use of inherited `current_tool_id`; shared `parse_base_json` path
  unreachable for `qwen3_coder`; unknown names do not produce `-1`.
- Delay-commit/framing and EOS-content rules: derived from the owner-relayed expert correction + owner
  binding framing + in-repo atomicity precedent.
- `finish()` is reachable in production on normal finish (`serving_chat.py:2566`,
  `serving_responses.py:2320`) and is NOT called on abort.

REQUIRED, NOT OBSERVED (normative targets): every "After" cell in E4; R3/R4/R5 as implemented behaviour.

EXCLUDED / NOT CLAIMED:
- That the named contract documents were read (they were not present); their content is not quoted.
- That the corrective implementation is written or verified here (this task is analysis/adjudication only).
- That the fix alone removes malformed model output (the model fault remains).
- That the gateway fail-open path is active (P1 notes `impl-toolcall-contract-v2.md` was WORKING; owner
  later marked the gateway contract VERIFIED DONE with the live end-to-end malformed-tool trace still
  pending).
- Any landing into `/opt`, any restart, any pin re-computation, any GPU work.
- The exact original byte streams for the live 502s (not recorded); probes reproduce shapes deterministically.

## Terminal state: DONE
