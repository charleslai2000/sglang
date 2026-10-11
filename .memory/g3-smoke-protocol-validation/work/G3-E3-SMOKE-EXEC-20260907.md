# G3-E3-SMOKE-EXEC-20260907

ENTRY: ACCEPT

invocation_status: blocked
task_id: G3-E3-SMOKE-EXEC-20260907
epoch: E3
role: devops

## Outcome

The required preflight drain gate passed and exactly one authorized native
SGLang smoke invocation was launched under run ID
`g3-e3-smoke-20260907T135400Z`. The client failed during Python import before
creating any generation request. Per the runbook, no retry or substitute
workload was attempted. Formal Production-A remains blocked pending a new
decision/Task ID that resolves the audit-hook incompatibility.

Remote raw root:
`/data/qwen3-g3-baseline/g3-e3-smoke-20260907T135400Z/`

Local copied raw root:
`.memory/g3-baseline-20260907/work/raw/g3-e3-smoke-20260907T135400Z/`

A prior launcher-quoting failure left a partial preflight-only directory at
`/data/qwen3-g3-baseline/g3-e3-smoke-20260907T135120Z/`; it contains no audit,
client, result, or request evidence and is excluded from this run. Only the
`135400Z` invocation launched the benchmark client.

## Authorized command and identity

The exact command is preserved in `command.txt` under both raw roots. It used:

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

Streaming and ignore-EOS negative flags were omitted. Offline/no-proxy
environment variables and the run-local `sitecustomize.py` audit were set.

Observed preflight identities:

- serving source SHA-256:
  `01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb`.
- model SHA-256:
  `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`.
- service PID: `298123`; pre/post command-line hash:
  `7832781e755152980cc32aafb518117a97cdfa0b08facd0f3611bd2c2b58e9bf`.
- preflight `/health`: HTTP 200; preflight `/v1/loads?include=all` had
  `num_running_reqs=0` and `num_waiting_reqs=0`.
- no old E2 wrapper/descendant, benchmark runner, or dmon process was present
  at admission. The service remained on loopback 8035 with the frozen parser,
  tool-parser, KV, Mamba, and template flags.

The deployed source directory is not a Git checkout (`git rev-parse` recorded
the fatal diagnostic); the serving-file SHA-256 above is the authoritative
source identity captured for this run.

## Observed evidence

The runner exit code was `1`. `result.jsonl` was not created, and the server-log
delta was only:

```text
[2026-09-07 21:56:19] INFO: 127.0.0.1:44784 - "GET /v1/loads?include=all HTTP/1.1" 200 OK
```

The audit log recorded one denied open and no `socket.connect` event:

```text
{"event": "open", "args": "('/data/sglang-qwen35/python/sglang/benchmark/datasets/__pycache__/sharegpt.cpython-312.pyc', 'r', 524288)", "verdict": "deny"}
```

The traceback states that this was import-time loading of the benchmark
dataset module's `.pyc`, before request construction. This is an observed
runtime failure, not evidence that ShareGPT data was downloaded or used.

RSS sampling remained small: peak `VmRSS=1792 kB`, `cap_exceeded=0`. The
postflight service health was HTTP 200 and loads were idle. The full raw audit,
RSS/process samples, stdout/stderr, server-log delta, endpoint snapshots,
process/GPU evidence, manifest, and `SHA256SUMS` are preserved under the raw
roots. Selected local artifact hashes:

```text
audit/events.jsonl       9bfa97c14a62307ccd72df75128a771e221edd84651c51c91b6c79765fb2d895
runner.stderr            849cc23aaa6aece145fa9e7b36ec63c48275ad5bde00dcfdbb028ee1b2ef76af
postflight/server_log_delta.txt
                         e662f1396562a71e82ece3196aa528d9d2c3afb32f006832ccec9d47f3161349
telemetry/rss_samples.txt
                         fcdc284b7c984f4233d1e85bf88f8f04482a677546f1791df7b77f88ccb12d49
```

## Gate disposition

1. No GGUF load/parse: **FAIL/BLOCKED**. The audit denied an import-time
   `sharegpt.cpython-312.pyc` open, so the required no-denied-event gate is not
   satisfied. No `.gguf` open was observed before failure.
2. Small/stable RSS: **observed pass**, peak 1.792 MB, but this is only the
   failed pre-request process and cannot make the smoke pass.
3. No external network/download: **observed pass for this attempt**; no
   `socket.connect` event and no server request beyond local loads GET.
4. Exact server input 2048/output 512: **not exercised**; no `/generate`, result
   JSONL, or server prefill line exists.
5. One successful request: **FAIL**; exit 1, zero generation requests.

## Followups and open issues

- The audit method must be revised or separately authorized so normal import of
  the benchmark's `sharegpt` Python module bytecode is distinguishable from
  opening ShareGPT dataset content. This requires a fresh Task ID; this task
  did not alter product code or retry.
- Tester verification should treat this run as blocked evidence and retain the
  E3 raw root separate from all E2 artifacts.
- No service restart, reconfiguration, model/weight change, or product-file
  edit occurred.

Final invocation status: **blocked**
