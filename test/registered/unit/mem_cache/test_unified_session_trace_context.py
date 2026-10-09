import os
import unittest
from unittest.mock import patch

from sglang.srt.managers.schedule_batch import Req
from sglang.srt.mem_cache.trace_context import make_trace_context
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache
from sglang.srt.session.session_controller import Session


class TraceContextContractTest(unittest.TestCase):
    def test_controller_session_request_without_generation_is_fail_closed(self):
        class Cache:
            _t38c_session_builds = {}
            _t38c_session_contexts = {}
            _t38c_req_session_id = staticmethod(UnifiedRadixCache._t38c_req_session_id)
            _t38c_trace_context_for_req = UnifiedRadixCache._t38c_trace_context_for_req

        cache = Cache()
        req = type("Req", (), {"session_id": None, "session": type("Session", (), {"session_id": "ordinary"})(), "rid": "rid-1", "session_generation": None})()
        with patch("sglang.srt.mem_cache.unified_radix_cache.durable_trace_enabled", return_value=True), patch(
            "sglang.srt.mem_cache.unified_radix_cache.make_trace_context", side_effect=make_trace_context
        ), patch.dict(os.environ, {"T38C_RUN_ID": "unit-run"}):
            self.assertIsNone(cache._t38c_trace_context_for_req(req))

    def test_radix_native_request_gets_request_scoped_build_context(self):
        class Cache:
            _t38c_session_builds = {}
            _t38c_session_contexts = {}
            _t38c_req_session_id = staticmethod(UnifiedRadixCache._t38c_req_session_id)
            _t38c_trace_context_for_req = UnifiedRadixCache._t38c_trace_context_for_req

        cache = Cache()
        req = type("Req", (), {"session_id": "radix-session", "session": None, "rid": "rid-2", "session_generation": 7})()
        with patch("sglang.srt.mem_cache.unified_radix_cache.durable_trace_enabled", return_value=True), patch.dict(
            os.environ, {"T38C_RUN_ID": "unit-run"}
        ):
            context = cache._t38c_trace_context_for_req(req)
        self.assertEqual(context["session_id"], "radix-session")
        self.assertEqual(context["session_generation"], 7)
        self.assertEqual(context["build_rid"], "rid-2")
        self.assertIsNone(context["warm_rid"])

    def test_session_controller_streaming_modes_are_distinct(self):
        ordinary = Session(32768, "ordinary", streaming=False)
        streaming = Session(32768, "streaming", streaming=True)
        self.assertFalse(ordinary.streaming)
        self.assertTrue(streaming.streaming)

    def test_r5_prefill_only_radix_native_req_is_finished(self):
        req = Req.__new__(Req)
        req.sampling_params = type("SamplingParams", (), {"max_new_tokens": 0})()
        with patch("sglang.srt.managers.schedule_batch.get_spec") as get_spec:
            get_spec.return_value.speculative_algorithm = None
            self.assertTrue(req.is_prefill_only)
