# G3-E3-SMOKE-AUDIT-FIX-20260907

ENTRY: ACCEPT

invocation_status: done
task_id: G3-E3-SMOKE-AUDIT-FIX-20260907
epoch: E3
role: devops

## Scope and disposition

This is a read-only diagnosis and runbook. I did not execute a benchmark
request, SSH command, remote write, download, process signal/restart, service
change, or product-code edit. The only local write for this invocation is this
report. A fresh retry should proceed only under a new authorized execution
Task ID and after the existing drain/idle gate is independently rechecked.

Recommendation: **proceed with a fresh one-request retry after admission
passes**. The prior attempt remains blocked evidence and must not be relabeled
as a smoke pass.

## Observed failure and false positive

The preserved execution report is
`.memory/g3-baseline-20260907/work/G3-E3-SMOKE-EXEC-20260907.md`; its raw run
is `.memory/g3-baseline-20260907/work/raw/g3-e3-smoke-20260907T135400Z/`.

Exact denied event (raw `audit/events.jsonl`, line 8280; SHA-256
`9bfa97c14a62307ccd72df75128a771e221edd84651c51c91b6c79765fb2d895`):

```json
{"event": "open", "args": "('/data/sglang-qwen35/python/sglang/benchmark/datasets/__pycache__/sharegpt.cpython-312.pyc', 'r', 524288)", "verdict": "deny"}
```

The traceback (`runner.stderr`, lines 4--16) is:

```text
serving.py:43 -> from sglang.benchmark.datasets import ...
datasets/__init__.py:15 -> from sglang.benchmark.datasets.sharegpt import ShareGPTDataset
importlib._bootstrap_external.py:990/1086/1185 -> exec_module/get_code/get_data
RuntimeError: forbidden client file: .../datasets/__pycache__/sharegpt.cpython-312.pyc
```

This is normal read-only Python module import. `datasets/__init__.py` imports
the `ShareGPTDataset` class to populate the dataset-class mapping, so the
module's bytecode is loaded even when the selected dataset is not ShareGPT.
`random.py` sets `random_sample=(args.dataset_name == "random")`; for
`random-ids` this is false, so the branch containing
`download_and_cache_hf_file`, `open(dataset_path)`, and `json.load` is not
entered. The selected branch creates integer token IDs. `--tokenize-prompt`
keeps those IDs as the request payload.

Therefore the path component `sharegpt.cpython-312.pyc` identifies installed
code, not a ShareGPT dataset/content/cache file. The event's mode `r` and
flags `524288` are also a read-only import open. The failed hook treated the
substring `sharegpt` as a data violation before considering the path's source
root, which caused the false positive. The client failed during import; it
created no `result.jsonl`, sent no `/generate`, and the server-log delta only
contained the preflight `GET /v1/loads?include=all`.

## Corrected run-local `sitecustomize.py`

Install exactly this file at `$RUN_DIR/audit/sitecustomize.py` for the fresh
run. It changes no product file. The policy order is significant:

1. Any path containing `.gguf` is denied before every allow rule.
2. Read-only code under the deployed SGLang source root is allowed by
   extension (`.py`/`.pyc`) before ShareGPT-name matching; this is the
   installed-code exception and includes `sharegpt.cpython-312.pyc`.
3. Read-only interpreter/runtime code roots are allowed so normal imports,
   extension loading, and the observed `python312.zip` import work.
4. ShareGPT-named dataset/content/cache paths are denied everywhere else.
5. The explicit tokenizer sidecar directory and run-local artifact directory
   are allowed only after the unconditional GGUF/ShareGPT checks.
6. Integer file-descriptor opens are resolved through `/proc/self/fd/N`.
   Unresolved descriptors, pipes, sockets, and other non-path targets are
   denied; a resolved target is classified by the same rules. The log records
   the target and classification, rather than claiming that an unresolved FD
   was safe.
7. IPv4/IPv6 loopback connects are allowed for the local service; non-loopback
   addresses and non-loopback name resolution are denied. Unix-domain sockets
   are allowed only as local-domain endpoints (`/tmp` or the run directory)
   and are not counted as network destinations.

```python
import ipaddress
import json
import os
import sys
import threading


AUDIT_LOG_PATH = os.environ["SGLANG_AUDIT_LOG"]
RUN_ROOT = os.path.realpath(os.environ["SGLANG_AUDIT_RUN_ROOT"])
SOURCE_ROOT = os.path.realpath(
    os.environ.get("SGLANG_SOURCE_ROOT", "/data/sglang-qwen35/python")
)
TOKENIZER_ROOT = os.path.realpath(
    os.environ.get(
        "SGLANG_TOKENIZER_ROOT",
        "/data/models/Qwen3.8-27B-GSQ-RCO-GGUF",
    )
)
AUDIT_ROOT = os.path.realpath(os.path.dirname(__file__))

# These are code/container roots observed in the preserved run. The source
# root has a narrower exception below; runtime roots cover .py/.pyc/.so and
# the Python stdlib zip needed for ordinary imports.
RUNTIME_ROOTS = tuple(
    dict.fromkeys(
        root
        for root in (
            os.path.realpath(sys.prefix),
            os.path.realpath(getattr(sys, "base_prefix", sys.prefix)),
            os.path.realpath(os.path.dirname(os.__file__)),
        )
        if root
    )
)
SYSTEM_ROOTS = tuple(
    os.path.realpath(root)
    for root in (
        "/dev",
        "/proc",
        "/tmp",
        "/usr/share/zoneinfo",
    )
)
SAFE_DEVICES = {"/dev/null", "/dev/urandom", "/dev/zero"}
WRITE_FLAGS = (
    os.O_WRONLY
    | os.O_RDWR
    | os.O_CREAT
    | os.O_TRUNC
    | os.O_APPEND
    | os.O_EXCL
)
READ_CODE_SUFFIXES = (".py", ".pyc")
RUNTIME_CODE_SUFFIXES = (".py", ".pyc", ".so", ".pyd", ".dll", ".zip")
_LOG_LOCK = threading.Lock()
_LOG = open(AUDIT_LOG_PATH, "a", buffering=1, encoding="utf-8")


def _under(path, root):
    try:
        return os.path.commonpath((path, root)) == root
    except (TypeError, ValueError):
        return False


def _safe_repr(value):
    try:
        return repr(value)
    except Exception:
        return "<unrepresentable:{}>".format(type(value).__name__)


def _emit(event, args, verdict, reason, **extra):
    record = {
        "event": event,
        "verdict": verdict,
        "reason": reason,
        "args": _safe_repr(args),
    }
    record.update(extra)
    with _LOG_LOCK:
        _LOG.write(json.dumps(record, sort_keys=True) + "\n")
        _LOG.flush()


def _readonly(mode, flags):
    try:
        flags = int(flags or 0)
    except (TypeError, ValueError):
        return False
    if flags & WRITE_FLAGS:
        return False
    if isinstance(mode, bytes):
        mode = os.fsdecode(mode)
    mode = "" if mode is None else str(mode)
    return not any(char in mode for char in "wax+")


def _resolve_path(value):
    """Return (resolved path or None, kind, detail) without hiding FD failure."""
    if isinstance(value, int):
        fd_name = "/proc/self/fd/{}".format(value)
        try:
            target = os.readlink(fd_name)
        except OSError as exc:
            return None, "fd", "fd-unresolved:{}".format(exc)
        if target.startswith(("socket:[", "pipe:[", "anon_inode:")):
            return None, "fd", "fd-nonfile:{}".format(target)
        return os.path.realpath(target), "fd", "fd-resolved:{}".format(target)
    try:
        raw = os.fspath(value)
    except TypeError:
        return None, "unknown", "path-not-pathlike"
    if isinstance(raw, bytes):
        raw = os.fsdecode(raw)
    if not isinstance(raw, str):
        return None, "unknown", "path-not-string"
    return os.path.realpath(raw), "path", "path"


def _sharegpt_data_marker(path):
    lower = path.lower()
    if "sharegpt" in lower:
        return True
    # Catch a ShareGPT artifact cached under a generic repository/cache name,
    # while allowing ordinary huggingface_hub/datasets Python code above.
    return (
        ("huggingface" in lower or "modelscope" in lower)
        and ("cache" in lower or "dataset" in lower)
    )


def _is_code(path, suffixes):
    return path.lower().endswith(suffixes)


def _deny(event, args, reason, **extra):
    _emit(event, args, "deny", reason, **extra)
    raise RuntimeError("audit denied {}: {}".format(event, reason))


def _audit_open(event, args):
    value = args[0] if args else None
    mode = args[1] if len(args) > 1 else None
    flags = args[2] if len(args) > 2 else None
    path, kind, detail = _resolve_path(value)
    fields = {
        "path": path,
        "path_kind": kind,
        "resolution": detail,
        "mode": _safe_repr(mode),
        "flags": flags,
    }
    if path is None:
        return _deny(event, args, detail, **fields)

    lower = path.lower()
    readonly = _readonly(mode, flags)

    # Absolute invariant: this check precedes every allow exception.
    if ".gguf" in lower:
        return _deny(event, args, "gguf-always-deny", **fields)

    # Installed SGLang source exception. It deliberately tests the resolved
    # path and suffix, not the module basename, so sharegpt.py/.pyc is code.
    if _under(path, SOURCE_ROOT) and _is_code(path, READ_CODE_SUFFIXES):
        if readonly:
            _emit(event, args, "allow", "installed-sglang-code-read", **fields)
            return
        return _deny(event, args, "installed-sglang-code-write", **fields)

    # The run-local hook itself may be imported from its .py/.pyc file.
    if _under(path, AUDIT_ROOT) and _is_code(path, READ_CODE_SUFFIXES):
        if readonly:
            _emit(event, args, "allow", "run-audit-code-read", **fields)
            return
        return _deny(event, args, "run-audit-code-write", **fields)

    # Runtime code/metadata is needed by the interpreter and native packages.
    if any(_under(path, root) for root in RUNTIME_ROOTS) and _is_code(
        path, RUNTIME_CODE_SUFFIXES
    ):
        if readonly:
            _emit(event, args, "allow", "runtime-code-read", **fields)
            return
        return _deny(event, args, "runtime-code-write", **fields)

    # This test follows code exceptions, so a module named sharegpt is not
    # mistaken for a dataset. Data/cache files with that marker are denied.
    if _sharegpt_data_marker(path):
        return _deny(event, args, "sharegpt-data-or-cache", **fields)

    # Normal package metadata/resources (for example dist-info/METADATA) are
    # not Python code suffixes but are part of the installed runtime. This
    # rule is deliberately after the ShareGPT test so a data/cache marker is
    # still denied.
    if any(_under(path, root) for root in RUNTIME_ROOTS):
        if readonly:
            _emit(event, args, "allow", "runtime-package-read", **fields)
            return
        return _deny(event, args, "runtime-package-write", **fields)

    if _under(path, TOKENIZER_ROOT):
        if readonly:
            _emit(event, args, "allow", "approved-tokenizer-sidecar-read", **fields)
            return
        return _deny(event, args, "tokenizer-sidecar-write", **fields)

    if _under(path, RUN_ROOT):
        _emit(event, args, "allow", "run-local-artifact", **fields)
        return

    if path in SAFE_DEVICES:
        _emit(event, args, "allow", "safe-device", **fields)
        return

    if _under(path, SYSTEM_ROOTS):
        if _under(path, "/tmp"):
            _emit(event, args, "allow", "runtime-temp", **fields)
            return
        if readonly:
            _emit(event, args, "allow", "runtime-system-read", **fields)
            return
        return _deny(event, args, "runtime-system-write", **fields)

    # Packaging metadata can expose this non-filesystem pseudo-path during
    # editable-package discovery; it is not a data file.
    raw = value.decode() if isinstance(value, bytes) else value
    if isinstance(raw, str) and raw.startswith("__editable__.") and readonly:
        _emit(event, args, "allow", "editable-package-metadata", **fields)
        return

    return _deny(event, args, "unapproved-path", **fields)


def _local_socket_address(address):
    if isinstance(address, bytes):
        address = os.fsdecode(address)
    if isinstance(address, str):
        # AF_UNIX is local IPC, not an external network destination.
        return address == "" or address.startswith("/tmp/") or _under(
            os.path.realpath(address), RUN_ROOT
        ), "unix-domain-local"
    if not isinstance(address, (tuple, list)) or not address:
        return False, "non-ip-address"
    try:
        ip = ipaddress.ip_address(str(address[0]).strip("[]"))
    except ValueError:
        return False, "non-ip-address"
    return ip.is_loopback, "loopback-ip" if ip.is_loopback else "non-loopback-ip"


def _audit(event, args):
    if event == "open":
        return _audit_open(event, args)
    if event in ("socket.connect", "socket.connect_ex", "socket.sendto"):
        address = args[-1] if args else None
        allowed, reason = _local_socket_address(address)
        fields = {"address": _safe_repr(address)}
        if allowed:
            _emit(event, args, "allow", reason, **fields)
            return
        return _deny(event, args, reason, **fields)
    if event == "socket.getaddrinfo":
        host = args[0] if args else None
        if isinstance(host, bytes):
            host = os.fsdecode(host)
        allowed = host is None or str(host).lower() in (
            "localhost",
            "127.0.0.1",
            "::1",
        )
        fields = {"host": host}
        if allowed:
            _emit(event, args, "allow", "loopback-name-resolution", **fields)
            return
        return _deny(event, args, "non-loopback-name-resolution", **fields)


sys.addaudithook(_audit)
```

The source-root check is the material correction to the failed hook. The
integer-FD branch is intentionally explicit: a descriptor is allowed only
when `/proc/self/fd/N` resolves to a safe path and its requested open is
read-only (or a safe device), and an unresolved/non-file descriptor is denied.
This records what was observed; it does not claim that a later native write
through an already-open descriptor is impossible.

## Exact fresh-retry environment and unchanged workload

The executor must first create a new run directory after the existing E2 tree
is terminal, the service is idle, and PID 298123's command identity is
unchanged. It must preserve the failed command's benchmark argv byte-for-byte;
the only additions below are run-local audit configuration and
`PYTHONDONTWRITEBYTECODE=1` so a source import cannot create a source-tree
bytecode write after the read-only code decision.

```bash
RUN_DIR=/data/qwen3-g3-baseline/g3-e3-smoke-<fresh-UTC>
mkdir -p "$RUN_DIR/audit"

env \
  PYTHONPATH="$RUN_DIR/audit" \
  SGLANG_AUDIT_LOG="$RUN_DIR/audit/events.jsonl" \
  SGLANG_AUDIT_RUN_ROOT="$RUN_DIR" \
  SGLANG_SOURCE_ROOT=/data/sglang-qwen35/python \
  SGLANG_TOKENIZER_ROOT=/data/models/Qwen3.8-27B-GSQ-RCO-GGUF \
  HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  HF_HUB_DISABLE_TELEMETRY=1 SGLANG_USE_MODELSCOPE=false \
  HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= NO_PROXY='*' \
  PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
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

The workload identity is unchanged: native `sglang`, `random-ids`, integer
tokenized prompt, ISL 2048, OSL 512, ratio 1.0, seed 42, concurrency 1,
one prompt, warmup 0, and `--flush-cache`. Streaming and ignore-EOS remain
enabled by omission of both negative flags. The explicit tokenizer sidecar is
the approved directory; the served model argument remains the same GGUF path.
Offline/no-proxy variables remain set exactly as in the failed attempt.

## Post-run evidence and deterministic acceptance

Save the exact hook, its SHA-256, the full environment/argv, timestamps,
client exit code, audit log, result JSONL, RSS/process samples, pre/post loads,
server-log byte delta, and pre/post service command identity in the fresh raw
run directory. Before interpreting any result, run a JSONL audit check with
the deployed interpreter. The check must fail if any audit record is malformed,
has `verdict=deny`, has an `open` path containing `.gguf`, has a ShareGPT data
marker outside the source/runtime-code exception, has `path_kind=fd` with an
unresolved/non-file resolution, has non-loopback `socket.connect`,
`socket.connect_ex`, or `socket.sendto`, or has `socket.getaddrinfo` for a
non-loopback host. For actual IP connects, require destination port 8035;
Unix-domain records are local IPC only.

The smoke is **PASS** only if all of the following are independently evidenced:

- The audit log is complete and contains zero deny records, zero GGUF paths,
  zero ShareGPT data/cache paths, zero unresolved FD records, and only
  loopback IP socket destinations (actual service connects only to
  `127.0.0.1:8035`/`::1:8035`). A source-root `sharegpt*.py`/`.pyc` record is
  accepted only with `reason=installed-sglang-code-read` and a read-only mode.
- The explicit tokenizer sidecar opens are read-only and under the exact
  approved directory. There is no open of the GGUF model by the client.
- The client exits 0, `result.jsonl` contains exactly one JSON object with
  `completed=1`, `input_lens=[2048]`, `output_lens=[512]`, empty error,
  `total_input_tokens=2048`, and `total_output_tokens=512`.
- The server-log delta contains exactly one expected local flush-cache POST
  and one HTTP-200 `/generate`, with the required
  `Prefill batch, #new-seq: 1, #new-token: 2048, #cached-token: 0, ...` line;
  no external/download line is present.
- Client RSS samples are nonempty, peak is below 4 GiB, and final RSS is
  within 256 MiB of its post-dataset plateau. Postflight health is 200,
  loads are idle, no benchmark process remains, and PID 298123's command hash
  and model identity are unchanged.

Any missing audit record, failed log parse, denied event, GGUF path, ShareGPT
data/cache path, non-loopback destination, nonzero exit, malformed result,
server-line mismatch, RSS bound violation, or service-identity change is
deterministic **FAIL/BLOCKED**; do not proceed to formal matrix runs.

Suggested read-only checker (run from the fresh run directory):

```bash
/data/sglang-qwen35-env/bin/python - "$RUN_DIR/audit/events.jsonl" <<'PY'
import json, os, sys

events = []
with open(sys.argv[1], encoding="utf-8") as f:
    for n, line in enumerate(f, 1):
        rec = json.loads(line)
        if not isinstance(rec, dict) or rec.get("verdict") not in {"allow", "deny"}:
            raise SystemExit(f"FAIL audit record {n}")
        events.append(rec)

bad = []
for rec in events:
    if rec["verdict"] == "deny":
        bad.append((rec, "deny"))
    if rec.get("event") == "open":
        path = str(rec.get("path") or "").lower()
        if ".gguf" in path:
            bad.append((rec, "gguf"))
        if rec.get("path_kind") == "fd" and rec.get("resolution", "").startswith(
            ("fd-unresolved", "fd-nonfile")
        ):
            bad.append((rec, "unresolved-fd"))
    if rec.get("event") in {"socket.connect", "socket.connect_ex", "socket.sendto"}:
        address = str(rec.get("address", ""))
        if "127.0.0.1" not in address and "::1" not in address and "unix" not in rec.get("reason", ""):
            bad.append((rec, "non-loopback-connect"))
    if rec.get("event") == "socket.getaddrinfo":
        host = str(rec.get("host", "")).lower()
        if host not in {"none", "localhost", "127.0.0.1", "::1"}:
            bad.append((rec, "non-loopback-resolution"))

if bad:
    raise SystemExit("FAIL audit policy: " + repr(bad[:3]))
print(f"PASS audit records={len(events)}")
PY
```

The checker is a negative assertion, not a substitute for source/runtime
evidence. Python audit hooks do not prove that a native extension issuing a
raw syscall bypassed the hook; this is the principal residual blind spot.
Where available, retain a scoped `strace -ff -e trace=openat,connect` as an
independent cross-check. On the preserved host those tools were unavailable,
so the run must explicitly retain this limitation. The offline variables and
the hook catch Python-level URL resolution/connects; they do not turn the
client audit into a kernel-level network/filesystem sandbox.

## Evidence, followups, and open issues

Evidence reviewed:

- `.memory/g3-baseline-20260907/work/G3-E3-SMOKE-EXEC-20260907.md`
- `.memory/g3-baseline-20260907/work/G3-E3-SMOKE-RUNBOOK-20260907.md`
- `.memory/g3-baseline-20260907/work/G3-CORE-UNBLOCK-20260907-SOURCE-AUDIT.md`
- `.memory/g3-baseline-20260907/work/G3-CORE-UNBLOCK-20260907-REMOTE-AUDIT.md`
- Raw audit, traceback, command, manifest, server-log delta, and postflight
  artifacts under `raw/g3-e3-smoke-20260907T135400Z/`.

Followups: dispatch a fresh execution Task ID to an authorized
`devops-executor`; re-run the preflight drain/idle gate; preserve all fresh
artifacts under a new run ID; then request independent tester verification.

Open issues: the old E2 process tree must be terminal before admission; the
host lacks kernel-level tracing tools, so native raw-syscall bypass remains a
residual blind spot; the service source is deployed without Git metadata, so
preserve the serving-file SHA-256 and process command hash. No formal matrix
or quality conclusion is authorized from the failed smoke.

Final invocation status: **done**
