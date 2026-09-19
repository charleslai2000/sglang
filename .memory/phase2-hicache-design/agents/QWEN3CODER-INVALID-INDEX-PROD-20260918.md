# QWEN3CODER-INVALID-INDEX-PROD-20260918

Task / Scope / Result / Evidence / Defects or blockers / Remaining claims or exclusions / Terminal state: DONE|BLOCKED

Terminal state: DONE

## Task
Bounded diagnosis of the owner-relayed gateway error
`{"message":"upstream response contained invalid tool calls (invalid index)","type":"invalid_request_error"}`
attributed to the `qwen3_coder` tool-call parser defect class (orphan fragments emitted with
`tool_index = -1`). Answer Q1..Q6 with raw evidence and a recommended safe rollout + runbook.
No product source edits. CPU-only. No GPU, no server stop/start, no port bind, no signal, no
`:30000` interaction.

## Scope
- In scope: local CPU reproduction of `tool_index=-1` on PRE-FIX bytes vs absence on POST-FIX bytes
  through the production entrypoint; causal assessment (PROVEN vs INFERRED); rollout option
  comparison; window runbook (not executed); acceptance evidence.
- Out of scope: editing product source (`python/**`, `test/**`, `3090-dev/**`, `/opt/**`, `/data/**`),
  executing any rollout/freeze, gateway-side observability (host is unreachable from here).
- Artifact: this file. Scratch (all probes/outputs): `/tmp/opencode/qwen3coder-invalid-index-20260918/`.

## Result

### Q1..Q6 table

| Q | One-line answer | Evidence anchor |
|---|---|---|
| **Q1** | **YES, reproduced both directions, CPU-only, no server.** PRE-FIX frozen M2 bytes emit `tool_index=-1` through the *production entrypoint* `FunctionCallParser.parse_stream_chunk`/`parse_stream_end` on orphan `</function>` and orphan `<parameter>` fragments (6 negative items across 3 cases, 0 in the clean control). POST-FIX repo bytes emit **0** negative items and still commit the clean call at index 0 with one complete JSON object. | `frozen-run.txt`, `repo-run.txt`, `fcp-frozen.txt`, `fcp-repo.txt`, `summary-fcp-frozen.json`, `summary-fcp-repo.json`; hashes `92eeaeaf…` (pre) vs `848e0690…` (post) |
| **Q2** | **PROVEN:** the wire object can carry `index:-1` and no SGLang schema forbids it (`ToolCall.model_dump_json()` → `{"id":null,"index":-1,...}`; `protocol.py:678 index: Optional[int]`; `serving_chat.py:2618 index=call_item.tool_index`). **INFERRED, not overclaimed:** the gateway validates the streamed `index` field (non-negative / dense / ordered) and aborts the turn; the gateway is not observable from this host and the string is absent from all on-host software checked. | `WIRE_JSON_NEG` probe; `protocol.py:678`; `serving_chat.py:2618`; string-absence greps below |
| **Q3** | **Plausible and consistent (INFERENCE, strong):** a model turn emitting an `index=-1` tool call makes the gateway abort the stream; the client then produces no assistant output ⇒ empty `task_result`/stub. Same error string appears twice in the live opencode log (21:57:55Z, 12:53:26Z) and matches ledger §87; the server logs `state was deleted in TokenizerManager` in the same second as the client abort. Correlation, not request-id-proven. | opencode.log:135332, opencode.log:179267; server.console.log:6721-6726; ledger §87; probe `fcp-frozen.txt` |
| **Q4** | **Recommended: (a) a NEW M2-only frozen tree carrying the detector fix — detector-only, M1 untouched, ~10–15 min window.** (b) combined HiCache+telemetry window also puts the fix live but touches M1 and is a much larger/longer window; (c) an in-place M2 mini-freeze is the fastest but breaks the frozen-tree-in-place discipline and is emergency-only. Detail below. | Inode/perm/launcher/digest evidence below; `M2-HICACHE-RELEASE-DESIGN-R2` D5/D7 |
| **Q5** | Window runbook below: pre-window offline freeze prerequisites; stop via `stop-m2.sh`; atomic move-aside + freeze at canonical path; start via `start.sh m2`; `/health` + `/v1/models` loopback+LAN; served model id; orphan-fragment acceptance; monitoring; rollback. **Not executed.** | Runbook section below |
| **Q6** | Acceptance: (i) new served tree detector sha == `848e0690…`; (ii) deterministic CPU probe on the new tree bytes → **0** negative indices; (iii) `pytest ...TestQwen3CoderDetector` 30 passed / full file 256 passed (independently re-run here); (iv) live tool-calling smoke accepted with valid indices and no `invalid index`; (v) M1 detector unchanged `92eeaeaf…`. | `oracle-smoke` outputs; pytest runs below |

### Recommended path (ONE)

**Option (a): a new M2-only frozen tree (`/opt/sglang/local-prod-v1.2.1-candidate-M2`, old tree moved
aside) carrying the detector fix; detector-only scope; M1 is NOT touched.**

Why this one:
1. **Smallest blast radius.** M1 and M2 currently share `src` inodes (detector inode `27529144`,
   link count 3, owned by `ubuntu`; `base_format_detector.py` inode `27529108`; `function_call_parser.py`
   inode `27529116`). A new M2 tree produced by `freeze.sh` `rsync -a` (no `-H`) de-hardlinks src, so
   M2 gets its own bytes and M1 keeps inode `27529144` untouched.
2. **Single-purpose acceptance.** Only one behaviour changes (index assignment), so a regression is
   attributable, unlike option (b) where detector + HiCache + telemetry land together.
3. **Short window.** The freeze is CPU/offline-heavy and can be prepared before the window; only the
   stop→start→verify occupies the GPU (cold start measured `111.8 s` for the current M2 run;
   `/tmp/opencode/prod-service-20260917/state/runs/m2.run`).
4. **Keeps the frozen-tree invariant** (the owner's stated preference in ledger §93 (a) and §111.C):
   a fresh tree with fresh manifest/identity + fail-closed dry-run gates, rather than an in-place edit.

**Prerequisites (CPU-only, offline, no GPU; must land before the window):**
- **P1** Complete the M2 branch of `3090-dev/tools/freeze/templates/launch.sh.tmpl` +
  `3090-dev/tools/freeze/bin/launcher-repin.sh` (open task `M2-TOOLING-TEMPLATE-20260918`; **no
  artifact exists yet**). Reason: `freeze.sh` *always* repins from the template
  (`launcher-repin.sh:1`: "ALWAYS renders from templates/launch.sh.tmpl"), and the template is
  currently M1-shaped (`--host 192.168.20.250`, `--served-model-name qwen35-9b-local`,
  `--hicache-storage-backend extent`, `--enable-ready-horizon`, `--hicache-size "$L2_GB"`), which the
  M2 audit profile forbids. Without P1 the M2 freeze cannot pass `launcher-repin` → `freeze.sh` exit 5.
- **P2** Add a detector-only M2 variant to `3090-dev/tools/freeze/pysrc/audit_launcher.py`
  (`LAUNCHER_PROFILES["LOCAL-PROD-v1.2.1-M2"]` currently *requires* `--enable-hierarchical-cache`,
  `--hicache-write-policy write_back`, `--hicache-size 32`; lines 200-252). A detector-only M2
  launcher would fail the audit. P2 is a small repo-local edit in the same file the prior task wrote.
- (If the owner prefers less tooling work and one combined window, choose **option (b)** instead and
  let the detector ride with the HiCache trio; see comparison.)

**Offer to owner:** if they want the HiCache trio folded into the same M2-only tree (their §106
decision), **P2 becomes unnecessary**, but the window must additionally verify
`hicache_attached=True` and N=16 retention 16/16 (longer window). That is the detector+trio variant
of (a). The detector-only variant is the shortest window.

### Option comparison

| Option | What it touches | M1 affected? | Risk | GPU window length | Rollback |
|---|---|---|---|---|---|
| **(a) NEW M2-only frozen tree, detector-only** *(recommended)* | New `/opt/sglang/local-prod-v1.2.1-candidate-M2` (old moved aside): `src/.../qwen3_coder_detector.py` + test, new `manifest/TREE-SHA256.txt` + `identity.json` + pins, re-pinned M2 launcher digest. Repo tooling P1/P2. | **No** — new tree de-hardlinks src; M1 inode `27529144` and sha `92eeaeaf…` stay. | **Medium-low.** Fail-closed launcher gates (GATE 1/2/3) refuse a botched manifest/digest, so a bad update means "M2 won't start", not a bad server. Requires P1/P2. | ~10–15 min (freeze offline-prep + stop ≤240 s graceful + cold start ~112 s + verify). | Keep old tree moved aside + pre-repin launcher copy; `stop-m2.sh`; move old back; `start.sh m2`; re-run preflight. |
| **(a') NEW M2-only frozen tree, detector + HiCache trio** | Same as (a) plus M2 launcher ARGS (add trio, drop the blanket HiCache-forbid gate per D2) and `--hicache-size 32`; no P2 needed. | **No** | Medium. Two behaviour changes in one window; needs retention measurement; disk: ~2 GB de-hardlinked src + stage (host has ~19 GB free, `/` 97%). | ~25–45 min (cold start + N=16 retention + telemetry if also bundled). | Same as (a); plus restore pre-change `launch.sh` and re-verify. |
| **(b) Already-planned combined M2 HiCache + telemetry window** (`M2-HICACHE-RELEASE-DESIGN-R2` D7, 15 steps) | Shared `src` telemetry revision (14 paths), M1 **and** M2 re-frozen, launcher/gate/audit/template tooling, pins, move-aside both trees. | **Yes** — shared src ⇒ M1 must be re-frozen and gets the detector fix + telemetry default flips + reasoning policy. M1 observable contract must be preserved. | **High** — largest surface; mixes 3 acceptance sets; M1 re-freeze changes production M1 bytes; disk-headroom and identity re-pin risks called out in the design itself. | ~30–60+ min (2 freezes, 2 identity verifications, HiCache N=16 retention, telemetry checks, optional M1 smoke). | Multiple backups (both trees, launcher, `service.env`); restore trees + `stop-m2.sh`/`stop.sh prod`; verify gate suite. |
| **(c) In-place targeted M2 mini-freeze (emergency only)** | Existing M2 tree: replace only the detector file (break hardlink first via `cp --remove-destination`/`mv`), regenerate `manifest/TREE-SHA256.txt`, patch `launcher/launch.sh` `EXPECTED_SRC_STREAM_SHA256` + `identity.json`, restore `a-w`. | **No** if the hardlink is broken before the write. | Medium — bespoke identity bump; bypasses `freeze.sh`/audit profile; a mistake is caught fail-closed by GATE 2/3 (M2 won't start). Breaks the "frozen tree = untouched hashes" discipline. | ~8–12 min (no full tree copy). | Backup old detector + manifest + launcher; restore; `start.sh m2`. |

**Reject without owner direction:** (d) do nothing on M2 and fix only the gateway — gateway host
`192.168.1.203:3456` is not observable/authorized from here. (e) switch M2 to a different
`--tool-call-parser` — changes model behaviour, does not fix the confirmed defect.

**Fallback rule:** if P1/P2 cannot land before the window, do **(b)** (already designed, detector
rides along) rather than (c). If M2 is DOWN for an unrelated reason and the only goal is restoring a
working tool-calling service, (c) is the emergency hotfix.

### Q5 — Window runbook for the recommended option (DO NOT EXECUTE)

Owner rules in force: **notify owner before stopping `:30000`** (ledger §97); **report to owner
immediately after `:30000` is back UP** (ledger §109). Use `bash .../bin/stop-m2.sh`; **there is no
`bin/stop.sh m2`** — `stop.sh` accepts only `prod|test|all` and dies with
`unknown target 'm2' (want prod|test|all)` (`bin/stop.sh:4,14,60`).

Legend: **[OFFLINE]** = no GPU, service can stay up; **[WINDOW]** = GPU/service operation; both are
in the single window only where sequenced. All commands below are illustrative for the executing
owner and were NOT run by this task.

**Pre-window offline (P0–P3) — M2 keeps serving**
0. Send the owner pre-stop notification; record current M2 identity:
   `sha256sum /opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh`
   `sha256sum /opt/sglang/local-prod-v1.2.1-candidate-M2/manifest/TREE-SHA256.txt`
   `sha256sum /opt/sglang/local-prod-v1.2.1-candidate-M2/manifest/identity.json`
   `cat /tmp/opencode/prod-service-20260917/state/runs/m2.run`
   Baseline confirmation observed this task: M2 is UP, pid `1851500` (supervisor `1851473`), run
   `m2-20260918T190239Z-1851237`, served id `/data/models/omnicoder-9b-gptq-int4`, cold start 111.8 s.
1. **[OFFLINE] Land P1** (template/repin M2 branch) and **P2** (detector-only M2 audit profile) as
   separate authorized repo edits; run `bash -n` and the audit tool's unit tests.
2. **[OFFLINE] Verify the fix bytes and stage a source tree** for the freeze:
   - `sha256sum python/sglang/srt/function_call/qwen3_coder_detector.py` must be
     `848e0690cb80719e70c7ceedb7c1eb253c879d39a1b7be1cb85645f861a9d151`.
   - Build the stage (copy of the current frozen M2 tree with the two repo files overlaid):
     `qwen3_coder_detector.py` and `test/registered/unit/function_call/test_function_call_parser.py`.
   - Confirm the stage has exactly `src/ launcher/ tools/` (freeze refuses extra top-level entries).
3. **[OFFLINE] Confirm disk headroom** (`df -h /`; ~19 GB free observed) and that no material GPU
   holder exists. Confirm `:30000` is UP and not being used by another window.

**Window — stop, swap, freeze, start**
4. **[WINDOW] Record the PID identity** (do not signal yet):
   `cat /tmp/opencode/prod-service-20260917/state/pids/m2.pid` → observed `1851500`.
5. **[WINDOW] Stop M2 with the identity-checked stopper:**
   `bash /tmp/opencode/prod-service-20260917/bin/stop-m2.sh`
   - It verifies `/proc/<pid>/cmdline` contains `launch_server`, `30000`, the M2 tree and the M2
     model before signalling; signals the supervisor first (releases the canonical GPU lock), then
     SIGTERM the server, waits ≤240 s, SIGKILL only if needed; never broad-pkill; never touches M1.
   - Confirm the GPU lock is released and `state/ready/m2.ready` is cleared
     (`bin/stop-m2.sh` clears `state/pids/m2.*` and `state/ready/m2.ready`).
6. **[WINDOW] Move the old M2 tree aside** (same filesystem rename; preserves rollback):
   `mv /opt/sglang/local-prod-v1.2.1-candidate-M2 /opt/sglang/.pre-detector-<stamp>/M2`
   (create the parent first; a `mv` within `/opt` is an inode rename, ~no extra space).
7. **[WINDOW] Freeze the new M2 tree at the canonical path** via the repo tool:
   `bash 3090-dev/tools/freeze/bin/freeze.sh --build-candidate --src <stage> \
     --dest /opt/sglang/local-prod-v1.2.1-candidate-M2 --identity LOCAL-PROD-v1.2.1-M2 \
     --tree-name local-prod-v1.2.1-candidate-M2 \
     --baseline-tree /opt/sglang/local-prod-v1.1-candidate --allow-production-dest`
   - Inside, `launcher-repin.sh` renders + audits + dry-runs the M2 launcher (GATE 1/2/3); the
     M2 DEST entry in `freeze.sh:127` is already present.
   - The freeze fails closed on: source scope not approved, GGUF delta, copy fidelity, immutability,
     manifest non-determinism, identity/pins, final preflight. Expect exit 0 only.
8. **[WINDOW] Verify the new tree standalone (CPU-only, before serving):**
   - `sha256sum .../src/python/sglang/srt/function_call/qwen3_coder_detector.py` == `848e0690…`
   - `env CUDA_VISIBLE_DEVICES=999 PYTHONPATH=<tree>/src/python <tree>/env/bin/python tools/preflight_identity.py --tree <tree> --pid self --all --json` → `PASS`
   - `bash /tmp/opencode/prod-service-20260917/bin/preflight.sh <tree>` → `preflight PASS`
   - `SGLANG_RUN_ID=<run> SGLANG_L3_MODE=disabled SGLANG_LAUNCH_DRY_RUN=1 bash <tree>/launcher/launch.sh` → dry-run OK, exact argv printed, nothing bound.
   - Run the deterministic orphan-fragment probe against `<tree>/src/python` (see Q6) → 0 negative indices.
9. **[WINDOW] Start M2 from the unchanged scaffold:**
   `bash /tmp/opencode/prod-service-20260917/bin/start.sh m2`
   - `start.sh m2` runs `preflight.sh`, refuses any material GPU holder, refuses a bound port,
     requires `SGLANG_L3_MODE=disabled`, then hands to `supervise.sh` which holds the canonical lock,
     verifies `/proc/<pid>/environ`, waits for `/health` 200 and records cold-start time.
   - Do **not** edit `conf/service.env` while the scaffold is in use (ledger §106.C warning);
     `M2_TREE_DEFAULT=/opt/sglang/local-prod-v1.2.1-candidate-M2` already points at the path we froze.
10. **[WINDOW] Liveness + identity verification (expect exactly the codes/values below):**
    - `curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:30000/health` → `200`
    - `curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://127.0.0.1:30000/v1/models` → `200`
    - `curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://192.168.20.250:30000/health` → `200`
    - `curl -s http://127.0.0.1:30000/v1/models` → `id` == `/data/models/omnicoder-9b-gptq-int4`
      (observed baseline this task).
    - `cat state/runs/m2.run` → new tree path + new run_id; new pid differs from `1851500`.
11. **[WINDOW] Tool-calling smoke (positive + orphan acceptance):**
    - Positive: a streaming `POST /v1/chat/completions` with a `bash` tool definition and a prompt
      that triggers a tool call; assert the response contains `tool_calls` with `"index":0` (or a
      higher non-negative integer) and that the gateway/client accepts it (no
      `invalid index` error).
    - Orphan acceptance: the deterministic requirement is asserted offline against the served tree
      bytes (step 8) because a served model cannot be forced to emit an orphan fragment. Live
      equivalent: monitor the client for `upstream response contained invalid tool calls
      (invalid index)` and the server console for `Tool 'None' is not defined in the tools list.`
      (the only emitter is the detector's `_get_arguments_config` warning) during the smoke window;
      neither may appear.
    - Record: request id, HTTP status, response body snippet, and the served tree detector hash.
12. **[WINDOW] Report to owner** immediately that `:30000` is back UP (ledger §109) with the health
    evidence and the new run_id.

**Rollback (any failure in steps 7–11):**
- `bash /tmp/opencode/prod-service-20260917/bin/stop-m2.sh` (identity-checked; accepts only the
  recorded pid).
- `mv /opt/sglang/local-prod-v1.2.1-candidate-M2 /opt/sglang/.failed-detector-<stamp>/M2` (if the
  new tree was installed) and `mv /opt/sglang/.pre-detector-<stamp>/M2
  /opt/sglang/local-prod-v1.2.1-candidate-M2` to restore the old tree.
- `bash /tmp/opencode/prod-service-20260917/bin/start.sh m2`; re-run step 10 and the pre-change
  identity hashes from step 0.
- M1 rollback is not needed for option (a) because M1 was never touched; if M1 happens to be down it
  is restarted per its own runbook (`start.sh prod`).

**Safety recap for the executing owner:** never `pkill`/`killall`; never edit
`src` in place while M1 shares the inode; `stop.sh m2` does not exist; `:30000` is externally
reachable (ledger §97); no port may be bound outside the scaffold.

## Evidence

### E1. Anchor hashes and shared-inode facts (verified this run)
```
PRE-FIX detector (frozen M2): 92eeaeaf02ac1c1e966a8b9bbd4393141353ca9177265044fe12e250c0e38089
POST-FIX detector (repo):     848e0690cb80719e70c7ceedb7c1eb253c879d39a1b7be1cb85645f861a9d151
M1 detector (frozen):         92eeaeaf02ac1c1e966a8b9bbd4393141353ca9177265044fe12e250c0e38089
inode=27529144 links=3 mode=-r--r--r-- owner=ubuntu:ubuntu
  /opt/sglang/local-prod-v1.2.1-candidate/src/.../qwen3_coder_detector.py
  /opt/sglang/local-prod-v1.2.1-candidate-M2/src/.../qwen3_coder_detector.py
  /tmp/opencode/F39-CAMPAIGN-20260918/test-tree/.../qwen3_coder_detector.py   (third link)
base_format_detector.py:  inode 27529108 links=3 (M1 == M2)
function_call_parser.py:  inode 27529116 links=3 (M1 == M2)
```
`base_format_detector.py` is byte-identical in both trees; line 45 is `self.current_tool_id: int = -1`
in both (this is the inherited seed of the `-1`), and the base `finish()` (`:353`) returns an empty
`StreamingParseResult()` in both. The defect lives in the **detector's** use of the inherited
`current_tool_id`, not in the base path.

Frozen M2 src stream digest (v1 convention) recomputed this run:
`c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc` (== the frozen M2 launcher's
baked `EXPECTED_SRC_STREAM_SHA256`; 14784 files; 7.1 s). Any src change requires re-pinning this.

M2 frozen launcher `/opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh`:
`GATE 2/3` compares the recomputed src stream digest to the baked constant and exits 12 on mismatch;
`GATE 1/3` runs `tools/preflight_identity.py --all`; `GATE 3/3` proves L3 disabled (expects
`l3_namespace.py --validate` exit 6) and **forbids any HiCache argv** (`--enable-hierarchical-cache`
etc.). M2 argv observed live (pid 1851500) contains `--tool-call-parser qwen3_coder`,
`--model-path /data/models/omnicoder-9b-gptq-int4`, `--max-total-tokens 262144`, and has no
`--served-model-name`. sha256 `9a557d5f…21c4` (matches identity.json).

Scaffold sha256: `stop-m2.sh` `3d27a0cd4f728f6c9dd34df252cb6f7c2ca98f2f0f216c902ac49b96c75c3243`;
`start.sh` `7fe92ce17044546f73b7e98e020b2c0034ff8c7a15b02cc2c3e98403c23c6611`.
`bin/stop.sh:4,14,60` = `Usage: stop.sh <prod|test|all>`, `TARGET=...`, `die "unknown target ...
(want prod|test|all)"` ⇒ **`stop.sh m2` does not exist**.

Live state at probe time: `ss -ltnp` → `LISTEN 0.0.0.0:30000 users:(("python",pid=1851500,...))`;
`/proc/1851500/cmdline` is the M2 launch_server; `curl` loopback `/health` 200, LAN
(`192.168.20.250:30000`) `/health` 200; `/v1/models` id `/data/models/omnicoder-9b-gptq-int4`.
No M1 server is running (no other `launch_server` proc).

### E2. Q1 reproduction — detectors directly and through the production entrypoint

Probe files: `probe_frozen.py`/`probe_repo.py` (direct detector),
`probe_fcp.py` (production `FunctionCallParser`), `probe_orphan_smoke.py` (operator-visible shape).
All run with `CUDA_VISIBLE_DEVICES=999`, `PYTHONDONTWRITEBYTECODE=1`, interpreter
`/opt/sglang/local-prod-v1.2.1-candidate-M2/env/bin/python`; `PYTHONPATH` selects the tree; 1-char
chunks; no GPU, no server, no port, no writes outside scratch.

**Methodological correction (important):** an initial `probe_fcp.py` run passed `tools=[]`. The
production `FunctionCallParser` short-circuits on an empty tool list
(`function_call_parser.py:172 if not self.tools: return chunk_text, []`), so it emitted 0 calls for
both trees — a false "no repro". The probe was corrected to pass a real `bash` tool schema; the
production reproduces the defect. All results below are from the corrected probe.

PRE-FIX (frozen M2), production entrypoint (`fcp-frozen.txt`):
```
FCP_FILE=/opt/sglang/local-prod-v1.2.1-candidate-M2/src/python/.../function_call_parser.py
CASE A orphan </function>: text='</function>'
   stream index=-1 name=None parameters='{' normal_text=''
   stream index=-1 name=None parameters='}' normal_text=''
   -> 2 call item(s), 2 with index<0
CASE B orphan <parameter=command>ls -la</parameter>:
   stream index=-1 name=None parameters='{'
   stream index=-1 name=None parameters='"command": "ls -la"'
   -> 2 call item(s), 2 with index<0
CASE C closed frame orphan param:
   text='<tool_call><parameter=command>ls -la</parameter></tool_call>'
   stream index=-1 name=None parameters='{'
   stream index=-1 name=None parameters='"command": "ls -la"'
   -> 2 call item(s), 2 with index<0
CASE D control clean call:
   stream index=0 name='bash' parameters=''
   stream index=0 name=None parameters='{'
   stream index=0 name=None parameters='"command": "ls -la"'
   stream index=0 name=None parameters='}'
   -> 4 call item(s), 0 with index<0
TOTAL negative-index items: 6
```
POST-FIX (repo), production entrypoint (`fcp-repo.txt`):
```
FCP_FILE=/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/.../function_call_parser.py
CASE A/B/C -> 0 call item(s), 0 with index<0
CASE D control -> stream index=0 name='bash' parameters='{"command": "ls -la"}' (1 item)
TOTAL negative-index items: 0
```
Direct-detector runs (`frozen-run.txt`, `repo-run.txt`) show the same: 6 negative items pre-fix,
0 post-fix; the clean call is a single complete-JSON item post-fix.

Operator-visible shape (`orphan-smoke-frozen.txt`): a stray `</function>` in prose followed by a real
call emits `index=-1` (`{`, `}`) **and then** `index=0` for the real call, i.e. the wire stream mixes
negative and non-negative indices in one turn. Post-fix (`orphan-smoke-repo.txt`): only the real
call, `index=0`, complete JSON.

Note: `tool_index` is a plain pydantic `int` (`core_types.py: ToolCallItem.tool_index: int`), so
negative values are accepted with no validation/error anywhere in the frozen tree's OpenAI layer.

### E3. Q2 — wire form and gateway predicate (PROVEN / INFERRED)

PROVEN (wire object): built exactly as `serving_chat.py:2618` does
(`ToolCall(index=call_item.tool_index, function=FunctionResponse(name=None, arguments="{"))`):
```
WIRE_JSON_NEG: {"id":null,"index":-1,"type":"function","function":{"name":null,"arguments":"{"}}
WIRE_JSON_POS: {"id":"call_x","index":0,...}
```
`protocol.py:678` is `index: Optional[int] = None` (no `ge=0`); the only `index < 0` check in the
frozen OpenAI entrypoint is `serving_chat.py:2681` guarding the *unstreamed-args* helper, not the
emitted delta. So SGLang will happily stream `index:-1`.

PROVEN (server accepted the request): `server.console.log:6686`
`[2026-09-17 21:57:51] INFO: 192.168.1.203:34358 - "POST /v1/chat/completions HTTP/1.1" 200 OK`,
immediately followed by the client-side abort at `21:57:55.786Z`.

ABSENCE (marks the string as gateway-side, not on-host): the exact
`upstream response contained invalid tool calls (invalid index)` has **no match** in
(a) frozen M2 `src/python/sglang` (`grep -rn` → no output), (b) frozen M1 `src/python/sglang`
(no output), (c) the opencode binary `/usr/local/bin/opencode` (`grep -aoc` → `0`), (d) opencode
`node_modules`. The provider tree `/opt/sglang/opencodex-provider-2d4e33a832` only contains unrelated
`invalid tool call for %s dropped` lines in `minimax_m2.py`/`minimax_m3.py`. This is the same
host-side greps the earlier QQUESTION hunt performed; it localises the rejection to the remote
gateway `192.168.1.203:3456` (opencode provider `baseURL` read from
`/home/ubuntu/.config/opencode/opencode.json`), which this host cannot observe.

INFERRED (the patch we cannot prove from here): the gateway's tool-call assembler validates each
streamed `tool_calls[].index` and rejects a negative / out-of-range value, aborting the turn. The
strongest justified form is: *"the gateway treats a streamed tool_call index that is not a valid
non-negative (and plausibly dense/ordered) index as an invalid response"*. Cannot be verified from
this host; no request-id-matched capture exists. **Do not overclaim** — only the wire payload and
the string's absence on-host are proven.

### E4. Q3 — orchestration empty-result/stub failure link (INFERENCE)

Live opencode log, two occurrences of the exact string, both on a `modelID=worker` subagent stream:
```
opencode.log:135332  2026-09-17T21:57:55.786Z ERROR ... session.id=ses_f4ea113d9ffe... agent=devops
  mode=subagent error.error.message="upstream response contained invalid tool calls (invalid index)"
opencode.log:179267  2026-09-18T12:53:26.001Z ERROR ... session.id=ses_f4b707571ffe... agent=coder
  mode=subagent error.error.message="upstream response contained invalid tool calls (invalid index)"
```
Same string as ledger §87 (`REASONING-USAGE-TELEMETRY-R3` failed subagent) and ledger §111.
Server-side corroboration of a client abort right after the defect fired: `server.console.log:6721-6726`
```
[2026-09-17 21:57:55] Tool 'None' is not defined in the tools list.
[2026-09-17 21:57:55] Received output for rid='40444f99b0264d8288fca1b02fa1a39f' but the state was deleted in TokenizerManager.
   (x5)
```
`Tool 'None' ...` is the detector's `_get_arguments_config(None, ...)` warning (frozen
`qwen3_coder_detector.py:91`), which is exactly what an orphan fragment with no function name
produces. The `state was deleted in TokenizerManager` lines are the server-side symptom of the client
dropping the stream. Attribution of that specific live pair is second-granularity coincidence
(matches the earlier adjudication: INFERRED, not request-id-proven), but the code+probe proof stands
independently.

Failure-shape correlation already on record (ledger §110.B): large multi-file / tool-call-heavy
tasks produced stub artifacts (`SERVICE-METRICS-MONITOR` 59-line stub,
`M2-HICACHE-FROZEN-PROFILE-DESIGN` 25-line all-TBD stub, `M2-RELEASE-TOOLING-PREREQ` 28-line all-
"(working)" stub) while small bounded tasks succeeded. A gateway that aborts a tool-calling turn on
`index=-1` would leave the invoking orchestrator an empty `task_result`, which matches the observed
stubs. **Judgment: plausible and consistent; causation not proven** (the gateway is unobservable, and
any other invalid tool-call shape would produce the same string).

### E5. Q4/Q5 — rollout facts used

- `freeze.sh` destination allowlist now includes `/opt/sglang/local-prod-v1.2.1-candidate-M2`
  (line 127; repo working-tree diff verified) and refuses to clobber an existing
  `manifest/identity.json`.
- `freeze.sh` build mode `ALLOW_MOD=launcher/launch.sh,tools/validate_telemetry.py,...` and copies
  with `rsync -a --delete` (no `-H`) ⇒ de-hardlinks M2's `src` from M1.
- `launcher-repin.sh` always renders from `templates/launch.sh.tmpl`; the template is M1-shaped
  (host `192.168.20.250`, `--served-model-name qwen35-9b-local`, extent L3 + ready-horizon,
  `--hicache-size "$L2_GB"`). The M2 audit profile
  (`3090-dev/tools/freeze/pysrc/audit_launcher.py:200-252`, DONE this session) requires the HiCache
  trio and forbids storage/prefetch/ready-horizon with a hard fail. ⇒ **P1 (template M2 branch) and
  P2 (detector-only M2 profile) are real prerequisites for a detector-only M2 freeze.**
- `M2-TOOLING-MECH-EDITS-20260918` = DONE: `freeze.sh:127` + the 14-path allowlist
  (`.../local-prod-v1.2-candidate-allowlist.txt`, now 167 lines; includes
  `src/python/sglang/srt/function_call/qwen3_coder_detector.py`). `M2-TOOLING-AUDIT-PROFILE-20260918`
  = DONE. `M2-TOOLING-TEMPLATE-20260918` has **no artifact** and `templates/`/`launcher-repin.sh`
  are unchanged (grep for M2/hicache/profile → no M2 branch).
- `freeze.sh` itself has a pre-existing indentation defect introduced alongside the `-M2` DEST edit
  (lines 124-133 are indented one level deeper than the opening `case`, altering only formatting;
  `bash -n` exit 0; the `esac`/`;;` structure is intact). Flagged for the executing owner; not a
  blocker, not in my write scope.
- Disk: `/` 484 G total, ~19 GB free, 97 % full. A new de-hardlinked M2 tree plus a stage is ~2–4 GB.
  Host RAM ~121 GiB available (from `HOST-CAPACITY-MEASURE`), so host-memory HiCache is feasible.
- `start.sh m2` requires `SGLANG_L3_MODE=disabled` (defaulted from `conf/service.env`), runs
  `preflight.sh`, refuses any material GPU holder and a bound port, then `supervise.sh` holds the
  canonical lock and waits for `/health` 200. `stop-m2.sh` identity-checks pid/cmdline before any
  signal and clears only M2 records.

### E6. Q6 acceptance — independently reproduced test counts

Run this task, `CUDA_VISIBLE_DEVICES=999`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`,
interpreter `/opt/sglang/local-prod-v1.2.1-candidate-M2/env/bin/python` from `/tmp`:
```
POST-FIX repo, TestQwen3CoderDetector :     30 passed, 1 warning in 10.61s
POST-FIX repo, full test file        :    256 passed, 1 warning, 4 subtests passed in 28.00s
PRE-FIX frozen src+test, full file   :    243 passed, 4 subtests passed in 34.39s
```
(256 vs 243 = the 13 new detector tests.) `python -m py_compile` clean was recorded by
`Q3A4-QWEN3CODER-IMPLEMENT-20260918` (base `92eeaeaf…` → after `848e0690…`).

### E7. Related artifacts consulted (read-only)
`QWEN3CODER-SCOPE-ADJUDICATE-20260918.md` §E (5 confirmed defects, acceptance table E4);
`Q3A4-QWEN3CODER-IMPLEMENT-20260918.md` (implementation + hashes + 256 tests);
`M2-HICACHE-RELEASE-DESIGN-R2-20260918.md` D1–D7 (combined-window design, 15-step runbook);
`M2-TOOLING-MECH-EDITS-20260918.md` (DONE), `M2-TOOLING-AUDIT-PROFILE-20260918.md` (DONE),
`M2-RELEASE-TOOLING-PREREQ-20260918.md` (stub), `M2-HICACHE-FROZEN-PROFILE-DESIGN-20260918.md`
(stub); ledger §§87, 93, 94, 97, 106–111.

## Defects or blockers

- **No blocker to the diagnosis.** Q1 is reproduced in both directions on CPU; Q2/Q3 are bounded and
  labelled; Q4/Q5/Q6 are delivered.
- **Blockers a future executing task must clear before option (a) can run (all CPU-only, offline):**
  1. `M2-TOOLING-TEMPLATE-20260918` has no artifact and no edits landed; `templates/launch.sh.tmpl`
     and `bin/launcher-repin.sh` have no M2 branch. Without it, `freeze.sh` for M2 fails at repin
     (template renders the M1 contract; M2 audit profile rejects it).
  2. The M2 audit profile mandates the HiCache trio, so a *detector-only* M2 tree needs either a
     detector-only M2 profile (small `audit_launcher.py` edit) or the trio folded into the tree.
  3. `freeze.sh` has a cosmetic indentation regression at the `-M2` DEST edit (lines 124-133);
     `bash -n` passes, flagged for review.
- **Not a blocker but noted:** the pre-existing `stop.sh` accepts only `prod|test|all`; the runbook
  uses `stop-m2.sh` exclusively.

## Remaining claims or exclusions

- **PROVEN here:** PRE-FIX frozen M2 bytes emit `ToolCallItem(tool_index=-1)` through the production
  `FunctionCallParser` on orphan `</function>` / orphan `<parameter>` fragments; POST-FIX repo bytes
  do not and still commit the clean call at index 0 with complete JSON; the exact wire object can
  carry `"index":-1` and no SGLang-side schema blocks it; the error string is not present in the
  frozen M1/M2 SGLang source, the opencode binary, or opencode `node_modules`; the production M2
  tree carries the defect bytes and the live process uses `--tool-call-parser qwen3_coder`.
- **INFERRED, not proven:** that the gateway `192.168.1.203:3456` rejects `index<0` (or
  non-dense/ordered indices) and aborts the turn; that this is the cause of the orchestration
  empty-result/stub failures; that the recorded live `Tool 'None'` / abort pair is the same request
  as the client error. The gateway is unobservable from this host; no request-id-matched capture.
- **NOT claimed:** that the fix is live (it is not); that the combined HiCache/telemetry release is
  safe or correct (only that it is designed); that the 32 GB HiCache value or any D1/D2/D3 decision is
  optimal; that M1 will remain unaffected by option (b) (it will not); that any acceptance test was
  run against a served M2 (none was run; no window executed).
- **Excluded:** any `/opt/**`, `/data/**`, `python/**`, `test/**`, `3090-dev/**` edit; any
  signal/stop/start; any port bind; any GPU use; any change to M1/M2 frozen trees; any gateway-side
  probing. All probe artifacts live under `/tmp/opencode/qwen3coder-invalid-index-20260918/`.
- **Follow-ons for the orchestrator (not performed; require fresh dispatch):** (i) implement P1/P2
  (template M2 branch + detector-only M2 profile) if option (a) is chosen; (ii) execute option (a) or
  (b) in an owner-notified window; (iii) if the owner wants the combined window, the detector fix is
  already in the repo working tree and only needs to be included in the stage allowlist
  (already present) — no detector change is required at window time.

## Terminal state: DONE
