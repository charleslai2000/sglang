"""Dependency-free focused checks for the V4.3 trace-context repairs."""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "python/sglang/srt/mem_cache/trace_context.py"
UNIFIED = ROOT / "python/sglang/srt/mem_cache/unified_radix_cache.py"
CONTROLLER = ROOT / "python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py"
HIRADIX = ROOT / "python/sglang/srt/mem_cache/hiradix_cache.py"
VEHICLE = ROOT / "3090-dev/p0_session_barrier_vehicle.py"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_trace_module():
    spec = importlib.util.spec_from_file_location("p0_trace_context_v4", TRACE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_vehicle_module():
    spec = importlib.util.spec_from_file_location("p0_session_barrier_vehicle", VEHICLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _DiagnosticLogger:
    def __init__(self):
        self.messages = []

    def warning(self, message, *args):
        self.messages.append(message % args)


def _load_build_complete_emitter():
    tree = ast.parse(_source(UNIFIED), filename=str(UNIFIED))
    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {
            "_t38c_build_complete_debug",
            "_t38c_emit_build_complete",
            "_t38c_is_tp_group_leader",
        }
    }
    assert set(methods) == {
        "_t38c_build_complete_debug",
        "_t38c_emit_build_complete",
        "_t38c_is_tp_group_leader",
    }
    diagnostic_logger = _DiagnosticLogger()
    marker = {"enabled": True}
    records = []
    namespace = {
        "durable_trace_enabled": lambda: marker["enabled"],
        "_t38c_durable_log": records.append,
        "logger": diagnostic_logger,
        "os": os,
    }
    exec(
        compile(
            ast.Module(
                body=[
                    methods["_t38c_build_complete_debug"],
                    methods["_t38c_emit_build_complete"],
                ],
                type_ignores=[],
            ),
            str(UNIFIED),
            "exec",
        ),
        namespace,
    )
    rank_namespace = {"torch": None}
    exec(
        compile(
            ast.Module(body=[methods["_t38c_is_tp_group_leader"]], type_ignores=[]),
            str(UNIFIED),
            "exec",
        ),
        rank_namespace,
    )
    return (
        namespace["_t38c_emit_build_complete"],
        rank_namespace["_t38c_is_tp_group_leader"],
        marker,
        records,
        diagnostic_logger.messages,
    )


class _BuildNode:
    def __init__(self, node_id="leaf", final_hash="hash"):
        self.id = node_id
        self.final_hash = final_hash

    def get_last_hash_value(self):
        return self.final_hash


class _BuildResult:
    def __init__(self, node):
        self.last_device_node = node


class _BuildReq:
    def __init__(self, rid="build-rid", finished_reason=object()):
        self.rid = rid
        self.finished_reason = finished_reason


class _BuildFixture:
    def __init__(self, context, node_context=None):
        self.context = context
        self.node_context = node_context if node_context is not None else dict(context)
        self.root_node = object()
        self.nodes = {}
        self.tree_core = type(
            "TreeCore",
            (),
            {
                "root_node": self.root_node,
                "node_by_id": lambda tree_core, node_id: self.nodes[node_id],
            },
        )()
        self.leader = True

    def _t38c_trace_context_for_req(self, _req):
        return self.context

    def _t38c_trace_context_for_node(self, _node_id):
        return self.node_context

    def _t38c_is_tp_group_leader(self):
        return self.leader


def check_build_complete_emitter_contract() -> None:
    emitter, _rank_method, marker, records, _diagnostics = _load_build_complete_emitter()
    context = {
        "schema_version": "p0_durable.v3",
        "session_id": "session-a",
        "session_generation": 1,
        "build_rid": "build-a",
        "warm_rid": None,
    }
    fixture = _BuildFixture(context)
    req = _BuildReq("build-a")
    node = _BuildNode("node-a", "hash-a")
    result = _BuildResult(node)

    source = _source(UNIFIED)
    bind = source.index("self._t38c_record_node_context(req, result.last_device_node)")
    emit = source.index("self._t38c_emit_build_complete(", bind)
    cleanup = source.index("# cleanup", emit)
    assert bind < emit < cleanup

    ordering = ["insert_commit", "node_context_bind"]
    emitter(fixture, req, result, is_insert=True, is_abort=False)
    ordering.append(records[-1]["evt"])
    ordering.extend(["storage_persisted", "durability_barrier"])
    assert ordering == [
        "insert_commit",
        "node_context_bind",
        "build_complete",
        "storage_persisted",
        "durability_barrier",
    ]
    assert records[-1]["trace_context"] == context
    assert records[-1]["node_id"] == "node-a"
    assert records[-1]["final_kv_hash"] == "hash-a"
    assert records[-1]["operation_id"] is None
    assert records[-1]["attempt_id"] is None
    assert records[-1]["result"] is True

    records.clear()
    integer_node = _BuildNode(17, "hash-int")
    fixture.nodes[17] = integer_node
    emitter(fixture, req, _BuildResult(17), is_insert=True, is_abort=False)
    assert len(records) == 1
    assert records[0]["node_id"] == "17"
    assert records[0]["final_kv_hash"] == "hash-int"

    for missing_node_id in (18, object()):
        records.clear()
        emitter(
            fixture,
            req,
            _BuildResult(missing_node_id),
            is_insert=True,
            is_abort=False,
        )
        assert records == []

    records.clear()
    warm_req = _BuildReq("warm-a")
    emitter(fixture, warm_req, result, is_insert=True, is_abort=False)
    assert records == []

    missing_context_fields = (
        "session_id",
        "session_generation",
        "build_rid",
        "schema_version",
    )
    for field in missing_context_fields:
        missing = dict(context)
        missing[field] = None
        fixture.context = missing
        fixture.node_context = dict(missing)
        records.clear()
        emitter(fixture, req, result, is_insert=True, is_abort=False)
        assert records == [], field
    fixture.context = dict(context)
    fixture.node_context = dict(context)

    for invalid_result in (
        None,
        _BuildResult(None),
        _BuildResult(_BuildNode("node-empty-hash", "")),
        _BuildResult(fixture.root_node),
    ):
        records.clear()
        emitter(fixture, req, invalid_result, is_insert=True, is_abort=False)
        assert records == []

    fixture.node_context = dict(context)
    fixture.node_context["build_rid"] = "other-build"
    records.clear()
    emitter(fixture, req, result, is_insert=True, is_abort=False)
    assert records == []
    fixture.node_context = dict(context)

    for is_insert, is_abort in ((False, False), (True, True)):
        records.clear()
        emitter(fixture, req, result, is_insert=is_insert, is_abort=is_abort)
        assert records == []

    records.clear()
    unfinished_req = _BuildReq("build-a", finished_reason=None)
    emitter(fixture, unfinished_req, result, is_insert=True, is_abort=False)
    assert records == []

    marker["enabled"] = False
    records.clear()
    emitter(fixture, req, result, is_insert=True, is_abort=False)
    assert records == []
    marker["enabled"] = True


def check_build_complete_rank_and_reopen_contract() -> None:
    emitter, rank_method, marker, records, _diagnostics = _load_build_complete_emitter()

    class Dist:
        available = True
        initialized = True
        rank = 0

        @staticmethod
        def is_available():
            return Dist.available

        @staticmethod
        def is_initialized():
            return Dist.initialized

        @staticmethod
        def get_rank(*, group):
            assert group == "tp"
            return Dist.rank

    torch_stub = type("Torch", (), {"distributed": Dist})
    rank_globals = rank_method.__globals__
    rank_globals["torch"] = torch_stub

    class RankFixture:
        tp_world_size = 1
        tp_group = None

    assert rank_method(RankFixture()) is True
    RankFixture.tp_world_size = 2
    RankFixture.tp_group = "tp"
    Dist.rank = 0
    assert rank_method(RankFixture()) is True
    Dist.rank = 1
    assert rank_method(RankFixture()) is False
    Dist.initialized = False
    assert rank_method(RankFixture()) is False
    RankFixture.tp_group = None
    Dist.initialized = True
    assert rank_method(RankFixture()) is False

    context_a = {
        "schema_version": "p0_durable.v3",
        "session_id": "reopened",
        "session_generation": 1,
        "build_rid": "build-a",
        "warm_rid": None,
    }
    fixture = _BuildFixture(context_a)
    req_a = _BuildReq("build-a")
    result_a = _BuildResult(_BuildNode("node-a", "hash-a"))
    emitter(fixture, req_a, result_a, is_insert=True, is_abort=False)
    emitter(fixture, req_a, result_a, is_insert=True, is_abort=False)
    assert len(records) == 2
    assert {
        (record["session_id"], record["session_generation"], record["build_rid"])
        for record in records
    } == {("reopened", 1, "build-a")}

    context_b = dict(context_a)
    context_b.update(session_generation=2, build_rid="build-b")
    fixture.context = context_b
    fixture.node_context = dict(context_b)
    records.clear()
    emitter(fixture, _BuildReq("build-a"), result_a, is_insert=True, is_abort=False)
    assert records == []
    emitter(
        fixture,
        _BuildReq("build-b"),
        _BuildResult(_BuildNode("node-b", "hash-b")),
        is_insert=True,
        is_abort=False,
    )
    assert len(records) == 1
    assert records[0]["session_generation"] == 2
    assert records[0]["build_rid"] == "build-b"
    assert marker["enabled"] is True


def check_build_complete_diagnostics() -> None:
    emitter, _rank_method, marker, records, diagnostics = _load_build_complete_emitter()
    fixture = _BuildFixture(
        {
            "schema_version": "p0_durable.v3",
            "session_id": "diagnostic-session",
            "session_generation": 1,
            "build_rid": "diagnostic-build",
            "warm_rid": None,
        }
    )
    req = _BuildReq("diagnostic-build", finished_reason=None)
    result = _BuildResult(_BuildNode("diagnostic-node", "diagnostic-hash"))
    original = os.environ.get("T38C_BUILD_COMPLETE_DEBUG")
    try:
        os.environ.pop("T38C_BUILD_COMPLETE_DEBUG", None)
        emitter(fixture, req, result, is_insert=True, is_abort=False)
        assert diagnostics == []

        os.environ["T38C_BUILD_COMPLETE_DEBUG"] = "1"
        emitter(fixture, req, result, is_insert=True, is_abort=False)
        assert records == []
        assert diagnostics == [
            "T38C build_complete suppressed: unfinished_request"
        ]
    finally:
        if original is None:
            os.environ.pop("T38C_BUILD_COMPLETE_DEBUG", None)
        else:
            os.environ["T38C_BUILD_COMPLETE_DEBUG"] = original


def check_event_tailer_fragment_buffering() -> None:
    vehicle = _load_vehicle_module()
    first = {
        "schema_version": vehicle.SCHEMA,
        "run_id": "tailer-run",
        "event_id": "tailer:first",
        "evt": "build_complete",
        "session_id": "tailer-session",
        "build_rid": "tailer-build",
        "node_id": "tailer-node",
        "final_kv_hash": "tailer-hash",
    }
    second = dict(first, event_id="tailer:second", evt="kv_durable", kv_durable=True)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "events.jsonl"
        path.write_text(json.dumps(first), encoding="utf-8")
        reducer = vehicle.Reducer("tailer-run")
        tailer = vehicle.EventTailer(path, reducer)
        tailer.start()
        try:
            assert not tailer.wait_for(lambda: bool(reducer.events), 0.1)
            assert tailer.error is None
            with path.open("a", encoding="utf-8") as handle:
                handle.write("\n" + json.dumps(second) + "\n")
            assert tailer.wait_for(lambda: len(reducer.events) == 2, 2.0)
            assert [event["evt"] for event in reducer.events] == [
                "build_complete",
                "kv_durable",
            ]
            with path.open("a", encoding="utf-8") as handle:
                handle.write("{malformed-complete}\n")
                handle.write(json.dumps(dict(second, event_id="tailer:later-valid")) + "\n")
            assert not tailer.wait_for(lambda: len(reducer.events) == 3, 2.0)
            assert tailer.error is not None
            assert tailer.error.startswith("invalid JSONL:")
            assert len(reducer.events) == 3
        finally:
            tailer.stop()


def check_event_tailer_parse_error_race() -> None:
    vehicle = _load_vehicle_module()
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "events.jsonl"
        path.write_text("", encoding="utf-8")
        reducer = vehicle.Reducer("tailer-race-run")
        tailer = vehicle.EventTailer(path, reducer)
        tailer.start()
        try:
            def yielding_predicate() -> bool:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("{malformed-race}\n")
                with tailer.condition:
                    deadline = time.monotonic() + 2.0
                    while tailer.error is None:
                        remaining = deadline - time.monotonic()
                        assert remaining > 0, "tailer did not publish parse error"
                        tailer.condition.wait(timeout=remaining)
                return True

            assert not tailer.wait_for(yielding_predicate, 2.0)
            assert tailer.error is not None
            assert tailer.error.startswith("invalid JSONL:")
        finally:
            tailer.stop()


def check_prefetch_signature() -> None:
    tree = ast.parse(_source(CONTROLLER), filename=str(CONTROLLER))
    definitions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "append_host_mem_release"
    ]
    assert len(definitions) == 1
    assert "trace_context" in {arg.arg for arg in definitions[0].args.args}
    unified = ast.parse(_source(UNIFIED), filename=str(UNIFIED))
    calls = [
        node for node in ast.walk(unified)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "append_host_mem_release"
    ]
    assert any(
        any(keyword.arg == "trace_context" for keyword in node.keywords)
        for node in calls
    )


def check_context_and_slot_reuse() -> None:
    module = _load_trace_module()
    original_enabled = module.durable_trace_enabled
    try:
        module.durable_trace_enabled = lambda: False
        assert module.make_trace_context("s", 1, "build-off") is None
        module.durable_trace_enabled = lambda: True
        first = module.make_trace_context("s", 1, "build-a")
        assert first is not None
        assert module.make_trace_context("s", None, "build-missing") is None
        module.retire_slot_contexts()
        token = module.remember_slot_context(
            "kv", "host", "digest", first,
            lifecycle={"run_id": "run-a", "node_id": "node-a"},
        )
        assert token is not None
        assert module.complete_slot_context(
            "kv", "host", "digest", token=token
        ) == token
        module.retire_slot_token(token)
        assert module.slot_context("kv", "host", "digest") is None
    finally:
        module.durable_trace_enabled = original_enabled
        module.retire_slot_contexts()


def check_exact_release_fifo() -> None:
    module = _load_trace_module()
    original_enabled = module.durable_trace_enabled
    try:
        module.durable_trace_enabled = lambda: True
        module.retire_slot_contexts()
        first = module.make_trace_context("s", 1, "build-a")
        second = module.make_trace_context("s", 1, "build-b")
        token_a = module.remember_slot_context(
            "kv", "host", "same-digest", first, {"run_id": "a", "node_id": "n1"}
        )
        token_b = module.remember_slot_context(
            "kv", "host", "same-digest", second, {"run_id": "b", "node_id": "n2"}
        )
        assert token_a is not None and token_b is not None and token_a != token_b
        assert module.complete_slot_context(
            "kv", "host", "same-digest", token=token_b
        ) == token_b
        module.retire_slot_token(token_b)
        assert module.complete_slot_context(
            "kv", "host", "same-digest", token=token_a
        ) == token_a
        module.retire_slot_token(token_a)
        reused = module.make_trace_context("s", 2, "build-reused")
        token_c = module.remember_slot_context(
            "kv", "host", "same-digest", reused, {"run_id": "c", "node_id": "n3"}
        )
        assert token_c not in (token_a, token_b)
        assert module.slot_context_for_token(token_a) is None
        assert module.slot_context_for_token(token_c) == reused
    finally:
        module.durable_trace_enabled = original_enabled
        module.retire_slot_contexts()


def check_fail_closed_release_tokens_and_marker_transitions() -> None:
    module = _load_trace_module()
    original_enabled = module.durable_trace_enabled
    try:
        module.durable_trace_enabled = lambda: True
        module.retire_slot_contexts()
        context_a = module.make_trace_context("session-a", 1, "build-a")
        context_b = module.make_trace_context("session-b", 1, "build-b")
        token_a = module.remember_slot_context(
            "kv", "host", "same-digest", context_a,
            {"run_id": "a", "node_id": "n1"},
        )
        token_b = module.remember_slot_context(
            "kv", "host", "same-digest", context_b,
            {"run_id": "b", "node_id": "n2"},
        )
        assert token_a is not None and token_b is not None
        assert module.complete_slot_context(
            "kv", "host", "same-digest",
            token=module.INERT_RELEASE_TOKEN,
        ) is None
        assert module.complete_slot_context(
            "kv", "host", "same-digest", token=None
        ) is None
        assert module.slot_context_for_token(token_a) == context_a
        assert module.slot_context_for_token(token_b) == context_b

        # The token is paired at enqueue time; changing marker state at drain
        # time cannot reinterpret an old page or cross-complete its digest.
        queued = [
            ("page-off", module.INERT_RELEASE_TOKEN),
            ("page-on", token_b),
            ("page-on-missing", module.INERT_RELEASE_TOKEN),
        ]
        completed = []
        marker_on_at_drain = True
        for page, token in queued:
            if marker_on_at_drain and not module.is_inert_release_token(token):
                completed.append(module.complete_slot_context(
                    "kv", "host", "same-digest", token=token
                ))
            else:
                completed.append(None)
        assert completed == [None, token_b, None]
        assert module.slot_context_for_token(token_a) == context_a
        module.retire_slot_token(token_b)

        # on -> off preserves the paired real token; off -> on preserves the
        # inert token. Neither transition can join a different lifecycle.
        assert module.complete_slot_context(
            "kv", "host", "same-digest", token=token_a
        ) == token_a
        module.retire_slot_token(token_a)
    finally:
        module.durable_trace_enabled = original_enabled
        module.retire_slot_contexts()


def check_concurrent_handoff_and_session_cleanup() -> None:
    class Handoff:
        def __init__(self):
            self.lock = threading.Lock()
            self.pages = []
            self.tokens = []
            self.ready = threading.Event()

        def publish(self, page, token):
            with self.lock:
                self.pages.append(page)
                self.tokens.append(token)
            self.ready.set()

        def drain(self):
            self.ready.wait()
            with self.lock:
                if not self.pages or not self.tokens:
                    return None
                return self.pages.pop(0), self.tokens.pop(0)

    handoff = Handoff()
    result = []
    producer = threading.Thread(target=handoff.publish, args=("same-digest", "token-a"))
    drainer = threading.Thread(target=lambda: result.append(handoff.drain()))
    drainer.start()
    producer.start()
    producer.join()
    drainer.join()
    assert result == [("same-digest", "token-a")]

    module = _load_trace_module()
    original_enabled = module.durable_trace_enabled
    try:
        module.durable_trace_enabled = lambda: True
        module.retire_slot_contexts()
        context = module.make_trace_context("session-a", 1, "build-a")
        token = module.remember_slot_context(
            "kv", "host", "same-digest", context,
            lifecycle={"run_id": "run-a", "node_id": "node-a"},
        )
        module.retire_slot_contexts("session-a")
        assert token is not None and module.slot_context_for_token(token) is None
    finally:
        module.durable_trace_enabled = original_enabled
        module.retire_slot_contexts()


def check_marker_off_session_retirement_fixture() -> None:
    unified = ast.parse(_source(UNIFIED), filename=str(UNIFIED))
    retirement = next(
        node for node in ast.walk(unified)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_t38c_retire_session_trace"
    )
    namespace = {
        "_T38C_DURABLE_DETACHED": {},
        "_T38C_DURABLE_COMPLETED": set(),
        "_T38C_DURABLE_BARRIERS": set(),
    }
    retired_slots = []
    namespace["retire_slot_contexts"] = retired_slots.append
    exec(
        compile(ast.Module(body=[retirement], type_ignores=[]), str(UNIFIED), "exec"),
        namespace,
    )

    class Controller:
        def __init__(self, tokens):
            self.tokens = set(tokens)
            self.retired = []

        def _t38c_retire_host_mem_release_tokens(self, session_id):
            self.retired.append(session_id)
            self.tokens = {
                token for token in self.tokens if token[1] != session_id
            }

    marker_off_token = ("release", "marker-off", "token")
    keep_token = ("release", "keep", "token")
    controller = Controller([marker_off_token, keep_token])
    fixture = type("RetirementFixture", (), {})()
    fixture._t38c_session_builds = {
        ("marker-off", 1): "build-off", ("keep", 1): "build-keep"
    }
    fixture._t38c_session_contexts = {
        ("marker-off", 1, "build-off"): {"session_id": "marker-off"},
        ("keep", 1, "build-keep"): {"session_id": "keep"},
    }
    fixture._t38c_node_contexts = {
        ("marker-off", 1, "build-off", "node-off"): {
            "session_id": "marker-off"
        },
        ("keep", 1, "build-keep", "node-keep"): {"session_id": "keep"},
    }
    fixture._t38c_node_context_index = {
        "node-off": ("marker-off", 1, "build-off", "node-off"),
        "node-keep": ("keep", 1, "build-keep", "node-keep"),
    }
    fixture._t38c_request_contexts = {
        "request-off": {"session_id": "marker-off"},
        "request-keep": {"session_id": "keep"},
    }
    fixture._t38c_durability_evidence = {
        "node-off": {
            ("op-off", "attempt-off"): {"trace_context": None}
        },
        "node-keep": {
            ("op-keep", "attempt-keep"): {
                "trace_context": {"session_id": "keep"}
            }
        },
    }
    namespace["_T38C_DURABLE_DETACHED"]["node-off"] = {
        ("node-off", "kv", "host", "digest-off", marker_off_token)
    }
    namespace["_T38C_DURABLE_DETACHED"]["node-keep"] = {
        ("node-keep", "kv", "host", "digest-keep", keep_token)
    }
    namespace["_T38C_DURABLE_COMPLETED"].update(
        {
            ("kv", "host", "digest-off", marker_off_token),
            ("kv", "host", "digest-keep", keep_token),
        }
    )
    namespace["_T38C_DURABLE_BARRIERS"].update(
        {
            (
                "barrier-off",
                (("node-off", "kv", "host", "digest-off", marker_off_token),),
            ),
            (
                "barrier-keep",
                (("node-keep", "kv", "host", "digest-keep", keep_token),),
            ),
        }
    )
    fixture.cache_controller = controller

    namespace["_t38c_retire_session_trace"](fixture, "marker-off")

    assert set(fixture._t38c_session_builds) == {("keep", 1)}
    assert set(fixture._t38c_session_contexts) == {
        ("keep", 1, "build-keep")
    }
    assert set(fixture._t38c_node_contexts) == {
        ("keep", 1, "build-keep", "node-keep")
    }
    assert fixture._t38c_node_context_index == {
        "node-keep": ("keep", 1, "build-keep", "node-keep")
    }
    assert fixture._t38c_request_contexts == {
        "request-keep": {"session_id": "keep"}
    }
    assert set(fixture._t38c_durability_evidence) == {
        "node-off", "node-keep"
    }
    assert controller.tokens == {keep_token}
    assert controller.retired == ["marker-off"]
    assert retired_slots == ["marker-off"]
    assert all(
        marker_off_token not in entries
        for entries in namespace["_T38C_DURABLE_DETACHED"].values()
    )
    assert all(
        marker_off_token not in entry
        for entry in namespace["_T38C_DURABLE_COMPLETED"]
    )
    assert all(
        all(marker_off_token not in key for key in barrier[1])
        for barrier in namespace["_T38C_DURABLE_BARRIERS"]
    )


def check_same_node_mixed_attempt_retirement_fixture() -> None:
    unified = ast.parse(_source(UNIFIED), filename=str(UNIFIED))
    retirement = next(
        node for node in ast.walk(unified)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_t38c_retire_session_trace"
    )
    namespace = {
        "_T38C_DURABLE_DETACHED": {},
        "_T38C_DURABLE_COMPLETED": set(),
        "_T38C_DURABLE_BARRIERS": set(),
        "retire_slot_contexts": lambda _session_id: None,
    }
    exec(
        compile(ast.Module(body=[retirement], type_ignores=[]), str(UNIFIED), "exec"),
        namespace,
    )

    fixture = type("RetirementFixture", (), {})()
    fixture._t38c_session_builds = {}
    fixture._t38c_session_contexts = {}
    fixture._t38c_node_contexts = {}
    fixture._t38c_node_context_index = {}
    fixture._t38c_request_contexts = {}
    fixture._t38c_durability_evidence = {
        "node-shared": {
            ("op-off", "attempt-off"): {"trace_context": None},
            ("op-live", "attempt-live"): {
                "trace_context": {"session_id": "s-live"}
            },
        }
    }
    fixture.cache_controller = None

    namespace["_t38c_retire_session_trace"](fixture, "s-off")

    assert set(fixture._t38c_durability_evidence["node-shared"]) == {
        ("op-off", "attempt-off"),
        ("op-live", "attempt-live"),
    }
    assert fixture._t38c_durability_evidence["node-shared"][(
        "op-live", "attempt-live"
    )]["trace_context"] == {"session_id": "s-live"}


class _DurabilityFixture:
    """Fail-closed model of the node/attempt promotion join."""

    def __init__(self):
        self.pending = defaultdict(dict)
        self.promoted = set()
        self.barriers = []

    def ack(
        self, node, operation, attempt, final_hash, *, context=True,
        mamba_keys=("mamba-key",), mamba_succeeded=1,
        expected_rank_set=("0",), observed_ack_rank_set=("0",),
    ):
        key = (node, operation, attempt)
        expected_rank_set = sorted(str(rank) for rank in expected_rank_set)
        observed_ack_rank_set = sorted(
            str(rank) for rank in observed_ack_rank_set
        )
        self.pending[node][key] = {
            "operation_id": operation,
            "attempt_id": attempt,
            "final_kv_hash": final_hash,
            "context": context,
            "kv_durable": True,
            "mamba_durable": bool(mamba_keys)
            and mamba_succeeded == len(mamba_keys)
            and set(observed_ack_rank_set) >= set(expected_rank_set),
            "expected_rank_set": expected_rank_set,
            "observed_ack_rank_set": observed_ack_rank_set,
            "observed_ack_rank_count": len(observed_ack_rank_set),
            "mamba_key_count": len(mamba_keys),
        }

    def promote(self, node_ids, hashes):
        for node in node_ids:
            if node in self.promoted:
                continue
            matches = [
                (key, candidate)
                for key, candidate in self.pending[node].items()
                if candidate["final_kv_hash"] == hashes[node]
            ]
            if len(matches) != 1:
                continue
            key, candidate = matches[0]
            if candidate["context"] and candidate["kv_durable"] and candidate[
                "mamba_durable"
            ]:
                self.barriers.append((node, candidate["operation_id"], candidate["attempt_id"]))
            self.pending[node].pop(key)
            self.promoted.add(node)


def check_attempt_keyed_frontier_fixture() -> None:
    fixture = _DurabilityFixture()
    fixture.ack("child", "child-op", "child-attempt", "child-hash")
    fixture.ack("parent", "parent-op", "parent-attempt", "parent-hash")
    fixture.promote(
        ["parent", "child"],
        {"parent": "parent-hash", "child": "child-hash"},
    )
    assert fixture.barriers == [
        ("parent", "parent-op", "parent-attempt"),
        ("child", "child-op", "child-attempt"),
    ]

    repeated = _DurabilityFixture()
    repeated.ack("child", "child-op-a", "attempt-a", "same-hash")
    repeated.ack("child", "child-op-b", "attempt-b", "same-hash")
    repeated.promote(["child"], {"child": "same-hash"})
    assert repeated.barriers == []
    assert len(repeated.pending["child"]) == 2


def check_fail_closed_context_and_mamba_fixture() -> None:
    missing_context = _DurabilityFixture()
    missing_context.ack("node", "op", "attempt", "hash", context=False)
    missing_context.promote(["node"], {"node": "hash"})
    assert missing_context.barriers == []
    zero_mamba = _DurabilityFixture()
    zero_mamba.ack("node", "op", "attempt", "hash", mamba_keys=(), mamba_succeeded=0)
    zero_mamba.promote(["node"], {"node": "hash"})
    assert zero_mamba.barriers == []
    single_rank = _DurabilityFixture()
    single_rank.ack(
        "node", "op", "attempt", "hash",
        expected_rank_set=("0",), observed_ack_rank_set=("0",),
    )
    single_rank.promote(["node"], {"node": "hash"})
    assert single_rank.barriers == [("node", "op", "attempt")]
    missing_rank = _DurabilityFixture()
    missing_rank.ack(
        "node", "op", "attempt", "hash",
        expected_rank_set=("0", "1"), observed_ack_rank_set=("0",),
    )
    missing_rank.promote(["node"], {"node": "hash"})
    assert missing_rank.barriers == []


def check_barrier_identity_and_explicit_durability() -> None:
    unified = _source(UNIFIED)
    controller = _source(CONTROLLER)
    hiradix = _source(HIRADIX)
    assert "node_evidence = self._t38c_durability_evidence.setdefault" in unified
    assert "_t38c_select_promoted_candidate" in unified
    assert "_t38c_durability_current" not in unified
    assert '"operation_id": promoted_evidence.get' in unified
    assert '"attempt_id": promoted_evidence.get' in unified
    assert '"kv_durable": operation.completed_tokens' in controller
    assert "mamba_key_count > 0" in controller and "mamba_key_count > 0" in unified
    assert "mamba_succeeded_pages == mamba_expected_pages" in controller
    assert "_ack_mamba_succeeded_pages == _ack_mamba_expected_pages" in unified
    assert '"mamba_key_set_digest"' in controller and '"mamba_key_set_digest"' in unified
    assert '"rank_set_unavailable"' in controller and '"rank_set_unavailable"' in unified
    assert "all_gather_object" in unified
    assert "observed_ack_rank_set" in controller and "observed_ack_rank_set" in unified
    assert "_t38c_rank_topology" in controller
    assert "INERT_RELEASE_TOKEN" in controller and "is_inert_release_token" in unified
    assert "is_inert_release_token" in _source(TRACE)
    assert "complete_slot_context" in _source(TRACE)
    assert "pop_pair" in hiradix
    assert "complete_trace_context(" in unified and "and context_complete" in unified
    assert '"session_generation": session_generation' in _source(TRACE)
    assert "retire_slot_contexts()" in unified
    assert "_t38c_pop_host_mem_release_pair" in controller
    assert "complete_slot_context(" in _source(TRACE)
    assert "token: Optional[tuple[Any, ...]] = None" in _source(TRACE)
    release_session = unified[unified.index("def release_session") :]
    assert "self.session.release_session(session_id)" in release_session
    assert "self._t38c_retire_session_trace(session_id)" in release_session
    drain = unified[unified.index("def _drain_release") : unified.index("def _drain_extra_release")]
    assert "_t38c_pop_host_mem_release_token" not in drain
    assert "slot_context_for_token(token)" in drain
    assert "_t38c_pop_host_mem_release_pair" in drain
    # F6 is pre-existing V2 storage-query behavior; trace emission remains
    # marker-gated and marker-off registration is a no-op.
    assert "not durable_trace_enabled()" in _source(TRACE)


def check_finished_zero_effective_length_fixture() -> None:
    """Exercise the finished zero-boundary contract without engine imports."""
    unified_source = _source(UNIFIED)
    unified = ast.parse(unified_source, filename=str(UNIFIED))
    finished = next(
        node
        for node in ast.walk(unified)
        if isinstance(node, ast.FunctionDef) and node.name == "cache_finished_req"
    )
    zero_guards = [
        node
        for node in ast.walk(finished)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "effective_cache_len"
        and any(
            isinstance(op, ast.LtE) for op in node.test.ops
        )
    ]
    assert len(zero_guards) == 1
    zero_guard = zero_guards[0]
    insert_lines = [
        node.lineno
        for node in ast.walk(finished)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "insert"
    ]
    assert insert_lines and zero_guard.lineno < min(insert_lines)
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "insert"
        for statement in zero_guard.body
        for node in ast.walk(statement)
    )
    cleanup_calls = [
        node
        for node in ast.walk(finished)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "cleanup_after_caching_req"
    ]
    assert any(
        any(keyword.arg == "insert_result" for keyword in call.keywords)
        for call in cleanup_calls
    )
    boundary_method = next(
        node
        for node in ast.walk(unified)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_t38c_record_mamba_boundary"
    )
    boundary_source = ast.get_source_segment(unified_source, boundary_method)
    assert boundary_source is not None
    assert "len(token_ids)" not in boundary_source
    assert "result.mamba_exist" in boundary_source
    assert "_t38c_mamba_boundaries" in boundary_source

    finished_boundary_method = next(
        node
        for node in ast.walk(unified)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_t38c_finished_boundary_result"
    )
    finished_boundary_source = ast.get_source_segment(
        unified_source, finished_boundary_method
    )
    assert finished_boundary_source is not None
    assert "_t38c_trace_context_for_node(node_id) != context" in finished_boundary_source
    assert "not isinstance(final_kv_hash, str)" in finished_boundary_source
    assert "context.get(\"schema_version\") != \"p0_durable.v3\"" in finished_boundary_source
    assert "context.get(\"warm_rid\") is not None" in finished_boundary_source

    class _ExtractedInsertResult:
        def __init__(self, prefix_len, last_device_node=None):
            self.prefix_len = prefix_len
            self.last_device_node = last_device_node

    class _ComponentData:
        def __init__(self, value=True):
            self.value = value
            self.host_value = None

    class _FinishedNode:
        def __init__(self, node_id=17, final_hash="hash-a"):
            self.id = node_id
            self.final_hash = final_hash
            self.forced_miss_tombstone = False
            self.component_data = {
                "full": _ComponentData(),
                "mamba": _ComponentData(),
            }

        def get_last_hash_value(self):
            return self.final_hash

    class _FinishedReq:
        def __init__(self, rid="build-a", finished_reason=object(), last_node=17):
            self.rid = rid
            self.finished_reason = finished_reason
            self.last_node = last_node

    class _ExtractedFinishedFixture:
        def __init__(self, *, node_context=None, final_hash="hash-a"):
            self.context = {
                "schema_version": "p0_durable.v3",
                "session_id": "session-a",
                "session_generation": 1,
                "build_rid": "build-a",
                "warm_rid": None,
            }
            self.node = _FinishedNode(final_hash=final_hash)
            self.node_context = (
                dict(self.context) if node_context is None else node_context
            )
            self.root_node = object()
            self.tree_core = type(
                "TreeCore",
                (),
                {
                    "root_node": self.root_node,
                    "node_by_id": lambda tree_core, node_id: self.node,
                },
            )()
            self._t38c_mamba_boundaries = {
                ("session-a", 1, "build-a"): [
                    {
                        "node_id": 17,
                        "request_rid": "build-a",
                        "effective_cache_len": 4,
                        "final_kv_hash": final_hash,
                        "trace_context": dict(self.context),
                    }
                ]
            }

        def _t38c_trace_context_for_req(self, _req):
            return self.context

        def _t38c_trace_context_for_node(self, _node_id):
            return self.node_context

        @staticmethod
        def _t38c_has_live_value(value):
            return value is not None

        @staticmethod
        def _t38c_is_tp_group_leader():
            return True

    helper_methods = {
        node.name: node
        for node in ast.walk(unified)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_t38c_finished_boundary_result"
    }
    helper_namespace = {
        "InsertResult": _ExtractedInsertResult,
        "ComponentType": type("ComponentType", (), {"FULL": "full", "MAMBA": "mamba"}),
    }
    exec(
        compile(
            ast.Module(body=[helper_methods["_t38c_finished_boundary_result"]], type_ignores=[]),
            str(UNIFIED),
            "exec",
        ),
        helper_namespace,
    )
    extracted_helper = helper_namespace["_t38c_finished_boundary_result"]
    emitter, _rank_method, marker, records, _diagnostics = _load_build_complete_emitter()

    def run_production_zero_path(fixture, *, req=None, is_abort=False):
        result = None
        req = req or _FinishedReq()
        event_result = extracted_helper(
            fixture,
            req,
            is_abort=is_abort,
        )
        records.clear()
        if event_result is not None:
            emitter(fixture, req, event_result, is_insert=True, is_abort=is_abort)
        build_events = [record["node_id"] for record in records]
        session_refs = []
        if event_result is not None:
            session_refs.append(event_result.last_device_node)
        return result, event_result, build_events, session_refs

    valid = _ExtractedFinishedFixture()
    result, event_result, build_events, session_refs = run_production_zero_path(valid)
    assert result is None
    assert event_result is not None
    assert event_result.prefix_len == 4
    assert build_events == ["17"]
    assert session_refs == [17]

    ambiguous_sidecar = _ExtractedFinishedFixture()
    ambiguous_sidecar.node_context = None
    for fixture in (ambiguous_sidecar, _ExtractedFinishedFixture(final_hash=17)):
        result, event_result, build_events, session_refs = run_production_zero_path(fixture)
        assert result is None
        assert event_result is None
        assert build_events == []
        assert session_refs == []

    for req, is_abort in (
        (_FinishedReq(finished_reason=None), False),
        (_FinishedReq(), True),
        (_FinishedReq(last_node=None), False),
    ):
        result, event_result, build_events, session_refs = run_production_zero_path(
            _ExtractedFinishedFixture(), req=req, is_abort=is_abort
        )
        assert result is None
        assert event_result is None
        assert build_events == []
        assert session_refs == []

    class FinishedZeroFixture:
        def __init__(self):
            self.insert_calls = []
            self.build_events = []
            self.session_refs = []
            self.freed = []
            self.cleanup_results = []

        def finish(
            self,
            effective_cache_len,
            *,
            candidate=None,
            finished=True,
            aborted=False,
        ):
            result = None
            event_result = None
            if effective_cache_len <= 0:
                self.freed.append("request-kv-tail")
                if (
                    candidate is not None
                    and candidate["live"]
                    and candidate["non_root"]
                    and candidate["kv"]
                    and candidate["mamba"]
                    and candidate["context"] == "build-a"
                    and candidate["rid"] == "build-a"
                    and finished
                    and not aborted
                ):
                    event_result = candidate
            else:
                result = {"node_id": 17}
                self.insert_calls.append(result)
                event_result = result
            self.cleanup_results.append(result)
            if event_result is not None and finished and not aborted:
                self.build_events.append(event_result["node_id"])
                self.session_refs.append(event_result["node_id"])

    valid_non_root = {
        "node_id": 17,
        "live": True,
        "non_root": True,
        "kv": True,
        "mamba": True,
        "context": "build-a",
        "rid": "build-a",
    }
    no_boundary = FinishedZeroFixture()
    no_boundary.finish(0)
    assert no_boundary.insert_calls == []
    assert no_boundary.build_events == []
    assert no_boundary.session_refs == []
    assert no_boundary.cleanup_results == [None]
    assert no_boundary.freed == ["request-kv-tail"]

    prior_boundary = FinishedZeroFixture()
    prior_boundary.finish(0, candidate=valid_non_root)
    assert prior_boundary.insert_calls == []
    assert prior_boundary.build_events == [17]
    assert prior_boundary.session_refs == [17]
    assert prior_boundary.cleanup_results == [None]

    for kwargs in (
        {"candidate": valid_non_root, "aborted": True},
        {"candidate": valid_non_root, "finished": False},
        {
            "candidate": dict(valid_non_root, context="other-build"),
        },
        {
            "candidate": dict(valid_non_root, mamba=False),
        },
    ):
        rejected = FinishedZeroFixture()
        rejected.finish(0, **kwargs)
        assert rejected.insert_calls == []
        assert rejected.build_events == []
        assert rejected.session_refs == []
        assert rejected.cleanup_results == [None]
        assert rejected.freed == ["request-kv-tail"]

    nonzero = FinishedZeroFixture()
    nonzero.finish(3)
    assert nonzero.insert_calls == [{"node_id": 17}]
    assert nonzero.build_events == [17]
    assert nonzero.cleanup_results == [{"node_id": 17}]


def check_session_barrier_scheduler_fixture() -> None:
    vehicle = _load_vehicle_module()

    class TrackingReducer(vehicle.Reducer):
        def __init__(self, run_id):
            super().__init__(run_id)
            self.ready_checks = 0

        def ready_for_warm(self, session_id):
            self.ready_checks += 1
            return super().ready_for_warm(session_id)

    class FixtureTailer:
        def __init__(self, reducer, error=None):
            self.reducer = reducer
            self.condition = threading.Condition()
            self.error = error
            self.restore_session = None

        def wait_for(self, predicate, timeout_s):
            if self.error:
                return False
            deadline = time.monotonic() + timeout_s
            while True:
                if predicate():
                    return True
                if self.restore_session is not None:
                    session_id = self.restore_session
                    self.restore_session = None
                    state = self.reducer._state(session_id)
                    self.reducer.ingest(
                        {
                            "schema_version": vehicle.SCHEMA,
                            "run_id": self.reducer.run_id,
                            "event_id": f"fixture:restore:{session_id}",
                            "evt": "restore_outcome",
                            "session_id": session_id,
                            "build_rid": state["build_rid"],
                            "node_id": state["node_id"],
                            "final_kv_hash": state["final_kv_hash"],
                            "restore_success": True,
                            "full_restore": True,
                        }
                    )
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                with self.condition:
                    self.condition.wait(timeout=min(0.005, remaining))

    args = SimpleNamespace(
        sessions=3,
        build_workers=2,
        model="fixture-model",
        endpoint="http://fixture",
        api_key=None,
        build_timeout_s=1.0,
        warm_timeout_s=1.0,
        watchdog_s=0.05,
    )
    reducer = TrackingReducer("scheduler-run")
    tailer = FixtureTailer(reducer)
    build_rows = {}
    fatal_errors = []
    lock = threading.Lock()
    calls = []
    original_post_chat = vehicle.post_chat

    def fake_post_chat(endpoint, payload, timeout_s, api_key):
        session_id = payload["session_id"]
        is_warm = len(payload["messages"]) == 3
        calls.append(("warm" if is_warm else "build", session_id))
        if is_warm:
            assert reducer.ready_for_warm(session_id), "warm submitted before exact barriers"
            tailer.restore_session = session_id
            return {
                "http": 200,
                "finished": True,
                "rid": f"fixture-warm-{session_id}",
                "rid_source": "response.id",
            }
        return {
            "http": 200,
            "finished": True,
            "rid": f"fixture-build-{session_id}",
            "rid_source": "response.id",
        }

    vehicle.post_chat = fake_post_chat
    try:
        contexts = vehicle._run_build_phase(
            args,
            lambda index: (f"fixture-history-{index}", vehicle.FROZEN["history_target"]),
            reducer,
            build_rows,
            fatal_errors,
            lock,
        )
        assert set(build_rows) == {f"p0-s25-s{index:05d}" for index in range(3)}
        assert set(contexts) == set(build_rows)
        assert [kind for kind, _ in calls].count("build") == 3
        assert reducer.ready_checks == 0, "build phase waited on a barrier"

        session_id = "p0-s25-s00000"
        common = {
            "schema_version": vehicle.SCHEMA,
            "run_id": reducer.run_id,
            "session_id": session_id,
            "build_rid": build_rows[session_id]["build_rid"],
            "node_id": "fixture-node-0",
            "final_kv_hash": "fixture-hash-0",
        }
        for event_name, fields in (
            ("build_complete", {}),
            ("kv_durable", {"kv_durable": True}),
            ("mamba_durable", {"mamba_durable": True}),
            ("durability_barrier", {"combined_durable": True}),
            ("residency_barrier", {"cold_residency": True}),
        ):
            event = dict(common, event_id=f"fixture:{event_name}", evt=event_name)
            event.update(fields)
            reducer.ingest(event)

        waits = vehicle._run_warm_scheduler(
            args, reducer, tailer, build_rows, contexts, fatal_errors, lock
        )
        assert len(waits) == 3
        assert {row["session_id"] for row in waits} == set(build_rows)
        assert waits[0]["ready"] is True
        assert waits[1]["ready"] is False and waits[1]["reason"] == "watchdog_timeout"
        assert waits[2]["ready"] is False and waits[2]["reason"] == "watchdog_timeout"
        assert [kind for kind, _ in calls].count("warm") == 1
        assert build_rows[session_id]["restore_checked"] is True
        assert build_rows[session_id]["restore_ready"] is True
        assert any("watchdog timeout" in error for error in fatal_errors)

        error_reducer = TrackingReducer("tailer-error-run")
        error_tailer = FixtureTailer(error_reducer, error="malformed JSONL")
        error_rows = {}
        error_contexts = vehicle._run_build_phase(
            args,
            lambda index: (f"fixture-history-{index}", vehicle.FROZEN["history_target"]),
            error_reducer,
            error_rows,
            [],
            lock,
        )
        error_waits = vehicle._run_warm_scheduler(
            args, error_reducer, error_tailer, error_rows, error_contexts, [], lock
        )
        assert len(error_waits) == 3
        assert all(row["ready"] is False for row in error_waits)
        assert all(row["reason"] == "tailer_error" for row in error_waits)
    finally:
        vehicle.post_chat = original_post_chat


def check_vehicle_target_churn_fixture() -> None:
    vehicle = _load_vehicle_module()
    original_post_chat = vehicle.post_chat
    args = SimpleNamespace(
        sessions=25,
        build_workers=8,
        model="fixture-model",
        endpoint="http://fixture",
        api_key=None,
        build_timeout_s=1.0,
        warm_timeout_s=1.0,
        watchdog_s=0.05,
    )
    builder = lambda seed: (
        f"fixture-history-{seed}",
        vehicle.FROZEN["history_target"],
    )
    target_ids = {f"p0-s25-s{index:05d}" for index in range(args.sessions)}
    churn_ids = {f"p0-s25-churn-{index:05d}" for index in range(vehicle.CHURN_COUNT)}

    try:
        calls = []

        def successful_post_chat(_endpoint, payload, _timeout_s, _api_key):
            session_id = payload["session_id"]
            calls.append(session_id)
            return {
                "http": 200,
                "finished": True,
                "rid": f"fixture-build-{session_id}",
                "rid_source": "response.id",
            }

        vehicle.post_chat = successful_post_chat
        reducer = vehicle.Reducer("target-churn-success")
        build_rows = {}
        fatal_errors = []
        contexts = vehicle._run_build_phase(
            args,
            builder,
            reducer,
            build_rows,
            fatal_errors,
            threading.Lock(),
        )
        churn = vehicle._run_churn_phase(
            args,
            builder,
            contexts,
            reducer,
            fatal_errors,
            threading.Lock(),
        )
        assert len(build_rows) == 25
        assert set(build_rows) == target_ids
        assert set(contexts) == target_ids
        assert churn["count"] == vehicle.CHURN_COUNT == 9
        assert set(churn["session_ids"]) == churn_ids
        assert not target_ids & set(churn["session_ids"])
        assert target_ids | churn_ids <= set(reducer.states)
        assert all(reducer._state(session_id)["build_rid"] for session_id in churn_ids)
        assert all(churn_id not in build_rows for churn_id in churn_ids)
        assert len(calls) == 25 + vehicle.CHURN_COUNT
        assert {row["builder_seed"] for row in churn["rows"]} == set(range(25, 34))
        assert len({row["history_sha256"] for row in churn["rows"]}) == vehicle.CHURN_COUNT

        source = _source(VEHICLE)
        churn_call = source.index("churn_evidence = _run_churn_phase")
        warm_call = source.index("barrier_waits = _run_warm_scheduler")
        assert churn_call < warm_call, "churn phase must precede warm scheduler"

        bundle_args = SimpleNamespace(
            sessions=25,
            task_id="target-churn-success",
            epoch="target-churn-success",
            run_id=reducer.run_id,
            endpoint="http://fixture",
            events=None,
            model="fixture-model",
            model_path="fixture-model-path",
        )
        with tempfile.TemporaryDirectory() as directory:
            result = vehicle._write_bundle(
                Path(directory),
                bundle_args,
                reducer,
                build_rows,
                [],
                True,
                fatal_errors,
                False,
                churn,
            )
            reducer_result = json.loads(
                (Path(directory) / "reducer-result.json").read_text(encoding="utf-8")
            )
            build_warm_ids = {
                json.loads(line)["session_id"]
                for line in (Path(directory) / "build-warm.jsonl").read_text(encoding="utf-8").splitlines()
            }
        assert result["planned_row_count"] == 25
        assert result["churn_count"] == 9
        assert set(reducer_result["rows"]) == target_ids
        assert build_warm_ids == target_ids
        assert not churn_ids & set(reducer_result["rows"])
        assert not churn_ids & build_warm_ids

        def failed_churn_post_chat(_endpoint, payload, _timeout_s, _api_key):
            session_id = payload["session_id"]
            if session_id.endswith("00000"):
                return {"http": 503, "finished": False, "rid": "http-failure", "rid_source": "response.id"}
            if session_id.endswith("00001"):
                return {"http": 200, "finished": True, "rid": None, "rid_source": None}
            return {
                "http": 200,
                "finished": True,
                "rid": f"fixture-build-{session_id}",
                "rid_source": "response.id",
            }

        vehicle.post_chat = failed_churn_post_chat
        reducer = vehicle.Reducer("target-churn-failure")
        build_rows = {}
        fatal_errors = []
        contexts = vehicle._run_build_phase(
            args, builder, reducer, build_rows, fatal_errors, threading.Lock()
        )
        churn = vehicle._run_churn_phase(
            args, builder, contexts, reducer, fatal_errors, threading.Lock()
        )
        assert len(build_rows) == 25
        assert churn["count"] == 9
        assert len(churn["failures"]) == 2
        assert any("HTTP/finished/response.id admission" in error for error in fatal_errors)
        assert any("churn-00000" in error for error in fatal_errors)
        assert any("churn-00001" in error for error in fatal_errors)
    finally:
        vehicle.post_chat = original_post_chat


def check_vehicle_fail_closed_boundaries() -> None:
    vehicle = _load_vehicle_module()

    def scheduler_args(run_id):
        return SimpleNamespace(
            sessions=1,
            build_workers=1,
            model="fixture-model",
            endpoint="http://fixture",
            api_key=None,
            build_timeout_s=1.0,
            warm_timeout_s=1.0,
            watchdog_s=0.05,
            run_id=run_id,
        )

    def seed_barriers(reducer, session_id, build_rid, node_id="node-a", final_kv_hash="hash-a"):
        reducer.establish_build(
            session_id,
            build_rid,
            vehicle.FROZEN["history_target"],
            False,
        )
        common = {
            "schema_version": vehicle.SCHEMA,
            "run_id": reducer.run_id,
            "session_id": session_id,
            "build_rid": build_rid,
            "node_id": node_id,
            "final_kv_hash": final_kv_hash,
        }
        for event_name, fields in (
            ("build_complete", {}),
            ("kv_durable", {"kv_durable": True}),
            ("mamba_durable", {"mamba_durable": True}),
            ("durability_barrier", {"combined_durable": True}),
            ("residency_barrier", {"cold_residency": True}),
        ):
            event = dict(common, event_id=f"boundary:{event_name}", evt=event_name)
            event.update(fields)
            reducer.ingest(event)

    original_post_chat = vehicle.post_chat
    try:
        # F1: an HTTP/build-finished failure with an otherwise usable id is
        # fatal and never becomes a build context.
        reducer = vehicle.Reducer("build-failure-run")
        rows = {}
        fatal_errors = []
        vehicle.post_chat = lambda *_args, **_kwargs: {
            "http": 500,
            "finished": False,
            "rid": "server-error-id",
            "rid_source": "response.id",
        }
        contexts = vehicle._run_build_phase(
            scheduler_args(reducer.run_id),
            lambda _index: ("history", vehicle.FROZEN["history_target"]),
            reducer,
            rows,
            fatal_errors,
            threading.Lock(),
        )
        assert contexts == {}
        assert rows["p0-s25-s00000"]["build_rid"] == "server-error-id"
        assert fatal_errors

        # F8: HTTP 200 plus a response ID is not terminal for an incomplete
        # SSE body.  Exercise the actual parser through both build and warm
        # admission so neither path can promote a truncated stream.
        class IncompleteSseResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return (
                    b'data: {"id":"partial-id","choices":[{"delta":'
                    b'{"content":"partial"}}]}\n'
                )

        original_urlopen = vehicle.urllib.request.urlopen
        vehicle.urllib.request.urlopen = lambda *_args, **_kwargs: IncompleteSseResponse()
        vehicle.post_chat = original_post_chat
        try:
            incomplete = vehicle.post_chat(
                "http://fixture",
                {"messages": [], "stream": True},
                1.0,
                None,
            )
            assert incomplete["http"] == 200
            assert incomplete["rid"] == "partial-id"
            assert incomplete["finished"] is False
            assert incomplete["finish_reason"] is None
            assert incomplete["stream_done"] is False

            class CompleteSseResponse(IncompleteSseResponse):
                def read(self):
                    return (
                        b'data: {"id":"complete-id","choices":[{"delta":'
                        b'{"content":"complete"},"finish_reason":"stop"}]}\n'
                        b"data: [DONE]\n"
                    )

            vehicle.urllib.request.urlopen = lambda *_args, **_kwargs: CompleteSseResponse()
            complete = vehicle.post_chat(
                "http://fixture",
                {"messages": [], "stream": True},
                1.0,
                None,
            )
            assert complete["finished"] is True
            assert complete["rid"] == "complete-id"
            assert complete["finish_reason"] == "stop"
            assert complete["stream_done"] is True

            vehicle.urllib.request.urlopen = lambda *_args, **_kwargs: IncompleteSseResponse()

            reducer = vehicle.Reducer("incomplete-build-sse-run")
            rows = {}
            fatal_errors = []
            contexts = vehicle._run_build_phase(
                scheduler_args(reducer.run_id),
                lambda _index: ("history", vehicle.FROZEN["history_target"]),
                reducer,
                rows,
                fatal_errors,
                threading.Lock(),
            )
            assert contexts == {}
            assert rows["p0-s25-s00000"]["finished"] is False
            assert any("build response failed" in error for error in fatal_errors)

            reducer = vehicle.Reducer("incomplete-warm-sse-run")
            session_id = "p0-s25-s00000"
            build_rid = "build-incomplete-warm"
            seed_barriers(reducer, session_id, build_rid)
            args = scheduler_args(reducer.run_id)
            rows = {
                session_id: {
                    "session_id": session_id,
                    "build_rid": build_rid,
                    "history": "history",
                    "history_tokens": vehicle.FROZEN["history_target"],
                    "build_rid_source": "response.id",
                    "http": 200,
                    "finished": True,
                }
            }
            fatal_errors = []
            vehicle._run_warm_scheduler(
                args,
                reducer,
                type(
                    "NoRestoreTailer",
                    (),
                    {
                        "error": None,
                        "condition": threading.Condition(),
                        "wait_for": lambda self, _predicate, _timeout: False,
                    },
                )(),
                rows,
                {session_id: dict(rows[session_id])},
                fatal_errors,
                threading.Lock(),
            )
            assert rows[session_id]["warm_http"] == 200
            assert rows[session_id]["warm_finished"] is False
            assert any("warm response failed" in error for error in fatal_errors)
        finally:
            vehicle.urllib.request.urlopen = original_urlopen

        # F3: a warm response without a successful response.id is terminal and
        # cannot enter restore accounting.
        reducer = vehicle.Reducer("warm-id-run")
        session_id = "p0-s25-s00000"
        build_rid = "build-warm-id"
        seed_barriers(reducer, session_id, build_rid)
        args = scheduler_args(reducer.run_id)
        rows = {
            session_id: {
                "session_id": session_id,
                "build_rid": build_rid,
                "history": "history",
                "history_tokens": vehicle.FROZEN["history_target"],
                "build_rid_source": "response.id",
                "http": 200,
                "finished": True,
            }
        }
        contexts = {session_id: dict(rows[session_id])}
        fatal_errors = []
        vehicle.post_chat = lambda *_args, **_kwargs: {
            "http": 200,
            "finished": True,
            "rid": None,
            "rid_source": None,
        }
        vehicle._run_warm_scheduler(
            args,
            reducer,
            type(
                "NoRestoreTailer",
                (),
                {
                    "error": None,
                    "condition": threading.Condition(),
                    "wait_for": lambda self, _predicate, _timeout: False,
                },
            )(),
            rows,
            contexts,
            fatal_errors,
            threading.Lock(),
        )
        assert rows[session_id]["warm_rid"] is None
        assert fatal_errors

        # F2: a tailer error published after the last warm/restore future still
        # becomes a run-level terminal failure before the scheduler returns.
        reducer = vehicle.Reducer("late-tailer-error-run")
        seed_barriers(reducer, session_id, "build-late-error")

        class LateErrorTailer:
            def __init__(self, reducer):
                self.reducer = reducer
                self.condition = threading.Condition()
                self.error = None

            def wait_for(self, predicate, _timeout):
                state = self.reducer._state(session_id)
                self.reducer.ingest(
                    {
                        "schema_version": vehicle.SCHEMA,
                        "run_id": self.reducer.run_id,
                        "event_id": "boundary:late-restore",
                        "evt": "restore_outcome",
                        "session_id": session_id,
                        "build_rid": state["build_rid"],
                        "node_id": state["node_id"],
                        "final_kv_hash": state["final_kv_hash"],
                        "restore_success": True,
                        "full_restore": True,
                    }
                )
                self.error = "late malformed JSONL"
                return predicate()

        rows = {
            session_id: {
                "session_id": session_id,
                "build_rid": "build-late-error",
                "build_rid_source": "response.id",
                "history": "history",
                "history_tokens": vehicle.FROZEN["history_target"],
                "http": 200,
                "finished": True,
            }
        }
        contexts = {session_id: dict(rows[session_id])}
        fatal_errors = []
        vehicle.post_chat = lambda *_args, **_kwargs: {
            "http": 200,
            "finished": True,
            "rid": "warm-late-error",
            "rid_source": "response.id",
        }
        vehicle._run_warm_scheduler(
            scheduler_args(reducer.run_id),
            reducer,
            LateErrorTailer(reducer),
            rows,
            contexts,
            fatal_errors,
            threading.Lock(),
        )
        assert any("terminal tailer error" in error for error in fatal_errors)

        # F4: the first product warm lookup owns causal order; the synthetic
        # client marker is only a fallback and cannot invalidate a restore.
        reducer = vehicle.Reducer("warm-order-run")
        seed_barriers(reducer, session_id, "build-warm-order")
        state = reducer._state(session_id)
        reducer.ingest(
            {
                "schema_version": vehicle.SCHEMA,
                "run_id": reducer.run_id,
                "event_id": "boundary:product-warm",
                "evt": "warm_lookup_start",
                "session_id": session_id,
                "build_rid": state["build_rid"],
                "node_id": state["node_id"],
                "final_kv_hash": state["final_kv_hash"],
                "warm_rid": "product-warm-id",
            }
        )
        product_order = reducer._state(session_id)["warm_order"]
        reducer.ingest(
            {
                "schema_version": vehicle.SCHEMA,
                "run_id": reducer.run_id,
                "event_id": "boundary:restore",
                "evt": "restore_outcome",
                "session_id": session_id,
                "build_rid": state["build_rid"],
                "node_id": state["node_id"],
                "final_kv_hash": state["final_kv_hash"],
                "restore_success": True,
                "full_restore": True,
            }
        )
        reducer.record_warm_request(session_id, "client-warm-id")
        assert reducer._state(session_id)["warm_order"] == product_order
        assert reducer.restore_ready(session_id) is True

        # F6: a product lookup observed before exact durability/residency
        # barriers is terminal for the session; later barriers cannot make it
        # eligible for a client warm submission.
        reducer = vehicle.Reducer("warm-before-barrier-run")
        session_id = "p0-s25-s00000"
        build_rid = "build-warm-before-barrier"
        reducer.establish_build(
            session_id,
            build_rid,
            vehicle.FROZEN["history_target"],
            False,
        )
        common = {
            "schema_version": vehicle.SCHEMA,
            "run_id": reducer.run_id,
            "session_id": session_id,
            "build_rid": build_rid,
            "node_id": "node-early-warm",
            "final_kv_hash": "hash-early-warm",
        }
        for event_name, fields in (
            ("build_complete", {}),
            ("warm_lookup_start", {"warm_rid": "product-early-warm"}),
            ("kv_durable", {"kv_durable": True}),
            ("mamba_durable", {"mamba_durable": True}),
            ("durability_barrier", {"combined_durable": True}),
            ("residency_barrier", {"cold_residency": True}),
        ):
            event = dict(common, event_id=f"boundary:early:{event_name}", evt=event_name)
            event.update(fields)
            reducer.ingest(event)
        assert reducer._state(session_id)["lookup_before_barrier"] is True
        assert reducer.ready_for_warm(session_id) is False

        rows = {
            session_id: {
                "session_id": session_id,
                "build_rid": build_rid,
                "build_rid_source": "response.id",
                "history": "history",
                "history_tokens": vehicle.FROZEN["history_target"],
                "http": 200,
                "finished": True,
            }
        }
        contexts = {session_id: dict(rows[session_id])}
        calls = []
        vehicle.post_chat = lambda *_args, **_kwargs: calls.append("warm")
        fatal_errors = []
        waits = vehicle._run_warm_scheduler(
            scheduler_args(reducer.run_id),
            reducer,
            type(
                "NoRestoreTailer",
                (),
                {"error": None, "condition": threading.Condition()},
            )(),
            rows,
            contexts,
            fatal_errors,
            threading.Lock(),
        )
        assert len(waits) == 1
        assert waits[0]["ready"] is False
        assert waits[0]["reason"] == "lookup_before_barrier"
        assert calls == []
        assert any("warm not submitted: lookup_before_barrier" in error for error in fatal_errors)
        assert reducer._state(session_id)["lookup_before_barrier"] is True

        # F7: a submitted warm worker that outlives the watchdog is terminally
        # accounted without waiting for executor context shutdown.  The bundle
        # remains fail-closed/NOT_VERIFIED while the worker is still sleeping.
        reducer = vehicle.Reducer("submitted-worker-watchdog-run")
        session_id = "p0-s25-s00000"
        build_rid = "build-slow-warm"
        seed_barriers(reducer, session_id, build_rid)
        args = scheduler_args(reducer.run_id)
        args.watchdog_s = 0.03
        rows = {
            session_id: {
                "session_id": session_id,
                "build_rid": build_rid,
                "build_rid_source": "response.id",
                "history": "history",
                "history_tokens": vehicle.FROZEN["history_target"],
                "http": 200,
                "finished": True,
            }
        }
        contexts = {session_id: dict(rows[session_id])}
        fatal_errors = []

        def slow_warm(*_args, **_kwargs):
            time.sleep(0.20)
            raise RuntimeError("slow warm fixture")

        vehicle.post_chat = slow_warm
        started = time.monotonic()
        waits = vehicle._run_warm_scheduler(
            args,
            reducer,
            type(
                "NoRestoreTailer",
                (),
                {
                    "error": None,
                    "condition": threading.Condition(),
                    "wait_for": lambda self, _predicate, _timeout: False,
                },
            )(),
            rows,
            contexts,
            fatal_errors,
            threading.Lock(),
        )
        elapsed = time.monotonic() - started
        assert len(waits) == 1 and waits[0]["ready"] is True
        assert elapsed < 0.15, f"watchdog return was not bounded: {elapsed:.3f}s"
        assert any("warm worker exceeded watchdog timeout" in error for error in fatal_errors)
        bundle_args = SimpleNamespace(
            sessions=1,
            task_id="submitted-worker-watchdog",
            epoch="submitted-worker-watchdog",
            run_id=reducer.run_id,
            endpoint="http://fixture",
            events=None,
            model="fixture-model",
            model_path="fixture-model-path",
        )
        with tempfile.TemporaryDirectory() as directory:
            result = vehicle._write_bundle(
                Path(directory),
                bundle_args,
                reducer,
                rows,
                waits,
                True,
                fatal_errors,
                False,
            )
        assert result["verdict"] == "NOT_VERIFIED"
        vehicle.post_chat = original_post_chat

        # F5: a second node/hash identity for the same session/build is an
        # immediate invalid join and cannot satisfy warm readiness.
        reducer = vehicle.Reducer("identity-run")
        seed_barriers(reducer, session_id, "build-identity")
        state = reducer._state(session_id)
        reducer.ingest(
            {
                "schema_version": vehicle.SCHEMA,
                "run_id": reducer.run_id,
                "event_id": "boundary:conflict",
                "evt": "mamba_durable",
                "session_id": session_id,
                "build_rid": state["build_rid"],
                "node_id": "node-b",
                "final_kv_hash": "hash-b",
                "mamba_durable": True,
            }
        )
        assert len(reducer._state(session_id)["identities"]) == 2
        assert reducer._state(session_id)["invalid_join"] is True
        assert reducer.ready_for_warm(session_id) is False
        assert reducer.errors

        # Final accounting repeats the build contract, so a malformed build
        # row cannot be promoted to PASS by complete-looking trace evidence.
        reducer = vehicle.Reducer("final-accounting-run")
        seed_barriers(reducer, session_id, "build-final")
        reducer.record_warm_request(session_id, "warm-final")
        state = reducer._state(session_id)
        reducer.ingest(
            {
                "schema_version": vehicle.SCHEMA,
                "run_id": reducer.run_id,
                "event_id": "boundary:final-restore",
                "evt": "restore_outcome",
                "session_id": session_id,
                "build_rid": state["build_rid"],
                "node_id": state["node_id"],
                "final_kv_hash": state["final_kv_hash"],
                "restore_success": True,
                "full_restore": True,
            }
        )
        build_row = {
            "session_id": session_id,
            "build_rid": "build-final",
            "build_rid_source": "response.id",
            "history_tokens": vehicle.FROZEN["history_target"],
            "short_suffix": False,
            "http": 500,
            "finished": False,
            "warm_http": 200,
            "warm_finished": True,
            "warm_rid": "warm-final",
            "warm_metrics": {"rid_source": "response.id"},
        }
        bundle_args = SimpleNamespace(
            sessions=1,
            task_id="boundary-test",
            epoch="boundary-test",
            run_id=reducer.run_id,
            endpoint="http://fixture",
            events=None,
            model="fixture-model",
            model_path="fixture-model-path",
        )
        with tempfile.TemporaryDirectory() as directory:
            result = vehicle._write_bundle(
                Path(directory),
                bundle_args,
                reducer,
                {session_id: build_row},
                [],
                False,
                [],
                False,
            )
        assert result["verdict"] != "PASS"
    finally:
        vehicle.post_chat = original_post_chat


def main() -> None:
    check_build_complete_emitter_contract()
    check_build_complete_rank_and_reopen_contract()
    check_build_complete_diagnostics()
    check_event_tailer_fragment_buffering()
    check_event_tailer_parse_error_race()
    check_prefetch_signature()
    check_context_and_slot_reuse()
    check_exact_release_fifo()
    check_fail_closed_release_tokens_and_marker_transitions()
    check_concurrent_handoff_and_session_cleanup()
    check_marker_off_session_retirement_fixture()
    check_same_node_mixed_attempt_retirement_fixture()
    check_attempt_keyed_frontier_fixture()
    check_fail_closed_context_and_mamba_fixture()
    check_barrier_identity_and_explicit_durability()
    check_finished_zero_effective_length_fixture()
    check_session_barrier_scheduler_fixture()
    check_vehicle_target_churn_fixture()
    check_vehicle_fail_closed_boundaries()
    print("P0 trace-context V4.3 focused checks: PASS")


if __name__ == "__main__":
    main()
