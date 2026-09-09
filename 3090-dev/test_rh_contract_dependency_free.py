"""Dependency-free RH contract checks for claim fencing and event joins."""

import ast
import logging
import unittest
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Optional


ROOT = Path(__file__).parents[1]
SCHEDULER = ROOT / "python/sglang/srt/managers/scheduler.py"


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
        "logger": logging.getLogger(__name__),
    }
    exec(compile(ast.Module(selected, []), str(SCHEDULER), "exec"), namespace)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
