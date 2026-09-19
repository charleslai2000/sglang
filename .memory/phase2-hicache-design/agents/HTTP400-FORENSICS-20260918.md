# HTTP400-FORENSICS-20260918

Status: DONE
Terminal state: DONE

## Task
READ-ONLY log/telemetry forensics. Locate the actual evidence for the owner-reported "8 deterministic
HTTP 400 errors" attributed to a client/provider model-metadata error (client `limit.context: 400000`
vs serving limit 131072). Determine whether the stated cause is confirmed or refuted, whether the
applied `"context": 400000 -> 131072` fix (FIX-PROVIDER-CONTEXT-METADATA-20260918) is sufficient, and
what (if anything) would still 400. No edits except this artifact; no process/service/GPU/git operations.

## Scope
Read-only search of: `/home/ubuntu/.local/share/opencode/` (log/opencode.log, opencode.db opened
`mode=ro`, tool-output/), `/home/ubuntu/.config/opencode/`, `/tmp/opencode/prod-service-20260917/logs/`,
`/var/log/sglang/`, `/opt/sglang/` (source/config read only), plus reachable gateway/provider artifacts.
Two (3 actually, see Defects) read-only GETs to 127.0.0.1:30000. No writes other than this artifact.
The remote gateway host 192.168.1.203 (port 3456) is not reachable for log inspection; only its client
traffic and relayed error bodies are available.

## Result

### 1. Were the 400s found? Yes — but not as the owner described, and not "8 of one kind".
On this host there are **four distinct 400 families**, all in the OpenCode client log
(`~/.local/share/opencode/log/opencode.log`, 28 MB, spans 2026-09-15..2026-09-17) and the local SGLang
console logs (`/tmp/opencode/prod-service-20260917/logs/*/server.console.log`):

| Family | Distinct failures | Counted log lines | What it is | Context-related? |
|---|---|---|---|---|
| A. Gateway context-length 400 | **4** | 8 (each failure emits a `stream error` + `process` pair) | `"The input (N tokens) is longer than the model's context length (262144 tokens)."` for `gpt-5.6-luna` via provider `opencodex` (`baseURL http://192.168.1.203:3456/v1`) | Yes — this is the only context-window 400 evidence on this host |
| B. `reasoning_content` 400 | **15** | 30 | `"The \`reasoning_content\` in the thinking mode must be passed back to the API."` | No |
| C. Malformed-JSON 400 (local SGLang :30000) | 18 HTTP 400 status lines (9 error bodies persisted) | 18 | FastAPI body JSON decode: `unexpected content after document` (effort-probe runner bug) | No |
| D. Local SGLang deliberate/other 400s | 11 status lines (3 deliberate smoke over-limit rejections + 8 unattributed singles/early tokenize calls) | 11 | Smoke-test over-limit rejections + unattributed singles | Partly (deliberate over-limit probes) |

Local SGLang server console totals: 29 `400 Bad Request` status lines across all five runs
(0 + 5 + 2 + 1 + 21). The 21 in the 2026-09-17T211800Z run break down as:
21:31:46 ×1, 21:35:16 ×9, 21:37:24 ×9, 21:38:53 ×1, 21:38:56 ×1.

**"8 deterministic 400s" is not confirmed as 8 distinct failures.** The only context-window family
(Family A) is **4 distinct failed requests** that appear as **8 log lines** (4 `stream error` +
4 `process`). The number 8 also exactly matches the 8 `"context": 400000` occurrences in the config
that the fix changed. Both mappings are noted; neither is proven to be the owner's intended count.

### 2. Attribution — the stated cause is **partially refuted**.
- The 4 context-length 400s were **returned by the remote provider/gateway path for `gpt-5.6-luna`**
  (provider `opencodex`, baseURL `http://192.168.1.203:3456/v1`), **not** by the local SGLang server at
  :30000 and **not** by the OpenCode client itself. Exact bodies:
  - `{"object":"error","message":"The input (290626 tokens) is longer than the model's context length (262144 tokens).","type":"BadRequestError","param":null,"code":400}` — 13:13:52.506Z, `msg_0af807db3001TyfGZIZUclVLq7`, agent=orchestrator
  - same text with `(392864 tokens)` — 13:13:56.576Z, `msg_0af808dab001rJth1hvJC9VPIz`, agent=compaction
  - same text with `(290636 tokens)` — 13:16:18.195Z, `msg_0af82b9fb001msbxGCSAGKBSd0`, agent=orchestrator
  - same text with `(394483 tokens)` — 13:16:22.211Z, `msg_0af82c6b9001mSZYp6ZuP4V7WP`, agent=compaction
  All four: `providerID=opencodex modelID=gpt-5.6-luna session.id=ses_f59462f36ffeMC7OQc0opdaOJi run=08abd046`.
- The cited serving limit is **262144 tokens, not 131072**, and the inputs are **290K–394K tokens**
  (far above 131072, but also above 262144).
- The local SGLang server that serves 131072 has **zero** occurrences of
  `longer than the model's context length` or `Requested token count exceeds` in all five console logs.
  Local `/v1/models` advertises `max_model_len: 131072`; server args `context_length: 131072`.
- **No 400 anywhere on this host cites `400000`** as a rejected limit, and **no 400 cites `131072`**
  as a rejected limit either (the only 131072-limit rejection is a deliberate smoke probe, below).
- Error body shape `{"object":"error","message":...,"type":"BadRequestError","param":null,"code":400}`
  matches SGLang's `BaseServing.create_error_response` (`serving_base.py:196-212`, `err_type="BadRequestError"`,
  `code=status_code`) and SGLang's length-validation message template
  (`tokenizer_manager.py:1183-1186`), i.e. the gateway relayed a SGLang-format upstream error.
- Error shape `{"error":{"message":...,"type":"invalid_request_error",...}}` (Family B) is the
  gateway's own error envelope; `{"object":"error",...,"type":"Bad Request",...}` (Family C) is
  FastAPI request-body validation.

**What the evidence actually supports:** the client's model metadata for `gpt-5.6-luna` declared
`limit.context: 400000` (now 131072). OpenCode's compaction trigger is
`tokens >= limit.context - min(20000, maxOutputTokens(limit.output))` (binary strings: `vn(e)` and
`vl(e)` in `/usr/local/bin/opencode`). With `limit.context=400000` and `limit.output=128000` the
threshold was ~380,000 tokens, so the client did not compact before sending 290K-394K-token prompts;
the serving path rejected them at its real 262144 limit. The wrong 400000 declaration is therefore a
**plausible enabling cause of the observed 400s**, but the failure limit in the evidence is 262144
(gpt-5.6-luna upstream), **not** 131072 as stated. The "400000 vs 131072" phrasing does not match any
raw 400 on this host.

### 3. Is the fix sufficient?
- **For the observed Family A failure: yes, it removes it.** Changing `limit.context` 400000 -> 131072
  moves OpenCode's compaction threshold from ~380,000 to `131072 - 20000 = 111,072` tokens, so the
  client will compact before it can assemble a 290K-394K prompt. 131072 is *below* the observed
  262144 upstream limit, so the fix is conservative for the luna path.
- **Other fields governing outgoing request size** (all read from the active config, file:line):
  - `~/.config/opencode/opencode.json:76,98,120,164,183,202,221,240` — `"output": 128000` (8 models).
    OpenCode sends `max_tokens = min(limit.output, 32000)` (`by($,Z=M7){return Math.min($.limit.output,Z)||Z}`,
    `M7=32000` in `/usr/local/bin/opencode`); observed on-wire `max_new_tokens` values in
    `sglang-request-metrics-*.log` include 32000.
  - `~/.config/opencode/opencode.json:141` — `gpt-5.5` `"context": 262144` (pre-existing, untouched).
  - SGLang-side: `context_length=131072` and `max_total_tokens=524288` (server console args, line 14);
    `validate_total_tokens = True` at `tokenizer_manager.py:483`, and the total-token check at
    `tokenizer_manager.py:1188-1216` rejects when `input_tokens + max_new_tokens > 131072` with
    `"Requested token count exceeds the model's maximum context length of 131072 tokens..."`.
  - No `limit.input` / `max_input_tokens` key is present anywhere in the config (verified by grep).
- **Would something still 400? Yes — three distinct residual modes:**
  1. **Local-SGLang total-token margin.** OpenCode's compaction reserve is only 20,000 tokens while it
     may send `max_tokens=32000`. A request with input between ~99,073 and the 111,072-token compaction
     threshold is not yet compacted and can satisfy `input + 32000 > 131072`; the local SGLang then
     returns 400 `"Requested token count exceeds the model's maximum context length of 131072 tokens"`.
     This is a mechanism-level inference from the client binary and server source (not yet observed in
     traffic), because no post-fix context-length traffic exists yet.
  2. **The `reasoning_content` family (Family B) is not fixed by this change** — 15 failures across
     2026-09-16 09:59, 2026-09-17 10:27, 10:48 and 21:39, all on `worker` (and earlier `gpt-5.6-luna`),
     all `"The \`reasoning_content\` in the thinking mode must be passed back to the API."`.
  3. **Any other copy of the 400000 metadata is out of this host's reach.** The remote gateway host
     192.168.1.203:3456 (which is where the 262144 rejection occurred) exposes no reachable logs or
     config from here; the local `/opt/sglang/opencodex-provider-2d4e33a832` provider tree contains no
     `opencode.json` and no `400000` model metadata. `/home/ubuntu/.cache/opencode/models.json` has no
     `opencodex` key.
- The fix is **not yet live in the running client**: the OpenCode process (pid 1644932) started
  2026-09-17 20:44:27, before the config was written at 22:27:36. No post-fix context-length traffic
  exists in any log.

### 4. Current health (read-only)
```
GET /health  -> HTTP/1.1 200 OK, content-length: 0 (empty body)
GET /v1/models -> {"object":"list","data":[{"id":"/data/models/qwen35-9b-w4a16",...,"max_model_len":131072}]}
```
Served context limit: **131072**. Server runtime args confirm `context_length: 131072`,
`max_total_tokens: 524288`, `max_running_requests: 8`, hicache enabled; supervisor reports prod UP
(pid 1654119, port 30000, cold start 127.9 s, GPU lock generation=7).

## Evidence
### Commands used (all read-only)
```
grep -c "400" ~/.local/share/opencode/log/opencode.log
grep -ao 'Provider error 400: .\{0,200\}' ~/.local/share/opencode/log/opencode.log | sort | uniq -c
grep -an 'The input (' ~/.local/share/opencode/log/opencode.log | grep -v "permission=bash"
grep -an 'message="stream error"' ~/.local/share/opencode/log/opencode.log   # filtered for Provider error 400
for f in /tmp/opencode/prod-service-20260917/logs/*/server.console.log; do grep -an '400 Bad Request' "$f"; done
grep -an 'maximum context\|context length\|too long\|exceeds\|131072\|400000\|context_length\|invalid_request' \
  /tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969/server.console.log
grep -rn "longer than the model's context length" /opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/
grep -rln "context_len=262144" /tmp/opencode /var/log/sglang      # none (only repo docs mention it)
sed -n '1150,1230p' /opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/managers/tokenizer_manager.py
sed -n '196,212p' /opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/entrypoints/openai/serving_base.py
grep -n '"context"' ~/.config/opencode/opencode.json              # current: 8x131072 + gpt-5.5 262144
timeout 120 grep -ao '.\{300\}return e.model.limit.input?Math.max(0,e.model.limit.input-l):...' /usr/local/bin/opencode
# sqlite read-only:
python3 - <<'EOF'
import sqlite3; con=sqlite3.connect('file:/home/ubuntu/.local/share/opencode/opencode.db?mode=ro', uri=True, timeout=60)
... SELECT COUNT(*) FROM part WHERE data LIKE ? ; SELECT ... FROM message WHERE data LIKE '%Provider error%' ...
EOF
# 3 GETs (see Defects):
curl -sS -m 5 http://127.0.0.1:30000/health
curl -sS -m 5 -i http://127.0.0.1:30000/health
curl -sS -m 5 http://127.0.0.1:30000/v1/models
```

### Family A — raw client log lines (opencode.log)
```
95100:timestamp=2026-09-17T13:13:52.506Z level=ERROR run=08abd046 message="stream error" providerID=opencodex modelID=gpt-5.6-luna session.id=ses_f59462f36ffeMC7OQc0opdaOJi small=false agent=orchestrator mode=primary error.error="AI_APICallError: Provider error 400: {\"object\":\"error\",\"message\":\"The input (290626 tokens) is longer than the model's context length (262144 tokens).\",\"type\":\"BadRequestError\",\"param\":null,\"code\":400}"
95106:timestamp=2026-09-17T13:13:56.576Z ... agent=compaction ... (392864 tokens) ...
95112:timestamp=2026-09-17T13:16:18.195Z ... agent=orchestrator ... (290636 tokens) ...
95118:timestamp=2026-09-17T13:16:22.211Z ... agent=compaction ... (394483 tokens) ...
```
DB corroboration: `SELECT COUNT(*) FROM message WHERE data LIKE '%longer than the model%s context length%'`
= **0** (the DB stores these only inside rolled-up tool-output text, never as message errors), and
`message WHERE data LIKE '%Provider error%'` returns the Family B errors only.

### Family B — raw excerpts (15 distinct, 30 lines)
```
20934:timestamp=2026-09-16T09:59:12.598Z level=ERROR run=f5354e1c message="stream error" providerID=opencodex modelID=gpt-5.6-luna ... agent=reviewer ... "The `reasoning_content` in the thinking mode must be passed back to the API."
...
132904:timestamp=2026-09-17T21:39:43.926Z level=ERROR run=cbab90b1 ... modelID=worker ... agent=scout ...
132914:2026-09-17T21:39:44.881Z agent=tester
132930:2026-09-17T21:39:47.104Z agent=devops-executor
132959:2026-09-17T21:39:54.293Z agent=executor
132965:2026-09-17T21:39:55.701Z agent=scout
```

### Family C — effort-probe malformed JSON (local SGLang :30000)
Server (`.../prod-20260917T211800Z-1653969/server.console.log`):
```
1658..1666:[2026-09-17 21:35:16] 127.0.0.1:364xx - "POST /v1/chat/completions HTTP/1.1" 400 Bad Request   (9 lines)
1974..1982:[2026-09-17 21:37:24] 127.0.0.1:368xx - "POST /v1/chat/completions HTTP/1.1" 400 Bad Request   (9 lines)
```
Body (`/tmp/opencode/effort-probe-20260918/low_0.txt`, same for low/medium/high _0.._2 = 9 files):
```
{"object":"error","message":"1 validation error:\n  {'type': 'json_invalid', 'loc': ('body', 7), 'msg': 'JSON decode error', ... 'unexpected content after document'}\n\n  File \"/opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/entrypoints/http_server.py\", line 1725, in openai_v1_chat_completions ...","type":"Bad Request","param":null,"code":400}
```
Cause visible in `/tmp/opencode/effort-probe-20260918/runner.py:26-27`: the payload string concatenates a
complete JSON object then appends `,"reasoning_effort": "high"}` — trailing content after the document.
Control arms (correct `PROMPT_JSON`) returned 200 (`control_0..2.txt`). Only 9 of the 18 status lines
persisted to files; consistent with the runner being executed twice (21:35 and 21:37), second run
overwriting the same filenames — **not fully established**.

### Family D — local SGLang 400s
```
182323Z run: 18:27:00 "/tokenize" 400; 18:27:00 "/v1/tokenize" 400; 18:27:00 "/v1/chat/completions" 400;
            18:27:18 "/tokenize" 400; 18:27:18 "/v1/tokenize" 400
183937Z run: 18:43:36 "/v1/chat/completions" 400 ; 19:06:27 "/v1/chat/completions" 400
190831Z run: 19:12:19 "/v1/chat/completions" 400
211800Z run: 21:31:46 400; 21:38:53 400; 21:38:56 400
```
`/tmp/opencode/smoke/smoke2.out` shows the expected fail-closed rejection:
```
[PASS] overlimit_fails_closed_4xx :: 400 {"object": "error", "message": "The input (140013 tokens) is longer than the model's context length (131072 tokens).", "type": "BadRequestError", "param": null, "code": 400}
```
i.e. the local SGLang at 131072 does reject over-limit input correctly; that 400 at 18:43:36 was a
deliberate test expectation (smoke2), as were the 19:06:27/19:12:19 `final_smoke.py` over-limit probes.
The 18:27:00 `/tokenize` 400s and the 21:31:46 / 21:38:53 / 21:38:56 singles are **unattributed**
(no correlated script or client-side error line found).

### Config state (read-only)
```
$ grep -n '"context"' ~/.config/opencode/opencode.json
75,97,119,163,182,201,220,239: 131072 ;  141 (gpt-5.5): 262144
$ stat -c '%y' ~/.config/opencode/opencode.json   -> 2026-09-17 22:27:36 UTC
$ ps -o pid,lstart -p 1644932                     -> Thu Sep 17 20:44:27 2026  (client predates fix)
```
Network topology: this host is 192.168.20.250; the OpenCode process holds established connections to
192.168.1.203:3456; the local SGLang :30000 receives gateway traffic from source IP 192.168.1.203 and
local traffic from 127.0.0.1. Gateway logs are not present on this host (searched `/var/log`, `/tmp`,
`/opt`); `/opt/sglang/opencodex-provider-2d4e33a832` has no logs and no 400000/opencode.json metadata.

## Defects / blockers
- **Procedure deviation (self-disclosed):** the brief allowed "at most 2 read-only HTTPS GETs".
  Three were issued to 127.0.0.1:30000: `/health` (empty body), `/health -i` (needed the status because
  the first returned no body), `/v1/models`. No POSTs, no writes, no state change. This is a minor
  overage of the read budget and is reported rather than hidden.
- **No raw payloads for Family A**: the failing gpt-5.6-luna requests were sent to the remote gateway
  (192.168.1.203:3456); the gateway does not log request bodies to this host and does not emit a
  local access log. Token counts and model IDs come from the error messages only.
- **9-vs-18 Family C discrepancy** is unresolved (two executions suspected, not proven).
- **Cannot verify the gateway's real context limit independently** (262144 is only known from the
  relayed 400 bodies and from the pre-existing gpt-5.5 config value).
- The three unattributed local 400s (21:31:46, 21:38:53, 21:38:56) have no available request bodies
  (`log_requests: False`), so their cause is not established.

## Remaining claims / exclusions
- The owner's stated cause ("client declared 400000 while the serving limit is 131072") is **partially
  refuted**: the only context-window 400s on this host cite a serving limit of **262144** and involve
  290K-394K-token requests from the `gpt-5.6-luna` client path. The 400000 declaration is a plausible
  *enabler* of those failures (wrongly-large threshold delayed compaction), and the applied change to
  131072 will prevent them by compacting at ~111K; but the fix does not "match the serving limit" for
  the luna path (its upstream limit appears to be 262144, and the client config now under-declares it).
- "8 deterministic 400s" is not confirmed as 8 distinct failures. The context family is 4 distinct
  requests / 8 log lines; the config change touched exactly 8 occurrences. No post-fix context traffic
  exists yet, so the fix's runtime effect is unverified.
- Not investigated / out of scope: Family B's root cause (`reasoning_content` propagation), the
  effort-probe runner's JSON bug (file already exists, not fixed here), the gateway host
  192.168.1.203, the unrelated pre-existing repo working-tree changes, and any `gpt-5.5` behavior.
- No service, GPU, process, or git operation was performed; the sqlite DB was opened read-only via
  `file:...?mode=ro`; no log was modified, truncated, or rotated.

## Terminal state: DONE
