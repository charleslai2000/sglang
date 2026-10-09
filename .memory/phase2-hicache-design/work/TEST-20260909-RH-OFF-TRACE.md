ENTRY: ACCEPT

# TEST-20260909-RH-OFF-TRACE

```text
status: done
task_id: T3060-RH-OFF-TRACE-20260909
orchestration_epoch: 20260909-rh-ab5
role: tester
target: root@i-1.gpushare.com:27460, RTX 3060, PID 97921, 127.0.0.1:30000
source_bundle_input: 82ab235606
ready_horizon: OFF (enable_ready_horizon=False)
verdict: PARTIAL; terminal HTTP trace completed, but acceptance evidence is incomplete
```

## Scope and preflight

This invocation used only remote HTTP requests and read-only remote process,
environment, storage, and log inspection. I did not restart or kill the service,
modify source, clear or alter storage, or touch the 3090. The only local write
was this report.

Preflight at `2026-09-09T14:06:30.531547903+08:00`:

- PID `97921` was alive (`Sl`) and served `/health` with HTTP `200`.
- The process command had `--max-running-requests 1`, the Qwen3.5-4B AWQ
  model, and the prescribed HiCache file-backend profile.
- The parsed startup `server_args` explicitly contained
  `enable_ready_horizon: False`.
- `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR` was
  `/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`.
- Storage before the trace was `23,051,071,488` bytes and `550,080` files.
- Startup log `/tmp/sglang3060-rh-startup-nvruntime-retry2-20260909.log`
  recorded file-backend creation, application startup completion, and the
  Uvicorn listener on `127.0.0.1:30000`.

The startup scan showed only the known optional-module import notices
(`cutlass`/`torchcodec`) and no startup traceback, assertion, OOM, or kill
record. A post-trace fatal scan and post-trace storage snapshot were not run
because the user instruction was to stop collection once all requests became
terminal.

## Exact workload and harness

The remote command was:

```bash
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  -o BatchMode=yes -o StrictHostKeyChecking=no root@i-1.gpushare.com \
  'python3 -' <<'PY'
import concurrent.futures, datetime, json, time
import urllib.error, urllib.request

chars = ["x", "y", "z", "w", "q"]
endpoint = "http://127.0.0.1:30000/generate"
batch_id = str(time.time_ns())
barrier = __import__("threading").Barrier(len(chars))

def iso_now():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat()

def run(ch):
    rid = f"TEST20260909RHOFFTRACE_{ch}_{batch_id}_{time.time_ns()}"
    payload = {"rid": rid, "text": (ch + " ") * 55000,
               "sampling_params": {"temperature": 0, "max_new_tokens": 1}}
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    barrier.wait(); start_wall = iso_now(); start_mono = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=420) as resp:
            body, status = resp.read(), resp.status
        result = {"char": ch, "rid": rid, "start": start_wall,
                  "end": iso_now(), "wall_s": time.perf_counter()-start_mono,
                  "http_status": status, "response": json.loads(body)}
    except Exception as e:
        result = {"char": ch, "rid": rid, "start": start_wall,
                  "end": iso_now(), "wall_s": time.perf_counter()-start_mono,
                  "error_type": type(e).__name__, "error": str(e)}
    print("RESULT " + json.dumps(result, sort_keys=True), flush=True)

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    [f.result() for f in [pool.submit(run, ch) for ch in chars]]
PY
```

Trace batch ID: `1788934033822239906`.

Important harness defect: the command used a `420` second per-request client
timeout. This is outside the later-required `<=180` second bound. All five
requests nevertheless became terminal, so collection was stopped as directed.

## HTTP outcomes

All requests started concurrently around `2026-09-09T14:07:13.832–.834+08:00`,
returned HTTP `200`, produced one token, and reported `prompt_tokens=55001`.

| key | request ID | end time (+08:00) | client wall s | e2e latency s | cached tokens | device | host | storage | result |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| x | `..._x_1788934033822239906_1788934033824125037` | 14:11:44.881767 | 271.048479 | 270.526141 | 0 | n/a | n/a | n/a | HTTP 200, one token, length |
| y | `..._y_1788934033822239906_1788934033825610785` | 14:08:56.235793 | 102.403040 | 102.265616 | 54,976 | 0 | 0 | 54,976 | HTTP 200, one token, length |
| z | `..._z_1788934033822239906_1788934033826809026` | 14:10:44.334844 | 210.501255 | 210.211659 | 0 | n/a | n/a | n/a | HTTP 200, one token, length |
| w | `..._w_1788934033822239906_1788934033828460992` | 14:08:02.063234 | 48.230202 | 48.220917 | 54,976 | 0 | 0 | 54,976 | HTTP 200, one token, length |
| q | `..._q_1788934033822239906_1788934033829751998` | 14:11:14.624174 | 240.793081 | 240.385357 | 0 | n/a | n/a | n/a | HTTP 200, one token, length |

The `cached_tokens=0` rows returned `cached_tokens_details=null`; they are not
classified here as misses because the request-correlated probe extraction was
not completed before collection stopped.

## Required internal telemetry status

The existing remote probe was `/tmp/t38c-probe.log`, but the attempted
request-correlated extraction command had a shell/heredoc syntax error. Per the
instruction to stop once all requests were terminal, I did not retry collection.
Therefore the following required fields are **missing evidence for this run**:

- per-RID `query_suffix_len`, `kv_hit_pages`, and `storage_hit_count`;
- per-RID device/host/storage hit counters beyond the HTTP response fields;
- KV/Mamba sidecar hit/error records;
- restore success/failure event records;
- wait reason, HOST_ALLOC/admission/queue timing, and retry telemetry;
- recompute/hybrid-discard event records;
- post-trace service fatal scan;
- post-trace storage bytes/file count.

No value in the table above should be read as a substitute for those internal
telemetry fields.

## Suitability for RH-ON replay

The request shape and five-key concurrency pattern are suitable to replay, and
the service remained responsive through five terminal HTTP outcomes. The trace
is not suitable for a directly comparable RH-ON run under a `<=180s` client
timeout without changing the observed timing envelope: x, z, and q completed
after 180 seconds (210.5s, 240.8s, and 271.0s). A replay harness must use the
required bounded timeout and explicitly classify those client-side timeouts.

## Artifacts, evidence, followups, and open issues

Artifacts/evidence:

- This report.
- Remote startup log: `/tmp/sglang3060-rh-startup-nvruntime-retry2-20260909.log`.
- Remote probe log: `/tmp/t38c-probe.log` (not re-parsed after the harness
  extraction command failed).
- Captured terminal client output for all five RIDs in the task execution log.

Summary: RH-OFF preflight passed and the exact five-way HTTP workload completed
with HTTP 200 for all requests. Two responses reported complete 54,976-token
storage hits; three reported zero cached tokens after long waits. Internal
per-RID telemetry, post-run storage, and post-run fatal scan remain unverified.

Followups require a fresh Task ID: rerun the same trace with a client timeout
`<=180s`, then collect the per-RID probe/service telemetry and post-run storage
snapshot before declaring the OFF baseline replay-ready.

Open issues:

- Product defect: none established by this trace.
- Harness defect: client timeout was `420s`, violating the requested bound.
- Missing evidence: internal telemetry, post-run storage invariant, and
  post-run fatal scan.
- The trace must not be used as a complete RH-OFF baseline or as an RH
  conclusion.
- Extra work requires a fresh Task ID.

```text
status: done
artifacts: TEST-20260909-RH-OFF-TRACE.md plus captured five-response client output; remote startup/probe log paths recorded
evidence: PID/health/RH-OFF/storage preflight; exact five-request workload; five HTTP 200 terminal outcomes; response-level cache timing
summary: terminal trace completed, but not acceptance-complete due 420s timeout and missing internal/post-run evidence
followups: fresh bounded-timeout replay with complete telemetry extraction
open_issues: harness timeout violation; missing per-RID internals, post-storage snapshot, and post-trace fatal scan; no RH conclusion
```
