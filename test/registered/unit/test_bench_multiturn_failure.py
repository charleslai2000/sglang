"""Failure-path regression tests for the official multi-turn benchmark."""

import queue
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from benchmark.hicache.bench_multiturn import WorkloadGenerator


class _Progress:
    n = 0
    total = 2

    def close(self):
        pass


class TestBenchMultiturnFailureExit(unittest.TestCase):
    def test_failed_response_stops_sender_and_response_handler(self):
        gen = WorkloadGenerator.__new__(WorkloadGenerator)
        gen.sent_requests = 1
        gen.completed_requests = 0
        gen.failed_requests = 0
        gen.request_failed = threading.Event()
        gen.client_failures = set()
        gen.response_queue = queue.Queue()
        gen.ready_queue = mock.Mock()
        gen.max_parallel = 4
        gen.pbar = _Progress()
        gen.pbar.n = 1
        gen.performance_metrics = {
            "ttft": [],
            "itl": [],
            "latency": [],
            "prompt_len": [],
            "cached_tokens": [],
            "generated_len": [],
        }
        gen.start_time = None
        gen.num_rounds = 1
        gen.finished_time = None
        gen.fixed_history_tokens = False
        gen.enable_round_barrier = False
        gen.distribution = "poisson"
        gen.request_rate = 8

        # The sender must not issue any additional work after the error; it
        # exits once the already-sent requests have all returned.
        gen.request_hash_log = None
        gen.ready_queue.pop.return_value = (0, {})
        sender = threading.Thread(target=gen.request_sender)
        response = SimpleNamespace(success=False, error="synthetic failure")
        gen.response_queue.put((0, response))
        handler = threading.Thread(target=gen.response_handler)

        handler.start()
        handler.join(timeout=2)
        sender.start()
        sender.join(timeout=2)

        self.assertFalse(sender.is_alive())
        self.assertFalse(handler.is_alive())
        self.assertEqual(gen.completed_requests, 1)
        self.assertEqual(gen.failed_requests, 1)
        self.assertEqual(gen.client_failures, {0})


if __name__ == "__main__":
    unittest.main()
