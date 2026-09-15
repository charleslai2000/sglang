"""Adversarial stdlib ``unittest`` coverage for the R111 fail-closed reducer.

The canonical stream is synthetic but real-shaped: every record uses the
exact product schema/event names and the exact fields the scheduler, cache and
durability producers emit.  A fully correct stream must pass all eleven
predicates; every single defect below must fail closed with ``NOT_VERIFIED``.

The R111 re-freeze makes the canonical stream real-shaped for
``generation_transition`` (authoritative counters; sampled edges corroborate)
and ``attempt_lineage`` (mandatory pre-wake failure + at most one post-wake
retry; finalize/READY join the deciding grant).

Run from this directory::

    source /mnt/data/neuron/envs/sglang-3090-opt/activate-sglang-3090.sh
    python -m unittest test_reducer -v
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest

import p0b_reducer


TASK_ID = "P0-B-ORACLE-REFREEZE-20260911-R111"
EPOCH = "2026-09-11"
TARGET_RID = "p0b-target"
TARGET_GEN = 5
TARGET_LIFECYCLE = f"{TARGET_RID}:{TARGET_GEN}"
RUNTIME = {
    "process_id": 251004,
    "run_id": "run-251004-1",
    "profile_id": "profile-abc123",
    "source_build": "4f41f5bab562b99562f30c67540eb05344d13637:deadbeef",
    "source_head": "4f41f5bab562b99562f30c67540eb05344d13637",
    "deployment_manifest_digest": "262a9362e345df15d93049301d2b0e60990ba65d80c3bbc5209fb4cdab140e2d",
}


def _fmt(value):
    if isinstance(value, (dict, list)):
        return repr(value)
    return str(value)


def _hae_record(evt, **fields):
    record = {
        "schema": "host_alloc.v1",
        "evt": evt,
        "ts_mono_ns": 1,
        "ts_wall_ms": 1,
        "worker": "pid-251004",
        "rank": 0,
        "rid": TARGET_RID,
        "attempt_id": None,
        "cache_instance_id": 7,
        "trace_context": None,
        **RUNTIME,
    }
    record.update(fields)
    return record


READY_ORDER = (
    "ts_ns",
    "evt",
    "schema",
    "rid",
    "attempt_id",
    "issue_origin",
    "completed_kv_tokens",
    "required_aux_pools",
    "completed_aux_units",
    "restore_state_before",
    "restore_state_after",
    "finalize_result",
    "ready_monotonic_ns",
    "event_id",
    "run_id",
    "process_id",
    "profile_id",
    "source_build",
    "deployment_manifest_digest",
    "lifecycle_key",
    "wait_id",
    "wake_event_id",
    "predecessor_wait_id",
    "predecessor_terminal_event_id",
    "predecessor_terminal_state",
    "cache_instance_id",
    "generation_vector_id",
)


def _render_server(specs):
    lines = []
    for kind, payload in specs:
        if kind == "hae":
            lines.append("[HAE] " + json.dumps(payload, sort_keys=True, default=str))
        elif kind == "ready":
            parts = ["[P3]"]
            for key in READY_ORDER:
                parts.append(f"{key}={_fmt(payload[key])}")
            lines.append(" ".join(parts))
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unknown spec kind {kind!r}")
    return lines


def _durable_record(evt, **fields):
    record = {
        "trace": "p0_durable",
        "evt": evt,
        "schema_version": "p0_durable.v3",
        "producer": dict(RUNTIME),
    }
    record.update(fields)
    return record


def _write_lines(path, records, as_json):
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            if as_json:
                handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
            else:
                handle.write(record + "\n")


class ReducerTestBase(unittest.TestCase):
    def setUp(self):
        self._tmpdirs = []

    def tearDown(self):
        for path in self._tmpdirs:
            shutil.rmtree(path, ignore_errors=True)

    # -- canonical fixture --------------------------------------------------
    def _canonical_specs(self):
        wait1 = _hae_record(
            "restore_host_alloc_wait",
            state="WAIT_CAPACITY",
            reason="HOST_ALLOC",
            wait_id=f"{TARGET_RID}:wait:0",
            fifo_sequence=0,
            captured_generations={"kv": 5},
            current_generations={"kv": 5},
            blocked_domains=["kv"],
            requested_primary_tokens=100,
            positive_hit_tokens=100,
            required_aux_units={},
            sidecar_hit_pages={},
            prefetch_reservation_held=False,
            lifecycle_key=TARGET_LIFECYCLE,
            retry_grant=False,
            retry_skip=False,
            retry_outcome="parked",
        )
        change1 = _hae_record(
            "host_allocability_change",
            rid=None,
            pool="kv",
            generation_before=5,
            generation_after=6,
            cause="direct_free",
            returned_units=10,
            evictable_before=0,
            evictable_after=10,
            causal_rid=TARGET_RID,
            blocked_pool_generations={"kv": 6},
            telemetry_seq=1,
            event_id="change-1",
            lifecycle_key=None,
            wait_id=None,
        )
        grant1 = _hae_record(
            "restore_host_alloc_wake_decision",
            decision="grant",
            event_id="E1",
            wake_event_id="E1",
            wait_id=f"{TARGET_RID}:wait:0",
            fifo_sequence=0,
            captured_generations={"kv": 5},
            current_generations={"kv": 6},
            blocked_domains=["kv"],
            predecessor_wait_id=None,
            predecessor_terminal_event_id=None,
            predecessor_terminal_state=None,
            predecessor_lineage_reason="no_released_predecessor",
            attempt_id=f"{TARGET_RID}:1",
            attempt_number=1,
            retry_grant=True,
            retry_skip=False,
            retry_outcome="grant",
            lifecycle_key=TARGET_LIFECYCLE,
        )
        release1 = _hae_record(
            "restore_host_alloc_wake_decision",
            decision="release",
            event_id="T1",
            terminal_event_id="T1",
            terminal_state="RELEASED",
            terminal_reason="restore_event:CAPACITY_FITS",
            wait_id=f"{TARGET_RID}:wait:0",
            fifo_sequence=0,
            attempt_id=f"{TARGET_RID}:1",
            attempt_number=1,
            retry_grant=False,
            retry_skip=True,
            retry_outcome="released",
            predecessor_lineage_reason=None,
            lifecycle_key=TARGET_LIFECYCLE,
        )
        retry = _hae_record(
            "restore_host_alloc_retry_result",
            attempt_id=f"{TARGET_RID}:1",
            wake_event_id="E1",
            retry_grant=True,
            retry_skip=False,
            retry_outcome="revoked_alloc_failed",
            terminal="revoked_alloc_failed",
            genuine_miss=False,
            crop_attempted=False,
            lower_checkpoint_queried=False,
            full_frontier_tokens=100,
            captured_generations={"kv": 6},
            current_generations={"kv": 6},
            failed_domains=["kv"],
            per_pool={},
            lifecycle_key=TARGET_LIFECYCLE,
            wait_id=f"{TARGET_RID}:wait:0",
        )
        wait2 = _hae_record(
            "restore_host_alloc_wait",
            state="WAIT_CAPACITY",
            reason="HOST_ALLOC",
            wait_id=f"{TARGET_RID}:wait:1",
            fifo_sequence=1,
            captured_generations={"kv": 6},
            current_generations={"kv": 6},
            blocked_domains=["kv"],
            requested_primary_tokens=100,
            positive_hit_tokens=100,
            required_aux_units={},
            sidecar_hit_pages={},
            prefetch_reservation_held=False,
            lifecycle_key=TARGET_LIFECYCLE,
            attempt_id=f"{TARGET_RID}:1",
            retry_grant=False,
            retry_skip=False,
            retry_outcome="parked",
        )
        change2 = _hae_record(
            "host_allocability_change",
            rid=None,
            pool="kv",
            generation_before=6,
            generation_after=7,
            cause="direct_free",
            returned_units=10,
            evictable_before=0,
            evictable_after=10,
            causal_rid=TARGET_RID,
            blocked_pool_generations={"kv": 7},
            telemetry_seq=2,
            event_id="change-2",
            lifecycle_key=None,
            wait_id=None,
        )
        grant2 = _hae_record(
            "restore_host_alloc_wake_decision",
            decision="grant",
            event_id="E2",
            wake_event_id="E2",
            wait_id=f"{TARGET_RID}:wait:1",
            fifo_sequence=1,
            captured_generations={"kv": 6},
            current_generations={"kv": 7},
            blocked_domains=["kv"],
            predecessor_wait_id=f"{TARGET_RID}:wait:0",
            predecessor_terminal_event_id="T1",
            predecessor_terminal_state="RELEASED",
            predecessor_lineage_reason=None,
            attempt_id=f"{TARGET_RID}:2",
            attempt_number=2,
            retry_grant=True,
            retry_skip=False,
            retry_outcome="grant",
            lifecycle_key=TARGET_LIFECYCLE,
        )
        finalize = _hae_record(
            "restore_hybrid_finalize",
            attempt_id=f"{TARGET_RID}:2",
            wake_event_id="E2",
            kv_expected=100,
            kv_fetched=100,
            sidecars={"mamba": {"expected": 3, "fetched": 3}},
            per_sidecar={"mamba": {"expected": 3, "fetched": 3}},
            all_or_nothing=True,
            result="accepted",
            restore_state_after="READY",
            lifecycle_key=TARGET_LIFECYCLE,
            wait_id=f"{TARGET_RID}:wait:1",
        )
        ready = {
            "ts_ns": 10,
            "evt": "ready_host",
            "schema": "rh_ready_host.v1",
            "rid": TARGET_RID,
            "attempt_id": f"{TARGET_RID}:prefetch:2",
            "issue_origin": "DEMAND_RETRY",
            "completed_kv_tokens": 100,
            "required_aux_pools": ["mamba"],
            "completed_aux_units": {"mamba": 3},
            "restore_state_before": "RESTORING",
            "restore_state_after": "READY",
            "finalize_result": "accepted",
            "ready_monotonic_ns": 11,
            "event_id": "ready-1",
            "run_id": RUNTIME["run_id"],
            "process_id": RUNTIME["process_id"],
            "profile_id": RUNTIME["profile_id"],
            "source_build": RUNTIME["source_build"],
            "deployment_manifest_digest": RUNTIME["deployment_manifest_digest"],
            "lifecycle_key": TARGET_LIFECYCLE,
            "wait_id": f"{TARGET_RID}:wait:1",
            "wake_event_id": "E2",
            "predecessor_wait_id": f"{TARGET_RID}:wait:0",
            "predecessor_terminal_event_id": "T1",
            "predecessor_terminal_state": "RELEASED",
            "cache_instance_id": 7,
            "generation_vector_id": "7:kv=7",
        }
        # Real emission always emits the initial pre-wake failure that causes
        # the park (unified_radix_cache.py:5460,6575): attempt_id=null,
        # retry_grant=false, no wake_event_id.  Only a post-wake failure would
        # emit the later retry with a non-empty host-alloc attempt id.
        retry_pre = _hae_record(
            "restore_host_alloc_retry_result",
            attempt_id=None,
            wake_event_id=None,
            retry_grant=False,
            retry_skip=False,
            retry_outcome="revoked_alloc_failed",
            terminal="revoked_alloc_failed",
            genuine_miss=False,
            crop_attempted=False,
            lower_checkpoint_queried=False,
            full_frontier_tokens=100,
            captured_generations={"kv": 5},
            current_generations={"kv": 5},
            failed_domains=["kv"],
            per_pool={},
            attempt_number=0,
            attempt_origin="HOST_ALLOC_WAIT",
            lifecycle_key=TARGET_LIFECYCLE,
            wait_id=None,
        )
        return [
            ("hae", retry_pre),
            ("hae", wait1),
            ("hae", change1),
            ("hae", grant1),
            ("hae", release1),
            ("hae", retry),
            ("hae", wait2),
            ("hae", change2),
            ("hae", grant2),
            ("hae", finalize),
            ("ready", ready),
        ]

    def _canonical_durable(self):
        return [
            _durable_record(
                "durability_barrier",
                session_id="session-1",
                session_generation=TARGET_GEN,
                build_rid=TARGET_RID,
                warm_rid=None,
                node_id="7",
                final_kv_hash="hash-abc",
                kv_durable=True,
                mamba_durable=True,
                kv_completed_tokens=100,
                kv_requested_tokens=100,
                mamba_expected_pages=3,
                mamba_succeeded_pages=3,
                mamba_key_count=3,
                result=True,
            )
        ]

    # -- bundle + reduce ----------------------------------------------------
    def _reduce_specs(self, server_specs, durable_records=None):
        if durable_records is None:
            durable_records = self._canonical_durable()
        tmpdir = tempfile.mkdtemp(prefix="p0b-r107-")
        self._tmpdirs.append(tmpdir)
        server_path = os.path.join(tmpdir, "server.log")
        durable_path = os.path.join(tmpdir, "durable.jsonl")
        source_path = os.path.join(tmpdir, "producer.py")
        _write_lines(server_path, _render_server(server_specs), as_json=False)
        _write_lines(durable_path, durable_records, as_json=True)
        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write("# frozen producer source binding for the test\n")

        def sha256(path):
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                digest.update(handle.read())
            return digest.hexdigest()

        manifest = {
            "format": "p0b.raw-bundle.v3",
            "task_id": TASK_ID,
            "epoch": EPOCH,
            "runtime": dict(RUNTIME),
            "target": {"rid": TARGET_RID, "lifecycle_key": TARGET_LIFECYCLE},
            "raw_files": {
                os.path.abspath(server_path): sha256(server_path),
                os.path.abspath(durable_path): sha256(durable_path),
            },
            "source_files": {os.path.abspath(source_path): sha256(source_path)},
        }
        manifest_path = os.path.join(tmpdir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, sort_keys=True)
        return p0b_reducer.reduce_paths(
            [os.path.abspath(server_path), os.path.abspath(durable_path)],
            os.path.abspath(manifest_path),
        )

    @staticmethod
    def _predicate(result, name):
        for item in result["predicates"]:
            if item["name"] == name:
                return item
        raise AssertionError(f"predicate {name} missing")

    def _assert_fails(self, result, expected_predicate=None):
        self.assertEqual(result["status"], "NOT_VERIFIED")
        self.assertEqual(len(result["predicates"]), 11)
        if expected_predicate is not None:
            predicate = self._predicate(result, expected_predicate)
            self.assertFalse(predicate["passed"], predicate)
            self.assertTrue(predicate["reason"], predicate)

    # -- fixture location helpers ------------------------------------------
    @staticmethod
    def _find(specs, evt, **match):
        for index, (kind, payload) in enumerate(specs):
            if kind != "hae" or payload.get("evt") != evt:
                continue
            if all(payload.get(key) == value for key, value in match.items()):
                return index
        raise AssertionError(f"no spec evt={evt} match={match}")


class OracleContractTests(ReducerTestBase):
    def test_oracle_exposes_exactly_eleven_names(self):
        names = p0b_reducer.oracle_names()
        self.assertEqual(len(names), 11)
        self.assertEqual(len(set(names)), 11)
        self.assertEqual(
            names,
            (
                "provenance",
                "singular_identity",
                "pid_profile_source_binding",
                "positive_full_hit",
                "host_alloc_park",
                "generation_transition",
                "fifo_predecessor",
                "attempt_lineage",
                "accepted_finalization",
                "ready_after_finalize",
                "negative_safety",
            ),
        )
        self.assertNotIn("raw_provenance", names)

    def test_canonical_stream_verifies_all_eleven(self):
        result = self._reduce_specs(self._canonical_specs())
        failing = [item for item in result["predicates"] if not item["passed"]]
        self.assertEqual(failing, [], failing)
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(len(result["predicates"]), 11)
        self.assertGreater(result["raw_event_count"], 0)
        self.assertTrue(all(":" in ref for ref in result["raw_references"]))
        # The sampled-edge corroboration fact is explicit in the output.
        generation = self._predicate(result, "generation_transition")
        self.assertEqual(generation["sampled_edges_seen"], {"kv": 1})
        self.assertIn("sampling", generation)


class AdversarialTests(ReducerTestBase):
    def test_missing_pid_profile_binding_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_host_alloc_retry_result")
        specs[index][1]["profile_id"] = None
        self._assert_fails(
            self._reduce_specs(specs), "pid_profile_source_binding"
        )

    def test_wrong_lifecycle_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_host_alloc_wait", fifo_sequence=0)
        specs[index][1]["lifecycle_key"] = "p0b-target:999"
        self._assert_fails(self._reduce_specs(specs), "singular_identity")

    def test_absent_park_fails_closed(self):
        specs = [
            item for item in self._canonical_specs()
            if not (
                item[0] == "hae"
                and item[1].get("evt") == "restore_host_alloc_wait"
            )
        ]
        self._assert_fails(self._reduce_specs(specs), "host_alloc_park")

    def test_non_contiguous_generation_edge_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "host_allocability_change", event_id="change-2")
        specs[index][1]["generation_before"] = 5
        self._assert_fails(self._reduce_specs(specs), "generation_transition")

    def test_generation_not_advancing_fails_closed(self):
        # Authoritative counters: current must be strictly greater than captured.
        specs = self._canonical_specs()
        index = self._find(specs, "restore_host_alloc_wake_decision", event_id="E2")
        specs[index][1]["current_generations"] = {"kv": 6}
        self._assert_fails(self._reduce_specs(specs), "generation_transition")

    def test_generation_wrong_cache_instance_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_host_alloc_wake_decision", event_id="E2")
        specs[index][1]["cache_instance_id"] = 99
        self._assert_fails(self._reduce_specs(specs), "generation_transition")

    def test_contradictory_sampled_edge_fails_closed(self):
        # A present edge for the pool in the park->grant window must be a
        # monotonic +1 step; a non-monotonic edge contradicts the counters.
        specs = self._canonical_specs()
        index = self._find(specs, "host_allocability_change", event_id="change-2")
        specs[index][1]["generation_after"] = 8
        self._assert_fails(self._reduce_specs(specs), "generation_transition")

    def test_wrong_instance_sampled_edge_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "host_allocability_change", event_id="change-2")
        specs[index][1]["cache_instance_id"] = 99
        self._assert_fails(self._reduce_specs(specs), "generation_transition")

    def test_absent_sampled_edges_still_verifies(self):
        # The producer deliberately samples host_allocability_change; absence
        # must never fail when the authoritative counters strictly advanced.
        specs = [
            item
            for item in self._canonical_specs()
            if not (
                item[0] == "hae"
                and item[1].get("evt") == "host_allocability_change"
            )
        ]
        result = self._reduce_specs(specs)
        generation = self._predicate(result, "generation_transition")
        self.assertTrue(generation["passed"], generation)
        self.assertEqual(generation["sampled_edges_seen"], {"kv": 0})
        self.assertEqual(result["status"], "VERIFIED")

    def test_fabricated_predecessor_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_host_alloc_wake_decision", event_id="E2")
        specs[index][1]["predecessor_wait_id"] = None
        specs[index][1]["predecessor_terminal_event_id"] = None
        specs[index][1]["predecessor_terminal_state"] = None
        specs[index][1]["predecessor_lineage_reason"] = "no_released_predecessor"
        self._assert_fails(self._reduce_specs(specs), "fifo_predecessor")

    def test_pre_grant_predecessor_fails_closed(self):
        specs = self._canonical_specs()
        release = self._find(specs, "restore_host_alloc_wake_decision", event_id="T1")
        grant = self._find(specs, "restore_host_alloc_wake_decision", event_id="E2")
        item = specs.pop(release)
        specs.insert(grant, item)
        self._assert_fails(self._reduce_specs(specs), "fifo_predecessor")

    def test_broken_attempt_lineage_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(
            specs, "restore_host_alloc_retry_result", attempt_id=f"{TARGET_RID}:1"
        )
        specs[index][1]["wake_event_id"] = "E-missing"
        self._assert_fails(self._reduce_specs(specs), "attempt_lineage")

    def test_missing_pre_wake_retry_fails_closed(self):
        specs = [
            item
            for item in self._canonical_specs()
            if not (
                item[0] == "hae"
                and item[1].get("evt") == "restore_host_alloc_retry_result"
                and item[1].get("attempt_id") is None
            )
        ]
        self._assert_fails(self._reduce_specs(specs), "attempt_lineage")

    def test_finalize_broken_wake_event_id_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_hybrid_finalize")
        specs[index][1]["wake_event_id"] = "E1"
        self._assert_fails(self._reduce_specs(specs), "attempt_lineage")

    def test_ready_broken_wake_event_id_fails_closed(self):
        specs = self._canonical_specs()
        ready = specs[-1]
        ready[1]["wake_event_id"] = "E1"
        self._assert_fails(self._reduce_specs(specs), "attempt_lineage")

    def test_second_post_wake_retry_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(
            specs, "restore_host_alloc_retry_result", attempt_id=f"{TARGET_RID}:1"
        )
        duplicate = copy.deepcopy(specs[index])
        duplicate[1]["attempt_id"] = f"{TARGET_RID}:2"
        specs.insert(index + 1, duplicate)
        self._assert_fails(self._reduce_specs(specs), "attempt_lineage")

    def test_post_wake_retry_grant_does_not_precede_fails_closed(self):
        # A post-wake retry must join a captured grant that precedes it; naming
        # a later grant is a broken lineage claim.
        specs = self._canonical_specs()
        index = self._find(
            specs, "restore_host_alloc_retry_result", attempt_id=f"{TARGET_RID}:1"
        )
        specs[index][1]["wake_event_id"] = "E2"
        self._assert_fails(self._reduce_specs(specs), "attempt_lineage")

    def test_post_wake_retry_wrong_namespace_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(
            specs, "restore_host_alloc_retry_result", attempt_id=f"{TARGET_RID}:1"
        )
        specs[index][1]["attempt_id"] = "not-the-target:1"
        self._assert_fails(self._reduce_specs(specs), "attempt_lineage")

    def test_incomplete_finalization_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_hybrid_finalize")
        specs[index][1]["sidecars"] = {"mamba": {"expected": 3, "fetched": 2}}
        specs[index][1]["per_sidecar"] = {"mamba": {"expected": 3, "fetched": 2}}
        self._assert_fails(self._reduce_specs(specs), "accepted_finalization")

    def test_ready_before_finalize_fails_closed(self):
        specs = self._canonical_specs()
        ready = specs.pop()
        finalize = self._find(specs, "restore_hybrid_finalize")
        specs.insert(finalize, ready)
        self._assert_fails(self._reduce_specs(specs), "ready_after_finalize")


class NegativeSafetyTests(ReducerTestBase):
    def test_genuine_miss_violation_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_host_alloc_retry_result")
        specs[index][1]["genuine_miss"] = True
        self._assert_fails(self._reduce_specs(specs), "negative_safety")

    def test_crop_attempted_violation_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_host_alloc_retry_result")
        specs[index][1]["crop_attempted"] = True
        self._assert_fails(self._reduce_specs(specs), "negative_safety")

    def test_lower_checkpoint_violation_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_host_alloc_retry_result")
        specs[index][1]["lower_checkpoint_queried"] = True
        self._assert_fails(self._reduce_specs(specs), "negative_safety")

    def test_same_generation_self_wake_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_host_alloc_wake_decision", event_id="E2")
        specs[index][1]["current_generations"] = {"kv": 6}
        self._assert_fails(self._reduce_specs(specs), "negative_safety")

    def test_repeated_retry_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(
            specs, "restore_host_alloc_retry_result", attempt_id=f"{TARGET_RID}:1"
        )
        duplicate = copy.deepcopy(specs[index])
        duplicate[1]["attempt_id"] = f"{TARGET_RID}:2"
        specs.insert(index + 1, duplicate)
        self._assert_fails(self._reduce_specs(specs), "negative_safety")

    def test_pre_wake_retry_is_not_a_repeated_retry(self):
        # The mandatory pre-wake failure is not a "repeat".  A second
        # pre-wake-shaped record fails predicate 8 but must NOT be reported by
        # negative_safety's repeated_retry (post-wake retries only).
        specs = self._canonical_specs()
        index = self._find(specs, "restore_host_alloc_retry_result", attempt_id=None)
        duplicate = copy.deepcopy(specs[index])
        specs.insert(index + 1, duplicate)
        result = self._reduce_specs(specs)
        self.assertFalse(self._predicate(result, "attempt_lineage")["passed"])
        self.assertTrue(
            self._predicate(result, "negative_safety")["passed"],
            self._predicate(result, "negative_safety"),
        )

    def test_skipped_eligible_predecessor_fails_closed(self):
        specs = self._canonical_specs()
        # Shift the target FIFO forward and insert a released waiter whose
        # sequence strictly precedes grant E1 while E1 still claims none.
        for event_id, sequence in (("E1", 1), ("T1", 1)):
            index = self._find(
                specs, "restore_host_alloc_wake_decision", event_id=event_id
            )
            specs[index][1]["fifo_sequence"] = sequence
        for wait_id, sequence in (
            (f"{TARGET_RID}:wait:0", 1),
            (f"{TARGET_RID}:wait:1", 2),
        ):
            index = self._find(
                specs, "restore_host_alloc_wait", wait_id=wait_id
            )
            specs[index][1]["fifo_sequence"] = sequence
        grant2 = self._find(specs, "restore_host_alloc_wake_decision", event_id="E2")
        specs[grant2][1]["fifo_sequence"] = 2
        holder_release = _hae_record(
            "restore_host_alloc_wake_decision",
            rid="p0b-holder",
            decision="release",
            event_id="T0",
            terminal_event_id="T0",
            terminal_state="TIMEOUT",
            terminal_reason="restore_event:TIMEOUT",
            wait_id="p0b-holder:wait:0",
            fifo_sequence=0,
            blocked_domains=["kv"],
            attempt_id="p0b-holder:1",
            attempt_number=1,
            retry_grant=False,
            retry_skip=True,
            retry_outcome="released",
            predecessor_lineage_reason=None,
            lifecycle_key="p0b-holder:4",
        )
        specs.insert(0, ("hae", holder_release))
        self._assert_fails(self._reduce_specs(specs), "negative_safety")

    def test_partial_sidecar_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_hybrid_finalize")
        specs[index][1]["sidecars"] = {"mamba": {"expected": 3, "fetched": 2}}
        self._assert_fails(self._reduce_specs(specs), "negative_safety")

    def test_discarded_hybrid_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_hybrid_finalize")
        specs[index][1]["result"] = "discarded"
        specs[index][1]["restore_state_after"] = "NONE"
        self._assert_fails(self._reduce_specs(specs), "negative_safety")

    def test_recompute_fallback_fails_closed(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_host_alloc_retry_result")
        specs[index][1]["terminal"] = "recompute"
        self._assert_fails(self._reduce_specs(specs), "negative_safety")

    def test_ready_before_finalization_fails_closed(self):
        specs = self._canonical_specs()
        ready = specs.pop()
        finalize = self._find(specs, "restore_hybrid_finalize")
        specs.insert(finalize, ready)
        self._assert_fails(self._reduce_specs(specs), "negative_safety")


class RawProvenanceGateTests(ReducerTestBase):
    def test_event_summary_verdict_field_rejected(self):
        specs = self._canonical_specs()
        index = self._find(specs, "restore_hybrid_finalize")
        specs[index][1]["oracle"] = {"accepted_finalization": True}
        result = self._reduce_specs(specs)
        self.assertEqual(result["status"], "NOT_VERIFIED")
        self.assertTrue(any("summary field" in reason for reason in result["reasons"]))

    def test_manifest_verdict_field_rejected(self):
        specs = self._canonical_specs()
        durable = self._canonical_durable()
        tmpdir = tempfile.mkdtemp(prefix="p0b-r107-manifest-")
        self._tmpdirs.append(tmpdir)
        server_path = os.path.join(tmpdir, "server.log")
        durable_path = os.path.join(tmpdir, "durable.jsonl")
        source_path = os.path.join(tmpdir, "producer.py")
        _write_lines(server_path, _render_server(specs), as_json=False)
        _write_lines(durable_path, durable, as_json=True)
        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write("source\n")

        def sha256(path):
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                digest.update(handle.read())
            return digest.hexdigest()

        manifest = {
            "format": "p0b.raw-bundle.v3",
            "task_id": TASK_ID,
            "epoch": EPOCH,
            "verdict": "VERIFIED",
            "runtime": dict(RUNTIME),
            "target": {"rid": TARGET_RID, "lifecycle_key": TARGET_LIFECYCLE},
            "raw_files": {
                os.path.abspath(server_path): sha256(server_path),
                os.path.abspath(durable_path): sha256(durable_path),
            },
            "source_files": {os.path.abspath(source_path): sha256(source_path)},
        }
        manifest_path = os.path.join(tmpdir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, sort_keys=True)
        result = p0b_reducer.reduce_paths(
            [os.path.abspath(server_path), os.path.abspath(durable_path)],
            os.path.abspath(manifest_path),
        )
        self.assertEqual(result["status"], "NOT_VERIFIED")
        self.assertTrue(
            any("verdict" in reason for reason in result["reasons"]),
            result["reasons"],
        )

    def test_tampered_raw_bundle_hash_fails_closed(self):
        specs = self._canonical_specs()
        durable = self._canonical_durable()
        # Recreate the bundle, then corrupt the server log after hashing.
        tmpdir = tempfile.mkdtemp(prefix="p0b-r107-tamper-")
        self._tmpdirs.append(tmpdir)
        server_path = os.path.join(tmpdir, "server.log")
        durable_path = os.path.join(tmpdir, "durable.jsonl")
        source_path = os.path.join(tmpdir, "producer.py")
        _write_lines(server_path, _render_server(specs), as_json=False)
        _write_lines(durable_path, durable, as_json=True)
        with open(source_path, "w", encoding="utf-8") as handle:
            handle.write("source\n")

        def sha256(path):
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                digest.update(handle.read())
            return digest.hexdigest()

        manifest = {
            "format": "p0b.raw-bundle.v3",
            "task_id": TASK_ID,
            "epoch": EPOCH,
            "runtime": dict(RUNTIME),
            "target": {"rid": TARGET_RID, "lifecycle_key": TARGET_LIFECYCLE},
            "raw_files": {
                os.path.abspath(server_path): sha256(server_path),
                os.path.abspath(durable_path): sha256(durable_path),
            },
            "source_files": {os.path.abspath(source_path): sha256(source_path)},
        }
        manifest_path = os.path.join(tmpdir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        with open(server_path, "a", encoding="utf-8") as handle:
            handle.write("[HAE] {\"schema\": \"host_alloc.v1\", \"evt\": \"restore_host_alloc_wait\"}\n")
        result = p0b_reducer.reduce_paths(
            [os.path.abspath(server_path), os.path.abspath(durable_path)],
            os.path.abspath(manifest_path),
        )
        self.assertEqual(result["status"], "NOT_VERIFIED")
        self.assertTrue(any("hash mismatch" in reason for reason in result["reasons"]))


if __name__ == "__main__":
    unittest.main()
