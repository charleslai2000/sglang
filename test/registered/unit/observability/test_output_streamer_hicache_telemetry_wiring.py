"""Regression: the generation accumulator must receive the hicache telemetry
accessor through the real scheduler output wiring.

The telemetry commit added ``self.hicache_telemetry.append(
self.get_hicache_telemetry(req))`` to ``_GenerationStreamAccumulator.accept``
but never declared the injected ``get_hicache_telemetry`` field nor bound it at
the construction site in ``SchedulerOutputStreamer._stream_output_generation``.
Because the failure is an attribute lookup, it fired before the staticmethod
body ran and crashed the first decode request unconditionally.

These tests drive ``_stream_output_generation`` (the production construction
site) rather than constructing the dataclass by hand, so they fail with the
exact ``AttributeError`` on the pre-fix bytes.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sglang.srt.disaggregation.utils import DisaggregationMode
from sglang.srt.managers.scheduler_components.output_streamer import (
    SchedulerOutputStreamer,
    _GenerationStreamAccumulator,
)
from sglang.srt.speculative.spec_info import SpeculativeAlgorithm
from sglang.test.ci.ci_register import register_cpu_ci

register_cpu_ci(est_time=1, suite="base-a-test-cpu")


class _FinishedReq:
    """Minimal faithful request that reaches the telemetry append in accept()."""

    def __init__(self, *, telemetry_enabled: bool, export_enabled: bool = False):
        self.rid = "req-1"
        self.http_worker_ipc = None
        self.finished_reason = SimpleNamespace(to_json=lambda: {"type": "stop"})
        self.finished_output = False
        self.finished_len = None
        self.beam_group = None
        self.stream = False
        self.sampling_params = SimpleNamespace(
            stream_interval=None,
            skip_special_tokens=True,
            spaces_between_special_tokens=True,
            no_stop_trim=False,
        )
        self.output_ids = [10]
        self.output_ids_through_stop = [10]
        self.send_token_offset = 0
        self.send_output_token_logprobs_offset = 0
        self.send_decode_id_offset = 0
        self.decoded_text = ""
        self.origin_input_ids = [1, 2, 3]
        self.reasoning_tokens = 0
        self.cached_tokens = 0
        self.cached_tokens_device = 0
        self.cached_tokens_host = 0
        self.cached_tokens_storage = 0
        self.retraction_count = 0
        self.time_stats = None
        self.return_hidden_states = False
        self.return_routed_experts = False
        self.return_indexer_topk = False
        self.return_sampling_mask = False
        self.mm_image_tokens = 0
        self.mm_audio_tokens = 0
        self.mm_video_tokens = 0
        self.multimodal_inputs = None
        self.customized_info = None
        self.weight_version_events = []
        self.hicache_telemetry_enabled = telemetry_enabled
        self.hicache_telemetry_export_enabled = export_enabled

    def finished(self):
        return True

    def init_incremental_detokenize(self):
        return self.output_ids_through_stop, 0


def _streamer() -> SchedulerOutputStreamer:
    class Streamer(SchedulerOutputStreamer):
        def get_cached_tokens_details(self, req):
            return None

    return Streamer(
        send_to_detokenizer=SimpleNamespace(send_output=lambda payload: None),
        tree_cache=None,
        ps=SimpleNamespace(dp_rank=0, attn_tp_rank=0),
        server_args=SimpleNamespace(),
        is_generation=True,
        spec_algorithm=SpeculativeAlgorithm.NONE,
        disaggregation_mode=DisaggregationMode.NULL,
        enable_hicache_storage=lambda: False,
    )


class TestOutputStreamerHicacheTelemetryWiring(unittest.TestCase):
    def setUp(self):
        serving_patch = patch(
            "sglang.srt.managers.scheduler_components.output_streamer.get_serving",
            return_value=SimpleNamespace(stream_interval=1, weight_version="default"),
        )
        observability_patch = patch(
            "sglang.srt.managers.scheduler_components.output_streamer.get_observability",
            return_value=SimpleNamespace(enable_request_time_stats_logging=False),
        )
        serving_patch.start()
        observability_patch.start()
        self.addCleanup(serving_patch.stop)
        self.addCleanup(observability_patch.stop)

    def _accept_through_wiring(self, req) -> _GenerationStreamAccumulator:
        """Run the real `_stream_output_generation` construction path and return
        the accumulator it built."""
        captured = {}

        def capture(acc, *, dp_rank, is_idle_batch):
            captured["acc"] = acc
            return None

        with patch.object(_GenerationStreamAccumulator, "to_payload", capture):
            _streamer()._stream_output_generation([req], False)

        return captured["acc"]

    def test_disabled_telemetry_accept_does_not_raise_and_records_none(self):
        acc = self._accept_through_wiring(
            _FinishedReq(telemetry_enabled=False)
        )
        # Populated per emitted request; None means telemetry is disabled.
        self.assertEqual(acc.hicache_telemetry, [None])

    def test_enabled_telemetry_flows_through_the_bound_accessor(self):
        sentinel = {"schema": "hicache_request.v1", "prompt_tokens": 3}
        req = _FinishedReq(telemetry_enabled=True, export_enabled=True)
        with patch(
            "sglang.srt.managers.scheduler_components.output_streamer."
            "build_and_observe_hicache_telemetry",
            return_value=sentinel,
        ):
            acc = self._accept_through_wiring(req)
        # The production staticmethod (not the safe default lambda) must be bound.
        self.assertEqual(acc.hicache_telemetry, [sentinel])


if __name__ == "__main__":
    unittest.main()
