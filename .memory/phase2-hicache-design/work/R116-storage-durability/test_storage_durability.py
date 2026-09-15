#!/usr/bin/env python3
"""Adversarial stdlib ``unittest`` suite for the R116 storage-durability reducer.

Every adversarial test builds a synthetic-but-real-shaped bundle in a temp dir,
exercises the CLI as a subprocess (``--json``), and asserts both the exit code
and the JSON verdict.  The control test runs the reducer against the real
frozen R114 bundle + frozen L3 evidence.

Run::

    python -m unittest test_storage_durability -v
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "storage_durability.py")

REAL_BUNDLE = os.path.abspath(os.path.join(HERE, "..", "R114-bundle"))
REAL_RAW = os.path.join(REAL_BUNDLE, "raw.log")
REAL_PROBE = os.path.join(REAL_BUNDLE, "probe.log")
REAL_MANIFEST = os.path.join(REAL_BUNDLE, "manifest.json")
REAL_L3 = os.path.abspath(
    os.path.join(HERE, "..", "R116-l3-evidence", "l3-evidence.json")
)

T_RID = "a" * 32
T_BUILD = "b" * 32
T_SID = "r116-c1"
T_GEN = 10
T_PREFIX = 32
LIFECYCLE = f"{T_RID}:{T_GEN}"


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hae(obj: dict) -> str:
    return "[2026-09-11 22:00:00] [HAE] " + json.dumps(obj)


def _keys(n: int = 4) -> list[str]:
    return [hashlib.sha256(f"r116-key-{i}".encode()).hexdigest() for i in range(n)]


def build_bundle(tmp: str, **overrides) -> dict:
    """Write a valid synthetic bundle, applying optional single-defect overrides.

    Overrides (all default to a passing bundle):
      l3_session_id, l3_rid, l3_build, l3_prefix, l3_generation
      restore_hits, restore_storage_hits
      build_keys, build_hits
      object_delete_index
      include_mamba_ack, mamba_durable
      l3_completed
      finalize_result, finalize_all_or_nothing
      extra_raw_lines
    """
    keys = _keys()
    key_set_sha256 = _sha256_text(json.dumps(keys))

    raw_lines = [
        _hae(
            {
                "evt": "restore_host_alloc_wait",
                "rid": T_RID,
                "lifecycle_key": LIFECYCLE,
                "state": "WAIT_CAPACITY",
                "reason": "HOST_ALLOC",
                "requested_primary_tokens": T_PREFIX,
                "positive_hit_tokens": T_PREFIX,
                "event_id": "run:host-alloc:1",
            }
        ),
        _hae(
            {
                "evt": "restore_host_alloc_wake_decision",
                "event_id": "run:host-alloc:2",
                "decision": "grant",
                "rid": T_RID,
                "lifecycle_key": LIFECYCLE,
                "requested_primary_tokens": T_PREFIX,
            }
        ),
        _hae(
            {
                "evt": "restore_hybrid_finalize",
                "rid": T_RID,
                "lifecycle_key": LIFECYCLE,
                "result": overrides.get("finalize_result", "accepted"),
                "all_or_nothing": overrides.get("finalize_all_or_nothing", True),
                "kv_expected": T_PREFIX,
                "kv_fetched": T_PREFIX,
                "sidecars": {"mamba": {"expected": 1, "fetched": 1}},
                "wake_event_id": "run:host-alloc:2",
                "trace_context": {
                    "session_id": T_SID,
                    "session_generation": T_GEN,
                    "build_rid": T_BUILD,
                },
            }
        ),
    ]
    raw_lines.extend(overrides.get("extra_raw_lines", []))
    raw_path = os.path.join(tmp, "raw.log")
    with open(raw_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(raw_lines) + "\n")

    probe_records = []
    build_keys = overrides.get("build_keys", keys)
    probe_records.append(
        {
            "evt": "pc_storage_query",
            "rid": T_BUILD,
            "keys": build_keys,
            "query_suffix_len": T_PREFIX + 42,
            "kv_hit_pages": overrides.get("build_hits", 0),
            "storage_hit_count": overrides.get("build_hits", 0),
            "sidecar_hits": {"kv": 0},
        }
    )
    probe_records.append(
        {
            "evt": "pc_storage_query",
            "rid": T_RID,
            "keys": keys,
            "query_suffix_len": T_PREFIX + 42,
            "kv_hit_pages": overrides.get("restore_hits", T_PREFIX),
            "storage_hit_count": overrides.get("restore_storage_hits", T_PREFIX),
            "sidecar_hits": {"kv": T_PREFIX, "mamba": T_PREFIX},
        }
    )
    half = T_PREFIX // 2
    for batch in (half, T_PREFIX - half):
        probe_records.append(
            {
                "evt": "pc_get_v2",
                "phase": "kv_batch",
                "rid": T_RID,
                "sidecar": "kv",
                "n_keys": batch,
                "kv_hits": batch,
            }
        )
    probe_records.append(
        {
            "evt": "pc_get_v2",
            "phase": "sidecar",
            "rid": T_RID,
            "sidecar": ["mamba"],
            "n_keys": 1,
            "hit_pages": {"mamba": 1},
        }
    )
    probe_records.append(
        {
            "evt": "pc_l3_host",
            "rid": T_RID,
            "completed_tokens": overrides.get("l3_completed", T_PREFIX),
            "requested_tokens": T_PREFIX + 42,
        }
    )
    if overrides.get("include_mamba_ack", True):
        probe_records.append(
            {
                "evt": "backup_ack_drain",
                "trace": "p0_durable",
                "session_id": T_SID,
                "session_generation": T_GEN,
                "build_rid": T_BUILD,
                "mamba_durable": overrides.get("mamba_durable", True),
            }
        )
    probe_path = os.path.join(tmp, "probe.log")
    with open(probe_path, "w", encoding="utf-8") as handle:
        for record in probe_records:
            handle.write(json.dumps(record) + "\n")

    objects_dir = os.path.join(tmp, "objects")
    os.makedirs(objects_dir, exist_ok=True)
    object_entries = []
    delete_index = overrides.get("object_delete_index")
    for index, key in enumerate(keys):
        payload = (f"r116-object-{index}-" * 8).encode("utf-8")
        object_path = os.path.join(objects_dir, f"{key}.bin")
        if index != delete_index:
            with open(object_path, "wb") as handle:
                handle.write(payload)
        object_entries.append(
            {
                "key": key,
                "src": f"/mnt/data/l3/{key}.bin",
                "frozen_copy": f"objects/{key}.bin",
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )

    l3 = {
        "format": "p0b.l3-evidence.v1",
        "target": {
            "rid": overrides.get("l3_rid", T_RID),
            "session_id": overrides.get("l3_session_id", T_SID),
            "session_generation": overrides.get("l3_generation", T_GEN),
            "build_rid": overrides.get("l3_build", T_BUILD),
            "prefix_tokens": overrides.get("l3_prefix", T_PREFIX),
        },
        "key_set_sha256": key_set_sha256,
        "key_count": len(keys),
        "objects": object_entries,
    }
    l3_path = os.path.join(tmp, "l3-evidence.json")
    with open(l3_path, "w", encoding="utf-8") as handle:
        json.dump(l3, handle, indent=2)

    manifest = {
        "format": "p0b.raw-bundle.v3",
        "task_id": "R116-synthetic",
        "epoch": "2026-09-11",
        "runtime": {
            "process_id": 1,
            "run_id": "run-1",
            "profile_id": "profile-1",
            "source_build": "deadbeef",
        },
        "target": {"rid": T_RID, "lifecycle_key": LIFECYCLE},
        "raw_files": {
            os.path.abspath(raw_path): _sha256_file(raw_path),
            os.path.abspath(probe_path): _sha256_file(probe_path),
        },
    }
    manifest_path = os.path.join(tmp, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    return {
        "raw": raw_path,
        "probe": probe_path,
        "manifest": manifest_path,
        "l3": l3_path,
    }


def run_cli(paths: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            SCRIPT,
            "--raw",
            paths["raw"],
            "--probe",
            paths["probe"],
            "--manifest",
            paths["manifest"],
            "--l3-evidence",
            paths["l3"],
            "--json",
        ],
        capture_output=True,
        text=True,
    )


def _failed_names(result: dict) -> set[str]:
    return {item["name"] for item in result["predicates"] if not item["passed"]}


class StorageDurabilityTests(unittest.TestCase):
    def test_r114_frozen_fixture_passes(self):
        completed = run_cli(
            {
                "raw": REAL_RAW,
                "probe": REAL_PROBE,
                "manifest": REAL_MANIFEST,
                "l3": REAL_L3,
            }
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        verdict = json.loads(completed.stdout)
        self.assertEqual(verdict["status"], "PASS")
        self.assertTrue(all(item["passed"] for item in verdict["predicates"]))
        self.assertEqual(verdict["target"]["prefix_tokens"], 27008)

    def test_wrong_identity_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_bundle(tmp, l3_session_id="wrong-session")
            completed = run_cli(paths)
            self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
            verdict = json.loads(completed.stdout)
            self.assertEqual(verdict["status"], "FAIL")
            self.assertIn("identity_consistency", _failed_names(verdict))

    def test_short_coverage_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_bundle(tmp, restore_hits=2048)
            completed = run_cli(paths)
            self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
            verdict = json.loads(completed.stdout)
            self.assertEqual(verdict["status"], "FAIL")
            self.assertIn("kv_prefix_coverage", _failed_names(verdict))

    def test_missing_durable_object_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_bundle(tmp, object_delete_index=2)
            completed = run_cli(paths)
            self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
            verdict = json.loads(completed.stdout)
            self.assertEqual(verdict["status"], "FAIL")
            self.assertIn("durable_object_existence", _failed_names(verdict))

    def test_keyset_mismatch_between_build_and_restore_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_bundle(tmp, build_keys=_keys(4)[::-1] + ["f" * 64])
            completed = run_cli(paths)
            self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
            verdict = json.loads(completed.stdout)
            self.assertEqual(verdict["status"], "FAIL")
            self.assertIn("durable_write_then_restore", _failed_names(verdict))

    def test_no_build_then_restore_causality_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_bundle(tmp, build_hits=16)
            completed = run_cli(paths)
            self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
            verdict = json.loads(completed.stdout)
            self.assertEqual(verdict["status"], "FAIL")
            self.assertIn("durable_write_then_restore", _failed_names(verdict))

    def test_mamba_ack_missing_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_bundle(tmp, include_mamba_ack=False)
            completed = run_cli(paths)
            self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
            verdict = json.loads(completed.stdout)
            self.assertEqual(verdict["status"], "FAIL")
            self.assertIn("mamba_sidecar_durable", _failed_names(verdict))

    def test_l3_host_incomplete_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_bundle(tmp, l3_completed=T_PREFIX - 1)
            completed = run_cli(paths)
            self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
            verdict = json.loads(completed.stdout)
            self.assertEqual(verdict["status"], "FAIL")
            self.assertIn("l3_to_host_completed", _failed_names(verdict))

    def test_recompute_or_discard_path_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            discard = (
                f"[2026-09-11 22:00:00] [P2A] ts_ms=1 evt=restore_disposition "
                f"rid={T_RID} disposition=DISCARD requested=27050 granted=27008 "
                "reason=hybrid_discard"
            )
            paths = build_bundle(tmp, extra_raw_lines=[discard])
            completed = run_cli(paths)
            self.assertEqual(completed.returncode, 1, completed.stderr + completed.stdout)
            verdict = json.loads(completed.stdout)
            self.assertEqual(verdict["status"], "FAIL")
            self.assertIn("finalize_consumed_restore", _failed_names(verdict))

    def test_invalid_input_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_bundle(tmp)
            paths = dict(paths)
            paths["probe"] = os.path.join(tmp, "does-not-exist.log")
            completed = run_cli(paths)
            self.assertEqual(completed.returncode, 2, completed.stderr + completed.stdout)
            verdict = json.loads(completed.stdout)
            self.assertEqual(verdict["status"], "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
