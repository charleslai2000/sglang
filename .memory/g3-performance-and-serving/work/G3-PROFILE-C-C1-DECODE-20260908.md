# G3-PROFILE-C-C1-DECODE-20260908

ENTRY: ACCEPT

status: blocked
invocation_status: blocked
task_id: G3-PROFILE-C-C1-DECODE-20260908
epoch: E4
role: devops-executor

## Result

The authorized C1 decode measurement was fail-closed before any benchmark
traffic. The pre-run guard incorrectly required `pgrep -x sglang`, while the
admitted service is launched as Python (`/data/sglang-qwen35-env/bin/python`)
with argv containing `/data/sglang-qwen35-env/bin/sglang serve`. Per the task
contract, after a repeat failure I did not retry or proceed to repeats 2/3.

No warmup, cache flush, generated request, dmon, or query telemetry was run.
The C1 candidate was left running for the separately dispatched restore task.

## Authorized target and verified state

- Host: `root@175.155.64.171:22109`
- Candidate PID: `470950`; loopback port `18035`
- Exact admitted argv was verified before attempted measurement and remained:
  `/data/sglang-qwen35-env/bin/python /data/sglang-qwen35-env/bin/sglang serve
  --model-path /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
  --host 127.0.0.1 --port 18035 --tp-size 1 --pp-size 1 --trust-remote-code
  --reasoning-parser auto --tool-call-parser qwen3_coder --kv-cache-dtype fp8_e4m3
  --mamba-radix-cache-strategy extra_buffer_lazy --default-chat-template-kwargs
  {"preserve_thinking": false} --log-level info --max-running-requests 4
  --max-mamba-cache-size 20 --cuda-graph-max-bs-decode 4`
- `/v1/loads?include=all`: HTTP 200, idle before attempt, effective
  `max_running_requests=4`, `max_total_num_tokens=148053`
- `/health`: HTTP 200 after halt
- Candidate remained alive after halt; no stop/signal was issued.

## Commands and observed outputs

Initial read-only verification:

```text
ps -p 470950 -o pid=,args=
470950 /data/sglang-qwen35-env/bin/python .../sglang serve ... --port 18035 ...
curl /v1/loads?include=all -> 200; num_running_reqs=0; max_running_requests=4
```

The only execution attempt used the exact plan benchmark command shape with
offline/no-proxy environment, C=4, N=32, ISL=1024, OSL=256, seed=42,
ratio=1.0, output details, flush-cache, and W=3 for repeat 1. Before that
command, the wrapper performed the following identity guard:

```bash
test "$(pgrep -x sglang 2>/dev/null | wc -l)" -ge 1 || {
  echo missing-server > repeat-1/HALTED.txt; exit 20;
}
```

Observed result: exit 20, `HALTED.txt` contains `missing-server`. The guard
was a local executor mistake, not evidence that the service was absent. The
benchmark process was never spawned.

## Artifacts and evidence

Remote measurement subtree (authorized fresh `measure/` subtree):

`/data/qwen3-g3-baseline/e3-profile-c/g3-profile-c1-20260907T182700Z/c1/measure/repeat-1/`

contains `start.utc`, `pre.pid`, and `HALTED.txt`. No JSONL, stdout/stderr,
loads-before/after, dmon, query CSV, or server-log delta exists because the
guard stopped before those steps. A local raw copy is retained at:

`.memory/g3-baseline-20260907/work/raw/g3-profile-c1-decode-20260908T/measure/`

The final remote check observed PID 470950 alive with RSS 1,605,736 KiB and
`/health` HTTP 200. No product/model files changed. No remote files outside
the authorized C1 `measure/` subtree were written.

## Followups

The separately dispatched C1 restore task must stop and restore the candidate.
Any corrected decode execution requires a fresh Task ID; this invocation may
not retry after the failed repeat.

## Open issues

1. No valid C1 measurement exists; repeats 1–3 are unrun.
2. The executor pre-run identity predicate was invalid for the admitted launch
   form. This task is blocked under the fail-closed rule.

Final status: **blocked**
