"""Focused stdlib unit tests for the P2-A observation-only timing probe.

Guards the FROZEN P2-A measurement contract requirements:

* inert when ``SGLANG_P2A_TIMING_PROBE`` is unset/false (no field write, no
  timestamp read, no emission);
* M1 sets ``req.hicache_enqueue_mono_ns`` exactly once and never overwrites on
  a re-queue/retraction;
* the marks live on the ``time.monotonic_ns`` domain (never wall-clock);
* ``probe_ns`` is reported and guarded.

Pure stdlib (no pytest, no torch); runs against the helper module directly.
"""

import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
)
sys.path.insert(0, os.path.join(_REPO_ROOT, "python"))

from sglang.srt.mem_cache import p2a_timing_probe as probe  # noqa: E402

ENV = probe.ENV_GATE


def _env(value):
    return mock.patch.dict(os.environ, {ENV: value})


class GateTest(unittest.TestCase):
    def test_truthy_values_enable(self):
        for value in ("1", "true", "TRUE", "yes", "on", " On "):
            with _env(value):
                self.assertTrue(probe.p2a_enabled(), value)

    def test_falsey_and_unset_disable(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ENV, None)
            self.assertFalse(probe.p2a_enabled())
        for value in ("", "0", "false", "False", "off", "no", "random"):
            with _env(value):
                self.assertFalse(probe.p2a_enabled(), value)


class MarkEnqueueTest(unittest.TestCase):
    def _req(self, **kw):
        req = SimpleNamespace(rid="rid-1", node_id=11, session_generation=3)
        for name, value in kw.items():
            setattr(req, name, value)
        return req

    def test_inert_when_disabled(self):
        req = self._req()
        with _env("0"), mock.patch.object(probe.logger, "info") as info:
            result = probe.mark_enqueue(req)
        self.assertFalse(result)
        self.assertFalse(
            hasattr(req, "hicache_enqueue_mono_ns"),
            "disabled probe must not write the mark field",
        )
        info.assert_not_called()

    def test_sets_exactly_once_and_never_overwrites(self):
        req = self._req()
        with _env("1"), mock.patch.object(probe.logger, "info") as info:
            first = probe.mark_enqueue(req)
            first_mark = req.hicache_enqueue_mono_ns
            # A retraction/re-queue re-enters with a stale field: no overwrite,
            # no second emission.
            second = probe.mark_enqueue(req)
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(req.hicache_enqueue_mono_ns, first_mark)
        self.assertEqual(info.call_count, 1)

    def test_mark_is_monotonic_ns_domain(self):
        req = self._req()
        with _env("1"), mock.patch.object(probe.logger, "info"):
            before = time.monotonic_ns()
            probe.mark_enqueue(req)
            after = time.monotonic_ns()
        mark = req.hicache_enqueue_mono_ns
        self.assertGreaterEqual(mark, before)
        self.assertLessEqual(mark, after)
        # A wall-clock epoch value is ~1.7e18 ns away from the boot clock; the
        # mark must be on the monotonic clock, not time.time_ns().
        self.assertLess(abs(mark - before), 10**9)
        self.assertGreater(abs(mark - time.time_ns()), 10**12)

    def test_probe_ns_reported_and_bounded(self):
        req = self._req()
        with _env("1"), mock.patch.object(probe, "emit") as emit_mock:
            probe.mark_enqueue(req)
        emit_mock.assert_called_once()
        args, kwargs = emit_mock.call_args
        self.assertEqual(args[1], "enqueue_mono_ns")
        probe_ns = args[2]
        self.assertIsInstance(probe_ns, int)
        self.assertGreaterEqual(probe_ns, 0)
        self.assertLess(probe_ns, 1_000_000)
        self.assertEqual(kwargs["rid"], "rid-1")
        self.assertEqual(kwargs["enqueue_mono_ns"], args[0])
        self.assertEqual(kwargs["session_generation"], 3)


class EmitTest(unittest.TestCase):
    def test_emit_inert_when_disabled(self):
        with _env("0"), mock.patch.object(probe.logger, "info") as info:
            probe.emit(1, "x", 0, rid="r")
        info.assert_not_called()

    def test_emit_when_enabled(self):
        with _env("1"), mock.patch.object(probe.logger, "info") as info:
            probe.emit(123, "evt", 7, rid="r")
        info.assert_called_once()
        format_string = info.call_args.args[0]
        self.assertIn("ts_ns", format_string)
        self.assertIn("probe_ns", format_string)


class IdentityTest(unittest.TestCase):
    def test_identity_prefers_object_then_context(self):
        operation = SimpleNamespace(node_id=None, session_generation=None)
        context = {
            "node_id": 42,
            "build_rid": "build-9",
            "session_generation": 5,
        }
        identity = probe.probe_identity(operation, context)
        self.assertEqual(identity["node_id"], 42)
        self.assertEqual(identity["build_id"], "build-9")
        self.assertEqual(identity["session_generation"], 5)

    def test_identity_never_fabricates(self):
        identity = probe.probe_identity(SimpleNamespace(rid="r"))
        self.assertIsNone(identity["node_id"])
        self.assertIsNone(identity["build_id"])
        self.assertIsNone(identity["session_generation"])


class StorageQueryProbeTest(unittest.TestCase):
    def test_begin_is_none_when_disabled(self):
        with _env("0"):
            self.assertIsNone(probe.begin_storage_query_probe())

    def test_begin_reads_monotonic_when_enabled(self):
        with _env("1"):
            before = time.monotonic_ns()
            handle = probe.begin_storage_query_probe()
            after = time.monotonic_ns()
        self.assertIsNotNone(handle)
        self.assertGreaterEqual(handle.enter_mono_ns, before)
        self.assertLessEqual(handle.enter_mono_ns, after)
        self.assertEqual(handle.backend_lookup_ns, 0)

    def test_emit_fields_async_prefetch(self):
        operation = SimpleNamespace(
            request_id="rid-7", prefetch_attempt_id="att-7"
        )
        handle = probe.StorageQueryProbe()
        with _env("1"), mock.patch.object(probe, "emit") as emit_mock:
            handle.note_backend_lookup(handle.enter_mono_ns)
            handle.emit(operation, query_len=8, kv_hit_pages=3)
        args, kwargs = emit_mock.call_args
        self.assertEqual(args[1], "storage_hit_query")
        self.assertEqual(kwargs["caller"], "async_prefetch")
        self.assertEqual(kwargs["rid"], "rid-7")
        self.assertEqual(kwargs["attempt_id"], "att-7")
        self.assertEqual(kwargs["query_len"], 8)
        self.assertEqual(kwargs["kv_hit_pages"], 3)
        self.assertEqual(kwargs["lock_wait_ns"], "N/A")
        self.assertEqual(kwargs["syscall_wait_ns"], "N/A")
        self.assertEqual(kwargs["all_reduce_ns"], "N/A")
        self.assertGreaterEqual(kwargs["backend_lookup_ns"], 0)
        self.assertGreaterEqual(args[2], 0)
        self.assertLess(args[2], 1_000_000)

    def test_emit_fields_sync_decode(self):
        operation = SimpleNamespace(request_id="__storage_hit_query__")
        handle = probe.StorageQueryProbe()
        with _env("1"), mock.patch.object(probe, "emit") as emit_mock:
            handle.emit(operation, query_len=4, kv_hit_pages=0)
        _, kwargs = emit_mock.call_args
        self.assertEqual(kwargs["caller"], "sync_decode")
        self.assertIsNone(kwargs["attempt_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
