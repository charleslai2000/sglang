#!/usr/bin/env python3
"""Log-only T003 request-lock lifecycle snapshots at existing release seams."""
from __future__ import annotations


def _t003_lock_snapshot(cache, req, phase: str) -> None:
    """Write bounded target-scoped node/owner counters when T38C markers are on."""
    if req is None or not getattr(cache, "_t003_lock_audit_enabled", False):
        return
    try:
        import json
        import os
        import time
        from sglang.srt.mem_cache.unified_cache.component_type import ComponentType

        rid = str(getattr(req, "rid", ""))
        target_rid = getattr(cache, "_t003_lock_audit_target_rid", None)
        session = getattr(req, "session", None)
        session_id = getattr(session, "session_id", None)
        target_session = getattr(cache, "_t003_lock_audit_target_session", None)
        receipt_node = getattr(req, "cache_lock_node", None)
        node = receipt_node if receipt_node is not None else getattr(req, "last_node", None)
        if rid != target_rid and session_id != target_session:
            return
        if node is None:
            node_id = None
            lock_refs = {}
            host_refs = {}
            ancestors = []
            device_values = {}
            host_values = {}
        else:
            node_id = int(node)
            tree_node = cache.tree_core.node_by_id(node_id)
            ancestors = []
            cur = tree_node
            while cur is not None:
                ancestors.append({
                    "node_id": int(cur.id),
                    "component_lock_refs": {
                        ct.name: int(cur.component_data[ct].lock_ref)
                        for ct in (ComponentType.FULL, ComponentType.MAMBA)
                        if ct in cur.component_types
                    },
                })
                cur = cur.parent
            lock_refs = ancestors[0]["component_lock_refs"]
            host_refs = {
                ct.name: int(tree_node.component_data[ct].host_lock_ref)
                for ct in (ComponentType.FULL, ComponentType.MAMBA)
                if ct in tree_node.component_types
            }
            device_values = {
                ct.name: tree_node.component_data[ct].value is not None
                for ct in (ComponentType.FULL, ComponentType.MAMBA)
                if ct in tree_node.component_types
            }
            host_values = {
                ct.name: tree_node.component_data[ct].host_value is not None
                for ct in (ComponentType.FULL, ComponentType.MAMBA)
                if ct in tree_node.component_types
            }
        slot = cache.session.slots.get(session_id) if session_id is not None else None
        slot_receipt = None if slot is None else {
            "node_id": int(slot.cache_lock_node) if slot.cache_lock_node is not None else None,
            "params": repr(slot.cache_lock_params),
        }
        record = {
            "evt": "request_lock_lifecycle",
            "phase": phase,
            "rid": rid,
            "session_id": session_id,
            "node_id": node_id,
            "receipt_node_id": int(receipt_node) if receipt_node is not None else None,
            "receipt_params": repr(getattr(req, "cache_lock_params", None)),
            "slot_receipt": slot_receipt,
            "lock_refs": lock_refs,
            "host_lock_refs": host_refs,
            "device_values": device_values,
            "host_values": host_values,
            "full_path_refs": ancestors,
            "ts_wall_ns": time.time_ns(),
        }
        path = os.environ.get("T38C_PROBE_LOG", "/tmp/t38c-probe.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    except Exception:
        # Diagnostic only: never alter scheduler/cache behavior.
        return
