# PROD-BIND-DIAG-20260918 — SGLang prod bind host diagnosis (READ-ONLY)

Task ID: PROD-BIND-DIAG-20260918
Role: devops (read-only diagnosis; no service actions, no config edits)
Repo: /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt (branch 3090-24g-opt, HEAD 910e5a01c0)
Host clock at diagnosis: 2026-09-17T21:05–21:07Z (UTC, `date -Is`)

## Result

**VERDICT: CONFIRMED — the production SGLang is loopback-only (`--host 127.0.0.1` hard-coded in the frozen launcher), so
192.168.20.250:30000 is unreachable. The causal attribution "the 03:08 restart changed it to loopback" is REFUTED:
every frozen production launcher (v1, v1.1, v1.1.2, v1.2, v1.2.1) has always hard-coded 127.0.0.1; the external
listener on :30000 was the separate opencodex DEV provider, which was moved to :30001 at 16:21:19Z (commit
7d08fb26f8) and then stopped at 16:30:12Z. Fix is FREEZE-REQUIRING (repo template + audit-allowance change + new
v1.2.2 freeze + prod restart). Not blocked by any host firewall.**

Corollaries:
- 192.168.20.250 IS an address of THIS host (`eth0`), hostname `sglang-build` = "VM 2500".
- No host firewall is filtering :30000; "Connection refused" is the expected signature of a loopback-only bind.
- The launcher audit (`audit_launcher.py`) fails closed on any `--host` value change vs the v1.1 reference; a bind
  change must be explicitly declared there before a new freeze can pass.

## Scope

In scope: read-only host/config/log/audit inspection to answer A–G of the dispatch; write only this artifact.
Out of scope (explicitly not performed): restart/stop/start/signal of any service, pkill, GPU-lock touch, any file
edit, git mutation, writes to /opt /data /var/log /tmp/opencode state, launching anything.

---

## A. Host identity

Observed facts:

```
$ hostname
sglang-build
$ hostname -I
192.168.20.250
$ ip -4 addr show
1: lo:    inet 127.0.0.1/8 scope host lo
2: eth0:  inet 192.168.20.250/24 brd 192.168.20.255 scope global eth0   (altname enp0s18)
$ ip -4 addr show eth0 | grep inet
    inet 192.168.20.250/24 brd 192.168.20.255 scope global eth0
```

**192.168.20.250 is an address of THIS host** (interface `eth0`). Corroborated by repo memory:
`.config/opencode/.bak-before-pc01-sync-20260918/AGENTS.md:158` — "`sglang-build` (VM 2500, `192.168.20.250`)".
So the owner's "VM 2500" is this machine; the gateway's target is this machine.

Current listeners (`ss -ltnp`):

```
LISTEN 0 2048  127.0.0.1:30000   0.0.0.0:*   users:(("python",pid=1602808,fd=68))
LISTEN 0 4096  *:36971           *:*         users:(("sglang::schedul",pid=1603222,fd=73))
LISTEN 0 4096  0.0.0.0:22        0.0.0.0:*
```

- `127.0.0.1:30000` → LISTEN, pid 1602808 (prod). No `0.0.0.0:30000`, no `192.168.20.250:30000`. → nothing external.
- Incidental observation (not the reported blocker): the prod server's scheduler child (pid 1603222,
  `sglang::scheduler`, ppid 1602808) listens on the wildcard address at `*:36971`. This socket is NOT controlled by
  `--host`; flag for separate review (see Security note D/G).

Current prod cmdline, verbatim (`pgrep -af sglang.launch_server`):

```
1602808 /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 127.0.0.1 --port 30000 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 524288 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --enable-hierarchical-cache --hicache-write-policy write_back --hicache-storage-backend extent --hicache-storage-prefetch-policy wait_complete --hicache-size 32 --enable-ready-horizon --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir /tmp/opencode/prod-service-20260917/logs/prod-20260917T190831Z-1602589 --disable-prefill-cuda-graph
```

Process tree (`ps -o pid,ppid,etime,cmd`): 1602781 (supervisor, ppid 1) → 1602808 (server) → 1603222 (scheduler).
Loopback liveness, read-only: `curl http://127.0.0.1:30000/health` → 200; `/v1/models` → `{"data":[{"id":"/data/models/qwen35-9b-w4a16",...}]}`.

## B. WHERE the bind host is configured (decisive)

The runtime `--host` comes from the **frozen tree launcher**, which is rendered from the repo template. The scaffold
has no host knob; `conf/service.env` and `bin/start.sh`/`bin/supervise.sh`/`bin/common.sh` only *health-check*
127.0.0.1 and pass SGLANG_PORT/PROFILE/RUN_ID/L3_ROOT/LOG_DIR to the tree launcher
(`bin/supervise.sh:43-50`).

The exact line that becomes `--host`:

- Repo template (source of truth for the freeze): `3090-dev/tools/freeze/templates/launch.sh.tmpl:146`
  `  --host 127.0.0.1 --port "$PORT"`
- Frozen tree (installed, read-only): `/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh:146`
  `  --host 127.0.0.1 --port "$PORT"`
  sha256: `38487942de63cb56249dae5080d2caef281364dcbac6c92ac53b1ff916672914`
  (matches `manifest/identity.json` `LAUNCHER_HASH` — verified read-only.)
- All other frozen prod trees are identical in kind:
  `/opt/sglang/local-prod-v1.2-candidate/launcher/launch.sh:146`,
  `/opt/sglang/local-prod-v1.1.2-candidate/launcher/launch.sh:140`,
  `/opt/sglang/local-prod-v1.1-candidate/launcher/launch.sh:46`,
  `/opt/sglang/local-prod-v1/launcher/launch.sh:46` — each `--host 127.0.0.1 --port "$PORT"`.
- Frozen `src/3090-dev/tools/freeze/templates/launch.sh.tmpl:146` is the same line (the tree carries its own copy).

Repo `3090-dev/` grep (`--host|PROD_HOST|BIND_HOST|HOST=|0.0.0.0|127.0.0.1`; evidence/harness noise elided):

| file:line | content |
|---|---|
| `3090-dev/tools/freeze/templates/launch.sh.tmpl:146` | `  --host 127.0.0.1 --port "$PORT"` |
| `3090-dev/deploy/conf/provider.env:72` | `BIND_HOST="192.168.20.250"` (DEV provider, port 30001) |
| `3090-dev/deploy/bin/provider-common.sh:251` | `    --host "$BIND_HOST" --port "$BIND_PORT"` |
| `3090-dev/deploy/bin/provider-common.sh:161,227,236,344` | BIND_HOST used for port-free probe, health, state, log |
| `3090-dev/direct-launch-gate3-parked.sh:59` | `  --host 0.0.0.0 --port "${SGLANG_PORT:-8024}" \` (parked gate harness, port 8024) |
| `3090-dev/deploy/bin/supervise.sh:126,131`, `status.sh:19` | health checks against `127.0.0.1` |
| `3090-dev/gates/production/gate_common.py:1449` | gate harness `"--host", "127.0.0.1"` |
| `3090-dev/handover-22151.md:17,22` | historical note: port 8024, `0.0.0.0` listen (old bring-up) |

`PROD_HOST`: **ABSENT** (no hits anywhere in `3090-dev/`).

Scaffold `/tmp/opencode/prod-service-20260917/` grep (`--host|PROD_HOST|BIND_HOST|HOST=|0.0.0.0|127.0.0.1`):

| file:line | content |
|---|---|
| `bin/supervise.sh:126,131` | health poll `http://127.0.0.1:$PORT/health` |
| `bin/status.sh:19` | health poll `http://127.0.0.1:$port/health` |
| `bin/common.sh:226` | `s.bind(("127.0.0.1", int(sys.argv[1])))` (port-free probe) |

No `--host` in the scaffold at all. **The scaffold cannot change the bind host.**

**Answer: the value is HARD-CODED in the FROZEN tree's launcher (and in the template used to render it). It is not
supplied by any env var or scaffold file, so it cannot be changed without a repo change + a new freeze.** The only
repo layer that passes `--host` from configuration is the *separate DEV provider* path
(`3090-dev/deploy/bin/provider-common.sh:251` + `conf/provider.env:72`), which serves a different deploy tree
(`/opt/sglang/opencodex-provider-2d4e33a832`, commit `2d4e33a832`) on port 30001 — not the frozen production identity.

Frozen launcher host line verbatim and sha256 (as requested):

```
$ grep -n -- "--host" /opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh
146:  --host 127.0.0.1 --port "$PORT"
$ sha256sum /opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh
38487942de63cb56249dae5080d2caef281364dcbac6c92ac53b1ff916672914  /opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh
```

## C. What changed at "2026-09-18 03:08" / "2026-09-17 21:13–21:16"

Time-base fact: this host runs UTC; owner-cited times are only consistent as **UTC+8 (CST)**. Two independent
timestamp matches:
- 03:08:31 CST 09-18 == 19:08:31Z 09-17 → scaffold `supervisor.log` `[19:08:31] canonical GPU lock ACQUIRED`.
- 21:13–21:16 CST 09-17 == 13:13–13:16Z 09-17 → opencodex provider request metrics first record 13:11:19Z.

(That timezone mapping is an inference, stated as such; every host-scaffold provider timestamp below is UTC.)

Scaffold start records (all four; from `logs/*/supervisor.log` + `state/runs/prod.run` + `state/pids/*`):

| run id | supervisor start | argv / host | outcome |
|---|---|---|---|
| `prod-20260917T162230Z-1480769` | 16:22:31Z | v1.1.2 tree launcher (host would be 127.0.0.1) | FATAL "runtime PYTHONPATH not inside tree" (rc=1); never bound |
| `prod-20260917T182323Z-1596154` | 18:23:23Z | v1.2 tree launcher; pid 1596407; host 127.0.0.1 | UP 18:25:45Z; stopped 18:39:08Z |
| `prod-20260917T183937Z-1600690` | 18:39:37Z | v1.2.1 tree launcher; pid 1600908; host 127.0.0.1 | UP 18:41:53Z; stopped 19:07:42Z |
| `prod-20260917T190831Z-1602589` | 19:08:31Z | **current** pid 1602808; argv verbatim in A; host 127.0.0.1 | UP 19:10:38Z; `started_at_utc=2026-09-17T19:10:38Z` |

There is **no literal "03:08" timestamp record** (ABSENT in local-UTC form); the newest start record is
`prod-20260917T190831Z-1602589` (19:08:31Z lock, 19:10:38Z ready), which maps to owner 03:08–03:10 CST. The
`gpu-owner.json` confirms the live holder: pid 1602808, port 30000, tree v1.2.1, state "serving".

The 21:13–21:16 (CST) working window — evidence found: the **opencodex DEV provider**, not the frozen production
tree, was bound externally on :30000:

```
$ grep -n "Uvicorn running" /opt/sglang/opencodex-provider-run/server.console*.log
server.console.20260917T132714Z.log:684:[2026-09-17 12:59:03] INFO: Uvicorn running on http://192.168.20.250:30000
server.console.20260917T132714Z.log:1485:[2026-09-17 13:26:24] INFO: Uvicorn running on http://192.168.20.250:30000
server.console.20260917T133101Z.log:684:[2026-09-17 13:28:50] INFO: Uvicorn running on http://192.168.20.250:30000
server.console.20260917T133853Z.log:684:[2026-09-17 13:32:33] INFO: Uvicorn running on http://192.168.20.250:30000
server.console.20260917T144717Z.log:684:[2026-09-17 13:40:27] INFO: Uvicorn running on http://192.168.20.250:30000
server.console.20260917T153558Z.log:683:[2026-09-17 14:48:53] INFO: Uvicorn running on http://192.168.20.250:30000
server.console.20260917T162153Z.log:683:[2026-09-17 15:37:31] INFO: Uvicorn running on http://192.168.20.250:30000
server.console.20260917T162639Z.log:683:[2026-09-17 16:23:33] INFO: Uvicorn running on http://192.168.20.250:30001
server.console.log:683:[2026-09-17 16:28:17] INFO: Uvicorn running on http://192.168.20.250:30001
```

Request metrics prove HTTP traffic in the owner's window: first `request_received_ts` decodes to
`Thu Sep 17 13:11:19 UTC 2026`, last activity 13:43:41Z (`/opt/sglang/opencodex-provider-run/verify/metrics/
sglang-request-metrics-20260917_13.log`). The provider was stopped at 16:30:12Z
(`provider.state`: `"port": 30001, "health": "down", "note": "stopped"`).

Git history for the config change (read-only):

```
$ git log --format='%h %aI %s' -6 -- 3090-dev/deploy/conf/provider.env
7d08fb26f8 2026-09-17T16:21:19+00:00 fix(deploy): separate DEV provider from production port
116afefbbe 2026-09-17T14:50:15+00:00 feat(deploy): serve the measured 128K-C8 profile on :30000
b11b9b5101 2026-09-17T14:08:42+00:00 revert(deploy): AUTH OFF per owner ruling; drop API key from launch path
ab59311dcc 2026-09-17T12:55:18+00:00 feat(3090-dev): add pinned DEV provider lifecycle scripts (L3 off, auth on)
```

**Loopback is NOT a new regression.** The frozen production launcher has hard-coded `127.0.0.1` in every version
(v1, v1.1, v1.1.2, v1.2, v1.2.1), and every scaffold prod launch (18:23Z, 18:39Z, 19:08Z) was loopback-only. The
externally reachable :30000 existed because the DEV provider held it (12:59Z–15:37Z, then stopped/moved). The
19:08:31Z prod restart (owner 03:08 CST) did not "change" any bind; it simply (re)started the always-loopback
production process after the external listener had already moved to :30001 (16:21Z commit; 16:23:33Z first 30001
bind) and been stopped (16:30:12Z).

## D. Firewall / exposure facts (read-only)

```
$ ufw status                          → ERROR: You need to be root to run this script
$ sudo -n ufw status verbose          → Status: inactive
$ systemctl is-active ufw; is-enabled → active; enabled   (service up, firewall inactive)
$ sudo -n iptables -S                 → -P INPUT ACCEPT / -P FORWARD ACCEPT / -P OUTPUT ACCEPT   (no rules)
$ sudo -n nft list ruleset | wc -l    → 0
```

- **No host firewall filtering :30000.** `iptables`/`nftables` hold no rules; ufw is inactive. Therefore:
  - The observed "Connection refused" from pc01 is fully explained by the loopback-only bind (kernel sends RST for
    192.168.20.250:30000 because nothing listens there). A host firewall would normally produce timeouts, not refusal.
  - A future `0.0.0.0` (or `192.168.20.250`) bind would **not** be blocked by a local firewall.
  - Cannot determine from this host whether anything upstream (pc01's route, its proxy at 192.168.1.203:8118, or an
    inter-VLAN firewall) filters traffic; no evidence of one, but out of observable scope here.
- Proxy note: `/etc/environment` sets `http_proxy=http://192.168.1.203:8118` with `no_proxy` covering
  `192.168.0.0/16` including 192.168.20.250, so this host's own clients bypass the proxy for :250. The gateway
  host's proxy setup is not visible here.

Security note — AUTH OFF (owner ruling for the private LAN):
- Current prod argv contains **0** `--api-key` occurrences (`tr '\0' '\n' < /proc/1602808/cmdline | grep -c -- "--api-key"` → `0`).
- The frozen launcher passes no `--api-key` (launcher lines 143-171); the audit declares it forbidden
  (`audit_launcher.py:66 FORBIDDEN_SERVING_TOKENS = frozenset({"--api-key"})`).
- The DEV provider path also passes no key (`provider-common.sh:291-293` comment; provider.env:12-16).

## E. Harness/firewall interaction (freeze audit)

`3090-dev/tools/freeze/pysrc/audit_launcher.py` — serving-profile firewall (check 4), read verbatim:

- Declared allowance (lines 53-60):
  - `PRODUCTION_REQUIRED_SERVING_TOKENS = frozenset({"--context-length","131072","--max-running-requests","8","--max-mamba-cache-size","48"})` (53-57)
  - `PRODUCTION_REQUIRED_SERVING_REPLACEMENTS = {"65536": "524288"}` (58-60)
  - `FORBIDDEN_SERVING_TOKENS = frozenset({"--api-key"})` (66)
- Comparison logic (lines 150-190): the rendered launcher's token list after `sglang.launch_server`
  (`serving_flags()`, lines 83-95, which keeps `--host` and its value as separate tokens) is compared **exactly**
  to the reference launcher (v1.1):
  - `flags != ref_flags` → compute `only_new` / `only_ref` (160-162)
  - `_allowed = PRODUCTION_REQUIRED_SERVING_TOKENS | replacements.values()` (168)
  - `unapproved_new = [t for t in only_new if t not in _allowed]` (169)
  - `unapproved_dropped = [t for t in only_ref if t not in sub]` (170)
  - any of these → **failure** (182-190); exit 1 (audit) → `launcher-repin.sh` exit 22.

Classification of `--host`:
- `--host` is not in the required-token set, not in the forbidden set, and not explicitly listed anywhere.
  It is **value-pinned transitively by the exact-diff against the v1.1 reference launcher**.
- Changing `127.0.0.1` → `0.0.0.0` (or → `192.168.20.250`) produces
  `only_new=["0.0.0.0"]` (or `["192.168.20.250"]`) and `only_ref=["127.0.0.1"]`; neither new token is in
  `_allowed`, and `"127.0.0.1"` is not a replacement key → **unapproved_new + unapproved_dropped → audit FAIL.**
- `launcher-repin.sh:37` fixes the reference to `/opt/sglang/local-prod-v1.1-candidate/launcher/launch.sh`
  (immutable, itself `127.0.0.1`); repin runs the audit at lines 116-121 and dies `exit 22` on failure. The renderer
  substitutes only `@@TREE@@/@@IDENTITY@@/@@TREE_NAME@@/@@SRC_STREAM_SHA256@@` (88-104) — **no host token exists**.
- Baseline check (read-only, no writes): current installed v1.2.1 launcher audits **PASS** with
  `serving_flags=[..., '--host', '127.0.0.1', '--port', '"$PORT"', ...]`; this is the exact baseline that a host
  change would break.

`3090-dev/tools/freeze/bin/freeze.sh`: no host/bind check. Two relevant gates for a new candidate:
- `/opt` destination exact-path allowlist — **only**
  `/opt/sglang/local-prod-v1.1.2-candidate|/opt/sglang/local-prod-v1.2-candidate|/opt/sglang/local-prod-v1.2.1-candidate`
  are permitted, each requiring `--allow-production-dest` (lines 121-134). A new `v1.2.2` dest needs a new entry.
- Approved-source-scope compare vs baseline (lines 309-366): launcher bytes are excluded from the source scope
  (`ALLOW_MOD` line 369 covers `launcher/launch.sh`); the template is tooling, not `src/`, so the host edit itself
  does not trip the source-scope gate — the audit does.

**Conclusion: (ii) repo change + new freeze.** Not blocked by the audit as an absolute — the audit's own declared
allowance is the sanctioned place to record the change (a "reviewed production decision", per lines 47-52) — but a
`--host` change without editing that declaration fails closed at repin `exit 22`.

## F. Gateway side

On THIS host the provider registry definition `"provider local" → http://192.168.20.250:30000/v1` is **ABSENT**:
- No readable config on this host maps anything to `192.168.20.250:30000/v1`. Searched `3090-dev/`, `/etc`,
  `~/.config`, `~/.local/share`, `/opt/sglang` (readable).
- This host's own opencode config (`~/.config/opencode/opencode.json:63-68`) defines a provider
  `"Local OpenCodex"` (`@ai-sdk/openai-compatible`) with `"baseURL": "http://192.168.1.203:3456/v1"` — i.e. it
  points *at* the gateway, not at SGLang. The named provider entry `local` that points at
  `http://192.168.20.250:30000/v1` must therefore live **on the gateway host 192.168.1.203:3456** (outside this
  host), where the gateway's provider registry/config is stored.
- The only on-host artifacts that ever pointed a served endpoint at `192.168.20.250:30000` are the DEV provider
  launcher + config (`3090-dev/deploy/conf/provider.env`, historically `BIND_PORT=30000`; now 30001) and the
  provider's own console/metrics logs. No auth/API-key expectation exists in either the frozen prod launcher or
  the DEV provider config (AUTH OFF; see D).

Compatibility flag for the fix (important): the stopped provider advertised `SERVED_MODEL_NAME="qwen35-9b-local"`
(`provider.env:69`), while the frozen production server does **not** pass `--served-model-name` and currently
advertises `"id": "/data/models/qwen35-9b-w4a16"` from `/v1/models`. If the gateway's "provider local" pins the
model name `qwen35-9b-local`, requests through the gateway may 404 after the bind fix. Verify the gateway's
expected model id before/after the change.

## G. Minimal correct fix (RECOMMENDATION ONLY — not applied)

Freeze-requiring path (preserves the frozen production identity):
1. `3090-dev/tools/freeze/templates/launch.sh.tmpl:146` — change `--host 127.0.0.1` to `--host 192.168.20.250`
   (least-exposure; see tradeoff), or parameterize as `HOST="${SGLANG_BIND_HOST:-127.0.0.1}"` + `--host "$HOST"`
   (still needs the audit allowance below; default stays loopback).
2. `3090-dev/tools/freeze/pysrc/audit_launcher.py:58-60` — declare the host replacement in
   `PRODUCTION_REQUIRED_SERVING_REPLACEMENTS`, e.g. add `"127.0.0.1": "192.168.20.250"` (mirrors the existing
   `"65536": "524288"` mechanism), or add both tokens to `PRODUCTION_REQUIRED_SERVING_TOKENS`. This is a reviewed
   production decision per the code's own comment (lines 47-52).
3. `3090-dev/tools/freeze/bin/freeze.sh:127` — add `/opt/sglang/local-prod-v1.2.2-candidate` to the exact-path
   destination allowlist.
4. Build the new candidate (`freeze.sh --build-candidate ... --allow-production-dest`) → v1.2.2 tree.
5. Update scaffold `conf/service.env` `PROD_TREE_DEFAULT`/identity vars to v1.2.2, then stop/start production
   through the scaffold (authorization required; NOT done here).
- Needs restart: **yes** (cold start ~127 s measured; GPU lock takeover required).
- Needs new freeze: **yes**.

Alternatives (not recommended for production identity):
- Reuse the DEV provider path on `:30000` (`provider.env` `BIND_HOST`, no freeze) — serves deploy tree
  `2d4e33a832` with different identity/features (L3 OFF, no namespace gates); changes what "production" is.
- A TCP forwarder on `192.168.20.250:30000 → 127.0.0.1:30000` (socat/`systemd-socket-proxyd`): no freeze, no
  restart, keeps prod running — but adds a new unmanaged listener/process and an extra failure domain; requires
  explicit authorization and a new ops component. Only a stopgap.

Exposure tradeoff (prefer least exposure):
- `--host 192.168.20.250` binds only eth0's LAN address → reachable only from the 192.168.20.0/24 lab network.
- `--host 0.0.0.0` binds every interface (eth0 + lo + any future docker0/VPN iface), a strictly larger surface
  for the same LAN benefit. **Prefer 192.168.20.250.**
- Independent of `--host`: the scheduler socket `*:36971` (pid 1603222) already listens on the wildcard address;
  if strict exposure is required, that needs a separate review (not part of this fix).

Re-verification required after the change:
1. `launcher-repin.sh`: `bash -n` + `audit_launcher.py` PASS (with the extended allowance) + dry-run
   negative (shared namespace exit 4) and positive (`DRY-RUN argv` shows `--host 192.168.20.250`, no side effects).
2. Freeze gates: manifest determinism ×3 (coreutils/Python agree), copy fidelity, immutable modes, identity
   fields (`LAUNCHER_HASH` matches the new launcher sha).
3. `preflight_identity.py --all` on v1.2.2; scaffold `preflight.sh`; scaffold start preconditions (GPU lock,
   port free, unique L3 namespace).
4. Post-restart: `ss -ltnp` shows `192.168.20.250:30000`; loopback `/health` 200; `argv` contains 0 `--api-key`;
   from pc01: TCP connect + `GET http://192.168.20.250:30000/v1/models` 200; through the gateway: chat completion 200.
5. Model-name compatibility with the gateway's "provider local" (see F): either add `--served-model-name
   qwen35-9b-local` to the serving argv (another audited profile delta + freeze) or update the gateway's model id.

---

## Defects / blockers

- **Root cause (confirmed):** frozen prod launcher hard-codes `--host 127.0.0.1` (template:146 / all trees); scaffold
  has no host knob. External reachability had been provided by the DEV provider, moved off :30000 at 16:21Z
  (commit 7d08fb26f8) and stopped 16:30:12Z.
- **Gate, not defect:** the freeze audit fails closed on any `--host` value change versus the v1.1 reference
  (`audit_launcher.py:150-190`); `freeze.sh:127` also needs the new destination allowlisted. Fix is therefore
  freeze-requiring (repo edit + new v1.2.2).
- **NOT a defect:** no firewall interference (ufw inactive; zero iptables/nft rules).
- **Latent exposure (separate follow-up):** scheduler `*:36971` wildcard listener on a public-iface host with AUTH
  OFF for the HTTP server; the HTTP server itself is currently loopback, so the report's port is not externally
  exposed today.
- **Naming/tz hazard:** owner-cited dates are CST (UTC+8); host logs are UTC. Any prod record lookup must apply the
  -8 h offset (03:08 CST == 19:08Z previous day). No literal 03:08 record exists on this host.

## Remaining claims / exclusions

- Could not independently verify pc01-side observations (ping/ssh reachable, TCP refused, gateway 502) — no access
  to pc01/gateway from this task; the loopback bind fully explains them but they are not directly re-tested here.
- Gateway provider `"local"` definition (auth expectations, model id) is ABSENT from this host; it resides on the
  gateway host (baseURL `http://192.168.1.203:3456/v1` per this host's opencode.json). Its contents are unverified.
- Whether upstream network/proxy on the pc01 side could also affect a future external bind is not determinable from
  this host; local firewall is verified open.
- The UTC+8 owner-timezone mapping is an inference from two exact timestamp coincidences, not a directly observed
  host fact.
- The exact instant the DEV provider last served a 200 in the owner's window is bounded by metrics (13:11:19Z first
  record, 13:43:41Z last in the 13h file); no per-request wall-clock list was exhaustively enumerated.
- No restart/repair was performed; the fix above is a recommendation requiring owner authorization, GPU-lock
  takeover, and a new freeze.

## Evidence index (verbatim sources)

- Host: `hostname`, `hostname -I`, `ip -4 addr show`; `ss -ltnp`; `pgrep -af sglang.launch_server`;
  `ps -o pid,ppid,etime,cmd -p 1602781,1602808,1603222`.
- Config: `3090-dev/tools/freeze/templates/launch.sh.tmpl:146`;
  `/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh:146` + sha256
  `38487942de63cb56249dae5080d2caef281364dcbac6c92ac53b1ff916672914`;
  `3090-dev/deploy/conf/provider.env:69,72,75`; `3090-dev/deploy/bin/provider-common.sh:251`;
  scaffold `conf/service.env`, `bin/supervise.sh:43-50`, `bin/start.sh:74-84`.
- Audit/freeze: `3090-dev/tools/freeze/pysrc/audit_launcher.py:53-66,83-95,150-190`;
  `3090-dev/tools/freeze/bin/launcher-repin.sh:37,88-121`;
  `3090-dev/tools/freeze/bin/freeze.sh:121-134,369`; read-only baseline audit run (PASS, flags listed).
- History: `git log` for `provider.env` (7d08fb26f8 16:21:19Z, 116afefbbe 14:50:15Z) and template; HEAD `910e5a01c0`.
- Prod records: `/tmp/opencode/prod-service-20260917/{logs/*/supervisor.log,state/runs/prod.run,state/gpu-owner.json,state/pids/*}`.
- Provider: `/opt/sglang/opencodex-provider-run/{provider.state,server.console*.log,verify/metrics/*}`.
- Firewall: `sudo -n ufw status verbose` (inactive), `sudo -n iptables -S` (ACCEPT only), `sudo -n nft list ruleset` (empty).
- Workspace memory: `.config/opencode/.bak-before-pc01-sync-20260918/AGENTS.md:158` ("sglang-build (VM 2500, 192.168.20.250)").

Terminal state: DONE
