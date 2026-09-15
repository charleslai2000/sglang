"""Dependency-light coordination substrate for the P3 3090 harnesses.

This module deliberately lives outside the production Python packages.  It
owns only processes that it starts, uses one fixed GPU lock, and writes all
run state below the caller's artifact root.  Later P3 drivers can import the
small classes here instead of reimplementing lifecycle and evidence rules.

Provenance policy: argv is sanitized before it is persisted or hashed.  Secret
option names (including authorization, bearer, token, password, secret,
credential, and API-key variants) redact their inline or following value.
The common ``--header`` and ``--auth`` split forms are deliberately rejected:
their grammar is ambiguous enough that a conservative caller must use an
inline form or omit the secret.  Secret-looking custom values such as
``Bearer ...`` and ``secret=...`` are redacted even when they are positional or
attached to another option.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import fcntl
import hashlib
import json
import os
import platform
import secrets
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "p3-harness.v1"
GPU_LOCK_PATH = Path("/mnt/data/gpu/3090.lock")
DEFAULT_ARTIFACT_ROOT = Path("/mnt/data/nerun-dev/p3")
_SECRET_OPTION_WORDS = (
    "auth",
    "authorization",
    "apikey",
    "bearer",
    "credential",
    "header",
    "password",
    "passwd",
    "secret",
    "token",
)
_SECRET_VALUE_PATTERN = re.compile(
    r"(?:bearer\s+\S+|custom[-_ ]?secret(?:[-_ ]\S+)?|(?:authorization|api[-_]?-?key|password|passwd|secret|token|credential)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


class HarnessError(RuntimeError):
    """Base error for an invalid harness operation."""


class LockBusyError(HarnessError):
    """The single permitted 3090 GPU lock is already held."""


class AmbiguousCleanupError(HarnessError):
    """Name-based or otherwise ambiguous process cleanup was requested."""


class UnsafeArgvError(HarnessError):
    """The command contains a secret-bearing argv form this substrate rejects."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write a complete metadata document without exposing a partial file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, default=_json_default, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


_AMBIGUOUS_SECRET_OPTIONS = {"auth", "authorization", "bearer", "header"}


def _redact_argv(argv: Sequence[str]) -> list[str]:
    redacted: list[str] = []
    index = 0
    while index < len(argv):
        item = str(argv[index])
        option_name = _option_name(item)
        if option_name in _AMBIGUOUS_SECRET_OPTIONS and "=" not in item:
            raise UnsafeArgvError(
                f"unsafe split secret option {item!r}; use an inline form such as "
                f"{item}=<value> so the harness can sanitize it"
            )
        if _secret_option_name(item):
            if "=" in item:
                redacted.append(item.split("=", 1)[0] + "=<redacted>")
            else:
                redacted.append(item)
                index += 1
                if index >= len(argv):
                    redacted.append("<redacted>")
                    break
                redacted.append("<redacted>")
                # Authorization headers are commonly split as
                # ``--authorization Bearer value``.  Consume the complete
                # token sequence so the value can never remain in metadata.
                if str(argv[index]).lower() in {"bearer", "authorization"} and index + 1 < len(argv):
                    index += 1
                    if str(argv[index]).lower() == "bearer" and index + 1 < len(argv):
                        index += 1
        elif _SECRET_VALUE_PATTERN.search(item):
            redacted.append("<redacted>")
        else:
            redacted.append(item)
        index += 1
    return redacted


def _option_name(item: str) -> str:
    if not item.startswith("-"):
        return ""
    return item.lstrip("-").split("=", 1)[0].lower()


def _secret_option_name(item: str) -> bool:
    if not item.startswith("-"):
        return False
    name = _option_name(item)
    compact = re.sub(r"[^a-z0-9]", "", name)
    return any(word in compact for word in _SECRET_OPTION_WORDS)


def args_hash(argv: Sequence[str]) -> str:
    encoded = json.dumps(sanitize_argv(argv), separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def sanitize_argv(argv: Sequence[str]) -> list[str]:
    """Return the only argv representation allowed in persisted metadata."""

    return _redact_argv(argv)


def _git_identity(repo_root: Path) -> dict[str, Any]:
    identity: dict[str, Any] = {"path": str(repo_root.resolve())}
    try:
        head = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        identity["commit"] = head.stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        identity["dirty"] = bool(status.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        identity["available"] = False
    return identity


def _gpu_identity() -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,driver_version,uuid",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    rows = []
    for line in result.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if fields:
            rows.append(fields)
    return {"nvidia_smi": rows} if rows else None


def collect_provenance(
    *,
    repo_root: Path,
    profile: str,
    argv: Sequence[str],
    run_id: str,
    started_at: str,
) -> dict[str, Any]:
    """Collect stable, non-secret run identity and selected environment data."""

    identifier_env = {
        key: os.environ[key]
        for key in (
            "CUDA_VISIBLE_DEVICES",
            "NVIDIA_VISIBLE_DEVICES",
            "SLURM_JOB_ID",
            "HOSTNAME",
        )
        if key in os.environ
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "started_at": started_at,
        "repo": _git_identity(repo_root),
        "profile": profile,
        "argv": sanitize_argv(argv),
        "args_sha256": args_hash(argv),
        "environment": {
            "hostname": platform.node(),
            "platform": platform.platform(aliased=True),
            "python": platform.python_version(),
            "identifiers": identifier_env,
        },
        "gpu": _gpu_identity(),
    }


class ArtifactNamespace:
    """Create and maintain one unique, preserved namespace per run."""

    def __init__(self, root: Path, *, profile: str, run_id: str | None = None) -> None:
        self._root_input = Path(root).expanduser()
        # Keep the supplied root lexical while validating it. Resolving it
        # here could allow an existing ancestor symlink to redirect creation.
        self.root = self._root_input.absolute()
        self.profile = _validate_component("profile", profile)
        self.run_id = _validate_component(
            "run_id",
            run_id or f"{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%S.%fZ}-{uuid.uuid4().hex[:10]}",
        )
        self.path = self.root / self.profile / self.run_id
        if self.root not in self.path.parents:
            raise HarnessError("artifact namespace escaped artifact root")

    def create(self) -> Path:
        self._verify_safe_components()
        self.path.mkdir(parents=True, exist_ok=False)
        (self.path / "logs").mkdir()
        (self.path / "metadata").mkdir()
        return self.path

    def _verify_safe_components(self) -> None:
        """Reject pre-existing symlinks and verify resolved containment.

        ``mkdir(..., parents=True)`` follows an existing profile component,
        so lexical ``Path`` containment alone is insufficient.  Check every
        component that will be used before creating the run directory and
        resolve again immediately before mkdir.
        """

        for component in _existing_lexical_components(self.path):
            if component.is_symlink():
                raise HarnessError(f"artifact namespace component must not be a symlink: {component}")
        resolved_root = self.root.resolve(strict=False)
        resolved_path = self.path.resolve(strict=False)
        if resolved_path != self.path or resolved_root not in resolved_path.parents:
            raise HarnessError("resolved artifact namespace escaped artifact root")

    def write_metadata(self, name: str, payload: Mapping[str, Any]) -> Path:
        if Path(name).name != name or not name.endswith(".json"):
            raise HarnessError("metadata names must be simple .json filenames")
        destination = self.path / "metadata" / name
        atomic_json(destination, payload)
        return destination


def _validate_component(name: str, value: str) -> str:
    if not value or value in {".", ".."} or Path(value).is_absolute() or "/" in value or "\\" in value:
        raise HarnessError(f"{name} must be one safe path component")
    if any(ord(char) < 32 for char in value):
        raise HarnessError(f"{name} contains unsafe control characters")
    if any(not (char.isalnum() or char in "._-") for char in value):
        raise HarnessError(f"{name} contains unsafe characters")
    return value


def _existing_lexical_components(path: Path) -> list[Path]:
    """Return existing path components without following symlinks."""

    absolute = path.absolute()
    components: list[Path] = []
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            current.lstat()
        except FileNotFoundError:
            break
        components.append(current)
    return components


class GpuLock:
    """The only supported 3090 coordination lock: /mnt/data/gpu/3090.lock."""

    def __init__(self, path: Path = GPU_LOCK_PATH) -> None:
        if Path(path) != GPU_LOCK_PATH:
            raise HarnessError(f"alternate GPU lock forbidden: {path}")
        self.path = GPU_LOCK_PATH
        self._file: Any = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a+")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._file.close()
            self._file = None
            raise LockBusyError(f"GPU lock busy: {self.path}") from exc

    def release(self) -> None:
        if self._file is not None:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
            self._file.close()
            self._file = None

    def __enter__(self) -> "GpuLock":
        self.acquire()
        return self

    def __exit__(self, *_: Any) -> None:
        self.release()


def _proc_start_time(pid: int) -> str | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        return fields[21]
    except (FileNotFoundError, OSError, IndexError):
        return None


def _proc_cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, OSError):
        return []
    return [part.decode(errors="replace") for part in raw.split(b"\0") if part]


@dataclasses.dataclass
class OwnedProcess:
    process: subprocess.Popen[Any]
    argv: list[str]
    started_at: str
    proc_start_time: str | None

    @property
    def pid(self) -> int:
        return self.process.pid

    def identity_matches(self) -> bool:
        current = _proc_start_time(self.pid)
        return current is not None and current == self.proc_start_time

    def ownership_state(self) -> tuple[bool, str | None]:
        """Return whether it is safe to act on or accept this PID as gone.

        A reaped Popen child has no /proc identity anymore, but is safe to
        accept as gone when launch established a non-null start token and
        Popen confirms that this exact child was reaped.  A missing token or
        a live/mismatched PID is ambiguous and is never treated as gone.
        """

        current = _proc_start_time(self.pid)
        if current is not None:
            return current == self.proc_start_time, None if current == self.proc_start_time else "proc identity mismatch"
        if self.proc_start_time is not None and self.process.poll() is not None:
            return True, None
        return False, "proc identity missing"

    def metadata(self) -> dict[str, Any]:
        return {
            "pid": self.pid,
            "argv": _redact_argv(self.argv),
            "started_at": self.started_at,
            "proc_start_time": self.proc_start_time,
            "cmdline": _redact_argv(_proc_cmdline(self.pid)),
        }


def launch_owned(argv: Sequence[str], *, stdout: Any = None, stderr: Any = None, cwd: Path | None = None) -> OwnedProcess:
    """Start exactly one child and return its ownership token."""

    if not argv:
        raise HarnessError("cannot launch an empty command")
    command = [str(item) for item in argv]
    process = subprocess.Popen(command, stdout=stdout, stderr=stderr, cwd=cwd, start_new_session=True)
    return OwnedProcess(process, command, utc_now(), _proc_start_time(process.pid))


def _pid_gone(owned: OwnedProcess) -> bool:
    owned_valid, _ = owned.ownership_state()
    return owned_valid and owned.process.poll() is not None


def cleanup_owned(owned: OwnedProcess, *, term_timeout: float = 5.0, kill_timeout: float = 5.0) -> dict[str, Any]:
    """TERM then KILL one identity-checked child; never search by process name."""

    result: dict[str, Any] = {
        "pid": owned.pid,
        "attempted": True,
        "term_sent": False,
        "kill_sent": False,
        "gone": False,
        "ownership_valid": False,
        "status": "FAIL",
        "errors": [],
    }
    ownership_valid, ownership_error = owned.ownership_state()
    result["ownership_valid"] = ownership_valid
    if not ownership_valid:
        result["errors"].append(ownership_error or "ownership validation failed")
        result["status"] = "AMBIGUOUS"
        return result
    if owned.process.poll() is not None:
        result["gone"] = True
        result["status"] = "PASS"
        return result
    try:
        os.kill(owned.pid, signal.SIGTERM)
        result["term_sent"] = True
        try:
            owned.process.wait(timeout=term_timeout)
        except subprocess.TimeoutExpired:
            ownership_valid, ownership_error = owned.ownership_state()
            result["ownership_valid"] = ownership_valid
            if not ownership_valid:
                result["errors"].append(ownership_error or "ownership validation failed before KILL")
                result["status"] = "AMBIGUOUS"
                return result
            os.kill(owned.pid, signal.SIGKILL)
            result["kill_sent"] = True
            try:
                owned.process.wait(timeout=kill_timeout)
            except subprocess.TimeoutExpired as exc:
                result["errors"].append(f"owned PID did not exit: {owned.pid}: {exc}")
                return result
    except (OSError, subprocess.SubprocessError) as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        return result
    ownership_valid, ownership_error = owned.ownership_state()
    result["ownership_valid"] = ownership_valid
    if not ownership_valid:
        result["errors"].append(ownership_error or "ownership validation failed after cleanup")
        result["status"] = "AMBIGUOUS"
        return result
    result["gone"] = owned.process.poll() is not None
    if not result["gone"]:
        result["errors"].append(f"owned PID still exists after cleanup: {owned.pid}")
    else:
        result["status"] = "PASS"
    return result


def refuse_ambiguous_cleanup(*, process_name: str | None = None) -> None:
    """Explicitly reject the unsafe process-name cleanup pattern."""

    raise AmbiguousCleanupError(
        "ambiguous cleanup refused; pass an OwnedProcess returned by launch_owned "
        f"(received name={process_name!r})"
    )


def rollback_namespace(namespace: ArtifactNamespace) -> dict[str, Any]:
    """Record the safe default rollback outcome.

    Run artifacts are intentionally preserved for evidence, so the common
    substrate has no destructive rollback action.  The explicit result gives
    later drivers a stable place to report a driver-specific rollback and
    keeps exception paths representable in the final manifest.
    """

    return {
        "attempted": False,
        "status": "PASS",
        "error": None,
        "errors": [],
        "detail": "not_needed; artifact namespace preserved",
    }


class HealthGate:
    def __init__(self, url: str, *, timeout: float = 60.0, poll_interval: float = 1.0, request_timeout: float = 2.0) -> None:
        self.url = url
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.request_timeout = request_timeout
        self.observations: list[dict[str, Any]] = []

    def check(self) -> bool:
        status: int | None = None
        error: str | None = None
        try:
            with urllib.request.urlopen(self.url, timeout=self.request_timeout) as response:
                status = int(response.status)
                healthy = 200 <= status < 300
        except (OSError, urllib.error.URLError, ValueError) as exc:
            healthy = False
            error = type(exc).__name__
        self.observations.append({"at": utc_now(), "healthy": healthy, "status": status, "error": error})
        return healthy

    def wait(self) -> bool:
        deadline = time.monotonic() + self.timeout
        while True:
            if self.check():
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(min(self.poll_interval, max(0.0, deadline - time.monotonic())))


@dataclasses.dataclass
class FailFastMonitor:
    timeout: float = 3600.0
    zero_progress_timeout: float = 300.0
    health_loss_threshold: int = 3
    started: float = dataclasses.field(default_factory=time.monotonic)
    last_progress: Any = None
    last_progress_at: float = dataclasses.field(default_factory=time.monotonic)
    health_failures: int = 0
    state: str = "RUNNING"
    reason: dict[str, Any] | None = None

    def observe(self, *, progress: Any = None, healthy: bool = True, now: float | None = None) -> str:
        now = time.monotonic() if now is None else now
        if self.state != "RUNNING":
            return self.state
        if now - self.started >= self.timeout:
            return self._stop("TIMEOUT", "overall timeout exceeded")
        if progress is not None and progress != self.last_progress:
            self.last_progress = progress
            self.last_progress_at = now
        if progress is not None and now - self.last_progress_at >= self.zero_progress_timeout:
            return self._stop("ZERO_PROGRESS", "progress value did not change")
        self.health_failures = 0 if healthy else self.health_failures + 1
        if self.health_failures >= self.health_loss_threshold:
            return self._stop("HEALTH_LOSS", "health failed consecutively")
        return self.state

    def _stop(self, code: str, detail: str) -> str:
        self.state = "FAIL_FAST"
        self.reason = {"code": code, "detail": detail}
        return self.state


def _read_progress(path: Path) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("progress")
    except (OSError, ValueError, AttributeError):
        return None


def _close_stream(stream: Any) -> None:
    stream.close()


def _run_cli(args: argparse.Namespace) -> int:
    resolved_artifact_root = args.artifact_root.absolute().resolve(strict=False)
    resolved_default_root = DEFAULT_ARTIFACT_ROOT.absolute().resolve(strict=False)
    if resolved_artifact_root != resolved_default_root and resolved_default_root not in resolved_artifact_root.parents:
        raise HarnessError(f"artifact root must be under {DEFAULT_ARTIFACT_ROOT}")
    # Reject unsafe forms before creating any artifact namespace.  This keeps
    # an ambiguous command from causing even a failure manifest to persist.
    sanitize_argv(args.command)
    namespace = ArtifactNamespace(args.artifact_root, profile=args.profile)
    namespace.create()
    started_at = utc_now()
    provenance = collect_provenance(
        repo_root=args.repo_root,
        profile=args.profile,
        argv=args.command,
        run_id=namespace.run_id,
        started_at=started_at,
    )
    namespace.write_metadata("provenance.json", provenance)
    monitor = FailFastMonitor(args.timeout, args.zero_progress_timeout, args.health_loss_threshold)
    owned: OwnedProcess | None = None
    cleanup: dict[str, Any] = {
        "pid": None,
        "attempted": False,
        "term_sent": False,
        "kill_sent": False,
        "gone": False,
        "ownership_valid": False,
        "status": "PASS",
        "errors": [],
    }
    rollback: dict[str, Any] = {
        "attempted": False,
        "status": "PASS",
        "error": None,
        "errors": [],
        "detail": "not_needed; artifact namespace preserved",
    }
    status = "FAIL"
    reason: dict[str, Any] = {"code": "HARNESS_ERROR", "detail": "run did not complete"}
    exit_code: int | None = None
    health: HealthGate | None = None
    stream_close_errors: list[str] = []
    stdout: Any = None
    stderr: Any = None
    try:
        with GpuLock():
            try:
                stdout = (namespace.path / "logs" / "child.stdout.log").open("w", encoding="utf-8")
                stderr = (namespace.path / "logs" / "child.stderr.log").open("w", encoding="utf-8")
                owned = launch_owned(args.command, stdout=stdout, stderr=stderr, cwd=args.cwd)
                provenance["child"] = owned.metadata()
                namespace.write_metadata("provenance.json", provenance)
                if args.health_url:
                    health = HealthGate(args.health_url, timeout=args.health_timeout, poll_interval=args.health_poll)
                    if not health.wait():
                        reason = {"code": "HEALTH_TIMEOUT", "detail": "health gate did not become healthy"}
                    else:
                        reason = {"code": "RUNNING", "detail": "health gate passed"}
                else:
                    reason = {"code": "RUNNING", "detail": "no health URL configured"}
                while owned.process.poll() is None and monitor.state == "RUNNING" and reason["code"] == "RUNNING":
                    healthy = True if health is None else health.check()
                    progress = _read_progress(args.progress_file) if args.progress_file else None
                    monitor.observe(progress=progress, healthy=healthy)
                    if monitor.state != "RUNNING":
                        reason = monitor.reason or {"code": "FAIL_FAST", "detail": "monitor stopped"}
                        break
                    time.sleep(args.monitor_poll)
                exit_code = owned.process.poll()
                if reason["code"] == "RUNNING":
                    status = "PASS" if exit_code == 0 else "FAIL"
                    reason = {"code": "CHILD_EXIT", "detail": "child exited", "exit_code": exit_code}
            finally:
                try:
                    for stream_name, stream in (("stdout", stdout), ("stderr", stderr)):
                        if stream is None:
                            continue
                        try:
                            _close_stream(stream)
                        except Exception as exc:  # noqa: BLE001 - manifest must preserve close failure
                            stream_close_errors.append(f"{stream_name}: {type(exc).__name__}: {exc}")
                finally:
                    # Cleanup remains inside the GPU lock and is guaranteed to
                    # run even if stream close handling itself fails.
                    if owned is not None:
                        try:
                            cleanup = cleanup_owned(owned)
                        except Exception as exc:  # noqa: BLE001 - manifest must preserve cleanup failure
                            cleanup = {
                                "pid": owned.pid,
                                "attempted": True,
                                "term_sent": False,
                                "kill_sent": False,
                                "gone": False,
                                "ownership_valid": False,
                                "status": "FAIL",
                                "errors": [f"{type(exc).__name__}: {exc}"],
                            }
    except LockBusyError as exc:
        reason = {"code": "GPU_LOCK_BUSY", "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 - manifest must preserve failure state
        reason = {"code": "HARNESS_ERROR", "detail": f"{type(exc).__name__}: {exc}"}
    if owned is not None and not (
        cleanup["attempted"]
        and cleanup["status"] == "PASS"
        and cleanup["gone"]
        and cleanup["ownership_valid"]
    ):
        status = "AMBIGUOUS" if cleanup["status"] == "AMBIGUOUS" else "FAIL"
        reason = {"code": "CLEANUP_FAILED", "detail": "child cleanup did not complete successfully"}
    elif stream_close_errors:
        status = "FAIL"
        reason = {"code": "STREAM_CLOSE_FAILED", "detail": "one or more child log streams failed to close"}
    try:
        rollback = rollback_namespace(namespace)
    except Exception as exc:  # noqa: BLE001 - manifest must preserve rollback failure
        rollback = {
            "attempted": True,
            "status": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
            "errors": [f"{type(exc).__name__}: {exc}"],
        }
        status = "FAIL"
        reason = {"code": "ROLLBACK_FAILED", "detail": rollback["error"]}
    finished_at = utc_now()
    result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": namespace.run_id,
        "status": status,
        "reason": reason,
        "started_at": started_at,
        "finished_at": finished_at,
        "exit_code": exit_code,
        "provenance": provenance,
        "health": None if health is None else {"url": health.url, "observations": health.observations},
        "fail_fast": dataclasses.asdict(monitor),
        "cleanup": cleanup,
        "stream_close_errors": stream_close_errors,
        "rollback": rollback,
        "rollback_baseline": {"repo": provenance["repo"], "artifact_namespace": str(namespace.path)},
    }
    namespace.write_metadata("manifest.json", result)
    print(json.dumps(result, default=_json_default, sort_keys=True))
    return 0 if status == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="p3")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--health-url")
    parser.add_argument("--health-timeout", type=float, default=60.0)
    parser.add_argument("--health-poll", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--zero-progress-timeout", type=float, default=300.0)
    parser.add_argument("--health-loss-threshold", type=int, default=3)
    parser.add_argument("--monitor-poll", type=float, default=1.0)
    parser.add_argument("--progress-file", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="child command after --")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        raise SystemExit("a child command is required after --")
    return _run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
