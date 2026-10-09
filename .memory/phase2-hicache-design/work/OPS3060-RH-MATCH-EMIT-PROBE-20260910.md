# OPS3060-RH-MATCH-EMIT-PROBE-20260910

```yaml
status: done
final_status: RUNTIME_TELEMETRY_FAILURE_PROBE_BOUNDED_HTTP_400
entry: ACCEPT
task_id: O3060-RH-MATCH-EMIT-PROBE-20260910
invocation_id: 20260910T-FRESH-OPS-PROBE-01
orchestration_epoch: E3060-RH-MATCH-EMIT-20260910
role: devops-executor
capability_level: L4
workdir: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
observed_root: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt
remote_host: root@i-1.gpushare.com:27460
remote_cwd: /root
remote_checkout_binding: /root/sglang-3060-12g-hicache
remote_checkout_git_root_observed: unavailable (git reported not a repository)
remote_service: 127.0.0.1:30000
remote_parent_pid: 127023
accepted_scheduler_sha256: cc63e1319e7c84f525647bc20370e6f8ad84dbdcc5fa70ce531457ace3cb8466
pre_probe_health: 200
post_probe_health: 200
post_probe_parent_pid: 127023
pre_probe_log_offset_bytes: 39854
post_probe_log_offset_bytes: 41951
report_path: /home/dev-codex/workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/OPS3060-RH-MATCH-EMIT-PROBE-20260910.md
```

## Procedure and exact request

The remote service was checked from `/root`; the configured deployment checkout was
`/root/sglang-3060-12g-hicache`. The service PID was `127023`, `/health` returned
HTTP 200, and the remote scheduler SHA-256 exactly matched the accepted deployment
SHA `cc63e1319e7c84f525647bc20370e6f8ad84dbdcc5fa70ce531457ace3cb8466`.

Exactly one request was sent with client hard timeout 90 seconds:

```json
{
  "text": "RHMatchEmitProbeCorrected_03a170_20260910 " repeated 55000,
  "sampling_params": {"temperature": 0, "max_new_tokens": 1}
}
```

The body contained only `text` and `sampling_params`; no `rid` or other unsupported
field was included. The request was POSTed to
`http://127.0.0.1:30000/generate`.

## Outcome and preserved artifacts

- HTTP status: `400`.
- Curl exit: `0` (the HTTP error was returned by the service).
- Raw response: `{"error":{"message":"The input (1265001 tokens) is longer than the model's context length (262144 tokens)."}}`
- Remote raw artifact: `/tmp/rh-match-emit-probe-03a170-20260910.raw`
- Raw artifact bytes: `109`.
- Raw artifact SHA-256: `5fe9d38ce1d3a36deea032771e11911059956aebd3f349afa7451d53280f766d`.
- No abort was required because the request was rejected before model execution and
  did not hang. No retry or second request was made.

## Log join, order, and safety scan

The post-probe log range was bytes `39855` through `41951` of
`/tmp/sglang3060-rh-match-emit-03a170-20260910.log`. It contains the unrelated
health-check `rh_preadmission.v1`/`rh_admission.v2` records and the probe rejection:

```text
[2026-09-09 21:43:40] [http_server] Error: The input (1265001 tokens) is longer than the model's context length (262144 tokens).
[2026-09-09 21:43:40] INFO:     127.0.0.1:40990 - "POST /generate HTTP/1.1" 400 Bad Request
```

No request ID was generated for the rejected probe. Consequently, the request join
contains no probe-correlated records:

- `rh_match_prepare.v1`: absent.
- `rh_stage.v2`: absent.
- `rh_ready_host.v1`: absent.
- `rh_admission.v2`: absent for the probe; the only post-offset admission record is
  for unrelated `HEALTH_CHECK_62dffd6695bf4ffe97836b021b1b7722`.
- Event ordering: not applicable for the rejected probe; no RH event preceded or
  followed another probe-correlated RH event.
- Nullable-field validation: not applicable; no `rh_match_prepare.v1` record existed.
- Fatal/OOM/HTTP5xx/zero-progress markers: no fatal, OOM, traceback, CUDA error,
  segmentation, zero-progress, or HTTP 5xx marker observed in the post-probe range.

Post-probe `/health` remained HTTP 200 and PID `127023` remained alive. No source,
service, GPU process, or HiCache storage mutation was performed.

## Final status

Invocation status: `done`.

The deployment hash and service health remained valid, and the request was safely
bounded, but `rh_match_prepare.v1` was not observable because the service rejected
the 1,265,001-token input before model execution. Runtime telemetry acceptance is
therefore not established. No RH performance, TTFT, or restore-success claim is made.

artifacts: this report; remote replacement log `/tmp/sglang3060-rh-match-emit-03a170-20260910.log`; remote raw probe `/tmp/rh-match-emit-probe-03a170-20260910.raw`
evidence: pre/post cwd and binding checks; service PID; health 200; exact scheduler SHA; pre/post log offsets; exact two-field request schema; HTTP 400 response; raw SHA-256; post-probe log join and safety scan
summary: exactly one corrected-schema probe was safely bounded by HTTP 400 due to context length; service remained healthy; no probe-correlated RH telemetry was emitted
followups: any probe with a shorter accepted input requires a fresh Task ID; do not claim runtime RH value from this invocation
open_issues: `rh_match_prepare.v1` remains unverified because the request was rejected before model execution; no request ID or RH event order exists for this probe
