# PROD-RESTORE-20260918-R3

Status: DONE

Terminal state: DONE

## Task

Operational recovery: restore a healthy serving instance on `:30000` after the
`MAMBA-F12-PARK-REGRESSION-20260918` task (GPU-window authority) stopped production and failed to
restore it, then leave the host in a clean, documented, healthy state.

## Scope

GPU-window authority. Diagnose actual state, identify stale F12/leftover GPU holders, restore
exactly one model on `:30000` (prefer M2 scaffold, fall back to M1), verify health (loopback + LAN),
record restored state. Operational recovery only — no source edits, no weight changes, no commits.

## Result

**`:30000` is UP and healthy, serving M2 (OmniCoder-9B GPT4 INT4).** Verified by real commands:
loopback `/health` = 200, LAN `/health` = 200, `GET /v1/models` returns the M2 model id, and
`POST /v1/chat/completions` succeeds over both loopback and LAN.

**Important attribution fact (not a claim of my own action):** I did NOT start the live server, and I
did NOT kill anything. During first-pass reconnaissance (12:43:18Z) a **concurrent actor**
started M2 via the last-resort `/tmp/opencode/MLINE-M2-CUTOVER-20260918/launch-m2.sh`; by the time
I had finished diagnosis, production was already up. Process ancestry shows that actor was launched
by an `opencode` process (PID 1758196) — i.e. orchestrator-side, not this task. I verified the
result end-to-end rather than disrupt it.

The **preferred M2 scaffold path does not exist** in the installed scaffold: `start.sh` accepts only
`prod|test` and rejects `m2` (exit 2). The `m2` role exists only in an *unapplied staged diff*
(`/tmp/opencode/M2-ARCH-STAGE-20260918/patch/b/bin/start.sh`) and `conf/service.env` has no `M2_*`
variables; only a draft `bin/stop-m2.sh` was installed. Therefore the fallback M1 path (which would
have restored M1) could not be used while M2 already held the single GPU, and switching would have
caused an unnecessary second outage. The M2 frozen tree launcher itself
(`/opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh`) is installed, passes its gates,
and is the viable long-term serving path — but it is not yet wired into `start.sh`.

## Evidence

### E1. Initial state — production DOWN (FACTS)

- `ss -ltnp | grep :30000` → no listener (only `State`/header lines; no :30000 row).
- `ps auxww | grep -iE 'sglang|omnicoder|qwen|30000|f12|launch'` → no matches (`exit:1`).
- `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:30000/health` → `000`, `curl_exit=7`.
- All recorded F12 / pre-outage PIDs DEAD: `1764091 1764114 1764226 1802907 1802913 1802943
  1804416 1804422 1804452` → each `DEAD`.
- `/tmp/opencode/gpu-3090.lock` (stale at diagnosis time):
  `{"owner": "f12-frozen-f12-frozen-20260918T120901Z-1802823", "pid": 1804422, "generation": 23, "acquired": "2026-09-18T12:22:34Z"}`
  — holder PID 1804422 is **DEAD**; lock is stale (liveness released by kernel; `flock -n` probe
  reported `LOCK_IS_FREE`).
- Scaffold state file `/tmp/opencode/prod-service-20260917/state/gpu-owner.json` (stale, gen 21)
  still named dead PID `1764114`, run `m2-cutover-20260918T100839Z-1764091`.
- `nvidia-smi --query-compute-apps=...` → `No running processes found` (GPU idle, 1 MiB).

### E2. F12 prior-task result (FACT) — never restored, never terminal

`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/MAMBA-F12-PARK-REGRESSION-20260918.md`
is `Status: WORKING` / `Terminal state: WORKING`; `Result`, `Defects / blockers`,
`Remaining claims / exclusions`, `Restored-state record` are all `PENDING`. Its F12 driver logs show
both arms completed and were stopped cleanly (`f12 repaired stopped 12:20:48Z`, `f12 frozen stopped
12:40:18Z`), but **no production restart was performed** — consistent with the outage.

### E3. Preferred M2 scaffold path — NOT INSTALLED (FACT, tried)

```
$ bash /tmp/opencode/prod-service-20260917/bin/start.sh m2
[12:43:25] FATAL: unknown role 'm2' (want prod|test) 2
EXIT=2
```

- `grep -rniE 'm2|omnicoder' /tmp/opencode/prod-service-20260917/bin/ /tmp/opencode/prod-service-20260917/conf/`
  → only `stop-m2.sh` (its header literally says "This is a DRAFT for review; it is not installed
  and not executed."). No `m2` case in `start.sh`; no `M2_*` keys in `conf/service.env`.
- The missing integration is exactly the staged diff at
  `/tmp/opencode/M2-ARCH-STAGE-20260918/patch/b/{bin/start.sh,conf/service.env}` (adds
  `m2)` role + `M2_PORT=30000`, `M2_TREE_DEFAULT=/opt/sglang/local-prod-v1.2.1-candidate-M2`,
  `M2_L3_MODE=disabled`). `patchcheck/` shows the patch was applied to a scratch git copy
  (`git -C .../patchcheck log --oneline` → `708f7e6 base`) and **rejected** in the live scaffold
  (`bin/start.sh.rej`, `conf/service.env.rej` present). It was never applied to
  `/tmp/opencode/prod-service-20260917`.

### E4. M2 frozen tree launcher — viable, passes gates (FACT, non-destructive dry-run)

```
$ cd /tmp && SGLANG_L3_MODE=disabled SGLANG_RUN_ID=probe-restore-20260918 \
    SGLANG_LAUNCH_DRY_RUN=1 bash /opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh
=== LOCAL-PROD-v1.2.1-M2 launcher (M2; L3/HiCache EXPLICITLY DISABLED) ===
tree=/opt/sglang/local-prod-v1.2.1-candidate-M2
model=/data/models/omnicoder-9b-gptq-int4 port=30000
PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate-M2/src/python
CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
SGLANG_L3_MODE=disabled (no L3 store is allocated; /data/l3 is untouched)
L3 GATE: EXPLICITLY DISABLED (SGLANG_L3_MODE=disabled; no store allocated; no extent env; no HiCache argv)
DRY-RUN OK identity=LOCAL-PROD-v1.2.1-M2 tree=/opt/sglang/local-prod-v1.2.1-candidate-M2 run_id=probe-restore-20260918 l3_mode=disabled
DRY-RUN src_stream_sha256=c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc
DRYRUN_EXIT=0
```

M2 manifest is consistent: `sha256sum M2/launcher/launch.sh` =
`9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4` = recorded `LAUNCHER_HASH`/
`launcher.sha256`; `TREE_HASH` = `e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a`;
`TREE-SHA256.txt` matches. M2 `tools/{l3_namespace,preflight_identity,validate_telemetry}.py` are
byte-identical to the M1 frozen tree's tools (`diff` → `IDENTICAL`), and M2 `src/` is hardlinked
from M1 (link count 2), i.e. one source lineage. M2 tree is `/opt/sglang/local-prod-v1.2.1-candidate-M2`
with `env -> /home/ubuntu/venvs/sglang-3090`.

### E5. M1 fallback live path — currently blocked by the live M2 holder (FACT, dry-run)

`START_DRY_RUN=1 bash .../start.sh prod` passed preflight (manifest/launcher hashes OK, gates P4/P5
present, P6 resolves inside the M1 tree) but failed closed at the GPU step:

```
[12:46:15] preflight PASS: /opt/sglang/local-prod-v1.2.1-candidate
[12:46:15] FATAL: GPU has a material compute holder; stop it first (this script never signals it):
1808321 18752 sglang::scheduler 1
EXIT=1
```

This is the scaffold's fail-closed GPU mutual-exclusion working as designed: M1 (which binds
`:30000` and uses L3/HiCache) cannot be started while M2 occupies the single 3090. No M1 namespace
was allocated and no lock was taken (`START_DRY_RUN=1` semantics).

### E6. Restoration event by the concurrent actor (FACT — derived from logs + process ancestry)

- `/tmp/opencode/MLINE-M2-CUTOVER-20260918/restore-f12.out` (mtime `2026-09-18 12:44:41Z`) and
  `.../logs/m2-cutover-20260918T124318Z-1808175/driver.log`:

```
M2_LAUNCH_START 2026-09-18T12:43:18Z run_id=m2-cutover-20260918T124318Z-1808175 pid=1808175
LOCK_ACQUIRED generation=24 owner=m2-cutover-m2-cutover-20260918T124318Z-1808175 pid=1808175
SERVER_LAUNCHED pid=1808198 log=.../m2-cutover-20260918T124318Z-1808175/server.console.log
STATE_WRITTEN pid=1808198
M2_UP pid=1808198 run_id=m2-cutover-20260918T124318Z-1808175 cold_start_s=83
HOLDING_LOCK pid=1808175 server_pid=1808198
```

- Server console confirms clean startup and readiness:
  `Engine startup timings ... tokenizer_e2e=60.56`, `Uvicorn running on http://0.0.0.0:30000`,
  `GET /health HTTP/1.1 200 OK`, `POST /v1/chat/completions HTTP/1.1 200 OK`,
  `The server is fired up and ready to roll!`.
- Ancestry: `1808175 (launch-m2.sh) PPID=1`, started `Fri Sep 18 12:43:17`; the supervising
  `opencode` process is `1758196 PPID=298244`, started 08:07:24, and it also spawned the
  one-shot verification poller `1808374 /bin/bash -c sleep 110; ... restore-f12.out ...`.
  This identifies the actor as orchestrator-side, **not** this `debugger-deep` task.

### E7. Final verified health (FACTS, post-restore)

- `ss -ltnp | grep 30000`:
  `LISTEN 0 2048 0.0.0.0:30000 0.0.0.0:* users:(("python",pid=1808198,fd=68))`
- `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:30000/health` → `200` (stable x3,
  ~1.00 s each).
- LAN `curl ... http://192.168.20.250:30000/health` → `200`.
- `GET /v1/models` (loopback and LAN) →
  `{"object":"list","data":[{"id":"/data/models/omnicoder-9b-gptq-int4","object":"model",...,"max_model_len":131072}]}`
- `POST /v1/chat/completions` loopback (max_tokens=200, temp=0) → `HTTP=200`, `finish_reason:"stop"`,
  content `4` for "What is 2+2?".
- GPU: `nvidia-smi --query-compute-apps` →
  `1808198 ...python, 300 MiB` and `1808321 sglang::scheduler, 18752 MiB`; total 19067/24576 MiB,
  4% util.
- Server env is correct: `PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python`,
  `CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587`, and **no `SGLANG_*` env**
  (L3/HiCache off, as intended for M2).
- Scaffold `state/pids/` and `state/ready/` are empty (no stale scaffold records).

### E8. Cleanliness (FACTS)

- Test ports free: `30170`/`30171` (F12 arms) no listeners.
- No leftover F12/test processes (`ps ... grep p6_load|f12_|sampler` → `NONE`); no `.ready`
  markers under F12 `state/`.
- Exactly one server family running (PIDs 1808175/1808198/1808321/1808322) + transient torch
  inductor compile workers under the scheduler.
- The canonical lock is held by the live M2 supervisor only: fd-holder scan shows
  PID 1808175 (`launch-m2.sh`) and PID 1808198 (server) referencing
  `/tmp/opencode/gpu-3090.lock`.
- Residual, intentionally NOT removed: F12 evidence namespaces
  `/data/l3/f12-frozen-20260918T120901Z-1802823` and
  `/data/l3/f12-repaired-20260918T120901Z-1802823` (frozen policy: a run never clears another run's
  L3 store; these are test evidence, not hygiene blockers).

## Defects / blockers

1. **[Scaffold gap — the reason the preferred path could not be used]**
   `/tmp/opencode/prod-service-20260917/bin/start.sh` has no `m2` role and `conf/service.env` has no
   `M2_*` keys. M2 scaffold support exists only as an unapplied/rejected staged patch
   (`M2-ARCH-STAGE-20260918/patch/b`, `.rej` files). Restoring via the intended long-term path is
   therefore impossible until that integration is installed (see followups).
2. **[Stale scaffold/owner state not reconciled]**
   `/tmp/opencode/prod-service-20260917/state/gpu-owner.json` still records `tree:
   /opt/sglang/local-prod-v1.2.1-candidate` (the M1 tree) while the live server is M2 from the
   frozen M1 **source** via the last-resort launcher. This is the last-resort `launch-m2.sh`'s own
   labeling; I did not silently rewrite another component's state record. It is informational, not a
   service defect. `lock_generation` is now 24 and coherent with the live supervisor.
3. **[Concurrent actor correctness not independently verified by me]**
   I did not execute the restore command and therefore cannot vouch for the actor's intent/context
   beyond the recorded logs and the observed healthy end state. I verified only the resulting state.

No blocker prevented the assigned deliverable: production is healthy.

## Remaining claims / exclusions

- FACTS established above (E1–E8) are from real command output/exit statuses captured in this task.
- INFERENCE: the actor that restored service is orchestrator-side recovery for this same outage,
  based on PPID/`opencode` ancestry and the `restore-f12.out`/`M2_UP_*` artifacts. Its exact
  dispatch text was not visible to me.
- I did **not**: start or stop any process; use `pkill`; modify source, weights, or git; commit;
  edit the ledger; or write any file other than this result artifact.
- I could not establish whether `launch-m2.sh`'s long-run stability (beyond ~2.5 min uptime and the
  smoke requests) holds; health was stable for the entire observation window.
- The M2 scaffold **launcher** is proven viable by non-destructive dry-run; the M2 scaffold
  **`start.sh` role** remains unproven because it is not installed.
- I did not "fix" the stale `gpu-owner.json` tree label or install the M2 scaffold patch — both
  would be product/tooling changes outside operational-recovery authority.

## Restored-state record

| Field | Value |
| --- | --- |
| Status | Healthy, serving |
| Model id (`/v1/models`) | `/data/models/omnicoder-9b-gptq-int4` (identity `M2-OMNICODER-9B-GPTQ-INT4`) |
| Model role | M2 (OmniCoder-9B GPTQ INT4), matching the pre-outage live model |
| Port / bind | `:30000`, host `0.0.0.0` |
| Server PID | `1808198` |
| Scheduler PID | `1808321` |
| Detokenizer PID | `1808322` |
| Supervisor / lock holder PID | `1808175` (`bash /tmp/opencode/MLINE-M2-CUTOVER-20260918/launch-m2.sh`, holds canonical flock on fd 9) |
| Canonical lock | `/tmp/opencode/gpu-3090.lock` = `{"owner": "m2-cutover-m2-cutover-20260918T124318Z-1808175", "pid": 1808175, "generation": 24, "acquired": "2026-09-18T12:43:18Z"}` |
| Lock generation | **24** |
| Run id | `m2-cutover-20260918T124318Z-1808175` |
| gpu-owner.json | `/tmp/opencode/prod-service-20260917/state/gpu-owner.json`: role `prod`, state `held`, pid `1808198`, port `30000`, run_id `m2-cutover-20260918T124318Z-1808175`, l3_namespace `""`, tree `/opt/sglang/local-prod-v1.2.1-candidate`, identity `M2-OMNICODER-9B-GPTQ-INT4`, lock_generation `24`, note "serving M2 (cutover window; direct launch_server, L3 off)" |
| GPU | `GPU-2e3ed202-3655-d919-0a64-259209bc6587`; 19067/24576 MiB used |
| L3/HiCache | Disabled (no `SGLANG_*` env in server; L3 namespace empty) |
| Loopback health | `200` |
| LAN health (`192.168.20.250:30000`) | `200` |
| `/v1/models` | returns M2 model id, `max_model_len` 131072 |
| Chat completion | `HTTP 200` loopback + LAN |
| Cold start (actor log) | 83 s |
| **Exact command used to restore (by concurrent orchestrator-side actor, NOT by me)** | `bash /tmp/opencode/MLINE-M2-CUTOVER-20260918/launch-m2.sh` (last-resort script; it derives `RUN_ID=m2-cutover-<utc>-$$`, holds the canonical flock, and execs `.../local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server --model-path /data/models/omnicoder-9b-gptq-int4 --host 0.0.0.0 --port 30000 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 262144 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir ... --disable-prefill-cuda-graph)` |

**Followups for the orchestrator (fresh dispatch; outside this task's authority):**

1. Install the M2 `start.sh` role + `M2_*` keys into `/tmp/opencode/prod-service-20260917`
   (staged in `M2-ARCH-STAGE-20260918/patch/b`) so the intended scaffold path
   `start.sh m2` works and the last-resort `launch-m2.sh` is retired. On next controlled restart,
   prefer `start.sh m2` over the scratch launcher.
2. Reconcile `/tmp/opencode/prod-service-20260917/state/gpu-owner.json` so `tree`/`identity` reflect
   the actual serving envelope, and stop the last-resort launcher mislabeling the M1 tree path.
3. Have the concurrent actor/orchestrator record its own terminal handoff for the restore (this
   artifact verifies the outcome; the acting component should own its record).
4. Optionally have the original F12 task close out its terminal `Restored-state record` /
   `Terminal state` now that service is restored.

Terminal state: DONE
