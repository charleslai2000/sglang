# QQUESTION-HALLUCINATION-HUNT-20260918

Status: DONE
Terminal state: DONE

## Task

Owner question: does the harness contain handling for TOOL HALLUCINATION, specifically for a
hallucinated tool named `qquestion`? A repo-only grep for the literal string returned nothing;
find the real runtime evidence, and determine what the production `qwen3_coder` tool-call parser
does when the model emits a call to an undeclared tool.

## Scope

READ-ONLY forensic sweep. No edits except this artifact. No service ops, no signals, no GPU, no
git mutation. Trees searched: `/home/ubuntu/.local/share/opencode/` (DB + log + tool-output),
`/home/ubuntu/.config/opencode/`, `/tmp/opencode/**`, `/var/log/**` (incl. the 108 GB
`/var/log/sglang` trees), repo `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/**`,
`/opt/sglang/**` (read-only), `/usr/local/bin/opencode` (binary string scan).
SQLite was read with `sqlite3` Python module against
`file:/home/ubuntu/.local/share/opencode/opencode.db?mode=ro` (no CLI `sqlite3` on host; the live
DB was opened read-only by URI, not copied, not modified).

## Result

**(1) YES — `qquestion` IS REAL and it was EMITTED by the served model.**
The production SGLang server for `/data/models/qwen35-9b-w4a16` (launched with
`--tool-call-parser qwen3_coder`) logged, at 21:39:43 on 2026-09-17:

```
[2026-09-17 21:39:43] Tool 'qquestion' is not defined in the tools list.
```

That message is emitted only by `qwen3_coder_detector.py:91`, i.e. it is proof that the model
actually produced a tool call whose function name was `qquestion`, and that the `qwen3_coder`
detector saw it. This settles the owner's question: `qquestion` is not a typo in the question;
it is a hallucinated tool name the model emitted at runtime.

Additionally the same server logged a second undeclared-name event:
`[2026-09-17 21:57:55] Tool 'None' is not defined in the tools list.` — the name was the literal
Python `None` (empty/nulled `<function=...>` name), so this is a second, distinct malformed-name
event, not a `qquestion` recurrence.

**(2) The harness DID NOT execute or persist any `qquestion` tool call.**
No `qquestion` tool part, callID, or persisted tool invocation exists anywhere in the opencode
session DB. All opencode-DB mentions of `qquestion` are conversation *about* it (the owner's
22:24 message, the orchestrator's reasoning, this hunt's own records). The harness's own
`ToolRegistry` contains an unknown-tool branch (binary string
`Unknown tool: ${S.call.name}` returning `result:{type:"error",value:...}`), but it was never
reached for `qquestion` because the SGLang layer never surfaced that name as a structured call.

**(3) `qwen3_coder` = `Qwen3CoderDetector` — it SURFACES undeclared tool calls, it does NOT skip
them.** Mapping: `function_call_parser.py:92` `"qwen3_coder": Qwen3CoderDetector`. The only
undeclared-name handling in `Qwen3CoderDetector` is the warning at `qwen3_coder_detector.py:91`
inside `_get_arguments_config()`, which returns `{}` and parsing continues. The call is already
appended at `qwen3_coder_detector.py:291-297` (`ToolCallItem(..., name=func_name, ...)`) *before*
`_get_arguments_config` is even called, and `detect_and_parse()` (line 225-231) unconditionally
appends the call after the same lookup. There is no membership check against `tools`, no `continue`,
no `return None` — unlike the panic-count "legacy" detectors. So an undeclared call is
**surfaced as a structured tool_call**, with parameters passed through as strings.

**(4) The harness/parser divergence described in the dispatch is CONFIRMED** (all cited lines
exist, see Evidence). Undeclared-tool behavior is inconsistent across detectors:
surface (qwen3_coder, inkling), skip (base_format_detector, gpt_oss, lfm2, pythonic), gated by
`SGLANG_FORWARD_UNKNOWN_TOOLS` (default `False`, `environ.py:676`) for hunyuan / base.

**(5) Consequence — what happened on the wire is consistent with a silent-degradation, not a
structured-error path.** The `qquestion` call was parsed; the detector then emitted:
- requests at 21:39:31/33/39 (192.168.1.203:36860, the gateway) returned HTTP 200;
- the request that produced the warning was the streaming continuation issued at
  `21:39:35.930` (message `msg_0b14f8d7a...`, session `ses_f4eb18efeffe...`, scout/worker);
- at `21:39:43.926` the harness recorded `AI_APICallError: Provider error 400 ... The
  `reasoning_content` in the thinking mode must be passed back to the API.` from the
  gateway `http://192.168.1.203:3456/v1/chat/completions` — i.e. the turn failed at the
  gateway after the hallucinated call was parsed server-side;
- no tool call (neither `qquestion` nor any other) was persisted for that turn.
This is a temporal coincidence (warning and gateway 400 in the same second), but the causal
link is NOT established: the 400's text is about `reasoning_content` in the echoed history,
which is raised by the remote gateway (3456) before/around generation. The local server
returned 200 for the requests it answered. Marked as inference, not fact.

**(6) A second, independent malformed-tool failure mode IS proven:** at `21:57:55.786` the
harness logged `stream error ... "upstream response contained invalid tool calls (invalid
index)"` (session `ses_f4ea113d9ffe0qewdzg05MNW3b`, devops) — immediately after the server's
`Tool 'None' is not defined` warning at `21:57:55`. The string `invalid tool calls (invalid
index)` does not exist in the SGLang source, so it originates in the harness/gateway, i.e. the
harness *does* validate tool calls it receives and *does* fail the turn on malformed ones.

## Evidence

### E1. The `qquestion` emission (primary, verbatim)

File: `/tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969/server.console.log`
Line 2580:

```
[2026-09-17 21:39:43] Tool 'qquestion' is not defined in the tools list.
```

Context (lines 2578-2582): surrounding lines are normal `Decode batch ...` lines; the warning
appears sandwiched between decode batches at 21:39:43, with the nearest access lines being
`21:39:39 ... 200 OK` (line 2570-ish) and `21:40:46 ... 200 OK` (line 2630). No 4xx/5xx access
line within ±60 s of the warning.

Same file, line 6721 (second undeclared-name event):

```
[2026-09-17 21:57:55] Tool 'None' is not defined in the tools list.
```

### E2. Source of that exact message (only one emitter on the host)

```
$ grep -rn "is not defined in the tools list" /opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/
.../function_call/qwen3_coder_detector.py:91:        logger.warning(f"Tool '{func_name}' is not defined in the tools list.")
```
Same line in the repo tree: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/function_call/qwen3_coder_detector.py:91`.
`md5sum` of both copies identical (`61d35298d14804e58e5b119c68387aa0`); `diff -rq` of the whole
`function_call/` dirs shows no source differences (only a `.pyc`).

### E3. Live server argv (read-only from `/proc`)

```
$ tr '\0' ' ' < /proc/1654119/cmdline
/opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server
  --model-path /data/models/qwen35-9b-w4a16 --host 0.0.0.0 --port 30000 ...
  --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics
  --export-metrics-to-file ... --disable-prefill-cuda-graph
```
Confirmed also in the server startup log itself (server.console.log:14): `'tool_call_parser':
'qwen3_coder'`. (An earlier `ps --width 500` was truncated and appeared to omit the flag;
`/proc/<pid>/cmdline` is authoritative.)

### E4. Parser mapping and the undeclared-tool branch (`qwen3_coder`)

File: `/opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/function_call/function_call_parser.py`

```
92:        "qwen3_coder": Qwen3CoderDetector,
```

File: `/opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/srt/function_call/qwen3_coder_detector.py`

```
 64:    def _get_arguments_config(
 65:        self, func_name: str, tools: Optional[list[Tool]]
 66:    ) -> dict:
 67:        """Extract argument configuration for a function."""
 68:        if tools is None:
 69:            return {}
 70:        for config in tools:
 ...
 78:            if config_type == "function" and config_function_name == func_name:
 ...
 91:        logger.warning(f"Tool '{func_name}' is not defined in the tools list.")
 92:        return {}
```

The call is constructed and appended **before** that lookup:

```
286:                    self.current_tool_name_sent = True
...
289:                    self.current_func_name = func_name
290:
291:                    calls.append(
292:                        ToolCallItem(
293:                            tool_index=self.current_tool_id,
294:                            name=func_name,
295:                            parameters="",
296:                        )
297:                    )
```

and in the non-streaming path:

```
206:                    param_config = self._get_arguments_config(func_name, tools)
...
225:                    calls.append(
226:                        ToolCallItem(
227:                            tool_index=tool_idx,
228:                            name=func_name,
229:                            parameters=json.dumps(parsed_params, ensure_ascii=False),
230:                        )
231:                    )
```

There is **no** `func_name not in tool_indices` check anywhere in this file. Therefore
`qwen3_coder` = SURFACE (structurally), with parameters degraded to raw strings for the unknown
tool (`_convert_param_value` returns the string when `param_config == {}`, line 109-115).

### E5. Divergence across detectors (dispatch claims verified verbatim)

Repo tree `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/function_call/`,
prod tree identical:

```
base_format_detector.py:88:                    continue  # Skip unknown tools (default legacy behavior)
gpt_oss_detector.py:225:                return None  # Skip unknown tools (default legacy behavior)
lfm2_detector.py:563:                return None  # Skip unknown tools (default legacy behavior)
pythonic_detector.py:96:                        continue  # Skip unknown tools (default legacy behavior)
hunyuan_detector.py:302:                if function_name not in tool_indices and not forward_unknown:
inkling_detector.py:309:            # Surface the call anyway (OpenAI behavior for hallucinated tools):
inkling_detector.py:310:            # the harness sees a structured tool_call, returns a tool error, and
inkling_detector.py:311:            # the model can self-correct — instead of the serialized invocation
inkling_detector.py:312:            # degrading into terminal answer text.
```

Gate default: `/opt/sglang/.../sglang/srt/environ.py:676: SGLANG_FORWARD_UNKNOWN_TOOLS = EnvBool(False)`.
Line numbers cited in the dispatch are correct in both trees.

### E6. Harness side — no `qquestion` execution, but an unknown-tool error path exists

- Session DB (`file:...opencode.db?mode=ro`), `part` table: 97 rows contain `qquestion`; every one
  is dated 2026-09-17T22:24:36Z or later (the owner's question, orchestrator reasoning, this hunt).
  Zero rows contain `"tool":"qquestion"`, `"name":"qquestion"`, or a `callID` for it.
- Declared/observed tool names actually persisted in the harness: `bash, read, apply_patch, glob,
  grep, todowrite, task, edit, write, webfetch, question`. Requested tool parts whose name is
  outside that set: **0**.
- Harness binary `/usr/local/bin/opencode` (v1.18.30) contains a tool-registry unknown branch:
  `...if($)return I(S,$.identity);return M.succeed({result:{type:"error",value:`Unknown tool:
  ${S.call.name}`}})`. Not reached for `qquestion`.
- Timing: the scout message `msg_0b14f8d7a001hnPClT8Rat5e96` started 21:39:35.930 (10 ms after
  the previous assistant message completed at 21:39:35.920), the server warning landed 21:39:43,
  and at `21:39:43.926`
  the harness logged the 400 from `http://192.168.1.203:3456/v1/chat/completions`:
  `AI_APICallError: Provider error 400: {"error":{"message":"The \`reasoning_content\` in the
  thinking mode must be passed back to the API.", ...}}`. The message has no content parts; the
  turn failed pre-execution.
- `~/.config/opencode/opencode.json` declares `"question": "allow"` in permissions — the real
  `question` tool is declared, consistent with `qquestion` being a doubled-`q` hallucination of it.

### E7. Independent malformed-tool failure (proves harness validation exists)

`/home/ubuntu/.local/share/opencode/log/opencode.log` (also session DB message
`msg_0b1604ec2001wHfyD8jbfX3u8I`, session `ses_f4ea113d9ffe0qewdzg05MNW3b` "Decide if model-id
blocks go-live", 21:57:55.786):

```
ERROR message="stream error" ... error.error.message="upstream response contained invalid tool
calls (invalid index)" error.error.type=invalid_request_error
```

This is the same second as the server-side parse that emitted `Tool 'None' is not defined in the
tools list.` (21:57:55); the server warning is timestamped to the second only, so identity of the
exact request is inferred from the coincidence of session/agent and time, not proven from a
request id. The substring `invalid tool calls` is absent from SGLang source and present in the
harness/gateway layer.

### E8. Search-completeness commands (the negative evidence, with trees)

All commands read-only, bounded, `--binary-files=without-match`, case-insensitive:

```
grep -rIn -i 'qquestion\|q_question\|ask_question\|question_tool\|qquestion_tool' \
  /home/ubuntu/.local/share/opencode/tool-output/            -> 0 hits
grep -rIn -i (same) /home/ubuntu/.local/share/opencode/log/  -> 24 hits (all this hunt's own
                                                                permission/grep traces, 22:30+)
grep -rIn -i (same) /home/ubuntu/.config/opencode/           -> 0 hits
grep -rIn -i (same) /tmp/opencode/                           -> 1 hit (E1 line 2580)
grep -rIl -i 'qquestion' /var/log                            -> 0 (60 s timeout; completed)
grep -rIl -i 'qquestion' /home/ubuntu (excl. .local/.cache/node_modules/.git/.npm/.vscode-server)
                                                             -> only transformers `Seq2SeqQuestion...`
                                                                substring matches (benign, case-fold)
grep -rIn -i (same) /opt/sglang/                             -> 0 hits
grep -rIl -i 'qquestion' repo --exclude-dir=.git              -> only this artifact + ledger.md
```

SQLite (read-only URI): `part`, `message`, `session_message`, `event`, `session`, `session_input`,
`session_context_epoch`, `todo` tables searched for `%qquestion%`; `event` has 141 rows, all from
the three sessions created by this investigation (owner/orchestrator conversation at 22:24+ and
the hunt subagents). `event.data`, `part.data` for the 21:39 window contain no model-emitted
`qquestion` call.

## Defects / blockers

1. **No tool-call-level record of the `qquestion` emission exists**, because the turn failed with
   the gateway 400 before the harness persisted any tool part. The *only* surviving artifact of
   the model's output for that request is the server-side warning line E1 plus inference from
   `qwen3_coder_detector.py:91`. The raw emitted token stream and the gateway request/response
   for that turn were not captured (request metrics do contain full prompts; the metrics file
   has full `<|im_start|>` transcripts but the failing continuation is only visible as 200-OK
   requests around it).
2. **The gateway at `192.168.1.203:3456` (opencodex provider) is on a different host** and was
   not reachable for logs from this host. The `reasoning_content` 400 originates there. Whether
   the gateway itself saw/forwarded `qquestion` cannot be established locally.
3. **Causal link between `qquestion` and the 400 is unproven.** Both occur at 21:39:43 in the same
   session, and the 400 is a provider-side validation of `reasoning_content` in echoed history —
   a plausible but unverified mechanism is that the malformed continuation caused the gateway to
   reject the next echo. Stated as inference only.
4. **`/var/log/sglang/local-prod-v1.1` (107 GB)** was listed and searched with `grep -rIl`
   (case-insensitive) with a 60 s cap; it returned no hits. If a hit existed in a binary or
   unreadable file it would have been missed. `/var/log` is readable as `ubuntu` except
   `/var/log/btmp*` (2 files, login records; not relevant). sudo escalation was not needed and
   not attempted.
5. **SGLang request metrics do not record tool-call names**; they store prompts/params only
   (`tool_calls` substring appears only inside prompt text). They cannot prove or disprove the
   emission by themselves; the console warning is the authoritative record.

## Remaining claims / exclusions

Claims this investigation does NOT establish (explicitly excluded):

- That the harness "handles tool hallucination for qquestion" via a qquestion-specific code path.
  No such specific handling exists; the generic paths are the SGLang detector warning (E4) and
  the harness `ToolRegistry` unknown-tool error branch (E6, never reached).
- That `qquestion` caused the 502/400/stall symptoms elsewhere. The observed 400 is a
  `reasoning_content`-in-thinking-mode gateway rejection; a second class of failure
  (`invalid tool calls (invalid index)`) is proven and harness/gateway-side, but attribution to
  `qquestion` specifically is not proven for either.
- That any qquestion call was ever executed in the harness. It was not.
- That the qquestion warning was surfaced to the user or model. It was logged server-side only
  (the harness persisted no tool part, no error mentioning it).
- Counts in the opencode DB after 22:33 are contaminated by this hunt's own activity and by the
  owner's conversation; they are excluded as evidence of model behavior.

Open follow-ons for the orchestrator (not performed here, not authorized):
1. If the gateway host is reachable by an authorized operator, capture the gateway request/response
   for session `ses_f4eb18efeffe...` at 2026-09-17T21:39:35.93–43.93Z to see what it did with the
   malformed continuation.
2. Decide whether `qwen3_coder` should adopt the `inkling`/`SGLANG_FORWARD_UNKNOWN_TOOLS` behavior;
   the divergence is real and currently `qwen3_coder` surfaces undeclared calls while
   `hunyuan`/`gpt_oss`/`lfm2`/`pythonic`/`base` skip them.
3. Consider whether the harness should validate tool-call names before executing; E7 shows the
   harness already rejects malformed tool-call indices, so an explicit unknown-name error would
   be consistent.

## Terminal state: DONE
