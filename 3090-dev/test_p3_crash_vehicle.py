"""CPU-only tests for the P3 crash/corruption/liveness vehicle."""

from __future__ import annotations

import json
from pathlib import Path
import signal
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import p3_crash_vehicle
from p3_crash_vehicle import CrashVehicleConfig, run_case
from p3_restart_vehicle import RestartVehicleConfig


ARTIFACT_ROOT = Path("/mnt/data/nerun-dev/p3")


def _backend_config(storage: Path) -> str:
    return "import os; os.makedirs(os.environ['P3_STORAGE_PATH'], exist_ok=True); os._exit(0)"


def _recovery_config(*, classification: str = "EXPLICIT_ORACLE", baseline_exit: int = 0) -> str:
    return (
        "import json,os; from pathlib import Path; "
        "p=Path(os.environ['P3_STORAGE_PATH']); e=Path(os.environ['P3_EVIDENCE_PATH']); "
        "case=os.environ['P3_CASE']; phase=os.environ['P3_PHASE']; "
        f"classification={classification!r}; "
        "exec(\"seg=next(p.glob('hicache.meta*.wal.0'))\\nsize=int(os.environ.get('P3_BASELINE_SEGMENT_SIZE',seg.stat().st_size))\\nseg.write_bytes(seg.read_bytes()[:size]) if phase!='baseline' else None\\ne.write_text(json.dumps({'status':'BASELINE_RECOVERED' if phase=='baseline' else 'RECOVERED','evidence_class':classification,'repaired_tail':phase!='baseline','post_segment_size':seg.stat().st_size,'resurrected_incomplete':False,'visibility':'NOT_RESURRECTED'}))\" if case=='torn-tail' else \"e.write_text(json.dumps({'status':'BASELINE_RECOVERED' if phase=='baseline' else 'RECOVERY_ERROR','evidence_class':classification,'recovery_error':None if phase=='baseline' else 'structured test recovery failure','failure_class':None if phase=='baseline' else ('wal-corruption' if case=='committed-corruption' else 'wal-replay-state'),'visibility':'NOT_RESURRECTED','cold_start':False,'salvaged':False}))\"); os._exit(" + str(baseline_exit) + " if phase=='baseline' else 0)"
    )


def _crc32c(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


def _frame(frame_type: int, seq: int, payload: bytes) -> bytes:
    header = struct.pack("<I H B B H I Q I", 0x484D3146, 1, frame_type, 0, 0, len(payload), seq, 0)
    crc = _crc32c(header[:22] + payload)
    return header[:22] + struct.pack("<I", crc) + payload


def _fixture(storage: Path) -> None:
    storage.mkdir()
    epoch = b"p3-committed-epoch"[:16]
    def set_payload(batch_id: int, key: bytes) -> bytes:
        return epoch + struct.pack("<QQII", 1, batch_id, 0, 1) + struct.pack("<H", len(key)) + key + struct.pack("<IIIQB", 0, 0, 4, 0, 0)
    header_base = struct.pack("<IHHQQ", 0x484D3153, 1, 0, 0, 0)
    segment = (
        header_base + struct.pack("<I", _crc32c(header_base))
        + _frame(1, 1, set_payload(1, b"key1"))
        + _frame(2, 2, struct.pack("<QI", 1, 1))
        + _frame(1, 3, set_payload(2, b"key2"))
        + _frame(2, 4, struct.pack("<QI", 2, 1))
        + _frame(3, 5, struct.pack("<16sQI", epoch, 1, 2))
    )
    (storage / "hicache.meta_p3.wal.current").write_text("0\n")
    (storage / "hicache.meta_p3.wal.0").write_bytes(segment)


def _fixture_with_uncommitted_interior_set(storage: Path) -> None:
    storage.mkdir()
    epoch = b"p3-committed-epoch"[:16]

    def set_payload(batch_id: int, key: bytes, member_count: int = 1) -> bytes:
        return epoch + struct.pack("<QQII", 1, batch_id, 0, member_count) + struct.pack("<H", len(key)) + key + struct.pack("<IIIQB", 0, 0, 4, 0, 0)

    header_base = struct.pack("<IHHQQ", 0x484D3153, 1, 0, 0, 0)
    segment = (
        header_base + struct.pack("<I", _crc32c(header_base))
        + _frame(1, 1, set_payload(99, b"uncommitted", member_count=2))
        + _frame(1, 2, set_payload(1, b"key1"))
        + _frame(2, 3, struct.pack("<QI", 1, 1))
        + _frame(1, 4, set_payload(2, b"key2"))
        + _frame(2, 5, struct.pack("<QI", 2, 1))
        + _frame(3, 6, struct.pack("<16sQI", epoch, 1, 2))
    )
    (storage / "hicache.meta_p3.wal.current").write_text("0\n")
    (storage / "hicache.meta_p3.wal.0").write_bytes(segment)


def _liveness_code(*, complete: bool) -> str:
    if complete:
        return (
            "import json,os,time; from pathlib import Path; "
            "p=Path(os.environ['P3_PROGRESS_PATH']); r=Path(os.environ['P3_RESPONSE_PATH']); "
            "p.write_text(json.dumps({'progress':1,'healthy':True})); time.sleep(.03); "
            "r.write_text(json.dumps({'request_id':os.environ['P3_RUN_ID'],'status':'COMPLETE'})); time.sleep(1)"
        )
    return (
        "import json,time; from pathlib import Path; "
        "Path(__import__('os').environ['P3_PROGRESS_PATH']).write_text(json.dumps({'progress':1,'healthy':True})); time.sleep(2)"
    )


def _restart_config(root: Path, storage: Path) -> RestartVehicleConfig:
    seed = (
        "import json,os; from pathlib import Path; p=Path(os.environ['P3_STORAGE_PATH']); "
        "p.mkdir(parents=True,exist_ok=True); (p/'bytes').write_bytes(b'identity-bytes'); "
        "Path(os.environ['P3_ACK_PATH']).write_text(json.dumps({'status':'ACK','identity':'p3'}))"
    )
    restore = "import json,os; from pathlib import Path; Path(os.environ['P3_RESTORE_PATH']).write_text(json.dumps({'status':'RESTORED','identity':'p3'}))"
    return RestartVehicleConfig(
        child_command=[sys.executable, "-c", "import time; time.sleep(30)"],
        seed_command=[sys.executable, "-c", seed],
        restore_command=[sys.executable, "-c", restore],
        artifact_root=root,
        storage_path=storage,
        repo_root=Path.cwd(),
        monitor_poll=0.005,
        timeout=2,
    )


class P3CrashVehicleTests(unittest.TestCase):
    def run_vehicle(self, config: CrashVehicleConfig) -> dict:
        with patch("p3_crash_vehicle.GpuLock", _NoGpuLock):
            return run_case(config)

    def make_fixture(self, temporary: str) -> Path:
        source = Path(temporary) / "source"
        _fixture(source)
        return source

    def config(self, temporary: str, case: str, source: Path) -> CrashVehicleConfig:
        return CrashVehicleConfig(
            case=case,
            storage_path=source,
            backend_command=[sys.executable, "-c", _recovery_config()],
            artifact_root=Path(temporary) / "artifacts",
            repo_root=Path.cwd(),
            timeout=10,
        )

    def test_torn_tail_repairs_and_does_not_resurrect_incomplete_record(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            source = self.make_fixture(temporary)
            result = self.run_vehicle(self.config(temporary, "torn-tail", source))
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["reason"]["code"], "REAL_BACKEND_UNAVAILABLE")
            self.assertEqual(result["fixture_outcome"]["status"], "PASS")
            self.assertEqual(result["evidence_classification"], "EXPLICIT_ORACLE")
            self.assertEqual(result["mutation"]["modified_segment_size"], result["mutation"]["baseline_segment_size"] + 12)
            self.assertEqual(result["visibility"]["resurrection"], "NOT_RESURRECTED")

    def test_committed_crc_corruption_is_fail_closed_with_structured_error(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            result = self.run_vehicle(self.config(temporary, "committed-corruption", self.make_fixture(temporary)))
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["reason"]["code"], "REAL_BACKEND_UNAVAILABLE")
            self.assertEqual(result["fixture_outcome"]["status"], "PASS")
            self.assertTrue(result["recovery_error"])
            self.assertEqual(result["failure_class"], "wal-corruption")
            self.assertFalse(result["evidence"].get("cold_start"))
            self.assertFalse(result["evidence"].get("salvaged"))

    def test_committed_crc_corruption_selects_only_proven_committed_set(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            source = Path(temporary) / "source"
            _fixture_with_uncommitted_interior_set(source)
            result = self.run_vehicle(self.config(temporary, "committed-corruption", source))
            self.assertEqual(result["fixture_outcome"]["status"], "PASS")
            selected_frame_offset = result["mutation"]["offset"] - 22
            committed_offsets = {
                item["offset"]
                for item in result["mutation"]["fixture_baseline"]["committed_set_identities"]
            }
            self.assertIn(selected_frame_offset, committed_offsets)
            self.assertNotEqual(selected_frame_offset, 28)

    def test_baseline_nonzero_exit_refuses_mutation_even_with_plausible_evidence(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            source = self.make_fixture(temporary)
            config = self.config(temporary, "torn-tail", source)
            config = CrashVehicleConfig(
                **{
                    **config.__dict__,
                    "backend_command": [
                        sys.executable,
                        "-c",
                        _recovery_config(baseline_exit=7),
                    ],
                }
            )
            result = self.run_vehicle(config)
            self.assertIn(result["status"], {"BLOCKED", "NOT_COMPUTABLE"})
            self.assertEqual(result["reason"]["code"], "BASELINE_COMMAND_FAILED")
            self.assertEqual(result["mutation"], None)
            self.assertEqual(result["baseline_command"]["exit_code"], 7)

    def test_spoofed_real_backend_is_downgraded_to_explicit_oracle(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            source = self.make_fixture(temporary)
            config = self.config(temporary, "torn-tail", source)
            config = CrashVehicleConfig(
                **{
                    **config.__dict__,
                    "backend_command": [
                        sys.executable,
                        "-c",
                        _recovery_config(classification="REAL_BACKEND"),
                    ],
                }
            )
            result = self.run_vehicle(config)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["evidence_classification"], "EXPLICIT_ORACLE")
            self.assertEqual(result["reason"]["code"], "REAL_BACKEND_UNAVAILABLE")
            self.assertEqual(result["product_acceptance"]["status"], "BLOCKED")

    def test_alternate_repo_root_cannot_bind_same_named_authoritative_adapter(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            source = self.make_fixture(temporary)
            alternate_root = Path(temporary) / "alternate-repo"
            alternate_adapter = alternate_root / "3090-dev" / p3_crash_vehicle._AUTHORITATIVE_BACKEND_ADAPTER
            alternate_adapter.parent.mkdir(parents=True)
            alternate_adapter.write_text(
                _recovery_config(classification="REAL_BACKEND"), encoding="utf-8"
            )
            config = self.config(temporary, "torn-tail", source)
            config = CrashVehicleConfig(
                **{
                    **config.__dict__,
                    "repo_root": alternate_root,
                    "backend_command": [sys.executable, str(alternate_adapter)],
                }
            )

            result = self.run_vehicle(config)

            self.assertFalse(
                p3_crash_vehicle._is_bound_authoritative_backend(
                    config.backend_command, config.repo_root
                )
            )
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["evidence_classification"], "EXPLICIT_ORACLE")
            self.assertFalse(result["backend_capability"]["available"])
            self.assertNotEqual(result["status"], "PASS")
            self.assertEqual(result["product_acceptance"]["status"], "BLOCKED")

    def test_missing_or_invalid_baseline_classification_refuses_mutation(self):
        for classification, expected_code in (("MISSING", "BASELINE_EVIDENCE_CLASS_REQUIRED"), ("bogus", "BASELINE_EVIDENCE_CLASS_REQUIRED")):
            with self.subTest(classification=classification), tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
                source = self.make_fixture(temporary)
                config = self.config(temporary, "torn-tail", source)
                config = CrashVehicleConfig(
                    **{
                        **config.__dict__,
                        "backend_command": [
                            sys.executable,
                            "-c",
                            _recovery_config(classification=classification),
                        ],
                    }
                )
                result = self.run_vehicle(config)
                self.assertEqual(result["status"], "NOT_COMPUTABLE")
                self.assertEqual(result["reason"]["code"], expected_code)
                self.assertIsNone(result["mutation"])

    def test_stale_generation_is_invisible_and_structured(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            result = self.run_vehicle(self.config(temporary, "stale-generation", self.make_fixture(temporary)))
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["reason"]["code"], "REAL_BACKEND_UNAVAILABLE")
            self.assertEqual(result["fixture_outcome"]["status"], "PASS")
            self.assertEqual(result["visibility"]["resurrection"], "NOT_RESURRECTED")
            self.assertEqual(result["failure_class"], "wal-replay-state")

    def test_synthetic_oracle_is_not_product_pass(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            result = self.run_vehicle(self.config(temporary, "torn-tail", self.make_fixture(temporary)))
            self.assertNotEqual(result["status"], "PASS")
            self.assertEqual(result["product_acceptance"]["status"], "BLOCKED")

    def test_invalid_noncommitted_fixture_is_refused(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            source = Path(temporary) / "invalid"
            _fixture(source)
            segment = next(source.glob("hicache.meta*.wal.0"))
            segment.write_bytes(segment.read_bytes()[: segment.stat().st_size - 34])
            result = self.run_vehicle(self.config(temporary, "committed-corruption", source))
            self.assertEqual(result["status"], "NOT_COMPUTABLE")
            self.assertEqual(result["reason"]["code"], "MUTATION_REFUSED")

    def test_storage_escape_is_refused(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            source = self.make_fixture(temporary)
            config = self.config(temporary, "torn-tail", source)
            escaped = Path(temporary) / "storage-link"
            escaped.symlink_to(source, target_is_directory=True)
            result = self.run_vehicle(CrashVehicleConfig(**{**config.__dict__, "storage_path": escaped}))
            self.assertEqual(result["status"], "NOT_COMPUTABLE")
            self.assertEqual(result["reason"]["code"], "MUTATION_REFUSED")

    def test_manifest_is_truthful_and_persisted(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            result = self.run_vehicle(self.config(temporary, "torn-tail", self.make_fixture(temporary)))
            manifest = Path(result["manifest_write"]["path"])
            persisted = json.loads(manifest.read_text())
            self.assertEqual(persisted["status"], result["status"])
            self.assertEqual(persisted["manifest_write"]["status"], "PASS")

    def test_malformed_mutation_is_refused_without_backend_invocation(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            source = Path(temporary) / "malformed"
            source.mkdir()
            result = self.run_vehicle(self.config(temporary, "torn-tail", source))
            self.assertIn(result["status"], {"BLOCKED", "NOT_COMPUTABLE"})
            self.assertEqual(result["reason"]["code"], "MUTATION_REFUSED")
            self.assertIsNone(result["command"])

    def test_no_liveness_loss_completes_within_bound(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            result = self.run_vehicle(CrashVehicleConfig(
                case="no-liveness-loss", liveness_command=[sys.executable, "-c", _liveness_code(complete=True)],
                artifact_root=Path(temporary) / "artifacts", repo_root=Path.cwd(), timeout=1, poll_interval=.005,
                zero_progress_timeout=.2,
            ))
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["reason"]["code"], "REQUEST_COMPLETED")

    def test_no_liveness_timeout_is_not_pass(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            result = self.run_vehicle(CrashVehicleConfig(
                case="no-liveness-loss", liveness_command=[sys.executable, "-c", _liveness_code(complete=False)],
                artifact_root=Path(temporary) / "artifacts", repo_root=Path.cwd(), timeout=.08, poll_interval=.005,
                zero_progress_timeout=1,
            ))
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["reason"]["code"], "TIMEOUT")
            self.assertNotEqual(result["status"], "PASS")

    def test_process_crash_reuses_restart_vehicle_sigkill_and_equivalence(self):
        with tempfile.TemporaryDirectory(dir=ARTIFACT_ROOT) as temporary:
            root = Path(temporary) / "artifacts"
            storage = Path(temporary) / "storage"
            with patch("p3_restart_vehicle.GpuLock", _NoGpuLock):
                result = run_case(CrashVehicleConfig(
                    case="process-crash", restart_config=_restart_config(root, storage),
                    artifact_root=root, repo_root=Path.cwd(),
                ))
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["kill"]["exit_code"], -signal.SIGKILL)
            self.assertTrue(result["visibility"]["identity_byte_equivalence"])


class _NoGpuLock:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


if __name__ == "__main__":
    unittest.main()
