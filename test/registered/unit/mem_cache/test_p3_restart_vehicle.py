"""CPU-only contract tests for the P3 restart vehicle."""

from __future__ import annotations

import json
import dataclasses
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from tools import p3_restart_vehicle
from tools.p3_restart_vehicle import (
    RestartVehicleConfig,
    _sigkill_owned,
    run_restart,
)


class _NoGpuLock:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _TrackingGpuLock:
    held = False

    def __enter__(self):
        type(self).held = True
        return self

    def __exit__(self, *_args):
        type(self).held = False
        return False


ARTIFACT_ROOT = Path("/mnt/data/nerun-dev/p3")


def _seed_code() -> str:
    return (
        "import json,os; from pathlib import Path; "
        "p=Path(os.environ['P3_STORAGE_PATH']); p.mkdir(parents=True,exist_ok=True); "
        "(p/'kv.bin').write_bytes(b'kv-durable'); (p/'mamba.bin').write_bytes(b'mamba-durable'); "
        "Path(os.environ['P3_ACK_PATH']).write_text(json.dumps({'status':'ACK','identity':'fixture-1'}))"
    )


def _restore_code() -> str:
    return (
        "import json,os; from pathlib import Path; "
        "Path(os.environ['P3_RESTORE_PATH']).write_text(json.dumps({'status':'RESTORED','identity':'fixture-1'}))"
    )


def _config(root: Path, storage: Path, seed: str | None = None, restore: str | None = None, **kwargs) -> RestartVehicleConfig:
    return RestartVehicleConfig(
        child_command=[sys.executable, "-c", "import time; time.sleep(30)"],
        seed_command=[sys.executable, "-c", seed or _seed_code()],
        restore_command=[sys.executable, "-c", restore or _restore_code()],
        artifact_root=root,
        storage_path=storage,
        repo_root=Path.cwd(),
        monitor_poll=0.005,
        timeout=2.0,
        zero_progress_timeout=0.05,
        **kwargs,
    )


class P3RestartVehicleTests(unittest.TestCase):
    def run_vehicle(self, config: RestartVehicleConfig):
        with patch("tools.p3_restart_vehicle.GpuLock", _NoGpuLock):
            return run_restart(config)

    def test_ack_exact_sigkill_restart_restore_identity_and_bytes(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            root = Path(temporary) / "artifacts"
            storage = Path(temporary) / "storage"
            result = self.run_vehicle(_config(root, storage))
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["reason"]["code"], "IDENTITY_BYTE_EQUIVALENT")
            self.assertEqual(result["kill"]["status"], "PASS")
            self.assertTrue(result["kill"]["sent"])
            self.assertTrue(result["kill"]["gone"])
            self.assertEqual(result["kill"]["exit_code"], -9)
            self.assertNotEqual(result["start"]["pid"], result["restart"]["pid"])
            self.assertEqual(result["seed"]["storage"], result["restore"]["storage"])
            manifest = Path(result["manifest_write"]["path"])
            self.assertEqual(json.loads(manifest.read_text())["status"], "PASS")

    def test_sigkill_refuses_ambiguous_or_unowned_pid(self):
        class FakeProcess:
            returncode = None

            def poll(self):
                return self.returncode

        class FakeOwned:
            pid = 999999
            process = FakeProcess()

            def ownership_state(self):
                return False, "proc identity mismatch"

            def identity_matches(self):
                return False

        result = _sigkill_owned(FakeOwned(), timeout=0.01)  # type: ignore[arg-type]
        self.assertEqual(result["status"], "AMBIGUOUS")
        self.assertFalse(result["sent"])

    def test_health_timeout_cleans_child_and_writes_manifest(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            root = Path(temporary) / "artifacts"
            storage = Path(temporary) / "storage"
            config = _config(root, storage, health_url="http://health.invalid", health_timeout=0, health_poll=0)
            with patch("tools.p3_restart_vehicle.HealthGate.wait", return_value=False):
                result = self.run_vehicle(config)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["reason"]["code"], "HEALTH_TIMEOUT")
            self.assertEqual(result["cleanup"]["start"]["status"], "PASS")
            self.assertTrue(Path(result["manifest_write"]["path"]).exists())

    def test_missing_ack_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            config = _config(Path(temporary) / "artifacts", Path(temporary) / "storage", seed="pass")
            result = self.run_vehicle(config)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["reason"]["code"], "ACK_FAILED")
            self.assertEqual(result["kill"], {})
            self.assertEqual(result["cleanup"]["start"]["status"], "PASS")

    def test_zero_progress_is_fail_fast_and_cleanup_is_preserved(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            progress = Path(temporary) / "progress.json"
            zero_progress = (
                "import json,os,time; from pathlib import Path; "
                "Path(os.environ['P3_STORAGE_PATH']).mkdir(parents=True,exist_ok=True); "
                "Path(os.environ['P3_PROGRESS_PATH']).write_text(json.dumps({'progress':0})); time.sleep(1)"
            )
            config = _config(
                Path(temporary) / "artifacts", Path(temporary) / "storage",
                seed=zero_progress, progress_path=progress,
            )
            result = self.run_vehicle(config)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["seed"]["reason"]["code"], "ZERO_PROGRESS")
            self.assertEqual(result["cleanup"]["start"]["status"], "PASS")
            self.assertEqual(result["manifest_write"]["status"], "PASS")

    def test_restore_identity_mismatch_is_not_product_pass(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            mismatch = "import json,os; from pathlib import Path; Path(os.environ['P3_RESTORE_PATH']).write_text(json.dumps({'status':'RESTORED','identity':'wrong'}))"
            result = self.run_vehicle(_config(Path(temporary) / "artifacts", Path(temporary) / "storage", restore=mismatch))
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["reason"]["code"], "IDENTITY_MISMATCH")

    def test_manifest_failure_is_reported(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            config = _config(Path(temporary) / "artifacts", Path(temporary) / "storage")
            with patch("tools.p3_restart_vehicle.ArtifactNamespace.write_metadata", side_effect=OSError("manifest unavailable")):
                result = self.run_vehicle(config)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["reason"]["code"], "MANIFEST_WRITE_FAILED")
            self.assertEqual(result["manifest_write"]["status"], "FAIL")

    def test_callbacks_are_not_a_supported_action_contract(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            config = _config(Path(temporary) / "artifacts", Path(temporary) / "storage")
            with self.assertRaises(TypeError):
                run_restart(config, seed_callback=lambda _context: None)  # type: ignore[call-arg]

    def test_artifact_root_rejected_before_namespace_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            outside = Path(temporary) / "repo-artifacts"
            config = _config(outside, Path(temporary) / "storage")
            with self.assertRaises(Exception) as raised:
                run_restart(config)
            self.assertIn("artifact root must be under", str(raised.exception))
            self.assertFalse(outside.exists())

    def test_all_owned_cleanup_happens_while_gpu_lock_is_held(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            observations = []
            original_cleanup = p3_restart_vehicle.cleanup_owned

            def tracked_cleanup(owned):
                observations.append(_TrackingGpuLock.held)
                return original_cleanup(owned)

            config = _config(Path(temporary) / "artifacts", Path(temporary) / "storage")
            with patch("tools.p3_restart_vehicle.GpuLock", _TrackingGpuLock), patch(
                "tools.p3_restart_vehicle.cleanup_owned", side_effect=tracked_cleanup
            ):
                result = run_restart(config)
            self.assertEqual(result["status"], "PASS")
            self.assertGreaterEqual(len(observations), 3)
            self.assertTrue(all(observations))
            self.assertFalse(_TrackingGpuLock.held)

    def test_rebuild_command_is_monitored(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            rebuild = "import time; time.sleep(1)"
            config = _config(
                Path(temporary) / "artifacts", Path(temporary) / "storage",
            )
            config = dataclasses.replace(
                config, rebuild_command=[sys.executable, "-c", rebuild], timeout=0.05
            )
            result = self.run_vehicle(config)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["rebuild"]["reason"]["code"], "TIMEOUT")

    def test_byte_mismatch_is_not_a_product_pass(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            mismatch = (
                "import json,os; from pathlib import Path; "
                "p=Path(os.environ['P3_STORAGE_PATH']); (p/'kv.bin').write_bytes(b'changed'); "
                "Path(os.environ['P3_RESTORE_PATH']).write_text(json.dumps({'status':'RESTORED','identity':'fixture-1'}))"
            )
            result = self.run_vehicle(_config(Path(temporary) / "artifacts", Path(temporary) / "storage", restore=mismatch))
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["reason"]["code"], "BYTE_MISMATCH")

    def test_child_death_after_ack_is_failure(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            child = [sys.executable, "-c", "import time; time.sleep(0.2)"]
            seed = (
                "import json,os,time; from pathlib import Path; time.sleep(0.3); "
                "p=Path(os.environ['P3_STORAGE_PATH']); p.mkdir(parents=True,exist_ok=True); "
                "(p/'kv.bin').write_bytes(b'kv-durable'); (p/'mamba.bin').write_bytes(b'mamba-durable'); "
                "Path(os.environ['P3_ACK_PATH']).write_text(json.dumps({'status':'ACK','identity':'fixture-1'}))"
            )
            config = _config(Path(temporary) / "artifacts", Path(temporary) / "storage", seed=seed)
            config = dataclasses.replace(config, child_command=child)
            result = self.run_vehicle(config)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["reason"]["code"], "CHILD_EXIT_AFTER_ACK")

    def test_health_loss_before_kill_is_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            config = _config(
                Path(temporary) / "artifacts", Path(temporary) / "storage",
                health_url="http://health.invalid", health_timeout=0, health_poll=0,
            )
            with patch("tools.p3_restart_vehicle.HealthGate.wait", return_value=True), patch(
                "tools.p3_restart_vehicle.HealthGate.check", return_value=False
            ):
                result = self.run_vehicle(config)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["reason"]["code"], "HEALTH_LOSS")

    def test_cleanup_ambiguity_is_not_reported_as_pass(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            config = dataclasses.replace(
                _config(Path(temporary) / "artifacts", Path(temporary) / "storage"),
                child_command=[sys.executable, "-c", "pass"],
            )
            ambiguous = {"status": "AMBIGUOUS", "gone": False, "ownership_valid": False, "errors": ["identity missing"]}
            with patch("tools.p3_restart_vehicle._safe_cleanup", return_value=ambiguous):
                result = self.run_vehicle(config)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["reason"]["code"], "CLEANUP_FAILED")
            self.assertEqual(result["cleanup"]["start"]["status"], "AMBIGUOUS")

    def test_rollback_failure_is_persisted_in_final_manifest(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            config = dataclasses.replace(
                _config(Path(temporary) / "artifacts", Path(temporary) / "storage"),
                child_command=[sys.executable, "-c", "pass"],
            )
            with patch("tools.p3_restart_vehicle.rollback_namespace", side_effect=RuntimeError("rollback unavailable")):
                result = self.run_vehicle(config)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["reason"]["code"], "ROLLBACK_FAILED")
            self.assertEqual(result["rollback"]["status"], "FAIL")
            manifest = Path(result["manifest_write"]["path"])
            self.assertTrue(manifest.exists())
            self.assertEqual(json.loads(manifest.read_text())["rollback"]["status"], "FAIL")

    def test_returned_rollback_failure_is_top_level_failure(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            config = dataclasses.replace(
                _config(Path(temporary) / "artifacts", Path(temporary) / "storage"),
                child_command=[sys.executable, "-c", "pass"],
            )
            for status in ("FAIL", "AMBIGUOUS"):
                with self.subTest(status=status), patch(
                    "tools.p3_restart_vehicle.rollback_namespace",
                    return_value={"attempted": True, "status": status, "error": "rollback rejected", "errors": ["rollback rejected"]},
                ):
                    result = self.run_vehicle(config)
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["reason"]["code"], "ROLLBACK_FAILED")
                self.assertEqual(result["rollback"]["status"], status)
                manifest = Path(result["manifest_write"]["path"])
                self.assertTrue(manifest.exists())
                self.assertEqual(json.loads(manifest.read_text())["status"], "FAIL")

    def test_post_namespace_initialization_failure_writes_failure_manifest(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            config = _config(Path(temporary) / "artifacts", Path(temporary) / "storage")
            for target in ("collect_provenance", "_source_identity"):
                with self.subTest(target=target), patch(
                    f"tools.p3_restart_vehicle.{target}", side_effect=RuntimeError(f"{target} unavailable")
                ):
                    result = self.run_vehicle(config)
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["reason"]["code"], "VEHICLE_ERROR")
                manifest = Path(result["manifest_write"]["path"])
                self.assertTrue(manifest.exists())
                manifest_result = json.loads(manifest.read_text())
                self.assertEqual(manifest_result["status"], "FAIL")
                self.assertIn(f"{target} unavailable", manifest_result["reason"]["detail"])

    def test_provenance_write_failure_stops_run_and_writes_failure_manifest(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            config = _config(Path(temporary) / "artifacts", Path(temporary) / "storage")
            original_write_metadata = p3_restart_vehicle.ArtifactNamespace.write_metadata

            def fail_provenance(namespace, name, payload):
                if name == "provenance.json":
                    raise OSError("provenance unavailable")
                return original_write_metadata(namespace, name, payload)

            with patch.object(
                p3_restart_vehicle.ArtifactNamespace,
                "write_metadata",
                autospec=True,
                side_effect=fail_provenance,
            ):
                result = self.run_vehicle(config)

            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["reason"], {
                "code": "PROVENANCE_WRITE_FAILED",
                "detail": "OSError: provenance unavailable",
            })
            self.assertEqual(result["provenance"]["write_error"], result["reason"])
            for phase in ("start", "seed", "kill", "restart", "rebuild", "restore"):
                self.assertNotEqual(result[phase].get("status"), "PASS")

            manifest = Path(result["manifest_write"]["path"])
            self.assertTrue(manifest.exists())
            manifest_result = json.loads(manifest.read_text())
            self.assertEqual(manifest_result["status"], "FAIL")
            self.assertEqual(manifest_result["reason"], result["reason"])
            self.assertEqual(manifest_result["provenance"]["write_error"], result["reason"])


if __name__ == "__main__":
    unittest.main()
