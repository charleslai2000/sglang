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


if __name__ == "__main__":
    unittest.main(verbosity=2)
