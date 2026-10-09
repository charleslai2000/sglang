# G3-E3-PRODUCTION-A-VERIFY-20260908

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: G3-E3-PRODUCTION-A-VERIFY-20260908
epoch: E3
role: reviewer
verdict: PASS

## Scope and evidence

Read-only independent verification of the completed Production A run. No remote
state, workload, service, or reviewed artifact was modified. The authoritative
raw subtree is:

`.memory/g3-baseline-20260907/work/raw/g3-e3-prod-a-20260907T145045488234751Z/`

The monitor and launch reports reviewed were
`G3-E3-PRODUCTION-A-MONITOR-20260907.md` and
`G3-E3-PRODUCTION-A-LAUNCH-20260907.md`; smoke identity was cross-checked against
`G3-E3-SMOKE-VERIFY-20260907.md` and its raw subtree.

## Independent checks

- `sha256sum -c SHA256SUMS` passes all 484 listed files (`rc=0`, 484 OK lines).
  The raw subtree has 485 files because `SHA256SUMS` is not self-listed. The
  recorded manifest and checksum digests are consistent with the monitor report.
- `progress.log` has one setup-only failure at line 2 (`cfg: unbound variable`)
  between an initial `RUN_START` and the repaired active `RUN_START`. No
  `POINT_START`, benchmark, result, or server workload follows the failed
  attempt. The active run then has exactly nine `POINT_START`/`POINT_END` pairs,
  all `rc=0`, and `RUN_COMPLETE`; no `HALTED.txt` exists and `COMPLETED.txt`
  exists. The setup attempt is therefore correctly excluded, not mixed into the
  scorecard.
- The nine `command.txt` files have one canonical command, differing only in
  `--max-concurrency`, `--num-prompts`, `--warmup-requests`, and output path.
  Required controls are present in every command: native `sglang`, loopback
  `8035`, `random-ids`, `--random-input-len 2048`, `--random-output-len 512`,
  `--random-range-ratio 1.0`, `--request-rate inf`, `--seed 42`,
  `--tokenize-prompt`, `--output-details`, `--flush-cache`, and
  `--flush-cache-timeout 60`. No ShareGPT dataset or forbidden disable flags
  occur. C/prompt mapping is C1=1/20, C4=4/40, C5=5/50, each repeated three
  times.
- `metadata.txt` and commands show warmup only at C1/repeat-1 (`3`); all other
  repeats show `0`. Each repeat has exactly one flush in its server-log delta.
  C1/repeat-1 has three warmup generates before the flush and 20 measured
  generates after it; the other repeats have exactly their scheduled measured
  generate count (20, 40, or 50).
- Every result is one valid JSONL summary with `completed` equal to the prompt
  count, all `input_lens` exactly 2048, all `output_lens` exactly 512, and no
  non-empty `errors`: C1 20/20/20, C4 40/40/40, C5 50/50/50. Retokenized output
  totals are 9,878, 19,621, and 24,338 respectively, while requested output
  totals are 10,240, 20,480, and 25,600.
- Server-log deltas correlate with the requested concurrency: C1 reaches
  `#running-req: 1`, C4 reaches `#running-req: 4`, and C5 reaches
  `#running-req: 5`. Every generate and flush endpoint is HTTP 200; prefill
  records for measured requests show `#new-token: 2048` and `#cached-token: 0`.
  Per-repeat before/after loads retain `max_running_requests=5` and return to
  zero running/waiting/used tokens.
- Telemetry is present for all nine repeats: `nvidia_smi_dmon.log` has 454–799
  lines and query CSVs have 436–767 lines; all dmon/query/after error files are
  empty. Postflight health and loads are HTTP 200, the service remains PID
  298123, and no wrapper, benchmark, or telemetry process remains.
- No prior RUN_ID strings (`T100230`, `T101034`, smoke, or prior prod-A roots)
  occur in the completed raw subtree. All nine result paths belong to the new
  run ID.

## Service cmdline hash reconciliation

This hard invariant passes. The earlier smoke's `7832781e755152980cc32aafb518117a97cdfa0b08facd0f3611bd2c2b58e9bf`
is the hash of the normalized, space-delimited rendering produced by
`tr '\0' ' ' < /proc/298123/cmdline` (also preserved as
`service/pre/cmdline.txt`). Production A's `750ac48907968dacfd3175b1547a1cd8b9b89cb3eeaa5ebfd625ce221717d200`
is the direct SHA-256 of the NUL-delimited `/proc/298123/cmdline`, as produced
by the wrapper's `sha256sum /proc/$SERVICE_PID/cmdline`. The same current live
read-only check produced 750ac… direct and 783278… after space normalization.
The preserved normalized command text is byte-equivalent to the production
before/after argument rendering; it contains the same model, port, parser,
tool-parser, KV, Mamba, and template flags. There is no argument or service
change; only hash input delimiters differ. All Production A before/after direct
hash files agree at 750ac… (`preflight`, every repeat, and `postflight`).

## Recomputed median scorecard

The following median-of-three values were independently recomputed from each
repeat's raw `result.jsonl` fields and match the monitor report (throughput in
tokens/s; latency in ms):

| config | req/s | in tok/s | out tok/s | total tok/s | TTFT p50/p95/p99 | TPOT p50/p95/p99 | E2E p50/p95/p99 |
|---|---:|---:|---:|---:|---|---|---|
| C1 | 0.047941 | 98.182879 | 24.545720 | 122.728599 | 2885.263/2889.311/2889.619 | 35.195/35.243/35.255 | 20870.928/20894.215/20896.515 |
| C4 | 0.066174 | 135.524626 | 33.881157 | 169.405783 | 8815.626/11468.756/11517.300 | 100.843/111.960/111.968 | 60441.638/60457.602/60457.841 |
| C5 | 0.066771 | 136.746389 | 34.186597 | 170.932986 | 8954.103/14338.957/14399.239 | 129.022/140.169/140.197 | 74889.240/74914.486/74915.513 |

## Findings and acceptance impact

No blocking finding. Production A is accepted and may admit the next gated
stage.

Non-blocking followups:

- All nine benchmark stderr files retain the known post-completion Python
  `multiprocess.resource_tracker` destructor traceback; exit codes, completion,
  and server results remain successful.
- The excluded setup-only `cfg` failure remains in the shared progress history
  for provenance; it produced no measurement and is not part of this scorecard.

artifacts:
- `.memory/g3-baseline-20260907/work/G3-E3-PRODUCTION-A-VERIFY-20260908.md`
- `.memory/g3-baseline-20260907/work/raw/g3-e3-prod-a-20260907T145045488234751Z/`

evidence:
- `SHA256SUMS`, `manifest.txt`, `progress.log`, `launch_manifest.txt`
- `C{1,4,5}/repeat-{1,2,3}/command.txt`, `metadata.txt`, `result.jsonl`,
  `server_log_delta.log`, `before/`, `after/`, and telemetry files
- `preflight/service.cmdline*`, `service/pre/cmdline.txt`,
  `postflight/service.cmdline*`, `postflight/loads_final.body`

summary: PASS; all nine exact points, inputs, outputs, flushes, concurrency
correlation, telemetry, service invariants, checksums, and medians independently
verified. Hash discrepancy is fully explained by delimiter normalization.

followups: retain the resource_tracker traceback and setup-only failure as
non-blocking provenance; no rerun is required for this verification task.

open_issues:
- benign post-completion resource_tracker traceback in benchmark stderr;
- setup-only `cfg` failure retained before the active RUN_START, explicitly
  excluded from measurements.
