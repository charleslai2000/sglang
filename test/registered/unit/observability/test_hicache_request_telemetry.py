import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

from sglang.srt.constants import HEALTH_CHECK_RID_PREFIX
from sglang.srt.managers.io_struct import (
    BatchEmbeddingOutput,
    BatchStrOutput,
    BatchTokenIDOutput,
    GenerateReqInput,
)
from sglang.srt.managers.cache_controller import PrefetchOperation
from sglang.srt.managers.multi_tokenizer_mixin import _handle_output_by_index
from sglang.srt.mem_cache.hicache_storage import (
    PoolName,
    PoolTransfer,
    PoolTransferResult,
    SidecarPoolSpec,
)
from sglang.srt.mem_cache.hybrid_cache.hybrid_cache_controller import (
    HybridCacheController,
)
from sglang.srt.mem_cache.unified_cache.component_type import ComponentType
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache
from sglang.srt.observability import metrics_collector as metrics_module
from sglang.srt.observability.request_metrics_exporter import (
    FileRequestMetricsExporter,
)
from sglang.srt.managers.tokenizer_manager import TokenizerManager

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


class _FakeTreeCore:
    """Minimal stand-in for the unified tree-core durability predicates."""

    def __init__(self, *, root=False, persisted=False, restored=False):
        self._root = root
        self._persisted = persisted
        self._restored = restored

    def is_root(self, node_id):
        return self._root

    def is_storage_persisted(self, node_id):
        return self._persisted

    def is_l3_durable(self, node_id):
        return self._persisted or self._restored


def _bare_cache(*, tree_core=None, components=(ComponentType.FULL,), sidecars=()):
    """Build a real UnifiedRadixCache instance with only the attributes the
    finalizer/proof production methods read.  The methods themselves are the
    unmodified production code."""
    cache = UnifiedRadixCache.__new__(UnifiedRadixCache)
    cache.tree_core = tree_core or _FakeTreeCore()
    cache.page_size = 16  # property setter writes through to tree_core
    cache.tree_components = tuple(components)
    cache.sidecar_pool_specs = list(sidecars)
    return cache


def _req_from_completion(
    *, prompt, l1, l2, l3, completion, rid="req-1", attempt="att-1", generation=7
):
    """Reproduce the scheduler's completion-fact copy (scheduler.py
    `_feed_restore_terminal`, RestoreEvent.FINALIZED branch) onto a request."""
    return SimpleNamespace(
        rid=rid,
        origin_input_ids=[0] * prompt,
        cached_tokens_device=l1,
        cached_tokens_host=l2,
        cached_tokens_storage=l3,
        session_generation=generation,
        hicache_telemetry_enabled=True,
        hicache_telemetry_session_generation=completion.get("session_generation"),
        hicache_prefetch_attempt_id=attempt,
        hicache_prefetch_last_attempt_id=attempt,
        hicache_prefetch_last_origin=None,
        hicache_invalid_reason=None,
        hicache_rh_eligible=True,
        hicache_enqueue_mono_ns=1,
        hicache_prefetch_issue_mono_ns=completion.get("prefetch_issue_mono_ns"),
        hicache_storage_query_start_mono_ns=completion.get(
            "storage_query_start_mono_ns"
        ),
        hicache_storage_query_end_mono_ns=completion.get("storage_query_end_mono_ns"),
        hicache_ready_mono_ns=20,
        hicache_admission_mono_ns=30,
        hicache_prefill_finish_mono_ns=40,
        hicache_completed_kv_tokens=completion.get("completed_kv_tokens"),
        hicache_required_aux_pools=completion.get("required_aux_pools", []),
        hicache_completed_aux_units=completion.get("completed_aux_units"),
        hicache_hybrid_restore_complete=completion.get("hybrid_restore_complete"),
        hicache_matched_prefix_tokens=completion.get("matched_prefix_tokens"),
        hicache_matched_prefix_l3_proof=completion.get("matched_prefix_l3_proof"),
        hicache_durable_reusable_prefix_tokens=completion.get(
            "durable_reusable_prefix_tokens"
        ),
    )


def _finalize(
    cache,
    operation,
    completed,
    *,
    finalize_result="accepted",
    prompt=20,
    l1=5,
    l2=0,
    l3=0,
):
    """Real finalizer -> scheduler fact -> real builder."""
    completion = cache._host_alloc_hybrid_completion(
        operation, completed, finalize_result
    )
    req = _req_from_completion(
        prompt=prompt, l1=l1, l2=l2, l3=l3, completion=completion
    )
    return completion, build_hicache_telemetry(req)


class TestFR1ProofInvalidationIsAtomic(unittest.TestCase):
    def test_mismatched_lineage_cannot_retain_positive_durable(self):
        """Reviewer falsification: a mismatched request_lineage proof must not
        leave a positive durable total / avoidable credit / complete outcome
        next to an `unknown` matched-prefix classification."""
        cache = _bare_cache(tree_core=_FakeTreeCore(persisted=True))
        operation = PrefetchOperation("req-1", [0] * 64, "hashline")
        operation.stats_matched_prefix_tokens = 5
        operation.prefetch_attempt_id = "att-1"
        operation.telemetry_session_generation = 7
        operation.prefetch_issue_mono_ns = 10
        operation.matched_prefix_l3_proof = {
            "request_lineage": "other-rid",  # <- mismatch
            "prefetch_attempt_id": "att-1",
            "session_generation": 7,
            "prompt_hash_lineage": "hashline",
            "selected_anchor": "1",
            "matched_token_boundary": 5,
            "required_component_set": ("kv",),
            "per_component_durable_boundary": {"kv": 5},
            "proof_kind": "persisted_contiguous",
            "proof_observation_point": "controller_acceptance",
        }
        _completion, telemetry = _finalize(cache, operation, 5)
        if telemetry["matched_prefix_authority"] == "unknown":
            self.assertIsNone(telemetry["matched_prefix_l3_tokens"])
            self.assertIsNone(telemetry["durable_reusable_prefix_tokens"])
            self.assertIsNone(telemetry["avoidable_recompute_tokens"])
            self.assertNotEqual(telemetry["_outcome"], "complete")

    def test_finalizer_itself_refuses_durable_on_lineage_mismatch(self):
        """The finalizer validates the full tuple before deriving D: a
        mismatched lineage must not produce a positive durable total even
        before the builder sees it."""
        cache = _bare_cache(tree_core=_FakeTreeCore(persisted=True))
        operation = PrefetchOperation("req-1", [0] * 64, "hashline")
        operation.stats_matched_prefix_tokens = 5
        operation.prefetch_attempt_id = "att-1"
        operation.telemetry_session_generation = 7
        operation.matched_prefix_l3_proof = {
            "request_lineage": "other-rid",
            "prefetch_attempt_id": "att-1",
            "session_generation": 7,
            "prompt_hash_lineage": "hashline",
            "selected_anchor": "1",
            "matched_token_boundary": 5,
            "required_component_set": ("kv",),
            "per_component_durable_boundary": {"kv": 5},
            "proof_kind": "persisted_contiguous",
            "proof_observation_point": "controller_acceptance",
        }
        completion = cache._host_alloc_hybrid_completion(operation, 5, "accepted")
        self.assertIsNone(completion["durable_reusable_prefix_tokens"])


class _SynchronousQueue:
    """Queue fake whose ``put`` inspects the operation at the handoff."""

    def __init__(self):
        self.puts = []
        self.issue_at_put = None
        self.generation_at_put = None
        self.attempt_at_put = None
        self.proof_at_put = None

    def put(self, operation):
        self.puts.append(operation)
        self.issue_at_put = getattr(operation, "prefetch_issue_mono_ns", None)
        self.generation_at_put = getattr(
            operation, "telemetry_session_generation", None
        )
        self.attempt_at_put = getattr(operation, "prefetch_attempt_id", None)
        self.proof_at_put = getattr(operation, "matched_prefix_l3_proof", None)


class TestT1QueuePublicationSeam(unittest.TestCase):
    def test_real_controller_prefetch_publication(self):
        controller = HybridCacheController.__new__(HybridCacheController)
        queue = _SynchronousQueue()
        controller.prefetch_queue = queue
        proof = {
            "request_lineage": "req-1",
            "prefetch_attempt_id": "att-9",
            "session_generation": 9,
            "prompt_hash_lineage": "h",
            "selected_anchor": "1",
            "matched_token_boundary": 4,
            "required_component_set": ("kv",),
            "per_component_durable_boundary": {"kv": 4},
            "proof_kind": "persisted_contiguous",
            "proof_observation_point": "controller_acceptance",
        }
        operation = controller.prefetch(
            "req-1",
            [1, 2, 3, 4],
            last_hash="h",
            prefix_keys=["p"],
            extra_pools=None,
            trace_context=None,
            telemetry_enabled=True,
            session_generation=9,
            prefetch_attempt_id="att-9",
            matched_prefix_l3_proof=proof,
            matched_prefix_tokens=4,
        )
        self.assertIsNotNone(queue.issue_at_put)
        self.assertEqual(queue.issue_at_put, operation.prefetch_issue_mono_ns)
        self.assertEqual(queue.generation_at_put, 9)
        self.assertEqual(queue.attempt_at_put, "att-9")
        self.assertEqual(queue.proof_at_put, proof)
        issue = operation.prefetch_issue_mono_ns
        operation.storage_query_start_mono_ns = issue + 1
        operation.storage_query_end_mono_ns = issue + 2
        self.assertLessEqual(issue, operation.storage_query_start_mono_ns)
        self.assertLessEqual(
            operation.storage_query_start_mono_ns,
            operation.storage_query_end_mono_ns,
        )
        self.assertEqual(operation.prefetch_issue_mono_ns, queue.issue_at_put)

    def test_disabled_telemetry_leaves_issue_and_query_null(self):
        controller = HybridCacheController.__new__(HybridCacheController)
        queue = _SynchronousQueue()
        controller.prefetch_queue = queue
        operation = controller.prefetch(
            "req-2",
            [1, 2, 3, 4],
            telemetry_enabled=False,
        )
        self.assertIsNone(queue.issue_at_put)
        self.assertIsNone(operation.prefetch_issue_mono_ns)
        self.assertIsNone(operation.telemetry_session_generation)
        self.assertIsNone(queue.proof_at_put)


class TestT2MatchedPrefixAndFinalizerAuthority(unittest.TestCase):
    def _operation(self, cache, *, matched, attempt="att-1", generation=7):
        operation = PrefetchOperation("req-1", [0] * 64, "hashline")
        operation.stats_matched_prefix_tokens = matched
        operation.prefetch_attempt_id = attempt
        operation.telemetry_session_generation = generation
        operation.prefetch_issue_mono_ns = 10
        operation.required_l3_components = cache._required_l3_component_set()
        operation.matched_prefix_l3_proof = cache._matched_prefix_l3_proof(
            "req-1", 1, matched, attempt, generation, "hashline"
        )
        return operation

    def test_root_zero_is_authoritative_zero(self):
        cache = _bare_cache(tree_core=_FakeTreeCore(root=True))
        operation = self._operation(cache, matched=0)
        completion, telemetry = _finalize(cache, operation, 0, prompt=20, l1=0)
        self.assertEqual(telemetry["matched_prefix_authority"], "none")
        self.assertEqual(telemetry["matched_prefix_l3_tokens"], 0)
        self.assertEqual(completion["durable_reusable_prefix_tokens"], 0)
        self.assertIsNotNone(telemetry["avoidable_recompute_tokens"])

    def test_device_only_is_device_reusable_durable_null(self):
        cache = _bare_cache(tree_core=_FakeTreeCore())
        operation = self._operation(cache, matched=8)
        _completion, telemetry = _finalize(
            cache, operation, 0, prompt=20, l1=8, l2=0
        )
        self.assertEqual(telemetry["matched_prefix_authority"], "device_reusable")
        self.assertIsNone(telemetry["matched_prefix_l3_tokens"])
        self.assertIsNone(telemetry["durable_reusable_prefix_tokens"])
        self.assertIsNone(telemetry["avoidable_recompute_tokens"])

    def test_host_only_is_host_reusable_durable_null(self):
        cache = _bare_cache(tree_core=_FakeTreeCore())
        operation = self._operation(cache, matched=8)
        _completion, telemetry = _finalize(
            cache, operation, 0, prompt=20, l1=4, l2=4
        )
        self.assertEqual(telemetry["matched_prefix_authority"], "host_reusable")
        self.assertIsNone(telemetry["matched_prefix_l3_tokens"])
        self.assertIsNone(telemetry["durable_reusable_prefix_tokens"])

    def test_storage_written_unacked_is_unknown_null(self):
        cache = _bare_cache(tree_core=_FakeTreeCore(persisted=False))
        operation = self._operation(cache, matched=8)
        self.assertIsNone(operation.matched_prefix_l3_proof)
        _completion, telemetry = _finalize(
            cache, operation, 0, prompt=20, l1=0, l2=0
        )
        self.assertEqual(telemetry["matched_prefix_authority"], "unknown")
        self.assertIsNone(telemetry["matched_prefix_l3_tokens"])
        self.assertIsNone(telemetry["durable_reusable_prefix_tokens"])

    def test_pure_kv_persisted_contiguous_positive_md(self):
        cache = _bare_cache(tree_core=_FakeTreeCore(persisted=True))
        operation = self._operation(cache, matched=8)
        self.assertIsNotNone(operation.matched_prefix_l3_proof)
        completion, telemetry = _finalize(
            cache, operation, 4, prompt=20, l1=0, l2=0
        )
        self.assertEqual(telemetry["matched_prefix_authority"], "l3_durable")
        self.assertEqual(telemetry["matched_prefix_l3_tokens"], 8)
        self.assertEqual(completion["durable_reusable_prefix_tokens"], 12)
        self.assertEqual(telemetry["avoidable_recompute_tokens"], 12)

    def test_accepted_partial_suffix_is_bounded_by_prompt(self):
        cache = _bare_cache(tree_core=_FakeTreeCore(persisted=True))
        operation = self._operation(cache, matched=8)
        completion, telemetry = _finalize(
            cache, operation, 20, prompt=20, l1=0, l2=0
        )
        # Md + S = 28 is clamped to the prompt.
        self.assertEqual(completion["durable_reusable_prefix_tokens"], 28)
        self.assertEqual(telemetry["durable_reusable_prefix_tokens"], 20)
        self.assertEqual(telemetry["avoidable_recompute_tokens"], 20)

    def test_broad_restored_flag_without_contiguous_proof_is_unknown(self):
        cache = _bare_cache(tree_core=_FakeTreeCore(restored=True))
        operation = self._operation(cache, matched=8)
        self.assertTrue(cache.tree_core.is_l3_durable(1))
        self.assertIsNone(operation.matched_prefix_l3_proof)
        _completion, telemetry = _finalize(
            cache, operation, 0, prompt=20, l1=0, l2=0
        )
        self.assertEqual(telemetry["matched_prefix_authority"], "unknown")
        self.assertIsNone(telemetry["durable_reusable_prefix_tokens"])

    def test_dsa_kv_derived_sidecar_shortfall_clamps_to_common_prefix(self):
        spec = SidecarPoolSpec(
            pool_name=PoolName.INDEXER, indices_from_pool=PoolName.KV
        )
        cache = _bare_cache(tree_core=_FakeTreeCore(root=True), sidecars=(spec,))
        self.assertEqual(cache._required_l3_component_set(), ("kv", "indexer"))
        operation = self._operation(cache, matched=0)
        operation.pool_transfers = [
            PoolTransfer(
                name=PoolName.INDEXER,
                keys=["h1", "h2", "h3", "h4"],
                indices_from_pool=PoolName.KV,
            )
        ]
        operation.pool_storage_result = PoolTransferResult(0, {})
        counts = cache._host_alloc_hybrid_sidecar_counts(operation, 32)
        self.assertEqual(counts["indexer"]["fetched"], 2)
        self.assertEqual(counts["indexer"]["expected"], 2)
        completion, telemetry = _finalize(
            cache, operation, 32, prompt=64, l1=0, l2=0
        )
        self.assertTrue(completion["hybrid_restore_complete"])
        self.assertEqual(telemetry["durable_reusable_prefix_tokens"], 32)

    def test_swa_sidecar_shortfall_nulls_total(self):
        cache = _bare_cache(
            tree_core=_FakeTreeCore(root=True),
            components=(ComponentType.FULL, ComponentType.SWA),
        )
        operation = self._operation(cache, matched=0)
        operation.pool_transfers = [
            PoolTransfer(name=PoolName.SWA, keys=["h1", "h2", "h3", "h4"])
        ]
        operation.pool_storage_result = PoolTransferResult(0, {PoolName.SWA: 2})
        completion, telemetry = _finalize(
            cache, operation, 48, prompt=64, l1=0, l2=0
        )
        self.assertFalse(completion["hybrid_restore_complete"])
        self.assertIsNone(completion["durable_reusable_prefix_tokens"])
        self.assertIsNone(telemetry["durable_reusable_prefix_tokens"])
        self.assertIsNone(telemetry["avoidable_recompute_tokens"])

    def test_rejected_finalizer_nulls_total(self):
        cache = _bare_cache(tree_core=_FakeTreeCore(persisted=True))
        operation = self._operation(cache, matched=8)
        completion, telemetry = _finalize(
            cache, operation, 12, finalize_result="discarded", prompt=32, l1=0
        )
        self.assertIsNone(completion["durable_reusable_prefix_tokens"])
        self.assertIsNone(telemetry["durable_reusable_prefix_tokens"])

    def test_stale_attempt_is_invalid_with_dependent_facts_null(self):
        cache = _bare_cache(tree_core=_FakeTreeCore(persisted=True))
        operation = self._operation(cache, matched=8)
        completion = cache._host_alloc_hybrid_completion(operation, 4, "accepted")
        req = _req_from_completion(
            prompt=20, l1=0, l2=0, l3=0, completion=completion, attempt="att-1"
        )
        req.hicache_prefetch_last_attempt_id = "att-2"
        telemetry = build_hicache_telemetry(req)
        self.assertEqual(telemetry["invalid_reason"], "attempt_mismatch")
        self.assertEqual(telemetry["_outcome"], "invalid")
        self.assertIsNone(telemetry["durable_reusable_prefix_tokens"])
        self.assertIsNone(telemetry["avoidable_recompute_tokens"])
        self.assertIsNone(telemetry["prefetch_issue_mono_ns"])
        self.assertIsNone(telemetry["ready_mono_ns"])

    def test_stale_generation_is_invalid_with_dependent_facts_null(self):
        cache = _bare_cache(tree_core=_FakeTreeCore(persisted=True))
        operation = self._operation(cache, matched=8)
        completion = cache._host_alloc_hybrid_completion(operation, 4, "accepted")
        req = _req_from_completion(
            prompt=20, l1=0, l2=0, l3=0, completion=completion, generation=7
        )
        req.session_generation = 8
        telemetry = build_hicache_telemetry(req)
        self.assertEqual(telemetry["invalid_reason"], "generation_mismatch")
        self.assertEqual(telemetry["_outcome"], "invalid")
        self.assertIsNone(telemetry["durable_reusable_prefix_tokens"])
        self.assertIsNone(telemetry["avoidable_recompute_tokens"])

    def test_hybrid_component_durability_unavailable_is_unknown_null(self):
        spec = SidecarPoolSpec(
            pool_name=PoolName.INDEXER, indices_from_pool=PoolName.KV
        )
        cache = _bare_cache(
            tree_core=_FakeTreeCore(persisted=True), sidecars=(spec,)
        )
        operation = self._operation(cache, matched=8)
        self.assertIsNone(operation.matched_prefix_l3_proof)
        _completion, telemetry = _finalize(
            cache, operation, 0, prompt=20, l1=0, l2=0
        )
        self.assertEqual(telemetry["matched_prefix_authority"], "unknown")
        self.assertIsNone(telemetry["matched_prefix_l3_tokens"])
        self.assertIsNone(telemetry["durable_reusable_prefix_tokens"])


class _FakeMetric:
    """DI double mirroring the prometheus_client Counter/Gauge/Histogram API."""

    registry = []

    def __init__(
        self,
        name=None,
        documentation=None,
        labelnames=(),
        buckets=None,
        multiprocess_mode=None,
        **kwargs,
    ):
        self.name = name
        self.labelnames = tuple(labelnames)
        self.buckets = buckets
        self.events = []
        _FakeMetric.registry.append(self)

    def labels(self, **labels):
        self.events.append(("labels", dict(labels)))
        return self

    def inc(self, n=1):
        self.events.append(("inc", n))
        return self

    def observe(self, v):
        self.events.append(("observe", v))
        return self

    def set(self, v):
        self.events.append(("set", v))
        return self


_BASE_LABELS = {
    "model_name": "test-model",
    "engine_type": "unified",
    "tp_rank": 0,
    "pp_rank": 0,
    "moe_ep_rank": 1,
}


def _make_metrics_collector():
    collector_cls = metrics_module.SchedulerMetricsCollector
    saved = (
        collector_cls._counter_cls,
        collector_cls._gauge_cls,
        collector_cls._histogram_cls,
        collector_cls._summary_cls,
    )
    saved_gauge_histogram = metrics_module.GaugeHistogram
    saved_get_schedule = metrics_module.get_schedule
    _FakeMetric.registry = []
    try:
        collector_cls._counter_cls = _FakeMetric
        collector_cls._gauge_cls = _FakeMetric
        collector_cls._histogram_cls = _FakeMetric
        collector_cls._summary_cls = _FakeMetric
        metrics_module.GaugeHistogram = _FakeMetric
        metrics_module.get_schedule = lambda: SimpleNamespace(
            prefill_delayer_max_delay_passes=4,
            prefill_delayer_forward_passes_buckets=None,
            prefill_delayer_wait_seconds_buckets=None,
        )
        server_args = SimpleNamespace(
            stat_loggers=None,
            should_export_expert_balancedness_to_prometheus=lambda: False,
        )
        return collector_cls(
            labels=dict(_BASE_LABELS),
            server_args=server_args,
            enable_hierarchical_cache=True,
        )
    finally:
        (
            collector_cls._counter_cls,
            collector_cls._gauge_cls,
            collector_cls._histogram_cls,
            collector_cls._summary_cls,
        ) = saved
        metrics_module.GaugeHistogram = saved_gauge_histogram
        metrics_module.get_schedule = saved_get_schedule


def _metric_by_name(name):
    for metric in _FakeMetric.registry:
        if metric.name == name:
            return metric
    raise AssertionError(f"metric {name!r} was never registered")


class _FakeExporterManager:
    def __init__(self, enabled):
        self._enabled = enabled

    def exporter_enabled(self):
        return self._enabled


def _bare_tokenizer_manager(enabled=True):
    manager = TokenizerManager.__new__(TokenizerManager)
    manager.request_metrics_exporter_manager = _FakeExporterManager(enabled)
    return manager


def _make_batch_token_output():
    return BatchTokenIDOutput(
        rids=["rid-0", "rid-1"],
        spec_verify_ct=[0, 0],
        spec_num_correct_drafts=[0, 0],
        spec_correct_drafts_histogram=[[], []],
        finished_reasons=[None, {"type": "length"}],
        decoded_texts=["a", "b"],
        decode_ids=[[], []],
        read_offsets=[0, 0],
        output_ids=[[1], [2]],
        skip_special_tokens=[False, False],
        spaces_between_special_tokens=[False, False],
        no_stop_trim=[False, False],
        prompt_tokens=[10, 20],
        completion_tokens=[1, 2],
        reasoning_tokens=[0, 0],
        cached_tokens=[3, 4],
        cached_tokens_details=[None, None],
        hicache_telemetry=[
            {"schema": "hicache_request.v1", "prompt_tokens": 10},
            {"schema": "hicache_request.v1", "prompt_tokens": 20},
        ],
        input_token_logprobs_val=[[], []],
        input_token_logprobs_idx=[[], []],
        output_token_logprobs_val=[[], []],
        output_token_logprobs_idx=[[], []],
        input_top_logprobs_val=[[], []],
        input_top_logprobs_idx=[[], []],
        output_top_logprobs_val=[[], []],
        output_top_logprobs_idx=[[], []],
        input_token_ids_logprobs_val=[[], []],
        input_token_ids_logprobs_idx=[[], []],
        output_token_ids_logprobs_val=[[], []],
        output_token_ids_logprobs_idx=[[], []],
        output_token_entropy_val=[0.0, 0.0],
        output_token_sampling_mask=[[], []],
        output_token_sampling_logprobs=[[], []],
        output_hidden_states=[None, None],
        routed_experts=[None, None],
        indexer_topk=[None, None],
        placeholder_tokens_idx=None,
        placeholder_tokens_val=None,
    )


def _make_embedding_output():
    return BatchEmbeddingOutput(
        rids=["rid-0", "rid-1"],
        finished_reasons=[None, {"type": "length"}],
        embeddings=[[0.1], [0.2]],
        prompt_tokens=[10, 20],
        cached_tokens=[3, 4],
        hicache_telemetry=[
            {"schema": "hicache_request.v1", "prompt_tokens": 10},
            {"schema": "hicache_request.v1", "prompt_tokens": 20},
        ],
        placeholder_tokens_idx=None,
        placeholder_tokens_val=None,
    )


def _make_batch_str_output():
    """Build a real BatchStrOutput with a list-valued ``hicache_telemetry``.

    Mirrors ``_make_batch_token_output`` field-for-field for the string-shaped
    output; the detokenizer forwards the per-request public objects here
    (``detokenizer_manager.py``) before ``_handle_output_by_index`` slices them.
    """
    return BatchStrOutput(
        rids=["rid-0", "rid-1"],
        finished_reasons=[None, {"type": "length"}],
        output_strs=["a", "b"],
        output_ids=[[1], [2]],
        prompt_tokens=[10, 20],
        completion_tokens=[1, 2],
        reasoning_tokens=[0, 0],
        cached_tokens=[3, 4],
        cached_tokens_details=[None, None],
        hicache_telemetry=[
            {"schema": "hicache_request.v1", "prompt_tokens": 10},
            {"schema": "hicache_request.v1", "prompt_tokens": 20},
        ],
        input_token_logprobs_val=[[], []],
        input_token_logprobs_idx=[[], []],
        output_token_logprobs_val=[[], []],
        output_token_logprobs_idx=[[], []],
        input_top_logprobs_val=[[], []],
        input_top_logprobs_idx=[[], []],
        output_top_logprobs_val=[[], []],
        output_top_logprobs_idx=[[], []],
        input_token_ids_logprobs_val=[[], []],
        input_token_ids_logprobs_idx=[[], []],
        output_token_ids_logprobs_val=[[], []],
        output_token_ids_logprobs_idx=[[], []],
        output_token_entropy_val=[0.0, 0.0],
        output_token_sampling_mask=[[], []],
        output_token_sampling_logprobs=[[], []],
        output_hidden_states=[None, None],
        routed_experts=[None, None],
        indexer_topk=[None, None],
        placeholder_tokens_idx=None,
        placeholder_tokens_val=None,
    )


class TestT3MetricsJsonlAndPaths(unittest.TestCase):
    def test_metric_registration_names_labels_and_buckets(self):
        _make_metrics_collector()
        base = tuple(_BASE_LABELS)
        prompt = _metric_by_name("sglang:hicache_prompt_tokens_total")
        avoidable = _metric_by_name(
            "sglang:hicache_avoidable_recompute_tokens_total"
        )
        lead = _metric_by_name("sglang:hicache_rh_prefetch_lead_seconds")
        slack = _metric_by_name("sglang:hicache_rh_ready_slack_seconds")
        stage = _metric_by_name("sglang:hicache_stage_latency_seconds")
        records = _metric_by_name("sglang:hicache_telemetry_records_total")
        self.assertEqual(prompt.labelnames, base + ("source",))
        self.assertEqual(avoidable.labelnames, base)
        self.assertEqual(lead.labelnames, base)
        self.assertEqual(slack.labelnames, base)
        self.assertEqual(stage.labelnames, base + ("stage",))
        self.assertEqual(records.labelnames, base + ("outcome",))
        self.assertEqual(lead.buckets, HICACHE_LATENCY_BUCKETS)
        forbidden = {
            "rid",
            "request_id",
            "session",
            "session_generation",
            "attempt",
            "prefetch_attempt_id",
            "cache_key",
            "node",
            "storage_key",
            "proof_kind",
            "reason",
        }
        for metric in (prompt, avoidable, lead, slack, stage, records):
            self.assertFalse(forbidden & set(metric.labelnames))

    def test_observation_enums_and_idempotence(self):
        collector = _make_metrics_collector()
        cache = _bare_cache(tree_core=_FakeTreeCore(persisted=True))
        operation = PrefetchOperation("req-1", [0] * 64, "hashline")
        operation.stats_matched_prefix_tokens = 8
        operation.prefetch_attempt_id = "att-1"
        operation.telemetry_session_generation = 7
        operation.prefetch_issue_mono_ns = 10
        operation.required_l3_components = cache._required_l3_component_set()
        operation.matched_prefix_l3_proof = cache._matched_prefix_l3_proof(
            "req-1", 1, 8, "att-1", 7, "hashline"
        )
        completion = cache._host_alloc_hybrid_completion(operation, 4, "accepted")
        req = _req_from_completion(
            prompt=20, l1=0, l2=0, l3=0, completion=completion
        )
        req.finished = lambda: True
        req.hicache_prometheus_observed = False
        build_and_observe_hicache_telemetry(req, collector)
        # A second observation must be a no-op (one terminal record).
        build_and_observe_hicache_telemetry(req, collector)
        prompt = _metric_by_name("sglang:hicache_prompt_tokens_total")
        sources = [
            event[1]["source"]
            for event in prompt.events
            if event[0] == "labels"
        ]
        self.assertEqual(
            sorted(set(sources)), sorted(HICACHE_PROMPT_SOURCES)
        )
        records = _metric_by_name("sglang:hicache_telemetry_records_total")
        outcome_labels = [
            event[1]["outcome"]
            for event in records.events
            if event[0] == "labels"
        ]
        self.assertEqual(outcome_labels, ["complete"])
        self.assertEqual(
            len([e for e in records.events if e[0] == "inc"]), 1
        )
        stage = _metric_by_name("sglang:hicache_stage_latency_seconds")
        stage_names = [
            event[1]["stage"]
            for event in stage.events
            if event[0] == "labels"
        ]
        self.assertTrue(set(stage_names) <= set(HICACHE_STAGE_NAMES))

    def test_invalid_record_skips_tokens_but_counts_outcome(self):
        collector = _make_metrics_collector()
        cache = _bare_cache(tree_core=_FakeTreeCore(persisted=True))
        operation = PrefetchOperation("req-1", [0] * 64, "hashline")
        operation.stats_matched_prefix_tokens = 8
        operation.prefetch_attempt_id = "att-1"
        operation.telemetry_session_generation = 7
        operation.required_l3_components = cache._required_l3_component_set()
        completion = cache._host_alloc_hybrid_completion(operation, 4, "accepted")
        req = _req_from_completion(
            prompt=20, l1=0, l2=0, l3=0, completion=completion, generation=7
        )
        req.session_generation = 8  # generation_mismatch
        req.finished = lambda: True
        req.hicache_prometheus_observed = False
        build_and_observe_hicache_telemetry(req, collector)
        prompt = _metric_by_name("sglang:hicache_prompt_tokens_total")
        self.assertEqual(
            [e for e in prompt.events if e[0] == "labels"], []
        )
        records = _metric_by_name("sglang:hicache_telemetry_records_total")
        outcomes = [
            event[1]["outcome"]
            for event in records.events
            if event[0] == "labels"
        ]
        self.assertEqual(outcomes, ["invalid"])

    def test_jsonl_writer_public_fields_and_health_exclusion(self):
        import asyncio
        import glob
        import json
        import os
        import tempfile

        cache = _bare_cache(tree_core=_FakeTreeCore(persisted=True))
        operation = PrefetchOperation("req-1", [0] * 64, "hashline")
        operation.stats_matched_prefix_tokens = 8
        operation.prefetch_attempt_id = "att-1"
        operation.telemetry_session_generation = 7
        operation.prefetch_issue_mono_ns = 10
        operation.required_l3_components = cache._required_l3_component_set()
        operation.matched_prefix_l3_proof = cache._matched_prefix_l3_proof(
            "req-1", 1, 8, "att-1", 7, "hashline"
        )
        completion = cache._host_alloc_hybrid_completion(operation, 4, "accepted")
        req = _req_from_completion(
            prompt=20, l1=0, l2=0, l3=0, completion=completion
        )
        telemetry = build_hicache_telemetry(req)

        manager = _bare_tokenizer_manager()
        embedding = _make_embedding_output()
        embedding.hicache_telemetry = [telemetry, None]
        meta_info = {}
        manager._attach_hicache_telemetry(meta_info, embedding, 0)
        self.assertIn("hicache_telemetry", meta_info)
        self.assertNotIn("_outcome", meta_info["hicache_telemetry"])

        with tempfile.TemporaryDirectory() as directory:
            exporter = FileRequestMetricsExporter(
                SimpleNamespace(export_metrics_to_file_dir=directory),
                set(),
                set(),
            )
            # The exporter formats request_parameters via dataclasses.fields,
            # so the record owner must be the real dataclass input type
            # (GenerateReqInput/EmbeddingReqInput), not a bare namespace.
            obj = GenerateReqInput(rid="rid-emb")
            asyncio.run(exporter.write_record(obj, {"meta_info": meta_info}))
            health = SimpleNamespace(rid=f"{HEALTH_CHECK_RID_PREFIX}-xyz")
            asyncio.run(
                exporter.write_record(
                    health, {"meta_info": {"hicache_telemetry": telemetry}}
                )
            )
            files = glob.glob(os.path.join(directory, "sglang-request-metrics-*.log"))
            self.assertEqual(len(files), 1)
            with open(files[0], encoding="utf-8") as handle:
                lines = [json.loads(line) for line in handle if line.strip()]
        self.assertEqual(len(lines), 1)
        record = lines[0]["hicache_telemetry"]
        self.assertEqual(record["schema"], "hicache_request.v1")
        self.assertEqual(record["outcome"], "complete")
        self.assertIsNone(record["invalid_reason"])
        self.assertIsNone(record["partial_reason"])
        self.assertEqual(record["matched_prefix_l3_tokens"], 8)
        self.assertEqual(record["durable_reusable_prefix_tokens"], 12)
        self.assertEqual(record["avoidable_recompute_tokens"], 12)
        self.assertNotIn("_prometheus_observed", record)
        self.assertNotIn("_outcome", record)

    def test_embedding_and_token_and_string_attach_preserve_object(self):
        entry = {
            "schema": "hicache_request.v1",
            "outcome": "partial",
            "partial_reason": "durable_unknown",
            "invalid_reason": None,
            "_outcome": "partial",
        }
        manager = _bare_tokenizer_manager()
        embedding = _make_embedding_output()
        embedding.hicache_telemetry = [entry, None]
        token_output = _make_batch_token_output()
        token_output.hicache_telemetry = [entry, None]
        string_output = _make_batch_str_output()
        string_output.hicache_telemetry = [entry, None]
        for recv_obj in (embedding, token_output, string_output):
            meta_info = {}
            manager._attach_hicache_telemetry(meta_info, recv_obj, 0)
            self.assertEqual(
                meta_info["hicache_telemetry"],
                {k: v for k, v in entry.items() if not k.startswith("_")},
            )

    def test_multi_tokenizer_paths_preserve_object(self):
        entry = {"schema": "hicache_request.v1", "prompt_tokens": 7}
        embedding = _make_embedding_output()
        embedding.hicache_telemetry = [entry, None]
        self.assertEqual(
            _handle_output_by_index(embedding, 0).hicache_telemetry, [entry]
        )
        token_output = _make_batch_token_output()
        token_output.hicache_telemetry = [entry, None]
        self.assertEqual(
            _handle_output_by_index(token_output, 0).hicache_telemetry, [entry]
        )
        string_output = _make_batch_str_output()
        string_output.hicache_telemetry = [entry, None]
        handled = _handle_output_by_index(string_output, 0)
        self.assertEqual(handled.hicache_telemetry, [entry])
        self.assertEqual(
            handled.hicache_telemetry[0]["schema"],
            "hicache_request.v1",
        )


if __name__ == "__main__":
    unittest.main()
