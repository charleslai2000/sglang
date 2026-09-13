"""Bounded P3 pressure/eviction vehicle for the existing Gate-3 workloads.

This is acceptance infrastructure only.  It starts the explicitly supplied
workload commands, records their structured output, and never imports product
packages or reimplements either workload.  A workload may emit a line of the
form ``P3_PRESSURE_RESULT {JSON}`` and/or point at an existing ``run_dir``
containing the normal Gate-3 ``verdict.json`` and ``runs.csv`` artifacts.

The acceptance verdict is deliberately stricter than a successful subprocess:
the workload result and explicit evidence for liveness, starvation,
zero-progress, timeout, and corruption are all required for PASS.  Missing
evidence is NOT_COMPUTABLE; it is never inferred from an exit code.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import sys
import time
from typing import Any, Iterable, Mapping, Sequence

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


SCHEMA_VERSION = "p3-pressure-vehicle.v1"
RESULT_SCHEMA_VERSION = "p3-pressure-result.v1"
RESULT_TYPE = "P3_PRESSURE_RESULT"
_RUN_DIR_RE = re.compile(r"(?:^|\s)run_dir=(\S+)")
_REQUIRED_EVIDENCE = ("health", "no_starvation", "no_zero_progress", "no_timeout", "no_corruption")
_RESULT_REQUIRED_FIELDS = {"schema_version", "type", "status", "source", *_REQUIRED_EVIDENCE}
_RESULT_STATUSES = {"PASS", "FAIL"}
_CAPACITY_RUN_COLUMNS = (
    "agent_id", "turn", "turn_kind", "round", "ts_start", "ts_end", "ttft_s", "wall_s",
    "http", "finished", "finish_reason", "rid", "rc", "history_tokens", "prompt_len",
    "completion_tokens", "cached_tokens", "cached_device", "cached_host", "cached_storage",
    "prefill_input_delta", "prefill_devicehit_delta", "prefill_hosthit_delta",
    "prefill_storagehit_delta", "output_field", "output_sha16",
)
_PARKED_RUN_COLUMNS = (
    "session", "turn", "turn_kind", "round", "ts_start", "ts_end", "ttft_s", "wall_s",
    "http", "finished", "finish_reason", "rid", "rc", "history_tokens", "prompt_len",
    "completion_tokens", "cached_tokens", "cached_device", "cached_host", "cached_storage",
    "prefill_input_delta", "prefill_devicehit_delta", "prefill_hosthit_delta",
    "prefill_storagehit_delta", "output_field", "output_sha16",
)
_PARKED_RESUME_COLUMNS = _PARKED_RUN_COLUMNS + (
    "age_at_wake_s", "turn_kind_parked", "hit_parent_mux", "rh_synced", "rh_flag", "cohort",
)
_RUN_COLUMNS = _CAPACITY_RUN_COLUMNS
_PRODUCERS = {"capacity", "parked"}
_FINISH_REASONS = {"stop", "length", "end_turn", "eos", "timeout", "error", "cancelled", "content_filter", "tool_calls"}
_TURN_KINDS_BY_PRODUCER = {
    "capacity": {"cold", "warm"},
    "parked": {"resume"},
}
_PARKED_BUILD_KIND = "build"
_PARKED_OPTIONAL_COLUMNS = {"age_at_wake_s", "turn_kind_parked", "hit_parent_mux", "rh_synced", "rh_flag", "cohort"}
_OPTIONAL_NUMBER_COLUMNS = {"age_at_wake_s"}
_OPTIONAL_INTEGER_COLUMNS = {"rh_synced"}
_PARKED_NULLABLE_COLUMNS = {"age_at_wake_s", "cohort"}
_PARKED_HIT_PARENTS = {
    "GPU-resident", "Host-ready", "RH-staged", "Host-ready-STAGED", "L3-on-demand", "miss",
}
_PARKED_RH_PARENTS = {"RH-staged", "Host-ready-STAGED"}
_PARKED_HIT_PARENTS_BY_RH_FLAG = {
    "off": {"GPU-resident", "Host-ready", "L3-on-demand", "miss"},
    "on": {"GPU-resident", "RH-staged", "Host-ready-STAGED", "L3-on-demand", "miss"},
}
_PARKED_COHORTS = {"HOT", "MID", "COLD"}
_PARKED_RH_FLAGS = {"on", "off"}
_ATTRIBUTION_COLUMNS = ("event", "session_id", "turn", "ts", "reason", "prior_l3", "hit_sum", "ttft_s", "evidence_ref")
_ATTRIBUTION_INTEGER_COLUMNS = {"turn"}
_ATTRIBUTION_NUMBER_COLUMNS = {"ts", "hit_sum", "ttft_s"}
_INTEGER_COLUMNS = {"agent_id", "session", "turn", "round", "http", "rc", "history_tokens", "prompt_len", "completion_tokens"}
_NUMBER_COLUMNS = {"ts_start", "ts_end", "ttft_s", "wall_s", "cached_tokens", "cached_device", "cached_host", "cached_storage", "prefill_input_delta", "prefill_devicehit_delta", "prefill_hosthit_delta", "prefill_storagehit_delta"}


class PressureVehicleError(HarnessError):
    """The pressure vehicle contract could not be established."""


@dataclasses.dataclass(frozen=True)
class PressureVehicleConfig:
    workload_commands: Sequence[Sequence[str]]
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    profile: str = "p3-pressure"
    repo_root: Path = Path.cwd()
    cwd: Path | None = None
    health_url: str | None = None
    health_timeout: float = 60.0
    health_poll: float = 1.0
    timeout: float = 3600.0
    zero_progress_timeout: float | None = 300.0
    health_loss_threshold: int = 3
    monitor_poll: float = 1.0
    progress_path: Path | None = None
    producer: str | None = None


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


def _validate_artifact_root(root: Path) -> None:
    supplied = Path(root).expanduser().absolute().resolve(strict=False)
    mandatory = DEFAULT_ARTIFACT_ROOT.absolute().resolve(strict=False)
    if supplied != mandatory:
        raise PressureVehicleError(
            f"artifact root must remain exactly {DEFAULT_ARTIFACT_ROOT}"
        )


def _read_progress(path: Path | None) -> Any:
    if path is None:
        return None


def _progress_sample(path: Path | None) -> tuple[bool, Any, str | None]:
    if path is None:
        return False, None, "progress evidence is required while zero-progress monitoring is enabled"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return False, None, f"unreadable progress evidence: {type(exc).__name__}: {exc}"
    if not isinstance(payload, Mapping) or "progress" not in payload:
        return False, None, "progress evidence must be an object containing progress"
    value = payload["progress"]
    try:
        value = _finite_number(value, label="progress")
    except ValueError as exc:
        return False, None, str(exc)
    if value < 0:
        return False, None, "progress must be non-negative"
    return True, value, None


def _wait_owned(
    owned: OwnedProcess,
    *,
    health: HealthGate | None,
    config: PressureVehicleConfig,
) -> dict[str, Any]:
    started = time.monotonic()
    monitor = FailFastMonitor(
        timeout=config.timeout,
        zero_progress_timeout=config.zero_progress_timeout,
        health_loss_threshold=config.health_loss_threshold,
        started=started,
        last_progress_at=started,
    )
    if health is not None and not health.wait():
        return {
            "status": "FAIL",
            "exit_code": owned.process.poll(),
            "reason": {"code": "HEALTH_TIMEOUT", "detail": "health gate did not become healthy"},
            "monitor": dataclasses.asdict(monitor),
        }
    while owned.process.poll() is None:
        healthy = True if health is None else health.check()
        progress = None
        if config.zero_progress_timeout is not None:
            valid, progress, progress_error = _progress_sample(config.progress_path)
            if not valid:
                return {
                    "status": "NOT_COMPUTABLE",
                    "exit_code": owned.process.poll(),
                    "reason": {"code": "PROGRESS_UNAVAILABLE", "detail": progress_error},
                    "monitor": dataclasses.asdict(monitor),
                }
        state = monitor.observe(progress=progress, healthy=healthy)
        if state != "RUNNING":
            return {
                "status": "FAIL",
                "exit_code": owned.process.poll(),
                "reason": monitor.reason,
                "monitor": dataclasses.asdict(monitor),
            }
        time.sleep(max(0.0, config.monitor_poll))
    exit_code = owned.process.returncode
    if config.zero_progress_timeout is not None:
        valid, _progress, progress_error = _progress_sample(config.progress_path)
        if not valid:
            return {
                "status": "NOT_COMPUTABLE",
                "exit_code": exit_code,
                "reason": {"code": "PROGRESS_UNAVAILABLE", "detail": progress_error},
                "monitor": dataclasses.asdict(monitor),
            }
    return {
        "status": "PASS" if exit_code == 0 else "FAIL",
        "exit_code": exit_code,
        "reason": None if exit_code == 0 else {"code": "WORKLOAD_EXIT", "exit_code": exit_code},
        "monitor": dataclasses.asdict(monitor),
    }


def _under_root(path: Path, root: Path) -> bool:
    try:
        path.absolute().resolve(strict=False).relative_to(root.absolute().resolve(strict=False))
    except ValueError:
        return False
    return True


def _safe_under_root(path: Path, root: Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if not _under_root(candidate, root):
        raise PressureVehicleError(f"{label} outside artifact namespace: {candidate}")
    for component in _existing_components(candidate):
        if component.is_symlink():
            raise PressureVehicleError(f"{label} contains symlink path component: {component}")
    resolved = candidate.absolute().resolve(strict=False)
    resolved_root = Path(root).absolute().resolve(strict=False)
    if not _under_root(resolved, resolved_root):
        raise PressureVehicleError(f"{label} escapes artifact namespace: {candidate}")
    return resolved


def _existing_components(path: Path) -> list[Path]:
    current = Path(path.absolute().anchor)
    components: list[Path] = []
    for part in path.absolute().parts[1:]:
        current /= part
        try:
            current.lstat()
        except FileNotFoundError:
            break
        components.append(current)
    return components


def _load_json(path: Path, *, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise PressureVehicleError(f"corrupt {label}: {path}: {exc}") from exc


def _number(value: Any, *, label: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PressureVehicleError(f"{label} must be numeric")
    return value


def _csv_rows(
    path: Path,
    required: Sequence[str],
    *,
    label: str,
    producer: str,
    nullable: set[str] | None = None,
) -> list[dict[str, Any]]:
    nullable = nullable or set()
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            columns = reader.fieldnames or []
            missing = [column for column in required if column not in columns]
            if missing:
                raise PressureVehicleError(f"{label} missing required columns: {missing}")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise PressureVehicleError(f"corrupt {label}: {path}: {exc}") from exc
    normalized: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, 2):
        if any(value is None for value in row.values()):
            raise PressureVehicleError(f"{label} has malformed columns at row {row_number}")
        parsed: dict[str, Any] = {}
        for column in required:
            value = row.get(column)
            if value is None and column not in nullable:
                raise PressureVehicleError(f"{label} null required field {column} at row {row_number}")
            if value == "" and column not in nullable:
                raise PressureVehicleError(f"{label} null required field {column} at row {row_number}")
            if value in {None, ""} and column in nullable:
                parsed[column] = None
                continue
            try:
                if column in _INTEGER_COLUMNS:
                    if not re.fullmatch(r"[+-]?\d+", value):
                        raise ValueError("integer syntax")
                    parsed[column] = int(value)
                elif column in _NUMBER_COLUMNS:
                    parsed[column] = _finite_number(value, label=f"{label} {column} at row {row_number}")
                elif column == "finished":
                    if value.lower() not in {"true", "false"}:
                        raise ValueError("boolean syntax")
                    parsed[column] = value.lower() == "true"
                elif column == "prior_l3":
                    if value not in {"True", "False"}:
                        raise ValueError("Boolean syntax")
                    parsed[column] = value == "True"
                elif column == "turn_kind_parked":
                    if value != "resume":
                        raise ValueError("parked turn kind")
                    parsed[column] = value
                elif column == "hit_parent_mux":
                    if value not in _PARKED_HIT_PARENTS:
                        raise ValueError("parked hit parent")
                    parsed[column] = value
                elif column == "rh_flag":
                    if value not in _PARKED_RH_FLAGS:
                        raise ValueError("parked RH flag")
                    parsed[column] = value
                elif column == "rh_synced":
                    if not re.fullmatch(r"[01]", value):
                        raise ValueError("parked RH synced")
                    parsed[column] = int(value)
                elif column == "age_at_wake_s":
                    parsed[column] = _finite_number(value, label=f"{label} {column} at row {row_number}")
                elif column == "cohort":
                    if value not in _PARKED_COHORTS:
                        raise ValueError("parked cohort")
                    parsed[column] = value
                elif column == "finish_reason":
                    if value not in _FINISH_REASONS:
                        raise ValueError("finish reason")
                elif column == "turn_kind":
                    if value not in _TURN_KINDS_BY_PRODUCER[producer]:
                        raise ValueError("turn kind")
                    parsed[column] = value
                else:
                    parsed[column] = value
            except ValueError as exc:
                raise PressureVehicleError(f"invalid {label} field {column} at row {row_number}") from exc
        for column, value in row.items():
            if column not in parsed:
                if column in _OPTIONAL_NUMBER_COLUMNS:
                    if value == "" and column in nullable:
                        parsed[column] = None
                    else:
                        parsed[column] = _finite_number(value, label=f"{label} {column} at row {row_number}")
                elif column in _OPTIONAL_INTEGER_COLUMNS:
                    if value in {None, ""} and column in nullable:
                        parsed[column] = None
                    elif not re.fullmatch(r"[+-]?\d+", value):
                        raise PressureVehicleError(f"invalid {label} integer {column} at row {row_number}")
                    else:
                        parsed[column] = int(value)
                elif column == "turn_kind_parked":
                    if value != "resume":
                        raise PressureVehicleError(f"invalid {label} parked turn kind at row {row_number}")
                    parsed[column] = value
                elif column == "hit_parent_mux":
                    if value not in _PARKED_HIT_PARENTS:
                        raise PressureVehicleError(f"invalid {label} hit_parent_mux at row {row_number}")
                    parsed[column] = value
                elif column == "rh_flag":
                    if value not in _PARKED_RH_FLAGS:
                        raise PressureVehicleError(f"invalid {label} rh_flag at row {row_number}")
                    parsed[column] = value
                elif column == "rh_synced":
                    if not re.fullmatch(r"[01]", value):
                        raise PressureVehicleError(f"invalid {label} rh_synced at row {row_number}")
                    parsed[column] = int(value)
                elif column == "age_at_wake_s":
                    parsed[column] = _finite_number(value, label=f"{label} {column} at row {row_number}")
                elif column == "cohort":
                    if value not in _PARKED_COHORTS:
                        raise PressureVehicleError(f"invalid {label} cohort at row {row_number}")
                    parsed[column] = value
                else:
                    parsed[column] = None if value in {None, ""} and column in nullable else value
        normalized.append(parsed)
    if not normalized:
        raise PressureVehicleError(f"{label} has no data rows: {path}")
    return normalized


def _attribution_rows(path: Path) -> list[dict[str, Any]]:
    rows = _csv_rows(
        path,
        _ATTRIBUTION_COLUMNS,
        label="recompute_attribution.csv",
        producer="parked",
    )
    for row_number, row in enumerate(rows, 2):
        try:
            if not re.fullmatch(r"[+-]?\d+", str(row["turn"])):
                raise ValueError("integer syntax")
            row["turn"] = int(row["turn"])
        except ValueError as exc:
            raise PressureVehicleError(f"invalid recompute_attribution.csv integer turn at row {row_number}") from exc
        for column in _ATTRIBUTION_INTEGER_COLUMNS:
            value = row[column]
            if not isinstance(value, int) or isinstance(value, bool):
                raise PressureVehicleError(f"invalid recompute_attribution.csv integer {column} at row {row_number}")
        if not isinstance(row["prior_l3"], bool):
            raise PressureVehicleError(
                f"invalid recompute_attribution.csv Boolean prior_l3 at row {row_number}"
            )
        for column in _ATTRIBUTION_NUMBER_COLUMNS:
            try:
                row[column] = _finite_number(row[column], label=f"recompute_attribution.csv {column} at row {row_number}")
            except ValueError as exc:
                raise PressureVehicleError(str(exc)) from exc
            if row[column] < 0:
                raise PressureVehicleError(f"recompute_attribution.csv negative {column} at row {row_number}")
    return rows


def _validate_parked_fields(row: Mapping[str, Any], *, label: str, row_number: int) -> None:
    """Validate the parked resume fields emitted by gate3_parked.py."""

    turn_kind_parked = row.get("turn_kind_parked")
    if turn_kind_parked != "resume":
        raise PressureVehicleError(f"{label} turn_kind_parked must be resume at row {row_number}")
    hit_parent = row.get("hit_parent_mux")
    if hit_parent not in _PARKED_HIT_PARENTS:
        raise PressureVehicleError(f"{label} has invalid hit_parent_mux at row {row_number}")
    rh_synced = row.get("rh_synced")
    if isinstance(rh_synced, bool) or not isinstance(rh_synced, int) or rh_synced not in {0, 1}:
        raise PressureVehicleError(f"{label} rh_synced must be 0 or 1 at row {row_number}")
    rh_flag = row.get("rh_flag")
    if rh_flag not in _PARKED_RH_FLAGS:
        raise PressureVehicleError(f"{label} rh_flag must be on or off at row {row_number}")
    if hit_parent not in _PARKED_HIT_PARENTS_BY_RH_FLAG[rh_flag]:
        raise PressureVehicleError(
            f"{label} hit_parent_mux is impossible with rh_flag at row {row_number}"
        )
    cohort = row.get("cohort")
    if cohort is not None and cohort not in _PARKED_COHORTS:
        raise PressureVehicleError(f"{label} has invalid cohort at row {row_number}")
    expected_rh_synced = int(hit_parent in _PARKED_RH_PARENTS)
    if rh_synced != expected_rh_synced:
        raise PressureVehicleError(
            f"{label} rh_synced contradicts hit_parent_mux at row {row_number}"
        )
    if (rh_flag == "off" and rh_synced != 0) or (hit_parent in _PARKED_RH_PARENTS and rh_flag != "on"):
        raise PressureVehicleError(f"{label} RH flag contradicts parked hit parent at row {row_number}")


def _finite_number(value: Any, *, label: str) -> float | int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must not be bool")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    if isinstance(value, int):
        return value
    return number


def _validate_json_row(
    value: Any,
    required: Sequence[str],
    *,
    label: str,
    row_number: int,
    producer: str,
    nullable: set[str] | None = None,
    turn_kinds: set[str] | None = None,
) -> dict[str, Any]:
    nullable = nullable or set()
    if not isinstance(value, Mapping):
        raise PressureVehicleError(f"{label} row {row_number} is not an object")
    missing = [column for column in required if column not in value]
    if missing:
        raise PressureVehicleError(f"{label} row {row_number} missing required fields: {missing}")
    row = dict(value)
    for column in required:
        field = row[column]
        if field is None and column not in nullable:
            raise PressureVehicleError(f"{label} null required field {column} at row {row_number}")
        if field == "" and column not in nullable:
            raise PressureVehicleError(f"{label} null required field {column} at row {row_number}")
        if field in {None, ""} and column in nullable:
            row[column] = None
            continue
        try:
            if column in _INTEGER_COLUMNS:
                if isinstance(field, bool) or not isinstance(field, int):
                    raise ValueError("integer type")
            elif column in _NUMBER_COLUMNS:
                _finite_number(field, label=f"{label} {column} at row {row_number}")
            elif column == "finished":
                if not isinstance(field, bool):
                    raise ValueError("boolean type")
            elif column == "finish_reason":
                if not isinstance(field, str) or field not in _FINISH_REASONS:
                    raise ValueError("finish reason")
            elif column == "turn_kind" and (not isinstance(field, str) or field not in (turn_kinds or _TURN_KINDS_BY_PRODUCER[producer])):
                raise ValueError("turn kind")
            elif column == "turn_kind_parked" and (not isinstance(field, str) or field != "resume"):
                raise ValueError("parked turn kind")
            elif column == "hit_parent_mux" and (not isinstance(field, str) or field not in _PARKED_HIT_PARENTS):
                raise ValueError("parked hit parent")
            elif column == "rh_synced":
                if isinstance(field, bool) or not isinstance(field, int) or field not in {0, 1}:
                    raise ValueError("parked RH synced")
            elif column == "rh_flag" and (not isinstance(field, str) or field not in _PARKED_RH_FLAGS):
                raise ValueError("parked RH flag")
            elif column == "cohort" and field is not None and field not in _PARKED_COHORTS:
                raise ValueError("parked cohort")
            elif column in {"turn_kind", "rid", "output_field", "output_sha16"} and not isinstance(field, str):
                raise ValueError("string type")
        except ValueError as exc:
            raise PressureVehicleError(f"invalid {label} field {column} at row {row_number}") from exc
    for column, field in row.items():
        if column in _OPTIONAL_NUMBER_COLUMNS:
            if field is not None:
                _finite_number(field, label=f"{label} {column} at row {row_number}")
        elif column in _OPTIONAL_INTEGER_COLUMNS:
            if field is None and column in nullable:
                continue
            if isinstance(field, bool) or not isinstance(field, int):
                raise PressureVehicleError(f"invalid {label} integer {column} at row {row_number}")
        elif column in _PARKED_OPTIONAL_COLUMNS and field is None and column in nullable:
            continue
        elif column in _PARKED_OPTIONAL_COLUMNS and field is None:
            continue
        elif column in _PARKED_OPTIONAL_COLUMNS and not isinstance(field, str):
            raise PressureVehicleError(f"invalid {label} string {column} at row {row_number}")
    return row


def _producer_columns(producer: str) -> tuple[str, ...]:
    if producer == "capacity":
        return _CAPACITY_RUN_COLUMNS
    if producer == "parked":
        return _PARKED_RUN_COLUMNS
    raise PressureVehicleError(f"unsupported or ambiguous Gate-3 producer: {producer!r}")


def _validate_row_semantics(
    rows: Sequence[Mapping[str, Any]],
    *,
    label: str,
    producer: str,
    allowed_turn_kinds: set[str] | None = None,
) -> None:
    """Validate values which are syntactically valid but cannot be evidence."""

    nonnegative = {
        "turn", "round", "session", "agent_id", "history_tokens", "prompt_len",
        "completion_tokens", "cached_tokens", "cached_device", "cached_host",
        "cached_storage", "prefill_input_delta", "prefill_devicehit_delta",
        "prefill_hosthit_delta", "prefill_storagehit_delta", "ttft_s", "wall_s",
        "age_at_wake_s", "ts_start", "ts_end",
    }
    for row_number, row in enumerate(rows, 1):
        kind = row.get("turn_kind")
        if kind not in (allowed_turn_kinds or _TURN_KINDS_BY_PRODUCER[producer]):
            raise PressureVehicleError(f"{label} row {row_number} has invalid turn kind")
        for column in nonnegative:
            value = row.get(column)
            if value is not None:
                try:
                    if _finite_number(value, label=f"{label} {column} at row {row_number}") < 0:
                        raise PressureVehicleError(f"{label} {column} is negative at row {row_number}")
                except ValueError as exc:
                    raise PressureVehicleError(str(exc)) from exc
        start = row.get("ts_start")
        end = row.get("ts_end")
        if end < start:
            raise PressureVehicleError(f"{label} ts_end precedes ts_start at row {row_number}")
        http = row.get("http")
        if not isinstance(http, int) or isinstance(http, bool) or not 100 <= http <= 599:
            raise PressureVehicleError(f"{label} has invalid HTTP status at row {row_number}")
        if row.get("finished") and row.get("finish_reason") in {"timeout", "error", "cancelled"}:
            raise PressureVehicleError(f"{label} finished row has failed finish reason at row {row_number}")
        if row.get("finish_reason") == "stop" and not row.get("finished"):
            # Preserve producer failure evidence for the verdict layer; this is
            # not a parser corruption condition.
            continue
        if row.get("rc") == 0 and not row.get("finished"):
            raise PressureVehicleError(f"{label} unfinished row has successful return code at row {row_number}")
        if row.get("prefill_input_delta") is not None:
            hits = sum(row.get(column) or 0 for column in (
                "prefill_devicehit_delta", "prefill_hosthit_delta", "prefill_storagehit_delta"
            ))
            if hits > row["prefill_input_delta"]:
                raise PressureVehicleError(f"{label} cache-hit deltas exceed input delta at row {row_number}")


def _infer_producer(fieldnames: Sequence[str]) -> str:
    matches = [producer for producer in _PRODUCERS if set(_producer_columns(producer)).issubset(set(fieldnames))]
    if len(matches) != 1:
        raise PressureVehicleError("Gate-3 producer is ambiguous; declare capacity or parked")
    return matches[0]


def _load_gate3_artifacts(run_dir: Path, *, producer: str | None = None) -> dict[str, Any]:
    required_files = ("runs.csv", "join.log", "mid-run-metrics.txt")
    paths = {name: run_dir / name for name in required_files}
    attribution_path = run_dir / "recompute_attribution.csv"
    missing = [name for name, path in paths.items() if not path.is_file() or path.is_symlink()]
    if missing:
        raise PressureVehicleError(f"missing required Gate-3 artifacts in {run_dir}: {missing}")
    build_rows: list[dict[str, Any]] = []
    try:
        with paths["runs.csv"].open(newline="", encoding="utf-8") as stream:
            fieldnames = csv.DictReader(stream).fieldnames or []
    except (OSError, UnicodeError, csv.Error) as exc:
        raise PressureVehicleError(f"corrupt runs.csv: {exc}") from exc
    selected_producer = producer or _infer_producer(fieldnames)
    if selected_producer not in _PRODUCERS:
        raise PressureVehicleError(f"unsupported Gate-3 producer: {selected_producer!r}")
    required_columns = (
        _PARKED_RESUME_COLUMNS if selected_producer == "parked"
        else _producer_columns(selected_producer)
    )
    allowed_columns = set(required_columns)
    unknown_columns = sorted(set(fieldnames) - allowed_columns)
    if unknown_columns:
        raise PressureVehicleError(f"runs.csv has unsupported {selected_producer} columns: {unknown_columns}")
    runs = _csv_rows(
        paths["runs.csv"],
        required_columns,
        label="runs.csv",
        producer=selected_producer,
        nullable=_PARKED_NULLABLE_COLUMNS if selected_producer == "parked" else set(),
    )
    if selected_producer == "parked":
        if any(row.get("turn_kind") != "resume" for row in runs):
            raise PressureVehicleError("parked runs.csv may contain resume rows only")
    _validate_row_semantics(runs, label="runs.csv", producer=selected_producer)
    try:
        join: list[dict[str, Any]] = []
        line_number = 0
        for line_number, line in enumerate(paths["join.log"].read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if selected_producer == "parked" and value.get("turn_kind") == _PARKED_BUILD_KIND:
                build_required = tuple(
                    column for column in _PARKED_RUN_COLUMNS if column not in {"round"}
                )
                row = _validate_json_row(
                    value,
                    build_required,
                    label="join.log build",
                    row_number=line_number,
                    producer="parked",
                    turn_kinds={"build"},
                )
                if value.get("kind") != "build":
                    raise PressureVehicleError(f"join.log build line {line_number} missing kind=build")
                if "round" in value:
                    raise PressureVehicleError(f"join.log build line {line_number} must not contain round")
                unknown_build_fields = sorted(set(row) - (set(build_required) | {"kind"}))
                if unknown_build_fields:
                    raise PressureVehicleError(f"join.log build line {line_number} has unsupported fields: {unknown_build_fields}")
                build_rows.append(row)
                continue
            row = _validate_json_row(
                value,
                required_columns,
                label="join.log",
                row_number=line_number,
                producer=selected_producer,
                nullable=_PARKED_NULLABLE_COLUMNS if selected_producer == "parked" else set(),
            )
            unknown_join_fields = sorted(set(row) - allowed_columns)
            if unknown_join_fields:
                raise PressureVehicleError(f"join.log line {line_number} has unsupported fields: {unknown_join_fields}")
            if selected_producer == "capacity" and set(row) != set(fieldnames):
                raise PressureVehicleError(f"join.log line {line_number} fields do not exactly match runs.csv")
            join.append(row)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, PressureVehicleError):
            raise
        raise PressureVehicleError(f"corrupt join.log line {line_number}: {paths['join.log']}: {exc}") from exc
    if not join:
        raise PressureVehicleError(f"join.log has no data rows: {paths['join.log']}")
    if selected_producer == "parked" and not build_rows:
        raise PressureVehicleError("parked join.log has no build evidence")
    if len(join) != len(runs):
        raise PressureVehicleError("runs.csv and join.log row counts contradict")
    key_columns = ("agent_id", "turn") if selected_producer == "capacity" else ("session", "turn")
    if len({tuple(row[column] for column in key_columns) for row in runs}) != len(runs):
        raise PressureVehicleError("runs.csv has duplicate authoritative row keys")
    if len({tuple(row[column] for column in key_columns) for row in join}) != len(join):
        raise PressureVehicleError("join.log has duplicate authoritative row keys")
    join_by_key = {tuple(row[column] for column in key_columns): row for row in join}
    for csv_row in runs:
        json_row = join_by_key.get(tuple(csv_row[column] for column in key_columns))
        if json_row is None:
            raise PressureVehicleError("runs.csv row is missing from join.log")
        for column in set(fieldnames).intersection(json_row):
            if csv_row[column] != json_row[column]:
                raise PressureVehicleError(f"runs.csv and join.log contradict at {column}")
    if selected_producer == "parked":
        build_keys = {(row["session"], row["turn"]) for row in build_rows}
        if any(row["turn"] != 0 for row in build_rows) or len(build_keys) != len(build_rows):
            raise PressureVehicleError("parked build evidence has invalid or duplicate keys")
        if {row["session"] for row in build_rows} != {row["session"] for row in runs}:
            raise PressureVehicleError("parked build evidence does not cover resume sessions")
        _validate_row_semantics(
            build_rows,
            label="join.log build",
            producer="parked",
            allowed_turn_kinds={_PARKED_BUILD_KIND},
        )
        for row_number, row in enumerate(runs, 2):
            _validate_parked_fields(row, label="runs.csv", row_number=row_number)
    _validate_row_semantics(join, label="join.log", producer=selected_producer)
    if selected_producer == "parked":
        for row_number, row in enumerate(join, 1):
            _validate_parked_fields(row, label="join.log", row_number=row_number)
    try:
        metrics: list[dict[str, Any]] = []
        line_number = 0
        for line_number, line in enumerate(paths["mid-run-metrics.txt"].read_text(encoding="utf-8").splitlines(), 1):
            value = json.loads(line)
            if not isinstance(value, Mapping) or "ts" not in value or "metrics" not in value:
                raise ValueError("each row requires ts and metrics")
            metric_ts = _finite_number(value["ts"], label=f"mid-run-metrics.txt ts at row {line_number}")
            if metric_ts < 0:
                raise ValueError("metrics timestamp must be non-negative")
            if not isinstance(value["metrics"], Mapping):
                raise ValueError("metrics must be an object")
            metrics.append(dict(value))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise PressureVehicleError(f"corrupt mid-run-metrics.txt line {line_number}: {exc}") from exc
    if not metrics:
        raise PressureVehicleError("mid-run-metrics.txt has no data rows")
    attribution_present = attribution_path.is_file() and not attribution_path.is_symlink()
    if attribution_path.is_symlink():
        raise PressureVehicleError("recompute_attribution.csv must not be a symlink")
    attribution = _attribution_rows(attribution_path) if attribution_present else []
    source_paths = {name: str(path) for name, path in paths.items()}
    integrity = {name: _sha256_file(path) for name, path in paths.items()}
    if attribution_present:
        source_paths["recompute_attribution.csv"] = str(attribution_path)
        integrity["recompute_attribution.csv"] = _sha256_file(attribution_path)
    return {
        "producer": selected_producer,
        "source_paths": source_paths,
        "integrity": integrity,
        "source_artifacts": {name: {"path": source_paths[name], "sha256": integrity[name]} for name in source_paths},
        "recompute_attribution_presence": {"present": attribution_present, "semantics": "validated when present; producer omission is allowed"},
        "runs": runs,
        "join": join,
        "build": build_rows,
        "mid_run_metrics": metrics,
        "recompute_attribution": attribution,
        "evidence": _gate3_evidence(runs, join, metrics, attribution, build_rows if selected_producer == "parked" else []),
    }


def _gate3_evidence(
    runs: Sequence[Mapping[str, Any]],
    join: Sequence[Mapping[str, Any]],
    metrics: Sequence[Mapping[str, Any]],
    attribution: Sequence[Mapping[str, Any]],
    build: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    row_failure = [
        index for index, row in enumerate(join)
        if row.get("http") < 200 or row.get("http") >= 300 or not row.get("finished")
        or row.get("rc") != 0 or row.get("finish_reason") in {"timeout", "error", "cancelled"}
    ]
    build_failure = [
        index for index, row in enumerate(build)
        if row.get("http") < 200 or row.get("http") >= 300 or not row.get("finished")
        or row.get("rc") != 0 or row.get("finish_reason") in {"timeout", "error", "cancelled"}
    ]
    all_failures = [f"resume:{index}" for index in row_failure] + [f"build:{index}" for index in build_failure]
    progress = bool(join) and all(row.get("ts_end", 0) >= row.get("ts_start", 0) for row in join)
    return {
        "health": not all_failures,
        "completion": not all_failures,
        "no_starvation": bool(join) and not all_failures,
        "no_zero_progress": progress,
        "no_timeout": not any(row.get("finish_reason") == "timeout" for row in join),
        "no_corruption": bool(runs) and len(runs) == len(join) and not all_failures,
        "invalid_rows": all_failures,
        "hit_restore": {
            "cached_device": sum(1 for row in join if _truthy_number(row.get("cached_device"))),
            "cached_host": sum(1 for row in join if _truthy_number(row.get("cached_host"))),
            "cached_storage": sum(1 for row in join if _truthy_number(row.get("cached_storage"))),
            "restore": sum(1 for row in attribution if "restore" in str(row.get("reason", "")).lower()),
        },
        "eviction_churn": {
            "eviction": sum(1 for row in metrics if row.get("eviction_observed") is True),
            "recompute": len(attribution),
        },
        "build": {
            "rows": len(build),
            "sessions": sorted({row.get("session") for row in build}),
            "separate_from_resume": bool(build),
        },
    }


def _truthy_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _load_run_artifacts(run_dir: Path, *, producer: str | None = None) -> dict[str, Any]:
    if not run_dir.is_dir():
        raise PressureVehicleError(f"workload run_dir is not a directory: {run_dir}")
    artifacts: dict[str, Any] = {"run_dir": str(run_dir)}
    verdict = run_dir / "verdict.json"
    if verdict.is_symlink():
        raise PressureVehicleError(f"verdict.json must not be a symlink: {verdict}")
    if verdict.exists():
        artifacts["verdict"] = _load_json(verdict, label="verdict.json")
        artifacts["verdict_source_artifact"] = {"path": str(verdict), "sha256": _sha256_file(verdict)}
    artifacts.update(_load_gate3_artifacts(run_dir, producer=producer))
    if artifacts.get("verdict_source_artifact") is not None:
        artifacts["source_artifacts"]["verdict.json"] = artifacts["verdict_source_artifact"]
    return artifacts


def _structured_output(stdout: str, *, artifact_root: Path, producer: str | None = None) -> dict[str, Any]:
    structured: list[dict[str, Any]] = []
    run_dirs: list[Path] = []
    result_files: list[Path] = []
    for line in stdout.splitlines():
        match = _RUN_DIR_RE.search(line)
        if match:
            run_dirs.append(Path(match.group(1)))
        if line.startswith("P3_PRESSURE_RESULT "):
            raw = line.removeprefix("P3_PRESSURE_RESULT ")
            try:
                payload = json.loads(raw)
            except ValueError as exc:
                raise PressureVehicleError(f"malformed P3_PRESSURE_RESULT: {exc}") from exc
            if not isinstance(payload, dict):
                raise PressureVehicleError("P3_PRESSURE_RESULT must be a JSON object")
            structured.append(_validate_result(payload, kind="stdout", identity="stdout"))
            for key in ("run_dir", "artifact_dir"):
                if isinstance(payload.get(key), str):
                    run_dirs.append(Path(payload[key]))
            if isinstance(payload.get("result_file"), str):
                result_files.append(Path(payload["result_file"]))
        elif line.startswith("P3_PRESSURE_RESULT_FILE "):
            result_files.append(Path(line.removeprefix("P3_PRESSURE_RESULT_FILE ").strip()))
    file_results: list[Any] = []
    for result_file in result_files:
        safe_file = _safe_under_root(result_file, artifact_root, label="result file")
        payload = _load_json(safe_file, label="result file")
        if not isinstance(payload, dict):
            raise PressureVehicleError("result file must contain a JSON object")
        identity = str(safe_file)
        validated = _validate_result(payload, kind="result_file", identity=identity)
        validated["_source_artifact"] = {"path": identity, "sha256": _sha256_file(safe_file)}
        file_results.append(validated)
    artifact_results: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        safe_dir = _safe_under_root(run_dir, artifact_root, label="run_dir")
        artifact_results.append(_load_run_artifacts(safe_dir, producer=producer))
    if not structured and not file_results:
        raise PressureVehicleError("missing authoritative P3_PRESSURE_RESULT")
    return {
        "structured": structured,
        "result_files": file_results,
        "artifacts": artifact_results,
    }


def _validate_result(payload: Mapping[str, Any], *, kind: str, identity: str) -> dict[str, Any]:
    missing = sorted(_RESULT_REQUIRED_FIELDS - set(payload))
    if missing:
        raise PressureVehicleError(f"P3_PRESSURE_RESULT missing required fields: {missing}")
    if payload.get("schema_version") != RESULT_SCHEMA_VERSION or payload.get("type") != RESULT_TYPE:
        raise PressureVehicleError("P3_PRESSURE_RESULT has unsupported schema or type")
    if payload.get("status") not in _RESULT_STATUSES:
        raise PressureVehicleError("P3_PRESSURE_RESULT status must be PASS or FAIL")
    source = payload.get("source")
    if not isinstance(source, Mapping) or source.get("kind") != kind or source.get("identity") != identity:
        raise PressureVehicleError("P3_PRESSURE_RESULT source identity is not bound to this vehicle input")
    health = payload.get("health")
    if isinstance(health, Mapping):
        if set(health) != {"status"} or health.get("status") not in _RESULT_STATUSES:
            raise PressureVehicleError("P3_PRESSURE_RESULT health must be boolean or exact status object")
    elif not isinstance(health, bool):
        raise PressureVehicleError("P3_PRESSURE_RESULT health must be boolean or exact status object")
    for field in _REQUIRED_EVIDENCE[1:]:
        if not isinstance(payload.get(field), bool):
            raise PressureVehicleError(f"P3_PRESSURE_RESULT {field} must be boolean")
    return dict(payload)


def _walk_values(value: Any) -> Iterable[tuple[str, Any]]:
    """Retained only for supplemental diagnostics; never used for acceptance."""
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key).lower(), child
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def _explicit_health(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        if set(value) != {"status"}:
            return None
        status = str(value.get("status", "")).upper()
        if status in {"PASS", "HEALTHY", "OK", "ALIVE"}:
            return True
        if status in {"FAIL", "UNHEALTHY", "ERROR", "DEAD"}:
            return False
    if isinstance(value, str):
        if value.upper() in {"PASS", "HEALTHY", "OK", "ALIVE"}:
            return True
        if value.upper() in {"FAIL", "UNHEALTHY", "ERROR", "DEAD"}:
            return False
    return None


def _explicit_no_bad(value: Any, *, field: str | None) -> bool | None:
    if isinstance(value, bool):
        return value if field is not None and (field.startswith("no_") or field.endswith("_free")) else not value
    return None


def _acceptance_verdict(
    *,
    workload_result: Mapping[str, Any],
    output: Mapping[str, Any],
    health: HealthGate | None,
) -> dict[str, Any]:
    if output.get("error"):
        return {"status": "FAIL", "reasons": [output["error"]], "required_evidence": {}}
    if workload_result.get("status") == "NOT_COMPUTABLE":
        return {"status": "NOT_COMPUTABLE", "reasons": [workload_result.get("reason")], "required_evidence": {}}
    if workload_result.get("status") != "PASS":
        reason = workload_result.get("reason") or {"code": "WORKLOAD_FAILED"}
        return {"status": "FAIL", "reasons": [reason], "required_evidence": {}}

    documents = list(output.get("structured", [])) + list(output.get("result_files", []))
    artifact_evidence = [artifact.get("evidence", {}) for artifact in output.get("artifacts", [])]
    evidence: dict[str, Any] = {name: {"found": False, "value": None, "sources": []} for name in _REQUIRED_EVIDENCE}
    missing: list[str] = []
    failures: list[dict[str, Any]] = []
    for name in _REQUIRED_EVIDENCE:
        values: list[tuple[bool, str]] = []
        for index, document in enumerate(documents):
            normalized = _explicit_health(document.get(name)) if name == "health" else document.get(name)
            if isinstance(normalized, bool):
                values.append((normalized, f"result[{index}]"))
        for index, artifact in enumerate(artifact_evidence):
            normalized = artifact.get(name)
            if isinstance(normalized, bool):
                values.append((normalized, f"gate3[{index}]"))
        distinct = {value for value, _ in values}
        evidence[name] = {"found": bool(values), "value": values[0][0] if len(distinct) == 1 and values else None, "sources": [source for _, source in values]}
        if not values:
            missing.append(name)
        elif len(distinct) > 1:
            failures.append({"field": name, "code": "CONTRADICTORY_EVIDENCE", "values": values})
        elif not values[0][0]:
            failures.append({"field": name, "value": False, "sources": [source for _, source in values]})
    if failures:
        return {
            "status": "FAIL",
            "reasons": [{"code": "NEGATIVE_EVIDENCE", "fields": failures}],
            "required_evidence": evidence,
        }
    if missing:
        return {
            "status": "NOT_COMPUTABLE",
            "reasons": [{"code": "MISSING_REQUIRED_EVIDENCE", "fields": missing}],
            "required_evidence": evidence,
        }
    return {"status": "PASS", "reasons": [], "required_evidence": evidence}


def _collect_hit_restore_and_churn(output: Mapping[str, Any]) -> dict[str, Any]:
    hit_fields: dict[str, Any] = {}
    churn_fields: dict[str, Any] = {}
    documents: list[Any] = list(output.get("structured", [])) + list(output.get("result_files", []))
    for artifact in output.get("artifacts", []):
        documents.append(artifact.get("evidence", {}))
        for rows_name in ("runs", "join"):
            for row in artifact.get(rows_name, []):
                documents.append(row)
    for document in documents:
        for key, value in _walk_values(document):
            if any(token in key for token in ("cached_device", "cached_host", "cached_storage", "prefill_devicehit", "prefill_hosthit", "prefill_storagehit", "restore", "hit")):
                hit_fields.setdefault(key, []).append(value)
            if any(token in key for token in ("evict", "recycle", "churn", "backup", "load_back", "starvation")):
                churn_fields.setdefault(key, []).append(value)
    return {"hit_restore": hit_fields, "eviction_churn": churn_fields}


def _safe_cleanup(owned: OwnedProcess | None) -> dict[str, Any]:
    if owned is None:
        return {"attempted": False, "status": "PASS", "gone": True, "ownership_valid": True, "errors": []}
    try:
        return cleanup_owned(owned)
    except Exception as exc:  # noqa: BLE001 - preserve cleanup truth in manifest
        return {
            "pid": owned.pid,
            "attempted": True,
            "status": "FAIL",
            "gone": False,
            "ownership_valid": False,
            "errors": [f"{type(exc).__name__}: {exc}"],
        }


def _log_identity(path: Path) -> dict[str, str] | None:
    if not path.is_file() or path.is_symlink():
        return None
    return {"path": str(path), "sha256": _sha256_file(path)}


def _run_one(
    *,
    index: int,
    command: Sequence[str],
    namespace: ArtifactNamespace,
    config: PressureVehicleConfig,
    health: HealthGate | None,
) -> dict[str, Any]:
    stdout_path = namespace.path / "logs" / f"workload-{index}.stdout.log"
    stderr_path = namespace.path / "logs" / f"workload-{index}.stderr.log"
    owned: OwnedProcess | None = None
    child_metadata: dict[str, Any] | None = None
    waited: dict[str, Any] = {"status": "FAIL", "reason": {"code": "NOT_STARTED"}}
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            owned = launch_owned(command, stdout=stdout, stderr=stderr, cwd=config.cwd)
            # Bind provenance at launch time.  Reading /proc after wait/cleanup
            # loses the child's cmdline and weakens the ownership evidence.
            child_metadata = owned.metadata()
            if not child_metadata.get("cmdline"):
                child_metadata["cmdline"] = sanitize_argv(command)
                child_metadata["cmdline_source"] = "launch_argv_fallback"
            waited = _wait_owned(owned, health=health, config=config)
    except Exception as exc:  # noqa: BLE001 - result must retain launch errors
        waited = {"status": "FAIL", "reason": {"code": "WORKLOAD_ERROR", "detail": f"{type(exc).__name__}: {exc}"}}
    cleanup = _safe_cleanup(owned)
    if cleanup.get("status") != "PASS":
        waited = {**waited, "status": "FAIL", "reason": {"code": "CLEANUP_FAILED", "detail": cleanup.get("errors", [])}}
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    output: dict[str, Any]
    try:
        output = _structured_output(stdout, artifact_root=DEFAULT_ARTIFACT_ROOT, producer=config.producer)
    except PressureVehicleError as exc:
        output = {"structured": [], "result_files": [], "artifacts": [], "error": {"code": "CORRUPT_OUTPUT", "detail": str(exc)}}
    stdout_identity = _log_identity(stdout_path)
    stderr_identity = _log_identity(stderr_path)
    if stdout_identity is not None:
        for document in output.get("structured", []):
            document["_source_artifact"] = stdout_identity
    output["hit_restore_and_churn"] = _collect_hit_restore_and_churn(output)
    authoritative = list(output.get("structured", [])) + list(output.get("result_files", []))
    if authoritative:
        declared_statuses = {item["status"] for item in authoritative}
        if len(declared_statuses) != 1:
            waited = {**waited, "status": "FAIL", "reason": {"code": "CONTRADICTORY_RESULT", "statuses": sorted(declared_statuses)}}
        elif next(iter(declared_statuses)) == "FAIL":
            waited = {**waited, "status": "FAIL", "reason": {"code": "WORKLOAD_RESULT_FAIL"}}
        elif waited.get("status") == "PASS" and waited.get("exit_code") != 0:
            waited = {**waited, "status": "FAIL", "reason": {"code": "WORKLOAD_EXIT", "exit_code": waited.get("exit_code")}}
    elif waited.get("status") == "PASS":
        waited = {**waited, "status": "NOT_COMPUTABLE", "reason": {"code": "MISSING_AUTHORITATIVE_RESULT"}}
    return {
        "index": index,
        "command": _command_identity(command),
        "exit_code": waited.get("exit_code"),
        "status": waited.get("status"),
        "reason": waited.get("reason"),
        "monitor": waited.get("monitor"),
        "output": output,
        "cleanup": cleanup,
        "child": child_metadata,
        "logs": {"stdout": stdout_identity, "stderr": stderr_identity},
    }


def run_pressure(config: PressureVehicleConfig) -> dict[str, Any]:
    """Run bounded workload command(s) and write one retained manifest."""

    lifecycle_errors: list[str] = []
    exception_state: list[dict[str, str]] = []
    namespace: ArtifactNamespace | None = None
    commands: list[list[str]] = []
    started_at = utc_now()
    provenance: dict[str, Any] = {"profile": config.profile, "workload_commands": []}
    try:
        _validate_artifact_root(config.artifact_root)
        commands = [[str(item) for item in command] for command in config.workload_commands]
        if not commands or any(not command for command in commands):
            raise PressureVehicleError("at least one non-empty workload command is required")
        for command in commands:
            sanitize_argv(command)
        namespace = ArtifactNamespace(config.artifact_root, profile=config.profile)
        namespace.create()
        provenance = collect_provenance(
            repo_root=config.repo_root,
            profile=config.profile,
            argv=commands[0],
            run_id=namespace.run_id,
            started_at=started_at,
        )
        provenance.update(
            {
                "source": _source_identity(),
                "profile_identity": _profile_identity(config.profile),
                "workload_commands": [_command_identity(command) for command in commands],
            }
        )
        namespace.write_metadata("provenance.json", provenance)
    except Exception as exc:  # noqa: BLE001 - preserve structured setup failure
        detail = f"{type(exc).__name__}: {exc}"
        lifecycle_errors.append(f"initialization: {detail}")
        exception_state.append({"phase": "initialization", "type": type(exc).__name__, "detail": str(exc)})
        if namespace is None or not (namespace.path / "metadata").is_dir():
            if isinstance(exc, PressureVehicleError):
                raise
            return {
                "schema_version": SCHEMA_VERSION,
                "status": "FAIL",
                "started_at": started_at,
                "finished_at": utc_now(),
                "provenance": provenance,
                "workload_result": {"status": "FAIL", "commands": [], "health": None},
                "acceptance_verdict": {"status": "FAIL", "reasons": [{"code": "LIFECYCLE_FAILED", "errors": lifecycle_errors}]},
                "rollback": {"status": "NOT_RUN", "attempted": False, "errors": []},
                "lifecycle_errors": lifecycle_errors,
                "exception_state": exception_state,
            }
    try:
        health = None if config.health_url is None else HealthGate(
            config.health_url, timeout=config.health_timeout, poll_interval=config.health_poll
        )
    except Exception as exc:  # noqa: BLE001 - preserve lifecycle failure for manifest
        detail = f"{type(exc).__name__}: {exc}"
        lifecycle_errors.append(f"health_initialization: {detail}")
        exception_state.append({"phase": "health_initialization", "type": type(exc).__name__, "detail": str(exc)})
        health = None
    workload_results: list[dict[str, Any]] = []
    try:
        with GpuLock():
            for index, command in enumerate(commands, 1):
                workload_results.append(
                    _run_one(
                        index=index,
                        command=command,
                        namespace=namespace,
                        config=config,
                        health=health,
                    )
                )
    except Exception as exc:  # noqa: BLE001 - preserve lock and vehicle errors
        detail = f"{type(exc).__name__}: {exc}"
        lifecycle_errors.append(f"operational_lifecycle: {detail}")
        exception_state.append({"phase": "operational_lifecycle", "type": type(exc).__name__, "detail": str(exc)})
        failed_index = len(workload_results) + 1
        failed_command = commands[failed_index - 1] if failed_index <= len(commands) else None
        failed_result: dict[str, Any] = {
            "index": failed_index,
            "status": "FAIL",
            "reason": {"code": "VEHICLE_ERROR", "detail": detail},
            "cleanup": {"status": "PASS", "attempted": False, "gone": True, "ownership_valid": True, "errors": []},
        }
        if failed_command is not None:
            failed_result["command"] = _command_identity(failed_command)
        workload_results.append(failed_result)
    if any(item.get("status") == "FAIL" or item.get("output", {}).get("error") for item in workload_results):
        workload_status = "FAIL"
    elif any(item.get("status") == "NOT_COMPUTABLE" for item in workload_results):
        workload_status = "NOT_COMPUTABLE"
    else:
        workload_status = "PASS" if workload_results else "FAIL"
    workload_result = {
        "status": workload_status,
        "commands": workload_results,
        "health": None if health is None else {"url": health.url, "observations": health.observations},
    }
    documents = [item.get("output", {}) for item in workload_results]
    acceptance_parts = []
    for item in workload_results:
        acceptance_parts.append(
            _acceptance_verdict(workload_result=item, output=item.get("output", {}), health=health)
        )
    try:
        final_health = None if health is None else health.check()
    except Exception as exc:  # noqa: BLE001 - preserve final operational state
        detail = f"{type(exc).__name__}: {exc}"
        lifecycle_errors.append(f"health_finalization: {detail}")
        exception_state.append({"phase": "health_finalization", "type": type(exc).__name__, "detail": str(exc)})
        final_health = False
    if workload_status == "FAIL":
        acceptance = {"status": "FAIL", "reasons": [{"code": "WORKLOAD_FAILED"}], "commands": acceptance_parts}
    elif workload_status == "NOT_COMPUTABLE":
        acceptance = {"status": "NOT_COMPUTABLE", "reasons": [{"code": "WORKLOAD_NOT_COMPUTABLE"}], "commands": acceptance_parts}
    elif any(item["status"] == "FAIL" for item in acceptance_parts):
        acceptance = {"status": "FAIL", "reasons": [], "commands": acceptance_parts}
    elif any(item["status"] == "NOT_COMPUTABLE" for item in acceptance_parts):
        acceptance = {"status": "NOT_COMPUTABLE", "reasons": [], "commands": acceptance_parts}
    else:
        acceptance = {"status": "PASS", "reasons": [], "commands": acceptance_parts}
    if final_health is False:
        acceptance = {
            "status": "FAIL",
            "reasons": [{"code": "HEALTH_LOSS", "detail": "health was not healthy at end"}],
            "commands": acceptance_parts,
        }
    try:
        rollback = rollback_namespace(namespace)
    except Exception as exc:  # noqa: BLE001 - final manifest reports rollback failure
        rollback = {"attempted": True, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}", "errors": [f"{type(exc).__name__}: {exc}"]}
        lifecycle_errors.append(f"rollback: {type(exc).__name__}: {exc}")
        exception_state.append({"phase": "rollback", "type": type(exc).__name__, "detail": str(exc)})
    if rollback.get("status") != "PASS":
        acceptance = {"status": "FAIL", "reasons": [{"code": "ROLLBACK_FAILED"}], "commands": acceptance_parts}
    if lifecycle_errors:
        acceptance = {"status": "FAIL", "reasons": [{"code": "LIFECYCLE_FAILED", "errors": lifecycle_errors}], "commands": acceptance_parts}
    finished_at = utc_now()
    result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": namespace.run_id,
        "status": acceptance["status"],
        "started_at": started_at,
        "finished_at": finished_at,
        "provenance": provenance,
        "thresholds": {
            "timeout": config.timeout,
            "zero_progress_timeout": config.zero_progress_timeout,
            "health_loss_threshold": config.health_loss_threshold,
            "monitor_poll": config.monitor_poll,
        },
        "workload_command": [_command_identity(command) for command in commands],
        "workload_result": workload_result,
        "acceptance_verdict": acceptance,
        "health_at_end": final_health,
        "cleanup": [item.get("cleanup", {}) for item in workload_results],
        "rollback": rollback,
        "rollback_baseline": {"artifact_namespace": str(namespace.path), "artifact_root": str(DEFAULT_ARTIFACT_ROOT)},
        "evidence": {"commands": documents},
        "source_artifacts": {
            f"workload-{item.get('index')}.stdout.log": item.get("logs", {}).get("stdout")
            for item in workload_results
            if item.get("logs", {}).get("stdout") is not None
        } | {
            f"workload-{item.get('index')}.stderr.log": item.get("logs", {}).get("stderr")
            for item in workload_results
            if item.get("logs", {}).get("stderr") is not None
        },
        "lifecycle_errors": lifecycle_errors,
        "exception_state": exception_state,
    }
    for item in workload_results:
        for artifact in item.get("output", {}).get("artifacts", []):
            for name, identity in artifact.get("source_artifacts", {}).items():
                if identity is not None:
                    result["source_artifacts"][name] = identity
        for document in item.get("output", {}).get("result_files", []):
            identity = document.get("_source_artifact")
            if identity is not None:
                result["source_artifacts"][identity["path"]] = identity
    try:
        namespace.write_metadata("manifest.json", result)
    except Exception as exc:  # noqa: BLE001 - truthful in-memory result on manifest failure
        lifecycle_errors.append(f"manifest: {type(exc).__name__}: {exc}")
        exception_state.append({"phase": "manifest", "type": type(exc).__name__, "detail": str(exc)})
        result["status"] = "FAIL"
        result["acceptance_verdict"] = {"status": "FAIL", "reasons": [{"code": "MANIFEST_WRITE_FAILED", "detail": lifecycle_errors[-1]}], "commands": acceptance_parts}
        try:
            namespace.write_metadata("manifest.json", result)
        except Exception as retry_exc:  # noqa: BLE001
            lifecycle_errors.append(f"manifest_retry: {type(retry_exc).__name__}: {retry_exc}")
    return result


def _parse_command(value: str) -> list[str]:
    command = shlex.split(value)
    if not command:
        raise argparse.ArgumentTypeError("workload command cannot be empty")
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--profile", default="p3-pressure")
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
    parser.add_argument("--producer", choices=sorted(_PRODUCERS), help="Gate-3 artifact producer schema")
    parser.add_argument(
        "--workload-command",
        action="append",
        type=_parse_command,
        required=True,
        help="repeat for sequential explicit commands; shell syntax is not used",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = PressureVehicleConfig(
        workload_commands=args.workload_command,
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
        progress_path=args.progress_file,
        producer=args.producer,
    )
    result = run_pressure(config)
    print(json.dumps(result, default=str, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
