# AUDIT-QWEN3CODER-ADJUDICATION-20260918

Status: DONE
Terminal state: DONE
Role: reviewer — independent, read-only audit of `QWEN3CODER-SCOPE-ADJUDICATE-20260918.md`
Audited artifact: `.memory/phase2-hicache-design/agents/QWEN3CODER-SCOPE-ADJUDICATE-20260918.md`
Audited bytes: sha256 `baa073167166f1a507e640bafe2c3a446e58c1653850fb37f36d777850c97291`,
33387 bytes, mtime `2026-09-17 23:36:55 UTC` (423 lines).
Baseline used for code claims: pristine `qwen3_coder_detector.py` sha256
`92eeaeaf02ac1c1e966a8b9bbd4393141353ca9177265044fe12e250c0e38089`, read from
`git show HEAD:...` **and** from the frozen tree; both identical (working tree also reverted to this sha at
audit time — see F1/E6 note).

## Task

Independent audit of the architect's normative adjudication (already being implemented by
`Q3A2-QWEN3CODER-IMPLEMENT-20260918`) against F1–F6: two-invocation integrity, `/proc` citation
feasibility, the five defect claims vs pristine bytes with `-1` attribution, the rules themselves
(delay-commit, EOS, acceptance table), write-scope minimality, and work justification. Read-only.

## Scope

- IN: adjudication artifact bytes; pristine `git HEAD` / frozen-tree detector, base and parser; repo test
  tree; `/opt/sglang/local-prod-v1.2.1-candidate` read-only; server/supervisor logs;
  `P0-PROD-LIVENESS-CHECK-20260918.md`, `HOST-GPU-SERVICE-STATE-20260918.md`, `QQUESTION-HALLUCINATION-HUNT-20260918.md`;
  ledger/session timestamps; my own CPU-only probes under `/tmp/opencode/audit-qwen3coder/`.
- OUT: any source edit, `/opt` write, GPU, service op, git mutation, ledger/other-agent write. I wrote only
  this artifact.

## Result

**VERDICT: SAFE TO IMPLEMENT AS-IS on scope and defect attribution, but it needs two corrections before it
is an unqualified implementation authority: (C1) explicitly reconcile the EOS/content-fallback with both
P1 §3.2 "do not degrade a decoded call to plain text" and P1 §4's "rows 6/7 must still be usable-empty";
(C2) state row 3b's status unambiguously as a reversible owner-flagged default (not a settled rule and not a
blocker). No production-safety blocker found; the core normative rules are internally consistent and match
the owner-relayed expert direction.**

- **F1 — deliverable-integrity defect: YES.** The current bytes specify *extend the existing*
  `test_function_call_parser.py` (line 40–42) and contain *both* "I2 has no remaining case" (line 137) and
  "R4.1 Residual judgment call flagged for the owner" (line 143). The two surviving statements are
  reconcilable (different sub-cases), but invocation 1's bytes were **silently overwritten and are not
  recoverable** (no `.bak`, `.memory/agents/` is untracked, no git history). The artifact cannot be treated
  as an unqualified authority *because of provenance*, though the surviving (invocation-2) scope is the
  correct/repo-conventional one.
- **F2 — `/proc` citations: POSSIBLE, stale-by-design and correctly attributed as *recorded*, with one
  imprecise citation pairing.** The artifact explicitly states the live process was absent at adjudication
  time and that it used *recorded* argv (lines 207–212). It does **not** claim a live read. The underlying
  routing claim stands on independent evidence (launcher flag, parser mapping, live log emitter,
  recorded PYTHONPATH).
- **F3 — five defect claims: ALL CONFIRMED against pristine `92eeaeaf…`** (with the stated
  streaming/non-stream distinctions). The **`-1` re-attribution is CORRECT**: the detector never calls
  `parse_base_json`, overrides both public parse methods, and its `-1` comes from the inherited
  `current_tool_id = -1`. The shared base's `tool_indices.get(name, -1)` is unreachable from `qwen3_coder`.
- **F4(a) delay-commit/I8 — JUSTIFIED and authorized, not unauthorized scope creep**, but it rests on an
  owner-relayed expert instruction rather than a quotable contract clause (the six named docs are absent —
  I independently confirmed this). Practical streaming cost: argument deltas are coalesced to `</tool_call>`,
  delaying first structured-call visibility; the canary `MultiToolCallStreamingOrderTestCase` is the correct
  gate.
- **F4(b) EOS=content — CORRECT per the later, more specific owner-relayed expert rule, but the artifact
  does not reconcile it with the earlier general guardrail**; see C1. It does *not* violate the
  unknown-name pass-through guardrail (row 10 unchanged), but the phrase "do not degrade a decoded call to
  plain text" read literally covers row 11 (a fully decoded call inside an unclosed envelope).

## Evidence

### F1 — two invocations, current bytes, and scope/row-3b classification

Current write scope (adjudication lines 40–42, verbatim):
> `2. test/registered/unit/function_call/test_function_call_parser.py — extend the existing`
> `TestQwen3CoderDetector (class at :2289). This is the repo's established function-call test file; do`
> `NOT invent a new hierarchy.`

Row 3b in current bytes (verbatim):
- line 129–130: "A closed, well-framed block → committed at `</tool_call>` (no repair needed at EOS; a
  missing `</function>` with all parameters terminated does not block commit, see R4.1)."
- line 143: "#### R4.1 Residual judgment call flagged for the owner (contract silent; not a blocker)"
- line 146: "Adjudicated rule: **commit** it with a complete JSON object, because the outer framing is
  complete…"
- line 197–200: "For a CLOSED block with missing inner `</function>`: contract silent → R4.1 residual
  judgment call." / "The one thing I could not settle from evidence alone: the R4.1 sub-case…"

The other surviving statement (line 136–137, verbatim):
> "(1) under delay-commit no `{` is ever emitted unclosed, so I2 has no remaining case;"

Reconcilable? **Yes, on different sub-cases.** "I2 has no remaining case" concerns the *unclosed-envelope*
JSON-close question (E4 row 3); R4.1 concerns the *closed-envelope, missing inner `</function>`* case (E4
row 13). They are not contradictory statements about the same row. The genuine contradiction the ledger
records was **between the two invocations**, not within current bytes.

Independent corroboration of the overwrite (ledger, lines 9455–9462, verbatim):
> "未及时处理交付物不稳定：`QWEN3CODER-SCOPE-ADJUDICATE-20260918` **被两次 invocation 写入同一 artifact**，
> 且两次终态摘要**互相矛盾**：
> - 第一次：写域 = detector + **新增** `test_qwen3_coder_detector.py`；并保留 **row 3b 为 MATERIAL DECISION**
> - 第二次：写域 = detector + **扩展既有** `test_function_call_parser.py`；并称 **"I2 has no remaining case"**"

Recovery check: `find /tmp/opencode /home/ubuntu -name "*QWEN3CODER*"` returns only the current artifact;
no `.bak`/`~` copies exist; `.memory/**` is untracked (`??` in `git status`), so invocation 1's bytes are
unrecoverable. The surviving bytes correspond to the **second** invocation's described scope
(extend-existing + "I2 has no remaining case").

Timeline: artifact mtime `2026-09-17 23:36:55Z`; the session parts that quote the adjudication are at
`23:56` (still post-dating the write; the DB cannot supply invocation-1's terminal bytes).

Assessment: **deliverable-integrity defect = YES** (a normative deliverable was overwritten in place with no
version history and no recovery). Reliance: the *surviving* scope is correct and matches repo convention
(`TestQwen3CoderDetector` already exists at `test_function_call_parser.py:2289`; there is no
`test_qwen3_coder_detector.py` on disk — verified by directory listing). So it may be relied on for scope
and defect analysis, but not as an unqualified authority until C1/C2 are stated.

### F2 — `/proc` citation feasibility

Artifact lines 207–212 (verbatim):
> "- Live process is NOT present at adjudication time (no `sglang.launch_server` in `ps` or `/proc` scan;
>   another task may be stopping/starting it). Recorded argv used instead, per dispatch:"
> "- Recorded `/proc/1654119/cmdline` (agent artifact `HOST-GPU-SERVICE-STATE-20260918.md:38` and
>   `P0-PROD-LIVENESS-CHECK-20260918.md:174`): `--model-path … --reasoning-parser qwen3 --tool-call-parser
>   qwen3_coder …`, `PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python`."

Timestamp evidence:
- `HOST-GPU-SERVICE-STATE-20260918.md` mtime `2026-09-17 21:39:37Z`; its line 38 is a direct
  `/proc/1654119/cmdline` read, and its `nvidia-smi --query-compute-apps` shows `1654119` alive at ~21:39.
- `P0-PROD-LIVENESS-CHECK-20260918.md` (mtime `23:09:58Z`) establishes pid `1654119` **GONE** at `23:09:23Z`,
  with `kill_process_tree` at `23:06:32` and supervisor exit at `23:05:31`.
- `supervisor.log` line `[21:18:24] /proc/1654119/environ PYTHONPATH=…` was logged **while the process was
  alive**.
- The adjudication ran at ~23:15–23:36 (scratch probe mtimes 23:15–23:33), i.e. **after** the process exit.

Therefore the referenced `/proc` reads were **temporally possible** (all captures are ≤21:39, ~1h25m before
exit) and the artifact **labels them as recorded**, explicitly stating no live process was present. Verdict:
**POSSIBLE (stale-by-design, correctly re-attributed as recorded)** — *not* "claimed a live read".

Minor imprecision: the artifact pairs `P0…:174` with `/proc/1654119/cmdline`. P0 line 174 is the
*supervisor.log environ* line, not a `/proc/cmdline` read. That is a citation-pairing slip, not a
misattribution of the routing claim.

Routing claim still stands on other evidence (independently re-verified by me):
- frozen `launcher/launch.sh:166` → `--tool-call-parser qwen3_coder` (read directly);
- `function_call_parser.py:92` → `"qwen3_coder": Qwen3CoderDetector`;
- `server.console.log:2580` → `[2026-09-17 21:39:43] Tool 'qquestion' is not defined in the tools list.`
  and the only source emitter is `qwen3_coder_detector.py:91` (repo-wide grep, frozen and repo, `.py` only);
- recorded `PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python`.

### F3 — five defects against pristine bytes (`92eeaeaf…`, via `git show HEAD` + frozen)

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| (i) | duplicate `</function>` emits extra `}` (streaming) | **CONFIRMED** | `qwen3_coder_detector.py:288` is the only `json_started=False`; `:392–402` appends `}` unconditionally on every `</function>`. My probe: `row2 duplicate FE` → params `'{"command": "cat /usr/local/bin/switch-codex"}}'` → `JSON FAIL: Extra data`. Non-stream tolerates it (regex `|<function=(.*)$`): my probe `NS row2 dupFE` → valid `{"command": "cat x"}`. |
| (ii) | missing `</function>` leaves arg JSON unclosed (streaming) | **CONFIRMED** | `}` only emitted in the `</function>` branch. My probe: `row3 missing FE` → `'{"command": "ls -la"'` → `JSON FAIL: Expecting ',' delimiter`; inherited `finish()` returns `StreamingParseResult()` (`base_format_detector.py:353–359`). Non-stream auto-closes: my probe `NS row3` → valid. |
| (iii) | `tool_index = -1` from orphan fragments | **CONFIRMED, re-attribution CORRECT** | `base_format_detector.py:45` `current_tool_id: int = -1`; incremented only at detector `:285`; used at `:293, :353, :376, :395, :400`. My probes: orphan `<parameter>` → `idx=-1`; stray `</function>` → `idx=-1` params `'{}'`. |
| (iv) | inherited `finish()` is a no-op | **CONFIRMED** | `base_format_detector.py:353–359` returns empty; no `qwen3_coder` override. `finish` overrides exist only in `kimik3_detector.py:221`, `muse_glimmer_detector.py:115`, `spark25_detector.py:240` (my scan of the frozen `function_call/` dir). Reached in production via `serving_chat.py:2566` and `serving_responses.py:2320`, gated by `serving_chat.py:790`. |
| (v) | streaming name extraction swallows text | **CONFIRMED (both paths)** | Streaming `:280–283` `end_angle = current_slice.find(">")` then slice. My probe `row5` → name `'grep -n "enable_thinking" /data/models/jinja\n</parameter'`. Non-stream `:202–203` same class; my probe `NS row5` → name `'grep -n "x" /p\n</parameter'`. Empty name `<function=>` yields `name=''` in both paths (probes `row9`/`NS row9`). |

**`-1` attribution verification (the item that determines write scope):**
- `grep -n "parse_base_json" qwen3_coder_detector.py` → only `super().__init__()` (no call). ✔
- `detect_and_parse` defined at `:178`; `parse_streaming_increment` at `:246` → **both overridden**. ✔
- `tool_indices.get(name, -1)` (`base_format_detector.py:92`) is reachable only via `parse_base_json`
  (`:77–101`); the other callers are `minimax_m2.py:500` and `minimax_m3.py:139`. It is therefore
  **unreachable from `qwen3_coder`**. The artifact's attribution is correct, and the write scope
  (detector-only) is sufficient for (iii). ✔
- Unknown names do **not** yield `-1` (probe `row10` `cat` → `idx=0`).

Hash/provenance claims re-verified: repo `HEAD` detector == `origin/3090-24g-opt` blob == frozen
`92eeaeaf…`; `main`/`origin/main` == `adf38ad6…`; `base_format_detector.py` `0e56a140…` == frozen;
`function_call_parser.py` `7433863d…` == frozen; test `bb8363f5…` == frozen; manifest
`TREE-SHA256.txt:4516/4480/4488/14240` match. `launch.sh:29 EXPECTED_SRC_STREAM_SHA256
c7427132…dafbc` matches. The version-skew hypothesis is correctly refuted for index/framing.

Minor accuracy slip: the artifact says the `main` divergence is "11 diff lines". `git diff --numstat HEAD
main` = `3 5` → **8 changed lines** (10 diff lines including headers), all in the
`_get_arguments_config` schema-properties extraction. Not material to the conclusion.

### F4 — adjudication of the rules

**(a) Delay-commit / framing (I8).** R3 (lines 96–102) requires a complete `</tool_call>` frame, a
well-formed name, and terminated parameter values before any `ToolCallItem`. Grounding: the artifact admits
the six named contract documents are **ABSENT** (R6 lines 170–176) and rests the rule on the owner-relayed
expert message `prt_0b1946b4d0016OuagGDQcXCBND` (I read it: "当前 streaming 在看到 `<function=name>` 后就
已经 emit tool call，早于 `</tool_call>` … 契约要求完整 framing … 在这个 detector 内延迟 commit") plus the
owner binding division-of-labour `prt_0b18ef28c001sIjia4MX6OpqjB` and non-goals
`prt_0b1940053001y7UHyeXGEZ1XBc`.
- I independently confirmed the six docs and all gateway source (`adapters/openai-chat.ts`,
  `toolCallArgumentsUsable`, `invalidToolCallsEvent`) are absent from `/home/ubuntu`, `/tmp/opencode`,
  `/opt/sglang` (bounded `find`).
- **Judgment: the grounding is sufficient for a production change because the owner relayed the expert
  opinion as an instruction ("一并处理"), and the owner is the contract authority here.** It is *not*
  unauthorized scope creep, but it *is* beyond the five defects (a correct `-1` fix and the duplicate-`}`
  fix do not strictly require delaying all emissions). Practical risk: tool-call arguments are coalesced to
  the closing `</tool_call>`, so streaming clients see structured calls later (higher time-to-first
  tool-call delta; any client that renders arguments incrementally stalls). The artifact acknowledges this
  cost (line 117–118) and names the correct canary (line 60–64), which I ran on pristine bytes:
  `MultiToolCallStreamingOrderTestCase` → **3 passed**.
- The extension "or `</function>` in the no-`<tool_call>` fallback" (R5 I8) is underspecified relative to the
  rest of the rules (the shipped detector's regex fallback is non-stream only); this is a wording gap, not a
  demonstrated defect.

**(b) EOS rule.** R4 (lines 120–141) returns uncommitted held text as `normal_text`, never repairs it into
a call, and extends the expert rule consistently to inner-framing failures. Assessment:
- **Consistent with the owner's guardrails on name validation:** row 10 (undeclared names) is unchanged
  `[K]`, so pass-through is preserved. It does **not** move gateway validation into the parser (no name
  membership check is added). ✔
- **"No silent drop":** the segment is released as visible content, not dropped. ✔ for the JSON-gateway
  framing.
- **BUT it conflicts, on its face, with P1 §3.2's broader clause**: "Do NOT silently drop calls and do NOT
  degrade them to plain text." E4 row 11 degrades a *fully decoded* call (name + args + `</function>`)
  inside an unclosed `<tool_call>` to content. The artifact's R6 restatement of the owner guardrails
  (line 181–183) **omits the "不得退化为正文 / do not degrade to plain text" clause**, which is exactly the
  clause in tension.
- **Consistent with P1 §4 for rows 3/6/7/11?** No: P1 §4 explicitly states "Rows 6 and 7 are the two cases
  that must still be treated as usable-empty by the gateway" and set their "After" = usable-empty call.
  E4 rows 6/7 change them to "no call; content" `[C]`. The artifact marks the change but never reconciles
  it with P1's explicit gateway requirement (`toolCallArgumentsUsable` — contract doc absent).
- **Judgment:** the EOS rule is correct **per the later, more specific owner-relayed expert instruction**,
  which supersedes the general non-goal for framing-incomplete blocks. It is therefore **not a confirmed
  production defect**, but the omitted reconciliation is a genuine specification tension the implementer
  could misread, and it is the single most consequential unaddressed item (C1). This tension is the
  strongest candidate for a required owner confirmation; it is not, in my judgment, a production-safety
  blocker because the owner's relay authorized exactly this behavior.

**(c) Acceptance-table internal consistency (current E4 rows 1–13).** Note: the dispatch's row labels
`3b`, `6b`, `7b` do **not** exist in the current table — they belonged to invocation 1's table, which was
overwritten (F1). Mapping: `row 3b` ≈ current **row 13**; there is no `6b`/`7b` in the surviving bytes.
- Rows 1, 2, 4, 8, 9, 10, 12: internally consistent with R3/R4 and with my measured "Before" values. ✔
- Rows 3, 6, 7, 11: content-release `[C]`; **consistent with R4** (unclosed envelope → content) but
  **contradict P1 §4's usable-empty requirement for 6/7 and the literal "do not degrade a decoded call"
  clause for 11** (see F4(b)). Flagged.
- Row 5: `[C]` rejecting P1's "name = leading token `grep`" and releasing content; consistent with R3's
  well-formed-name condition (the malformed tag's name contains whitespace/`<`). Not impossible. ✔
- Row 13 (row 3b): `[C]` commit complete `{"command": "ls -la"}` at `</tool_call>`. **Consistent with the
  single EOS rule** (R4 bullet 3 and R3's "closing `</tool_call>`" parameter-terminator option). ✔
  However, R4.1's reversal note (line 151–152) says "the two rows below marked `[C]`" while there are six
  `[C]` rows — **ambiguous wording**; it evidently means rows 3 and 13. Cosmetic.
- Legend mismatch: `[C]` is defined as "changes the expected value relative to P1 §4", but rows 11 and 13
  are outside P1 §4's 10-row table. Cosmetic.
- Minor: E4's "After" for row 3/6/7/11 is a *requires-override-of-`finish()`* target, while the inherited
  `finish()` is a no-op — correctly captured by defect (iv) and R4's corollary. ✔

### F5 — scope minimality (detector-only)

All five defects are fixable in `qwen3_coder_detector.py` alone:
- (i) duplicate `}` — local (`:392–402`).
- (ii) unclosed JSON — local (`finish()` override + buffering already exists via `_buffer`/`parsed_pos`).
- (iii) `-1` — local (detector uses its own inherited `current_tool_id`; base `parse_base_json` unreachable).
- (iv) `finish()` no-op — override in the detector.
- (v) name swallowing — local (`:280–283`, `:202–203`).
No base-class change is required. Serving-layer support for detector-only changes was verified:
- `FunctionCallParser.parse_stream_end()` delegates to `detector.finish()` and returns its `normal_text`
  and `calls` (`function_call_parser.py:186–195`).
- `serving_chat.py:2566` appends `end_text` to `normal_text` and `end_calls` to `calls`, gated by
  `serving_chat.py:790`; `serving_responses.py:2320` does the same.
- The chat residual-args path `_check_for_unstreamed_tool_args` (`serving_chat.py:2651`) guards on
  `detector.prev_tool_call_arr` / `streamed_args_for_tool`, which `qwen3_coder` never populates (grep:
  no references), so it no-ops safely — no base change needed.
- Serving already handles a whole call arriving in one delta (the continuing-vs-opening classification in
  `serving_responses.py:2440–2461`).
**Scope restriction is valid.** No defect requires touching `base_format_detector.py` or
`function_call_parser.py`.

### F6 — work justification

Substantive, non-redundant contributions:
1. **`-1` re-attribution** with source + introspection + probes (correctly rejects the expert's initial
   "shared base or version skew" hypothesis and P2's hypothesis (b)). This directly determines the write
   scope.
2. **Version-skew refutation** by hashing HEAD/frozen/origin/`main` and isolating the only divergence to the
   schema-properties extraction.
3. **P1-I2 vs expert-EOS adjudication** into one rule set (R3/R4) with the consequence table.
4. **In-flight dirty-edit detection (E6)** — high-value: warns the corrective round not to inherit the
   failed Q3a diff. (At audit time the working file was back to pristine `92eeaeaf…`, mtime
   `23:38:20`, i.e. Q3A2 reconciled after the artifact was written; E6 was accurate at write time and is now
   historical.)
5. Correct canary identification.

Unnecessary / redundant / padding:
- E1 re-derives the production path already established in `QQUESTION-HALLUCINATION-HUNT` and
  `HOST-GPU-SERVICE-STATE` (duplicated effort); the dispatch did ask for deliverable A, so partly excusable.
- E2 hashes partially duplicate `FROZEN-TREE-INTEGRITY-AUDIT-20260918.md`.
- E5's six-document "NOT found" enumeration is verbose for the conclusion it supports.
- R5's I1–I9 table largely restates R3/R4/R1.
Estimated redundancy ~20–30%. **An hour is defensible but not tight**; the `-1` attribution, version-skew
refutation, E6 dirty-edit warning and the canary are the parts a shorter analysis would most likely have
missed.

## Defects / blockers

Ordered by severity. **None is a confirmed production-safety blocker; all are evidence-integrity,
specification-tension, or documentation items.**

1. **[HIGH — deliverable integrity] F1: the artifact was overwritten in place by two invocations with
   contradictory scope, and invocation 1's terminal bytes are unrecoverable.** The surviving bytes are
   internally consistent and specify the correct scope, but the deliverable has no version history and the
   ledger independently records the contradiction. Acceptance impact: the artifact can be implemented from,
   but must not be cited as a stable authority without noting the overwrite.
2. **[MEDIUM — specification tension] F4(b)/F4(c): the EOS content-fallback (rows 3/6/7/11) is authorized
   by the owner-relayed expert but was never reconciled with P1 §3.2 "do not degrade a decoded call to plain
   text" or P1 §4's explicit "rows 6/7 must still be usable-empty".** The artifact's R6 guardrail
   paraphrase omits the "不得退化为正文" clause. Acceptance impact: an implementer following R4 without the
   owner's relay could be judged to have silently degraded a call; conversely, an implementer honoring
   P1 §4 could emit a call R4 forbids. **Correction C1: add an explicit reconciliation paragraph.**
3. **[MEDIUM — grounding] F4(a): delay-commit (I8) rests on an owner-relayed message, not a contract
   clause; the contract docs are absent.** Authorized but under-documented. Acceptance impact: if the owner
   later disowns the relay, I8 is unsupported. **Correction C2: mark I8's authority explicitly as
   owner-relayed (it already is in R6, but not in R3/I8 itself).**
4. **[LOW — evidence attribution] F2: `/proc/1654119` is correctly labeled *recorded*, but the artifact
   pairs `P0…:174` (a supervisor.log environ line) with `/proc/cmdline`.** The reads were temporally
   possible; the routing claim stands on launcher + mapping + live log emitter. Acceptance impact: none on
   the routing conclusion; fix the citation pairing.
5. **[LOW — ambiguity] R4.1 says "the two rows below marked `[C]`" when six rows are `[C]`; the `[C]`
   legend is defined only against P1's 10-row table while rows 11/13 are new.** Acceptance impact: minor
   misreading risk.
6. **[LOW — accuracy] "11 diff lines" for the `HEAD` vs `main` divergence; actual is 8 changed lines
   (`git diff --numstat` = `3 5`).** Acceptance impact: none.
7. **[LOW — provenance] E6's in-flight working-tree sha `3c1a06a1…` is historical; at audit time the file
   was reverted to pristine `92eeaeaf…` (mtime `23:38:20`).** Correct at write time; note it is not current.
8. **[STYLE — padding] E1/E2/E5 partly re-derive already-established facts; R5 restates R3/R4/R1.** Not a
   correctness issue.

Distinguishing findings from questions — question for the owner (not a finding):
- Q1: Does the owner ratify R4.1's default (commit a closed envelope with missing inner `</function>`)?
  The artifact flags it but does not require a decision before implementation; the ledger records the
  orchestrator adopting the default as reversible. **Ratification recommended.**
- Q2: Does the owner confirm that rows 6/7 content-release supersedes P1 §4's usable-empty requirement?
  This is the substantive C1 question.

## Remaining claims / exclusions

- **Reviewed artifact bytes only** (sha `baa07316…`); I did not review the Q3A2 implementation in progress
  (it is out of my dispatch and still running). The current working detector is pristine `92eeaeaf…`; if it
  changes under the implementer, re-derive from the pristine blob.
- **Pristine code source:** `git show HEAD:python/sglang/srt/function_call/qwen3_coder_detector.py`
  (sha `92eeaeaf…`), cross-checked byte-identical against the frozen tree; my probes loaded the **frozen**
  tree (`PYTHONPATH=/opt/.../src/python`, `CUDA_VISIBLE_DEVICES=999`, no GPU, no server).
- **Not established:** that the six named contract documents' content supports either reading of the EOS
  rule (they are absent); that the gateway predicate `toolCallArgumentsUsable` exists as described; that
  production routes for any request other than the recorded session; that the canary passes *after* the fix
  (it passes on pristine: 3 passed).
- **Not claimed:** any source edit, `/opt` write, service op, git mutation, or ledger write by this audit.
  The only file written is this artifact; scratch probes live under `/tmp/opencode/audit-qwen3coder/`.
- **Lead detection:** the observed `Tool 'None' is not defined…` and `invalid index` client errors are
  second-granularity coincidences in the artifact (it labels this INFERRED); the code+probe proof does not
  depend on them.

## Terminal state: DONE
