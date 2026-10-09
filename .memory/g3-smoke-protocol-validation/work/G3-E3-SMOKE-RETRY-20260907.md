# G3-E3-SMOKE-RETRY-20260907

ENTRY: ACCEPT

invocation_status: blocked
task_id: G3-E3-SMOKE-RETRY-20260907
epoch: E3
role: devops

## Outcome

Exactly one fresh native-SGLang smoke launch was admitted and attempted under
run ID `g3-e3-smoke-retry-20260907T141610Z`. The benchmark client failed during
Python/CUDA import because the required corrected audit hook denied normal
runtime opens. Per the dispatch, no retry, workload change, audit change,
service transition, or formal matrix point was attempted.

Remote raw root:
`/data/qwen3-g3-baseline/g3-e3-smoke-retry-20260907T141610Z/`

Local copied raw root:
`.memory/g3-baseline-20260907/work/raw/g3-e3-smoke-retry-20260907T141610Z/`

The local raw subtree contains 116 files and its `SHA256SUMS` passes
`sha256sum -c`.

## Admission and identity evidence

The final admission record is `preflight/admission2_fail.txt` with value `0`.
It records health HTTP 200, idle loads (`num_running_reqs=0`,
`num_waiting_reqs=0`), no benchmark or dmon process, and the frozen service
identity. The prior partial preflight hash-normalization check is retained in
the same raw root; it did not launch a client. The final admission recheck was
performed immediately before launch.

The exact requested runner argv is preserved in `command.txt` and
`exact_exec_command.txt`, with the benchmark executable:

```text
/data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving
--backend sglang --base-url http://127.0.0.1:8035
--model /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
--tokenizer /data/models/Qwen3.8-27B-GSQ-RCO-GGUF
--dataset-name random-ids --random-input-len 2048 --random-output-len 512
--random-range-ratio 1.0 --request-rate inf --seed 42
--max-concurrency 1 --num-prompts 1 --tokenize-prompt
--output-details --output-file <run>/result.jsonl
--flush-cache --flush-cache-timeout 60 --warmup-requests 0
```

The run used the exact corrected hook from the audit-fix report. Hook SHA-256:
`470fcf33e89c47e3501700148cd3e789c8341ab4ad761d39a6795cf46ba1f9e2`.
The environment and offline/no-proxy settings are in `environment.txt`.
The required compatibility note is in `compat_note.txt`:
`compat_note: requested fixed-length workload; current runner requires random_range_ratio=1.0`.

Observed identity hashes:

- serving source SHA-256: `01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb`
- model SHA-256: `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`
- service PID: `298123`
- pre/post normalized service command hash: `7832781e755152980cc32aafb518117a97cdfa0b08facd0f3611bd2c2b58e9bf`

Postflight health was HTTP 200, loads were idle, and no benchmark or dmon
process remained. The service command and frozen parser/tool-parser, KV,
Mamba, and template flags remained unchanged.

## Failure evidence

The client PID was `429087`; `client_exit_code.txt` is `1`. `runner.stderr`
shows failure before request construction:

```text
RuntimeError: audit denied open: fd-nonfile:pipe:[2750854]
```

The audit checker exit is `1`; it found 415 records and 9 denies. Denied
records include normal `/proc/stat` and `/proc/self/maps` reads, CUDA runtime
`.pyx` lookup paths, and the subprocess pipe FD. No `.gguf` path, ShareGPT
path, or client socket-connect record was observed before the import failure.

No `result.jsonl` was created. The retained server-log delta contains no
`POST /generate`, no flush-cache POST, and no required exact prefill line; it
does contain an unexpected observed `#new-token: 1` prefill line plus the
postflight health/loads/models requests. Therefore the server-side exact-input
and successful-request gates were not exercised and are not passed.

RSS evidence is nonempty and small for the failed import process:
`telemetry/rss_summary.txt` reports 10 samples and peak `1788 kB`. This does
not establish the smoke RSS gate because the workload did not reach request
construction.

## Gate disposition

1. **No client GGUF load/parse:** blocked. No GGUF open was observed, but the
   required audit log has deny records and the client did not complete import.
2. **Small/stable RSS:** observed small (`1788 kB` peak), but blocked as a
   smoke gate because the client failed before dataset/request construction.
3. **No network/dataset download:** no client network event or GGUF/ShareGPT
   data path was observed before failure; the gate is not sufficient to admit
   the workload because the client never ran.
4. **Exact server input:** blocked. No result JSONL, `/generate`, or required
   `Prefill batch, #new-seq: 1, #new-token: 2048, #cached-token: 0` line.
5. **One successful request:** blocked. Client exit 1 and zero measured
   generation requests; postflight service health/idle identity remained good.

## Evidence, followups, and open issues

Evidence artifacts are under the local raw root above, including the exact
hook/hash, full `audit/events.jsonl`, checker output, command/environment,
stdout/stderr, RSS/process samples, pre/post health and loads, service
identity, source/model hashes, server-log byte delta, telemetry, manifest,
and `SHA256SUMS`.

The host still lacks kernel-level tracing (`strace`, `bpftrace`, `tcpdump`, and
`lsof`), recorded in `audit_limitations.txt`; Python audit hooks do not prove
absence of native raw-syscall bypass. The corrected hook's strict
unresolved/non-file FD and runtime-path policy is incompatible with this
deployed torch/CUDA import path as exercised here. A future attempt requires a
new Task ID and an explicitly authorized policy decision; this invocation must
remain blocked. Formal matrices remain blocked.

Final invocation status: **blocked**
