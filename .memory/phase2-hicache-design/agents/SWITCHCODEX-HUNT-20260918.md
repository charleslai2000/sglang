# SWITCHCODEX-HUNT-20260918

Status: DONE
Task: Exhaustively locate `switch-codex` on this host and resolve the EXISTS / NOT-EXISTS
contradiction; inventory any context/model declarations it contains; enumerate all remaining
context-window declarations reachable from this host; determine the authoritative component on the
request path; probe gateway reachability read-only.
Owner: orchestrator (SWITCHCODEX-HUNT-20260918 dispatch). Artifact owner: this file only.

## Scope

Host under test: `sglang-build` (VM 2500), `192.168.20.250`, Ubuntu 24.04, kernel 6.8.0-139.
Read-only forensic search of the whole filesystem (root sudo available), content searches for
`publish_deepseek_tiers`, `switch-codex`, `qwen35-9b-local`, `deepseek-flash`,
`deepseek/deepseek-flash`; enumeration of context-window declarations in
`~/.config/opencode/` (incl. all backups), `~/.local/share/opencode/`, `/usr/local/{bin,share}`,
`/etc`, `/opt`, `/tmp/opencode`, `~/.cache/opencode`; identification of the request path for the
active `opencodex` provider; at most 2 read-only HTTP GETs against `192.168.1.203:3456`.
Constraints honored: no edits (except this artifact), no service ops/signals/GPU, no git mutation,
no POSTs, no auth attempts.

## Result

### 1. switch-codex: NOT-EXISTS on this host (definitive)

No file named `switch-codex*` exists anywhere on this host's root filesystem. `sudo -n` worked
(`sudo -n true` → rc 0), so this is not a permission-limited conclusion. Coverage:

| Search | Result |
|---|---|
| `ls -la /usr/local/bin/` | only `opencode` (185,989,248 B), `nsys`/`nsys-ui` symlinks — no switch-codex |
| `command -v switch-codex` / `type -a` | rc=1; "not found" |
| `sudo -n find / -xdev -name 'switch-codex*' -print` (whole root fs, root) | 0 hits, find exit 0 |
| `find /home /opt /srv /root /etc /usr/local /var` (non-root, same) | 0 hits |
| `find /home /usr/local /opt /etc /var /srv /root /tmp /usr/share /usr/lib /snap /mnt /media` | 0 hits |
| `sudo -n find / -xdev -iname '*switch*codex*'` | 0 hits (only this artifact name matched in a later iname scan because of its own filename) |
| `find /boot /boot/efi /dev/shm /run/user` (non-xdev mounts) | 0 hits, incl. any `*codex*` name |
| `sudo -n grep -rIl 'publish_deepseek_tiers' /` (whole fs) | hits ONLY in logs/session records, no script (see Evidence) |
| `sudo -n grep -rIl 'switch-codex' /home /usr /opt /etc /var /srv /root /tmp` | hits ONLY in logs/session records |
| rc/alias/function files (`/etc/profile*`, `/etc/bash.bashrc`, `~/.bashrc`, `~/.profile`, `~/.bash_aliases`, root shell files) | 0 references |
| systemd / cron units | 0 references |
| git history (`git log --all`, `git rev-list --all --objects`) in repo | 0 references |
| `lsof +L1` (deleted-but-open files), `lsof | grep switch`, `/proc/*/root/...` scan | no process holds it; all process roots = `/` (no container overlay) |
| `debugfs` raw directory listing of `/usr/local/bin` (inode 50791) | exactly 5 entries: `.`, `..`, `opencode` (inode 1774), `nsys` (3557), `nsys-ui` (3625). No unlinked/deleted `switch-codex` entry |
| `~/.local/share/Trash`, editor swap/tilde backups | non-existent / 0 hits |
| `/root/.bash_history` | does not exist (root interactive history unavailable — recorded limitation, not proof of absence) |
| `last -x` / `lastlog` root logins | no root console logins; root ops only via sudo (auth.log) |

`/var/log/auth.log` (covers 2026-09-15 19:14 → present) plus rotated `auth.log.1` (2026-08-29 →
2026-09-05) were scanned: the ONLY ever-observed write into `/usr/local/bin` is
`/usr/local/bin/opencode` (tee + chmod 0755 + chown root:root, 2026-09-15 19:23:45–47). No
`switch-codex` ever appears as a sudo command, target, or path in either log rotation.

**Why the contradictions arose.** The owner's claim exists on this host only as *pasted text*:

- `~/.local/state/opencode/prompt-history.jsonl:26` — verbatim owner paste:
  `"做了什么" ... "- /usr/local/bin/switch-codex 加了共享 publish_deepseek_tiers()；local 模式发布 5 个 tier combo，只有 worker 不同：worker → local/qwen35-9b-local, deepseek/deepseek-flash（failover）..."`.
- Same text was echoed through a prior dispatch brief in `opencode.db` (224 `switch-codex` text
  hits) and `~/.local/share/opencode/log/opencode.log` (75+ references, all as prompt text).
- The prior `FIX-PROVIDER-CONTEXT-METADATA-20260918` task searched this host, found nothing, and
  reported "does not exist on this host". This hunt confirms that statement as TRUE for this host.

The pasted claims describe host-local facts (`VM 2500` sglang change + `switch-codex` edit) that
were **performed on a different machine** (owner's workstation / pc01 / the `dev-codex` pod — see
Remaining claims). Session history on this VM proves cross-host session sharing: e.g.
`opencode.log:135-138` shows a prior session operating on `/home/dev-codex/workspaces/3rdparty/...`
paths, which do not exist here. The file does not exist on this host; it cannot be inventoried here.

### 2. `switch-codex` inventory (Part 2)

N/A — file absent. No context/model declaration can be attributed to it on this host. No
`400000` was found in any file whose path contains `switch` or `codex`.

### 3. Remaining context-window declarations reachable from this host (Part 3)

All `"context"` values in `~/.config/opencode/` (active + 4 backup copies; 30× 131072, 4× 262144,
**0× 400000**; JSON-valid; active sha256 `97cf0f5b…57ec` matches the fix task's attested hash):

| File | 131072 | 262144 | 400000 |
|---|---|---|---|
| `~/.config/opencode/opencode.json` (ACTIVE) | 8 | 1 (`gpt-5.5`, line 141) | 0 |
| `opencode.json.bak-before-gpt55-20260916T112940Z` | 3 | 0 | 0 |
| `.bak-before-tier-rebind-20260917-202809/opencode.json` | 3 | 1 | 0 |
| `.bak-before-topmodel-20260917-204306/opencode.json` | 8 | 1 | 0 |
| `.bak-before-low-variant-20260917-203524/opencode.json` | 8 | 1 | 0 |

- **No `400000` declaration remains anywhere in `~/.config/opencode/`** (tree-wide regex count: 0).
- The only declaration **larger than the server's 131072** in the config tree is `gpt-5.5`
  `"context": 262144` (`opencode.json:141` and 3 backups). It is **client-side metadata only and is
  not on the request path**: no agent tier references `gpt-5.5` (all tiers use
  luna/terra/sol/public/worker/control/expert/frontier, all at 131072).
- Other trees:
  - `/usr/local/bin`, `/usr/local/share`, `/etc` (json/jsonc/conf/env), `/tmp/opencode` JSON:
    **no** `"context":` model-metadata declarations at all. `/tmp/opencode` hits are unrelated:
    `nokey.json` (Sep 17 13:09) is a captured `/v1/models` response advertising
    `max_model_len: 262144` from an earlier server run — a historical snapshot, not config;
    `chain.json` `"limit": "39321"` is a freeze-bundle constraint string.
  - `/opt`: no `opencode.json`, no `"context": 400000|262144|131072` model metadata (grep → 0).
  - `/home/ubuntu/.local/share/opencode/`: only DB/log/tool-output (no JSON configs); DB contains
    no `"context": 400000` literal (0 hits) and no opencodex registry declarations.
  - `/home/ubuntu/.cache/opencode/models.json`: models.dev public registry cache (221 providers,
    no `opencodex` key). It contains many 400000 entries (qiniu-ai, nano-gpt, vercel, openai, poe,
    openrouter, …) — public third-party provider metadata, **not** local provider metadata and not
    reachable by the `opencodex` provider config. It cannot affect requests to the gateway.
- Server side (live): SGLang pid 1654119 (started 21:18Z) argv contains
  `--max-total-tokens 524288 --context-length 131072`; `server.console.log:673` →
  `context_len=131072`. `3090-dev/deploy/conf/provider.env:116` → `CONTEXT_LENGTH=131072`.

**Any remaining >131072 declaration reachable on the request path?** Only `gpt-5.5` 262144 in the
active config — client-side, unused by every agent tier, and the model is never selected by
`default_agent`/routing. Within the actually-used request path: none.

### 4. Authoritative component for the context limit (Part 4)

Active provider block (`~/.config/opencode/opencode.json:63-256`):

```
"provider": {
  "opencodex": {
    "npm": "@ai-sdk/openai-compatible",
    "name": "Local OpenCodex",
    "options": {
      "baseURL": "http://192.168.1.203:3456/v1",     # line 68
      "apiKey": "{file:/home/ubuntu/.opencodex-api-key}"  # line 69
    },
    "models": { ... 9 models; all agent-used models limit.context=131072 ... }
```

- **All agent tiers** (orchestrator/architect/coder/context-manager/debugger-deep/devops/
  devops-executor/doc-writer/domain-analyzer/executor/external-*/frontend/reviewer*/scout/
  task-manager/test-runner/tester) route through **one host**: `192.168.1.203:3456`. Every request
  from this machine goes to that gateway (`file:line: opencode.json:68`); the gateway then routes
  to backends (per prior campaign records: `local/*` → this VM's SGLang, `deepseek/*` → upstream).
- Authoritativeness: OpenCode's `limit.context` is **client-side budgeting metadata** (compaction/
  token planning), not an enforcement mechanism; the **gateway** is authoritative for model-id
  routing, and the **SGLang server** enforces the hard cap (`context_length=131072`, live-verified
  on pid 1654119). A client-side value larger than the server cap leads the client to build
  requests the server/serving path rejects — consistent with the reported deterministic 400.
  Assigning the exact 8×400 responder (gateway vs SGLang) is owned by `HTTP400-FORENSICS-20260918`;
  from this host the only verifiable facts are: client now declares 131072 for all used models,
  server enforces 131072, gateway registry is not inspectable (auth, see below).

### 5. Gateway reachability (Part 5)

- `curl -sS -m 5 -o /dev/null -w '%{http_code}' http://192.168.1.203:3456/v1/models`
  → **HTTP 401** (curl rc 0). Second GET (final allowed) returned:
  `{"error":{"message":"opencodex API key required","type":"authentication_error","code":"invalid_api_key"}}`
- **Reachable** at TCP/HTTP level from this host. **Registry NOT inspectable without auth**; per
  constraints no auth attempt was made. Therefore the gateway's advertised model ids/limits remain
  unverifiable from this host.
- Proxy: `/etc/environment` sets `http_proxy=https_proxy=http://192.168.1.203:8118` but
  `no_proxy` (line 6) includes `192.168.1.203`, `192.168.20.250`, and `127.0.0.1`; shell env at
  probe time had the same. **No proxy interference**; the probe went direct.
- Note: `/home/ubuntu/.opencodex-api-key` exists (49 B, mode 600) — not used, per constraints.

## Evidence

Raw, trimmed where noted. Full outputs are in the OpenCode tool-output store
(`~/.local/share/opencode/tool-output/`) as produced by this session.

**E1 — /usr/local/bin and PATH (name absence, not permission-limited)**
```
$ command -v switch-codex; type -a switch-codex
(no output; rc=1)   # "type: switch-codex: not found"
$ ls -la /usr/local/bin/
-rwxr-xr-x 1 root root 185989248 Sep 15 19:23 opencode
lrwxrwxrwx 1 root root        22 Mar  1  2025 nsys -> /etc/alternatives/nsys
lrwxrwxrwx 1 root root        25 Mar  1  2025 nsys-ui -> /etc/alternatives/nsys-ui
$ sudo -n true; echo rc=$?
rc=0                # sudo -n available; absence is not a sudo limitation
```

**E2 — Whole-filesystem find as root; find exit status captured**
```
$ sudo -n sh -c "find / -xdev -name 'switch-codex*' -print 2>/dev/null; echo FIND_RC=$?"
FIND_RC=0
$ sudo -n find / -xdev \( -name 'switch*' -o -name '*codex*' -o -name 'Codex*' \) ... 
(only OS packages: switcheroo-control, switch_root, switchtec, switchdev, linux headers, etc.)
```

**E3 — debugfs raw directory listing of /usr/local/bin (proves no deleted/unlinked entry)**
```
$ sudo -n debugfs -R 'ls -l /usr/local/bin' /dev/sda1
  50791   40755 (2)      0      0    4096 15-Sep-2026 19:23 .
  50775   40755 (2)      0      0    4096 29-Aug-2026 15:45 ..
   1774  100755 (1)      0      0   185989248 15-Sep-2026 19:23 opencode
   3557  120777 (7)      0      0      22  1-Mar-2025 07:32 nsys
   3625  120777 (7)      0      0      25  1-Mar-2025 07:54 nsys-ui
```

**E4 — Content search for the function and the tokens (whole fs, root)**
```
$ sudo -n grep -rIl 'publish_deepseek_tiers' / --exclude-dir=proc --exclude-dir=sys --exclude-dir=dev
/var/log/auth.log
/tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969/sglang-request-metrics-20260917_22.log
/tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969/sglang-request-metrics-20260917_21.log
/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/ledger.md
/home/ubuntu/.local/share/opencode/log/opencode.log
/home/ubuntu/.local/state/opencode/prompt-history.jsonl
# The metrics-log "hits" are LLM request payload echoes (prompt text rendered through the model),
# not a script: a 7-count of the token occurs inside `"text":"...<tool_response>...` captures.
$ sudo -n grep -rIl 'switch-codex' /home /usr /opt /etc /var /srv /root /tmp
... (same log/session-only list; no executables, no configs) ...
```

**E5 — The owner's claim as it exists on this host (verbatim, prompt-history.jsonl:26, abridged)**
```
"- /usr/local/bin/switch-codex 加了共享 publish_deepseek_tiers()；local 模式发布 5 个 tier combo，
只有 worker 不同：worker → local/qwen35-9b-local, deepseek/deepseek-flash（failover），其余四档与
deepseek 完全一致。deepseek 模式 dry-run 与旧脚本逐行相同（21 行，无回归）。"
```
Prior in-flight brief containing the same framing (ledger.md:8687-8691): the previous task flagged
`/usr/local/bin/switch-codex` as "在本机不存在", hypothesizing "该脚本…在另一台主机上（很可能是网关
192.168.1.203 或你的工作站）". This hunt confirms that: on this host it is text, not a file.

**E6 — auth.log: every sudo event mentioning /usr/local (the only write into /usr/local/bin ever)**
```
$ sudo -n grep -n '/usr/local' /var/log/auth.log | grep -v '<our-own this-hunt commands>'
131: 2026-09-15T19:23:45 ... COMMAND=/usr/bin/tee /usr/local/bin/opencode
134: 2026-09-15T19:23:47 ... COMMAND=/usr/bin/chmod 0755 /usr/local/bin/opencode
137: 2026-09-15T19:23:47 ... COMMAND=/usr/bin/chown root:root /usr/local/bin/opencode
$ sudo -n zgrep -i 'switch-codex' /var/log/auth.log.1 /var/log/syslog.1   # (none)
```
Coverage: `auth.log` 2026-09-15T19:14 → present; `auth.log.1` 2026-08-29 → 2026-09-05.

**E7 — Active provider config (opencode.json, verbatim key lines)**
```
68:        "baseURL": "http://192.168.1.203:3456/v1",
69:        "apiKey": "{file:/home/ubuntu/.opencodex-api-key}"
75/97/119/163/182/201/220/239:  "context": 131072,
141:        "context": 262144,    # gpt-5.5 — unused by all agent routing
```
sha256 `97cf0f5b23019616238db7404b5f037ff15893eab5cd832c033f35191e1957ec` (active) matches
`FIX-PROVIDER-CONTEXT-METADATA-20260918` evidence. Tree-wide `400000` count in
`~/.config/opencode/`: **0**.

**E8 — Server-side cap (live process + console)**
```
$ sudo -n tr '\0' ' ' < /proc/1654119/cmdline
... --max-total-tokens 524288 --context-length 131072 --max-running-requests 8 ...
$ grep context_len /opt/sglang/opencodex-provider-run/server.console.log:673
max_total_num_tokens=524288, ..., context_len=131072, available_gpu_mem=1.92 GB
3090-dev/deploy/conf/provider.env:116  CONTEXT_LENGTH=131072
```

**E9 — Gateway probe (2 read-only GETs total)**
```
$ curl -sS -m 5 -o /dev/null -w 'GATEWAY_HTTP=%{http_code}\n' http://192.168.1.203:3456/v1/models
GATEWAY_HTTP=401
$ curl -sS -m 5 -i http://192.168.1.203:3456/v1/models | head
HTTP/1.1 401 Unauthorized
Content-Type: application/json
...
{"error":{"message":"opencodex API key required","type":"authentication_error","code":"invalid_api_key"}}
$ echo $http_proxy / $no_proxy
http://192.168.1.203:8118 ; ...no_proxy includes 192.168.1.203, 192.168.20.250, 127.0.0.1...
```

**E10 — models.dev cache identification (public registry, not local provider metadata)**
```
$ python3: models.json providers=221, 'opencodex' in registry = False
examples: ('/openai/models/openai/gpt-5/limit/context', 400000),
          ('/nano-gpt/.../gpt-5*.limit/context', 400000), ... 5555 entries >=200000 overall
```

## Defects / blockers

1. **Contradiction resolved against the owner's implied host.** The claim "switch-codex exists and
   was recently modified" is not true of `sglang-build` (this VM). It is only present here as
   pasted prompt text. No local evidence of the file, its backups, or an invocation path.
2. **Cannot inventory what is not here.** Part 2 is vacuous on this host by evidence, not by
   speculation.
3. **Gateway registry unauditable from here** (HTTP 401; auth attempts prohibited by the brief).
   Any gateway-side model metadata >131072 (if it exists) remains unverified. This is the largest
   remaining blind spot for "400 fully fixed".
4. **Runtime re-verification not performed** (read-only constraint): we know config now declares
   131072, but no request was issued to confirm the 400 stopped. A live client reload + request
   test remains a separate follow-up.
5. **Root interactive history unavailable** (`/root/.bash_history` absent; no root logins ever) —
   cannot audit root's own shell history; mitigated by full sudo auth.log coverage of any
   privileged write into `/usr/local/bin`.
6. **Potential same-name artifact on other hosts** (pc01 / dev-codex pod / owner workstation) is
   outside this host's reach; if its copy still declares 400000 (or routes `local/*` tiers), the
   end-to-end 400 story may differ there.

## Remaining claims / exclusions

- **Established facts:** no `switch-codex*` path or content anywhere on this host (root-level
  whole-fs search; raw ext4 dir listing; no rc/cron/systemd/git/process references); zero `400000`
  in `~/.config/opencode/`; active provider = `opencodex` @ `http://192.168.1.203:3456/v1` for all
  agent tiers; server cap 131072 live; gateway TCP-reachable, 401 without auth; no proxy
  interference.
- **Hypotheses (not established):** the owner's `switch-codex` edit happened on a different host —
  most plausibly the machine the owner SSHes from / pc01 / the `dev-codex` pod; that machine may
  hold the only live copy. This is supported only by (a) cross-host session path evidence
  (`/home/dev-codex/...`) and (b) absence here, not by direct observation of that host.
- **Exclusions:** I did not attempt to mine/parse the 224 `switch-codex` text occurrences in
  `opencode.db` beyond confirming they are conversation records; I did not read the API key; I did
  not POST anywhere; I did not verify the gateway's routing table; I did not check other hosts.
- **Only remaining local declaration >131072:** `gpt-5.5 "context": 262144` in the active
  opencode.json (line 141; plus 3 stale backups) — client-side, unused by every agent tier, not on
  the serving path. If the 400 forensics later shows a 400 can be triggered by any *available*
  model selection, this value should be reviewed; unilaterally it is not the current defect.
- **Ownership note:** this artifact is the exclusive deliverable of this task; no other file was
  created or modified (read-only hunt; no service/GPU/git operations; exactly 2 GETs, both
  read-only, both to the same endpoint).

## Terminal state: DONE
