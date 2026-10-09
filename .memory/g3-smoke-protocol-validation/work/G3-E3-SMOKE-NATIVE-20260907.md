# G3-E3-SMOKE-NATIVE-20260907

status: done
task_id: G3-E3-SMOKE-NATIVE-20260907
orchestration_epoch: E3
role: devops

## Scope and authorization

Executed exactly one native, uninstrumented SGLang serving benchmark request on the
authorized target `root@175.155.64.171:22109`, using only
`http://127.0.0.1:8035`. No service restart, reconfiguration, model/download
operation, product edit, injected policy, audit hook, `sitecustomize`, preload, or
interposer was used. No formal matrix point was executed.

## Run identity

- UTC run ID: `g3-e3-smoke-native-20260907T143437Z`
- Remote run directory: `/data/qwen3-g3-baseline/g3-e3-smoke-native-20260907T143437Z/`
- Local raw copy: `.memory/g3-baseline-20260907/work/raw/g3-e3-smoke-native-20260907T143437Z/`
- Exact command: `command.txt` in the raw copy
- Environment record: `environment.txt` in the raw copy; offline/no-proxy variables only
- Python: `3.12.8`; SGLang: `0.5.10.dev0`
- Serving source: `/data/sglang-qwen35/python/sglang/benchmark/serving.py`
- Serving source SHA-256: `01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb`
- Service PID: `298123`; pre/post command-line SHA-256 both
  `7832781e755152980cc32aafb518117a97cdfa0b08facd0f3611bd2c2b58e9bf`

## Observed evidence

Admission and postflight both returned health HTTP 200. The service remained PID
298123 with the frozen command-line settings (model, parser, tool parser, KV,
Mamba cache strategy, and template setting). Pre/post `/v1/loads?include=all`
were idle (`num_running_reqs=0`, `num_waiting_reqs=0`; postflight also
`num_used_tokens=0`, `num_total_tokens=0`). No benchmark/dmon process was present
in either process snapshot.

The native client exited 0 and emitted exactly one JSONL result/completion:

- `completed=1`
- `input_lens=[2048]`, `output_lens=[512]`
- `total_input_tokens=2048`, `total_output_tokens=512`
- duration `20.379107057s`
- input/output/total throughput `100.4951 / 25.1238 / 125.6189` tokens/s

The server log delta contains one successful flush and one successful generation:

```text
POST /flush_cache?timeout=60.0 ... 200 OK
POST /generate ... 200 OK
Prefill batch, #new-seq: 1, #new-token: 2048, #cached-token: 0
```

The client process was sampled passively. RSS peaked at `1,498,280 kB` and was
below that after request completion; this is far below the server-reported
`11.857 GB` weight footprint. Postflight returned to idle. Passive `ss -tpn`
snapshots showed only the existing SSH/agent connections and SGLang's loopback
scheduler pair; no external client connection was observed. No download was
observed.

Client stderr contained only the known Python 3.12 `multiprocess.resource_tracker`
destructor traceback after successful completion; it did not affect exit status.

## Compatibility note

The requested fixed-length workload is compatible with this runner only with
`--random-range-ratio 1.0`; this invocation used that explicit value. The
explicit tokenizer sidecar and `--tokenize-prompt` produced exact 2048-token
input fidelity. `--disable-stream` and `--disable-ignore-eos` were intentionally
omitted as required.

## Artifacts

The local raw subtree preserves command, environment, stdout/stderr, result JSONL,
pre/post health, loads, service identity, source hash, process/RSS samples,
connections, listener snapshots, and server-log tails. The remote run directory
is preserved under the authorized baseline root. Prior failed smoke artifacts were
not modified.

## Followups

The formal G3/MMQ matrix may begin using this run as the native smoke admission
evidence and should preserve the exact command/identity conventions above.

## Open issues and limitations

- The server log is a shared append-only log; the raw pre/post tails and timestamped
  request lines delimit this run's observed delta, but the entire log is not copied.
- RSS sampling is observational and includes client setup/teardown variation; it is
  not a GPU-memory measurement.
- The benign `resource_tracker` destructor traceback remains present in stderr and
  should be retained in downstream evidence rather than hidden.
