#!/usr/bin/env python3
"""Targeted unit tests for the harness helpers (no GPU, no sglang, no server).

Run with:  CUDA_VISIBLE_DEVICES="" <tree>/env/bin/python -m unittest -v test_gate_helpers
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gate_common as gc  # noqa: E402
import gate_a_content_integrity as ga  # noqa: E402
import gate_a_f1_cold_l1 as f1  # noqa: E402
import f2_restart_recovery as f2  # noqa: E402


class TestGateVerdicts(unittest.TestCase):
    def _gate(self, td, name="t"):
        return gc.Gate(name, td)

    def test_pass(self):
        with tempfile.TemporaryDirectory() as td:
            g = self._gate(td)
            g.check("a", True)
            g.check("b", True)
            self.assertEqual(g.finish(), ("PASS", 0))

    def test_fail(self):
        with tempfile.TemporaryDirectory() as td:
            g = self._gate(td)
            g.check("a", True)
            g.check("b", False)
            self.assertEqual(g.finish(), ("FAIL", 1))

    def test_skipped_is_invalid_never_pass(self):
        with tempfile.TemporaryDirectory() as td:
            g = self._gate(td)
            g.check("a", True)
            g.skip("b", "probe not executed")
            verdict, rc = g.finish()
            self.assertEqual(verdict, "INVALID")
            self.assertEqual(rc, 2)

    def test_missing_required_is_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            g = self._gate(td)
            g.require("never_ran")
            verdict, rc = g.finish()
            self.assertEqual(verdict, "INVALID")
            self.assertEqual(rc, 2)

    def test_invalidate_beats_fail(self):
        with tempfile.TemporaryDirectory() as td:
            g = self._gate(td)
            g.check("a", False)
            g.invalidate("storage tier not proven")
            verdict, rc = g.finish()
            self.assertEqual(verdict, "INVALID")
            self.assertEqual(rc, 2)
            self.assertIn("storage", g.report["invalid_reason"])

    def test_pending_and_error(self):
        with tempfile.TemporaryDirectory() as td:
            g = self._gate(td)
            g.pending("lock busy")
            self.assertEqual(g.finish(), ("PENDING", 3))
        with tempfile.TemporaryDirectory() as td:
            g = self._gate(td)
            g.error(ValueError("boom"), "tb")
            self.assertEqual(g.finish(), ("ERROR", 4))

    def test_optional_never_gates(self):
        with tempfile.TemporaryDirectory() as td:
            g = self._gate(td)
            g.check("a", True)
            g.record("info", {"x": 1})
            self.assertEqual(g.finish(), ("PASS", 0))


class TestLock(unittest.TestCase):
    def test_acquire_probe_release(self):
        with tempfile.TemporaryDirectory() as td:
            lock = os.path.join(td, "gpu.lock")
            fd = gc.acquire_lock("unit", max_attempts=1, poll_s=0, lock_path=lock)
            self.assertIsNotNone(fd)
            p = gc.lock_probe(lock)
            self.assertTrue(p["locked"], p)
            with open(lock) as fh:
                rec = json.loads(fh.read().strip())
            self.assertEqual(rec["owner"], "unit")
            self.assertEqual(rec["generation"], 1)
            gc.release_lock(fd)
            p2 = gc.lock_probe(lock)
            self.assertFalse(p2["locked"], p2)

    def test_generation_increments(self):
        with tempfile.TemporaryDirectory() as td:
            lock = os.path.join(td, "gpu.lock")
            fd = gc.acquire_lock("one", max_attempts=1, poll_s=0, lock_path=lock)
            gc.release_lock(fd)
            fd2 = gc.acquire_lock("two", max_attempts=1, poll_s=0, lock_path=lock)
            with open(lock) as fh:
                rec = json.loads(fh.read().strip())
            self.assertEqual(rec["generation"], 2)
            gc.release_lock(fd2)

    def test_second_acquire_times_out(self):
        with tempfile.TemporaryDirectory() as td:
            lock = os.path.join(td, "gpu.lock")
            fd = gc.acquire_lock("one", max_attempts=1, poll_s=0, lock_path=lock)
            fd2 = gc.acquire_lock("two", max_attempts=2, poll_s=0, lock_path=lock)
            self.assertIsNone(fd2)
            gc.release_lock(fd)


class TestPort(unittest.TestCase):
    def test_port_free(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            s.listen(1)
            self.assertFalse(gc.port_free(port))
        self.assertTrue(gc.port_free(port))


class TestEventParsing(unittest.TestCase):
    LINES = [
        "[P2A] ts_ms=1 evt=prefetch_revoke rid=abc terminated=False "
        "storage_hit=0 requested=23182 miss_reason=miss storage_generation=0\n",
        "[P2A] ts_ms=2 evt=restore_success rid=abc n_tokens=23165\n",
        "[P3] ts_ms=3 evt=extent_write node=None component=kv keys_n=1024 "
        "bytes=16777216\n",
        "[P3] ts_ms=4 evt=extent_write node=None component=mamba keys_n=1 "
        "bytes=51511296\n",
        "[P3] ts_ms=5 evt=extent_recycle slot=0 generation=1 freed=52559872\n",
    ]

    def test_parse(self):
        ev = gc.parse_storage_events(self.LINES)
        self.assertEqual(len(ev["prefetch_revoke"]), 1)
        self.assertEqual(len(ev["restore_success"]), 1)
        self.assertEqual(len(ev["extent_write"]), 2)
        self.assertEqual(len(ev["extent_recycle"]), 1)
        self.assertEqual(ev["prefetch_revoke"][0]["storage_hit"], "0")
        self.assertEqual(ev["prefetch_revoke"][0]["miss_reason"], "miss")

    def test_derived(self):
        ev = gc.parse_storage_events(self.LINES)
        self.assertEqual(gc.extent_write_bytes(ev), 16777216 + 51511296)
        self.assertTrue(gc.revoke_miss(ev))
        self.assertEqual(gc.max_restore_n_tokens(ev), 23165)
        self.assertEqual(gc.revoke_storage_hit(ev), 0)
        slim = gc.slim_storage_events(ev)
        self.assertEqual(slim["extent_write_n"], 2)
        self.assertEqual(slim["extent_recycle_n"], 1)

    def test_positive_hit_not_miss(self):
        ev = gc.parse_storage_events([
            "[P2A] evt=prefetch_revoke rid=x terminated=False storage_hit=1024 "
            "requested=1024 miss_reason=none storage_generation=1\n"])
        self.assertFalse(gc.revoke_miss(ev))
        self.assertEqual(gc.revoke_storage_hit(ev), 1024)

    def test_tier_of(self):
        tier = gc.tier_of({
            "cached_tokens_details": {"device": 1, "host": 2, "storage": 3,
                                      "storage_backend": "ExtentFileBackend"},
            "hicache_telemetry": {"l1_tokens": 1, "l2_tokens": 2,
                                  "l3_tokens": 3, "prefetch_origin": "DEMAND"},
            "prompt_tokens": 65000,
        })
        self.assertEqual(tier["storage"], 3)
        self.assertEqual(tier["l3_tokens"], 3)
        self.assertTrue(tier["has_cached_tokens_details"])
        self.assertTrue(tier["has_hicache_telemetry"])
        self.assertEqual(tier["prompt_tokens"], 65000)


class TestF1Geometry(unittest.TestCase):
    class A:
        extent_size = 64 << 20
        file_size = 0
        chain_tokens = 62000
        filler_tokens = 16000
        slots_margin = 8
        page_bytes = 16384
        sweep_tokens = 2048

    def test_geometry(self):
        g = f1.compute_geometry(self.A())
        self.assertEqual(g["pages_per_slot"], 4096)
        self.assertEqual(g["chain_slots"], 16)
        self.assertEqual(g["filler_slots"], 4)
        # chain + 2 filler rounds + margin
        self.assertEqual(g["num_slots"], 16 + 8 + 8)
        self.assertEqual(g["file_size"], 32 * (64 << 20))
        self.assertLessEqual(g["file_size"], 3 << 30)  # cheap, not 64 GiB
        self.assertEqual(g["sweep_bytes_per_request"], 2048 * 16384)

    def test_geometry_rejects_bad(self):
        class B(self.A):
            file_size = 4096
        with self.assertRaises(gc.GateInvalid):
            f1.compute_geometry(B())

    def test_geometry_reloc_reserve_bounded(self):
        class R(self.A):
            reloc_reserve_slots = 2
        g = f1.compute_geometry(R())
        self.assertEqual(g["reloc_reserve_slots"], 2)
        self.assertEqual(g["reloc_reserve_bytes"], 2 * 64 << 20)
        # chain + 2 filler rounds + margin + bounded reserve
        self.assertEqual(g["num_slots"], 16 + 8 + 8 + 2)
        self.assertEqual(g["file_size"], 34 * (64 << 20))
        self.assertLessEqual(g["file_size"], 3 << 30)

    def test_gate_a_geometry(self):
        class A:
            extent_size = 64 << 20
            file_size = 0
            prompt_tokens = 65000
            filler_tokens = 16000
            max_fillers = 6
            slots_margin = 4
        g = ga.compute_geometry(A())
        self.assertEqual(g["target_slots"], 16)
        self.assertEqual(g["filler_slots"], 4)
        self.assertEqual(g["num_slots"], 16 + 24 + 4)
        self.assertEqual(g["file_size"], 44 * (64 << 20))

    def test_config_suffix(self):
        self.assertEqual(f1.config_suffix("/data/models/qwen35-9b-w4a16"),
                         "_-data-models-qwen35-9b-w4a16_0_1")
        self.assertEqual(f2.config_suffix("/data/models/qwen35-9b-w4a16"),
                         "_-data-models-qwen35-9b-w4a16_0_1")

    def test_strip_phase(self):
        self.assertEqual(f2._strip_phase(
            ["--tree", "/x", "--phase", "all", "--port", "1"]),
            ["--tree", "/x", "--port", "1"])
        self.assertEqual(f2._strip_phase(["--phase=all", "--port", "1"]),
                         ["--port", "1"])


class TestNamespaceGuard(unittest.TestCase):
    def test_fresh_namespace_created(self):
        with tempfile.TemporaryDirectory() as td:
            ns = gc.resolve_namespace(td, "g", "r1")
            self.assertTrue(os.path.isdir(ns))

    def test_populated_namespace_refused(self):
        with tempfile.TemporaryDirectory() as td:
            ns = gc.resolve_namespace(td, "g", "r1")
            open(os.path.join(ns, "hicache.meta_x.manifest"), "w").close()
            with self.assertRaises(gc.GateInvalid):
                gc.resolve_namespace(td, "g", "r1")

    def test_production_store_refused(self):
        # resolve_namespace nests under <root>/<task-id>/<gate>-<rid>; using the
        # production store itself as the root must be refused.
        with self.assertRaises(gc.GateInvalid):
            gc.resolve_namespace(gc.PRODUCTION_STORE, "gateA", "0")


class TestCopyStore(unittest.TestCase):
    def test_copy_only_store_files(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "src")
            os.makedirs(src)
            for n in ("hicache.data_x", "hicache.meta_x.manifest",
                      "hicache.meta_x.wal.0", "hicache.meta_x.wal.current",
                      "hicache.meta_x.lock", "hicache.meta_x.manifest.tmp.1",
                      "unrelated.txt"):
                with open(os.path.join(src, n), "wb") as fh:
                    fh.write(b"data")
            dst = os.path.join(td, "dst")
            copied = gc.copy_store(src, dst)
            self.assertIn("hicache.meta_x.manifest", copied)
            self.assertIn("hicache.meta_x.wal.0", copied)
            # the multi-GiB sparse data file is skipped by default
            self.assertNotIn("hicache.data_x", copied)
            self.assertNotIn("hicache.meta_x.manifest.tmp.1", copied)
            self.assertNotIn("hicache.meta_x.lock", copied)
            self.assertNotIn("unrelated.txt", copied)
            with self.assertRaises(gc.GateInvalid):
                gc.copy_store(src, dst)
            dst2 = os.path.join(td, "dst2")
            copied2 = gc.copy_store(src, dst2, include_data=True)
            self.assertIn("hicache.data_x", copied2)


class TestLatestMetric(unittest.TestCase):
    def test_latest_metric(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "sglang-request-metrics-20260916_22.log")
            with open(path, "w") as fh:
                fh.write(json.dumps({"id": "a", "prompt_tokens": 10,
                                     "cached_tokens_details": None}) + "\n")
                fh.write(json.dumps({"id": "b", "prompt_tokens": 20,
                                     "cached_tokens_details": {"storage": 5}}) + "\n")
            rec = gc.latest_metric([td], prompt_tokens=20, timeout_s=1)
            self.assertEqual(rec["id"], "b")
            rec2 = gc.latest_metric([td], rid="a", timeout_s=1)
            self.assertEqual(rec2["prompt_tokens"], 10)
            self.assertIsNone(gc.latest_metric([td], prompt_tokens=999,
                                               timeout_s=0.1))


class TestNamespaceManifest(unittest.TestCase):
    def test_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            suffix = "_-m_0_1"
            with open(os.path.join(td, f"hicache.meta{suffix}.wal.current"),
                      "w") as fh:
                fh.write("3")
            open(os.path.join(td, f"hicache.meta{suffix}.wal.2"), "w").close()
            open(os.path.join(td, f"hicache.meta{suffix}.wal.3"), "w").close()
            man = gc.namespace_manifest(td, suffix)
            self.assertEqual(man["wal_current"], 3)
            self.assertEqual(man["wal_generations"], [2, 3])


class TestF1Classify(unittest.TestCase):
    class Args:
        expect = "unfixed"
        min_restore_fraction = 0.8

    @staticmethod
    def _gate(td, chain_n=1000):
        g = gc.Gate("f1", td)
        g.report["prompt"] = {"n": chain_n}
        return g

    @staticmethod
    def _reclaim(**kw):
        base = {"wrap_observed": True, "generation_changed": True,
                "relocated_count": 0, "recycle_count": 0, "refused_count": 0,
                "head_detail": {"head_current_slot": 5,
                                "moved_out_of_victim": True},
                "batch_exists": 99, "batch_exists_expected": 99,
                "batch_exists_eq_expected": True}
        base.update(kw)
        return base

    def test_unfixed_reproduction_passes(self):
        with tempfile.TemporaryDirectory() as td:
            g = self._gate(td)
            f1._classify(
                g, self.Args(), cold_hit=0, cold_miss=True, cold_restore=0,
                cold={"tier": {"storage": 0, "device": 0}},
                mem={"first_absent_index": 0, "n_present": 997},
                head={"head_present_in_rebuilt_index": False,
                      "head_refreshed_after_drop": False},
                reclaim=self._reclaim(recycle_count=1))
            self.assertEqual(g.finish()[0], "PASS")

    def test_unfixed_without_reclaim_fails(self):
        with tempfile.TemporaryDirectory() as td:
            g = self._gate(td)
            f1._classify(
                g, self.Args(), cold_hit=0, cold_miss=True, cold_restore=0,
                cold={"tier": {"storage": 0, "device": 0}},
                mem={"first_absent_index": 0, "n_present": 997},
                head={"head_present_in_rebuilt_index": False,
                      "head_refreshed_after_drop": False},
                reclaim=self._reclaim(wrap_observed=False,
                                      generation_changed=False))
            self.assertEqual(g.finish()[0], "FAIL")

    def test_fixed_full_restore_passes(self):
        with tempfile.TemporaryDirectory() as td:
            args = self.Args()
            args.expect = "fixed"
            g = self._gate(td)
            g.check("cold_ids_eq_device", True)
            f1._classify(
                g, args, cold_hit=None, cold_miss=False, cold_restore=999,
                cold={"tier": {"storage": 990, "device": 0}},
                mem={"first_absent_index": None, "n_present": 1000},
                head={"head_present_in_rebuilt_index": True,
                      "head_refreshed_after_drop": True},
                reclaim=self._reclaim(relocated_count=12))
            self.assertEqual(g.finish()[0], "PASS")

    def test_fixed_single_page_refresh_fails(self):
        # The known partial fix: page 0 refreshed but page 1 lost -> tiny run.
        with tempfile.TemporaryDirectory() as td:
            args = self.Args()
            args.expect = "fixed"
            g = self._gate(td)
            g.check("cold_ids_eq_device", True)
            f1._classify(
                g, args, cold_hit=1, cold_miss=False, cold_restore=1,
                cold={"tier": {"storage": 1, "device": 0}},
                mem={"first_absent_index": 1, "n_present": 1},
                head={"head_present_in_rebuilt_index": True,
                      "head_refreshed_after_drop": True},
                reclaim=self._reclaim(relocated_count=1))
            verdict, rc = g.finish()
            self.assertEqual(verdict, "FAIL")
            self.assertEqual(rc, 1)
            self.assertIn("FIXED", g.fail_reason)


class TestReclaimParsing(unittest.TestCase):
    RELOC = ("ExtentFileBackend: reclaim relocated 12 live refs out of victim "
             "slots [3, 4] (196608 bytes)")
    REFUSED = ("ExtentFileBackend: reclaim relocation of 953 live refs "
               "refused: no destination capacity outside victims [1]")
    RECYCLE = "[P3] ts_ms=5 evt=extent_recycle slot=0 generation=1 freed=52559872"

    def test_parse_relocated(self):
        r = gc.parse_reclaim_line(self.RELOC)
        self.assertEqual(r["kind"], "relocated")
        self.assertEqual(r["live_refs"], 12)
        self.assertEqual(r["slots"], [3, 4])
        self.assertEqual(r["bytes"], 196608)

    def test_parse_refused(self):
        r = gc.parse_reclaim_line(self.REFUSED)
        self.assertEqual(r["kind"], "refused")
        self.assertEqual(r["slots"], [1])

    def test_events_and_slot_filter(self):
        ev = gc.parse_storage_events([self.RELOC + "\n", self.REFUSED + "\n",
                                      self.RECYCLE + "\n",
                                      "junk\n"])
        self.assertEqual(len(ev["reclaim_relocated"]), 1)
        self.assertEqual(len(ev["reclaim_refused"]), 1)
        self.assertEqual(gc.extent_recycle_count(ev), 1)
        self.assertEqual(gc.reclaim_events_for_slot(ev, 1)["refused"][0][
            "live_refs"], 953)
        self.assertEqual(gc.reclaim_events_for_slot(ev, 0)["recycle"][0][
            "slot"], "0")
        self.assertEqual(gc.reclaim_events_for_slot(ev, 9), {
            "relocated": [], "refused": [], "recycle": []})

    def test_hits_for_slots_dynamic_victim(self):
        # The campaign's real shape: head in slot 0, the cursor wrapped into
        # slot 1 (also full of live target refs) and the product refused.
        ev = gc.parse_storage_events([self.REFUSED + "\n"])
        target_slots = set(range(20))
        hits = gc.reclaim_hits_for_slots(ev, target_slots)
        self.assertEqual([(k, s) for k, s, _ in hits], [("refused", 1)])
        self.assertEqual(gc.reclaim_hits_for_slots(ev, {5, 6}), [])
        self.assertEqual(gc.reclaim_hits_for_slots(ev, {1})[0][0], "refused")

    def test_dropped_without_backup_parsed(self):
        ev = gc.parse_storage_events([
            "write_back: KV subtree dropped without backup due to host memory "
            "pressure, root node 17\n"])
        self.assertEqual(len(ev["dropped_no_backup"]), 1)
        slim = gc.slim_storage_events(ev)
        self.assertEqual(slim["dropped_no_backup_n"], 1)


class TestHostPoolSizing(unittest.TestCase):
    CONSOLE = (
        "HiCache kv host pool (19904 tokens) is smaller than the device pool "
        "(65536 tokens);L2 cache effectiveness is reduced.\n"
        "Allocating kv hierarchical KV host pool: 19904 tokens, "
        "0.33 GB host memory.\n"
        "Allocating mamba hierarchical KV host pool: 33 tokens, "
        "0.05 GB host memory.\n")

    def test_parse_and_reject_small_pool(self):
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as fh:
            fh.write(self.CONSOLE)
            path = fh.name
        try:
            hp = gc.parse_host_pool(path, prompt_tokens=65000,
                                    host_pool_margin=4096)
            self.assertFalse(hp["ok"])
            self.assertEqual(hp["kv_tokens"], 19904)
            self.assertEqual(hp["mamba_tokens"], 33)
            self.assertEqual(hp["required_kv_host_tokens"], 69096)
            self.assertTrue(hp["smaller_than_device_warnings"])
        finally:
            os.unlink(path)

    def test_sizing_arithmetic(self):
        # production anchor: 32 GB -> 318457 kv tokens; 2 GB -> 19904
        self.assertEqual(gc.kv_host_tokens_for_gb(2), 19904)
        self.assertAlmostEqual(gc.kv_host_tokens_for_gb(32), 318457, delta=16)
        a = gc.sizing_arithmetic(8, 65000, 4096)
        self.assertGreaterEqual(a["predicted_kv_host_tokens"], 69096)
        self.assertEqual(a["min_hicache_size_gb_for_required"], 7)
        self.assertLess(a["chosen_hicache_size_gb_SI"], 32)


class TestGateAStorageProof(unittest.TestCase):
    def _arm(self, storage, device):
        return {"tier": {"storage": storage, "device": device,
                         "storage_backend": "ExtentFileBackend"}}

    def test_storage_proven(self):
        self.assertTrue(ga._storage_proven(self._arm(10, 0), self._arm(10, 0)))

    def test_device_hit_is_not_storage_proof(self):
        self.assertFalse(ga._storage_proven(self._arm(0, 10), self._arm(0, 10)))

    def test_device_residual_blocks_proof(self):
        self.assertFalse(ga._storage_proven(self._arm(10, 3), self._arm(10, 0)))

    def test_per_target_threshold_not_global_max(self):
        # L3: a shorter prompt is judged against its OWN window, not the longer
        # target's global max threshold (which was a false-INVALID for it).
        membership = {"a": {"n_present": 100}, "b": {"n_present": 100}}
        self.assertTrue(ga._targets_in_index_ok(membership,
                                                {"a": 100, "b": 100}, 1000))
        self.assertFalse(ga._targets_in_index_ok(membership,
                                                 {"a": 100, "b": 101}, 1000))


class TestF1ReclaimEvidence(unittest.TestCase):
    def test_refusal_only_is_not_executed(self):
        sweep = {"recycle_count": 0, "relocated_count": 0, "refused_count": 1,
                 "wrap_kind": "refused", "dropped_no_backup_n": 0}
        post = {"membership": {"query_window_len": 100},
                "predicate": {"window_from_page0_hits": 100},
                "head": {"head_present_in_rebuilt_index": True,
                         "head_refreshed_after_drop": False},
                "target_slots": {"head_current_slot": 0},
                "victim": {"generation": 0, "drop_frames": []}}
        ev = f1._reclaim_evidence(sweep, post, 0, 0)
        self.assertTrue(ev["wrap_observed"])
        self.assertFalse(ev["reclaim_executed"])
        self.assertFalse(ev["generation_changed"])
        self.assertIn("fail-closed", ev["refusal_reason"])

    def test_relocation_is_executed_and_head_resolved(self):
        sweep = {"recycle_count": 0, "relocated_count": 1, "refused_count": 0,
                 "wrap_kind": "relocated", "dropped_no_backup_n": 0,
                 "wrap_event": {"kind": "relocated", "live_refs": 12,
                                "slots": [0], "bytes": 196608}}
        post = {"membership": {"query_window_len": 100},
                "predicate": {"window_from_page0_hits": 100},
                "head": {"head_present_in_rebuilt_index": True,
                         "head_refreshed_after_drop": False},
                "target_slots": {"head_current_slot": 7,
                                 "head_current_generation": 0},
                "victim": {"generation": 1,
                           "drop_frames": [{"slot": 0, "new_generation": 1}]}}
        ev = f1._reclaim_evidence(sweep, post, 0, 0)
        self.assertTrue(ev["reclaim_executed"])
        self.assertTrue(ev["generation_changed"])
        self.assertTrue(ev["head_resolved"])
        self.assertTrue(ev["batch_exists_eq_expected"])

    def test_foreign_drop_does_not_block(self):
        sweep = {"recycle_count": 0, "relocated_count": 1, "refused_count": 0,
                 "wrap_kind": "relocated", "dropped_no_backup_n": 7,
                 "drop_scope": {"ok": True, "n_total": 7, "n_foreign": 7,
                                "n_target": 0, "n_unknown": 0}}
        post = {"membership": {"query_window_len": 100},
                "predicate": {"window_from_page0_hits": 100},
                "head": {"head_present_in_rebuilt_index": True,
                         "head_refreshed_after_drop": False},
                "target_slots": {"head_current_slot": 7},
                "victim": {"generation": 1, "drop_frames": []}}
        ev = f1._reclaim_evidence(sweep, post, 0, 0)
        self.assertTrue(ev["no_target_drop_without_backup"])
        self.assertEqual(ev["dropped_no_backup_n"], 7)

    def test_target_drop_blocks(self):
        sweep = {"recycle_count": 0, "relocated_count": 1, "refused_count": 0,
                 "wrap_kind": "relocated", "dropped_no_backup_n": 2,
                 "drop_scope": {"ok": False, "n_total": 2, "n_target": 2,
                                "n_unknown": 0, "target_roots": [77, 78]}}
        post = {"membership": {"query_window_len": 100},
                "predicate": {"window_from_page0_hits": 100},
                "head": {"head_present_in_rebuilt_index": True,
                         "head_refreshed_after_drop": False},
                "target_slots": {"head_current_slot": 7},
                "victim": {"generation": 1, "drop_frames": []}}
        ev = f1._reclaim_evidence(sweep, post, 0, 0)
        self.assertFalse(ev["no_target_drop_without_backup"])

    def test_non_none_scope_without_ok_is_fail_closed(self):
        # L5: with drop rows present, a scope dict lacking an explicit
        # ok=True must never default permissive.
        sweep = {"recycle_count": 0, "relocated_count": 1, "refused_count": 0,
                 "wrap_kind": "relocated", "dropped_no_backup_n": 7,
                 "drop_scope": {"n_total": 7, "n_foreign": 7}}
        post = {"membership": {"query_window_len": 100},
                "predicate": {"window_from_page0_hits": 100},
                "head": {"head_present_in_rebuilt_index": True,
                         "head_refreshed_after_drop": False},
                "target_slots": {"head_current_slot": 7},
                "victim": {"generation": 1, "drop_frames": []}}
        ev = f1._reclaim_evidence(sweep, post, 0, 0)
        self.assertIsNone(ev["drop_scope"].get("ok"))
        self.assertFalse(ev["no_target_drop_without_backup"])
        # No drop rows at all stays ok (nothing to attribute).
        sweep0 = dict(sweep)
        sweep0["dropped_no_backup_n"] = 0
        sweep0.pop("drop_scope")
        ev0 = f1._reclaim_evidence(sweep0, post, 0, 0)
        self.assertTrue(ev0["no_target_drop_without_backup"])


class TestDropScopePredicate(unittest.TestCase):
    UNIFIED = ("[P3] write_back: KV subtree dropped without backup due to host "
               "memory pressure, root node 83")
    HIRADIX = ("[P3] write_back: KV cache on device are dropped without backup "
               "due to host memory pressure, subtree root 77, num_nodes 12")
    UNPARSED = ("write_back: something was dropped without backup due to host "
                "memory pressure (no root in this line)")

    def test_parse_both_producer_formats(self):
        u = gc.parse_drop_no_backup(self.UNIFIED)
        self.assertEqual((u["root_id"], u["num_nodes"], u["format"]),
                         (83, None, "unified"))
        h = gc.parse_drop_no_backup(self.HIRADIX)
        self.assertEqual((h["root_id"], h["num_nodes"], h["format"]),
                         (77, 12, "hiradix"))
        p = gc.parse_drop_no_backup(self.UNPARSED)
        self.assertIsNone(p["root_id"])
        self.assertEqual(p["format"], "unparsed")

    def test_parse_events_collects_scoped_rows(self):
        ev = gc.parse_storage_events([self.UNIFIED + "\n", self.HIRADIX + "\n"])
        self.assertEqual(len(ev["dropped_no_backup"]), 2)
        self.assertEqual([d["root_id"] for d in ev["dropped_scopes"]], [83, 77])
        self.assertEqual(gc.slim_storage_events(ev)["dropped_no_backup_n"], 2)

    def test_target_node_evidence(self):
        ev = gc.parse_storage_events([
            "[P3] evt=rh_match_prepare rid=a fill_len=65000 anchor_id=51\n",
            "[P3] evt=rh_match_prepare rid=b fill_len=65000 anchor_id=84\n",
            "[P3] evt=rh_match_prepare rid=c fill_len=80 anchor_id=9\n",
            "[P3] evt=restore_backup op=3 node=18 requested_frontier=61\n",
            "[P3] evt=restore_backup op=4 node=44 requested_frontier=61\n",
            "[P3] evt=restore_backup op=5 node=200 requested_frontier=61\n",
            "[P3] evt=restore_backup op=6 node=None requested_frontier=61\n",
        ])
        e = gc.target_node_evidence(ev, 65000)
        self.assertEqual(e["anchors"], [51, 84])
        self.assertEqual(e["max_anchor"], 84)
        # node 200 is above the max target anchor -> other subtree
        self.assertEqual(e["durable_nodes"], [18, 44])
        self.assertEqual(e["max_node_id"], 84)
        self.assertTrue(e["has_evidence"])

    def test_no_evidence_is_fail_closed(self):
        ev = gc.parse_storage_events([self.UNIFIED + "\n"])
        e = gc.target_node_evidence(ev, 65000)
        self.assertFalse(e["has_evidence"])
        scoped = gc.scope_drop_events(ev, e, refs_intact=None)
        self.assertEqual(scoped[0]["scope"], gc.DropScope.UNKNOWN)
        self.assertFalse(gc.drop_scope_ok(scoped)["ok"])

    def test_foreign_drop_refs_intact_does_not_invalidate(self):
        # The r2 shape: an unrelated/filler subtree drops while the graded
        # target's durable refs are proven intact offline.
        ev = gc.parse_storage_events([self.UNIFIED + "\n"])
        evidence = {"node_ids": [18, 51], "max_node_id": 51}
        scoped = gc.scope_drop_events(ev, evidence, refs_intact=True)
        self.assertEqual(scoped[0]["scope"], gc.DropScope.FOREIGN)
        self.assertTrue(gc.drop_scope_ok(scoped)["ok"])
        with tempfile.TemporaryDirectory() as td:
            g = gc.Gate("new", td)
            if not gc.drop_scope_ok(scoped)["ok"]:
                g.invalidate("target-scoped drop")
            self.assertEqual(g.finish()[0], "PASS")

    def test_old_any_drop_predicate_invalidates_new_does_not(self):
        # OLD-fails / NEW-passes demonstration against the SAME evidence.
        ev = gc.parse_storage_events([self.UNIFIED + "\n"])
        scoped = gc.scope_drop_events(
            ev, {"node_ids": [18, 51], "max_node_id": 51}, refs_intact=True)
        with tempfile.TemporaryDirectory() as td:
            g_old = gc.Gate("old", td)
            if ev.get("dropped_no_backup"):   # predecessor predicate
                g_old.invalidate("any drop -> INVALID")
            self.assertEqual(g_old.finish()[0], "INVALID")
        with tempfile.TemporaryDirectory() as td:
            g_new = gc.Gate("new", td)
            if not gc.drop_scope_ok(scoped)["ok"]:
                g_new.invalidate("target-scoped drop")
            self.assertEqual(g_new.finish()[0], "PASS")

    def test_root_above_bound_is_unknown_fail_closed(self):
        # The removed node-id bound claimed "drop root 83 > max target node 51
        # => foreign".  Its invariant is false (_split_node can make a higher-id
        # new node the parent of an older lower-id child), so with no positive
        # no-decrease delta proof (refs_intact=None) a drop is UNKNOWN and the
        # run is INVALID -- fail closed, never a foreign PASS.
        ev = gc.parse_storage_events([self.UNIFIED + "\n"])  # root 83
        scoped = gc.scope_drop_events(
            ev, {"node_ids": [18, 51], "max_node_id": 51}, refs_intact=None)
        self.assertEqual(scoped[0]["scope"], gc.DropScope.UNKNOWN)
        summary = gc.drop_scope_ok(scoped)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["unknown_roots"], [83])
        with tempfile.TemporaryDirectory() as td:
            g = gc.Gate("unknown-drop", td)
            if not summary["ok"]:
                g.invalidate("unattributable drop -> INVALID")
            self.assertEqual(g.finish(), ("INVALID", 2))

    def test_root_id_does_not_steer_scope_without_delta_proof(self):
        # Current semantics: the parsed root id is record-only.  A root above
        # the old bound (83 > 51) and one below it (77 <= 84) classify
        # identically as UNKNOWN when no delta proof exists.
        ev = gc.parse_storage_events([self.UNIFIED + "\n",
                                      self.HIRADIX + "\n"])  # roots 83, 77
        scoped = gc.scope_drop_events(
            ev, {"node_ids": [18, 84], "max_node_id": 84}, refs_intact=None)
        self.assertEqual([d["scope"] for d in scoped],
                         [gc.DropScope.UNKNOWN, gc.DropScope.UNKNOWN])
        summary = gc.drop_scope_ok(scoped)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["unknown_roots"], [83, 77])

    def test_refs_lost_is_target(self):
        ev = gc.parse_storage_events([self.HIRADIX + "\n"])  # root 77
        scoped = gc.scope_drop_events(
            ev, {"node_ids": [18], "max_node_id": 18}, refs_intact=False)
        self.assertEqual(scoped[0]["scope"], gc.DropScope.TARGET)
        summary = gc.drop_scope_ok(scoped)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["target_roots"], [77])

    def test_unparsed_without_refs_verdict_is_unknown(self):
        ev = gc.parse_storage_events([self.UNPARSED + "\n"])
        scoped = gc.scope_drop_events(ev, {}, refs_intact=None)
        self.assertIsNone(scoped[0]["root_id"])
        self.assertEqual(scoped[0]["scope"], gc.DropScope.UNKNOWN)
        self.assertFalse(gc.drop_scope_ok(scoped)["ok"])


class TestDurableDeltaProof(unittest.TestCase):
    """Owner closure 1 + D1: FOREIGN requires a no-decrease delta measured
    against a COMPLETE (full-window) drop-free baseline with every proxy
    present.  The stage-level 0.99 ratio is a separate (unchanged) acceptance;
    a single lost durable page must fail closed here even when the ratio is
    still >= 0.99.
    """

    UNIFIED = TestDropScopePredicate.UNIFIED
    # The C2b re-reviewer's exact partial-baseline reproduction: a drop of pages
    # that were not durable yet at the frozen baseline, masked by later growth.
    PARTIAL_BASELINE = {"n_present": 100, "n_absent": 64899,
                        "first_absent_index": 100, "n_runs": 1,
                        "longest_run_len": 100}
    GROWN_NOW = {"n_present": 64998, "n_absent": 1,
                 "first_absent_index": 64998, "n_runs": 1,
                 "longest_run_len": 64998}

    @staticmethod
    def _mem(n_present, n_absent=0, first_absent=None, n_runs=1,
             longest_run_len=None, query_window_len=None):
        mem = {
            "n_present": n_present,
            "n_absent": n_absent,
            "first_absent_index": first_absent,
            "n_runs": n_runs,
            "longest_run_len": (n_present if longest_run_len is None
                                else longest_run_len),
        }
        if query_window_len is not None:
            mem["query_window_len"] = query_window_len
        return mem

    def test_one_page_loss_is_lost_even_above_099_ratio(self):
        # 64999 -> 64998 present is still >= 0.99 of the window; a ratio-based
        # tolerance would call that intact.  The delta proof must report the
        # loss: refs_intact=False -> TARGET -> INVALID.
        window = 64999
        baseline = self._mem(window, query_window_len=window)
        self.assertTrue(gc.baseline_is_complete(baseline))
        now = self._mem(window - 1)
        self.assertGreaterEqual(now["n_present"] / window, 0.99)
        status = gc.durable_delta_status(baseline, now)
        self.assertEqual(status, "lost")
        self.assertIs(gc.combine_delta_status([status]), False)
        ev = gc.parse_storage_events([self.UNIFIED + "\n"])
        scoped = gc.scope_drop_events(ev, {}, refs_intact=False)
        self.assertEqual(scoped[0]["scope"], gc.DropScope.TARGET)
        summary = gc.drop_scope_ok(scoped)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["target_roots"], [83])

    def test_complete_baseline_no_decrease_is_foreign(self):
        # Utility preserved: a COMPLETE baseline plus an unchanged recheck still
        # justifies FOREIGN (a provably unrelated/filler drop stays disposable).
        baseline = self._mem(1000, query_window_len=1000)
        self.assertTrue(gc.baseline_is_complete(baseline))
        self.assertEqual(gc.durable_delta_status(baseline, dict(baseline)),
                         "intact")
        ev = gc.parse_storage_events([self.UNIFIED + "\n"])
        scoped = gc.scope_drop_events(ev, {}, refs_intact=True)
        self.assertEqual(scoped[0]["scope"], gc.DropScope.FOREIGN)
        self.assertTrue(gc.drop_scope_ok(scoped)["ok"])

    def test_partial_baseline_growth_cannot_mask_drop(self):
        # D1 regression: with the permissive old semantics (kept reachable via
        # require_complete_baseline=False) this reads "intact"; the shipped
        # default fails closed because the baseline is partial.
        old = gc.durable_delta_status(self.PARTIAL_BASELINE, self.GROWN_NOW,
                                      require_complete_baseline=False)
        self.assertEqual(old, "intact")
        self.assertFalse(gc.baseline_is_complete(self.PARTIAL_BASELINE))
        status = gc.durable_delta_status(self.PARTIAL_BASELINE, self.GROWN_NOW)
        self.assertEqual(status, "unknown")
        self.assertIsNone(gc.combine_delta_status([status]))
        ev = gc.parse_storage_events([self.UNIFIED + "\n"])  # r2 root 83
        scoped = gc.scope_drop_events(ev, {}, refs_intact=None)
        self.assertEqual(scoped[0]["scope"], gc.DropScope.UNKNOWN)
        summary = gc.drop_scope_ok(scoped)
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["unknown_roots"], [83])
        with tempfile.TemporaryDirectory() as td:
            g = gc.Gate("partial-baseline", td)
            if not summary["ok"]:
                g.invalidate("partial baseline cannot prove a foreign drop")
            self.assertEqual(g.finish(), ("INVALID", 2))

    def test_legitimate_nondurable_tail_is_not_false_invalid_without_drop(self):
        # A legitimate non-durable tail must NOT, by itself, create a
        # false-INVALID: with NO drop rows the scope is vacuously ok and the
        # (unchanged) 0.99 stage check still accepts the tail.  With a drop
        # present, the same partial baseline can no longer prove FOREIGN --
        # that is the deliberate conservative direction (D1).
        tail = self._mem(64000, n_absent=999, first_absent=64000,
                         n_runs=2, longest_run_len=64000,
                         query_window_len=64999)
        self.assertFalse(gc.baseline_is_complete(tail))
        scoped = gc.scope_drop_events(gc.parse_storage_events([]), {},
                                      refs_intact=None)
        self.assertEqual(scoped, [])
        self.assertTrue(gc.drop_scope_ok(scoped)["ok"])
        with tempfile.TemporaryDirectory() as td:
            g = gc.Gate("tail-no-drop", td)
            if not gc.drop_scope_ok(scoped)["ok"]:
                g.invalidate("target-scoped drop")
            self.assertEqual(g.finish(), ("PASS", 0))
        # 0.99 STAGE check unchanged: the legitimate tail is still accepted.
        self.assertTrue(ga._targets_in_index_ok({"A": tail}, {"A": 64000},
                                                64000))
        # A drop with the same partial baseline is unknown, never foreign.
        dropped = gc.parse_storage_events([self.UNIFIED + "\n"])
        refs = gc.combine_delta_status(
            [gc.durable_delta_status(tail, dict(tail))])
        self.assertIsNone(refs)
        self.assertFalse(gc.drop_scope_ok(gc.scope_drop_events(
            dropped, {}, refs_intact=refs))["ok"])

    def test_recheck_snapshot_catches_drop_between_snapshots(self):
        # D1(ii): a single post-drop snapshot can look intact while the drop
        # lands between it and its successor; the recheck combiner is
        # worst-case and fails closed when a re-snapshot is missing.
        baseline = self._mem(1000, query_window_len=1000)
        between = self._mem(1000, query_window_len=1000)
        after = self._mem(999, n_absent=1, first_absent=999, n_runs=2,
                          longest_run_len=999, query_window_len=1000)
        self.assertEqual(
            gc.delta_status_with_rechecks(baseline, [between]), "intact")
        self.assertEqual(
            gc.delta_status_with_rechecks(baseline, [between, after]), "lost")
        self.assertIs(gc.combine_delta_status(
            [gc.delta_status_with_rechecks(baseline, [between, after])]), False)
        self.assertEqual(
            gc.delta_status_with_rechecks(baseline, [between, {}]), "unknown")
        self.assertEqual(gc.delta_status_with_rechecks(baseline, []),
                         "unknown")

    def test_missing_proxy_is_unknown(self):
        # L4: an omitted proxy is never treated as unchanged.
        full = self._mem(1000, query_window_len=1000)
        self.assertEqual(
            gc.durable_delta_status({"n_present": 1000}, full), "unknown")
        self.assertEqual(
            gc.durable_delta_status(full, {"n_present": 1000}), "unknown")
        for key in gc._DELTA_PROXIES:
            partial = dict(full)
            del partial[key]
            self.assertIn(key, gc._missing_delta_proxies(partial))
            self.assertEqual(
                gc.durable_delta_status(partial, full), "unknown")
            self.assertFalse(gc.baseline_is_complete(partial))

    def test_empty_or_missing_membership_is_fail_closed(self):
        # L1: empty/absent snapshots must never default to "intact".
        self.assertEqual(gc.durable_delta_status({}, self._mem(100)), "unknown")
        self.assertEqual(gc.durable_delta_status(self._mem(100), {}), "unknown")
        self.assertIsNone(gc.combine_delta_status([]))
        self.assertIsNone(gc.combine_delta_status(["unknown"]))
        self.assertIsNone(gc.combine_delta_status(["intact", "unknown"]))
        self.assertFalse(ga._targets_in_index_ok({}, {}, 1))
        ev = gc.parse_storage_events([self.UNIFIED + "\n"])
        scoped = gc.scope_drop_events(ev, {}, refs_intact=None)
        self.assertEqual(scoped[0]["scope"], gc.DropScope.UNKNOWN)
        self.assertFalse(gc.drop_scope_ok(scoped)["ok"])

    def test_unscoped_raw_rows_are_fail_closed(self):
        # L2: rows without a recognised scope key are never disposable.
        summary = gc.drop_scope_ok([{"root_id": 83},
                                    {"root_id": 77, "scope": "bogus"}])
        self.assertFalse(summary["ok"])
        self.assertEqual(summary["n_unknown"], 2)


class TestF1ColdWindowDropScope(unittest.TestCase):
    """Owner closure C3: the cold window classifies against the POST-request
    membership; the pre-request verdict is never reused as refs_intact."""

    DROP = ("[P3] write_back: KV subtree dropped without backup due to host "
            "memory pressure, root node 83\n")

    @staticmethod
    def _full(n_present=64999, window=64999):
        absent = window - n_present
        return {"n_present": n_present, "n_absent": absent,
                "first_absent_index": (None if absent == 0 else n_present),
                "n_runs": (1 if absent == 0 else 2),
                "longest_run_len": n_present, "query_window_len": window}

    def test_post_cold_loss_overrides_pre_request_full_snapshot(self):
        # The pre-request check sees every page present; reusing it would call
        # this cold-window drop foreign.  The post-cold snapshot lost a page
        # -> refs_intact=False -> TARGET -> the cold oracle is INVALID.
        ev = gc.parse_storage_events([self.DROP])
        refs, scope = f1._cold_window_drop_scope(
            ev, {}, self._full(), self._full(64998))
        self.assertIs(refs, False)
        self.assertFalse(scope["ok"])
        self.assertEqual(scope["target_roots"], [83])

    def test_no_decrease_delta_makes_cold_drop_foreign(self):
        ev = gc.parse_storage_events([self.DROP])
        refs, scope = f1._cold_window_drop_scope(
            ev, {}, self._full(), self._full())
        self.assertIs(refs, True)
        self.assertTrue(scope["ok"])
        self.assertEqual(scope["n_foreign"], 1)

    def test_missing_post_snapshot_is_unknown_fail_closed(self):
        ev = gc.parse_storage_events([self.DROP])
        refs, scope = f1._cold_window_drop_scope(ev, {}, self._full(), {})
        self.assertIsNone(refs)
        self.assertFalse(scope["ok"])

    def test_partial_pre_snapshot_is_unknown_fail_closed(self):
        # D1: a PARTIAL pre-request snapshot cannot prove a cold-window drop
        # foreign even when the post snapshot is unchanged (no growth observed
        # is not a complete-baseline proof).
        ev = gc.parse_storage_events([self.DROP])
        tail_pre = self._full(n_present=64000)
        self.assertFalse(gc.baseline_is_complete(tail_pre))
        refs, scope = f1._cold_window_drop_scope(
            ev, {}, tail_pre, dict(tail_pre))
        self.assertIsNone(refs)
        self.assertFalse(scope["ok"])
        self.assertEqual(scope["unknown_roots"], [83])


class TestRelocationReserve(unittest.TestCase):
    def test_destination_fits_is_ok(self):
        r = gc.relocation_reserve_check({
            "slot": 1, "live_bytes": 61079552,
            "relocation_headroom_bytes": 67108864,
            "target_live_refs": 953, "reclaim_relocatable": True})
        self.assertTrue(r["holds_target_live_refs"])
        self.assertTrue(r["destination_capacity_exists"])
        self.assertTrue(r["ok"])

    def test_option_c_backpressure_is_invalid(self):
        # The preserved r2 shape: victim live 61079552 B > headroom 49201152 B.
        r = gc.relocation_reserve_check({
            "slot": 1, "live_bytes": 61079552,
            "relocation_headroom_bytes": 49201152,
            "target_live_refs": 953, "reclaim_relocatable": False})
        self.assertTrue(r["holds_target_live_refs"])
        self.assertFalse(r["destination_capacity_exists"])
        self.assertFalse(r["ok"])

    def test_no_target_refs_not_ok(self):
        r = gc.relocation_reserve_check({
            "slot": 2, "live_bytes": 0,
            "relocation_headroom_bytes": 1 << 30,
            "target_live_refs": 0, "reclaim_relocatable": False})
        self.assertFalse(r["ok"])


class TestAssertPreconditions(unittest.TestCase):
    def test_missing_precondition_is_invalid_never_fail(self):
        with tempfile.TemporaryDirectory() as td:
            g = gc.Gate("p", td)
            ok = gc.assert_preconditions(g, "arm", [
                ("ready", True),
                ("present", False, {"why": "not in index"})])
            self.assertFalse(ok)
            verdict, rc = g.finish()
            self.assertEqual(verdict, "INVALID")
            self.assertEqual(rc, 2)
            self.assertIn("present", g.invalid_reason)

    def test_all_present_passes(self):
        with tempfile.TemporaryDirectory() as td:
            g = gc.Gate("p", td)
            self.assertTrue(gc.assert_preconditions(
                g, "arm", [("a", True), ("b", True, {"n": 1})]))
            self.assertEqual(g.finish(), ("PASS", 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
