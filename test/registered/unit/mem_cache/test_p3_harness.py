"""CPU-only tests for the common P3 harness substrate."""

import json
import hashlib
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from argparse import Namespace

from tools.p3_harness import (
    AmbiguousCleanupError,
    ArtifactNamespace,
    FailFastMonitor,
    GpuLock,
    HealthGate,
    HarnessError,
    UnsafeArgvError,
    args_hash,
    cleanup_owned,
    collect_provenance,
    launch_owned,
    refuse_ambiguous_cleanup,
    sanitize_argv,
)


class P3HarnessTests(unittest.TestCase):
    def test_manifest_generation_is_atomic_and_has_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            namespace = ArtifactNamespace(Path(temporary), profile="restart-pressure")
            namespace.create()
            argv = ["python", "driver.py", "--authorization=Bearer top-secret", "Bearer custom-secret"]
            provenance = collect_provenance(
                repo_root=Path.cwd(),
                profile="restart-pressure",
                argv=argv,
                run_id=namespace.run_id,
                started_at="2026-09-13T00:00:00+00:00",
            )
            path = namespace.write_metadata("manifest.json", {"provenance": provenance})
            payload = json.loads(path.read_text())
            sanitized = ["python", "driver.py", "--authorization=<redacted>", "<redacted>"]
            self.assertEqual(payload["provenance"]["argv"], sanitized)
            self.assertEqual(payload["provenance"]["args_sha256"], args_hash(argv))
            self.assertNotIn("top-secret", path.read_text())
            self.assertNotIn("custom-secret", path.read_text())
            raw_hash = hashlib.sha256(json.dumps(argv, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
            self.assertNotEqual(payload["provenance"]["args_sha256"], raw_hash)
            self.assertTrue(path.exists())
            self.assertFalse(any(path.parent.glob("*.tmp")))

    def test_namespace_is_unique_and_rejects_nested_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = ArtifactNamespace(Path(temporary), profile="soak")
            second = ArtifactNamespace(Path(temporary), profile="soak")
            first.create()
            second.create()
            self.assertNotEqual(first.path, second.path)
            with self.assertRaises(HarnessError):
                first.write_metadata("../manifest.json", {})
            for profile in ("../escape", "/tmp/escape", "nested/profile", ""):
                with self.assertRaises(HarnessError):
                    ArtifactNamespace(Path(temporary), profile=profile)
            with self.assertRaises(HarnessError):
                ArtifactNamespace(Path(temporary), profile="safe", run_id="/tmp/escape")
            with self.assertRaises(HarnessError):
                ArtifactNamespace(Path(temporary), profile="safe", run_id="../escape")

    def test_namespace_rejects_existing_symlink_components(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            outside_path = Path(outside)
            (root / "profile-link").symlink_to(outside_path, target_is_directory=True)
            with self.assertRaises(HarnessError):
                ArtifactNamespace(root, profile="profile-link", run_id="run").create()
            self.assertFalse((outside_path / "run").exists())

            safe_profile = root / "safe"
            safe_profile.mkdir()
            (safe_profile / "run-link").symlink_to(outside_path, target_is_directory=True)
            with self.assertRaises(HarnessError):
                ArtifactNamespace(root, profile="safe", run_id="run-link").create()
            self.assertFalse((outside_path / "logs").exists())

    def test_namespace_rejects_symlinked_artifact_root_ancestor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            supplied_parent = Path(temporary) / "link"
            supplied_parent.symlink_to(Path(outside), target_is_directory=True)
            supplied_root = supplied_parent / "artifact-root"
            with self.assertRaises(HarnessError):
                ArtifactNamespace(supplied_root, profile="profile", run_id="run").create()
            self.assertFalse((Path(outside) / "artifact-root").exists())

    def test_secret_argv_policy_rejects_ambiguous_split_forms(self) -> None:
        for argv in (
            ["driver", "--header", "Bearer", "secret-one"],
            ["driver", "--header", "Authorization", "Bearer", "secret-two"],
            ["driver", "--auth", "secret-three"],
            ["driver", "--bearer", "secret-four"],
            ["driver", "--authorization", "Bearer", "secret-five"],
        ):
            with self.subTest(argv=argv):
                with self.assertRaises(UnsafeArgvError):
                    sanitize_argv(argv)
                with self.assertRaises(UnsafeArgvError):
                    args_hash(argv)

    def test_secret_argv_policy_sanitizes_inline_forms_and_hashes_only_safe_argv(self) -> None:
        forms = (
            ["driver", "--header=Bearer secret-one"],
            ["driver", "--header=Authorization Bearer secret-two"],
            ["driver", "--auth=secret-three"],
        )
        for argv in forms:
            with self.subTest(argv=argv):
                sanitized = sanitize_argv(argv)
                self.assertNotIn("secret", json.dumps(sanitized).lower())
                self.assertNotIn("secret", json.dumps(collect_provenance(
                    repo_root=Path.cwd(), profile="p3", argv=argv,
                    run_id="run", started_at="now",
                )).lower())
                changed = list(argv)
                changed[-1] = argv[-1].replace("secret-one", "different-secret").replace(
                    "secret-two", "different-secret"
                ).replace("secret-three", "different-secret")
                self.assertEqual(args_hash(argv), args_hash(changed))

    def test_pid_ownership_cleanup_and_name_refusal(self) -> None:
        owned = launch_owned([sys.executable, "-c", "import time; time.sleep(30)"])
        self.assertTrue(owned.identity_matches())
        cleanup = cleanup_owned(owned, term_timeout=0.2, kill_timeout=1.0)
        self.assertTrue(cleanup["gone"])
        self.assertTrue(cleanup["ownership_valid"])
        self.assertEqual(cleanup["status"], "PASS")
        self.assertEqual(cleanup["errors"], [])
        self.assertIsNotNone(owned.process.poll())
        with self.assertRaises(AmbiguousCleanupError):
            refuse_ambiguous_cleanup(process_name="python")

    def test_pid_cleanup_handles_child_that_ignores_term(self) -> None:
        owned = launch_owned([sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"])
        time.sleep(0.1)
        cleanup = cleanup_owned(owned, term_timeout=0.05, kill_timeout=1.0)
        self.assertTrue(cleanup["kill_sent"])
        self.assertTrue(cleanup["gone"])

    def test_cleanup_does_not_touch_same_name_sibling(self) -> None:
        command = [sys.executable, "-c", "import time; time.sleep(30)"]
        owned = launch_owned(command)
        sibling = launch_owned(command)
        try:
            cleanup = cleanup_owned(owned, term_timeout=0.05, kill_timeout=1.0)
            self.assertTrue(cleanup["gone"])
            self.assertIsNone(sibling.process.poll())
            self.assertTrue(sibling.identity_matches())
        finally:
            if sibling.process.poll() is None:
                cleanup_owned(sibling)

    def test_cleanup_refuses_missing_or_mismatched_identity(self) -> None:
        owned = launch_owned([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            with patch("tools.p3_harness._proc_start_time", return_value="different"):
                mismatch = cleanup_owned(owned)
            self.assertFalse(mismatch["gone"])
            self.assertFalse(mismatch["ownership_valid"])
            self.assertIn("proc identity mismatch", mismatch["errors"])

            with patch("tools.p3_harness._proc_start_time", return_value=None):
                missing = cleanup_owned(owned)
            self.assertFalse(missing["gone"])
            self.assertFalse(missing["ownership_valid"])
            self.assertIn("proc identity missing", missing["errors"])
        finally:
            cleanup_owned(owned)

    def test_reaped_owned_child_is_safe_gone(self) -> None:
        owned = launch_owned([sys.executable, "-c", "pass"])
        owned.process.wait(timeout=1)
        cleanup = cleanup_owned(owned)
        self.assertTrue(cleanup["gone"])
        self.assertTrue(cleanup["ownership_valid"])

    def test_fail_fast_timeout_zero_progress_and_health_loss(self) -> None:
        monitor = FailFastMonitor(timeout=5, zero_progress_timeout=2, health_loss_threshold=2, started=10, last_progress_at=10)
        self.assertEqual(monitor.observe(progress=1, healthy=True, now=10), "RUNNING")
        self.assertEqual(monitor.observe(progress=1, healthy=True, now=12), "FAIL_FAST")
        self.assertEqual(monitor.reason["code"], "ZERO_PROGRESS")

        health_monitor = FailFastMonitor(timeout=5, zero_progress_timeout=100, health_loss_threshold=2, started=10)
        self.assertEqual(health_monitor.observe(healthy=False, now=10), "RUNNING")
        self.assertEqual(health_monitor.observe(healthy=False, now=11), "FAIL_FAST")
        self.assertEqual(health_monitor.reason["code"], "HEALTH_LOSS")

        timeout_monitor = FailFastMonitor(timeout=1, zero_progress_timeout=100, health_loss_threshold=2, started=10)
        self.assertEqual(timeout_monitor.observe(healthy=True, now=11), "FAIL_FAST")
        self.assertEqual(timeout_monitor.reason["code"], "TIMEOUT")

    def test_gpu_lock_rejects_alternate_path(self) -> None:
        with self.assertRaises(HarnessError):
            GpuLock(Path("/tmp/not-the-3090-lock"))

    def test_health_gate_records_status_and_fails_closed(self) -> None:
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        gate = HealthGate("http://health.invalid", timeout=0, poll_interval=0)
        with patch("tools.p3_harness.urllib.request.urlopen", return_value=Response()):
            self.assertTrue(gate.wait())
        self.assertEqual(gate.observations[-1]["status"], 200)

        failed = HealthGate("http://health.invalid", timeout=0, poll_interval=0)
        with patch("tools.p3_harness.urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertFalse(failed.wait())
        self.assertFalse(failed.observations[-1]["healthy"])

    def test_owned_process_metadata_does_not_require_live_server(self) -> None:
        owned = launch_owned([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            metadata = owned.metadata()
            self.assertEqual(metadata["pid"], owned.pid)
            self.assertTrue(metadata["cmdline"])
        finally:
            cleanup_owned(owned)

    def test_cli_manifest_captures_cleanup_exception(self) -> None:
        from tools import p3_harness

        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = Path(temporary)
            args = Namespace(
                artifact_root=artifact_root,
                profile="cleanup-exception",
                repo_root=Path.cwd(),
                command=[sys.executable, "-c", "pass"],
                cwd=None,
                health_url=None,
                health_timeout=0,
                health_poll=0,
                timeout=1,
                zero_progress_timeout=1,
                health_loss_threshold=1,
                monitor_poll=0,
                progress_file=None,
            )
            with patch.object(p3_harness, "DEFAULT_ARTIFACT_ROOT", artifact_root), patch.object(
                p3_harness, "cleanup_owned", side_effect=RuntimeError("forced cleanup failure")
            ):
                self.assertEqual(p3_harness._run_cli(args), 1)
            manifests = list(artifact_root.glob("cleanup-exception/*/metadata/manifest.json"))
            self.assertEqual(len(manifests), 1)
            manifest = json.loads(manifests[0].read_text())
            self.assertEqual(manifest["cleanup"]["status"], "FAIL")
            self.assertIn("forced cleanup failure", manifest["cleanup"]["errors"][0])
            self.assertIn("status", manifest["rollback"])

    def test_cli_stream_close_failure_still_cleans_child_and_reports_truthfully(self) -> None:
        from tools import p3_harness

        def close_then_raise(stream):
            stream.close()
            raise RuntimeError("forced stream close failure")

        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = Path(temporary)
            args = Namespace(
                artifact_root=artifact_root,
                profile="stream-close-exception",
                repo_root=Path.cwd(),
                command=[sys.executable, "-c", "import time; time.sleep(30)"],
                cwd=None,
                health_url=None,
                health_timeout=0,
                health_poll=0,
                timeout=0,
                zero_progress_timeout=1,
                health_loss_threshold=1,
                monitor_poll=0,
                progress_file=None,
            )
            with patch.object(p3_harness, "DEFAULT_ARTIFACT_ROOT", artifact_root), patch.object(
                p3_harness, "_close_stream", side_effect=close_then_raise
            ):
                self.assertEqual(p3_harness._run_cli(args), 1)
            manifests = list(artifact_root.glob("stream-close-exception/*/metadata/manifest.json"))
            self.assertEqual(len(manifests), 1)
            manifest = json.loads(manifests[0].read_text())
            self.assertEqual(manifest["status"], "FAIL")
            self.assertEqual(manifest["cleanup"]["status"], "PASS")
            self.assertTrue(manifest["cleanup"]["attempted"])
            self.assertTrue(manifest["cleanup"]["gone"])
            self.assertTrue(manifest["cleanup"]["ownership_valid"])
            self.assertEqual(len(manifest["stream_close_errors"]), 2)
            self.assertEqual(manifest["cleanup"]["pid"], manifest["provenance"]["child"]["pid"])

    def test_cli_rejects_unsafe_argv_before_artifact_persistence(self) -> None:
        from tools import p3_harness

        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = Path(temporary)
            args = Namespace(
                artifact_root=artifact_root,
                profile="unsafe-argv",
                repo_root=Path.cwd(),
                command=["driver", "--header", "Bearer", "raw-secret"],
                cwd=None,
                health_url=None,
                health_timeout=0,
                health_poll=0,
                timeout=1,
                zero_progress_timeout=1,
                health_loss_threshold=1,
                monitor_poll=0,
                progress_file=None,
            )
            with patch.object(p3_harness, "DEFAULT_ARTIFACT_ROOT", artifact_root):
                with self.assertRaises(UnsafeArgvError):
                    p3_harness._run_cli(args)
            self.assertEqual(list(artifact_root.iterdir()), [])

    def test_cli_manifest_captures_rollback_exception(self) -> None:
        from tools import p3_harness

        with tempfile.TemporaryDirectory() as temporary:
            artifact_root = Path(temporary)
            args = Namespace(
                artifact_root=artifact_root,
                profile="rollback-exception",
                repo_root=Path.cwd(),
                command=[sys.executable, "-c", "pass"],
                cwd=None,
                health_url=None,
                health_timeout=0,
                health_poll=0,
                timeout=1,
                zero_progress_timeout=1,
                health_loss_threshold=1,
                monitor_poll=0,
                progress_file=None,
            )
            with patch.object(p3_harness, "DEFAULT_ARTIFACT_ROOT", artifact_root), patch.object(
                p3_harness, "rollback_namespace", side_effect=RuntimeError("forced rollback failure")
            ):
                self.assertEqual(p3_harness._run_cli(args), 1)
            manifests = list(artifact_root.glob("rollback-exception/*/metadata/manifest.json"))
            self.assertEqual(len(manifests), 1)
            manifest = json.loads(manifests[0].read_text())
            self.assertEqual(manifest["rollback"]["status"], "FAIL")
            self.assertIn("forced rollback failure", manifest["rollback"]["error"])


if __name__ == "__main__":
    unittest.main()
