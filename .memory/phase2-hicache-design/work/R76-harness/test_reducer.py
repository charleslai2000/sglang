#!/usr/bin/env python3
"""Synthetic positive and negative traces for the offline P0-B reducer."""

from __future__ import annotations

import copy
import unittest

from p0b_reducer import reduce_trace


IDENTITY = {
    "rid": "r76-rid-1",
    "session_id": "r76-session-1",
    "node_id": "3060-node-1",
    "build_id": "build-r76",
}


def event(seq: int, event_type: str, **fields: object) -> dict[str, object]:
    return {"seq": seq, "type": event_type, **IDENTITY, **fields}


def positive_trace() -> dict[str, object]:
    return {
        "schema": "p0b.trace.v1",
        "target_gpu": "3060",
        "identity": dict(IDENTITY),
        "events": [
            event(1, "storage_query", hit_kind="full", kv_required_tokens=54976, kv_hit_tokens=54976, mamba_required_units=1, mamba_hit_units=1),
            event(2, "alloc_attempt", attempt=1, outcome="terminal_failure", non_allocable=True, failure_class="NON_ALLOCABLE", failed_domains=["kv"]),
            event(3, "wait", state="WAIT_CAPACITY", reason="HOST_ALLOC", parked=True, fifo_position=0, generations={"kv": 7}),
            event(4, "allocability_change", domain="kv", real=True, change_id="kv-change-8"),
            event(5, "generation_advance", domain="kv", before=7, after=8, change_id="kv-change-8"),
            event(6, "retry", attempt=2, fifo_position=0, grant=True, generation=8),
            event(7, "reclaim", attempt=2, bounded=True, full_span=True, requested_tokens=54976, reclaimed_tokens=54976),
            event(8, "alloc_attempt", attempt=2, outcome="success", full_span=True),
            event(9, "restore", attempt=2, kv_restored_tokens=54976, mamba_restored_units=1, complete=True),
            event(10, "ready", attempt=2, state="READY", kv_complete=True, mamba_complete=True),
        ],
    }


class ReducerTests(unittest.TestCase):
    def test_positive_trace_passes_all_oracle_items(self) -> None:
        result = reduce_trace(positive_trace())
        self.assertTrue(result["accepted"], result)
        self.assertEqual(result["oracle_items"], 11)

    def test_incomplete_trace_rejects_fail_closed(self) -> None:
        trace = positive_trace()
        trace["events"] = trace["events"][:-2]
        result = reduce_trace(trace)
        self.assertFalse(result["accepted"])

    def test_same_generation_retry_rejects(self) -> None:
        trace = positive_trace()
        trace["events"][5]["generation"] = 7
        result = reduce_trace(trace)
        self.assertFalse(result["accepted"])

    def test_crop_and_repeated_retry_reject(self) -> None:
        trace = positive_trace()
        trace["events"][7]["crop_attempted"] = True
        trace["events"].insert(6, copy.deepcopy(trace["events"][5]))
        for sequence, item in enumerate(trace["events"], start=1):
            item["seq"] = sequence
        result = reduce_trace(trace)
        self.assertFalse(result["accepted"])


if __name__ == "__main__":
    unittest.main()
