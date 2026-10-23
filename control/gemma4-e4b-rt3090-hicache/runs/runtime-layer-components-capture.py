"""Tiny external callback for RID-bound component snapshots."""
import json
import os
from pathlib import Path
import torch


def capture(module, boundary, tensor, positions, forward_batch):
    path = os.getenv("GEMMA4_COMPONENT_STATE_FILE")
    if not path or forward_batch.batch_size != 1:
        return
    configured_layer = os.getenv("GEMMA4_COMPONENT_LAYER")
    configured_layers = os.getenv("GEMMA4_COMPONENT_LAYERS")
    if configured_layers is not None and int(module.layer_id) not in {int(x) for x in configured_layers.split(",")}:
        return
    if configured_layers is None and configured_layer is not None and int(module.layer_id) != int(configured_layer):
        return
    min_tokens = int(os.getenv("GEMMA4_COMPONENT_MIN_TOKENS", "1"))
    if forward_batch.input_ids.numel() < min_tokens:
        return
    layer_id = int(module.layer_id)
    rec = {
        "layer": layer_id,
        "boundary": boundary,
        "forward_id": getattr(forward_batch, "gemma4_forward_id", None),
        "rid": forward_batch.rids[0] if forward_batch.rids and len(forward_batch.rids) == 1 else None,
        "batch_slot_offsets": getattr(forward_batch, "batch_slot_offsets", None).detach().cpu().tolist() if getattr(forward_batch, "batch_slot_offsets", None) is not None else [0, int(forward_batch.input_ids.numel())],
        "step_input_ids": forward_batch.input_ids.detach().cpu().tolist(),
        "step_positions": positions.detach().cpu().tolist(),
        "seq_lens": forward_batch.seq_lens.detach().cpu().tolist(),
        "extend_seq_lens": forward_batch.extend_seq_lens.detach().cpu().tolist() if forward_batch.extend_seq_lens is not None else None,
        "extend_prefix_lens": forward_batch.extend_prefix_lens.detach().cpu().tolist() if forward_batch.extend_prefix_lens is not None else None,
        "out_cache_loc": forward_batch.out_cache_loc.detach().cpu().tolist() if forward_batch.out_cache_loc is not None else None,
        "req_to_token_row": None,
        "req_pool_indices": forward_batch.req_pool_indices.detach().cpu().tolist() if forward_batch.req_pool_indices is not None else None,
        "forward_mode": forward_batch.forward_mode.name,
        "is_prefill_only": bool(forward_batch.is_prefill_only),
        "batch_slot": 0,
        "shape": list(tensor.shape),
        "dtype": str(tensor.dtype),
        "model_identity": json.loads(os.environ.get("GEMMA4_MODEL_IDENTITY", "{}")),
        "model_sha256": os.environ.get("GEMMA4_MODEL_SHA256"),
        "value": tensor.detach().float().cpu().tolist(),
    }
    rec["capture_scope"] = "scheduler_forward_tensor"
    if hasattr(forward_batch, "forward_mode") and str(boundary).startswith(("extend_attention_fwd.", "extend_attention_fwd_unified.")):
        rec["capture_scope"] = "triton_kernel_input"
        rec["forward_mode"] = forward_batch.forward_mode.name
        rec["model_identity"] = json.loads(os.environ.get("GEMMA4_MODEL_IDENTITY", "{}"))
        rec["model_sha256"] = os.environ.get("GEMMA4_MODEL_SHA256")
        rec["shape"] = list(tensor.shape)
        rec["dtype"] = str(tensor.dtype)
        rec["value"] = tensor.detach().float().cpu().tolist()
        target = Path(path) / f"component.{rec['rid']}.{rec['forward_id']}.layer{layer_id}.{boundary}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x") as f:
            json.dump(rec, f)
            f.flush()
            os.fsync(f.fileno())
        return
    if tensor.shape[0] != positions.numel() or positions.numel() != forward_batch.input_ids.numel():
        raise RuntimeError(f"Gemma component capture range mismatch: layer={layer_id} boundary={boundary} tensor={tensor.shape[0]} positions={positions.numel()} input_ids={forward_batch.input_ids.numel()}")
    if forward_batch.gemma4_forward_id is None:
        raise RuntimeError("component capture has no per-forward UUID")
    if forward_batch.rids is None or len(forward_batch.rids) != forward_batch.batch_size:
        raise RuntimeError("component capture request identities do not align with batch slots")
    rec["batch_slot"] = 0
    rec["batch_slot_rid"] = forward_batch.rids[0]
    rec["batch_slot_seq_len"] = int(forward_batch.seq_lens[0])
    rec["batch_slot_req_pool_index"] = int(forward_batch.req_pool_indices[0])
    if forward_batch.forward_mode.is_extend():
        if int(module.layer_id) in (17, 23) and forward_batch.extend_prefix_lens is not None and int(forward_batch.extend_prefix_lens[0]) == 0:
            from sglang.srt.model_executor.forward_context import get_req_to_token_pool
            row = forward_batch.req_pool_indices[0]
            seq_len = int(forward_batch.seq_lens[0])
            rec["req_to_token_row"] = get_req_to_token_pool().req_to_token[row, :seq_len].detach().cpu().tolist()
        if forward_batch.extend_seq_lens is None or forward_batch.extend_prefix_lens is None:
            raise RuntimeError("extend component capture missing per-request prefix/query lengths")
        if rec["rid"] is None:
            raise RuntimeError("single-request component capture cannot bind scheduler request identity")
        if forward_batch.extend_prefix_lens_cpu is None or forward_batch.extend_seq_lens_cpu is None:
            raise RuntimeError("extend component capture lacks CPU query-range bounds")
        rec["extend_token_range"] = [0, int(tensor.shape[0])]
        rec["decode_token_range"] = None
        rec["extend_seq_lens"] = forward_batch.extend_seq_lens.detach().cpu().tolist()
        rec["extend_prefix_lens"] = forward_batch.extend_prefix_lens.detach().cpu().tolist()
        rec["token_context_positions"] = positions.detach().cpu().tolist()
        prefix_len = int(forward_batch.extend_prefix_lens_cpu[0])
        query_len = int(forward_batch.extend_seq_lens_cpu[0])
        rec["query_token_range_in_request"] = [prefix_len, prefix_len + query_len]
        if len(rec["token_context_positions"]) != tensor.shape[0] or tensor.shape[0] != query_len or len(rec["step_input_ids"]) != tensor.shape[0]:
            raise RuntimeError("extend component tensor cannot be proven to align with request token range")
        if rec["token_context_positions"] != positions.detach().cpu().tolist():
            raise RuntimeError("extend query positions disagree with the component tensor token range")
        rec["extend_token_ids_sha256"] = __import__("hashlib").sha256(json.dumps(rec["step_input_ids"],separators=(",",":")).encode()).hexdigest()
    elif forward_batch.forward_mode.is_decode():
        rec["extend_token_range"] = None
        rec["decode_token_range"] = [0, int(tensor.shape[0])]
        rec["token_context_positions"] = positions.detach().cpu().tolist()
        if tensor.shape[0] != forward_batch.batch_size:
            raise RuntimeError("decode component tensor rows do not align with batch slots")
    else:
        raise RuntimeError(f"unsupported component capture mode {forward_batch.forward_mode.name}")
    target = Path(path) / f"component.{rec['rid']}.{rec['forward_id']}.layer{layer_id}.{boundary}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x") as f:
        json.dump(rec, f)
        f.flush()
        os.fsync(f.fileno())
