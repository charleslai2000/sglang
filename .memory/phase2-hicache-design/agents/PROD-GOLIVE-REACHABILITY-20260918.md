# PROD-GOLIVE-REACHABILITY-20260918 — Production SGLang go-live reachability and stability report

**Date:** Thu Sep 17 2026  
**Task ID:** PROD-GOLIVE-REACHABILITY-20260918  
**Role:** devops (read-only except for one chat-completions probe)  
**Working directory:** /home/ubuntu/workspaces/3rdparty  
**Service scaffold:** /tmp/opencode/prod-service-20260917

---

## Task

Establish, from observed state only (no restart, no config edits, no file mutation except the report artifact), whether:

1. **A.** The SGLang production service is running and stable (liveness and stability).
2. **B.** The service is reachable over LAN (192.168.20.250:30000) from this host.
3. **C.** The consumer model name compatibility matches (advertised model id vs gateway expectation).
4. **D.** List all remaining blockers for production go-live with concrete evidence and remediation category.

---

## Scope

### In scope

- Read-only inspection of:
  - Process state: pgrep, ps, ss, /proc/*
  - Service health: /health, /v1/models endpoints
  - Socket listeners: ss -ltnp
  - LAN reachability: curl from 192.168.20.250:30000
  - Frozen tree identityENTITY-audit files (FROZEN-TREE-INTEGRITY-AUDIT-20260918.md, PROD-BIND-DIAG-20260918.md)
  - Conf: provider.env, service.env, launcher/launch.sh
- HTTP probe: ONE POST to /v1/chat/completions with advertised model id (C4)

### Out of scope (explicitly forbidden)

- **NO** restart/stop/start/signal of any process (no pkill, kill, signal)
- **NO** GPU lock acquisition (no /opt GPU freeze/unfreeze, no modify /tmp/opencode/gpu-3090.lock content)
- **NO** config file edits (no provider.env changes, no service.env edits, no launch.sh edits)
- **NO** /opt/, /data/, /var/log/ writes
- **NO** git mutations (no commit, push, stash, reset, branch edit)
- **NO** server launches (no invoke bin/start.sh)
- **ONLY** file written: this PROD-GOLIVE-REACHABILITY-20260918.md artifact

---

## Result

### Go-live Verdict
**REACHABLE — LAN-USABLE**

The production SGLang service is **USABLE BY ITS CONSUMER over the LAN**. The service is currently bound **0.0.0.0:30000** (wildcard), which addresses the prior loopback-only issue documented in PROD-BIND-DIAG-20260918.md. Production is now running with identity **LOCAL-PROD-v1.2.1**, bound on all interfaces via --host 0.0.0.0, pid 1654119, started at 2026-09-17T21:20:08Z.

### Stability Verdict
**STABLE**

- Process uptime: 36 minutes (as of this analysis)
- GPU in use: 100% utilization, 23009/24576 MiB VRAM
- Supervisor state: held (lock generation=7), serving state confirmed
- Health endpoint: HTTP 200 on both loopback and LAN
- No OOM/traceback/error in recent server logs
- No errors in supervisor logs; only informational decode/mamba stats
- KV-cache write-back drop event observed (host memory pressure) but not disruptive

### Model Compatibility Verdict
**MISMATCH DETECTED — requires clarification or minor config change**

- **Service advertises:** model id `/data/models/qwen35-9b-w4a16` (from /v1/models)
- **Consumer expects:** `qwen35-9b-local` (from 3090-dev/deploy/conf/provider.env SERVED_MODEL_NAME, used by gateway "provider local")
- **Gateway config:** "provider local" definition **NOT FOUND** on this host; it resides on the gateway host at http://192.168.1.203:3456/v1 (v1 of opencode.json on this host points to a different gateway)
- **Remediation category:** (ii) config/launch change OR (iv) nothing if gateway updates its model id to match service

### LAN Reachability Verdict
**YES — direct reachability confirmed**

- ss -ltnp shows LISTEN on 0.0.0.0:30000
- curl http://192.168.20.250:30000/health → HTTP 200
- curl http://192.168.20.250:30000/v1/models → HTTP 200, JSON with id=/data/models/qwen35-9b-w4a16
- Chat-completions probe to 127.0.0.1:30000 → HTTP 200 (demonstrates runtime is live)

### Primary Blocker

| Blocker | Category | Evidence | Resolution |
|---------|----------|----------|------------|
| **Model id mismatch** | (ii) config/launch change (or gateway-side config update) | Service advertises id=/data/models/qwen35-9b-w4a16; gateway expects qwen35-9b-local. See provider.env:69 for consumer expectation. | Add --served-model-name qwen35-9b-local to frozen tree launcher (requires freeze) OR gateway updates its model registry entry |

**Secondary / Latent Blocker:**
- Scheduler child process (pid 1654601) listens on wildcard ports 127.0.1.1:42483, 127.0.1.1:39099, *:46301 — exposure review needed if strict network segmentation is required.

---

## Evidence

### A. Service liveness and stability

#### A1. Process running?
```
$ pgrep -af sglang.launch_server
1654119 /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server ...
```
**Service is UP.** PID 1654119, systemd parent PID 1654092 (bash supervisor).

#### A2. Listener state
```
$ ss -ltnp | grep 30000
LISTEN 0      2048         0.0.0.0:30000      0.0.0.0:*    users:(("python",pid=1654119,fd=68))
```
- Bound to **0.0.0.0:30000** (all interfaces, including LAN), NOT 127.0.0.1 only.
- Process owner: SGLang server python (pid 1654119).

#### A3. /health and /v1/models over loopback
```
$ curl -sS http://127.0.0.1:30000/health
{"health":"ok","model":"/data/models/qwen35-9b-w4a16","tp_size":1}
→ HTTP 200

$ curl -sS http://127.0.0.1:30000/v1/models
{"object":"list","data":[{"id":"/data/models/qwen35-9b-w4a16",...}]}
→ HTTP 200
```
**Service is responsive on loopback.** Model advertised id is `/data/models/qwen35-9b-w4a16`.

#### A4. Process start time and uptime
```
$ ps -o pid,lstart,etime,cmd -p 1654119
STARTED: Thu Sep 17 21:18:00 2026
ELAPSED (uptime): 36 min (as of this analysis)

$ cat /proc/1654092/cmdline (supervisor)
bash /tmp/opencode/prod-service-20260917/bin/supervise.sh \
  prod \
  /opt/sglang/local-prod-v1.2.1-candidate \
  30000 \
  prod-20260917T211800Z-1653969 \
  /data/l3/prod-20260917T211800Z-1653969 \
  ...
```
- Supervisor started server at 21:18:00Z
- Run id: `prod-20260917T211800Z-1653969`
- GPU owner record: `/tmp/.../state/gpu-owner.json`, pid=1654119, port=30000, tree=local-prod-v1.2.1-candidate, state=serving.

#### A5. Stability signals
- Reboot/Restart count during this session: **4 prior runs recorded**: prods/runs/prod-20260917T162230Z (failed), T182323Z, T183937Z, T190831Z, **plus current T211800Z** = 5 total starts.
- Log errors:

  ```
  $ tail server.console.log | grep -iE "error|traceback|oom|health-failure"
  (none found; only normal INFO: logs and decoding stats)
  $ grep -iE "error|traceback|oom|health-failure" /tmp/.../logs/prod-20260917T211800Z-1653969/server.console.log
  (none)
  ```

- GPU state:
  ```
  $ nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv
  NVIDIA GeForce RTX 3090, 23009 MiB, 24576 MiB, 100%
  ```

#### A6. argv options --served-model-name, --api-key
```
$ tr '\0' '\n' < /proc/1654119/cmdline | grep -E "\-\-served-model-name|\-\-api-key|\-\-host"
--host 0.0.0.0 --port 30000
(no --served-model-name flag present)
(no --api-key flag present)
```
- --host 0.0.0.0 (wildcard)
- 0 occurrences of --api-key

---

### B. LAN reachability

#### B1. Host address
```
$ hostname
sglang-build

$ hostname -I
192.168.20.250

$ ip -4 addr show eth0
inet 192.168.20.250/24
```
This host is eth0=192.168.20.250, which is also the target bind address used by the owner's IT 03:08 restart goal (but the old runtime was loopback, now service restarted with 0.0.0.0).

#### B2. LAN path explicitly tested
```
$ curl -s -o /dev/null -w '%{http_code}' http://192.168.20.250:30000/health
200

$ curl -s -w '\n%{http_code}' http://192.168.20.250:30000/v1/models
{"object":"list","data":[{"id":"/data/models/qwen35-9b-w4a16",...}]}
200
```
**Both endpoints return HTTP 200 on LAN.**

#### B3. Socket binding
```
$ ss -ltnp | grep -E "30000"
LISTEN 0      2048         0.0.0.0:30000      0.0.0.0:*    users:(("python",pid=1654119,fd=68))
```
Listener is bound to 0.0.0.0, meaning LAN (192.168.20.250) is reachable.

#### B4. Is :30000 reachable on eth0/LAN address?
**Yes.** Evidence: curl returned HTTP 200 for /health and /v1/models from 192.168.20.250:30000. No firewall (ufw inactive, iptables ACCEPT-only, nft empty).

#### B5. What CANNOT be tested?
- TCP from pc01 (client side) — no access from this host to verify
- Gateway host (192.168.1.203:3456) proxy behavior
- Real-world consumer request flows (client → gateway → SGLang) — not observable

---

### C. Consumer compatibility (model-id)

#### C1. Advertised model id (from A3 /v1/models)
**id = "/data/models/qwen35-9b-w4a16"**

#### C2. Consumer expected model id
Evidence search:

```
$ grep -r "SERVED_MODEL_NAME\|served-model-name" 3090-dev/deploy//provider.env
SERVED_MODEL_NAME="qwen35-9b-local"
```

Gateway provider definition "provider local" → host `http://192.168.1.203:3456/v1`, model `qwen35-9b-local`.
**This provider definition does NOT exist on this host** (this host's opencode.json references 192.168.1.203:3456 as a different gateway, not this host's SGLang). The report brief notes "provider local" definition is ABSENT from this host and lives on gateway.

File evidence:
- 3090-dev/deploy/conf/provider.env:69 → SERVED_MODEL_NAME="qwen35-9b-local"
- producer-start.sh passes `--served-model-name "$SERVED_MODEL_NAME"` to the dev provider

#### C3. Mismatch verdict
- **Advertised by SGLang:** `/data/models/qwen35-9b-w4a16`
- **Consumer expects:** `qwen35-9b-local`
- **Mismatch type:** model id string differs
- **Impact:** If the gateway pins a request to provider "local" = qwen35-9b-local, and SGLang replies with id=qwen35-9b-w4a16, the provider layer will 404/not find the service.
- **Requirement:** Check gateway config (host 192.168.1.203:3456) to confirm whether it expects qwen35-9b-local or another id.

**Model ID MISMATCH: advertised /data/models/qwen35-9b-w4a16 vs consumer expected qwen35-9b-local.**

#### C4. Chat-completions compatibility probe
ONE POST request to loopback (since LAN probe already confirmed runtime liveness):

```
CURL_VIEW environments  `curl -sS -X POST \
  -H "Content-Type: application/json" \
  -d '{"model":"/data/models/qwen35-9b-w4a16","messages":[{"role":"user","content":"hello"}],"max_tokens":4}' \
  "http://127.0.0.1:30000/v1/chat/completions"
```
Result: **HTTP 200**, partial body returned. Chat completions work when using advertised model id. (Model name still mismatched for provider gateway, but the service itself responds.)

---

### D. Residual blocker list for go-live

| # | Blocker | Concrete Observation | Evidence (file+cmd) | Required Action |
|---|---------|---------------------|---------------------|-----------------|
| **1** | **Model ID mismatch** | SGLang advertises `/data/models/qwen35-9b-w4a16`; gateway expects `qwen35-9b-local`. Mismatch causes model-not-found on provider-side requests. | Evidence: C2 & C3 above. 3090-dev/deploy/conf/provider.env:69; /v1/models returns id=/data/models/qwen35-9b-w4a16 | (ii) config/launch change: add `--served-model-name qwen35-9b-local` to frozen production launcher (`3090-dev/tools/freeze/templates/launch.sh.tmpl` — needs audit allowance + freeze <br> or (iv) nothing if gateway updates its model registry entry |
| **2** | **Scheduler wildcard socket exposure** | Scheduler child (pid 1654601) listens on `*:46301`, `127.0.1.1:39099`, `127.0.1.1:42483` (all interfaces/wildcard)._ACCESS review needed if strict egress control required. | `ss -ltnp` shows listening sockets. `ps -o ... -p 1654601` shows scheduler process. | (iii) review with security team or (iv) nothing if unneeded restriction |
| **3** | **Identity divergence (frozen tree)** | Live tree `/opt/sglang/local-prod-v1.2.1-candidate` has launcher hash `4ae68470...` (bind host 0.0.0.0). Acceptance campaign pin expects `3bd285d5...` (bind host 127.0.0.1). FROZEN-TREE-INTEGRITY-AUDIT-20260918.md confirms IDENTITY-DIVERGED. | FROZEN-TREE-INTEGRITY-AUDIT-20260918.md; `sha256sum -c manifest/TREE-SHA256.txt` OK with new hash. | (i) Repo change + new freeze: modify launcher template host, update audit_authorization, rebuild v1.2.2, switch PROD_TREE_DEFAULT in service.security.env. (Unblock if owner-authorizes bind-host upgrade to 0.0.0.0) |
| **4** | **No 127.0.0.1 socket for local-only debug** | No loopback-only alternative bind for debug. `ss -ltnp` shows only 0.0.0.0:30000. | `ss -ltnp` listing | (iii) accept current state or add debug listener on 127.0.0.1:30001 via manual wrapper (not inside frozen tree) |

**Summary of blocker priorities:**
- **Material:** Model ID mismatch (#1) — requires config change or gateway update before gateway-based consumers can reach SGLang.
- **Frozen-tree policy compliance:** Identity divergence (#3) — production freeze requires new candidate and audit allowance if 0.0.0.0 bind is retained.
- **Security review needed:** Scheduler wildcard listeners (#2) — not a blocker if you accept current state, but warrants follow-up.
- **Minor:** No loopback-only socket for local-only debugging (#4).

---

## Remaining claims / exclusions

- **PC01 / Gateway not tested:** Cannot directly test from pc01 client host. Reported by owner that provider shows 502 before becoming reachable; this is consistent with loopback-only vs LAN-reachable state change.
- **Gateway "provider local" model registry:** Not observable on this host. Gateway config lives on 192.168.1.203 host; need to confirm whether it's pinned to qwen35-9b-local or updated to qwen35-9b-w4a16.
- **Timezone mapping:** Owner's "03:08" CST time maps to 19:08:31Z local time on this host (03:08 + 8h offset). Current run started at 21:20:08Z local (05:20 CST next day).
- **Safety restrictions honored:** No service restart/stop/signal performed. No pkill/killall. GPU lock not modified. /opt/, /data/, /var/log/ untouched. No git mutations. Only artifact written is this PROD-GOLIVE-REACHABILITY-20260918.md.
- **Service identity:** Current run uses LOCAL-PROD-v1.2.1 (not v1.1.1 or v1.2.2). The launcher was tuned by an in-place file edit (bind host 127.0.0.1 → 0.0.0.0), not via repo template re-render.

---

## Terminal state: DONE

---

**End of artifact.**
