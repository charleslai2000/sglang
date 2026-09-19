# SMOKE-AUDIT-VARIANT-EXT-20260917-01 — extended model/variant coverage audit

**Status: DONE** (terminal)

## Task

Extension of `SMOKE-AUDIT-MODELS-PROTOCOL-20260917-01`. Determine, for exactly these 5 previously
uncovered dispatches: (1) configured model/variant, (2) observed model/variant recorded by the local
runtime, (3) MATCH / MISMATCH / NOT-DETERMINABLE, (4) error/fallback/retry/substitution/provider-limit
signatures in the local logs. Second deliverable in the same artifact: independently re-confirm or
refute that the dispatch (`task`) tool exposes no `model` and no `variant` parameter.

Task IDs and claimed sessions (identity re-verified in E1):

| task_id | claimed session |
|---|---|
| SMOKE-EXT-ANALYST-20260917-01 | ses_f4ecfb819ffer5AQgnSAwh8doP |
| SMOKE-EXT-INVESTIGATOR-20260917-01 | ses_f4ed1f716ffegSr1aZGMQVA0mR |
| SMOKE-EXT-RESEARCHER-20260917-01 | ses_f4ed1f6eeffePw8nhu026zYHz5 |
| SMOKE-DEVOPS-EXEC-20260917-01 | ses_f4ed398e8ffeDkDSdCsTAkUoD1 |
| SMOKE-FRONTEND-20260917-01 | ses_f4ed398bdffeK170mLA2EveYfG |

No other session was audited. All 5 were dispatched from orchestrator session
`ses_f4ee2a9d7ffeCiIWveFN2FsJUr` (control/high).

## Scope

- **In scope:** the 5 sessions above, and only those. Read-only.
- **Read set used:** `/home/ubuntu/.config/opencode/**` (opencode.json, agents/*.md, `.bak-before-*`
  snapshots), `~/.local/share/opencode/opencode.db` (SQLite opened via
  `file:...?mode=ro`, URI read-only), `~/.local/share/opencode/log/opencode.log`, the runtime binary
  `/usr/local/bin/opencode` (byte reads only), and the task root
  `.memory/protocol-subagent-smoke-20260917/`.
- **Method:** direct reads and counted queries. DB sessions/messages/parts/events queried by session
  id; log scanned line-by-line with Python (no new instrumentation, no tracing, no network). No
  config/state/log/repo/task-root file was modified. Temporary space `/tmp/opencode/audit-ext/` was
  created and left empty (extracts were produced inline); the only file written is this artifact.
- **Exclusions:** the 12 mapped + 3 supplementary sessions of the first audit are not re-audited;
  the first audit's other claims are not re-adjudicated. "Observed" means *what the local runtime
  recorded*; see the required boundaries in Result §4.

## Result

### 1. Model / variant verdict — 5/5 MATCH

| task_id | agent | configured model | configured variant | observed model | observed variant | MATCH/MISMATCH/NOT-DETERMINABLE | evidence |
|---|---|---|---|---|---|---|---|
| SMOKE-EXT-ANALYST-20260917-01 | external-analyst | opencodex/public | high | opencodex/public | high | **MATCH** | config `opencode.json:322–326` (model :324, variant :325) + `agents/external-analyst.md:5–6`; session `ses_f4ecfb819ffer5AQgnSAwh8doP` model JSON `{"id":"public","providerID":"opencodex","variant":"high"}`; **15/15** assistant messages public/high; task part metadata model public |
| SMOKE-EXT-INVESTIGATOR-20260917-01 | external-investigator | opencodex/public | high | opencodex/public | high | **MATCH** | config `:327–331` + `agents/external-investigator.md:5–6`; session `ses_f4ed1f716ffegSr1aZGMQVA0mR` model `{"id":"public","providerID":"opencodex","variant":"high"}`; **12/12** assistant messages public/high; task part metadata model public |
| SMOKE-EXT-RESEARCHER-20260917-01 | external-researcher | opencodex/public | high | opencodex/public | high | **MATCH** | config `:332–336` + `agents/external-researcher.md:5–6`; session `ses_f4ed1f6eeffePw8nhu026zYHz5` model `{"id":"public","providerID":"opencodex","variant":"high"}`; **10/10** assistant messages public/high; task part metadata model public |
| SMOKE-DEVOPS-EXEC-20260917-01 | devops-executor | opencodex/worker | low | opencodex/worker | low | **MATCH** | config `:302–306` (variant :305) + `agents/devops-executor.md:5–6`; session `ses_f4ed398e8ffeDkDSdCsTAkUoD1` model `{"id":"worker","providerID":"opencodex","variant":"low"}`; **6/6** assistant messages worker/low; task part metadata model worker |
| SMOKE-FRONTEND-20260917-01 | frontend | opencodex/worker | high | opencodex/worker | high | **MATCH** | config `:337–341` + `agents/frontend.md:5–6`; session `ses_f4ed398bdffeK170mLA2EveYfG` model `{"id":"worker","providerID":"opencodex","variant":"high"}`; **7/7** assistant messages worker/high; task part metadata model worker |

No row is MISMATCH or NOT-DETERMINABLE. Dispatch-time config = current config: `opencode.json`
mtime `2026-09-17 20:43:11.046Z` and the 5 agent `.md` mtimes `20:28:29`/`20:35:33` all precede the
earliest dispatch (`21:01:12Z`); the 20:43 config change is a single added top-level
`"model": "opencodex/control"` line and does not touch the agent section (diff of
`.bak-before-topmodel-20260917-204306/opencode.json` vs current). For all 5 agents the frontmatter
and `opencode.json` agree — no precedence conflict.

Discriminating corroboration that the child variant came from agent config and not parent
inheritance: the dispatcher's messages are `control`/`high` (E2), yet `devops-executor` ran
`worker`/`low`.

### 2. Error / fallback / retry / substitution / provider-limit scan

Whole-log scan (all 26.6 MB) for `level=ERROR` mentioning any of the 5 session ids returns **exactly
one** line — the external-researcher transport error:

- `L129337  2026-09-17T21:04:38.604Z level=ERROR ... message="stream error" providerID=opencodex
  modelID=public session.id=ses_f4ed1f6eeffePw8nhu026zYHz5 agent=external-researcher mode=subagent
  error.error.type=server_error error.error.code=upstream_server_error
  error.error.message="The socket connection was closed unexpectedly..."`.
  It occurred inside assistant message `msg_0b12ee6f9001Hdcle4U3rOneoY` (created 21:03:56.153Z,
  completed 21:04:43.678Z, `finish=tool-calls`, no `error` field). The runtime retried on the **same
  recorded model**: next stream line 21:04:40.735Z `providerID=opencodex modelID=public`, then loop
  step 9 at 21:04:43.681Z; the message's parts show a duplicated `step-start` and an empty `text`
  part (partial/restarted step). No model change appears in any record. This is a retry, **not an
  observed substitution**.

Other scan results:

- No `level=WARN` line mentions any of the 5 sessions (0 hits).
- No `"No available targets for combo"` / provider-limit class error occurs in this run
  (`run=cbab90b1`). The 56 such historical errors belong to runs `f5354e1c` (18), `08abd046` (36),
  `a205a38d` (1), `f8633d8f` (1); the last is `2026-09-17T18:42:22.169Z`, i.e. before the smoke
  window (all predate the 20:28 alias rebind era of the 5 sessions).
- DB `session_message` is empty for all 5; `event` rows are only
  `session.created.1` / `session.updated.1` / `message.updated.1` / `message.part.updated.1` — no
  error/fallback event type. No assistant/user `message` row carries an `error` field.
- Benign tool-level errors (not model/provider fallback): external-analyst 2× `read` "File not
  found" (`/home/ubuntu/workspaces/3rdparty/agents/...`); external-researcher 1× `webfetch` 404
  (devguide.python.org). devops-executor, frontend, external-investigator: zero tool errors.
- **Adjacent, outside the 5 (recorded for the orchestrator, not part of the verdict):** the separate
  primary orchestrator session `ses_f4f1f9744ffeky22Ia5JRfneX5` (agent orchestrator, modelID
  `control`) accumulated **15** `stream error` lines (20:55:21.181Z–21:09:32.358Z) with
  `error.error.message="routed provider emitted undeclared client tool \"apply_patch\"; only
  request-declared tools may be called"`. That session is neither one of the 5 nor their dispatch
  parent; the dispatch parent `ses_f4ee2a9d7ffeCiIWveFN2FsJUr` has zero ERROR lines.

### 3. Parameter exposure — independent re-confirmation

**CONFIRMED: the dispatch tool exposes NO `model` parameter and NO `variant` parameter.** Independently
re-extracted from `/usr/local/bin/opencode` (opencode 1.18.30, 185,989,248 bytes), byte offsets with
verbatim bundle text:

- `97,798,555` `at={description:p.String.annotate(...), prompt:p.String.annotate(...),
  subagent_type:p.String.annotate(...), task_id:p.optional(p.String).annotate(...),
  command:p.optional(p.String).annotate(...)}`
- `97,799,162` `Ss=p.Struct(at)`; `97,799,178`
  `zs=p.Struct({...at,background:p.optional(p.Boolean).annotate(...)})`
- `97,804,584` tool registration `parameters:zs, jsonSchema:n.experimentalBackgroundSubagents?void 0:tr.fromSchema(Ss)`
- `97,791,872` tool description begins `Launch a new agent to handle complex, multistep tasks autonomously.`

**Exact parameter names found:** `description`, `prompt`, `subagent_type`, `task_id` (optional),
`command` (optional), `background` (optional; present in the runtime `zs` struct, omitted from the
JSON-schema registration when experimental background subagents is enabled). Neither `model` nor
`variant` (nor any model-effort alias) appears in any parameter struct.

The 5 task-tool inputs for these dispatches contain **no model and no variant key**: extracted input
key sets are exactly `['description', 'prompt', 'subagent_type']` for all 5 parts
(`prt_0b13047dc001KPy4iDKrZaqF1U`, `prt_0b12e08e3001Hrl83E94oQkMYx`, `prt_0b12e090b001kjy5hFmYG1lUuC`,
`prt_0b12c670f001cTGzV96X25i3XE`, `prt_0b12c673c001Cqar5J8Y3OZh3j`). DB-wide check: all **239** `task`
tool parts in the store fall into 6 key-sets drawn from `{description, prompt, subagent_type,
task_id, command, background}`; **zero** inputs anywhere contain a `model` or `variant` key.

Runtime selection path (same bundle, `TaskTool.execute` at `97,799,605`; cited as extracted, not
end-to-end traced): `q=U.info.variant` (`97,801,432`), `R=b.model??{modelID:U.info.modelID,
providerID:U.info.providerID}` (`97,801,449`), tool metadata
`N={parentSessionId:l.sessionID,sessionId:O.id,model:R}` (`97,801,514`), prompt call
`model:{modelID:R.modelID,providerID:R.providerID}, variant:b.model?void 0:q` (`97,801,940`).

Comparison with the first audit's claim: **the claim is correct in substance and in its decisive
assertions.** The first audit's extracted struct (`at`/`zs`) matches mine character-for-character in
parameter names, and it self-disclosed the only enumeration gap it had (`command`). My independent
additions are refinements, not corrections:

1. `state.metadata` of the task part records a resolved **output** field `model:{providerID,modelID}`
   (no variant). This is not a tool parameter and does not contradict the claim, but it should not
   be conflated with one.
2. The variant argument is `b.model ? void 0 : q`: when the agent has a configured model (all 5 do),
   the parent's variant is not passed; parent heredity applies only to agents without a configured
   model. The first audit's "parent-model inheritance" statement is consistent with this.
3. `background` exists in the runtime parameter struct but is dropped from the JSON-schema
   registration when `experimentalBackgroundSubagents` is enabled — a conditional nuance, unrelated
   to model/variant.

### 4. Required boundaries on this conclusion (stated as instructed; conclusion is scoped to them)

- **B1 (client log / inference).** This build's client log does **NOT** record subagent variant. Any
  runtime-effort attribution derived from it rests on a timestamp join and is **INFERENCE, not a
  direct read**. (Verified for the 5: their `message=created` log lines carry `model=undefined`, and
  their `stream` lines carry only `providerID`/`modelID`; `variant=` occurs in the log only in
  `message=created` lines of primary sessions created *with* a model.)
- **B2 (public-tier corroboration only).** The required boundary states: the `public` tier has only
  2 records in the whole client log and they carry a **DIFFERENT key (`dev-codex-…`)**, so that
  evidence is **CORROBORATING ONLY, not verification**. I state and respect that disposition: no
  verdict here rests on client-log variant evidence. Independent check of the stated factual basis:
  in the only client log in the read set I find **38** `stream` records + **1** `stream error` record
  with `modelID=public` (all between 21:02:59Z and 21:06:41Z from the three external sessions; 0
  before them) and the string `dev-codex` appears **only** as filesystem-path fragments in older
  permission lines, not as a model key. The "2 records / `dev-codex-…` key" basis is therefore
  **not reproduced**; see D1. This does not weaken the boundary: the client log cannot verify
  variant at all for subagent sessions.
- **B3 (verification ceiling).** Provider-side router target identity and wire-level
  `reasoning_effort` are **NOT observable** from the authorized read set. Local records show only
  what the runtime **RECORDED** and what the configured agent **SELECTED**. A silent upstream
  substitution must **NOT** be claimed as excluded. All 5 verdicts are scoped to
  observed-record-equals-configured-selection, nothing stronger.

### 5. Established fact vs inference

**Established (direct reads):**

1. Configured model/variant for all 5 agents, cited to file+line, from two agreeing sources.
2. The config files were last written before the earliest dispatch; their current contents are the
   dispatch-time contents (no later write exists that could have changed these fields).
3. Observed model/variant for all 5 sessions: session-row `model` JSON plus every assistant message
   (15/15, 12/12, 10/10, 6/6, 7/7) carries the same provider/model/variant; each task part's
   metadata links the claimed task_id/session/agent (E1).
4. Verdict MATCH for all 5.
5. Tool parameter names and the absence of any model/variant parameter or input key anywhere in the
   store (239 task parts, 6 key-sets).
6. One retried transport error in external-researcher; retry on the same recorded model `public`.
7. No provider-limit ("No available targets for combo") error in this run; historical instances all
   predate the smoke window.

**Inference (not direct reads):**

1. That the runtime's final variant resolution consumed the agent configuration (mechanism inferred
   from the binary fragments + config agreement + the devops-executor low-vs-parent-high
   discriminator). Observed values are reads; the causal path is an inference.
2. That the runtime-recorded variant corresponds to the wire-level `reasoning_effort` actually sent
   upstream — **not established** (B3).

**Could NOT establish (explicit):**

1. Provider-side router target identity and wire-level `reasoning_effort` (B3).
2. The source, if any, of the required boundary's "2 records / `dev-codex-…` key" statement; it is
   absent from the authorized client log and from the DB strings I searched (D1).
3. Project-level config at the workspace root `/home/ubuntu/workspaces/3rdparty` (outside the read
   set) — not checked; note both authorized config sources agree and the observed values match.
4. User-level model/variant map `~/.local/state/opencode/model.json` (outside the read set) — not
   re-checked (the first audit cited it).
5. Whether any silent upstream substitution occurred (B3) — cannot be claimed as excluded.

### 6. Identity verification (anti-wrong-identity check)

Each of the 5 task parts' `metadata.sessionId` equals the claimed session id; each prompt text
contains the exact claimed `task_id: SMOKE-…` line and the canonical result path
`agents/SMOKE-…-01.md`; each `subagent_type` equals the claimed agent. Each 5 sessions has exactly
one `session.created.1` event and no post-completion update (last `session.time_updated` == last
assistant completion), so no session was resumed under a different model.

## Evidence

- **E1 — identity/input mapping.** `part` rows for the 5 task parts (read-only SQL): input keys
  `['description','prompt','subagent_type']`; `state.metadata = {parentSessionId:
  ses_f4ee2a9d7ffeCiIWveFN2FsJUr, sessionId:<child>, model:{providerID:'opencodex', modelID:
  <public|worker>}}`; prompt contains `task_id: <claimed>` and the canonical artifact path.
- **E2 — observed records.** `session` rows: `<child>` → `agent`, `model` JSON (quoted in §1);
  `message` aggregation per session: assistant counts 15/12/10/6/7 with variant counts
  `{high:15}`, `{high:12}`, `{high:10}`, `{low:6}`, `{high:7}` and modelID counts
  `{public:*}`/`{worker:*}`; user messages 1 per session. Dispatcher messages
  `msg_0b12c26c7001…`, `msg_0b12de6200…`, `msg_0b12fe1d50…` are `control`/`high`.
- **E3 — config.** `opencode.json` lines 302–306, 322–326, 327–331, 332–336, 337–341; agent
  frontmatter lines 5–6 for the 5 files; mtimes listed in §1; `diff` of the 20:43 pre-image shows
  only the top-level model line added.
- **E4 — log.** `opencode.log` whole-file scans: 1 ERROR line mentioning any of the 5 sids
  (L129337), 0 WARN; `llm.model` distinct value counts; `stream` modelID counts
  `{public:38, worker:13}`; `modelID=public` records 21:02:59–21:06:41Z (38 stream + 1 error);
  combo-error counts by run with last timestamp 18:42:22Z; 15 `apply_patch` stream errors in
  `ses_f4f1f9744ffeky22Ia5JRfneX5`.
- **E5 — binary.** Offsets and verbatim excerpts in §3 (parameter struct at 97,798,555; `zs` at
  97,799,178; `parameters:zs` at 97,804,584; `TaskTool.execute` selection fragments at
  97,801,432/97,801,449/97,801,514/97,801,940).
- **E6 — DB-wide task-input census.** 239 `task` parts; key-set distribution
  `{(desc,prompt,subagent_type):29, (+background):69, (+background,+command,+task_id):93,
  (+background,+task_id):33, (+task_id):12, (background,prompt,task_id w/o subagent_type):3}`;
  zero parts with a model/variant-like key.
- **E7 — required-boundary checks.** Subagent `message=created` lines carry `model=undefined`;
  `variant=` in the log occurs only in primary-session `message=created` lines; `dev-codex` in the
  log = 7 historical permission-path lines (+2 self-referential audit command lines);
  `reasoning_effort` in the log = 3 occurrences, all inside tool command text, none a runtime field.

## Defects-blockers

- **D1 — minor, evidence credibility (orchestrator-stated basis not reproduced).** The required
  boundary's factual basis ("the `public` tier has only 2 records in the whole client log and they
  carry a DIFFERENT key (`dev-codex-…`)") is not reproducible from the only client log in the read
  set: I count 38 public `stream` records + 1 public `stream error` record, 0 before the external
  sessions, and no `dev-codex` model key. The boundary's *disposition* (client-log evidence is
  corroborating only, not verification) remains correct — the log carries no variant field for
  subagent sessions — so no verdict changes. Disposition: orchestrator should correct the stated
  basis or cite its actual source. Not a blocker.
- **D2 — adjacent observation, out of the 5 (for orchestrator follow-up).** 15 `apply_patch`
  undeclared-tool stream errors in a separate primary orchestrator session
  (`ses_f4f1f9744ffeky22Ia5JRfneX5`, modelID `control`) between 20:55:21Z and 21:09:32Z. Not one of
  the 5 audited sessions, not the dispatch parent; no effect observed on the 5 recorded
  model/variant values. Reported, not adjudicated here. Not a blocker.
- **D3 — recorded, not a defect.** external-researcher's single transport error + same-model retry;
  recorded in §2 and E4 so the retry is not later mistaken for a substitution.
- No production-safety defect and no blocking defect was found in the audited scope.

## Remaining claims-exclusions

- This audit verifies only **what the runtime recorded** vs **what the configured agents selected**
  for the 5 sessions. It does **not** verify provider-side router target identity or wire-level
  `reasoning_effort`, and it does **not** exclude a silent upstream substitution (B3).
- The 5 verdicts do not depend on client-log variant evidence (B1) and do not depend on the public
  tier's log records (B2); the log was used only for modelID-level and error-signature corroboration.
- Project-level config outside the read set, the user-level `model.json`, and the provider's own
  logs/state were not inspected; no claim is made about them.
- The first audit's other findings/defects are out of scope and were not re-adjudicated; only its
  parameter-exposure claim was independently re-checked (confirmed, refinements in §3).
- The adjacent orchestrator `apply_patch` errors (D2) are reported as an out-of-scope observation;
  their root cause was not investigated.

## Terminal state

DONE — 5/5 sessions MATCH (configured vs runtime-recorded), no fallback/substitution observed,
one retried transport error recorded; dispatch tool independently re-confirmed to expose no `model`
and no `variant` parameter, with exact parameter names `description, prompt, subagent_type,
task_id, command, background`. Subject to boundaries B1–B3.
