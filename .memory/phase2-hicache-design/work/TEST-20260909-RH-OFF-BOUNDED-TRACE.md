ENTRY: ACCEPT

# TEST-20260909-RH-OFF-BOUNDED-TRACE

```text
status: done
task_id: T3060-RH-OFF-BOUNDED-TRACE-20260909
orchestration_epoch: 20260909-rh-ab7
role: tester
target: root@i-1.gpushare.com:27460, RTX 3060, PID 100040, 127.0.0.1:30000
ready_horizon: OFF (enable_ready_horizon=False)
verdict: COMPLETE bounded replay; suitable for RH-ON comparison under the same bounded protocol
```

## Verdict and scope

The bounded RH-OFF replay is complete. All five client requests reached a terminal
state using the required 180-second timeout: `w` and `z` returned HTTP 200, while
`x`, `y`, and `q` were classified as terminal client timeouts at approximately
180 seconds. Request-correlated service/probe telemetry was available for all five
RIDs, and the post-run PID, health, storage invariant, and fatal scans completed.

This replay is suitable as the RH-ON comparison baseline when RH-ON uses the same
five-way workload and 180-second bounded timeout. It is not a successful-response
latency baseline for `x`, `y`, and `q`; their response status/latency and response
cache fields are missing because the client timed out. Missing fields below are
explicitly not interpreted as zero.

Only the authorized remote HTTP requests and read-only process, environment, log,
metrics/probe, and storage inspection were used. No service restart/kill, source
change, cache clear/alteration, seed change, or 3090 access was performed. The only
local write was this report.

## Preflight evidence

Preflight timestamp: `2026-09-09T14:20:13.531750726+08:00`.

- PID `100040` was alive and listening on `127.0.0.1:30000`; `/health` returned
  HTTP 200.
- The command line showed the Qwen3.5-4B AWQ model, `--max-running-requests 1`,
  hierarchical file HiCache, and no ready-horizon flag. The process command line
  and the clean-restart record both show `enable_ready_horizon: False`.
- `/proc/100040/environ` contained
  `SGLANG_HICACHE_FILE_BACKEND_STORAGE_DIR=/hy-tmp/hicache-qwen35-4b-p4-retry-20260909`.
- Seed before replay: `du -sb` = `23051071488` bytes; regular files = `550080`.
- Immediately before requests, at `2026-09-09T14:20:13.531750726+08:00`, log
  offsets were:

  ```text
  /tmp/sglang3060-rh-off-clean-restart-20260909.log  29533 bytes, 92 lines
  /tmp/t38c-probe.log                              153424932 bytes, 175420 lines
  ```

## Exact workload and commands

The request harness was sent to the remote interpreter through this SSH command:

```bash
ssh -i /home/dev-codex/.ssh/sglang_3060_ed25519 -p 27460 \
  -o BatchMode=yes -o StrictHostKeyChecking=no root@i-1.gpushare.com python3 -
```

The remote Python harness used five concurrent workers, a barrier, and this exact
request construction for `ch` in `x,y,z,w,q`:

```python
rid = f"TEST20260909RHOFFBOUNDED_{ch}_{batch_id}_{time.time_ns()}"
payload = {
    "rid": rid,
    "text": (ch + " ") * 55000,
    "sampling_params": {"temperature": 0, "max_new_tokens": 1},
}
urllib.request.urlopen(req, timeout=180)
```

The replay batch ID was `1788934855379755042`. The five RIDs were:

```text
TEST20260909RHOFFBOUNDED_x_1788934855379755042_1788934855382532731
TEST20260909RHOFFBOUNDED_y_1788934855379755042_1788934855384564219
TEST20260909RHOFFBOUNDED_z_1788934855379755042_1788934855386155438
TEST20260909RHOFFBOUNDED_w_1788934855379755042_1788934855387775939
TEST20260909RHOFFBOUNDED_q_1788934855379755042_1788934855388846292
```

Client requests began at `2026-09-09T14:20:55.389630–14:20:55.391483+08:00`.
The client timeout was 180 seconds; no timed-out request was waited on beyond that
bound.

## HTTP outcomes

| RID suffix | terminal time (+08:00) | client wall seconds | status | response cache fields |
|---|---:|---:|---|---|
| `w` | 14:21:44.485465 | 49.094363 | HTTP 200 | `cached_tokens=54976`, device `0`, host `0`, storage `54976` |
| `z` | 14:22:44.898234 | 109.507534 | HTTP 200 | `cached_tokens=54976`, device `0`, host `0`, storage `54976` |
| `x` | 14:23:55.411199 | 180.019736 | client `TimeoutError` | response fields missing; not zero |
| `q` | 14:23:55.469631 | 180.079970 | client `TimeoutError` | response fields missing; not zero |
| `y` | 14:23:55.493011 | 180.102502 | client `TimeoutError` | response fields missing; not zero |

The two HTTP 200 responses had `prompt_tokens=55001`, one output token, and
`finish_reason.type=length`. The timeout rows did not produce a client response.

## Request-correlated HiCache/Mamba telemetry

Probe source: `/tmp/t38c-probe.log`. Service-log source:
`/tmp/sglang3060-rh-off-clean-restart-20260909.log`. Correlation used fixed-string
RID matching followed by bounded parsing/aggregation; the raw service log contains
458,902 matching lines, mostly repeated admission records.

For every RID, the probe emitted one `pc_storage_query` with:

```text
query_suffix_len=55000
kv_hit_pages=54976
storage_hit_count=54976
sidecar_hits.kv=54976
sidecar_hits.mamba=54976
```

The probe also emitted `pc_prefetch_enter` gate records with
`matched_len=0`, `match_end=55000`, and `suffix_len=55000` for every RID.

Per-RID service/probe result:

| RID | restore/prefetch outcome | wait/retry telemetry | Mamba/device/host details |
|---|---|---|---|
| `w` | One prefetch issued for 55000. Restore was `PARTIAL`, granted 54976 for `shortfall`; `prefetch_io_finished=54976`, `prefetch_finalize completed_tokens=54976 mode=cache`, `restore_success n_tokens=54976`, and `restore_ready` were recorded. | No wait-budget retry or failure record. Admission records: 32,135; one eventual `can_run=1`. | Probe: 54 `pc_get_v2` KV batches totaling 54,976 hits, one sidecar record with `hit_pages.mamba=1`, and one `pc_l3_host`. HTTP response explicitly reports device 0/host 0/storage 54,976. No Mamba error record. |
| `z` | Same successful path as `w`: one issue; partial 54976/55000; I/O finished/finalized 54976; restore success/ready. | No wait-budget retry or failure record. Admission records: 66,194; one eventual `can_run=1`. | Probe: 54 `pc_get_v2` KV batches totaling 54,976 hits, one Mamba sidecar hit-page record, and one `pc_l3_host`. HTTP response explicitly reports device 0/host 0/storage 54,976. No Mamba error record. |
| `x` | One prefetch issued. 121 `WAIT` dispositions were `denied_rate_limit` with `granted=0`; one `WAIT` state was `HOST_ALLOC`; one retry had `cause=capacity`; prefetch revoked with `miss_reason=alloc_failed`, storage hit 54976. One `restore_recompute cause=timeout final_storage_survivability=host` occurred at 14:23:55. No restore success/finalize record. | Admission records: 119,997; one `can_run=1` record occurred after the client timeout. | Probe storage query confirms KV/Mamba storage hits 54,976. `pc_get_v2` and HTTP device/host response counters are missing, not zero. No Mamba error record. |
| `y` | One prefetch issued. 121 `WAIT` dispositions were `denied_rate_limit` with `granted=0`; one `WAIT` state was `HOST_ALLOC`; one retry had `cause=capacity`; prefetch revoked with `miss_reason=alloc_failed`, storage hit 54976. No restore success/finalize record in the captured post-run log. | Admission records: 119,862; all captured records were `can_run=0`. | Probe storage query confirms KV/Mamba storage hits 54,976. `pc_get_v2` and HTTP device/host response counters are missing, not zero. No Mamba error record. |
| `q` | One prefetch issued. 121 `WAIT` dispositions were `denied_rate_limit` with `granted=0`; one `WAIT` state was `HOST_ALLOC`; one retry had `cause=capacity`; prefetch revoked with `miss_reason=alloc_failed`, storage hit 54976. No restore success/finalize or recompute record in the captured post-run log. | Admission records: 119,921; all captured records were `can_run=0`. | Probe storage query confirms KV/Mamba storage hits 54,976. `pc_get_v2` and HTTP device/host response counters are missing, not zero. No Mamba error record. |

The timeout rows had no `hybrid_discard` record. The only recompute record was the
`x` timeout recompute noted above. Absence of a Mamba error or hybrid-discard event
means no matching event was recorded; it is not a numeric zero assertion.

## Post-run invariants and fatal scan

Post-run timestamp: `2026-09-09T14:24:21.508320109+08:00`.

- PID `100040` remained alive with the original launch command and listener on
  `127.0.0.1:30000`.
- `/health` returned HTTP 200.
- Seed after replay: `du -sb` = `23051071488` bytes; regular files = `550080`.
  This exactly matches the preflight snapshot.
- Final log offsets were:

  ```text
  /tmp/sglang3060-rh-off-clean-restart-20260909.log  77621731 bytes, 459016 lines
  /tmp/t38c-probe.log                              154027528 bytes, 177032 lines
  ```

- Fatal scan commands were read-only scans of the post-preflight deltas:

  ```bash
  tail -n +93 /tmp/sglang3060-rh-off-clean-restart-20260909.log \
    | grep -E "Traceback|AssertionError|OOM|ImportError|FileNotFoundError|Killed"
  tail -c +153424933 /tmp/t38c-probe.log \
    | grep -E "Traceback|AssertionError|OOM|ImportError|FileNotFoundError|Killed"
  ```

  Both scans returned no matches.

## Evidence classification

- Product defect: none established by this verification task. The replay observed
  `alloc_failed`, capacity waits, and three client timeouts; causal diagnosis is
  outside this tester dispatch.
- Test defect: none in the bounded replay. The client timeout was exactly 180
  seconds or less by configuration, and timeout was treated as terminal.
- Infrastructure issue: none. SSH, HTTP, log/probe parsing, post-run health, and
  storage inspection all completed without infrastructure failure.
- Missing evidence: response-level device/host/status/latency fields for `x`, `y`,
  and `q` because the clients timed out; probe `pc_get_v2` records for those rows
  were not emitted. These are missing fields, not zero values.

## Artifacts, followups, and open issues

Artifacts/evidence:

- This report.
- Remote restart log: `/tmp/sglang3060-rh-off-clean-restart-20260909.log`.
- Remote request-correlated probe: `/tmp/t38c-probe.log`.
- Captured client output for all five RIDs, including exact terminal times,
  status/timeout classification, and wall latency.
- Pre/post process, health, storage-count, log-offset, and fatal-scan command output
  in the task execution record.

Summary: complete bounded RH-OFF replay. All five RIDs have correlated storage,
KV, Mamba-sidecar, prefetch, restore, wait, retry, admission, and post-run evidence
to the extent emitted by the service. Two requests completed successfully from the
client perspective; three reached the mandated terminal timeout and are represented
as bounded timeout outcomes.

Followups: none required for this dispatch. Any additional replay, RH-ON run, or
causal debugging requires a fresh Task ID.

Open issues:

- Timeout rows cannot support successful-response latency comparison because the
  client response never arrived.
- No `hybrid_discard` event was observed; this is an absence of telemetry, not a
  claim that an uninstrumented path could not have discarded anything.

```text
status: done
artifacts: TEST-20260909-RH-OFF-BOUNDED-TRACE.md; remote restart/probe log paths; captured five-RID client output
evidence: bounded 180s replay; complete RID-correlated telemetry; unchanged seed; healthy PID; clean fatal scans
summary: complete bounded RH-OFF baseline; suitable for same-protocol RH-ON comparison
followups: none; new replay or diagnosis requires fresh Task ID
open_issues: timeout rows lack response-level status/latency/device/host fields; no hybrid_discard event observed
```
