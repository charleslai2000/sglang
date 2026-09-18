# FIX-PROVIDER-CONTEXT-METADATA-20260918

Status: DONE

## Task
Owner-authorized bounded defect fix: client/provider model metadata declared a context window of
400000 tokens, causing 8 deterministic HTTP 400 responses. Correct the declaration to exactly
131072 and eliminate the incorrect 400000 declaration so it cannot be used again. Server side must
not be changed (must remain at 128K / context_length=131072). No restarts, no GPU, no git mutation.

## Scope
In scope (read-only search + authorized edit):
- `~/.config/opencode/` — active OpenCode client/provider config and its backup copies in that tree
- `/usr/local/bin/switch-codex` — specified consumer/router script
- `3090-dev/deploy/conf/provider.env` and `3090-dev/deploy/bin/*` — repo deploy config
- `/etc/opencode*`, `~/.local/share/opencode/`, repo JSON/env, `/tmp/opencode` — provider registry /
  model metadata search
Out of scope / untouched: `/opt/**`, server launcher/argv, ports, auth, tier/model routing,
sampling defaults, `3090-dev/gates/**`, GGUF/tokenizer files, git.

## Result
The incorrect declaration was **`"context": 400000` inside
`~/.config/opencode/opencode.json`, under `provider.opencodex.models.*.limit`** — an OpenCode
client/provider model-metadata block (tokens; sibling `"output"` is also in tokens). It is the
local OpenCodex provider (`baseURL http://192.168.1.203:3456/v1`) used by all agent tiers.

All 8 occurrences now read exactly `"context": 131072`, and the stale 400000 copies in the same
config tree's backup files were changed consistently (no 400000 remains anywhere in
`~/.config/opencode/` JSON):

| File (role) | BEFORE | AFTER |
|---|---|---|
| `~/.config/opencode/opencode.json` (ACTIVE client/provider config) | 8× `"context": 400000` (lines 75, 97, 119, 163, 182, 201, 220, 239) | 8× `"context": 131072` at same lines |
| `~/.config/opencode/opencode.json.bak-before-gpt55-20260916T112940Z` (stale backup) | 3× at 74, 96, 118 | 3× `131072` |
| `~/.config/opencode/.bak-before-low-variant-20260917-203524/opencode.json` (stale backup) | 8× at 74, 96, 118, 162, 181, 200, 219, 238 | 8× `131072` |
| `~/.config/opencode/.bak-before-tier-rebind-20260917-202809/opencode.json` (stale backup) | 3× at 74, 96, 118 | 3× `131072` |
| `~/.config/opencode/.bak-before-topmodel-20260917-204306/opencode.json` (stale backup) | 8× at 74, 96, 118, 162, 181, 200, 219, 238 | 8× `131072` |

Model-level result in the active config (`provider.opencodex.models`):
`gpt-5.6-luna/terra/sol/public/worker/control/expert/frontier` = 131072;
`gpt-5.5` left at its pre-existing 262144 (not part of the 400000 declaration; untouched).
Nothing else changed: names, `output`, `reasoning`, `variants`, agent routing, permissions, options
are byte-identical apart from the 27 `400000→131072` substitutions.

`3090-dev/deploy/conf/provider.env` already contained the correct server value
`CONTEXT_LENGTH=131072` (line 116) and was NOT modified. No repo file was changed.

## Evidence
### BEFORE (raw)
```
$ grep -n '"context"' ~/.config/opencode/opencode.json        # before edit
75:            "context": 400000,
97:            "context": 400000,
119:            "context": 400000,
141:            "context": 262144,
163:            "context": 400000,
182:            "context": 400000,
201:            "context": 400000,
220:            "context": 400000,
239:            "context": 400000,
```
Backup files before edit (grep `400000` counts): `.bak-before-gpt55`: 74,96,118;
`.bak-before-low-variant`: 74,96,118,162,181,200,219,238;
`.bak-before-tier-rebind`: 74,96,118; `.bak-before-topmodel`: 74,96,118,162,181,200,219,238.

### AFTER (raw)
```
$ grep -n '"context"' ~/.config/opencode/opencode.json        # after edit
75:            "context": 131072,
97:            "context": 131072,
119:            "context": 131072,
141:            "context": 262144,
163:            "context": 131072,
182:            "context": 131072,
201:            "context": 131072,
220:            "context": 131072,
239:            "context": 131072,

$ grep -rIn '"context": 400000' ~/.config/opencode/ --include='*.json' | grep -v node_modules
(no output; exit 1)

$ for f in <5 files>; do printf "%s: %s\n" "$f" "$(grep -c '"context": 131072' "$f")"; done
opencode.json: 8
opencode.json.bak-before-gpt55-20260916T112940Z: 3
.bak-before-low-variant-20260917-203524/opencode.json: 8
.bak-before-tier-rebind-20260917-202809/opencode.json: 3
.bak-before-topmodel-20260917-204306/opencode.json: 8
```

### Semantics confirmation (field is a token context window)
- Sibling fields in the same `limit` object: `"output": 128000` (also tokens).
- Sibling model `gpt-5.5` uses `"context": 262144`.
- OpenCode config schema `provider.<id>.models.<id>.limit.context` is the model context window in
  tokens. The server's own env uses the token value `CONTEXT_LENGTH=131072`, matching the target.

### Syntax / validation (raw)
```
$ python3 -m json.tool <each of the 5 files> > /dev/null && echo "JSON VALID"
VALID  /home/ubuntu/.config/opencode/opencode.json
VALID  /home/ubuntu/.config/opencode/opencode.json.bak-before-gpt55-20260916T112940Z
VALID  /home/ubuntu/.config/opencode/.bak-before-low-variant-20260917-203524/opencode.json
VALID  /home/ubuntu/.config/opencode/.bak-before-tier-rebind-20260917-202809/opencode.json
VALID  /home/ubuntu/.config/opencode/.bak-before-topmodel-20260917-204306/opencode.json
```
No shell or Python file was touched, so `bash -n` / `py_compile` were not applicable.

### Parsed post-fix values (python3 json.load of active config)
```
gpt-5.6-luna   context=131072 output=128000
gpt-5.6-terra  context=131072 output=128000
gpt-5.6-sol    context=131072 output=128000
gpt-5.5        context=262144 output=32768
public         context=131072 output=128000
worker         context=131072 output=128000
control        context=131072 output=128000
expert         context=131072 output=128000
frontier       context=131072 output=128000
```

### State check
```
$ cd /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt && git status --porcelain -- .memory/phase2-hicache-design/agents/FIX-PROVIDER-CONTEXT-METADATA-20260918.md
?? .memory/phase2-hicache-design/agents/FIX-PROVIDER-CONTEXT-METADATA-20260918.md
```
No repo file was modified by this task (the active config is outside the repo). The repo already
had 16 unrelated modified/untracked entries before this task; they were left untouched.
`3090-dev/deploy/conf/provider.env` unchanged (mtime 2026-09-17 16:21, `CONTEXT_LENGTH=131072`).
sha256 of edited files:
```
97cf0f5b23019616238db7404b5f037ff15893eab5cd832c033f35191e1957ec  ~/.config/opencode/opencode.json
aab15cc1f09395947321fcb423f87416b7a465da97c058afdf94eb93015654c3  ~/.config/opencode/opencode.json.bak-before-gpt55-20260916T112940Z
f0f1f4cbe167d76b74c3ac6a5f8c25c8566b956edced3d7ee1a863f0b1703dfa  ~/.config/opencode/.bak-before-low-variant-20260917-203524/opencode.json
930033830218192e497af98771d079990fa0126b7dd20bf98975c0c7d902de8d  ~/.config/opencode/.bak-before-tier-rebind-20260917-202809/opencode.json
80d1d772b319c368f04dde7cb62bacf12aeb09e098fddbb5dd1a9b9b0bd22ff3  ~/.config/opencode/.bak-before-topmodel-20260917-204306/opencode.json
```

### Search coverage (what was checked; 400000 model-metadata hits elsewhere)
- `/usr/local/bin/switch-codex` — **does not exist on this host** (see Defects). No such script
  anywhere under `/home/ubuntu`, `/usr/local`, `/opt` (maxdepth 5).
- `/etc/opencode*` — no such path; `/etc` has no opencode provider config.
- `~/.local/share/opencode/` — no `"context": 400000` in JSON (only DB/logs/tool-output).
- `3090-dev/deploy/**`, repo `*.json`/`*.env`/`*.conf` — no `"context": 400000`; provider.env uses
  `CONTEXT_LENGTH=131072`.
- `/tmp/opencode/**` — no `"context": 400000` in JSON. Remaining literal `400000` hits there are
  unrelated source constants (`0x40000000`, mmap `0x1400000`, metrics histogram buckets) in
  sglang source trees, not model metadata.
- `/opt/sglang/**` — read-only inspection only: no `opencode.json`/provider metadata with 400000
  (only unrelated sglang source/evidence files). **Not modified.**
- `/home/ubuntu/.cache/opencode/models.json` — public models.dev registry cache (221 providers);
  contains 400000 entries only for third-party providers (e.g. databricks). It has **no
  `opencodex` key** and does not declare the local model; not modified.
- Project-level `.opencode/` / `opencode.json` at any parent of the working directory: none.

## Defects / blockers
- The directed path `/usr/local/bin/switch-codex` does not exist on this host. This did not block
  the fix because the offending declaration was located and corrected in the active client config;
  it is reported for completeness (the router script may live on another host, but the defect was
  fully fixed here).
- No blocker prevented completion.

## Remaining claims / exclusions
- The active provider metadata is fixed on this host. If a separate copy of this model metadata
  exists on another host (e.g. the gateway at 192.168.1.203), it was **NOT** changed and is outside
  this host's reach — not observed from here and not required to close this host's deterministic
  400 cause.
- Server side was not touched: `/opt/**` untouched, no launcher/argv change, no restart/signal/
  pkill/GPU lock, `CONTEXT_LENGTH=131072` in `3090-dev/deploy/conf/provider.env` unchanged.
- No restart was performed, so the fix takes effect when the OpenCode client next loads its config;
  runtime re-verification of the HTTP 400 disappearance is a separate follow-up.
- `gpt-5.5` model's pre-existing `262144` context was intentionally left unchanged (it was never
  400000).
- The unrelated 16 pre-existing repo working-tree changes were not investigated or modified.

## Terminal state: DONE
