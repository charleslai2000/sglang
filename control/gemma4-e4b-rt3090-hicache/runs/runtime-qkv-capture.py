"""Capture exact Gemma4 normalized and RoPE Q/K/V at selected layers."""
import os
from pathlib import Path
import torch


def capture(module, hidden_states, positions, forward_batch):
    path = os.getenv("GEMMA4_COMPONENT_STATE_FILE")
    if not path or forward_batch.batch_size != 1:
        return
    layer_id = int(module.layer_id)
    if layer_id not in (17, 18, 19, 20, 21, 22, 23):
        return
    qkv, _ = module.qkv_proj(hidden_states)
    q, k, v = qkv.split([module.q_size, module.kv_size, module.kv_size], dim=-1)
    is_shared = module.is_kv_shared_layer and module.kv_shared_layer_index is not None
    if module.q_norm.scale_shift == 0.0 and module.k_norm.scale_shift == 0.0 and not module.v_norm.with_scale and (q.is_cuda or q.is_xpu):
        # We must not execute the fused in-place norm separately: record only
        # pre-normalized projections and let production code perform the norm.
        return
    qn = module.q_norm(q.unflatten(-1, (module.num_heads, module.head_dim))).flatten(-2, -1)
    kn = None if is_shared else module.k_norm(k.unflatten(-1, (module.num_kv_heads, module.head_dim))).flatten(-2, -1)
    vn = None if is_shared else module.v_norm(v.unflatten(-1, (module.num_kv_heads, module.head_dim)))
    dummy = torch.zeros_like(qn[:, : module.kv_size]) if kn is None else kn
    qr, kr = module.rotary_emb(positions, qn, dummy if kn is None else kn)
    rec = {
        "layer": layer_id,
        "forward_id": getattr(forward_batch, "gemma4_forward_id", None),
        "rid": forward_batch.rids[0] if forward_batch.rids and len(forward_batch.rids)==1 else None,
        "positions": positions.detach().cpu().tolist(),
        "input_ids": forward_batch.input_ids.detach().cpu().tolist(),
        "qkv_pre_norm": qkv.detach().float().cpu().tolist(),
        "q_pre_rope": qn.detach().float().cpu().tolist(),
        "k_pre_rope": None if kn is None else kn.detach().float().cpu().tolist(),
        "v_pre_attn": None if vn is None else vn.detach().float().cpu().tolist(),
        "q_post_rope": qr.detach().float().cpu().tolist(),
        "k_post_rope": None if kn is None else kr.detach().float().cpu().tolist(),
        "shared": bool(is_shared),
    }
    Path(path, f"qkv.layer{layer_id}.json").write_text(__import__('json').dumps(rec))
