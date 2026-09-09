"""Dependency-free RH contract checks for claim fencing and event joins."""

import ast
import logging
import re
import time
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Optional


ROOT = Path(__file__).parents[1]
SCHEDULER = ROOT / "python/sglang/srt/managers/scheduler.py"
UNIFIED_CACHE = ROOT / "python/sglang/srt/mem_cache/unified_radix_cache.py"


class _RestoreEvents:
    FINALIZED = object()
    DENIED_SHORT = object()
    REVOKED_TERMINATED = object()
    BACKUP_PENDING = object()
    DENIED_ALLOC = object()
    REVOKED_MISS = object()


class _RestoreStates:
    RESTORING = SimpleNamespace(name="RESTORING")
    READY = SimpleNamespace(name="READY")
    NONE = SimpleNamespace(name="NONE")
    WAIT_CAPACITY = SimpleNamespace(name="WAIT_CAPACITY")


def _load_methods(*names):
    module = ast.parse(SCHEDULER.read_text())
    cls = next(
        node
        for node in ast.walk(module)
        if isinstance(node, ast.ClassDef) and node.name == "Scheduler"
    )
    selected = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {
        "Req": object,
        "Optional": Optional,
        "HiCachePrefetchOrigin": object,
        "RestoreEvent": _RestoreEvents,
        "RestoreState": _RestoreStates,
        "logger": logging.getLogger(__name__),
        "time": time,
    }
    exec(compile(ast.Module(selected, []), str(SCHEDULER), "exec"), namespace)
    return namespace


def _load_unified_cache_methods(*names):
    module = ast.parse(UNIFIED_CACHE.read_text())
    cls = next(
        node
        for node in ast.walk(module)
        if isinstance(node, ast.ClassDef) and node.name == "UnifiedRadixCache"
    )
    selected = [
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {
        "Optional": Optional,
        "PoolName": SimpleNamespace(KV="kv"),
        "PrefetchOperation": object,
    }
    exec(compile(ast.Module(selected, []), str(UNIFIED_CACHE), "exec"), namespace)
    return namespace


class RHContractDependencyFreeTests(unittest.TestCase):
    def test_stale_release_cannot_clear_newer_claim(self):
        methods = _load_methods("_claim_prefetch", "_release_prefetch_claim")
        scheduler = SimpleNamespace()
        scheduler._claim_prefetch = MethodType(methods["_claim_prefetch"], scheduler)
        scheduler._release_prefetch_claim = MethodType(
            methods["_release_prefetch_claim"], scheduler
        )
        req = SimpleNamespace(rid="r1")
        first = scheduler._claim_prefetch(req, object())
        self.assertTrue(scheduler._release_prefetch_claim(req, first, "terminal"))
        second = scheduler._claim_prefetch(req, object())
        self.assertNotEqual(first, second)
        self.assertFalse(scheduler._release_prefetch_claim(req, first, "stale"))
        self.assertEqual(req.hicache_prefetch_active_attempt_id, second)
        self.assertTrue(scheduler._release_prefetch_claim(req, second, "terminal"))

    def test_required_event_join_fields_are_present(self):
        source = SCHEDULER.read_text()
        required = {
            "schema=rh_preadmission.v1": (
                "decision_id",
                "frontier_rank",
                "negative_cache_blocked",
                "physical_budget_limit_tokens",
                "speculative_budget_limit_tokens",
            ),
            "schema=rh_stage.v2": (
                "decision_id",
                "restore_state_before",
                "restore_state_after",
                "reason",
            ),
            "schema=rh_ready_host.v1": (
                "completed_kv_tokens",
                "required_aux_pools",
                "completed_aux_units",
                "ready_monotonic_ns",
            ),
            "schema=rh_admission.v2": (
                "rh_decision_id",
                "ready_host_observed",
                "can_run",
                "admission_monotonic_ns",
            ),
        }
        for schema, fields in required.items():
            self.assertIn(schema, source)
            for field in fields:
                self.assertIn(field, source)

    def test_issue_join_uses_returned_attempt_and_event_order(self):
        source = SCHEDULER.read_text()
        ready_pass = next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef)
            and node.name == "_ready_horizon_pass"
        )
        prefetch_line = next(
            node.lineno
            for node in ast.walk(ready_pass)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "_prefetch_kvcache"
        )
        issue_emit_lines = [
            node.lineno
            for node in ast.walk(ready_pass)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_emit_rh_decision"
        ]
        post_issue_emit = [line for line in issue_emit_lines if line > prefetch_line]
        self.assertTrue(post_issue_emit)
        post_issue_calls = [
            node
            for node in ast.walk(ready_pass)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_emit_rh_decision"
            and node.lineno > prefetch_line
        ]
        self.assertTrue(
            any(
                keyword.arg == "attempt_id"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "result_attempt_id"
                for call in post_issue_calls
                for keyword in call.keywords
            )
        )

        records = [
            "evt=rh_preadmission_decision schema=rh_preadmission.v1 rid=r1 decision=issue attempt_id=N",
            "evt=ready_stage schema=rh_stage.v2 rid=r1 attempt_id=N result=issued",
            "evt=ready_host schema=rh_ready_host.v1 rid=r1 attempt_id=N finalize_result=accepted",
            "evt=admission.v2 schema=rh_admission.v2 rid=r1 hicache_prefetch_attempt_id=N can_run=true",
        ]
        fields = {
            "rid": lambda record: re.search(r"\brid=(\S+)", record).group(1),
            "attempt": lambda record: re.search(
                r"\b(?:attempt_id|hicache_prefetch_attempt_id)=(\S+)", record
            ).group(1),
        }
        parsed = [
            (fields["rid"](record), fields["attempt"](record))
            for record in records
        ]
        self.assertEqual(parsed, [("r1", "N")] * 4)
        self.assertEqual(
            [
                "rh_preadmission.v1",
                "rh_stage.v2",
                "rh_ready_host.v1",
                "rh_admission.v2",
            ],
            [re.search(r"\bschema=(\S+)", record).group(1) for record in records],
        )

    def test_ready_host_aux_fields_come_from_finalizer_completion(self):
        methods = _load_unified_cache_methods(
            "_host_alloc_hybrid_sidecar_counts", "_host_alloc_hybrid_completion"
        )
        cache = SimpleNamespace()
        cache._host_alloc_hybrid_sidecar_counts = MethodType(
            methods["_host_alloc_hybrid_sidecar_counts"], cache
        )
        cache._host_alloc_hybrid_completion = MethodType(
            methods["_host_alloc_hybrid_completion"], cache
        )
        operation = SimpleNamespace(
            pool_transfers=[
                SimpleNamespace(
                    indices_from_pool="device",
                    name="mamba",
                    keys=["m0", "m1", "m2"],
                )
            ],
            pool_storage_result=SimpleNamespace(
                extra_pool_hit_pages={"mamba": 3}
            ),
        )

        completion = cache._host_alloc_hybrid_completion(
            operation, completed_tokens=8, finalize_result="accepted"
        )

        self.assertEqual(completion["completed_kv_tokens"], 8)
        self.assertEqual(completion["required_aux_pools"], ["mamba"])
        self.assertEqual(completion["completed_aux_units"], {"mamba": 3})
        self.assertEqual(completion["finalize_result"], "accepted")

    def test_discarded_finalization_cannot_be_ready_host(self):
        methods = _load_methods("_feed_restore_terminal")

        class CapturingLogger:
            def __init__(self):
                self.info_records = []

            def info(self, *args, **kwargs):
                self.info_records.append(args)

            def warning(self, *args, **kwargs):
                pass

        def run(finalize_result):
            logger = CapturingLogger()
            events = []
            completion = {"finalize_result": finalize_result}
            tree_cache = SimpleNamespace(
                pop_storage_prefetch_terminal=lambda rid: ("a1", "finalized"),
                pop_storage_prefetch_completion=lambda rid: completion,
                peek_prefetch_loaded_tokens=lambda rid: 0,
            )
            scheduler = SimpleNamespace(tree_cache=tree_cache)
            scheduler._prefetch_state_name = lambda state: state.name
            scheduler._release_prefetch_claim = lambda *args: None

            def apply_restore_event(req, event, **kwargs):
                events.append((event, kwargs))
                if event is _RestoreEvents.FINALIZED:
                    req.hicache_restore_state = _RestoreStates.READY
                else:
                    req.hicache_restore_state = _RestoreStates.NONE

            scheduler._apply_restore_event = apply_restore_event
            scheduler._feed_restore_terminal = MethodType(
                methods["_feed_restore_terminal"], scheduler
            )
            req = SimpleNamespace(
                rid="r1",
                hicache_prefetch_active_attempt_id="a1",
                hicache_prefetch_active_origin=None,
                hicache_prefetch_last_origin=None,
                hicache_restore_state=_RestoreStates.RESTORING,
                last_host_node=None,
            )

            feed_globals = methods["_feed_restore_terminal"].__globals__
            original_logger = feed_globals["logger"]
            feed_globals["logger"] = logger
            try:
                scheduler._feed_restore_terminal(req)
            finally:
                feed_globals["logger"] = original_logger
            return req, events, logger.info_records

        for finalize_result in ("discarded", "rejected"):
            discarded_req, discarded_events, discarded_logs = run(finalize_result)
            self.assertIs(discarded_req.hicache_restore_state, _RestoreStates.NONE)
            self.assertIs(discarded_events[0][0], _RestoreEvents.DENIED_SHORT)
            self.assertTrue(discarded_events[0][1]["short_tail_recompute"])
            self.assertFalse(
                any(
                    "schema=rh_ready_host.v1" in record[0]
                    for record in discarded_logs
                )
            )

        accepted_req, accepted_events, accepted_logs = run("accepted")
        self.assertIs(accepted_req.hicache_restore_state, _RestoreStates.READY)
        self.assertIs(accepted_events[0][0], _RestoreEvents.FINALIZED)
        self.assertFalse(accepted_events[0][1]["short_tail_recompute"])
        self.assertTrue(
            any("schema=rh_ready_host.v1" in record[0] for record in accepted_logs)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
