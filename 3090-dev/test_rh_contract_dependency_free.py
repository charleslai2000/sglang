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
    PREFETCH_ISSUED = object()
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
    MISS_RECOMPUTE = SimpleNamespace(name="MISS_RECOMPUTE")
    WAIT_CAPACITY = SimpleNamespace(name="WAIT_CAPACITY")


class _RestoreWaitReasons:
    PREFETCH_BUDGET = SimpleNamespace(name="PREFETCH_BUDGET")
    DEVICE_QUOTA = SimpleNamespace(name="DEVICE_QUOTA")
    HOST_ALLOC = SimpleNamespace(name="HOST_ALLOC")
    FRONTIER = SimpleNamespace(name="FRONTIER")
    REVALIDATE = SimpleNamespace(name="REVALIDATE")
    BACKUP_PENDING = SimpleNamespace(name="BACKUP_PENDING")


class _Prepared(SimpleNamespace):
    pass


class _PrefetchOrigins:
    READY_HORIZON = object()


class _PrefetchStatuses:
    ISSUED = object()
    HELD = object()
    SKIPPED_ACTIVE = object()
    SKIPPED_STATE = object()
    FAILED_BEFORE_ISSUE = object()


class _PrefetchIssueResult(SimpleNamespace):
    pass


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
        "HiCachePrefetchOrigin": _PrefetchOrigins,
        "HiCachePrefetchIssueStatus": _PrefetchStatuses,
        "PrefetchIssueResult": _PrefetchIssueResult,
        "RestoreEvent": _RestoreEvents,
        "RestoreState": _RestoreStates,
        "RestoreWaitReason": _RestoreWaitReasons,
        "_ReadyHorizonPreparedMatch": _Prepared,
        "logger": logging.getLogger(__name__),
        "time": time,
        "_t38c_log": lambda *args, **kwargs: None,
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
        "NodeId": int,
        "PoolName": SimpleNamespace(KV="kv"),
        "PrefetchOperation": object,
    }
    exec(compile(ast.Module(selected, []), str(UNIFIED_CACHE), "exec"), namespace)
    return namespace


class RHContractDependencyFreeTests(unittest.TestCase):
    def _match_scheduler(self, *, live=True):
        methods = _load_methods(
            "_rh_match_candidate",
            "_rh_match_candidate_reason",
            "_rh_match_candidate_without_active_attempt",
            "_rh_current_match_anchors_valid",
            "_rh_state_name",
            "_rh_value_fingerprint",
            "_rh_counter_value",
            "_rh_mamba_snapshot",
            "_rh_match_observation",
            "_prefetch_state_name",
            "_prefetch_kvcache_impl",
            "_emit_rh_match_prepare",
            "_prepare_ready_horizon_match",
            "_rh_prepared_match_valid",
        )
        tree = SimpleNamespace(
            ongoing_prefetch=set(),
            node_exists=lambda node_id: live and node_id in {1, 7},
        )
        scheduler = SimpleNamespace(
            tree_cache=tree,
            chunked_req=None,
            server_args=SimpleNamespace(hicache_host_memory_mode="cache"),
        )
        method_names = (
            "_rh_match_candidate",
            "_rh_match_candidate_reason",
            "_rh_match_candidate_without_active_attempt",
            "_rh_current_match_anchors_valid",
            "_rh_state_name",
            "_rh_value_fingerprint",
            "_rh_counter_value",
            "_rh_mamba_snapshot",
            "_rh_match_observation",
            "_prefetch_state_name",
            "_prefetch_kvcache_impl",
            "_emit_rh_match_prepare",
            "_prepare_ready_horizon_match",
            "_rh_prepared_match_valid",
        )
        for name in method_names:
            setattr(
                scheduler,
                name,
                MethodType(methods[name], scheduler),
            )
        scheduler._emit_rh_match_prepare = lambda *args, **kwargs: None
        return scheduler

    @staticmethod
    def _match_req(state=_RestoreStates.NONE, reason=None):
        req = SimpleNamespace(
            rid="r1",
            last_node=1,
            last_host_node=1,
            full_untruncated_fill_ids=[1, 2, 3],
            output_ids=[],
            extra_key=None,
            cache_salt=None,
            session_generation=4,
            retraction_count=0,
            hicache_request_enqueue_seq=9,
            hicache_restore_state=state,
            hicache_restore_wait_reason=reason,
            host_hit_length=0,
            hicache_prefetch_active_attempt_id=None,
            to_finish=None,
            finished=lambda: False,
        )
        calls = []

        def init_next_round_input(tree_cache, cow_mamba=None):
            calls.append(cow_mamba)
            req.last_node = 7
            req.last_host_node = 7

        req.init_next_round_input = init_next_round_input
        req.match_calls = calls
        return req

    def _issue_scheduler(self, *, fallback_anchor=7):
        names = (
            "_rh_match_candidate",
            "_rh_match_candidate_reason",
            "_rh_match_candidate_without_active_attempt",
            "_rh_current_match_anchors_valid",
            "_rh_state_name",
            "_rh_value_fingerprint",
            "_rh_counter_value",
            "_rh_mamba_snapshot",
            "_rh_match_observation",
            "_prefetch_state_name",
            "_emit_rh_decision",
            "_prefetch_kvcache_impl",
            "_emit_rh_match_prepare",
            "_prepare_ready_horizon_match",
            "_rh_prepared_match_valid",
        )
        methods = _load_methods(*names)
        existing = {1, 7}
        storage_calls = []
        restore_events = []

        class CapturingLogger:
            def __init__(self):
                self.records = []

            def info(self, *args, **kwargs):
                self.records.append(args)

            def warning(self, *args, **kwargs):
                self.records.append(args)

        capture_logger = CapturingLogger()
        tree = SimpleNamespace(
            ongoing_prefetch=set(),
            req_to_token_pool=None,
            mamba_alloc_calls=11,
            mamba_evict_calls=4,
            node_exists=lambda node_id: node_id in existing,
            is_root=lambda node_id: node_id == 1,
            is_backuped=lambda node_id: node_id == 7,
            prefetch_gate_ok=lambda node_id, buffer_mode=False: node_id in existing,
            get_last_hash_value=lambda node_id: f"hash-{node_id}",
            get_prefix_hash_values=lambda node_id: [f"prefix-{node_id}"],
            hicache_storage_pass_prefix_keys=False,
            prefetch_from_storage=lambda *args, **kwargs: storage_calls.append(
                (args, kwargs)
            )
            or "issued",
        )
        req = SimpleNamespace(
            rid="r1",
            last_node=1,
            last_host_node=1,
            full_untruncated_fill_ids=[1, 2, 3],
            prefix_indices=[1, 2],
            output_ids=[],
            extra_key=None,
            cache_salt=None,
            session_generation=4,
            retraction_count=0,
            hicache_request_enqueue_seq=9,
            hicache_restore_state=_RestoreStates.NONE,
            hicache_restore_wait_reason=None,
            host_hit_length=0,
            hicache_prefetch_active_attempt_id=None,
            to_finish=None,
            mamba_pool_idx="pool-0",
            mamba_cow_src_index="src-0",
            mamba_needs_clear=True,
            finished=lambda: False,
            _compute_max_prefix_len=lambda input_len: input_len,
        )
        req.match_calls = []

        def init_next_round_input(tree_cache, cow_mamba=None):
            req.match_calls.append(cow_mamba)
            req.last_node = fallback_anchor
            req.last_host_node = fallback_anchor

        req.init_next_round_input = init_next_round_input
        scheduler = SimpleNamespace(
            enable_hicache_storage=True,
            tree_cache=tree,
            server_args=SimpleNamespace(hicache_host_memory_mode="cache"),
            _rh_pass_seq=3,
        )
        for name in names:
            setattr(scheduler, name, MethodType(methods[name], scheduler))

        def apply_restore_event(request, event, **kwargs):
            restore_events.append((event, kwargs))
            request.hicache_restore_state = _RestoreStates.RESTORING

        scheduler._apply_restore_event = apply_restore_event
        method_globals = methods["_emit_rh_match_prepare"].__globals__
        method_globals["logger"] = capture_logger
        method_globals["_t38c_log"] = lambda *args, **kwargs: None
        return scheduler, req, tree, storage_calls, restore_events, capture_logger

    @staticmethod
    def _log_text(logger):
        records = []
        for record in logger.records:
            if not record:
                continue
            try:
                records.append(record[0] % record[1:])
            except (TypeError, ValueError):
                records.append(str(record[0]))
        return records

    def test_rh_preparation_is_one_shot_and_non_cow(self):
        scheduler = self._match_scheduler()
        req = self._match_req()

        prepared = scheduler._prepare_ready_horizon_match(req, pass_seq=3)

        self.assertIsNotNone(prepared)
        self.assertEqual(req.match_calls, [False])
        self.assertEqual(prepared.last_host_node, 7)
        self.assertTrue(scheduler._rh_prepared_match_valid(req, prepared, 3))

    def test_real_impl_consumes_valid_ticket_without_issue_rematch(self):
        scheduler, req, tree, storage, events, logger = self._issue_scheduler()
        before = (
            req.mamba_pool_idx,
            req.mamba_cow_src_index,
            req.mamba_needs_clear,
            tree.mamba_alloc_calls,
            tree.mamba_evict_calls,
        )
        prepared = scheduler._prepare_ready_horizon_match(req, pass_seq=3)
        req.hicache_prefetch_active_attempt_id = "a1"
        result = scheduler._prefetch_kvcache_impl(
            req,
            origin=_PrefetchOrigins.READY_HORIZON,
            prepared_match=prepared,
        )

        self.assertIs(result.status, _PrefetchStatuses.ISSUED)
        self.assertEqual(req.match_calls, [False])
        self.assertEqual(len(storage), 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(
            (
                req.mamba_pool_idx,
                req.mamba_cow_src_index,
                req.mamba_needs_clear,
                tree.mamba_alloc_calls,
                tree.mamba_evict_calls,
            ),
            before,
        )
        prepare_records = [
            record
            for record in self._log_text(logger)
            if "schema=rh_match_prepare.v1" in record
        ]
        self.assertTrue(prepare_records)
        for field in (
            "restore_state_before=",
            "match_duration_us=",
            "mamba_pool_idx_changed=",
            "mamba_cow_src_changed=",
            "mamba_needs_clear_changed=",
            "mamba_alloc_calls_delta=",
            "mamba_evict_calls_delta=",
        ):
            self.assertIn(field, prepare_records[0])
        self.assertIn("mamba_pool_idx_changed=False", prepare_records[0])
        self.assertIn("mamba_alloc_calls_delta=0", prepare_records[0])

    def test_later_pass_preparation_joins_current_decision_and_null_session(self):
        scheduler, req, _, _, _, logger = self._issue_scheduler()
        scheduler._prefetch_state_name = scheduler._prefetch_state_name.__func__
        req.hicache_last_rh_decision_id = "r1:rh:1"
        req.session_generation = None
        scheduler._rh_pass_seq = 2

        scheduler._emit_rh_match_prepare(
            req,
            pass_seq=2,
            result="prepared",
            reason="current_match",
            match_count_for_pass=1,
        )
        scheduler._emit_rh_decision(
            SimpleNamespace(
                req=req,
                state=_RestoreStates.NONE,
                wait_reason=None,
                staging_eligible=True,
            ),
            rank=1,
            frontier_n=1,
            decision="hold",
            reason="reserve_floor",
            epochs=SimpleNamespace(
                l3_publish=0,
                host_headroom=0,
                host_release=0,
                spec_budget=0,
                waiting_frontier=(req.rid,),
            ),
            headroom=0,
            reserve_floor=0,
            physical_limit=None,
            physical_used=None,
            speculative_limit=None,
            speculative_used=None,
            negative_entry=None,
            issue_origin=None,
            attempt_id=None,
        )

        records = self._log_text(logger)
        prepare = next(
            record for record in records if "schema=rh_match_prepare.v1" in record
        )
        decision = next(
            record
            for record in records
            if "schema=rh_preadmission.v1" in record
        )
        prepare_id = re.search(r"decision_id=(\S+)", prepare).group(1)
        decision_id = re.search(r"decision_id=(\S+)", decision).group(1)
        self.assertEqual(prepare_id, "r1:rh:2")
        self.assertEqual(prepare_id, decision_id)
        self.assertNotIn("r1:rh:1", prepare)
        self.assertIn("session_generation=null", prepare)

    def test_match_preparation_emits_with_nullable_fields(self):
        scheduler, req, _, _, _, _ = self._issue_scheduler()
        req.hicache_request_enqueue_seq = None
        req.session_generation = None
        req.hicache_prefetch_active_attempt_id = None
        req.retraction_count = None

        class EagerFormattingLogger:
            def __init__(self):
                self.records = []

            def info(self, *args, **kwargs):
                self.records.append(args[0] % args[1:])

        logger = EagerFormattingLogger()
        scheduler._emit_rh_match_prepare.__func__.__globals__["logger"] = logger
        scheduler._emit_rh_match_prepare(
            req,
            pass_seq=2,
            result="skipped",
            reason="active_attempt",
            match_duration_us=None,
            match_count_for_pass=0,
        )

        self.assertEqual(len(logger.records), 1)
        record = logger.records[0]
        self.assertIn("schema=rh_match_prepare.v1", record)
        self.assertIn("enqueue_seq=null", record)
        self.assertIn("session_generation=null", record)
        self.assertIn("attempt_id=null", record)
        self.assertIn("match_duration_us=null", record)
        self.assertIn("retraction_count=0", record)

    def test_match_preparation_emits_safe_failure_marker_for_field_error(self):
        scheduler, req, _, _, _, logger = self._issue_scheduler()

        class FailingLength:
            def __len__(self):
                raise RuntimeError("injected telemetry accessor failure")

        req.prefix_indices = FailingLength()
        scheduler._emit_rh_match_prepare(
            req,
            pass_seq=2,
            result="prepared",
            reason="current_match",
        )

        records = self._log_text(logger)
        failure_records = [
            record
            for record in records
            if "schema=rh_match_prepare_emit_failed.v1" in record
        ]
        self.assertEqual(len(failure_records), 1)
        self.assertIn("rid=r1", failure_records[0])
        self.assertIn("exception_class=RuntimeError", failure_records[0])
        self.assertNotIn("schema=rh_match_prepare.v1", failure_records[0])
        self.assertEqual(
            set(failure_records[0].split()),
            {
                "[P3]",
                "evt=rh_match_prepare_emit_failed",
                "schema=rh_match_prepare_emit_failed.v1",
                "rid=r1",
                "exception_class=RuntimeError",
            },
        )

    def test_real_impl_invalid_ticket_rematches_exactly_once(self):
        scheduler, req, _, storage, events, logger = self._issue_scheduler()
        prepared = scheduler._prepare_ready_horizon_match(req, pass_seq=3)
        req.hicache_prefetch_active_attempt_id = "a1"
        req.retraction_count += 1
        result = scheduler._prefetch_kvcache_impl(
            req,
            origin=_PrefetchOrigins.READY_HORIZON,
            prepared_match=prepared,
        )

        self.assertIs(result.status, _PrefetchStatuses.ISSUED)
        self.assertEqual(req.match_calls, [False, False])
        self.assertEqual(len(storage), 1)
        self.assertEqual(len(events), 1)
        records = self._log_text(logger)
        self.assertEqual(
            sum("result=invalidated" in record for record in records), 1
        )
        self.assertEqual(
            sum("reason=fallback_rematch" in record for record in records), 1
        )
        self.assertIn("match_count_for_pass=2", records[-1])

    def test_match_telemetry_classifies_buffer_device_fallback(self):
        scheduler, req, _, _, _, logger = self._issue_scheduler()
        scheduler.server_args.hicache_host_memory_mode = "buffer_only"
        req.last_host_node = 1
        req.last_node = 7
        scheduler._emit_rh_match_prepare(
            req,
            pass_seq=3,
            result="skipped",
            reason="buffer_anchor",
            match_count_for_pass=0,
        )

        records = self._log_text(logger)
        self.assertTrue(
            any("anchor_kind=buffer_device_fallback" in record for record in records)
        )
        self.assertTrue(any("anchor_id=7" in record for record in records))

    def test_real_impl_deleted_and_unknown_anchor_fail_closed(self):
        scheduler, req, tree, storage, events, _ = self._issue_scheduler()
        prepared = scheduler._prepare_ready_horizon_match(req, pass_seq=3)
        req.hicache_prefetch_active_attempt_id = "a1"
        req.retraction_count += 1
        tree.node_exists = lambda node_id: node_id != 7
        result = scheduler._prefetch_kvcache_impl(
            req,
            origin=_PrefetchOrigins.READY_HORIZON,
            prepared_match=prepared,
        )
        self.assertIs(result.status, _PrefetchStatuses.FAILED_BEFORE_ISSUE)
        self.assertEqual(len(storage), 0)
        self.assertEqual(events, [])

        scheduler, req, tree, storage, events, _ = self._issue_scheduler(
            fallback_anchor=99
        )
        prepared = scheduler._prepare_ready_horizon_match(req, pass_seq=3)
        self.assertIsNone(prepared)
        req.hicache_prefetch_active_attempt_id = "a1"
        result = scheduler._prefetch_kvcache_impl(
            req,
            origin=_PrefetchOrigins.READY_HORIZON,
            prepared_match=None,
        )
        self.assertIs(result.status, _PrefetchStatuses.FAILED_BEFORE_ISSUE)
        self.assertEqual(len(storage), 0)
        self.assertEqual(events, [])

    def test_retraction_and_chunk_lifecycle_do_not_reuse_match(self):
        scheduler = self._match_scheduler()
        req = self._match_req()
        prepared = scheduler._prepare_ready_horizon_match(req, pass_seq=3)
        req.retraction_count += 1
        self.assertFalse(scheduler._rh_prepared_match_valid(req, prepared, 3))

        scheduler = self._match_scheduler()
        req = self._match_req()
        scheduler.chunked_req = req
        self.assertIsNone(scheduler._prepare_ready_horizon_match(req, pass_seq=3))
        self.assertEqual(req.match_calls, [])

    def test_rh_ticket_rejects_deleted_anchor_retraction_and_fill_change(self):
        scheduler = self._match_scheduler()
        req = self._match_req()
        prepared = scheduler._prepare_ready_horizon_match(req, pass_seq=3)

        scheduler.tree_cache.node_exists = lambda node_id: False
        self.assertFalse(scheduler._rh_prepared_match_valid(req, prepared, 3))

        scheduler.tree_cache.node_exists = lambda node_id: node_id in {1, 7}
        req.retraction_count += 1
        self.assertFalse(scheduler._rh_prepared_match_valid(req, prepared, 3))

        req.retraction_count -= 1
        req.full_untruncated_fill_ids = list(req.full_untruncated_fill_ids)
        self.assertFalse(scheduler._rh_prepared_match_valid(req, prepared, 3))

    def test_rh_non_stageable_states_receive_no_match(self):
        cases = [
            (_RestoreStates.RESTORING, None),
            (_RestoreStates.READY, None),
            (_RestoreStates.WAIT_CAPACITY, _RestoreWaitReasons.HOST_ALLOC),
            (_RestoreStates.WAIT_CAPACITY, _RestoreWaitReasons.REVALIDATE),
            (_RestoreStates.WAIT_CAPACITY, _RestoreWaitReasons.FRONTIER),
            (_RestoreStates.WAIT_CAPACITY, _RestoreWaitReasons.BACKUP_PENDING),
        ]
        for state, reason in cases:
            scheduler = self._match_scheduler()
            req = self._match_req(state, reason)
            self.assertIsNone(
                scheduler._prepare_ready_horizon_match(req, pass_seq=1),
                (state.name, reason.name if reason is not None else None),
            )
            self.assertEqual(req.match_calls, [])

        scheduler = self._match_scheduler()
        req = self._match_req()
        req.hicache_prefetch_active_attempt_id = "r1:prefetch:1"
        self.assertIsNone(scheduler._prepare_ready_horizon_match(req, 1))
        self.assertEqual(req.match_calls, [])

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
            "schema=rh_match_prepare.v1": (
                "restore_state_before",
                "match_duration_us",
                "mamba_pool_idx_changed",
                "mamba_cow_src_changed",
                "mamba_needs_clear_changed",
                "mamba_alloc_calls_delta",
                "mamba_evict_calls_delta",
                "anchor_kind",
                "buffer_device_fallback",
                "match_count_for_pass",
            ),
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

    def test_ready_pass_joins_raw_frontier_req_to_policy_view(self):
        methods = _load_methods("_ready_horizon_pass")
        scheduler = SimpleNamespace(
            enable_ready_horizon=True,
            _rh_pass_seq=0,
            tree_cache=SimpleNamespace(cache_controller=SimpleNamespace()),
            ready_horizon=SimpleNamespace(
                frontier=lambda queue: queue,
                epoch_event=lambda previous, current: object(),
                should_refill=lambda **kwargs: True,
                refill_plan=lambda *args, **kwargs: SimpleNamespace(
                    declines=[],
                    to_issue=[],
                    candidates=[],
                    ready_count=0,
                    ready_tokens=0,
                ),
                describe_watermarks=lambda: "0/0",
            ),
            waiting_queue=[],
            _ready_horizon_epoch_prev=None,
            _ready_horizon_last_refill_ts=0.0,
            _ready_horizon_negatives={},
            _ready_horizon_last_log=None,
        )
        req = SimpleNamespace(rid="raw-r1")
        view = SimpleNamespace(
            req=req,
            rid=req.rid,
            staging_eligible=False,
            state=SimpleNamespace(name="NONE"),
        )
        decisions = []
        scheduler.waiting_queue = [req]
        scheduler._ready_horizon_views = lambda frontier, prepared_matches=None: [view]
        scheduler._prepare_ready_horizon_match = lambda req, pass_seq: None
        scheduler._ready_horizon_epochs = lambda frontier, views, cc: SimpleNamespace(
            l3_publish=0,
            host_headroom=0,
            host_release=0,
            spec_budget=0,
            waiting_frontier=(req.rid,),
        )
        scheduler._ready_host_headroom = lambda cc, views: 0
        scheduler._ready_reserve_floor_tokens = lambda cc: 0
        scheduler._emit_rh_decision = lambda policy_view, **kwargs: decisions.append(
            (policy_view, kwargs)
        )

        method = methods["_ready_horizon_pass"]
        method.__globals__["logger"] = SimpleNamespace(
            info=lambda *args, **kwargs: None
        )
        method.__globals__["time"] = SimpleNamespace(
            perf_counter=lambda: 1.0, time=lambda: 1.0
        )
        method.__globals__["RestoreState"] = SimpleNamespace(
            NONE=view.state,
            MISS_RECOMPUTE=object(),
            WAIT_CAPACITY=object(),
        )
        method.__globals__["HiCachePrefetchIssueStatus"] = SimpleNamespace()
        method.__globals__["PrefetchIssueResult"] = object
        method.__globals__["HiCachePrefetchOrigin"] = SimpleNamespace(
            READY_HORIZON=object()
        )

        method(scheduler)

        self.assertEqual(len(decisions), 1)
        decision_view, fields = decisions[0]
        self.assertIs(decision_view, view)
        self.assertEqual(fields["decision"], "exclude")
        self.assertEqual(fields["reason"], "no_restore_potential")
        self.assertEqual(fields["rank"], 1)
        self.assertEqual(fields["frontier_n"], 1)

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

    def test_l3_durable_only_anchor_matches_prefetch_potential_gate(self):
        methods = _load_unified_cache_methods(
            "has_restore_potential", "prefetch_gate_ok"
        )
        cache = SimpleNamespace(
            prompt_can_qualify_for_prefetch=lambda prompt_len, host_hit: True,
            ongoing_prefetch=set(),
            _storage_prefetch_missed_rids=set(),
            is_backuped=lambda node_id: False,
            is_root=lambda node_id: False,
            is_l3_durable=lambda node_id: node_id == 7,
            tree_core=SimpleNamespace(
                node_exists=lambda node_id: node_id == 7,
                is_backuped=lambda node_id: False,
                is_root=lambda node_id: False,
                is_l3_durable=lambda node_id: node_id == 7,
            ),
        )
        cache.has_restore_potential = MethodType(
            methods["has_restore_potential"], cache
        )
        cache.prefetch_gate_ok = MethodType(methods["prefetch_gate_ok"], cache)

        self.assertTrue(cache.prefetch_gate_ok(7, False))
        self.assertTrue(cache.has_restore_potential("r1", 7, 0, 128))
        cache.is_l3_durable = lambda node_id: False
        self.assertFalse(cache.prefetch_gate_ok(7, False))
        cache.tree_core.is_l3_durable = lambda node_id: False
        self.assertFalse(cache.has_restore_potential("r1", 7, 0, 128))

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
