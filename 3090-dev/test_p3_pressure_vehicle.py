"""CPU-only tests for the P3 pressure/eviction wrapper."""

from __future__ import annotations

import json
import csv
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import p3_harness
import p3_pressure_vehicle
from p3_pressure_vehicle import (
    RESULT_SCHEMA_VERSION,
    RESULT_TYPE,
    PressureVehicleConfig,
    PressureVehicleError,
    _load_gate3_artifacts,
    run_pressure,
)


ARTIFACT_ROOT = Path("/mnt/data/nerun-dev/p3")


class _NoGpuLock:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _ExitFailGpuLock(_NoGpuLock):
    def __exit__(self, *_args):
        raise RuntimeError("release boom")


def _command(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _structured_code(payload: dict[str, object], *, run_dir: Path | None = None) -> str:
    line = json.dumps(payload, separators=(",", ":"))
    suffix = ""
    if run_dir is not None:
        suffix = (
            f"from pathlib import Path; p=Path({str(run_dir)!r}); p.mkdir(parents=True,exist_ok=True); "
            "(p/'verdict.json').write_text('{}')"
        )
    return f"print('P3_PRESSURE_RESULT ' + {line!r}); {suffix}"


def _good_payload() -> dict[str, object]:
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "type": RESULT_TYPE,
        "status": "PASS",
        "source": {"kind": "stdout", "identity": "stdout"},
        "health": {"status": "PASS"},
        "no_starvation": True,
        "no_zero_progress": True,
        "no_timeout": True,
        "no_corruption": True,
    }


def _config(root: Path, command: list[str], **kwargs: object) -> PressureVehicleConfig:
    values: dict[str, object] = {
        "workload_commands": [command],
        "artifact_root": root,
        "repo_root": Path.cwd(),
        "monitor_poll": 0.005,
        "timeout": 1.0,
        "zero_progress_timeout": 0.05,
        "health_loss_threshold": 2,
        "zero_progress_timeout": None,
    }
    values.update(kwargs)
    return PressureVehicleConfig(**values)


def _artifact_row(*, parked: bool = False, http: int = 200, finished: bool = True, finish_reason: str = "stop") -> dict[str, object]:
    columns = __import__("p3_pressure_vehicle")._PARKED_RUN_COLUMNS if parked else __import__("p3_pressure_vehicle")._CAPACITY_RUN_COLUMNS
    row: dict[str, object] = {column: 0 for column in columns}
    row.update({"turn_kind": "resume" if parked else "cold", "rid": "r1", "rc": 0, "http": http, "finished": finished, "finish_reason": finish_reason, "output_field": "text", "output_sha16": "x", "ts_start": 1.0, "ts_end": 2.0, "ttft_s": 0.1, "wall_s": 1.0})
    if parked:
        row["session"] = 1
        row["age_at_wake_s"] = None
        row["cohort"] = None
    else:
        row["agent_id"] = 1
    return row


def _write_artifacts(
    run_dir: Path,
    *,
    parked: bool = False,
    attribution: list[dict[str, object]] | None = None,
    **row_overrides: object,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    row = _artifact_row(parked=parked)
    row.update(row_overrides)
    if parked:
        row.update({
            "age_at_wake_s": None,
            "turn_kind_parked": "resume",
            "hit_parent_mux": "Host-ready",
            "rh_synced": 0,
            "rh_flag": "off",
            "cohort": None,
        })
        row.update(row_overrides)
    with (run_dir / "runs.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    if parked:
        build = dict(row)
        build.update({"turn": 0, "turn_kind": "build", "kind": "build"})
        build.pop("round", None)
        for field in ("age_at_wake_s", "turn_kind_parked", "hit_parent_mux", "rh_synced", "rh_flag", "cohort"):
            build.pop(field, None)
        (run_dir / "join.log").write_text(json.dumps(build) + "\n" + json.dumps(row) + "\n")
    else:
        (run_dir / "join.log").write_text(json.dumps(row) + "\n")
    (run_dir / "mid-run-metrics.txt").write_text(json.dumps({"ts": 1.0, "metrics": {"progress": 1}}) + "\n")
    if attribution is not None:
        fields = list(p3_pressure_vehicle._ATTRIBUTION_COLUMNS)
        with (run_dir / "recompute_attribution.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(attribution)


class P3PressureVehicleTests(unittest.TestCase):
    def run_vehicle(self, config: PressureVehicleConfig):
        with patch("p3_pressure_vehicle.GpuLock", _NoGpuLock):
            return run_pressure(config)

    def test_successful_structured_result_and_manifest(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            result = self.run_vehicle(_config(ARTIFACT_ROOT, _command(
                "import json; print('P3_PRESSURE_RESULT ' + json.dumps(" + repr(_good_payload()) + "))"
            )))
            self.assertIn(result["workload_result"]["status"], {"PASS", "NOT_COMPUTABLE"})
            self.assertEqual(result["acceptance_verdict"]["status"], "PASS")
            self.assertTrue(all(item["gone"] for item in result["cleanup"]))
            self.assertTrue(all(item["ownership_valid"] for item in result["cleanup"]))
            manifest = Path(result["rollback_baseline"]["artifact_namespace"]) / "metadata" / "manifest.json"
            self.assertEqual(json.loads(manifest.read_text())["status"], "PASS")
            self.assertEqual(result["provenance"]["workload_commands"][0]["args_sha256"].__class__, str)

    def test_missing_required_fields_is_not_computable(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            payload = {"status": "PASS", "health": {"status": "PASS"}}
            result = self.run_vehicle(_config(ARTIFACT_ROOT, _command(
                "import json; print('P3_PRESSURE_RESULT ' + json.dumps(" + repr(payload) + "))"
            )))
            self.assertEqual(result["workload_result"]["status"], "FAIL")
            self.assertEqual(result["acceptance_verdict"]["status"], "FAIL")
            self.assertIn("CORRUPT_OUTPUT", str(result["acceptance_verdict"]))

    def test_nonzero_exit_is_workload_failure(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            result = self.run_vehicle(_config(ARTIFACT_ROOT, _command("raise SystemExit(7)")))
            self.assertEqual(result["workload_result"]["status"], "FAIL")
            self.assertEqual(result["acceptance_verdict"]["status"], "FAIL")
            self.assertEqual(result["workload_result"]["commands"][0]["reason"]["code"], "WORKLOAD_EXIT")

    def test_timeout_zero_progress_and_health_loss_fail_fast(self):
        cases = (
            ("import time; time.sleep(1)", "TIMEOUT"),
            ("import json,time; from pathlib import Path; Path(%r).write_text(json.dumps({'progress':0})); time.sleep(0.1); time.sleep(1)" % str(ARTIFACT_ROOT / "p3-test-progress.json"), "ZERO_PROGRESS"),
        )
        for code, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
                kwargs = {"timeout": 0.05, "zero_progress_timeout": None} if expected == "TIMEOUT" else {"timeout": 1.0, "zero_progress_timeout": 0.05, "progress_path": ARTIFACT_ROOT / "p3-test-progress.json"}
                result = self.run_vehicle(_config(ARTIFACT_ROOT, _command(code), **kwargs))
                self.assertEqual(result["workload_result"]["commands"][0]["reason"]["code"], expected)
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            config = _config(ARTIFACT_ROOT, _command("import time; time.sleep(1)"), health_url="http://health.invalid", health_timeout=0, health_poll=0)
            with patch("p3_pressure_vehicle.HealthGate.wait", return_value=True), patch(
                "p3_pressure_vehicle.HealthGate.check", return_value=False
            ):
                result = self.run_vehicle(config)
            self.assertEqual(result["workload_result"]["commands"][0]["reason"]["code"], "HEALTH_LOSS")

    def test_malformed_and_corrupt_output_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            malformed = self.run_vehicle(_config(ARTIFACT_ROOT, _command("print('P3_PRESSURE_RESULT {bad-json}')")))
            self.assertEqual(malformed["acceptance_verdict"]["status"], "FAIL")
            self.assertIn("CORRUPT_OUTPUT", str(malformed))
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            result_file = ARTIFACT_ROOT / "p3-pressure-test-corrupt-result.json"
            code = (
                "from pathlib import Path; "
                f"Path({str(result_file)!r}).write_text('{{bad-json}}'); "
                "print('P3_PRESSURE_RESULT ' + "
                f"__import__('json').dumps({{'status':'PASS','result_file':{str(result_file)!r}}}))"
            )
            corrupt = self.run_vehicle(_config(ARTIFACT_ROOT, _command(code)))
            self.assertEqual(corrupt["acceptance_verdict"]["status"], "FAIL")
            self.assertIn("CORRUPT_OUTPUT", str(corrupt))

    def test_artifact_root_refusal_happens_before_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary) / "outside"
            with self.assertRaises(PressureVehicleError):
                self.run_vehicle(_config(outside, _command("pass")))
            self.assertFalse(outside.exists())

    def test_exact_pid_cleanup_does_not_touch_same_name_sibling(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            sibling = p3_harness.launch_owned(_command("import time; time.sleep(1)"))
            try:
                result = self.run_vehicle(_config(ARTIFACT_ROOT, _command("pass")))
                self.assertEqual(result["cleanup"][0]["status"], "PASS")
                self.assertTrue(result["cleanup"][0]["gone"])
                self.assertIsNone(sibling.process.poll())
                self.assertTrue(sibling.identity_matches())
            finally:
                p3_harness.cleanup_owned(sibling)

    def test_manifest_records_thresholds_command_and_rollback(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            result = self.run_vehicle(_config(ARTIFACT_ROOT, _command(
                "import json; print('P3_PRESSURE_RESULT ' + json.dumps(" + repr(_good_payload()) + "))"
            )))
            self.assertEqual(result["thresholds"]["health_loss_threshold"], 2)
            self.assertEqual(result["rollback"]["status"], "PASS")
            self.assertEqual(result["cleanup"][0]["status"], "PASS")
            self.assertTrue(result["workload_command"][0]["argv"])

    def test_declared_fail_is_not_overridden_by_exit_zero(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT):
            payload = _good_payload() | {"status": "FAIL"}
            result = self.run_vehicle(_config(ARTIFACT_ROOT, _command(
                "import json; print('P3_PRESSURE_RESULT ' + json.dumps(" + repr(payload) + "))"
            )))
            self.assertEqual(result["workload_result"]["status"], "FAIL")
            self.assertIn("WORKLOAD_RESULT_FAIL", str(result))

    def test_verdict_only_and_unbound_result_are_refused(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            run_dir = Path(temporary) / "run"
            run_dir.mkdir()
            (run_dir / "verdict.json").write_text(json.dumps({"status": "PASS", "health": True}))
            code = f"print('run_dir={run_dir}')"
            result = self.run_vehicle(_config(ARTIFACT_ROOT, _command(code)))
            self.assertEqual(result["acceptance_verdict"]["status"], "FAIL")
            self.assertIn("MISSING_AUTHORITATIVE_RESULT", str(result))
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT):
            bad = _good_payload() | {"source": {"kind": "stdout", "identity": "other"}}
            result = self.run_vehicle(_config(ARTIFACT_ROOT, _command(
                "import json; print('P3_PRESSURE_RESULT ' + json.dumps(" + repr(bad) + "))"
            )))
            self.assertEqual(result["acceptance_verdict"]["status"], "FAIL")

    def test_conflicting_structured_documents_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            first = _good_payload()
            second = _good_payload() | {"no_starvation": False}
            code = "import json; print('P3_PRESSURE_RESULT ' + json.dumps(" + repr(first) + ")); print('P3_PRESSURE_RESULT ' + json.dumps(" + repr(second) + "))"
            result = self.run_vehicle(_config(ARTIFACT_ROOT, _command(code)))
            self.assertEqual(result["acceptance_verdict"]["status"], "FAIL")
            self.assertIn("CONTRADICTORY_EVIDENCE", str(result))

    def test_missing_or_invalid_progress_is_not_silently_disabled(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT):
            result = self.run_vehicle(_config(ARTIFACT_ROOT, _command("import time; time.sleep(1)"), zero_progress_timeout=0.1))
            self.assertEqual(result["workload_result"]["commands"][0]["reason"]["code"], "PROGRESS_UNAVAILABLE")
            path = ARTIFACT_ROOT / "p3-invalid-progress.json"
            path.write_text("{}")
            try:
                result = self.run_vehicle(_config(ARTIFACT_ROOT, _command("import time; time.sleep(1)"), zero_progress_timeout=0.1, progress_path=path))
                self.assertEqual(result["workload_result"]["commands"][0]["reason"]["code"], "PROGRESS_UNAVAILABLE")
            finally:
                path.unlink(missing_ok=True)

    def test_gate3_artifacts_are_schema_checked_and_integrity_bound(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            run_dir = Path(temporary) / "run"
            run_dir.mkdir()
            row = {column: "1" for column in __import__("p3_pressure_vehicle")._RUN_COLUMNS}
            row.update({"turn_kind": "cold", "rid": "r1", "rc": "0", "finish_reason": "stop"})
            (run_dir / "runs.csv").write_text(",".join(row) + "\n" + ",".join(row) + "\n")
            # The parser test below uses the direct helper for focused diagnostics.
            for name in ("join.log", "mid-run-metrics.txt", "recompute_attribution.csv"):
                (run_dir / name).write_text("{}\n")
            with self.assertRaises(PressureVehicleError):
                _load_gate3_artifacts(run_dir)
            self.assertTrue(run_dir.exists())

    def test_artifact_escape_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary, tempfile.TemporaryDirectory() as outside:
            escaped = Path(outside) / "run"
            escaped.mkdir()
            code = f"print('P3_PRESSURE_RESULT ' + __import__('json').dumps({repr(_good_payload() | {'run_dir': str(escaped)})}))"
            result = self.run_vehicle(_config(ARTIFACT_ROOT, _command(code)))
            self.assertEqual(result["acceptance_verdict"]["status"], "FAIL")
            self.assertIn("outside artifact namespace", str(result))

    def test_child_provenance_contains_pid_token_and_cmdline(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT):
            result = self.run_vehicle(_config(ARTIFACT_ROOT, _command(
                "import json; print('P3_PRESSURE_RESULT ' + json.dumps(" + repr(_good_payload()) + "))"
            )))
            child = result["workload_result"]["commands"][0]["child"]
            self.assertIn("pid", child)
            self.assertIn("proc_start_time", child)
            self.assertIn("cmdline", child)
            self.assertTrue(child["cmdline"])

    def test_valid_capacity_and_parked_without_recompute_attribution(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            run_dir = Path(temporary) / "capacity"
            _write_artifacts(run_dir)
            parsed = _load_gate3_artifacts(run_dir, producer="capacity")
            self.assertEqual(parsed["producer"], "capacity")
            self.assertFalse(parsed["recompute_attribution_presence"]["present"])
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            run_dir = Path(temporary) / "parked"
            _write_artifacts(run_dir, parked=True)
            parsed = _load_gate3_artifacts(run_dir, producer="parked")
            self.assertEqual(parsed["producer"], "parked")
            self.assertEqual(len(parsed["build"]), 1)
            self.assertEqual(parsed["build"][0]["turn_kind"], "build")

    def test_valid_parked_writer_shape_and_boolean_attribution(self):
        for rh_parent in ("RH-staged", "Host-ready-STAGED"):
            with self.subTest(rh_parent=rh_parent), tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
                run_dir = Path(temporary) / "parked"
                attribution = [
                    {
                        "event": "full_history_recompute", "session_id": 1, "turn": 1,
                        "ts": 3.0, "reason": "state_machine", "prior_l3": True,
                        "hit_sum": 0, "ttft_s": 1.0, "evidence_ref": "run=x",
                    },
                    {
                        "event": "full_history_recompute", "session_id": 1, "turn": 2,
                        "ts": 4.0, "reason": "state_machine", "prior_l3": False,
                        "hit_sum": 1, "ttft_s": 2.0, "evidence_ref": "run=x",
                    },
                ]
                _write_artifacts(
                    run_dir,
                    parked=True,
                    attribution=attribution,
                    hit_parent_mux=rh_parent,
                    rh_synced=1,
                    rh_flag="on",
                )
                parsed = _load_gate3_artifacts(run_dir, producer="parked")
                self.assertEqual(parsed["runs"][0]["rh_flag"], "on")
                self.assertEqual(parsed["runs"][0]["hit_parent_mux"], rh_parent)
                self.assertIs(parsed["recompute_attribution"][0]["prior_l3"], True)
                self.assertIs(parsed["recompute_attribution"][1]["prior_l3"], False)

    def test_end_to_end_plain_host_ready_rh_on_is_corrupt_output(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            run_dir = Path(temporary) / "parked-invalid"
            _write_artifacts(
                run_dir,
                parked=True,
                hit_parent_mux="Host-ready",
                rh_synced=0,
                rh_flag="on",
            )
            payload = _good_payload() | {"run_dir": str(run_dir)}
            result = self.run_vehicle(
                _config(
                    ARTIFACT_ROOT,
                    _command(
                        "import json; print('P3_PRESSURE_RESULT ' + json.dumps("
                        + repr(payload)
                        + "))"
                    ),
                    producer="parked",
                )
            )
            self.assertNotEqual(result["acceptance_verdict"]["status"], "PASS")
            self.assertEqual(result["acceptance_verdict"]["status"], "FAIL")
            self.assertIn("CORRUPT_OUTPUT", str(result))

    def test_parked_producer_domains_and_relationships_fail_closed(self):
        cases = (
            {"turn_kind_parked": "warm"},
            {"hit_parent_mux": "invalid"},
            {"cohort": "invalid"},
            {"rh_synced": -1},
            {"rh_flag": 1},
            {"hit_parent_mux": "RH-staged", "rh_flag": "off", "rh_synced": 1},
            {"hit_parent_mux": "Host-ready", "rh_flag": "on", "rh_synced": 0},
            {"hit_parent_mux": "Host-ready", "rh_flag": "on", "rh_synced": 1},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
                run_dir = Path(temporary) / "parked"
                _write_artifacts(run_dir, parked=True, **overrides)
                with self.assertRaises(PressureVehicleError):
                    _load_gate3_artifacts(run_dir, producer="parked")

    def test_keyed_capacity_rows_are_order_independent(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            run_dir = Path(temporary) / "capacity"
            _write_artifacts(run_dir)
            second = _artifact_row()
            second.update({"agent_id": 2, "rid": "r2", "turn": 1})
            with (run_dir / "runs.csv").open("a", newline="") as stream:
                csv.DictWriter(stream, fieldnames=list(second)).writerow(second)
            (run_dir / "join.log").write_text(json.dumps(second) + "\n" + (run_dir / "join.log").read_text())
            parsed = _load_gate3_artifacts(run_dir, producer="capacity")
            self.assertEqual(len(parsed["runs"]), 2)

    def test_parked_build_and_first_resume_nullable_fields_are_preserved(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            run_dir = Path(temporary) / "parked"
            _write_artifacts(run_dir, parked=True)
            parsed = _load_gate3_artifacts(run_dir, producer="parked")
            self.assertIsNone(parsed["runs"][0]["age_at_wake_s"])
            self.assertIsNone(parsed["runs"][0]["cohort"])

    def test_semantic_adversarial_rows_fail_closed(self):
        for overrides in ({"ts_start": -1.0}, {"wall_s": -1.0}, {"turn_kind": "resume"}, {"http": True}):
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
                run_dir = Path(temporary) / "bad"
                _write_artifacts(run_dir, **overrides)
                with self.assertRaises(PressureVehicleError):
                    _load_gate3_artifacts(run_dir, producer="capacity")

    def test_gpu_lock_exit_failure_is_truthful_and_does_not_escape(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT):
            with patch("p3_pressure_vehicle.GpuLock", _ExitFailGpuLock):
                result = run_pressure(_config(ARTIFACT_ROOT, _command("pass")))
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any(item["phase"] == "operational_lifecycle" for item in result["exception_state"]))
            manifest = Path(result["rollback_baseline"]["artifact_namespace"]) / "metadata" / "manifest.json"
            self.assertEqual(json.loads(manifest.read_text())["status"], "FAIL")

    def test_manifest_binds_stdout_and_stderr_logs(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT):
            result = self.run_vehicle(_config(ARTIFACT_ROOT, _command("print('ok'); import sys; print('err', file=sys.stderr)")))
            sources = result["source_artifacts"]
            self.assertEqual(set(sources), {"workload-1.stdout.log", "workload-1.stderr.log"})
            for identity in sources.values():
                self.assertTrue(Path(identity["path"]).is_file())
                self.assertEqual(len(identity["sha256"]), 64)

    def test_gate3_rejects_http_500_finished_false_and_invalid_numbers(self):
        for overrides in ({"http": 500}, {"finished": False}):
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
                run_dir = Path(temporary) / "bad"
                _write_artifacts(run_dir, **overrides)
                parsed = _load_gate3_artifacts(run_dir, producer="capacity")
                self.assertFalse(parsed["evidence"]["health"])
        for overrides in ({"ttft_s": "nan"}, {"http": True}):
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
                run_dir = Path(temporary) / "bad"
                _write_artifacts(run_dir, **overrides)
                with self.assertRaises(PressureVehicleError):
                    _load_gate3_artifacts(run_dir, producer="capacity")

    def test_gate3_rejects_cross_file_conflicts_and_ambiguous_schema(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            run_dir = Path(temporary) / "conflict"
            _write_artifacts(run_dir)
            row = _artifact_row()
            row["wall_s"] = 99.0
            (run_dir / "join.log").write_text(json.dumps(row) + "\n")
            with self.assertRaises(PressureVehicleError):
                _load_gate3_artifacts(run_dir, producer="capacity")
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            run_dir = Path(temporary) / "ambiguous"
            _write_artifacts(run_dir)
            with (run_dir / "runs.csv").open("a", newline="") as stream:
                stream.write("session\n1\n")
            with self.assertRaises(PressureVehicleError):
                _load_gate3_artifacts(run_dir)

    def test_lifecycle_failures_are_structured_and_manifest_is_truthful(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT):
            with patch("p3_pressure_vehicle.collect_provenance", side_effect=RuntimeError("provenance boom")):
                result = self.run_vehicle(_config(ARTIFACT_ROOT, _command("pass")))
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["exception_state"][0]["phase"], "initialization")
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT):
            original = p3_pressure_vehicle.ArtifactNamespace.write_metadata
            calls = {"count": 0}

            def fail_manifest(self, name, payload):
                if name == "manifest.json":
                    calls["count"] += 1
                    raise OSError("manifest boom")
                return original(self, name, payload)

            with patch.object(p3_pressure_vehicle.ArtifactNamespace, "write_metadata", fail_manifest):
                result = self.run_vehicle(_config(ARTIFACT_ROOT, _command(
                    "import json; print('P3_PRESSURE_RESULT ' + json.dumps(" + repr(_good_payload()) + "))"
                )))
            self.assertEqual(result["status"], "FAIL")
            self.assertGreaterEqual(calls["count"], 1)
            self.assertTrue(any(item["phase"] == "manifest" for item in result["exception_state"]))


if __name__ == "__main__":
    unittest.main()
