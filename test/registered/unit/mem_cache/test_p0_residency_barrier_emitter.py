"""Dependency-free probes for the product-owned cold residency fold."""

from __future__ import annotations

import ast
from enum import Enum
from queue import Queue
import time
import threading
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
UNIFIED = ROOT / "python/sglang/srt/mem_cache/unified_radix_cache.py"


def _load_barrier_functions():
    tree = ast.parse(UNIFIED.read_text(encoding="utf-8"), filename=str(UNIFIED))
    wanted = {
        "_t38c_residency_identity",
        "_t38c_residency_component_snapshot",
        "_t38c_residency_retire",
        "_t38c_residency_release_queues_drained",
        "_t38c_residency_reconcile",
        "_t38c_residency_seal_detach",
        "_t38c_note_detach",
        "_t38c_note_completion",
        "_t38c_residency_queue_snapshot",
        "_t38c_residency_outcome",
        "_t38c_residency_node_lookup",
        "_t38c_residency_barrier",
        "_t38c_poll_residency_barriers",
        "_t38c_residency_log",
    }
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    }
    assert set(functions) == wanted

    class ComponentType:
        FULL = "full"
        MAMBA = "mamba"

    records = []
    active_tokens = {}
    completion_history = []
    token_sequence = [0]
    durable_enabled = [True]

    def remember(pool, tier, digest, context, lifecycle=None):
        for token, entry in active_tokens.items():
            if (
                entry[:3] == (pool, tier, digest)
                and entry[3] == dict(context)
                and (lifecycle is None or entry[4] == dict(lifecycle))
            ):
                return token
        token_sequence[0] += 1
        token = (
            lifecycle["run_id"],
            context["session_id"],
            lifecycle["node_id"],
            lifecycle["session_generation"],
            context["build_rid"],
            token_sequence[0],
        )
        active_tokens[token] = (
            pool,
            tier,
            digest,
            dict(context),
            dict(lifecycle or {}),
        )
        return token

    def complete(pool, tier, digest, token=None):
        if active_tokens.get(token, ())[:3] == (pool, tier, digest):
            completion_history.append((pool, tier, digest, token))
            return token
        return None

    def retire(token):
        active_tokens.pop(token, None)

    namespace = {
        "_t38c_durable_enabled": lambda: durable_enabled[0],
        "complete_trace_context": lambda context, node_id, final_hash: bool(
            context.get("session_id")
            and context.get("build_rid")
            and context.get("session_generation") is not None
            and context.get("node_id") == str(node_id)
            and context.get("final_kv_hash") == final_hash
        ),
        "ComponentType": ComponentType,
        "_t38c_pool_name": lambda component_type: {
            ComponentType.FULL: "kv",
            ComponentType.MAMBA: "mamba",
        }.get(component_type, str(component_type)),
        "_t38c_free_slots": lambda frees: sum(
            len(value) for values in frees.values() for value in values
        ),
        "_t38c_slot_digest": lambda pool, values: (
            f"{pool}:{getattr(values[0], 'digest', values[0])}"
        ),
        "remember_slot_context": remember,
        "complete_slot_context": complete,
        "is_inert_release_token": lambda token: token == ("inert",),
        "_t38c_durable_log": lambda record: records.append(record)
        or f"event-{len(records)}",
        "retire_slot_token": retire,
        "__import__": __import__,
        "os": __import__("os"),
        "time": time,
        "threading": threading,
    }
    module = ast.Module(
        body=[functions[name] for name in wanted], type_ignores=[]
    )
    exec(compile(module, str(UNIFIED), "exec"), namespace)
    namespace["_active_tokens"] = active_tokens
    namespace["_durable_enabled"] = durable_enabled
    namespace["_records"] = records
    namespace["_completion_history"] = completion_history
    return namespace


def _load_node_context_recorder():
    tree = ast.parse(UNIFIED.read_text(encoding="utf-8"), filename=str(UNIFIED))
    recorder = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name == "_t38c_record_node_context"
    )
    namespace = {"durable_trace_enabled": lambda: True}
    exec(
        compile(ast.Module(body=[recorder], type_ignores=[]), str(UNIFIED), "exec"),
        namespace,
    )
    return namespace["_t38c_record_node_context"]


def _load_build_complete_with_identity():
    tree = ast.parse(UNIFIED.read_text(encoding="utf-8"), filename=str(UNIFIED))
    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name
        in {
            "_t38c_build_complete_debug",
            "_t38c_emit_build_complete",
        }
    }
    assert set(methods) == {
        "_t38c_build_complete_debug",
        "_t38c_emit_build_complete",
    }
    records = []
    namespace = _load_barrier_functions()
    namespace.update(
        {
            "durable_trace_enabled": lambda: True,
            "_t38c_durable_log": lambda record: records.append(record) or "event",
            "logger": SimpleNamespace(warning=lambda *_args: None),
            "os": __import__("os"),
        }
    )
    exec(
        compile(
            ast.Module(
                body=[methods["_t38c_build_complete_debug"], methods["_t38c_emit_build_complete"]],
                type_ignores=[],
            ),
            str(UNIFIED),
            "exec",
        ),
        namespace,
    )
    return namespace["_t38c_emit_build_complete"], records


class _Node:
    def __init__(self, node_id="node-a", final_hash="hash-a", parent=None):
        self.id = node_id
        self.final_hash = final_hash
        self.parent = parent
        self.forced_miss_tombstone = False
        self.component_data = {
            "full": SimpleNamespace(value=None, host_value=None),
            "mamba": SimpleNamespace(value=None, host_value=None),
        }

    def get_last_hash_value(self):
        return self.final_hash


class _Free:
    def __init__(self, digest):
        self.digest = digest

    def __len__(self):
        return 1

    def numel(self):
        return 1


class _Cache:
    def __init__(self, namespace, context, node=None):
        self._namespace = namespace
        self.node = node or _Node()
        self.context = None if context is None else dict(context)
        self._nodes = {str(self.node.id): self.node}
        self._contexts = {
            str(self.node.id): dict(self.context) if self.context is not None else None
        }
        self.tree_core = SimpleNamespace(
            root_node=object(), node_by_id=lambda _node_id: self.node
        )
        self.tree_core.node_by_id = self._node_by_id
        self._t38c_residency_lock = threading.RLock()
        self._t38c_residency_detached = {}
        self._t38c_residency_completed = set()
        self._t38c_residency_barriers = set()
        self._t38c_residency_outcomes = set()
        self._t38c_residency_retry_epoch = 0
        self._t38c_residency_lifecycle = {}
        self._t38c_residency_retired = set()
        self._t38c_residency_reconcile_ready = set()
        self._t38c_residency_queue_blocked = set()
        self.cache_controller = SimpleNamespace(
            _t38c_release_handoff_lock=threading.RLock(),
            host_mem_release_queue=Queue(),
            extra_host_mem_release_queues={"extra": Queue()},
        )
        identity = (
            namespace["_t38c_residency_identity"](
                self.context, self.node.id, self.node.final_hash
            )
            if self.context is not None
            else None
        )
        self._t38c_build_identities = {identity} if identity is not None else set()
        self._t38c_durability_ready = {identity} if identity is not None else set()

    def _node_by_id(self, node_id):
        return self._nodes[str(node_id)]

    def add_build_identity(self, context, node=None):
        node = node or _Node(
            context["node_id"], context["final_kv_hash"]
        )
        self._nodes[str(node.id)] = node
        self._contexts[str(node.id)] = dict(context)
        identity = self._namespace["_t38c_residency_identity"](
            context, node.id, node.final_hash
        )
        self._t38c_build_identities.add(identity)
        self._t38c_durability_ready.add(identity)
        return identity

    def _t38c_trace_context_for_node(self, node_id):
        if str(node_id) == str(self.node.id) and self.context is not None:
            return dict(self.context)
        context = self._contexts.get(str(node_id))
        return dict(context) if context is not None else None


def _context(
    session_id="session-a", generation=1, build_rid="build-a", run_id="run-a"
):
    return {
        "schema_version": "p0_durable.v3",
        "run_id": run_id,
        "session_id": session_id,
        "session_generation": generation,
        "build_rid": build_rid,
        "warm_rid": None,
        "node_id": "node-a",
        "final_kv_hash": "hash-a",
    }


def _tokens(cache, *, pool=None, tier=None):
    entries = [
        entry
        for expected in cache._t38c_residency_detached.values()
        for entry in expected
        if (pool is None or entry[1] == pool) and (tier is None or entry[2] == tier)
    ]
    assert entries
    return [entry[4] for entry in entries]


def _published_records(records):
    return [record for record in records if record.get("evt") == "residency_barrier"]


def _record_session(record):
    return record.get("session_id") or (record.get("trace_context") or {}).get(
        "session_id"
    )


def _load_real_scheduler_surfaces(namespace):
    """Bind the production handoff/drain/checkpoint methods to a tiny harness."""
    controller_path = (
        ROOT
        / "python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py"
    )
    wanted = {
        "_append_host_mem_release_pages",
        "append_host_mem_release",
        "_t38c_token_queue",
        "_t38c_pop_host_mem_release_pair",
        "_drain_storage_control_queues_impl",
        "_sync_hicache_ready_counts",
        "_drain_async_work",
        "check_hicache_events",
    }
    nodes = {}
    for path in (controller_path, UNIFIED):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in wanted:
                nodes[node.name] = node
    assert set(nodes) == wanted

    class _PoolName(Enum):
        KV = "kv"
        MAMBA = "mamba"

    class _FakeTensor:
        def __init__(self, length=0, digest=None, values=None):
            self.length = length if values is None else len(values)
            self.digest = digest
            self.values = list(range(self.length)) if values is None else list(values)

        def __len__(self):
            return self.length

        def numel(self):
            return self.length

        def split(self, page_size):
            return [
                _FakeTensor(
                    min(page_size, self.length - offset),
                    self.digest,
                )
                for offset in range(0, self.length, page_size)
            ]

        def __getitem__(self, item):
            values = self.values[item]
            if not isinstance(values, list):
                values = [values]
            return _FakeTensor(values=values, digest=self.digest)

        def tolist(self):
            return list(self.values)

    class _FakeTorch:
        int = object()
        int64 = object()

        class distributed:
            class ReduceOp:
                MIN = object()

        @staticmethod
        def tensor(values, **_kwargs):
            return _FakeTensor(values=list(values))

        @staticmethod
        def cat(values, dim=0):
            del dim
            return _FakeTensor(
                length=sum(value.numel() for value in values),
                digest=values[0].digest if values else None,
            )

    class _Logger:
        def info(self, *args, **kwargs):
            del args, kwargs

        def warning(self, *args, **kwargs):
            del args, kwargs

        def error(self, *args, **kwargs):
            del args, kwargs

    class _HostPool:
        page_size = 4

        def __init__(self):
            self.free_calls = []
            self.entry_map = {
                _PoolName.MAMBA: SimpleNamespace(
                    is_primary_index_anchor=False,
                    host_pool=SimpleNamespace(page_size=4),
                )
            }

        def free(self, tensor, pool=None):
            self.free_calls.append((tensor, pool))

    class _Controller:
        def __init__(self):
            self._t38c_release_handoff_lock = threading.Lock()
            self.host_mem_release_queue = Queue()
            self.extra_host_mem_release_queues = {_PoolName.MAMBA: Queue()}
            self._t38c_host_mem_release_tokens = Queue()
            self._t38c_extra_host_mem_release_tokens = {
                _PoolName.MAMBA: Queue()
            }
            self.prefetch_hit_queue = Queue()
            self.ack_prefetch_queue = Queue()
            self.ack_backup_queue = Queue()
            self.ack_write_queue = Queue()
            self.ack_load_queue = Queue()
            self.storage_failure_reason = None
            self.mem_pool_host = _HostPool()
            self.prefetch_tokens_occupied = 0
            self.prefetch_capacity_limit = 1

    class _SchedulerCache(_Cache):
        def __init__(self, loaded_namespace, context):
            super().__init__(loaded_namespace, context)
            self.cache_controller = _Controller()
            self.enable_storage = True
            self.enable_storage_metrics = False
            self.storage_metrics_collector = None
            self.host_memory_mode = "cache"
            self.pp_size = 1
            self.pp_rank = 0
            self.tp_world_size = 1
            self.tp_group = None
            self.pp_group = None
            self.buffer_pipeline = None
            self.work_list = []
            self.ongoing_prefetch = {}
            self.prefetch_threshold = 1
            self._prefetch_outcome_stats = {}
            self.tree_core.write_back_duplicate_reclaim_digest = 0

        def _all_reduce(self, data, _op):
            del data, _op

        def _count_ready_acks(self, ack_queue):
            del ack_queue
            return 0

        def writing_check(self, finish_count=None, **kwargs):
            del finish_count, kwargs

        def loading_check(self, finish_count=None):
            del finish_count

    fake_torch = _FakeTorch()
    namespace.update(
        {
            "PoolName": _PoolName,
            "torch": fake_torch,
            "Queue": Queue,
            "logger": _Logger(),
            "T": object,
            "durable_trace_enabled": lambda: True,
            "INERT_RELEASE_TOKEN": ("inert",),
            "slot_context_for_token": lambda token: (
                active[3] if (active := namespace["_active_tokens"].get(token)) else None
            ),
            "_t38c_slot_digest": lambda pool, values: (
                f"{getattr(pool, 'value', pool)}:{values[0].digest}"
            ),
            "ordered_key_set_digest": lambda keys: ("empty", len(list(keys))),
            "_t38c_log": lambda record: None,
        }
    )

    method_module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__",
                names=[ast.alias(name="annotations")],
                level=0,
            )
        ]
        + [nodes[name] for name in wanted],
        type_ignores=[],
    )
    ast.fix_missing_locations(method_module)
    exec(compile(method_module, str(UNIFIED), "exec"), namespace)
    for name in (
        "_append_host_mem_release_pages",
        "append_host_mem_release",
        "_t38c_token_queue",
        "_t38c_pop_host_mem_release_pair",
    ):
        setattr(_Controller, name, namespace[name])
    for name in (
        "_drain_storage_control_queues_impl",
        "_sync_hicache_ready_counts",
        "_drain_async_work",
        "check_hicache_events",
    ):
        setattr(_SchedulerCache, name, namespace[name])
    namespace["_FakeTensor"] = _FakeTensor
    namespace["_PoolName"] = _PoolName
    return _SchedulerCache, _PoolName, _FakeTensor


def _run_real_scheduler_checkpoint_probe(namespace):
    SchedulerCache, pool_name, fake_tensor = _load_real_scheduler_surfaces(
        namespace
    )
    complete = namespace["_t38c_note_completion"]
    detach = namespace["_t38c_note_detach"]
    records = namespace["_records"]
    completion_history = namespace["_completion_history"]

    def run_case(session_id, host_pool, host_digest):
        cache = SchedulerCache(namespace, _context(session_id, 1, f"{session_id}-build"))
        detach(cache, "node-a", "kv", "device", f"{session_id}-kv-device")
        detach(cache, "node-a", "mamba", "device", f"{session_id}-mamba-device")
        detach(cache, "node-a", host_pool, "host", host_digest)
        _seal(
            cache,
            namespace,
            ("kv", "device"),
            ("mamba", "device"),
            (host_pool, "host"),
        )
        for pool, digest in (
            ("kv", f"{session_id}-kv-device"),
            ("mamba", f"{session_id}-mamba-device"),
        ):
            token = _token_for(cache, pool, "device", digest)
            complete(cache, pool, "device", digest, token=token)

        if host_pool == "kv":
            cache.cache_controller.append_host_mem_release(
                host_indices=fake_tensor(1, digest=host_digest.split(":", 1)[1]),
                trace_context=cache.context,
            )
            release_queue = cache.cache_controller.host_mem_release_queue
        else:
            transfer = SimpleNamespace(
                name=pool_name.MAMBA,
                host_indices=fake_tensor(
                    1, digest=host_digest.split(":", 1)[1]
                ),
                indices_from_pool=None,
                _t38c_trace_context=cache.context,
            )
            cache.cache_controller.append_host_mem_release(
                extra_pools=[transfer], trace_context=cache.context
            )
            release_queue = cache.cache_controller.extra_host_mem_release_queues[
                pool_name.MAMBA
            ]

        host_token = _token_for(cache, host_pool, "host", host_digest)
        # This is the real completion callback surface, before the scheduler
        # checkpoint: it proves the queue guard suppresses publication while
        # the controller-owned handoff queue still owns the page.
        complete(cache, host_pool, "host", host_digest, token=host_token)
        # The completion-triggered attempt may already have recorded an
        # earlier token-incomplete predicate. A real pending-identity poll
        # gives the queue guard its own retry epoch before the scheduler
        # checkpoint drains the handoff.
        namespace["_t38c_poll_residency_barriers"](cache)
        suppressed = [
            record
            for record in records
            if record.get("evt") == "residency_barrier_outcome"
            and record.get("reason") == "queue_nonempty"
            and record.get("session_id") == session_id
        ]
        assert len(suppressed) == 1
        assert suppressed[0]["queue_snapshot_locked"] is True
        assert suppressed[0]["primary_queue_empty"] is (host_pool != "kv")
        assert suppressed[0]["extra_queue_empty"] is (host_pool == "kv")
        assert release_queue.qsize() == 1
        assert not _published_records(records) or all(
            _record_session(record) != session_id
            for record in _published_records(records)
        )

        before_completions = len(completion_history)
        cache.check_hicache_events()
        assert release_queue.empty()
        assert len(cache.cache_controller.mem_pool_host.free_calls) == 1
        assert len(completion_history) == before_completions
        published = [
            record
            for record in _published_records(records)
            if _record_session(record) == session_id
        ]
        assert len(published) == 1
        outcome = [
            record
            for record in records
            if record.get("evt") == "residency_barrier_outcome"
            and _record_session(record) == session_id
            and record.get("reason") == "published"
        ]
        assert len(outcome) == 1
        assert outcome[0]["primary_queue_empty"] is True
        assert outcome[0]["extra_queue_empty"] is True
        cache.check_hicache_events()
        assert len(
            [
                record
                for record in _published_records(records)
                if _record_session(record) == session_id
            ]
        ) == 1
        assert len(completion_history) == before_completions

    run_case(
        "scheduler-primary",
        "kv",
        "kv:scheduler-primary-host",
    )
    run_case(
        "scheduler-extra",
        "mamba",
        "mamba:scheduler-extra-host",
    )
    print("Real TP=1 scheduler checkpoint primary/extra probe: PASS")


def _token_for(cache, pool, tier, digest):
    entries = [
        entry
        for expected in cache._t38c_residency_detached.values()
        for entry in expected
        if entry[1:4] == (pool, tier, digest)
    ]
    assert len(entries) == 1
    return entries[0][4]


def _detach_and_complete(cache, namespace, pool, tier, digest):
    detach = namespace["_t38c_note_detach"]
    complete = namespace["_t38c_note_completion"]
    detach(cache, cache.node.id, pool, tier, digest)
    entries = [
        entry
        for expected in cache._t38c_residency_detached.values()
        for entry in expected
        if entry[1] == pool and entry[2] == tier and entry[3] == digest
    ]
    if not entries:
        return None
    token = entries[-1][4]
    complete(cache, pool, tier, digest, token=token)
    return token


def _seal(cache, namespace, *entries):
    namespace["_t38c_residency_seal_detach"](
        cache, cache.node.id, set(entries)
    )


def _complete_entries(cache, namespace, entries):
    complete = namespace["_t38c_note_completion"]
    for pool, tier, digest in entries:
        complete(
            cache,
            pool,
            tier,
            digest,
            token=_token_for(cache, pool, tier, digest),
        )


_DEFAULT_CONTEXT = object()


def _new_ready_cache(namespace, context=_DEFAULT_CONTEXT):
    if context is _DEFAULT_CONTEXT:
        context = _context()
    return _Cache(namespace, context)


def _residency_state(cache, namespace):
    return (
        {
            identity: frozenset(entries)
            for identity, entries in cache._t38c_residency_detached.items()
        },
        frozenset(cache._t38c_residency_completed),
        frozenset(cache._t38c_residency_barriers),
        frozenset(cache._t38c_residency_outcomes),
        frozenset(cache._t38c_build_identities),
        frozenset(cache._t38c_durability_ready),
        dict(namespace["_active_tokens"]),
    )


def _assert_invalid_context_case(namespace, records, case_name, context):
    cache = _new_ready_cache(namespace, context)
    before = _residency_state(cache, namespace)
    record_count = len(_published_records(records))
    assert namespace["_t38c_residency_identity"](
        context, cache.node.id, cache.node.final_hash
    ) is None
    namespace["_t38c_note_detach"](
        cache, cache.node.id, "kv", "device", f"invalid-{case_name}"
    )
    namespace["_t38c_residency_barrier"](cache, cache.node.id)
    namespace["_t38c_poll_residency_barriers"](cache)
    assert len(_published_records(records)) == record_count, case_name
    assert _residency_state(cache, namespace) == before, case_name
    print(f"F-4 invalid residency context {case_name}: PASS")


def check_node_sidecar_context_contract():
    record_node_context = _load_node_context_recorder()
    root = object()
    parent = _Node("parent", "hash-parent", root)
    leaf = _Node("leaf", "hash-leaf", parent)
    nodes = {"leaf": leaf, "parent": parent}
    context = {
        "schema_version": "p0_durable.v3",
        "run_id": "run-sidecar",
        "session_id": "session-sidecar",
        "session_generation": 3,
        "build_rid": "build-sidecar",
        "warm_rid": None,
    }

    class Fixture:
        def __init__(self, active_context):
            self.context = active_context
            self.tree_core = SimpleNamespace(
                root_node=root, node_by_id=lambda node_id: nodes[node_id]
            )
            self._t38c_session_builds = {}
            self._t38c_session_contexts = {}
            self._t38c_node_contexts = {}
            self._t38c_node_context_index = {}
            self._t38c_build_identities = set()

        def _t38c_trace_context_for_req(self, _req):
            return dict(self.context)

        def _t38c_trace_context_for_node(self, node_id):
            key = self._t38c_node_context_index.get(str(node_id))
            context = self._t38c_node_contexts.get(key) if key is not None else None
            return dict(context) if context is not None else None

        @staticmethod
        def _t38c_is_tp_group_leader():
            return True

    fixture = Fixture(context)
    record_node_context(fixture, SimpleNamespace(), "leaf")
    assert fixture._t38c_node_contexts["session-sidecar", 3, "build-sidecar", "leaf"] == dict(
        context, node_id="leaf", final_kv_hash="hash-leaf"
    )
    assert fixture._t38c_node_contexts[
        "session-sidecar", 3, "build-sidecar", "parent"
    ] == dict(context, node_id="parent", final_kv_hash="hash-parent")

    leaf_context = fixture._t38c_trace_context_for_node("leaf")
    assert leaf_context["node_id"] == "leaf"
    assert leaf_context["final_kv_hash"] == "hash-leaf"
    parent_context = fixture._t38c_trace_context_for_node("parent")
    assert parent_context["node_id"] == "parent"
    assert parent_context["final_kv_hash"] == "hash-parent"

    identity = (
        context["run_id"],
        context["session_id"],
        context["session_generation"],
        context["build_rid"],
        "leaf",
        "hash-leaf",
    )
    namespace = _load_barrier_functions()
    assert namespace["_t38c_residency_identity"](
        leaf_context, "leaf", "hash-leaf"
    ) == identity

    emitter, records = _load_build_complete_with_identity()
    emitter(
        fixture,
        SimpleNamespace(rid="build-sidecar", finished_reason=object()),
        SimpleNamespace(last_device_node=leaf),
        is_insert=True,
        is_abort=False,
    )
    assert records[-1]["evt"] == "build_complete"
    assert fixture._t38c_build_identities == {identity}

    mismatch = Fixture(context)
    record_node_context(mismatch, SimpleNamespace(), "leaf")
    mismatch._t38c_trace_context_for_node = lambda _node_id: dict(
        leaf_context, build_rid="other-build"
    )
    emitter(
        mismatch,
        SimpleNamespace(rid="build-sidecar", finished_reason=object()),
        SimpleNamespace(last_device_node=leaf),
        is_insert=True,
        is_abort=False,
    )
    assert mismatch._t38c_build_identities == set()
    assert records[-1]["evt"] == "build_complete"

    record_node_context(fixture, SimpleNamespace(), "leaf")
    assert fixture._t38c_trace_context_for_node("leaf") == leaf_context
    conflicting = Fixture(dict(context, session_id="other-session"))
    conflicting._t38c_node_contexts = fixture._t38c_node_contexts
    conflicting._t38c_node_context_index = fixture._t38c_node_context_index
    conflicting._t38c_session_builds = fixture._t38c_session_builds
    conflicting._t38c_session_contexts = fixture._t38c_session_contexts
    record_node_context(conflicting, SimpleNamespace(), "leaf")
    assert conflicting._t38c_node_context_index["leaf"] is None
    assert conflicting._t38c_trace_context_for_node("leaf") is None
    fixture._t38c_node_context_index["leaf"] = None
    emitter(
        fixture,
        SimpleNamespace(rid="build-sidecar", finished_reason=object()),
        SimpleNamespace(last_device_node=leaf),
        is_insert=True,
        is_abort=False,
    )
    assert fixture._t38c_build_identities == {identity}
    assert records[-1]["evt"] == "build_complete"
    assert fixture._t38c_node_contexts[
        "session-sidecar", 3, "build-sidecar", "leaf"
    ] == leaf_context
    print("Six-field leaf/parent sidecar and no-last-write-wins checks: PASS")


def check_residency_node_lookup_boundary():
    namespace = _load_barrier_functions()
    lookup = namespace["_t38c_residency_node_lookup"]

    class Node:
        def __init__(self, node_id):
            self.id = node_id

    exact = Node(41)
    exact_cache = SimpleNamespace(
        tree_core=SimpleNamespace(node_by_id=lambda node_id: {41: exact}[node_id])
    )
    assert lookup(exact_cache, 41) is exact
    assert lookup(exact_cache, "41") is exact

    def missing_node(_node_id):
        raise KeyError("missing")

    missing_cache = SimpleNamespace(
        tree_core=SimpleNamespace(node_by_id=missing_node)
    )
    assert lookup(missing_cache, "41") is None

    wrong_node = Node(42)
    wrong_cache = SimpleNamespace(
        tree_core=SimpleNamespace(node_by_id=lambda _node_id: wrong_node)
    )
    assert lookup(wrong_cache, "41") is None

    wrong_alias_cache = SimpleNamespace(
        tree_core=SimpleNamespace(
            node_by_id=lambda node_id: {"41": wrong_node, 41: exact}[node_id]
        )
    )
    assert lookup(wrong_alias_cache, "41") is None

    string_alias = Node(41)
    ambiguous_cache = SimpleNamespace(
        tree_core=SimpleNamespace(
            node_by_id=lambda node_id: {41: exact, "41": string_alias}[node_id]
        )
    )
    assert lookup(ambiguous_cache, "41") is None
    print("Exact NodeId/string lookup, missing, and ambiguity checks: PASS")


def check_final_only_eligibility(namespace, records):
    cache = _new_ready_cache(namespace, _context("session-parent", 1, "build-leaf"))
    parent_context = dict(
        cache.context,
        node_id="parent",
        final_kv_hash="hash-parent",
    )
    cache._t38c_trace_context_for_node = lambda node_id: (
        parent_context if node_id == "parent" else dict(cache.context)
    )
    before = len(records)
    namespace["_t38c_note_detach"](
        cache, "parent", "kv", "device", "parent-device"
    )
    namespace["_t38c_note_detach"](
        cache, "parent", "kv", "device", "parent-device-2"
    )
    assert cache._t38c_residency_detached == {}
    assert namespace["_active_tokens"] == {}
    parent_records = [
        record
        for record in records[before:]
        if record.get("reason") == "nonterminal_not_build_registered"
    ]
    assert len(parent_records) == 1
    print("Final-node-only eligibility and bounded parent diagnostic: PASS")


def check_async_durability_retry(namespace, records):
    cache = _new_ready_cache(
        namespace, _context("session-async", 1, "build-async")
    )
    identity = next(iter(cache._t38c_build_identities))
    cache._t38c_durability_ready.clear()
    namespace["_t38c_note_detach"](
        cache, "node-a", "kv", "device", "async-device"
    )
    namespace["_t38c_note_detach"](
        cache, "node-a", "mamba", "host", "async-host"
    )
    _seal(
        cache,
        namespace,
        ("kv", "device"),
        ("mamba", "host"),
    )
    namespace["_t38c_note_completion"](
        cache,
        "kv",
        "device",
        "async-device",
        token=_token_for(cache, "kv", "device", "async-device"),
    )
    namespace["_t38c_note_completion"](
        cache,
        "mamba",
        "host",
        "async-host",
        token=_token_for(cache, "mamba", "host", "async-host"),
    )
    assert _published_records(records) == []
    cache._t38c_durability_ready.add(identity)
    namespace["_t38c_residency_reconcile"](cache, identity, "durability_ready")
    assert len(_published_records(records)) == 1
    print("Async durability readiness and exact-free retry: PASS")


def check_component_snapshot_blocker(namespace, records):
    cache = _new_ready_cache(
        namespace, _context("session-component", 1, "build-component")
    )
    before_published = len(_published_records(records))
    cache.node.component_data["mamba"].value = object()
    namespace["_t38c_note_detach"](
        cache, "node-a", "kv", "device", "component-device"
    )
    namespace["_t38c_note_detach"](
        cache, "node-a", "mamba", "host", "component-host"
    )
    _seal(
        cache,
        namespace,
        ("kv", "device"),
        ("mamba", "host"),
    )
    namespace["_t38c_note_completion"](
        cache,
        "kv",
        "device",
        "component-device",
        token=_token_for(cache, "kv", "device", "component-device"),
    )
    namespace["_t38c_note_completion"](
        cache,
        "mamba",
        "host",
        "component-host",
        token=_token_for(cache, "mamba", "host", "component-host"),
    )
    blockers = [
        record
        for record in records
        if record.get("evt") == "residency_barrier_outcome"
        and record.get("session_id") == "session-component"
        and record.get("reason") == "live_component_value"
    ]
    assert blockers
    mamba = next(
        tier for tier in blockers[-1]["component_tiers"] if tier["component"] == "MAMBA"
    )
    assert mamba["device_present"] is True
    assert blockers[-1]["snapshot_complete"] is True
    assert len(_published_records(records)) == before_published
    cache.node.component_data["mamba"].value = None
    identity = next(iter(cache._t38c_build_identities))
    namespace["_t38c_residency_reconcile"](cache, identity, "detach_sealed")
    assert len(_published_records(records)) == before_published + 1
    print("Required component snapshot and live blocker proof: PASS")


def check_bounded_outcomes(namespace, records):
    cache = _new_ready_cache(
        namespace, _context("session-bounded", 1, "build-bounded")
    )
    namespace["_t38c_note_detach"](
        cache, "node-a", "kv", "host", "bounded-host"
    )
    namespace["_t38c_note_detach"](
        cache, "node-a", "mamba", "host", "bounded-mamba-host"
    )
    _seal(cache, namespace, ("kv", "host"), ("mamba", "host"))
    identity = next(iter(cache._t38c_build_identities))
    for _ in range(8):
        namespace["_t38c_residency_reconcile"](cache, identity, "watchdog")
    pre_seal_outcomes = [
        record
        for record in records
        if record.get("evt") == "residency_barrier_outcome"
        and record.get("session_id") == "session-bounded"
        and record.get("reason") == "detach_not_sealed"
    ]
    assert len(pre_seal_outcomes) == 1
    outcomes = [
        record
        for record in records
        if record.get("evt") == "residency_barrier_outcome"
        and record.get("session_id") == "session-bounded"
        and record.get("reason") == "no_device_detach"
    ]
    assert len(outcomes) == 1
    assert outcomes[0]["reason"] == "no_device_detach"
    assert outcomes[0]["reconcile_attempt_count"] == 3
    assert outcomes[0]["reason_attempt_counts"] == {
        "detach_not_sealed": 2,
        "no_device_detach": 1,
    }
    assert outcomes[0]["suppressed_diagnostic_count"] == 1
    assert cache._t38c_residency_lifecycle[identity]["suppressed_diagnostic_count"] >= 1
    print("Bounded diagnostic outcome emission under repeated reconcile: PASS")


def main() -> None:
    check_node_sidecar_context_contract()
    check_residency_node_lookup_boundary()
    namespace = _load_barrier_functions()
    regression_namespace = namespace
    regression_records = regression_namespace["_records"]
    check_final_only_eligibility(regression_namespace, regression_records)
    check_async_durability_retry(regression_namespace, regression_records)
    check_component_snapshot_blocker(regression_namespace, regression_records)
    check_bounded_outcomes(regression_namespace, regression_records)

    # Run the original end-to-end emitter/scheduler sequence against a fresh
    # marker-backed fixture so its exact publication-count assertions remain
    # local to that sequence.
    namespace = _load_barrier_functions()
    barrier = namespace["_t38c_residency_barrier"]
    detach = namespace["_t38c_note_detach"]
    complete = namespace["_t38c_note_completion"]
    poll = namespace["_t38c_poll_residency_barriers"]
    records = namespace["_records"]

    # A completion must not publish until the final exact token completes; the
    # final completion itself is the retry trigger, without another request or
    # queue-drain poll.
    cache = _new_ready_cache(namespace)
    detach(cache, "node-a", "mamba", "host", "digest-host")
    _detach_and_complete(cache, namespace, "kv", "device", "digest-device")
    _seal(cache, namespace, ("kv", "device"), ("mamba", "host"))
    host_token = _tokens(cache, pool="mamba", tier="host")[0]
    barrier(cache, "node-a")
    assert _published_records(records) == []
    complete(cache, "mamba", "host", "digest-host", token=host_token)
    assert len(_published_records(records)) == 1
    assert _published_records(records)[0]["evt"] == "residency_barrier"
    assert _published_records(records)[0]["trace_context"] == cache.context
    assert _published_records(records)[0]["run_id"] == "run-a"
    assert _published_records(records)[0]["node_id"] == "node-a"
    assert _published_records(records)[0]["final_kv_hash"] == "hash-a"
    assert _published_records(records)[0]["cold_residency"] is True
    assert _published_records(records)[0]["result"] is True

    no_next_request = _new_ready_cache(
        namespace, _context("session-no-next-request", 1, "build-no-next-request")
    )
    detach(no_next_request, "node-a", "kv", "device", "final-device")
    detach(no_next_request, "node-a", "mamba", "host", "before-final-host")
    detach(no_next_request, "node-a", "mamba", "host", "final-host")
    _seal(no_next_request, namespace, ("kv", "device"), ("mamba", "host"))
    device_token = _token_for(
        no_next_request, "kv", "device", "final-device"
    )
    before_final_token = _token_for(
        no_next_request, "mamba", "host", "before-final-host"
    )
    final_token = _token_for(no_next_request, "mamba", "host", "final-host")
    complete(
        no_next_request,
        "kv",
        "device",
        "final-device",
        token=device_token,
    )
    complete(
        no_next_request,
        "mamba",
        "host",
        "before-final-host",
        token=before_final_token,
    )
    assert len(_published_records(records)) == 1
    complete(
        no_next_request,
        "mamba",
        "host",
        "final-host",
        token=final_token,
    )
    assert len(_published_records(records)) == 2
    complete(
        no_next_request,
        "mamba",
        "host",
        "final-host",
        token=final_token,
    )
    poll(no_next_request)
    assert len(_published_records(records)) == 2
    print("No-next-request final-token trigger: PASS")

    # A completed final token cannot publish while either the owning KV
    # release queue or an extra host-pool release queue still has work. Once
    # both queues are drained, the existing completion-triggered retry/poll
    # publishes exactly once and remains at-most-once on repeats.
    for queue_name in ("host_mem_release_queue", "extra_host_mem_release_queues"):
        queued = _new_ready_cache(
            namespace, _context(f"session-queue-{queue_name}", 1, "build-queue")
        )
        detach(queued, "node-a", "kv", "device", "queue-device")
        detach(queued, "node-a", "mamba", "host", "queue-host")
        _seal(queued, namespace, ("kv", "device"), ("mamba", "host"))
        device_token = _token_for(queued, "kv", "device", "queue-device")
        host_token = _token_for(queued, "mamba", "host", "queue-host")
        release_queues = (
            [queued.cache_controller.host_mem_release_queue]
            if queue_name == "host_mem_release_queue"
            else list(queued.cache_controller.extra_host_mem_release_queues.values())
        )
        for release_queue in release_queues:
            release_queue.put(object())
        before_queue_case = len(_published_records(records))
        complete(
            queued,
            "kv",
            "device",
            "queue-device",
            token=device_token,
        )
        complete(
            queued,
            "mamba",
            "host",
            "queue-host",
            token=host_token,
        )
        assert len(_published_records(records)) == before_queue_case
        for release_queue in release_queues:
            release_queue.get_nowait()
        poll(queued)
        assert len(_published_records(records)) == before_queue_case + 1
        poll(queued)
        assert len(_published_records(records)) == before_queue_case + 1
    print("Non-empty host-release queue barrier: PASS")

    # F-1: a second physical recycle with a different token set cannot publish
    # another event for the same exact logical identity.
    detach(cache, "node-a", "kv", "device", "digest-recycle")
    assert len(_published_records(records)) == 4
    assert not cache._t38c_residency_detached

    # F-2: same numeric node IDs in different cache instances are isolated.
    cache_a = _new_ready_cache(namespace, _context("session-a", 2, "build-a2"))
    cache_b = _new_ready_cache(namespace, _context("session-b", 1, "build-b"))
    detach(cache_a, "node-a", "mamba", "host", "digest-a-host")
    token_a = _detach_and_complete(
        cache_a, namespace, "kv", "device", "digest-a-device"
    )
    _seal(cache_a, namespace, ("kv", "device"), ("mamba", "host"))
    # B cannot consume A's token and has no own pending lifecycle.
    complete(cache_b, "kv", "device", "digest-a-device", token=token_a)
    poll(cache_b)
    assert len(_published_records(records)) == 4
    poll(cache_a)
    assert len(_published_records(records)) == 4
    host_a = _tokens(cache_a, pool="mamba", tier="host")[0]
    complete(cache_a, "mamba", "host", "digest-a-host", token=host_a)
    poll(cache_a)
    assert len(_published_records(records)) == 5

    # Concurrent release/poll: the lock may make poll observe either side of
    # the handoff, but the final fold is exactly one publication.
    concurrent = _new_ready_cache(namespace, _context("session-c", 1, "build-c"))
    detach(concurrent, "node-a", "mamba", "host", "digest-c-host")
    _detach_and_complete(
        concurrent, namespace, "kv", "device", "digest-c-device"
    )
    _seal(concurrent, namespace, ("kv", "device"), ("mamba", "host"))
    concurrent_token = _tokens(concurrent, pool="mamba", tier="host")[0]
    start = threading.Barrier(2)

    def release_host():
        start.wait()
        complete(
            concurrent,
            "mamba",
            "host",
            "digest-c-host",
            token=concurrent_token,
        )

    def poll_once():
        start.wait()
        poll(concurrent)

    threads = [
        threading.Thread(target=release_host),
        threading.Thread(target=poll_once),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    poll(concurrent)
    assert len(_published_records(records)) == 6

    # A stale pending generation cannot be folded against the current node
    # context. Restoring the old context proves the pending state was retained.
    stale = _new_ready_cache(namespace, _context("session-d", 1, "build-d1"))
    detach(stale, "node-a", "mamba", "host", "digest-d-host")
    _detach_and_complete(stale, namespace, "kv", "device", "digest-d-device")
    stale.context = _context("session-d", 2, "build-d2")
    stale._t38c_build_identities = {
        namespace["_t38c_residency_identity"](
            stale.context, stale.node.id, stale.node.final_hash
        )
    }
    stale._t38c_durability_ready = set(stale._t38c_build_identities)
    poll(stale)
    assert len(_published_records(records)) == 6

    def no_barrier(cache, *, host=True, device=True):
        if device:
            _detach_and_complete(cache, namespace, "kv", "device", "digest-test-device")
        if host:
            _detach_and_complete(cache, namespace, "mamba", "host", "digest-test-host")
        barrier(cache, "node-a")

    # Existing fail-closed predicates remain enforced.
    host_only = _new_ready_cache(namespace, _context("session-e", 1, "build-e"))
    no_barrier(host_only, host=True, device=False)
    partial = _new_ready_cache(namespace, _context("session-f", 1, "build-f"))
    detach(partial, "node-a", "kv", "device", "partial-device")
    barrier(partial, "node-a")
    not_durable = _new_ready_cache(namespace, _context("session-g", 1, "build-g"))
    not_durable._t38c_durability_ready.clear()
    no_barrier(not_durable)
    ambiguous = _new_ready_cache(namespace, _context("session-h", 1, "build-h"))
    ambiguous.context["warm_rid"] = "warm-h"
    no_barrier(ambiguous)
    forced = _new_ready_cache(namespace, _context("session-i", 1, "build-i"))
    forced.node.forced_miss_tombstone = True
    no_barrier(forced)

    # F-3: changing only the authoritative run boundary changes the complete
    # residency identity and therefore cannot collide with stale run state.
    run_a = namespace["_t38c_residency_identity"](
        _context("session-run", 1, "build-run", run_id="run-a"),
        "node-a",
        "hash-a",
    )
    run_b = namespace["_t38c_residency_identity"](
        _context("session-run", 1, "build-run", run_id="run-b"),
        "node-a",
        "hash-a",
    )
    assert run_a == ("run-a", "session-run", 1, "build-run", "node-a", "hash-a")
    assert run_b == ("run-b", "session-run", 1, "build-run", "node-a", "hash-a")
    assert run_a != run_b
    print("F-3 run-ID collision probe: PASS")

    # F-4: direct residency-fold boundary cases must be absence-only and must
    # not mutate the cache-owned lifecycle ledger.
    _assert_invalid_context_case(namespace, records, "none-trace-context", None)
    _assert_invalid_context_case(namespace, records, "absent-trace-context", {})
    complete_context = _context("session-invalid", 1, "build-invalid")
    for missing_field in (
        "schema_version",
        "run_id",
        "session_id",
        "session_generation",
        "build_rid",
        "warm_rid",
        "node_id",
        "final_kv_hash",
    ):
        missing = dict(complete_context)
        missing.pop(missing_field)
        _assert_invalid_context_case(
            namespace, records, f"missing-{missing_field}", missing
        )
    _assert_invalid_context_case(
        namespace,
        records,
        "node-context-mismatch",
        dict(complete_context, node_id="node-other"),
    )

    _run_real_scheduler_checkpoint_probe(namespace)

    namespace["_durable_enabled"][0] = False
    marker_off = _new_ready_cache(namespace, _context("session-j", 1, "build-j"))
    _detach_and_complete(marker_off, namespace, "kv", "device", "off-device")
    poll(marker_off)
    assert len(_published_records(records)) == 8

    print("P0 residency-barrier emitter focused checks: PASS")


if __name__ == "__main__":
    main()
