"""Operator trace-marker gating: memoized, still enable-able mid-run."""

import unittest
from unittest import mock

from sglang.srt.mem_cache import trace_context
from sglang.srt.mem_cache import unified_radix_cache


class TraceMarkerMemoTests(unittest.TestCase):
    def setUp(self):
        trace_context._MARKER_CACHE.clear()

    def tearDown(self):
        trace_context._MARKER_CACHE.clear()

    def test_durable_gate_stats_once_per_interval(self):
        with mock.patch.object(
            trace_context.os.path, "exists", return_value=False
        ) as exists:
            for _ in range(64):
                self.assertFalse(trace_context.durable_trace_enabled())
            # One stat for the whole interval instead of one per call.
            self.assertEqual(exists.call_count, 1)

    def test_marker_is_still_observed_after_the_interval(self):
        with mock.patch.object(
            trace_context.os.path, "exists", side_effect=[False, True]
        ) as exists:
            self.assertFalse(trace_context.durable_trace_enabled())
            with mock.patch.object(trace_context, "_MARKER_TTL_S", 0.0):
                self.assertTrue(trace_context.durable_trace_enabled())
            self.assertEqual(exists.call_count, 2)

    def test_cache_gate_and_log_gate_share_the_memo(self):
        self.assertIs(trace_context.marker_present, trace_context.marker_present)
        with mock.patch.object(
            trace_context.os.path, "exists", return_value=False
        ) as exists:
            self.assertFalse(unified_radix_cache._t38c_durable_enabled())
            unified_radix_cache._t38c_log({"evt": "probe"})
            unified_radix_cache._t38c_durable_log({"evt": "probe"})
            # Same one-second window: still at most one stat per marker path
            # (two paths total: the durable marker and the probe marker).
            self.assertLessEqual(exists.call_count, 2)


if __name__ == "__main__":
    unittest.main()
