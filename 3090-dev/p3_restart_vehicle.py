"""CPU-testable P3 restart vehicle built on :mod:`p3_harness`.

The vehicle owns no product semantics.  A supplied child command represents
the process under test; supplied seed, rebuild, and restore subprocess
commands provide the durable-store actions.  Commands receive these
environment variables:

``P3_STORAGE_PATH``
    The caller-provided durable storage namespace.
``P3_ACK_PATH`` / ``P3_RESTORE_PATH``
    JSON evidence paths.  Seed must write ``{"status": "ACK", "identity":
    ...}``; restore must write ``{"status": "RESTORED", "identity": ...}``.
``P3_PROGRESS_PATH``
    Optional progress JSON path used by the common fail-fast monitor.

The manifest is retained in the common artifact namespace.  Storage is never
deleted by this vehicle.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Any, Iterable, Sequence

import p3_harness
from p3_harness import (
    DEFAULT_ARTIFACT_ROOT,
    ArtifactNamespace,
    FailFastMonitor,
    GpuLock,
    HarnessError,
    HealthGate,
    OwnedProcess,
    args_hash,
    cleanup_owned,
    collect_provenance,
    launch_owned,
    rollback_namespace,
    sanitize_argv,
    utc_now,
)


class RestartVehicleError(HarnessError):
    """The restart contract could not be established."""


@dataclasses.dataclass(frozen=True)
class ActionContext:
    storage_path: Path
    ack_path: Path
    restore_path: Path
    progress_path: Path | None
    run_id: str
    phase: str


@dataclasses.dataclass(frozen=True)
class RestartVehicleConfig:
    child_command: Sequence[str]
    storage_path: Path
    seed_command: Sequence[str] | None = None
    rebuild_command: Sequence[str] | None = None
    restore_command: Sequence[str] | None = None
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    profile: str = "p3-restart"
    repo_root: Path = Path.cwd()
    cwd: Path | None = None
    health_url: str | None = None
    health_timeout: float = 60.0
    health_poll: float = 1.0
    timeout: float = 3600.0
    zero_progress_timeout: float = 300.0
    health_loss_threshold: int = 3
    monitor_poll: float = 1.0
    progress_path: Path | None = None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_identity() -> dict[str, str]:
    source = Path(__file__).resolve()
    return {"path": str(source), "sha256": _sha256_file(source)}


def _profile_identity(profile: str) -> dict[str, str]:
    return {"name": profile, "sha256": hashlib.sha256(profile.encode()).hexdigest()}


def _command_identity(command: Sequence[str]) -> dict[str, Any]:
    command = [str(item) for item in command]
    return {"argv": sanitize_argv(command), "args_sha256": args_hash(command)}


def _read_progress(path: Path | None) -> Any:
    if path is None:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload.get("progress")
    except (OSError, ValueError, AttributeError):
        return None


def _wait_owned(
    owned: OwnedProcess,
    *,
    health: HealthGate | None,
    progress_path: Path | None,
    config: RestartVehicleConfig,
) -> dict[str, Any]:
    started = time.monotonic()
    monitor = FailFastMonitor(
        timeout=config.timeout,
        zero_progress_timeout=config.zero_progress_timeout,
        health_loss_threshold=config.health_loss_threshold,
        started=started,
        last_progress_at=started,
    )
    while owned.process.poll() is None:
        healthy = True if health is None else health.check()
        state = monitor.observe(progress=_read_progress(progress_path), healthy=healthy)
        if state != "RUNNING":
            return {"status": "FAIL", "reason": monitor.reason, "monitor": dataclasses.asdict(monitor)}
        time.sleep(max(0.0, config.monitor_poll))
    return {
        "status": "PASS" if owned.process.returncode == 0 else "FAIL",
        "exit_code": owned.process.returncode,
        "reason": None if owned.process.returncode == 0 else {"code": "CHILD_EXIT"},
        "monitor": dataclasses.asdict(monitor),
    }


def _health_ready(owned: OwnedProcess, health: HealthGate | None) -> tuple[bool, dict[str, Any]]:
    if owned.process.poll() is not None:
        return False, {"code": "CHILD_EXIT", "exit_code": owned.process.returncode}
    if health is not None and not health.wait():
        return False, {"code": "HEALTH_TIMEOUT", "detail": "health gate did not become healthy"}
    if owned.process.poll() is not None:
        return False, {"code": "CHILD_EXIT", "exit_code": owned.process.returncode}
    if not owned.identity_matches():
        return False, {"code": "PID_IDENTITY_MISMATCH", "detail": "owned child identity changed"}
    return True, {"code": "HEALTHY" if health is not None else "ALIVE"}


def _health_still_ready(owned: OwnedProcess, health: HealthGate | None) -> tuple[bool, dict[str, Any]]:
    """Check the final owner, PID identity, and current health without waiting."""

    if owned.process.poll() is not None:
        return False, {"code": "CHILD_EXIT", "exit_code": owned.process.returncode}
    if not owned.identity_matches():
        return False, {"code": "PID_IDENTITY_MISMATCH", "detail": "owned child identity changed"}
    if health is not None and not health.check():
        return False, {"code": "HEALTH_LOSS", "detail": "restarted child lost health"}
    if owned.process.poll() is not None:
        return False, {"code": "CHILD_EXIT", "exit_code": owned.process.returncode}
    return True, {"code": "HEALTHY" if health is not None else "ALIVE"}


def _sigkill_owned(owned: OwnedProcess, *, timeout: float) -> dict[str, Any]:
    """SIGKILL exactly one still-live, identity-checked child."""

    result: dict[str, Any] = {
        "pid": owned.pid,
        "signal": signal.SIGKILL,
        "sent": False,
        "alive_before": owned.process.poll() is None,
        "ownership_valid": False,
        "gone": False,
        "exit_code": None,
        "status": "FAIL",
        "errors": [],
    }
    ownership_valid, ownership_error = owned.ownership_state()
    result["ownership_valid"] = ownership_valid
    if not ownership_valid:
        result["errors"].append(ownership_error or "PID ownership is ambiguous")
        result["status"] = "AMBIGUOUS"
        return result
    if owned.process.poll() is not None:
        result["errors"].append("child was not alive after ACK")
        result["status"] = "FAIL"
        return result
    if not owned.identity_matches():
        result["errors"].append("PID identity mismatch before SIGKILL")
        result["status"] = "AMBIGUOUS"
        return result
    try:
        os.kill(owned.pid, signal.SIGKILL)
        result["sent"] = True
        owned.process.wait(timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        return result
    result["exit_code"] = owned.process.returncode
    result["gone"] = owned.process.returncode is not None and p3_harness._proc_start_time(owned.pid) is None
    if not result["gone"]:
        result["errors"].append("owned PID remains present after SIGKILL")
    elif result["exit_code"] != -signal.SIGKILL:
        result["errors"].append(f"child exit was {result['exit_code']}, expected {-signal.SIGKILL}")
    else:
        result["status"] = "PASS"
    return result


def _snapshot_storage(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        raise RestartVehicleError(f"storage namespace is not a directory: {path}")
    entries: list[dict[str, Any]] = []
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise RestartVehicleError(f"storage symlink is not accepted: {item}")
        if item.is_file():
            relative = item.relative_to(path).as_posix()
            entries.append({"path": relative, "size": item.stat().st_size, "sha256": _sha256_file(item)})
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return {
        "files": entries,
        "file_count": len(entries),
        "total_bytes": sum(item["size"] for item in entries),
        "tree_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _evidence(path: Path, *, expected_status: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RestartVehicleError(f"missing or invalid {expected_status} evidence: {path}") from exc
    if not isinstance(payload, dict) or payload.get("status") != expected_status:
        raise RestartVehicleError(f"{expected_status} evidence status mismatch: {path}")
    if "identity" not in payload:
        raise RestartVehicleError(f"{expected_status} evidence has no identity: {path}")
    return payload


def _action_environment(context: ActionContext) -> dict[str, str]:
    values = {
        "P3_STORAGE_PATH": str(context.storage_path),
        "P3_ACK_PATH": str(context.ack_path),
        "P3_RESTORE_PATH": str(context.restore_path),
        "P3_RUN_ID": context.run_id,
        "P3_PHASE": context.phase,
    }
    if context.progress_path is not None:
        values["P3_PROGRESS_PATH"] = str(context.progress_path)
    return values


def _run_command_action(
    *,
    phase: str,
    command: Sequence[str],
    context: ActionContext,
    namespace: ArtifactNamespace,
    health: HealthGate | None,
    config: RestartVehicleConfig,
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update(_action_environment(context))
    stdout_path = namespace.path / "logs" / f"{phase}.stdout.log"
    stderr_path = namespace.path / "logs" / f"{phase}.stderr.log"
    owned: OwnedProcess | None = None
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            process = subprocess.Popen(
                [str(item) for item in command],
                stdout=stdout,
                stderr=stderr,
                cwd=config.cwd,
                env=environment,
                start_new_session=True,
            )
            owned = OwnedProcess(process, [str(item) for item in command], utc_now(), p3_harness._proc_start_time(process.pid))
            waited = _wait_owned(owned, health=health, progress_path=config.progress_path, config=config)
    except Exception as exc:  # noqa: BLE001 - preserve action failure
        waited = {"status": "FAIL", "reason": {"code": "ACTION_FAILED", "detail": f"{type(exc).__name__}: {exc}"}}
    cleanup = None
    if owned is not None:
        try:
            cleanup = cleanup_owned(owned)
        except Exception as exc:  # noqa: BLE001 - preserve cleanup failure
            cleanup = {"status": "FAIL", "errors": [f"{type(exc).__name__}: {exc}"], "pid": owned.pid}
    result = {"mode": "command", "command": _command_identity(command), **waited, "cleanup": cleanup}
    if cleanup is not None and cleanup.get("status") != "PASS":
        result["status"] = "FAIL"
        result["reason"] = {"code": "CLEANUP_FAILED"}
    return result


def _safe_cleanup(owned: OwnedProcess | None) -> dict[str, Any]:
    if owned is None:
        return {"attempted": False, "status": "PASS", "gone": True, "ownership_valid": True, "errors": []}
    try:
        return cleanup_owned(owned)
    except Exception as exc:  # noqa: BLE001 - manifest must preserve cleanup failure
        return {
            "pid": owned.pid,
            "attempted": True,
            "status": "FAIL",
            "gone": False,
            "ownership_valid": False,
            "errors": [f"{type(exc).__name__}: {exc}"],
        }


def _validate_artifact_root(root: Path) -> None:
    """Require all retained run artifacts to live below the common P3 root."""

    supplied = Path(root).expanduser().absolute().resolve(strict=False)
    mandatory = DEFAULT_ARTIFACT_ROOT.absolute().resolve(strict=False)
    if supplied != mandatory and mandatory not in supplied.parents:
        raise RestartVehicleError(f"artifact root must be under {DEFAULT_ARTIFACT_ROOT}")


def _finalize_result(namespace: ArtifactNamespace, result: dict[str, Any]) -> dict[str, Any]:
    if any(item.get("status") != "PASS" for item in result["cleanup"].values()):
        result["status"] = "FAIL"
        result["reason"] = {"code": "CLEANUP_FAILED"}
    elif result["status"] != "PASS":
        for phase in ("start", "seed", "kill", "restart", "rebuild", "restore"):
            phase_result = result[phase]
            if phase_result.get("status") == "FAIL" and phase_result.get("reason"):
                result["reason"] = phase_result["reason"]
                break
    try:
        result["rollback"] = rollback_namespace(namespace)
        if result["rollback"].get("status") != "PASS":
            result["status"] = "FAIL"
            detail = result["rollback"].get("error") or result["rollback"].get("errors") or result["rollback"].get("detail")
            result["reason"] = {"code": "ROLLBACK_FAILED", "detail": detail}
    except Exception as exc:  # noqa: BLE001 - final manifest must preserve rollback failure
        result["rollback"] = {
            "attempted": True,
            "status": "FAIL",
            "error": f"{type(exc).__name__}: {exc}",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "detail": "rollback evaluation failed",
        }
        result["status"] = "FAIL"
        result["reason"] = {"code": "ROLLBACK_FAILED", "detail": result["rollback"]["error"]}
    result["finished_at"] = utc_now()
    manifest_path = namespace.path / "metadata" / "manifest.json"
    result["manifest_write"] = {"status": "PASS", "path": str(manifest_path)}
    try:
        namespace.write_metadata("manifest.json", result)
    except Exception as exc:  # noqa: BLE001 - caller receives explicit manifest failure
        result["status"] = "FAIL"
        result["reason"] = {"code": "MANIFEST_WRITE_FAILED", "detail": f"{type(exc).__name__}: {exc}"}
        result["manifest_write"] = {"status": "FAIL", "path": str(manifest_path), "error": str(exc)}
    return result


def run_restart(
    config: RestartVehicleConfig,
) -> dict[str, Any]:
    """Run ``start -> seed/ACK -> exact SIGKILL -> restart -> restore/oracle``."""

    _validate_artifact_root(config.artifact_root)
    if config.seed_command is None or config.restore_command is None:
        raise RestartVehicleError("seed_command and restore_command are required subprocess commands")
    commands = [config.child_command, config.seed_command, config.rebuild_command, config.restore_command]
    for command in commands:
        if command is not None:
            sanitize_argv(command)
    namespace = ArtifactNamespace(config.artifact_root, profile=config.profile)
    namespace.create()
    started_at = utc_now()
    storage_path = config.storage_path.absolute()
    ack_path = namespace.path / "metadata" / "seed_ack.json"
    restore_path = namespace.path / "metadata" / "restore.json"
    result: dict[str, Any] = {
        "schema_version": "p3-restart-vehicle.v1",
        "run_id": namespace.run_id,
        "status": "FAIL",
        "reason": {"code": "NOT_COMPLETED"},
        "started_at": started_at,
        "finished_at": None,
        "provenance": {},
        "storage": {"path": str(storage_path)},
        "start": {},
        "seed": {},
        "kill": {},
        "restart": {},
        "rebuild": {},
        "restore": {},
        "cleanup": {},
        "rollback": {
            "attempted": False,
            "status": "PENDING",
            "error": None,
            "errors": [],
            "detail": "rollback deferred to finalization",
        },
        "rollback_baseline": {"artifact_namespace": str(namespace.path), "storage_path": str(storage_path)},
        "manifest_write": {"status": "PENDING", "path": str(namespace.path / "metadata" / "manifest.json")},
    }
    try:
        provenance = collect_provenance(
            repo_root=config.repo_root,
            profile=config.profile,
            argv=config.child_command,
            run_id=namespace.run_id,
            started_at=started_at,
        )
        provenance.update(
            {
                "source": _source_identity(),
                "profile_identity": _profile_identity(config.profile),
                "commands": {
                    "child": _command_identity(config.child_command),
                    "seed": None if config.seed_command is None else _command_identity(config.seed_command),
                    "rebuild": None if config.rebuild_command is None else _command_identity(config.rebuild_command),
                    "restore": None if config.restore_command is None else _command_identity(config.restore_command),
                },
            }
        )
        result["provenance"] = provenance
        try:
            namespace.write_metadata("provenance.json", provenance)
        except Exception as exc:  # noqa: BLE001 - final result reports this path
            write_error = {
                "code": "PROVENANCE_WRITE_FAILED",
                "detail": f"{type(exc).__name__}: {exc}",
            }
            provenance["write_error"] = write_error
            result["reason"] = write_error
            return _finalize_result(namespace, result)
    except Exception as exc:  # noqa: BLE001 - final manifest must preserve initialization failure
        result["reason"] = {"code": "VEHICLE_ERROR", "detail": f"{type(exc).__name__}: {exc}"}
        return _finalize_result(namespace, result)

    context_base = dict(
        storage_path=storage_path,
        ack_path=ack_path,
        restore_path=restore_path,
        progress_path=config.progress_path,
        run_id=namespace.run_id,
    )
    first: OwnedProcess | None = None
    restarted: OwnedProcess | None = None
    health = None if config.health_url is None else HealthGate(config.health_url, timeout=config.health_timeout, poll_interval=config.health_poll)
    try:
        with GpuLock():
            storage_path.mkdir(parents=True, exist_ok=True)
            log_dir = namespace.path / "logs"
            first_stdout = None
            first_stderr = None
            try:
                first_stdout = (log_dir / "child.start.stdout.log").open("w", encoding="utf-8")
                first_stderr = (log_dir / "child.start.stderr.log").open("w", encoding="utf-8")
                first = launch_owned(config.child_command, stdout=first_stdout, stderr=first_stderr, cwd=config.cwd)
                result["start"] = first.metadata()
                ready, reason = _health_ready(first, health)
                if not ready:
                    result["reason"] = reason
                else:
                    seed_context = ActionContext(phase="seed", **context_base)
                    result["seed"] = _run_command_action(
                        phase="seed", command=config.seed_command, context=seed_context,
                        namespace=namespace, health=health, config=config,
                    )
                    if result["seed"].get("status") == "PASS":
                        try:
                            ack = _evidence(ack_path, expected_status="ACK")
                            seed_storage = _snapshot_storage(storage_path)
                            if seed_storage["file_count"] == 0:
                                raise RestartVehicleError("seed storage snapshot is empty")
                            result["seed"]["evidence"] = ack
                            result["seed"]["storage"] = seed_storage
                            result["rollback_baseline"]["seed_storage"] = seed_storage
                            result["reason"] = {"code": "ACK"}
                        except RestartVehicleError as exc:
                            result["seed"] = {**result["seed"], "status": "FAIL", "reason": {"code": "ACK_FAILED", "detail": str(exc)}}
                    elif result["seed"].get("reason"):
                        result["reason"] = result["seed"]["reason"]
                    if result["seed"].get("status") == "PASS":
                        if health is not None and not health.check():
                            result["reason"] = {"code": "HEALTH_LOSS", "detail": "health lost before SIGKILL"}
                        else:
                            result["kill"] = _sigkill_owned(first, timeout=config.timeout)
                            if result["kill"].get("status") != "PASS":
                                result["kill"]["reason"] = {
                                    "code": "CHILD_EXIT_AFTER_ACK"
                                    if "child was not alive after ACK" in result["kill"].get("errors", [])
                                    else "SIGKILL_FAILED",
                                    "detail": result["kill"].get("errors", []),
                                }
                            if result["kill"].get("status") == "PASS":
                                with (log_dir / "child.restart.stdout.log").open("w", encoding="utf-8") as restart_stdout, (log_dir / "child.restart.stderr.log").open("w", encoding="utf-8") as restart_stderr:
                                    restarted = launch_owned(config.child_command, stdout=restart_stdout, stderr=restart_stderr, cwd=config.cwd)
                                result["restart"] = restarted.metadata()
                                if restarted.pid == first.pid and restarted.proc_start_time == first.proc_start_time:
                                    result["reason"] = {"code": "FRESH_IDENTITY_FAILED"}
                                else:
                                    ready, reason = _health_ready(restarted, health)
                                    if not ready:
                                        result["reason"] = reason
                                    else:
                                        rebuild_context = ActionContext(phase="rebuild", **context_base)
                                        if config.rebuild_command is not None:
                                            result["rebuild"] = _run_command_action(
                                                phase="rebuild", command=config.rebuild_command, context=rebuild_context,
                                                namespace=namespace, health=health, config=config,
                                            )
                                        else:
                                            result["rebuild"] = {"status": "PASS", "mode": "implicit", "detail": "no rebuild action supplied"}
                                        restore_context = ActionContext(phase="restore", **context_base)
                                        if result["rebuild"].get("status") == "PASS":
                                            result["restore"] = _run_command_action(
                                                phase="restore", command=config.restore_command, context=restore_context,
                                                namespace=namespace, health=health, config=config,
                                            )
                                        if result["restore"].get("status") == "PASS":
                                            try:
                                                restore_evidence = _evidence(restore_path, expected_status="RESTORED")
                                                restore_storage = _snapshot_storage(storage_path)
                                                result["restore"]["evidence"] = restore_evidence
                                                result["restore"]["storage"] = restore_storage
                                                if restore_evidence["identity"] != result["seed"]["evidence"]["identity"]:
                                                    result["reason"] = {"code": "IDENTITY_MISMATCH"}
                                                elif restore_storage != result["seed"]["storage"]:
                                                    result["reason"] = {"code": "BYTE_MISMATCH"}
                                                else:
                                                    final_ready, final_reason = _health_still_ready(restarted, health)
                                                    result["restart"]["final_check"] = final_reason
                                                    if not final_ready:
                                                        result["restart"]["status"] = "FAIL"
                                                        result["restart"]["reason"] = final_reason
                                                        result["reason"] = final_reason
                                                    else:
                                                        result["status"] = "PASS"
                                                        result["reason"] = {"code": "IDENTITY_BYTE_EQUIVALENT"}
                                            except RestartVehicleError as exc:
                                                result["restore"] = {**result["restore"], "status": "FAIL", "reason": {"code": "RESTORE_FAILED", "detail": str(exc)}}
                                                result["reason"] = result["restore"]["reason"]
            finally:
                try:
                    if first_stdout is not None:
                        first_stdout.close()
                finally:
                    try:
                        if first_stderr is not None:
                            first_stderr.close()
                    finally:
                        # Both owned-child cleanups stay inside the GPU lock,
                        # including stream and action exception paths.
                        result["cleanup"]["start"] = _safe_cleanup(first)
                        result["cleanup"]["restart"] = _safe_cleanup(restarted)
    except Exception as exc:  # noqa: BLE001 - preserve a structured vehicle result
        result["reason"] = {"code": "VEHICLE_ERROR", "detail": f"{type(exc).__name__}: {exc}"}
    finally:
        _finalize_result(namespace, result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--profile", default="p3-restart")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--cwd", type=Path)
    parser.add_argument("--storage-path", type=Path, required=True)
    parser.add_argument("--seed-command", nargs="+", required=True)
    parser.add_argument("--rebuild-command", nargs="+")
    parser.add_argument("--restore-command", nargs="+", required=True)
    parser.add_argument("--health-url")
    parser.add_argument("--health-timeout", type=float, default=60.0)
    parser.add_argument("--health-poll", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--zero-progress-timeout", type=float, default=300.0)
    parser.add_argument("--health-loss-threshold", type=int, default=3)
    parser.add_argument("--monitor-poll", type=float, default=1.0)
    parser.add_argument("--progress-path", type=Path)
    parser.add_argument("child_command", nargs=argparse.REMAINDER)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    child = list(args.child_command)
    if child and child[0] == "--":
        child = child[1:]
    if not child:
        raise SystemExit("a child command is required after --")
    config = RestartVehicleConfig(
        child_command=child,
        storage_path=args.storage_path,
        seed_command=args.seed_command,
        rebuild_command=args.rebuild_command,
        restore_command=args.restore_command,
        artifact_root=args.artifact_root,
        profile=args.profile,
        repo_root=args.repo_root,
        cwd=args.cwd,
        health_url=args.health_url,
        health_timeout=args.health_timeout,
        health_poll=args.health_poll,
        timeout=args.timeout,
        zero_progress_timeout=args.zero_progress_timeout,
        health_loss_threshold=args.health_loss_threshold,
        monitor_poll=args.monitor_poll,
        progress_path=args.progress_path,
    )
    result = run_restart(config)
    print(json.dumps(result, sort_keys=True, default=str))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
