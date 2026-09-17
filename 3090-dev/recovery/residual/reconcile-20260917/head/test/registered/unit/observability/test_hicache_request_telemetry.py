import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

_MODULE_PATH = (
    Path(__file__).parents[4]
    / "python/sglang/srt/observability/hicache_telemetry.py"
)
_SPEC = importlib.util.spec_from_file_location("hicache_telemetry", _MODULE_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

(
    HICACHE_LATENCY_BUCKETS,
    HICACHE_PROMPT_SOURCES,
    HICACHE_STAGE_NAMES,
    build_hicache_telemetry,
    build_and_observe_hicache_telemetry,
    derive_hicache_accounting,
    public_hicache_telemetry,
) = (
    _MODULE.HICACHE_LATENCY_BUCKETS,
    _MODULE.HICACHE_PROMPT_SOURCES,
    _MODULE.HICACHE_STAGE_NAMES,
    _MODULE.build_hicache_telemetry,
    _MODULE.build_and_observe_hicache_telemetry,
    _MODULE.derive_hicache_accounting,
    _MODULE.public_hicache_telemetry,
)


class TestHiCacheControllerPublication(unittest.TestCase):
    def test_issue_timestamp_is_initialized_at_queue_put(self):
        controller_module_path = (
            Path(__file__).parents[4]
            / "python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py"
        )
        # The production controller seam is covered structurally here: the
        # controller assigns the field immediately before put, while the
        # worker-side query only assigns query timestamps after dequeue.
        source = controller_module_path.read_text()
        self.assertLess(
            source.index("operation.prefetch_issue_mono_ns = time.monotonic_ns()"),
            source.index("self.prefetch_queue.put(operation)"),
        )
        self.assertNotIn(
            "operation.prefetch_issue_mono_ns = time.monotonic_ns()",
            Path(__file__).parents[4]
            .joinpath("python/sglang/srt/mem_cache/unified_radix_cache.py")
            .read_text(),
        )


class TestHiCacheAccounting(unittest.TestCase):
    def test_conservation_and_mamba_exclusion(self):
        result = derive_hicache_accounting(
            prompt_tokens=100,
            l1_tokens=20,
            l2_tokens=30,
            l3_tokens=40,
            durable_reusable_prefix_tokens=90,
        )
        self.assertEqual(result["newly_prefilled_tokens"], 10)
        self.assertEqual(result["avoidable_recompute_tokens"], 0)
        self.assertTrue(result["tier_conservation_valid"])

    def test_avoidable_recompute_vectors_and_unknown(self):
        for durable, expected in ((None, None), (0, 0), (100, 10), (70, 0)):
            result = derive_hicache_accounting(
                prompt_tokens=100,
                l1_tokens=20,
                l2_tokens=30,
                l3_tokens=40,
                durable_reusable_prefix_tokens=durable,
            )
            self.assertEqual(result["avoidable_recompute_tokens"], expected)

    def test_durable_unknown_is_partial(self):
        req = SimpleNamespace(
            origin_input_ids=[1] * 10,
            cached_tokens_device=2,
            cached_tokens_host=3,
            cached_tokens_storage=4,
            hicache_durable_reusable_prefix_tokens=None,
            hicache_enqueue_mono_ns=1,
            hicache_prefetch_issue_mono_ns=2,
            hicache_storage_query_start_mono_ns=None,
            hicache_storage_query_end_mono_ns=None,
            hicache_ready_mono_ns=4,
            hicache_admission_mono_ns=5,
            hicache_prefill_finish_mono_ns=6,
            hicache_rh_eligible=True,
            hicache_prefetch_last_origin=None,
            hicache_prefetch_last_attempt_id=None,
            hicache_completed_kv_tokens=None,
            hicache_required_aux_pools=[],
            hicache_completed_aux_units=None,
            hicache_hybrid_restore_complete=None,
            hicache_invalid_reason=None,
        )
        telemetry = build_hicache_telemetry(req)
        self.assertEqual(telemetry["partial_reason"], "durable_unknown")
        self.assertIsNone(telemetry["invalid_reason"])
        self.assertEqual(telemetry["_outcome"], "partial")

    def test_total_durable_prefix_includes_matched_prefix(self):
        result = derive_hicache_accounting(
            prompt_tokens=100,
            l1_tokens=20,
            l2_tokens=10,
            l3_tokens=20,
            durable_reusable_prefix_tokens=70,
        )
        self.assertEqual(result["avoidable_recompute_tokens"], 20)

    def test_generation_mismatch_is_invalid(self):
        req = SimpleNamespace(
            origin_input_ids=[1],
            cached_tokens_device=0,
            cached_tokens_host=0,
            cached_tokens_storage=0,
            hicache_durable_reusable_prefix_tokens=None,
            hicache_telemetry_session_generation=1,
            session_generation=2,
            hicache_invalid_reason=None,
        )
        telemetry = build_hicache_telemetry(req)
        self.assertEqual(telemetry["invalid_reason"], "generation_mismatch")
        self.assertEqual(telemetry["_outcome"], "invalid")

    def test_failure_isolation(self):
        req = SimpleNamespace(
            finished=lambda: True,
            hicache_prometheus_observed=False,
            origin_input_ids=[1],
            cached_tokens_device=0,
            cached_tokens_host=0,
            cached_tokens_storage=0,
            hicache_durable_reusable_prefix_tokens=0,
            hicache_telemetry_session_generation=None,
            session_generation=None,
            hicache_invalid_reason=None,
        )
        class RejectingCollector:
            def observe_hicache_telemetry(self, telemetry):
                raise RuntimeError("collector")

        telemetry = build_and_observe_hicache_telemetry(
            req, RejectingCollector()
        )
        self.assertIsNotNone(telemetry)
        self.assertFalse(req.hicache_prometheus_observed)

    def test_timestamp_null_and_order_semantics(self):
        req = SimpleNamespace(
            origin_input_ids=[1] * 10,
            cached_tokens_device=2,
            cached_tokens_host=3,
            cached_tokens_storage=4,
            hicache_durable_reusable_prefix_tokens=None,
            hicache_enqueue_mono_ns=1,
            hicache_prefetch_issue_mono_ns=2,
            hicache_storage_query_start_mono_ns=None,
            hicache_storage_query_end_mono_ns=None,
            hicache_ready_mono_ns=4,
            hicache_admission_mono_ns=3,
            hicache_prefill_finish_mono_ns=5,
            hicache_telemetry_enabled=True,
            hicache_rh_eligible=True,
            hicache_prefetch_last_origin=None,
            hicache_prefetch_last_attempt_id=None,
            hicache_completed_kv_tokens=None,
            hicache_required_aux_pools=[],
            hicache_completed_aux_units=None,
            hicache_hybrid_restore_complete=None,
            hicache_invalid_reason=None,
        )
        telemetry = build_hicache_telemetry(req)
        self.assertIsNone(telemetry["rh_prefetch_lead_seconds"])
        self.assertIsNone(telemetry["rh_ready_slack_seconds"])
        self.assertEqual(telemetry["invalid_reason"], "clock_order")
        self.assertEqual(telemetry["_outcome"], "invalid")

    def test_invalid_partition_is_not_clamped(self):
        result = derive_hicache_accounting(
            prompt_tokens=10,
            l1_tokens=8,
            l2_tokens=4,
            l3_tokens=0,
            durable_reusable_prefix_tokens=10,
        )
        self.assertFalse(result["tier_conservation_valid"])
        self.assertIsNone(result["newly_prefilled_tokens"])
        self.assertIsNone(result["avoidable_recompute_tokens"])

    def test_matched_prefix_requires_complete_proof(self):
        proof = {
            "request_lineage": "r",
            "prefetch_attempt_id": "a",
            "session_generation": 1,
            "prompt_hash_lineage": "h",
            "selected_anchor": "n",
            "matched_token_boundary": 8,
            "required_component_set": ("kv", "mamba"),
            "per_component_durable_boundary": {"kv": 8, "mamba": 4},
            "proof_kind": "joined_restore",
            "proof_observation_point": "finalizer",
        }
        self.assertEqual(
            _MODULE.classify_matched_prefix_l3(proof)["matched_prefix_authority"],
            "unknown",
        )
        proof["per_component_durable_boundary"]["mamba"] = 8
        self.assertEqual(
            _MODULE.classify_matched_prefix_l3(proof)["matched_prefix_l3_tokens"],
            8,
        )

    def test_public_schema_has_outcome_and_reason_fields(self):
        result = public_hicache_telemetry(
            {"schema": "hicache_request.v1", "outcome": "partial", "partial_reason": "durable_unknown", "invalid_reason": None}
        )
        self.assertEqual(result["outcome"], "partial")
        self.assertEqual(result["partial_reason"], "durable_unknown")
        self.assertIsNone(result["invalid_reason"])

    def test_schema_strips_internal_outcome(self):
        result = public_hicache_telemetry({"schema": "hicache_request.v1", "_outcome": "complete"})
        self.assertEqual(result, {"schema": "hicache_request.v1"})


class TestHiCacheMetricContract(unittest.TestCase):
    def test_fixed_enums_and_buckets(self):
        self.assertEqual(
            HICACHE_PROMPT_SOURCES,
            ("l1", "l2", "l3", "newly_prefilled"),
        )
        self.assertEqual(len(HICACHE_STAGE_NAMES), 4)
        self.assertEqual(HICACHE_LATENCY_BUCKETS[-1], 80)


if __name__ == "__main__":
    unittest.main()
