"""No-op overhead baseline for the P2-A timing probe (stdlib unittest).

The FROZEN P2-A contract requires the per-call overhead of the probe helper
primitives (timestamp read + f-string formatting + emit path) to be
``<< 1 ms`` with a target ``< 50 us``.  This does NOT need a live server: it
exercises the helper module only.

Run:
    python -m unittest 3090-dev/test_p2a_timing_probe_overhead.py -v
"""

import logging
import os
import sys
import time
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "python"))

from sglang.srt.mem_cache import p2a_timing_probe as probe  # noqa: E402

ENV = probe.ENV_GATE
TARGET_NS = 50_000
ITERATIONS = 100_000
ROUNDS = 7


def _median_ns_per_call(func, iterations=ITERATIONS, rounds=ROUNDS):
    for _ in range(max(1, iterations // 10)):  # warmup
        func()
    samples = []
    for _ in range(rounds):
        start = time.perf_counter_ns()
        for _ in range(iterations):
            func()
        samples.append((time.perf_counter_ns() - start) / iterations)
    samples.sort()
    return samples[len(samples) // 2]


class ProbeOverheadBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Discard the emitted record without touching stderr/stdout; the point
        # is the helper's CPU cost, not log I/O.
        cls._logger = probe.logger
        cls._old_handlers = cls._logger.handlers[:]
        cls._old_propagate = cls._logger.propagate
        cls._old_level = cls._logger.level
        cls._logger.handlers = [logging.NullHandler()]
        cls._logger.propagate = False
        cls._logger.setLevel(logging.INFO)
        cls._old_env = os.environ.get(ENV)
        os.environ[ENV] = "1"

    @classmethod
    def tearDownClass(cls):
        cls._logger.handlers = cls._old_handlers
        cls._logger.propagate = cls._old_propagate
        cls._logger.setLevel(cls._old_level)
        if cls._old_env is None:
            os.environ.pop(ENV, None)
        else:
            os.environ[ENV] = cls._old_env

    def test_clock_read_baseline(self):
        ns_per_call = _median_ns_per_call(time.monotonic_ns)
        print(
            f"\n[P2A baseline] time.monotonic_ns(): {ns_per_call:.1f} ns/call"
        )
        self.assertLess(ns_per_call, TARGET_NS)

    def test_emit_path_overhead_under_target(self):
        # Full probe primitive: clock read + identity/probe payload formatting
        # (f-strings) + gated emit path.
        identity = {"node_id": 11, "build_id": "b-1", "session_generation": 2}

        def _call():
            block_start = time.monotonic_ns()
            probe_ns = time.monotonic_ns() - block_start
            probe.emit(
                block_start,
                "prefetch_issued",
                probe_ns,
                rid="rid-bench",
                prefetch_length=512,
                prefetch_issue_mono_ns=block_start,
                attempt_id="att-bench",
                **identity,
            )

        ns_per_call = _median_ns_per_call(_call)
        print(
            f"[P2A baseline] emit path (clock + f-strings + emit): "
            f"{ns_per_call:.1f} ns/call"
        )
        self.assertLess(
            ns_per_call,
            TARGET_NS,
            f"probe emit overhead {ns_per_call:.1f} ns/call exceeds "
            f"target {TARGET_NS} ns/call",
        )

    def test_disabled_gate_path_under_target(self):
        old = os.environ.get(ENV)
        os.environ[ENV] = "0"
        try:
            disabled_ns = _median_ns_per_call(
                lambda: probe.emit(1, "x", 0, rid="r")
            )
        finally:
            if old is None:
                os.environ.pop(ENV, None)
            else:
                os.environ[ENV] = old
        print(f"[P2A baseline] emit path (gate OFF): {disabled_ns:.1f} ns/call")
        self.assertLess(disabled_ns, TARGET_NS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
