# Production / test service scaffold — RTX 3090 single-GPU exclusive owner

**Status: SCAFFOLD ONLY. No server was started, no port was bound, no GPU lock
was taken, and no frozen/`/data`/evidence path was written by this task.**

This directory contains start / stop / status / switch tooling for a production
service and a separate test service on one host with exactly one usable GPU.
The tooling is parameterised so either frozen production identity can be driven.

---

## 1. Port map

| Port  | Role | Owner | Notes |
|------:|------|-------|-------|
| 30000 | **PRODUCTION** | `bin/start.sh prod` | Launcher default (`SGLANG_PORT`); frozen identity. |
| 30164 | **TEST / diagnostic** | `bin/start.sh test` | Same frozen bytes, different namespace + port. |
| 30165 | **GATE HARNESS — RESERVED** | gate scripts only | These scripts refuse to use it. |

`bin/start.sh` hard-refuses the gate port, and `switch.sh` never starts two
services: there is no code path in this scaffold that runs prod and test
concurrently.

---

## 2. The single-GPU constraint (why the switch exists)

Observed on this host (2026-09-17):

| fact | value |
|---|---|
| GPU | `NVIDIA GeForce RTX 3090`, 24576 MiB, UUID `GPU-2e3ed202-3655-d919-0a64-259209bc6587` |
| M1 at 64K fp8 (observed in the canary server log) | `mem usage=10.36 GB` weights + `6.27 GB` avail after KV/graphs, ~18.7 GiB resident |
| two concurrent servers | ~37 GiB **> 24576 MiB** → impossible |

**Consequence: production and test can never both serve on this GPU.** The
scaffold therefore implements a *single exclusive GPU owner* with an explicit
handoff, never a concurrent pair.

NVML index and CUDA ordinal are **inverted** on this box. Always pin by UUID;
`CUDA_VISIBLE_DEVICES=1` lands on the GT 1030 and fails with
`no kernel image is available`.

---

## 3. GPU handoff protocol

```
        ┌──────────────────────┐
        │ state/gpu-owner.json │   owner-visible record: who holds the GPU
        └──────────┬───────────┘
                   │
  switch.sh prod ──┤
                   │  1. read current owner from state file
                   │  2. stop current owner  (identity-checked SIGTERM; never pkill)
                   │  3. wait for canonical flock to free (bounded, never signal incumbent)
                   │  4. verify no material compute holder (>= 2 GiB)
                   │  5. start target -> supervisor acquires flock, allocates a
                   │     UNIQUE L3 namespace, launches the frozen launcher,
                   │     verifies /proc/<pid>/environ, waits /health 200
                   └── 6. publish new owner + measured cold-start time
```

Canonical lock: **`/tmp/opencode/gpu-3090.lock`** (flock, held by
`bin/supervise.sh` for the *entire server lifetime*). This path is **not
overridable** from the environment, because a redirectable lock path silently
destroys mutual exclusion — the exact incident recorded in
`GPU-LOCK-COORDINATION-RULE-20260916.md`.

Lock discipline implemented:

* `flock -n` only; bounded backoff (`GPU_LOCK_TIMEOUT_S`, default 900 s).
* **Never signal the incumbent.** If the lock is still held at the deadline the
  start path fails closed and reports BLOCKED-on-resource.
* The holder record is written **in place through the locked fd**; the file is
  never replaced with `mv`, which would swap the inode and break `flock` for
  every other waiter.

---

## 4. Commands

```bash
cd /tmp/opencode/prod-service-20260917

# --- inspect (read-only, never takes the lock) ---
bash bin/status.sh
bash bin/status.sh --json | jq .

# --- start (CPU-only preflight first; refuses if anything is wrong) ---
bash bin/start.sh prod                 # production, port 30000
bash bin/start.sh test                 # test, port 30164
bash bin/start.sh prod /opt/sglang/local-prod-v1.1.2-candidate   # explicit tree

# --- stop ---
bash bin/stop.sh prod
bash bin/stop.sh test
bash bin/stop.sh all

# --- handoff ---
bash bin/switch.sh test                # prod -> test
bash bin/switch.sh prod                # test -> prod

# --- gates, standalone ---
bash bin/preflight.sh /opt/sglang/local-prod-v1.1.2-candidate
```

### Selecting a frozen identity

| identity | tree | selectable? |
|---|---|---|
| `LOCAL-PROD-v1.1.2` | `/opt/sglang/local-prod-v1.1.2-candidate` | **yes (default)** — launcher has the identity + namespace gates |
| `LOCAL-PROD-v1.1` | `/opt/sglang/local-prod-v1.1-candidate` | refused by preflight: launcher has **no** identity/namespace gate |
| `LOCAL-PROD-BASELINE-v1` | `/opt/sglang/local-prod-v1` | refused by preflight: no `manifest/TREE-SHA256.txt`, no gates |

`preflight.sh` refuses a tree whose launcher does not enforce the fail-closed
source-identity gate, because such a launcher can silently run the wrong source
(the v1 → v1.1 failure mode). Adding a newly-frozen identity only requires
setting `PROD_TREE_DEFAULT` / `PROD_IDENTITY_DEFAULT` in `conf/service.env`.

---

## 5. L3 namespace policy

Frozen policy: **one task/run → one unique L3 store namespace.** Each start
allocates `<SGLANG_L3_ROOT>/<run_id>` through the frozen tree's own
`tools/l3_namespace.py`, which has **no clear/delete code path at all**.

| rule | enforcement |
|---|---|
| unique namespace per start | `l3_namespace.py --allocate --task-id <role>-<utc>-<pid>` |
| shared store never used/cleared | `--task-id local-prod-*` → `REFUSE` (rc=4) |
| shared store `/data/l3/local-prod-v1.1` | asserted present, **never written** |
| pre-existing unclaimed store | `REFUSE` (rc=6) |
| launcher re-checks the same rule | `l3_namespace.py --validate` inside `launch.sh` |

---

## 6. Measured cold-start time (the switch cost)

Measured from the canary server console log
(`/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916/canary/server.console.log`),
2026-09-17:

| milestone | timestamp (UTC) | Δ from launch |
|---|---|---|
| driver `launched server pid=304751` | 09:25:29 | — |
| server `server_args={...}` printed (launcher gates done) | 09:25:42 | +13 s |
| `Load weight begin` | 09:26:13 | +44 s |
| `Load weight end` (`elapsed=3.21 s`, 10.36 GB) | 09:26:16 | +47 s |
| `KV Cache is allocated` (fp8, 65536 tok) | 09:26:33 | +64 s |
| decode CUDA-graph capture end (`elapsed=5.36 s`) | 09:26:38 | +69 s |
| `The server is fired up and ready to roll!` | 09:26:45 | +76 s |
| `/health` 200 (driver `server_healthy: OK`) | 09:26:48 | **+79 s** |

**Observed cold start = 79 s** (launcher invoked → `/health` 200). Breakdown:
**~13 s in the frozen launcher's source-identity gates** before the server
process is exec'd, then **~66 s** of server init (weight load 3.2 s, KV alloc,
CUDA-graph capture, host pools, uvicorn, health).

Standalone measurements taken by this task (CPU-only, no server, no port):

```
launcher DRY-RUN (gates 1-3 + argv render, no server, no port) : 22.3 s
preflight_identity.py --all (full 14648-entry manifest)        : 15.9 s
import sglang (warm page cache)                                :  9.0 s
```

The 13 s vs 22 s spread is page-cache warmth; the launcher gate cost depends on
how recently the 14648 tree files were hashed.

**Switch cost to budget: ~80 s cold start per handoff**, plus up to ~240 s for
a graceful stop of the incumbent under load. A `switch.sh` round trip is
therefore **~1.5 min best case, ~5 min worst case**.

---

## 7. Preflight failure modes

Every start path runs `bin/preflight.sh` **before** anything is launched. It
fails closed (non-zero, starts nothing) on any of:

| code | check | failure mode it catches |
|---|---|---|
| P1 | tree layout | missing tree / launcher / python / identity manifest |
| P2 | recorded manifest digest vs bytes | tampered or stale tree |
| P3 | recorded launcher sha256 vs bytes | stale/byte-copied launcher (v1→v1.1 mode) |
| P4 | launcher enforces source-identity gate | untrusted launcher |
| P5 | launcher enforces per-run L3 namespace gate | shared-store risk |
| P6 | `sglang.__file__` inside `<tree>/src/python` | **editable-install landmine** |
| P7 | reserved store presence | accidental use of the shared store |

### The editable-install landmine (P6)

Confirmed empirically on this host, CPU-only:

```
$ <tree>/env/bin/python -c "import sglang; print(sglang.__file__)"      # no PYTHONPATH
/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/__init__.py   # STALE WORKSPACE

$ PYTHONPATH=<tree>/src/python <tree>/env/bin/python -c "import sglang; print(sglang.__file__)"
/opt/sglang/local-prod-v1.1.2-candidate/src/python/sglang/__init__.py            # CORRECT
```

The venv's editable finder (`__editable__.sglang-0.5.20.dev22+g9c9e7b7c7.pth`)
binds to the live WIP workspace. `bin/preflight.sh` proves this both ways, and
`bin/supervise.sh` additionally re-reads `PYTHONPATH` and
`CUDA_VISIBLE_DEVICES` from **`/proc/<pid>/environ`** of the running server, so
a process that was started some other way is detected too.

Other fail-closed conditions at start time:

* any material compute holder on the GPU (`>= 2 GiB`) — the scaffold **never**
  signals it;
* port already bound;
* L3 namespace allocation refused (reserved / pre-existing / claimed);
* supervisor exits before `/health` 200.

---

## 8. Rollback / stop

```bash
bash bin/stop.sh all        # stops test then prod, releases the GPU, publishes state=free
bash bin/status.sh          # verify: lock free, no material app, both services down
```

Stop is identity-checked: a PID is only signalled if it is a `launch_server`
referencing the expected tree and port. A PID that does not match is **not**
signalled and stop exits non-zero. There is no `pkill -f` anywhere in this
scaffold.

Rollback of the service *identity* is a selection change, not a code change:
point `PROD_TREE_DEFAULT` at another frozen tree whose launcher passes
preflight. The frozen trees themselves are read-only and were not modified.

---

## 9. Files

```
/tmp/opencode/prod-service-20260917/
  README.md                  this file
  conf/service.env           ports, trees, GPU UUID, lock path, L3 policy
  bin/common.sh              shared helpers (state, flock, identity, namespaces)
  bin/preflight.sh           fail-closed identity + environment gate
  bin/start.sh               start one service (preflight -> supervisor)
  bin/supervise.sh           long-lived flock holder + launcher + health/timing
  bin/stop.sh                identity-checked stop, releases GPU
  bin/status.sh              read-only owner/service status (human + --json)
  bin/switch.sh              explicit prod<->test GPU handoff
  state/                     gpu-owner.json, pids/, ready/, runs/
  logs/                      per-run console + supervisor logs
  scratch-l3/                scratch namespace root used by dry-run tests only
```
