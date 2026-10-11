# G3-E3-SMOKE-RUNBOOK-20260907

ENTRY: ACCEPT

Task ID: `G3-E3-SMOKE-RUNBOOK-20260907`; epoch E3; role `devops`.
Invocation status: **done**.

## Scope and admission state

This is a design-only runbook. I performed no benchmark request, remote write,
download, process control, service change, or product edit. The only local
write is this report.

Use only `root@175.155.64.171:22109`, service `http://127.0.0.1:8035`, and
service PID `298123`. The service must not be stopped, restarted, or
reconfigured.

The read-only audit at 2026-09-07 20:44--20:46 +0800 found the drain gate
not satisfied: old E2 wrapper PID `368185` and runner PID `381226` were active,
`/v1/loads?include=all` reported `num_running_reqs=4`, and the GPU was busy.
No E3 smoke may start until that tree is terminal, the service is idle, and
the GPU has only its resident service application. This task did not stop it.

Observed service identity:

```text
listen: 127.0.0.1:8035; health HTTP 200; SGLang 0.5.10.dev0
source root: /data/sglang-qwen35/python
serving.py SHA-256: 01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb
server log: /data/sglang-qwen35/exp_server_j1_v1.log
model: /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
tokenizer sidecars: tokenizer.json and tokenizer_config.json are present
```

The frozen PID-298123 argv remains the v1 profile: GGUF model path, loopback
8035, TP/PP 1, `--reasoning-parser auto`, `--tool-call-parser qwen3_coder`,
`--kv-cache-dtype fp8_e4m3`, `--mamba-radix-cache-strategy extra_buffer_lazy`,
and `--default-chat-template-kwargs {"preserve_thinking": false}`.

## Runner and tokenizer binding

The deployed runner is exactly:

```text
/data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving
```

Its `--help` exits 0 and includes `random-ids`, `--tokenize-prompt`,
`--flush-cache`, `--warmup-requests`, and `--output-details`. `strace`,
`bpftrace`, `tcpdump`, and `lsof` are unavailable on the host; `ss`,
`timeout`, and `nvidia-smi` are available.

Use an explicit local tokenizer directory in both smoke and formal commands:

```text
--model /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
--tokenizer /data/models/Qwen3.8-27B-GSQ-RCO-GGUF
```

This preserves the served model identity through `--model` while making
`get_tokenizer()` use the sidecar directory instead of the GGUF-aware tokenizer
path. The settled `check_chat_template()` guard still receives the GGUF model
argument, checks sidecars, and must not open the GGUF. If the sidecar directory
is absent or the explicit tokenizer binding fails, abort; do not fall back to
an implicit GGUF tokenizer.

## Exact one-request smoke

After the drain gate passes, create a fresh authorized directory, for example
`/data/qwen3-g3-baseline/g3-e3-smoke-<UTC>/`. Save preflight command/hash,
PID tree, `/health`, `/v1/models`, `/model_info`, `/v1/loads?include=all`, model
stat/hash, source hash, Python/SGLang version, and `serving --help` plus its
SHA-256. Fail closed before launch if any benchmark process exists, loads are
nonzero, PID 298123 is absent, or its command hash differs.

The exact inner command is:

```bash
env PYTHONPATH="$RUN_DIR/audit" SGLANG_AUDIT_LOG="$RUN_DIR/audit/events.jsonl" \
  HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  HF_HUB_DISABLE_TELEMETRY=1 SGLANG_USE_MODELSCOPE=false \
  HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= NO_PROXY='*' PYTHONUNBUFFERED=1 \
  /data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving \
  --backend sglang --base-url http://127.0.0.1:8035 \
  --model /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --tokenizer /data/models/Qwen3.8-27B-GSQ-RCO-GGUF \
  --dataset-name random-ids --random-input-len 2048 --random-output-len 512 \
  --random-range-ratio 1.0 --request-rate inf --seed 42 \
  --max-concurrency 1 --num-prompts 1 --tokenize-prompt \
  --output-details --output-file "$RUN_DIR/result.jsonl" \
  --flush-cache --flush-cache-timeout 60 --warmup-requests 0
```

Record that command verbatim, start/end UTC timestamps, exit code, stdout and
stderr. `--warmup-requests 0` makes the one `POST /generate` the only measured
request. Streaming and ignore-EOS remain enabled by omission of both negative
disable flags. `--flush-cache` is retained; its local `POST /flush_cache` is
not a measured generation request.

Because strace is absent, place this no-product-edit audit module at
`$RUN_DIR/audit/sitecustomize.py` and set `PYTHONPATH` as above before launch:

```python
import json, os, sys
log = open(os.environ["SGLANG_AUDIT_LOG"], "a", buffering=1)
forbidden = (".gguf", "ShareGPT", "sharegpt", "huggingface.co", "modelscope.cn")
def emit(event, args, verdict):
    log.write(json.dumps({"event":event, "args":repr(args), "verdict":verdict})+"\n")
def audit(event, args):
    if event == "open":
        path = str(args[0]) if args else ""
        verdict = "deny" if any(x in path for x in forbidden) else "allow"
        emit(event, args, verdict)
        if verdict == "deny": raise RuntimeError("forbidden client file: "+path)
    elif event == "socket.connect":
        addr = args[1] if len(args) > 1 else None
        ok = isinstance(addr, tuple) and len(addr) >= 2 and addr[0] in ("127.0.0.1", "::1") and int(addr[1]) == 8035
        emit(event, args, "allow" if ok else "deny")
        if not ok: raise RuntimeError("non-service socket: "+repr(addr))
    elif event == "socket.getaddrinfo":
        emit(event, args, "observe")
sys.addaudithook(audit)
```

Run the client in the background and sample `/proc/$CLIENT_PID/status`
`VmRSS`, `/proc/$CLIENT_PID/smaps_rollup` `Rss`, and the process tree every
200 ms into raw files. Abort only the identified runner tree if peak RSS
exceeds 4 GiB or grows by more than 256 MiB after dataset construction; record
the tree and mark the smoke failed. This bound is far below the prior ~42.6-GiB
GGUF parse failure. Never kill PID 298123.

Capture `log_start=$(stat -c%s "$SERVER_LOG")` before launch and copy the
byte-range delta after completion with `dd`; also save pre/post loads and
one-second `nvidia-smi dmon -s pucvmt` plus query samples.

## Independent verifier: all five gates required

Mark `PASS` only when every item below is evidenced. Missing evidence, old-run
interleaving, nonzero exit, OOM, timeout, external socket, GGUF open, or a
server-line mismatch is `FAIL`; formal matrices remain blocked.

1. **No client GGUF load/parse:** exact command has explicit sidecar
   `--tokenizer`; audit has no denied event and no `.gguf` open; process RSS is
   under 4 GiB. A host with strace should additionally retain a scoped
   `strace -ff -e trace=openat,connect` log with no GGUF open.
2. **Small/stable RSS:** raw samples are nonempty, peak is under 4 GiB, and
   final RSS is within 256 MiB of the post-dataset plateau with no unbounded
   growth.
3. **No network/dataset download:** audit socket destinations are only
   loopback `127.0.0.1:8035`/`::1:8035`; offline variables are present; no
   HF/ModelScope/ShareGPT path occurs in artifacts; the server delta contains
   only expected local GETs, one `POST /flush_cache?timeout=60.0`, and one
   `POST /generate`.
4. **Exact server input:** `result.jsonl` has exactly one JSON object with
   `completed=1`, `input_lens=[2048]`, `output_lens=[512]`, empty error,
   `total_input_tokens=2048`, and `total_output_tokens=512`. The server-log
   delta must contain exactly one line matching:

   ```text
   Prefill batch, #new-seq: 1, #new-token: 2048, #cached-token: 0, ...
   ```

   This exact `#new-token: 2048` line is required; runner JSON alone is not
   sufficient. The deployed log was observed to use this form.
5. **One successful request:** exit code 0, one HTTP-200 `/generate`, no error,
   timeout, or zero-progress marker, and one completed result. Postflight must
   show PID 298123's command hash/model identity unchanged, health 200, idle
   loads, and no new benchmark client.

Mark HiCache/cache device/host/storage fields `N/A` (HiCache disabled). The
regular RadixCache flush is evidenced by the runner's exact endpoint and the
server-log `POST /flush_cache?timeout=60.0`.

## Formal handoff

Only after independent smoke `PASS` may formal runs begin. Keep each repeat's
JSONL and raw telemetry separate; use `--flush-cache --flush-cache-timeout 60`
before every measured repeat. Production A remains C1/C4/C5, ISL 2048/OSL 512,
20/40/50 prompts; do not send C8/C16 to PID 298123. Performance-only B and
prefill 2K/8K/32K x OSL32 require their separately admitted service/profile.
All retain `random-ids`, ratio 1.0, seed 42, `--tokenize-prompt`, explicit
tokenizer directory, native SGLang, and no ShareGPT. Preserve runner/source
hashes and exact commands in every manifest.

## Open issue and final status

Execution is gated by the active old E2 process tree; a fresh execution task
must recheck drain/idle before using this runbook. This design task is complete.

Final status: **done**
