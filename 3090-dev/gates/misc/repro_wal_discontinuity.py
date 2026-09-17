#!/usr/bin/env python3
"""Metadata-only reproduction of the WAL sequence discontinuity (l3-disk-reclaim).

Runs the exact metadata kernel that raised the recorded failure:
    read_manifest + read_current + resolve_wal_range + iter_segment_frames + replay_records

extent_metadata.py is pure stdlib except one import (PoolName). We register a
faithful PoolName stub and load the module by file path, so no torch/sglang
package import and no hicache.data payload byte is ever opened or read.
"""
import enum, importlib.util, json, os, sys, types

META = "/opt/sglang/local-prod-v1/src/python/sglang/srt/mem_cache/storage/extent/extent_metadata.py"
SUFFIX = "_-data-models-qwen35-9b-w4a16_0_1"


def load_metadata_module():
    class PoolName(str, enum.Enum):
        KV = "kv"
        MAMBA = "mamba"
        SWA = "swa"
        INDEXER = "indexer"
        DEEPSEEK_V4_C4 = "deepseek_v4_c4"
        DEEPSEEK_V4_C4_INDEXER = "deepseek_v4_c4_indexer"
        DEEPSEEK_V4_C128 = "deepseek_v4_c128"
        DEEPSEEK_V4_C4_STATE = "deepseek_v4_c4_state"
        DEEPSEEK_V4_C4_INDEXER_STATE = "deepseek_v4_c4_indexer_state"
        DEEPSEEK_V4_C128_STATE = "deepseek_v4_c128_state"
        DRAFT = "draft"
        DRAFT_INDEXER = "draft_indexer"
        DRAFT_SWA = "draft_swa"

        def __str__(self):
            return self.value

    for name in ("sglang", "sglang.srt", "sglang.srt.mem_cache"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    stub = types.ModuleType("sglang.srt.mem_cache.hicache_storage")
    stub.PoolName = PoolName
    sys.modules["sglang.srt.mem_cache.hicache_storage"] = stub

    spec = importlib.util.spec_from_file_location("extent_metadata", META)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["extent_metadata"] = mod
    spec.loader.exec_module(mod)
    return mod


def run(m, store):
    manifest = m.manifest_path(store, SUFFIX)
    cur = m.current_path(store, SUFFIX)
    state = m.read_manifest(manifest)
    gen = m.read_current(cur)
    wr = m.resolve_wal_range(state, gen)
    num_slots = state.file_size // state.extent_size
    info = {
        "store": store,
        "manifest_checkpoint_lsn": state.checkpoint_lsn,
        "manifest_wal_floor": state.wal_floor,
        "manifest_file_size": state.file_size,
        "manifest_extent_size": state.extent_size,
        "manifest_num_slots": num_slots,
        "wal_current_generation": gen,
        "wal_range": [wr.start_generation, wr.end_generation],
        "wal_pending_rotation": wr.pending_rotation,
        "segment_first_seq": {},
        "metadata_bytes_read": os.path.getsize(manifest),
    }
    frames = []
    for g in wr.generations:
        p = m.segment_path(store, SUFFIX, g)
        fr = m.iter_segment_frames(p, active=(g == gen))
        if len(fr):
            info["segment_first_seq"][f"wal.{g}"] = fr[0].seq
        info["metadata_bytes_read"] += os.path.getsize(p)
        frames.append(fr)
    info["payload_bytes_read"] = 0
    try:
        m.replay_records(frames, state, num_slots=num_slots)
        info["result"] = "NO_ERROR (replay succeeded)"
    except m.RecoveryError as e:
        info["result"] = "RecoveryError"
        info["error_message"] = str(e)
        info["error_failure_class"] = getattr(e, "failure_class", None)
        info["error_lsn"] = getattr(e, "lsn", None)
    return info


if __name__ == "__main__":
    m = load_metadata_module()
    print(json.dumps([run(m, s) for s in sys.argv[1:]], indent=2))
