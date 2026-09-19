# PROD-RESTORE-M1-20260918

Task: Restore production M1 on port 30000 after the failed M2 cutover stopped it, and verify it
end to end. M1 = frozen tree `/opt/sglang/local-prod-v1.2.1-candidate`, model
`/data/models/qwen35-9b-w4a16`. The M2 cutover was explicitly OUT OF SCOPE.

Scope: Pre-flight (read-only) → start via canonical entrypoint → bounded readiness wait → verify
health/models/chat on loopback + LAN → record PIDs/argv/logs/GPU/lock. No M2, no source/tree edits,
no git changes, no `pkill`, no signal to any pre-existing process.

Result: **DONE — production `:30000` is UP and serving M1.** Entrypoint `start.sh prod` returned rc=0,
cold start 132.0s (identical to the prior recorded cold start), and all Phase-2 checks passed on both
loopback and LAN.

Terminal state: DONE

---

## Exact restore command used (verbatim)

```
timeout 360 bash /tmp/opencode/prod-service-20260917/bin/start.sh prod
```

(`timeout` was applied by me only as a bounded-budget wrapper; the inner command is the canonical
entrypoint from PROD-STATE-PROBE-20260918-R2 §8 and it is the only start command executed. It was run
once, on the first attempt. No retries were needed.)

Verbatim stdout of the restore (captured to `/tmp/opencode/PROD-RESTORE-M1-start.out`):

```
RESTORE_START 2026-09-18T08:42:08Z
[08:42:08] === start role=prod port=30000 tree=/opt/sglang/local-prod-v1.2.1-candidate ===
[08:42:08] preflight: tree=/opt/sglang/local-prod-v1.2.1-candidate
[08:42:08] P2 manifest digest OK: 5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950
[08:42:08] P3 launcher sha OK: 4ae6847066ca0104159cef66f0ae67cd09b940e4d6c8bb1725fe4cdb32ff2ff5
[08:42:08] P4 launcher enforces the source-identity gate
[08:42:08] P5 launcher enforces the per-run L3 namespace gate
[08:42:17] P6 sglang.__file__ OK: /opt/sglang/local-prod-v1.2.1-candidate/src/python/sglang/__init__.py
[08:42:26] WARN: P6 LANDMINE CONFIRMED: without PYTHONPATH, import sglang resolves to /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/__init__.py
[08:42:26] WARN:    This is the stale workspace copy.  The launcher sets PYTHONPATH itself;
[08:42:26] WARN:    never invoke launch_server directly without it.
[08:42:26] P7 shared production L3 store present and MUST NOT be cleared: /data/l3/local-prod-v1.1
[08:42:26] preflight PASS: /opt/sglang/local-prod-v1.2.1-candidate
[08:42:26] port 30000 free
[08:42:26] L3 namespace (unique, never cleared): /data/l3/prod-20260918T084226Z-1761580
[08:42:26] supervisor pid=1761795 (holds the canonical GPU lock for the server lifetime)
[08:44:38] === prod UP ===
role=prod
pid=1761822
supervisor_pid=1761795
port=30000
tree=/opt/sglang/local-prod-v1.2.1-candidate
run_id=prod-20260918T084226Z-1761580
namespace=/data/l3/prod-20260918T084226Z-1761580
lock_generation=20
cold_start_s=132.0
started_at_utc=2026-09-18T08:44:38Z
start.sh_pipeline_rc=0
RESTORE_END 2026-09-18T08:44:38Z
```

Bounded budget: I set a 360 s (6 min) outer timeout. Previous cold start was ~132 s; this run also
took 132.0 s, inside budget with margin. Exactly 1 start attempt, 0 retries.

---

## Phase 0 — Pre-flight (read-only) — verbatim confirmation of the down state

Listener, health, GPU:

```
=== ss :30000 ===
NO LISTENER on :30000
=== curl health ===
curl: (7) Failed to connect to 127.0.0.1 port 30000 after 0 ms: Couldn't connect to server
HTTP 000
=== nvidia-smi ===
index, name, memory.used [MiB], memory.total [MiB], utilization.gpu [%]
0, NVIDIA GeForce RTX 3090, 1 MiB, 24576 MiB, 0 %
=== compute apps ===
pid, process_name, used_gpu_memory [MiB]
```

Lock + owner state (note: the canonical owner file lives under `state/`, not `/tmp/opencode/`):

```
=== lock ===
-rw-rw-r-- 1 ubuntu ubuntu 128 Sep 18 00:21 /tmp/opencode/gpu-3090.lock
{"owner": "supervise-prod-prod-20260918T002151Z-1750622", "pid": 1750851, "generation": 19, "acquired": "2026-09-18T00:21:51Z"}
=== lock flock test ===
LOCK_FREE
=== owner pid alive? ===
ls: cannot access '/proc/1750851': No such file or directory
PID 1750851 DEAD
=== gpu-owner.json ===
{
  "gpu": "GPU-2e3ed202-3655-d919-0a64-259209bc6587",
  "role": "free", "state": "free", "pid": null, "port": null,
  "run_id": "", "l3_namespace": "", "tree": "", "identity": "",
  "lock_generation": 19, "updated_at_utc": "2026-09-18T08:34:25Z", "note": "stopped"
}
```

Paths + no stray processes (runtime-assembled patterns; self+parent excluded):

```
=== model path ===        drwxrwxr-x 3 ubuntu ubuntu 4096 Sep 15 21:34 /data/models/qwen35-9b-w4a16
=== frozen candidate ===  drwxrwxr-x 6 ubuntu ubuntu 4096 Sep 17 18:35 /opt/sglang/local-prod-v1.2.1-candidate
=== process sweep ===     total non-self matches = 0
=== port check ===        no 30000/30001 listener
=== LAN addr ===          eth0 UP 192.168.20.250/24
```

Script reading (summary of what the entrypoint does, with the relevant lines):

- `bin/start.sh` — sources `common.sh`; role `prod` ⇒ `PORT=30000`, `TREE=/opt/sglang/local-prod-v1.2.1-candidate`.
  Runs `preflight.sh`; refuses a material GPU holder (`>=2 GiB`); refuses a busy port; allocates a unique
  L3 namespace; hands off with:
  ```
  setsid bash "$SCAFFOLD_ROOT/bin/supervise.sh" \
    "$ROLE" "$TREE" "$PORT" "$RUN_ID" "$NAMESPACE" "$LOG_DIR" "$START_TS" \
    >>"$LOG_DIR/supervisor.log" 2>&1 < /dev/null &
  ```
  and waits for `state/ready/$ROLE.ready` (`DEADLINE=$(( SECONDS + 2500 ))`).
- `bin/supervise.sh` — takes the canonical flock for the whole server lifetime
  (`gpu_lock_acquire 9 "supervise-$ROLE-$RUN_ID"`); launches the frozen launcher:
  ```
  setsid env \
    SGLANG_PORT="$PORT" \
    SGLANG_PROFILE="${SGLANG_PROFILE:-perf}" \
    SGLANG_RUN_ID="$RUN_ID" \
    SGLANG_L3_ROOT="$L3_ROOT" \
    SGLANG_LOG_DIR="$LOG_DIR" \
    bash "$(tree_launcher "$TREE")" \
    >>"$CONSOLE" 2>&1 < /dev/null &
  ```
  then polls `/proc/<pid>/environ` for `PYTHONPATH=<tree>/src/python` and
  `CUDA_VISIBLE_DEVICES=$GPU_UUID`, waits for `http://127.0.0.1:$PORT/health == 200`
  (`HEALTH_DEADLINE=$(( SECONDS + 2400 ))`), writes `state/runs/prod.run`, touches the ready file, and
  blocks in `wait "$SERVER_PID"` holding fd 9.
- `../launcher/launch.sh` (frozen) — fail-closed identity gate (P2/P3 digests, src-stream sha256
  `c7427132…dafbc`, namespace gate) then `exec "$PY" -u "${ARGS[@]}"` with `PYTHONPATH` set and
  `CUDA_VISIBLE_DEVICES=GPU-2e3ed202-…`. **`/tmp/m1-rollback.sh` was not used** (it only stops M1).

---

## Phase 2 — Verification (all must hold)

### Health — loopback and LAN both 200

```
=== /health loopback ===
HTTP_CODE=200
=== /health LAN 192.168.20.250 ===
HTTP_CODE=200
```

### `/v1/models` — 200, served id present (loopback and LAN identical)

```
HTTP_CODE=200
{"object":"list","data":[{"id":"/data/models/qwen35-9b-w4a16","object":"model","created":1789721083,"owned_by":"sglang","root":"/data/models/qwen35-9b-w4a16","parent":null,"max_model_len":131072}]}
```

### Deterministic chat smoke — `temperature=0`

First two attempts used fixed `max_tokens` of 24 and 256 against a prompt that invited a direct
sentence. Both returned **HTTP 200 but empty `content`** because this model emits `reasoning_content`
first and the reasoning parser consumed the whole token budget (`finish_reason="length"`,
`reasoning_tokens` == `completion_tokens`). That is an **observation about the smoke-prompt/token
budget, not a service failure** — the reasoning text was non-empty and coherent. With a larger fixed
budget the final completion is non-empty and coherent:

Request (`/tmp/opencode/PROD-RESTORE-M1-smoke3.json`):

```json
{"model":"/data/models/qwen35-9b-w4a16","messages":[{"role":"user","content":"What is 2+2? Answer with just the number."}],"temperature":0,"max_tokens":1024}
```

Response, loopback (verbatim, `/tmp/opencode/PROD-RESTORE-M1-smoke3.out`):

```json
{"id":"efb0cceabb034295936170603ba8bcba","object":"chat.completion","created":1789721095,"model":"/data/models/qwen35-9b-w4a16","choices":[{"index":0,"message":{"role":"assistant","content":"\n\n4","reasoning_content":"Thinking Process:\n\n1.  **Analyze the Request:**\n    *   Question: \"What is 2+2?\"\n    *   Constraint: \"Answer with just the number.\"\n\n2.  **Determine the Answer:**\n    *   2 + 2 = 4.\n\n3.  **Format the Output:**\n    *   The user explicitly asked for *just the number*.\n    *   So, I should not include any text like \"The answer is\" or \"4.\". Just \"4\".\n\n4.  **Final Check:**\n    *   Does \"4\" satisfy the constraint? Yes.\n    *   Is it mathematically correct? Yes.\n\n5.  **Construct Output:** 4\n","tool_calls":null},"logprobs":null,"finish_reason":"stop","matched_stop":248046}],"usage":{"prompt_tokens":23,"total_tokens":185,"completion_tokens":162,"prompt_tokens_details":null,"reasoning_tokens":159},"metadata":{"weight_version":"default","weight_versions":[{"version":"default","start":0,"end":162}]}}
HTTP_CODE=200
```

Response, LAN `192.168.20.250` (verbatim, `/tmp/opencode/PROD-RESTORE-M1-smoke3-lan.out`):

```json
{"id":"11c06efff299415d8dd0b079d93c35db","object":"chat.completion","created":1789721108,"model":"/data/models/qwen35-9b-w4a16","choices":[{"index":0,"message":{"role":"assistant","content":"\n\n4","reasoning_content":"Thinking Process:\n\n1.  **Analyze the Request:**\n    *   Question: \"What is 2+2?\"\n    *   Constraint: \"Answer with just the number.\"\n\n2.  **Determine the Answer:**\n    *   2 + 2 = 4.\n\n3.  **Format the Output:**\n    *   The user explicitly asked for *just the number*.\n    *   So, I should not include any text like \"The answer is\" or \"4.\". Just \"4\".\n\n4.  **Final Check:**\n    *   Does \"4\" satisfy the constraint? Yes.\n    *   Is it mathematically correct? Yes.\n\n5.  **Construct Output:** 4\n","tool_calls":null},"logprobs":null,"finish_reason":"stop","matched_stop":248046}],"usage":{"prompt_tokens":23,"total_tokens":185,"completion_tokens":162,"prompt_tokens_details":null,"reasoning_tokens":159},"metadata":{"weight_version":"default","weight_versions":[{"version":"default","start":0,"end":162}]}}
HTTP_CODE=200
```

### PIDs, effective argv, log path

PIDs: main/server **1761822**, scheduler child **1762267**, supervisor/lock holder **1761795**.

```
$ ps -o pid,ppid,pgid,etimes,comm,args -p 1762267
1762267 1761822 1761822 118 sglang::schedul sglang::scheduler

$ tr '\0' ' ' < /proc/1761822/cmdline   # effective argv, matches probe §8 verbatim (minus %q quoting)
/opt/sglang/local-prod-v1.2.1-candidate/env/bin/python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 0.0.0.0 --port 30000 --tp-size 1 --mem-fraction-static 0.92 --max-total-tokens 524288 --context-length 131072 --max-running-requests 8 --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --attention-backend flashinfer --linear-attn-prefill-backend triton --linear-attn-decode-backend triton --mamba-radix-cache-strategy extra_buffer --mamba-ssm-dtype float32 --enable-hierarchical-cache --hicache-write-policy write_back --hicache-storage-backend extent --hicache-storage-prefetch-policy wait_complete --hicache-size 32 --enable-ready-horizon --reasoning-parser qwen3 --tool-call-parser qwen3_coder --enable-metrics --export-metrics-to-file --export-metrics-to-file-dir /tmp/opencode/prod-service-20260917/logs/prod-20260918T084226Z-1761580 --disable-prefill-cuda-graph
```

Log dir: `/tmp/opencode/prod-service-20260917/logs/prod-20260918T084226Z-1761580/`
(`supervisor.log`, `server.console.log`, `sglang-request-metrics-20260918_08.log`).
`supervisor.log`:

```
[08:42:26] canonical GPU lock ACQUIRED generation=20 owner=supervise-prod-prod-20260918T084226Z-1761580 pid=1761795
[08:42:26] supervisor launching prod on port 30000 (tree=/opt/sglang/local-prod-v1.2.1-candidate)
[08:42:51] /proc/1761822/environ PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
[08:44:38] COLD START (launch -> /health 200): 132.0s
[08:44:38] === prod UP: pid=1761822 port=30000 cold_start=132.0s ===
```

### GPU state

```
=== nvidia-smi summary ===
index, name, memory.used [MiB], memory.free [MiB], memory.total [MiB], utilization.gpu [%]
0, NVIDIA GeForce RTX 3090, 22573 MiB, 1552 MiB, 24576 MiB, 0 %
=== compute apps ===
pid, process_name, used_gpu_memory [MiB]
1761822, /opt/sglang/local-prod-v1.2.1-candidate/env/bin/python, 300 MiB
1762267, sglang::scheduler, 22198 MiB
```

### Lock / owner consistency with a live owner

```
=== gpu-owner.json (live) ===
{
  "gpu": "GPU-2e3ed202-3655-d919-0a64-259209bc6587",
  "role": "prod", "state": "held", "pid": 1761822, "port": 30000,
  "run_id": "prod-20260918T084226Z-1761580",
  "l3_namespace": "/data/l3/prod-20260918T084226Z-1761580",
  "tree": "/opt/sglang/local-prod-v1.2.1-candidate",
  "identity": "LOCAL-PROD-v1.2.1",
  "lock_generation": 20, "updated_at_utc": "2026-09-18T08:44:38Z", "note": "serving"
}
=== canonical lock ===
{"owner": "supervise-prod-prod-20260918T084226Z-1761580", "pid": 1761795, "generation": 20, "acquired": "2026-09-18T08:42:26Z"}
=== flock held test (non-blocking, fresh process) ===
LOCK_HELD by another process (expected): [Errno 11] Resource temporarily unavailable
=== lock fd held by live supervisor ===
lrwx------ 1 ubuntu ubuntu 64 Sep 18 08:45 9 -> /tmp/opencode/gpu-3090.lock
```

Lock generation advanced 19→20, owner PID 1761795 is live and holds fd 9; `gpu-owner.json` advanced
from `free` to `held` with the live server pid and the frozen identity `LOCAL-PROD-v1.2.1`. Consistent.

`status.sh` (owner-visible) at 08:45:01Z:

```
 ROLE   PORT   PID      ALIVE   HEALTH  TREE
 prod   30000  1761822  yes     up      /opt/sglang/local-prod-v1.2.1-candidate
 test   30164  -        no      down    -
```

### Negative self-checks (real output)

1. Exactly one `launch_server` process (kernel `/proc/*/cmdline` scan, no grep self-match):
   ```
   launch_server processes: 1
      (1761822, '/opt/sglang/local-prod-v1.2.1-candidate/env/bin/python', '… -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16')
   ```
2. Zero M2/omnicoder processes: `M2 matches: [] count= 0`.
3. No listener on M2/other ports: `none of 30001/30164/30165 listening`.
4. The only `:30000` listener is the M1 server:
   ```
   LISTEN 0 2048 0.0.0.0:30000 0.0.0.0:* users:(("python",pid=1761822,fd=68))
   ```
5. Final re-check at 08:45:13Z: `loopback HTTP 200`, `LAN HTTP 200`.

---

## Defects / blockers

None blocking. Two observations recorded for the orchestrator:

1. **Reasoning parser consumes small `max_tokens`.** With `reasoning-parser qwen3`, a smoke request with
   a small fixed `max_tokens` returns HTTP 200 with empty `content` and non-empty `reasoning_content`
   (`finish_reason=length`). A future smoke must budget enough tokens for the reasoning block (or read
   `reasoning_content`). This is model/parser behavior, not a service defect.
2. **P6 landmine confirmed (expected).** Without `PYTHONPATH`, `import sglang` resolves to
   `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/__init__.py` (live WIP), so the
   launcher's own `PYTHONPATH` is load-bearing. The canonical `start.sh` path sets it; a hand-rolled
   `launch_server` would silently run the wrong source.

The prior incident's trap is confirmed avoided: `/tmp/m1-rollback.sh` (stop-only) was NOT used; the
service was restored with `bin/start.sh prod`.

## Remaining claims / exclusions

- **Not claimed:** anything about M2 (`/data/models/omnicoder-9b-gptq-int4`) — no M2 process, port, or
  launch was attempted or observed.
- **Not claimed:** long-duration stability or throughput of this M1 run beyond the health/models/chat
  checks above; verification window is ~08:44–08:45Z 2026-09-18.
- **Excluded:** any source/tree/git modification, any stop/kill of existing processes, any port other
  than 30000.
- The `/data/l3/prod-20260918T084226Z-1761580` namespace is new and unique (run id
  `prod-20260918T084226Z-1761580`); the shared store `/data/l3/local-prod-v1.1` was not touched.

## Changed-artifact list

- `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/agents/PROD-RESTORE-M1-20260918.md` (this report; only file written under the repo).
- Runtime state written by the service scaffold itself (not by me directly):
  `/tmp/opencode/gpu-3090.lock`, `/tmp/opencode/prod-service-20260917/state/gpu-owner.json`,
  `state/pids/prod.*`, `state/runs/prod.run`,
  `logs/prod-20260918T084226Z-1761580/{supervisor.log,server.console.log,sglang-request-metrics-20260918_08.log}`.
- Scratch evidence files under `/tmp/opencode/`: `PROD-RESTORE-M1-start.out`,
  `PROD-RESTORE-M1-models-lan.json`, `PROD-RESTORE-M1-smoke{,2,3}.json`,
  `PROD-RESTORE-M1-smoke{,2,3}.out`, `PROD-RESTORE-M1-smoke3-lan.out`.
- No product source, tests, frozen tree, or git state changed.

Terminal state: DONE
