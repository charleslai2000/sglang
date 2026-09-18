# C4-CAMPAIGN-IGNITION-RECON-20260917 — IGNITION MANIFEST

- task_id: `C4-CAMPAIGN-IGNITION-RECON-20260917`
- role: scout — READ-ONLY reconnaissance. Facts with file:line / verbatim command evidence only.
- repo: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` (branch `3090-24g-opt`)
- authority: ledger entry `### 2026-09-17 — OWNER RULING (Option A)` §3 (6-step campaign) and
  `### 2026-09-17 — C4 点火准备` (this recon), `.memory/phase2-hicache-design/ledger.md:7852-7891`
  and `:8052-8070`.
- Dispatch validation: the repo-root `AGENTS.md` is **ABSENT**; the only in-repo `AGENTS.md` is
  `docs/AGENTS.md` (upstream Mintlify documentation guide, lines 1-30 — not applicable to
  `3090-dev/`). The account-global `/home/ubuntu/.config/opencode/AGENTS.md` governs. Dispatch is
  in-scope for a read-only scout and does not exceed this role.

## IN-FLIGHT-HARNESS CAVEAT (binding on this report)

The six gate files under `3090-dev/gates/production/` were last written at
`2026-09-17 20:35:46–20:36:40Z` (`stat`), i.e. **after** the C1 implementation round whose artifact
reports 760/1024/687-line files (`agents/GATEA-CLOSURES-IMPLEMENT-20260917.md:62-68`). Current bytes
are e.g. `gate_a_content_integrity.py` **819 lines**, `gate_common.py` **1597 lines**. Per dispatch,
**no behavioral claim below rests on those current bytes**; argparse argument *names* and README
statements are cited but every gate-behavior cell is marked **“subject to the in-flight harness
change”**.

---

## A. Runner / driver surfaces

### A.1 Is there an existing six-step campaign runner? — **ABSENT**

- No script sequences the six steps. Search of repo (`--include=*.sh --include=*.py --include=*.md`
  for `gate_a_content_integrity|gate_a_f1_cold_l1|f2_restart_recovery` outside the scripts
  themselves) returns only `test_gate_helpers.py` imports and the README; **no runner**
  (`grep -rIn` over `3090-dev`, `.memory`).
- No runner in `/var/log/sglang/**` either: `grep -rIl "gate_a_content_integrity" /var/log/sglang`
  returns only the deployed *copies* of `gate_common.py`, `test_gate_helpers.py`, `README.md`, and
  two prose `REPORT.md`/`NOTES.md` files. The prior campaign was driven step-by-step; its per-step
  output dirs exist but the orchestration script does not:
  `/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916/{gateA,gateA-F1,f2,canary,final-campaign-20260917,final-campaign-20260917-r2}`.
- The owner ruling’s sequence is prose, not an executable: `ledger.md:7871-7873`
  (`Gate A 64K → Gate A 128K → F1 real post-wrap → F2 true restart/rebuild → production-profile
  native 128K perf → short canary`).
- The only driver artifact that exists is the canary driver, and it is **not in the repo**
  (see A.5 / B.2).

### A.2 Exact CLI forms of the three gates (argparse + README)

`README.md` run commands (`3090-dev/gates/production/README.md:28-48`):

```bash
TREE=/opt/sglang/local-prod-v1.1.2-candidate          # the tree UNDER TEST
PY=$TREE/env/bin/python
H=/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916

CUDA_VISIBLE_DEVICES="" $PY $H/gate_a_content_integrity.py --tree $TREE --port 30165
CUDA_VISIBLE_DEVICES="" $PY $H/gate_a_f1_cold_l1.py       --tree $TREE --port 30165 --expect fixed
CUDA_VISIBLE_DEVICES="" $PY $H/f2_restart_recovery.py     --tree $TREE --port 30165
```

Argument surface (argparse; **subject to the in-flight harness change**):

- **Gate A** `gate_a_content_integrity.py:59-84`: `--tree`, `--model`, `--port`,
  `--hc-size` (default 8), `--prompt-tokens` (default 65000), `--host-pool-margin` (default 4096),
  `--max-new` (32), `--filler-tokens` (16000), `--max-fillers` (8), `--extent-size` (64 MiB),
  `--file-size` (0 ⇒ computed), `--slots-margin` (4), `--min-index-fraction` (0.99),
  `--wal-checkpoint-bytes` (32 MiB), `--namespace`, `--reuse-namespace`, `--run-id`,
  `--lock-attempts` (240), `--lock-poll` (15), `--health-timeout` (2400).
- **F1** `gate_a_f1_cold_l1.py:67-104`: adds `--chain-tokens` (62000), `--page-bytes`,
  `--sweep-tokens` (2048), `--sweep-requests` (160), `--max-consecutive-refusals` (16),
  `--cold-fillers` (1), `--min-restore-fraction` (0.8), `--expect {fixed,unfixed}` (default fixed),
  `--reloc-reserve-slots` (default 2 — the reserve knob), plus Gate-A’s common set.
- **F2** `f2_restart_recovery.py:55-76`: `--phase {all,primer,recover}` (default `all`), and the
  common set (`--tree/--model/--port/--hc-size/--chain-tokens/--host-pool-margin/--max-new/
  --filler-tokens/--max-fillers/--extent-size/--file-size/--slots-margin/--min-index-fraction/
  --wal-checkpoint-bytes(16 MiB)/--namespace/--reuse-namespace/--run-id/--lock-attempts/
  --lock-poll/--health-timeout`).

Environment fallbacks (all optional; README `:55-73`, constants `gate_common.py:34-51`):

| var | default | meaning |
|---|---|---|
| `SGLANG_GATE_TREE` | `/opt/sglang/local-prod-v1.1-candidate` (`gate_common.py:40-41`) | tree under test |
| `SGLANG_GATE_MODEL` | `/data/models/qwen35-9b-w4a16` (`:42-43`) | model path |
| `SGLANG_GATE_PORT` | `30165` (`:44`) | gate server port (never 30000/30164) |
| `SGLANG_GATE_L3_ROOT` | `/data/l3` (`:50`) | namespace root |
| `SGLANG_GATE_RUN_ID` | UTC-stamp+pid (`gate_common.py:167-169`) | unique namespace |
| `SGLANG_GATE_RUN_DIR` | `/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916` (`:36-38`) | reports/logs |
| `SGLANG_GATE_PYTHON` | `<tree>/env/bin/python` (README `:65`) | interpreter fallback |
| `SGLANG_GATE_NAMESPACE_REUSE` | unset | `=1` allows reusing a populated namespace |
| `SGLANG_GATE_LOCK` | `/tmp/opencode/gpu-3090.lock` (`:47`) | canonical lock |
| `SGLANG_GATE_GPU_UUID` | `GPU-2e3ed202-3655-d919-0a64-259209bc6587` (`:45-46`) | GPU pin |

Per-gate knobs advertised by README `:70-73`: `--hc-size`, `--host-pool-margin`, `--chain-tokens`,
`--prompt-tokens`, `--filler-tokens`, `--max-fillers`, `--sweep-tokens`, `--sweep-requests`,
`--extent-size`, `--file-size`, `--min-index-fraction`, `--min-restore-fraction`, `--expect`,
`--namespace`. (`--reloc-reserve-slots` is documented in the F1 prose, README `:246` and `:292`.)

> Note: the README example tree is `local-prod-v1.1.2-candidate`; the campaign runtime under test is
> `/opt/sglang/local-prod-v1.2.1-candidate` (see §E). The tree is a parameter, not a default.

### A.3 Verdict artifacts, exit codes, verdict vocabulary

- **Gate A** writes `gate-a-result.json` in `<SGLANG_GATE_RUN_DIR>/gateA/`
  (`gate_a_content_integrity.py:125-127` tag/run_dir; `:793-796` `gate.save("gate-a-result.json")`).
- **F1** writes `gate-a-f1-result.json` in `<SGLANG_GATE_RUN_DIR>/gateA-F1/`
  (`gate_a_f1_cold_l1.py:148-150`; `:1080-1083`).
- **F2** writes `<SGLANG_GATE_RUN_DIR>/f2/f2-primer-result.json`, `f2-recover-result.json`, and the
  controller’s `f2-combined-result.json` (`f2_restart_recovery.py:122-151`, `:173-175`, `:437-438`,
  `:673-676`).
- RUN_DIR default: `/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916` (`gate_common.py:36-38`).
- Exit codes / vocabulary (`gate_common.py:122-123`, mirrored in README `:362-372`):
  `PASS=0`, `FAIL=1`, `INVALID=2`, `PENDING=3`, `ERROR=4`, `BLOCKED=5`.
  `finish()` precedence: PENDING → BLOCKED → ERROR → INVALID → (missing required ⇒ INVALID) →
  FAIL → PASS (`gate_common.py:300-340`).

### A.4 Do the gates launch their own server? — **YES (all three, plus canary)**

- `gate_common.build_server_args()` emits `python -m sglang.launch_server --model-path …
  --host 127.0.0.1 --port <port> --tp-size 1 --mem-fraction-static 0.92
  --max-total-tokens 65536 --kv-cache-dtype fp8_e4m3 … --hicache-size <hc> …`
  (`gate_common.py:1444-1471`; the `--max-total-tokens 65536` literal is `:1452`).
- `gate_common.launch_server()` sets `PYTHONPATH=<tree>/src/python`,
  `CUDA_VISIBLE_DEVICES=<GPU UUID>`, and `SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR=<namespace>`
  then `Popen(..., start_new_session=True)` (`gate_common.py:1474-1495`).
- Each gate takes the canonical lock itself (`gc.acquire_lock`, `gate_common.py:350-394`; Gate A
  `:218-219`, F1 `:211-212`, F2 primer `:226-237` / recover via state). README `:50-53` confirms:
  “Each gate takes the canonical GPU lock … itself … and never signals another agent’s server.”
- **Consequence:** the one-shot campaign must have production release the GPU. Owner ruling records
  the same: `ledger.md:7927-7929` (`production stop.sh` → confirm `:30000` down → server PID gone →
  flock released → GPU clean → campaign takes canonical lock) and `ledger.md:7895-7899`.

### A.5 Campaign runner / prior invocations found read-only

- Prior campaign output directories (evidence the steps were run individually):
  `/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916/` contains `gateA/` (`gate-a-result.json`),
  `gateA-F1/` (`gate-a-f1-result.json`), `f2/` (`f2-combined-result.json`), `canary/`
  (`canary-result.json`), plus `final-campaign-20260917/` and `final-campaign-20260917-r2/`.
- `final-campaign-20260917/` holds the only exec'd driver: `canary_driver.py`
  (`/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916/final-campaign-20260917/canary_driver.py`,
  157 lines) with per-step console logs (`gateA.console.log`, `f1.console.log`, `f2.console.log`).
  Its `sys.path.insert(0, "/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916")` (line 7)
  means it imports the **deployed** `gate_common`, not repo bytes.
- **No executable six-step orchestrator exists anywhere searched** ⇒ **ABSENT**.

---

## B. Definitions of the last two steps

### B.1 “production-profile native 128K performance” = **Gate B**

- **Authoritative definition** (owner ruling sequence includes it): `ledger.md:7871-7873`
  (“production-profile native 128K perf”); owner scheduling earlier: `HANDOFF-20260917-PRODUCTION-PRIORITY.md:300`
  (“native 128K Gate-B”).
- **Acceptance thresholds / what must be recorded** — verbatim from
  `.memory/phase2-hicache-design/work/GATE-B-PASS-AND-F1-ROOT-CAUSE-20260916.md:89-96`:
  - `aggregate(B)/aggregate(L1-hot) = 0.926 (64K) / 0.932 (128K) ≥ 0.85`
  - `plateau(B)/plateau(L1-hot) = 0.997 (64K) / 1.001 (128K) ≥ 0.85`
  - inter-forward gap returns to baseline (`0.124 ms` @128K vs `0.093` L1-hot; Python `8.89 ms`)
  - `100–290 ms` stalls materially disappear (`0` Native vs `193 / 35.14 s` Python)
  - GPU util recovered (`94.4 %` Native vs `58.4 %` Python, `97.9 %` L1-hot)
  - no durability regression (Phase 0.1 both arms + Phase 0.2 arm-B oracle).
  Also recorded per-cell: `completed=4`, `errors=0`, `tier_established=true`, fp8_e4m3, MTP off,
  port `30164`, write volume equal at 64K (10.648 GB both arms)
  (`/var/log/sglang/local-prod-v1.1/phase9-native-ab-20260916/REPORT.md:58-70`).
- **The only driver is NOT in the repo**: `run_native_ab.py` /
  `analyze_native_ab.py` under `/var/log/sglang/local-prod-v1.1/phase9-native-ab-20260916/run/`
  (`run_native_ab.py:34-63`). It pins:
  - `OVERLAY=/tmp/opencode/l3-native-ab-inst-20260916`, `WORKTREE=/tmp/opencode/l3-native-src-20260916`
    (`:36-38`) — **not** the frozen v1.2.1 tree;
  - `PY=/opt/sglang/local-prod-v1/env/bin/python` (`:39`) — a third tree;
  - `POOL=262144`; `SPECS=[{context:65536,batch:2,output_len:1024},{context:131072,batch:2,output_len:2048}]`
    (`:50-54`); `ARMS=[("L1hot","A",None),("Python","C","0"),("Native","C","1")]` (`:56-60`);
  - port `30164` (`:17,127`), canonical lock `/tmp/opencode/gpu-3090.lock` (`:40,80-107`);
  - imports `fleet_matrix_v2` from
    `/var/log/sglang/local-prod-v1/phase8/l3-cadence-forensics-20260916` (`:62`).
  - Production-profile server argv captured in `run/Native/arm_C/server-meta.json`:
    `--max-total-tokens 262144 --kv-cache-dtype fp8_e4m3 --max-running-requests 21
    --enable-hierarchical-cache --hicache-size 32 --enable-ready-horizon
    --hicache-storage-backend extent --hicache-storage-prefetch-policy wait_complete` with
    `SGLANG_L3_NATIVE_WRITE_PATH=1` (`run_native_ab.py:179-182`).
- **Conclusion:** the *definition* (Gate B, thresholds) is cited; the *tool* is **ABSENT from the
  authoritative repo**, tests a `/tmp` overlay (not the v1.2.1 frozen runtime), and uses a different
  port/pool/profile than production. A one-shot campaign cannot invoke step 5 “from authoritative
  repo bytes” without authoring/porting a driver. Candidate sources listed:
  `3090-dev/gates/native-poc/{smoke_ab.py,smoke_ab_meta.py}` (native **POC smoke**, 2.0/3.2 KB,
  not the 6-cell A/B), and the Gate B run dir above.

### B.2 “short canary”

- Definition (README, subject to in-flight change): “Short canary (existing driver, no storage
  oracle; run last)”, invoked as
  `TREE=$TREE PORT=30165 OUT=$H/final-campaign-20260917/canary.json CUDA_VISIBLE_DEVICES=""
  $PY $H/final-campaign-20260917/canary_driver.py` (`README.md:45-48`).
- The driver (deployed only, **not in repo**):
  `/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916/final-campaign-20260917/canary_driver.py`
  - env `TREE` (required), `PORT` (default 30165), `OUT` (required file) (`:10-12`);
  - `N=32` offered, `MAX_NEW=256`, shared 2000-token prefix + 170 random suffix tokens (`:13-14,29-31,79-83`);
  - pass checks (`:117-125`): `canary_errors_zero`, `canary_offered_32`,
    `canary_cache_telemetry_present`, `canary_max_running_le_21`, `canary_no_cross_session_bleed`;
  - writes `OUT` and `<RUN_DIR>/canary/canary-result.json` (`:136,151-153`).
- Reference verdict: `canary-result.json` = `PASS`, 32/32, `max_running=21`,
  `device_hit=63488`, `storage_hit=0` (`/var/log/.../canary/canary-result.json:1-79`).
- **ABSENT from repo**: `find` for `canary_driver.py` returns nothing under the repo
  (only unrelated product `python/sglang/.../kv_canary/*`). The README points at a
  `/var/log` artifact.

---

## C. Production stop / restore sequence

### C.1 Exact scripts and command forms

Two byte-identical repo copies exist; the live scaffold is materialised from
`3090-dev/tools/prod-service/`:

- repo: `3090-dev/tools/prod-service/bin/{common,preflight,start,supervise,stop,status,switch}.sh`
  (`ls`); `3090-dev/deploy/bin/` holds an identical copy (`cmp -s` of `start.sh` ⇒ **IDENTICAL**).
- live: `/tmp/opencode/prod-service-20260917/` — `common.sh:13` defaults
  `SCAFFOLD_ROOT=/tmp/opencode/prod-service-20260917` and sources `$SCAFFOLD_ROOT/conf/service.env`
  (`common.sh:13-15`); `PROD-SERVICE-README-20260917.md:242-255` documents this layout; handoff §6
  says `/tmp` is discardable and the repo is the authoritative source.

Commands (`PROD-SERVICE-README-20260917.md:83-106`; `conf/service.env:15-17`):

```bash
bash bin/stop.sh prod      # stop production (port 30000)
bash bin/start.sh prod     # start production (port 30000)
bash bin/status.sh [--json]# read-only verify
bash bin/switch.sh test    # identity-checked handoff (prod<->test); never runs two
bash bin/preflight.sh <tree>
```

### C.2 Identity checks each performs

- **stop.sh** (`tools/prod-service/bin/stop.sh`): reads `$PID_DIR/$role.pid` / `.tree`; kills the
  **supervisor first** only if `pid_matches "$sp" "supervise.sh" "$role"` (`:28-35`); then
  `stop_owned_server` (`:37`) which refuses unless the cmdline contains
  `launch_server --port <port>` (`common.sh:190-194`) **and** references the expected tree
  (`common.sh:195-198`); SIGTERM → wait 240 s → SIGKILL → wait 60 s (`common.sh:200-215`).
  Publisher (`stop.sh:64-69`): if no material GPU holder and lock not held → `state_write_free "stopped"`.
- **start.sh** (`tools/prod-service/bin/start.sh`): (1) `preflight.sh "$TREE"` (`:41`);
  (2) refuse if `gpu_material_holder` non-empty (`:43-48`); (3) refuse if port bound (`:52-56`);
  (4) allocate a unique namespace via `allocate_namespace` (`:58-64`; helper `common.sh:274-293`
  calls the tree’s own `$tree/tools/l3_namespace.py --allocate --task-id … --root … --json`);
  (5) `setsid bash supervise.sh` and wait for `state/ready/<role>.ready` (`:73-99`).
- **supervise.sh** holds the canonical lock for the server lifetime (`:37-39`), launches the tree
  launcher, polls `/proc/<pid>/environ` until `PYTHONPATH` is inside `$TREE/src/python` and
  `CUDA_VISIBLE_DEVICES == $GPU_UUID` (`:79-118`), waits `/health==200` (`:120-136`), publishes the
  served tree’s identity from `$TREE/manifest/identity.json` (`:63-69`), then `wait`s (`:156-162`).
- **preflight.sh** (`tools/prod-service/bin/preflight.sh`; codes P1-P7 documented
  `PROD-SERVICE-README-20260917.md:178-192`): tree layout, recorded manifest digest vs bytes,
  launcher sha, launcher-enforces-source-identity-gate, launcher-enforces-namespace-gate,
  `sglang.__file__` inside `<tree>/src/python`, reserved-store presence.

### C.3 Verification order: port down → PID gone → flock released → GPU clean

| signal | exposing command/script | citation |
|---|---|---|
| port 30000 down | `port_is_free <port>` / `wait_port_free <port> <timeout>` (fresh socket bind); `status.sh` `probe_health` `GET /health` | `common.sh:219-243`, `status.sh:15-21,79-86` |
| server PID gone | `[ -d /proc/$pid ]`; `stop.sh` waits on supervisor; `stop_owned_server` loops to `/proc` disappearance; `status.sh` `alive` | `stop.sh:44-48`, `common.sh:186-215`, `status.sh:30-32` |
| flock released | `lock_is_held` — a **fresh** python process does `fcntl.flock(LOCK_EX\|LOCK_NB)` and prints `true/false`; also `lock_holder_json` | `common.sh:132-151`, `status.sh:40-44` |
| GPU clean | `gpu_material_holder` = `nvidia-smi --query-compute-apps` filtered to `>= 2048 MiB`; `gpu_compute_apps` full list | `common.sh:247-264`, `status.sh:45-46,72-76` |

One read-only command shows all four: `bash bin/status.sh --json` (lock + GPU + per-role pid/health,
`status.sh:49-62`). Owner ruling mandates this exact order before the campaign:
`ledger.md:7927-7929`.

### C.4 Is `pkill -f` used anywhere? — **NO**

`grep -rIn "pkill|killall"` over `3090-dev/tools` and `3090-dev/deploy` returns only two **comment**
lines: `tools/prod-service/bin/stop.sh:8` and `deploy/bin/stop.sh:8` (“Never uses broad pkill
patterns.”). The only kill calls are identity-checked `kill -TERM`/`kill -KILL` on a recorded PID
(`common.sh:200-208`, `provider-common.sh:356-367`). Handoff §6 restates the ban:
`HANDOFF-20260917-SESSION-CLOSE.md:145`. (Historical violation noted, not repeated:
`GATE-B-PASS-AND-F1-ROOT-CAUSE-20260916.md:74-88`.)

---

## D. GPU lock + L3 namespace

### D.1 Canonical GPU lock and acquire idiom

- Path: `/tmp/opencode/gpu-3090.lock`
  - harness: `gate_common.py:47` (`LOCK_PATH` default) and `acquire_lock` `:350-394`;
  - production scaffold: `conf/service.env:50` (`GPU_LOCK`; comment says deliberately not
    env-overridable), `common.sh:65-111` (`gpu_lock_acquire`);
  - DEV provider: `deploy/conf/provider.env:87`.
- Idiom (harness): `os.open(lock_path, os.O_RDWR|os.O_CREAT|os.O_CLOEXEC, 0o644)` then bounded
  `fcntl.flock(fd, LOCK_EX|LOCK_NB)`; on success it writes
  `{"owner","pid","generation","acquired"}` through the fd and returns the fd (`gate_common.py:350-394`);
  released via `release_lock` `fcntl.flock(fd, LOCK_UN)` (`:397-408`).
- Idiom (scaffold): open `exec 9<>"$lock_path"` without truncation, `flock -n 9`, then truncate the
  same inode and write the holder record through fd 9; bounded by `GPU_LOCK_TIMEOUT_S=900`,
  `GPU_LOCK_POLL_S=10`; **never signals the incumbent** (`common.sh:65-111`, `service.env:52-53`).
- The owner ruling requires the campaign to acquire this same lock after production releases it
  (`ledger.md:7927-7929`).

### D.2 L3 store namespace policy

- Canonical policy tool: `3090-dev/tools/freeze/pysrc/l3_namespace.py` (installed verbatim into a
  frozen tree as `<tree>/tools/l3_namespace.py`; wrapper `3090-dev/tools/freeze/bin/l3-namespace.sh:24`
  execs it). It **has no clear/delete operation by design** (`l3-namespace.sh:16`,
  `pysrc/l3_namespace.py` doc); modes/flags: `--allocate | --validate`, `--task-id` (required),
  `--root` (default `/data/l3`), `--path`, `--expect-tree-digest`, `--resume-token`, `--json`
  (`l3_namespace.py:306-313`). Refusals: reserved/shared names (exit 4), outside root (5),
  pre-existing unclaimed store (6), symlink (7), claim mismatch (8), non-unique (9)
  (`l3-namespace.sh:8-20`).
- Production uses it twice per start: `--allocate` at start
  (`common.sh:274-293`) and `--validate` inside the frozen launcher
  (`launch.sh.tmpl:122-133`; frozen `/opt/.../launcher/launch.sh:126-128`).
- The gate harness has its **own** equivalent allocator, `gate_common.resolve_namespace(base_root,
  gate, rid, reuse)` → `<L3_ROOT>/<TASK_ID>/<gate>-<rid>`; it refuses a namespace resolving inside
  the shared production store and refuses a populated namespace unless
  `SGLANG_GATE_NAMESPACE_REUSE=1` (`gate_common.py:1368-1384`; `TASK_ID="phase9-gates-final-20260916"`
  `:34`).
- “Never share a namespace” operationally: one task/run → one unique store; the shared store is
  never read/written/cleared; no store-clear endpoint is called — Gate A-F1’s `/flush_cache` resets
  in-memory state only (`README.md:320-333`). The frozen identity records the same rule
  (`/opt/sglang/local-prod-v1.2.1-candidate/manifest/identity.json` `namespace_policy`), and the
  production service env repeats it (`service.env:62-66`).

### D.3 Which store is READ-ONLY / never-clear; where the campaign namespace lands

- Read-only / never-clear reserved store: **`/data/l3/local-prod-v1.1`**
  - harness: `gate_common.PRODUCTION_STORE` `:49`, refusal `:1376-1378`;
  - production scaffold: `service.env:66` (`RESERVED_L3_STORE`), `start.sh:62-64` refuses it;
  - policy tool: `l3-namespace.sh:9-12`;
  - handoff §5.2 (`HANDOFF-20260917-PRODUCTION-PRIORITY.md:271-273`).
- Campaign’s own namespaces land at:
  `SGLANG_GATE_L3_ROOT` (default `/data/l3`) `/phase9-gates-final-20260916/<gate>-<run-id>` —
  i.e. `/data/l3/phase9-gates-final-20260916/gateA-<rid>`, `gateA-F1-<rid>`, `f2-<rid>`,
  `canary-<rid>` (`gate_common.py:34,50,1368-1384`; observed example
  `canary-result.json:18` = `/data/l3/phase9-gates-final-20260916/canary-canary-20260917T092529Z-304612`).
- Note: current free space warning on `/data` (119 G left) and the extent store only-grows history
  are recorded in `work/EPOCH-RESUME-20260917-R2.md:92`.

---

## E. Identity pins for this campaign

### E.1 Runtime under test (frozen tree) — authoritative identity

`/opt/sglang/local-prod-v1.2.1-candidate/manifest/identity.json` (read-only), verbatim fields:

- `"SOURCE_COMMIT": "b2bbd6ea28"` (`identity.json:21`; also `identity-pins.json` `SOURCE_COMMIT`)
- `"TREE_HASH": "3bd285d51e3fdb0c338400dd0203bf8d131f26504baf1076084eea372849f7c8"` (`:22`)
- `"LAUNCHER_HASH": "38487942de63cb56249dae5080d2caef281364dcbac6c92ac53b1ff916672914"` (`:2`)
- `"RUST_SOURCE_DIGEST": "51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376"` (`:19`)
- `"LOADED_SO_HASH": { bytes:578264, sha256:"f1f0c0d3634f3e11891d6632790fc9301167d2e9168b2e441506684846220750", … }` (`:3-16`)
- `"name": "LOCAL-PROD-v1.2.1"`; `"status": "FROZEN"`;
  `tree_manifest_sha256 = 3bd285d5…` (`identity-pins.json:1-20`).

### E.2 Exact identity/preflight invocations

| purpose | exact invocation | citation |
|---|---|---|
| Frozen-tree source identity (used by the launcher on every start) | `env CUDA_VISIBLE_DEVICES=999 PYTHONDONTWRITEBYTECODE=1 <tree>/env/bin/python <tree>/tools/preflight_identity.py --tree <tree> --pid self --all --json` (requires `PYTHONPATH=<tree>/src/python` for `--pid self`) | `launch.sh.tmpl:99-106`; frozen `launcher/launch.sh:99-106`; parser `pysrc/preflight_identity.py:230-247`; exit codes `:17-24` |
| External, independent freeze preflight (engine + external pins + namespace + launcher repin) | `<repo>/3090-dev/tools/freeze/bin/preflight.sh --tree <tree> --run-id <run-id> --l3-root /data/l3 --json` | parser `bin/preflight.sh:60-75`; engine `:113-136`; pins `:138-194`; namespace `:196-204`; launcher repin `:206-226`; exit codes `:22-33` |
| Native `.so` build identity the loader selects | `<tree>/env/bin/python <repo>/3090-dev/tools/freeze/pysrc/rust_identity.py --tree <tree> --json [--package l3-native-wal --library l3_native_wal --python-module sglang.srt.rust_extensions._l3wal]` | parser `rust_identity.py:156-163`; docstring `:1-17` (note: `--verify-with-loader` is mentioned in the docstring but **not** in the parser) |
| Telemetry validator | `<tree>/env/bin/python <tree>/tools/validate_telemetry.py <jsonl...>` | frozen `/opt/.../tools/validate_telemetry.py:115-136`; usage `:118`; exit codes `:8`; pinned hash `identity-pins.json` `tools_sha256.validate_telemetry.py = 63246815…89f8` |
| DEV-provider deploy-tree identity (separate lane, not the production runtime) | `python3 3090-dev/deploy/bin/provider-tree-id.py check <deploy> <commit> <repo> <artifact...>`; `provider-start` G1/G2 gates | `provider-tree-id.py:136-144`; `provider-start:9-13,80-100`; `provider-common.sh:70-113` |

**ABSENT:** the repo working tree contains **no** `validate_telemetry.py`
(`find` returns nothing); it exists only inside frozen trees and as pinned metadata
(`3090-dev/tools/freeze/pins/*-pins.json`). `preflight_identity.py` exists in the repo only under
`3090-dev/tools/freeze/pysrc/` (source) and in frozen trees (`<tree>/tools/`).

### E.3 Harness identity vs runtime identity — recorded separately?

- **Runtime identity surfaces:** `manifest/identity.json` + `manifest/identity-pins.json`, the
  launcher’s three gates (`launch.sh.tmpl:96-133`), `<tree>/tools/preflight_identity.py`, and the
  DEV provider’s `provider-tree-id.py` manifest. Every gate report also records the runtime
  `tree` and a `preflight_import` block (`gate_common.preflight_import` at `:182`, used in Gate A
  `:160-162`).
- **Harness identity surface:** the C3 commit (repo commit) per `ledger.md:8072-8090`; the owner
  ruling requires them recorded **separately** (`ledger.md:7923-7926`).
- **GAP:** the gate verdict JSON does **not** currently record a harness commit/hash/version.
  `gate_common.py` defines `HARNESS_DIR` but uses it only to locate helper scripts (`:35`, `:419`,
  `:1293`, `:1317`); `grep` for `harness|HARNESS|version|sha256` finds no self-identity field.
  Therefore a result artifact binds the *runtime tree* but not the *harness bytes* that produced
  it — a traceability gap for the one-shot campaign (see Defects).

---

## F. Abort / cleanup conditions

### F.1 Per-gate abort behavior (code paths)

- **Gate A**: top-level `try/except GateBlocked|GateInvalid|Exception` then
  `finally:` `gc.stop_server(proc, console)` and `gc.release_lock(lock_fd)`
  (`gate_a_content_integrity.py:475-490`). Intermediate L3→RECOVERED restart stops s1 explicitly
  and requires `/proc` gone (`:378-387`).
- **F1**: same pattern — `except` at `:597-604`, `finally` stops the server and releases the lock
  (`gate_a_f1_cold_l1.py:606-612`).
- **F2**: `--phase all` runs primer and recover as **separate subprocesses**
  (`f2_restart_recovery.py:120-153`); primer’s `finally` stops its server and releases the lock
  (`:427-433`); recover’s `finally` does the same (`:633-639`). Primer deliberately SIGTERMs server
  #1 while still holding the lock, then proves `/proc/<pid>` gone, a fresh probe still sees the lock
  held, and the port free (`:400-416`); lock is released only when the primer process exits.
- `gc.stop_server` kills the **process group** (`os.killpg`) SIGTERM → bounded SIGKILL, then closes
  the console fh (`gate_common.py:1529-1569`).
- On a lock-window timeout the gates return `PENDING` (rc 3) without launching
  (`gate_common.finish` precedence `:307-308`).

### F.2 What cleanup is required after INVALID/abort

- Normal abort: the gate’s own `finally` already stopped the server and released the lock; the
  unique namespace is intentionally **left in place** as evidence (no clear path exists,
  `gate_common.py:1368-1384`; `README.md:320-333`).
- **Hard-death case (observed, not hypothetical):** if the *driver* process dies before its
  `finally`, its `start_new_session=True` server survives and keeps port 30165 LISTEN. Recorded
  incident: driver pid 1488437 died, lock was in fact FREE, but orphan server pid 1488800
  (`sglang.launch_server --port 30165`) plus children remained, holding ~18 GB
  (`work/EPOCH-RESUME-20260917-R2.md:17-31`). Cleanup therefore requires an **identity-checked**
  stop (terminal→KILL of the pgid), then verify `/proc` gone + lock free + all ports free + GPU free
  (`EPOCH-RESUME-20260917-R2.md:46`, `:17-31`). Do **not** use `pkill` (`HANDOFF-20260917-SESSION-CLOSE.md:145`).
- After an aborted run the campaign must not silently re-run: the owner ruling binds the campaign to
  “exactly one” run (`ledger.md:7871-7873`); a re-run requires a fresh authority.

### F.3 Preserved / aborted store must not be overwritten — documented rule

- `README.md:329-330`: “The preserved `pre-gate4-store/` copy and `/data/l3/local-prod-v1.1/**` are
  never read, written, or deleted.”
- `README.md:320-333` + `gate_common.resolve_namespace` refusal of a populated namespace
  (`:1379-1382`) ⇒ a new run cannot reuse/overwrite a preserved run’s store unless
  `SGLANG_GATE_NAMESPACE_REUSE=1` is explicitly set.
- The r2 INVALID artifact is explicitly preserved as real evidence:
  `work/EPOCH-RESUME-20260917-R2.md:91` (“r2 的 INVALID artifact **保留**”);
  `/var/log/sglang/.../gateA/*` (07:41 INVALID evidence) must not be overwritten
  (`EPOCH-RESUME-20260917-R2.md:128`).
- The preserved round-1 WAL was hash-verified intact after a prior abort
  (`GATE-B-PASS-AND-F1-ROOT-CAUSE-20260916.md:90-92`).

---

## IGNITION TABLE

Every cell traceable to a citation, or marked **ABSENT / subject to in-flight harness change**.
“TREE” = `/opt/sglang/local-prod-v1.2.1-candidate`; “REPO” =
`/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`; “PY” = `$TREE/env/bin/python`;
`CUDA_VISIBLE_DEVICES=""` on the driver (README `:25-26`).

| # | Step | Exact command (from authoritative repo bytes unless noted) | Verdict artifact | Required evidence |
|---|---|---|---|---|
| 0 | Pre-campaign identity + release | `bash /tmp/opencode/prod-service-20260917/bin/stop.sh prod` → verify `:30000` down (`port_is_free`), PID gone (`/proc`), flock free (`lock_is_held`), GPU clean (`gpu_material_holder`) → capture `$TREE/manifest/identity.json` + run `preflight_identity.py --tree $TREE --pid self --all --json` | none (identity captured into campaign log) | owner sequence `ledger.md:7927-7929`; scripts `stop.sh:17-69`, `common.sh:132-264`; identity `identity.json`; preflight `launch.sh.tmpl:99-106` |
| 1 | Gate A 64K | `CUDA_VISIBLE_DEVICES="" $PY REPO/3090-dev/gates/production/gate_a_content_integrity.py --tree $TREE --port 30165 --prompt-tokens 65000 --hc-size 8` (README example passes only `--tree/--port`; defaults `--prompt-tokens=65000`, `--hc-size=8`) | `$SGLANG_GATE_RUN_DIR/gateA/gate-a-result.json` | README `:33-34`; argparse `gate_a_content_integrity.py:59-84`; save `:793-796`; verdict/exit `gate_common.py:122-123,300-340`. **Subject to in-flight harness change.** |
| 2 | Gate A 128K | **ABSENT** — no citable invocation. Current `build_server_args` hardcodes `--max-total-tokens 65536` (`gate_common.py:1452`) and Gate A asserts only `>=64K` (`gate_a_content_integrity.py:184-185`); no `--context-length`/`--max-total-tokens` knob exists; README describes only “two >=65K prompts” (`README.md:13,33`). Candidate (not repo, not v1.2.1): ad-hoc `run_gate_a_native.py` under `/var/log/sglang/.../phase9-native-ab-20260916/run/`. **Subject to in-flight harness change** | `…/gateA/gate-a-result.json` if it gains 128K support | owner sequence `ledger.md:7871-7873`; blockers above; in-flight edit mtimes `2026-09-17T20:36Z` |
| 3 | F1 real post-wrap | `CUDA_VISIBLE_DEVICES="" $PY REPO/3090-dev/gates/production/gate_a_f1_cold_l1.py --tree $TREE --port 30165 --expect fixed` (optionally `--reloc-reserve-slots 2` default) | `$SGLANG_GATE_RUN_DIR/gateA-F1/gate-a-f1-result.json` | README `:36-37`; argparse `gate_a_f1_cold_l1.py:67-104` (`--expect`, `--reloc-reserve-slots`); save `:1080-1083`. **Subject to in-flight harness change.** |
| 4 | F2 true restart/rebuild | `CUDA_VISIBLE_DEVICES="" $PY REPO/3090-dev/gates/production/f2_restart_recovery.py --tree $TREE --port 30165` (default `--phase all` ⇒ primer then recover) | `$SGLANG_GATE_RUN_DIR/f2/f2-primer-result.json`, `f2-recover-result.json`, `f2-combined-result.json` | README `:42-43`; argparse `f2_restart_recovery.py:55-76`; controller/save `:120-153`, `:673-676`. **Subject to in-flight harness change.** |
| 5 | production-profile native 128K perf (= Gate B) | **ABSENT from repo.** Only known driver: `python3 /var/log/sglang/local-prod-v1.1/phase9-native-ab-20260916/run/run_native_ab.py` (port 30164; overlay `/tmp/opencode/l3-native-ab-inst-20260916`; `POOL=262144`; 64K+128K cells; arms L1hot/Python/Native; `SGLANG_L3_NATIVE_WRITE_PATH=1`) | `…/phase9-native-ab-20260916/run/native-ab-analysis.json` + per-cell `run/<arm>/ctx*/cell.json` (declared verdict doc `REPORT.md`) | thresholds `GATE-B-PASS-AND-F1-ROOT-CAUSE-20260916.md:89-96`; driver `run_native_ab.py:34-63,124-201`; profile `server-meta.json`; owner step `ledger.md:7871-7873`. **Tool not authoritative; overlay ≠ v1.2.1** |
| 6 | short canary | `TREE=$TREE PORT=30165 OUT=$RUN_DIR/canary.json CUDA_VISIBLE_DEVICES="" $PY /var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916/final-campaign-20260917/canary_driver.py` — driver **not in repo**; it `sys.path.insert`s the deployed harness dir (line 7) | `$RUN_DIR/canary/canary-result.json` + `$OUT` | README `:45-48`; driver `canary_driver.py:10-14,117-125,136,151-153`; reference PASS `/var/log/.../canary/canary-result.json:78`. **ABSENT from repo** |
| — | Restore production | after the campaign (any verdict): `bash /tmp/opencode/prod-service-20260917/bin/start.sh prod` → `/health` 200, `/v1/models` 200, inference smoke → `:30000` UP | `state/gpu-owner.json`, `<logdir>/server.console.log` | owner ruling `ledger.md:7930-7933`; README `:90-93`; supervise health `supervise.sh:120-136` |

---

## Result (concise)

- **Steps 1, 3, 4** have a citable CLI surface (README + argparse) **subject to the in-flight
  harness change**; verdict artifacts and exit-code vocabulary are identified.
- **Step 2 (Gate A 128K) is ABSENT** as an invocation: the current harness pins the server to a
  65536-token device pool and only asserts `>=64K`. Whether the in-flight writer adds a 128K knob
  is unknown and was not assumed.
- **Step 5 (native 128K perf) has a documented definition/threshold but no repo tool**; the only
  driver is a `/var/log` artifact testing a `/tmp` overlay and a third tree (`/opt/sglang/local-prod-v1`),
  not the v1.2.1 frozen runtime.
- **Step 6 (short canary) has a reference driver but it is not in the repo** (deployed `/var/log`
  artifact; imports deployed `gate_common`).
- **No six-step campaign orchestrator exists** in repo, `/var/log/sglang`, or `/tmp/opencode`
  (searched read-only).
- Production stop/start is well-defined, identity-checked, and free of `pkill`.
- GPU lock path/idiom and L3 namespace policy are citable and consistent across harness, scaffold,
  and policy tool.

## Defects / blockers (observed, not designed-around)

1. **No campaign runner** → the one-shot campaign has no single executable surface; every step must
   be invoked manually in order (owner ruling `ledger.md:7871-7873`).
2. **Gate A 128K has no invocation surface** in current repo bytes
   (`gate_common.py:1452` fixed 65536; README `:13,33` only `>=65K`).
3. **Gate B driver and short-canary driver are not in the repo**, and Gate B’s driver tests a `/tmp`
   overlay (`run_native_ab.py:36-39`) rather than the campaign runtime `b2bbd6ea28`.
4. **Harness-vs-runtime identity is not recorded separately** in verdict artifacts (no harness
   commit/hash field in `gate_common`/gate reports) — conflicts with the owner’s
   “身份分开记录” constraint (`ledger.md:7923-7926`).
5. **Hard-death cleanup risk**: gates stop their own servers only in `finally`; a killed driver
   leaves an orphan `launch_server` + LISTEN port (observed `EPOCH-RESUME-20260917-R2.md:17-31`).
6. **`/var/log` (read-only evidence) vs campaign outputs**: default `SGLANG_GATE_RUN_DIR` is the
   *same* `/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916` that holds the preserved
   07:41/r2 INVALID evidence; a campaign that does not override `SGLANG_GATE_RUN_DIR` risks
   overwriting preserved artifacts (`EPOCH-RESUME-20260917-R2.md:91,128`).

## Remaining claims / exclusions

- All gate *behavioral* claims (preconditions, verdict semantics, server argv) are marked subject to
  the in-flight harness change; only argparse names, README text, and version-pinned helper paths are
  quoted as stable.
- `run_native_ab.py`’s `inst/cadence` instrumentation and `fleet_matrix_v2` dependency were not
  inspected in depth (out of scope); only the top-level argv/profile/cells were read.
- `/tmp/opencode` was read selectively (identity/deploy/campaign-related paths); it is discardable
  and not authoritative.
- No git operations were performed; branch/HEAD/commit ancestry claims are quoted from `.memory`
  records, not re-derived.
- Searches were limited to repo, `/var/log/sglang`, and selected `/tmp/opencode` paths; other hosts/
  directories were not scanned.
- The `--hc-size`/`--host-pool-margin` arithmetic (README `:77-123`) was not independently re-derived.

## Terminal state: DONE
