#!/usr/bin/env python3
"""Opt-in external SGLang hook: observe real SWA slots/window and owner KV."""
import json
import os
import threading
import uuid
from pathlib import Path

_lock = threading.Lock()
_done = False
_forward_count = 0
_record = {}


def _tensor(x):
    if x is None:
        return None
    try:
        return x.detach().to("cpu").tolist()
    except Exception:
        return {"type": type(x).__name__}


def capture(backend, forward_batch, layer, model=None):
    """Called after extend attention; fail closed and write an atomic observation."""
    global _done, _forward_count, _record
    path = os.getenv("GEMMA4_RUNTIME_STATE_FILE")
    if not path or _done:
        return
    try:
        seq = getattr(forward_batch, "seq_lens", None)
        if forward_batch.batch_size != 1 or seq is None or int(seq[0].item()) < 513:
            return
        layer_id = int(layer.layer_id)
        if layer_id not in (18, 23):
            return
        with _lock:
            if _done:
                return
            pool = backend.token_to_kv_pool
            req = forward_batch.req_pool_indices
            row = int(req[0].item())
            n = int(seq[0].item())
            req_slots = backend.req_to_token[row, :n].detach().clone()
            allocator = getattr(backend, "token_to_kv_pool_allocator", None)
            mapping = getattr(allocator, "full_to_swa_index_mapping", None)
            if mapping is None:
                mapping = getattr(getattr(allocator, "_kvcache", None), "full_to_swa_index_mapping", None)
            if mapping is None:
                mapping = getattr(pool, "full_to_swa_index_mapping", None)
            swa_slots = mapping[req_slots].detach().clone() if mapping is not None else None
            full_slots = req_slots
            if getattr(backend, "_translate_kv_loc", None) is not None:
                full_slots = backend._translate_kv_loc(full_slots)
            full_slots = full_slots.detach().clone()
            metadata = backend.forward_metadata

            if not _record:
                if forward_batch.rids and len(forward_batch.rids) == 1:
                    rid = forward_batch.rids[0]
                else:
                    rid = None
                _record = {
                    "capture_link_id": uuid.uuid4().hex,
                    "rid": rid,
                    "forward_id": getattr(forward_batch, "gemma4_forward_id", None),
                    "seq_len": n,
                    "req_pool_indices": _tensor(req),
                    "req_to_token_slots": _tensor(req_slots),
                    "kernel_full_kv_indices": _tensor(full_slots),
                    "full_to_swa_mapping": _tensor(swa_slots),
                    "out_cache_loc": _tensor(getattr(forward_batch, "out_cache_loc", None)),
                    "input_ids": _tensor(getattr(forward_batch, "input_ids", None)),
                    "positions": _tensor(getattr(forward_batch, "positions", None)),
                    "forward_mode": str(getattr(forward_batch, "forward_mode", None)),
                    "window_kv_indptr": _tensor(getattr(metadata, "window_kv_indptr", None)),
                    "window_kv_indices": _tensor(getattr(metadata, "window_kv_indices", None)),
                    "prefix_lens": _tensor(getattr(forward_batch, "extend_prefix_lens", None)),
                    "extend_seq_lens": _tensor(getattr(forward_batch, "extend_seq_lens", None)),
                    "window_kv_offsets": _tensor(getattr(metadata, "window_kv_offsets", None)),
                    "kv_indptr": _tensor(getattr(metadata, "kv_indptr", None)),
                    "kv_indices": _tensor(getattr(metadata, "kv_indices", None)),
                    "pool_dtype": str(pool.dtype),
                    "sliding_window_size": backend.sliding_window_size,
                    "layers_mapping": {str(k): list(v) for k, v in pool.layers_mapping.items()},
                    "pool_layer_ids": {
                        "18": int(pool.layers_mapping[18][0]),
                        "23": int(pool.layers_mapping[23][0]),
                    },
                    "owners": {},
                }

            is_swa = bool(pool.layers_mapping.get(layer_id, (None, False))[1])
            write_locs = getattr(forward_batch, "out_cache_loc", None)
            if write_locs is None:
                write_locs = swa_slots if is_swa else full_slots
            write_locs = write_locs.detach().clone()
            cache_locs = (
                pool.translate_loc_from_full_to_swa(write_locs)
                if is_swa and hasattr(pool, "translate_loc_from_full_to_swa")
                else write_locs
            )
            k_buffer, v_buffer = pool.get_kv_buffer(layer_id)
            sample_locs = cache_locs[-min(2, n) :]
            owner = {
                "owner_layer": layer_id,
                "pool_layer_id": int(pool.layers_mapping[layer_id][0]),
                "is_swa": is_swa,
                "write_locs": _tensor(write_locs),
                "cache_locs": _tensor(cache_locs),
                "cache_dtype": str(k_buffer.dtype),
                "cache_k_shape": list(k_buffer.shape),
                "cache_v_shape": list(v_buffer.shape),
                "cached_k_sample": _tensor(k_buffer[sample_locs]),
                "cached_v_sample": _tensor(v_buffer[sample_locs]),
            }
            # Preserve model-level scale evidence when the exact runner model
            # can be associated with this backend; absence remains explicit.
            owner_layer = None
            if model is not None:
                owner_layer = model.model.layers[layer_id].self_attn.attn
            owner["scale_binding"] = owner_layer is not None
            owner["layer_k_scale_float"] = getattr(owner_layer, "k_scale_float", None)
            owner["layer_v_scale_float"] = getattr(owner_layer, "v_scale_float", None)
            owner["layer_k_scale"] = _tensor(getattr(owner_layer, "k_scale", None))
            owner["layer_v_scale"] = _tensor(getattr(owner_layer, "v_scale", None))
            _record["owners"][str(layer_id)] = owner
            if set(_record["owners"]) == {"18", "23"}:
                _record["complete"] = True
                _done = True
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(f"{target.name}.tmp.{os.getpid()}")
            temp.write_text(json.dumps(_record, sort_keys=True))
            os.replace(temp, target)
    except Exception as exc:
        Path(path + ".error").write_text(repr(exc))
        raise
