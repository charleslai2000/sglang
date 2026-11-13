"""Opt-in Eager numerical capture for the Gemma4 Q4_0/FP8-KV gate."""

import json
import os
from pathlib import Path

import torch


def capture_l5_operator(stage, layer_id, value, forward_batch, **metadata):
    """Persist one selected layer position for an explicitly named request."""
    if os.environ.get("G2_L5_CAPTURE") != "1":
        return
    target_layer = int(os.environ.get("G2_CAPTURE_LAYER", "5"))
    if int(layer_id) != target_layer:
        return
    if torch.cuda.is_current_stream_capturing():
        return
    stages = os.environ.get("G2_CAPTURE_STAGES")
    if stages and stage not in {item for item in stages.split(",") if item}:
        return
    expected = os.environ.get("G2_L5_CAPTURE_RID")
    if not forward_batch.rids or forward_batch.rids[0] != expected:
        return
    path = os.environ.get("G2_L5_CAPTURE_FILE")
    if not path:
        raise RuntimeError("G2 Layer-5 capture requires G2_L5_CAPTURE_FILE")
    ids = forward_batch.input_ids.detach().cpu().reshape(-1)
    positions = forward_batch.positions.detach().cpu().reshape(-1)
    if value.shape[0] != ids.numel():
        raise RuntimeError(f"Layer-5 {stage} rows are not aligned with ForwardBatch")
    identity = json.loads(os.environ.get("GEMMA4_MODEL_IDENTITY", "{}"))
    wanted_position = os.environ.get("G2_L5_CAPTURE_POSITION")
    for i in range(ids.numel()):
        position = int(positions[i])
        if wanted_position is not None and position != int(wanted_position):
            continue
        rec = {
            "schema": 1, "stage": stage, "layer": target_layer,
            "forward_id": forward_batch.gemma4_forward_id,
            "rid": list(forward_batch.rids),
            "forward_mode": forward_batch.forward_mode.name,
            "position": position, "input_id": int(ids[i]),
            "model_identity": identity,
            "value": value[i:i+1].detach().float().cpu().clone(),
            **metadata,
        }
        target = f"{path}.{rec['forward_id']}.layer{target_layer}.pos{position}.{stage}.pt"
        save_gemma4_capture(rec, target)


def snapshot_gemma4_logits_capture(logits: torch.Tensor, forward_batch) -> dict:
    """Clone logits and mutable ForwardBatch metadata before scheduler reuse."""
    return {
        "output": logits.detach().float().cpu().clone(),
        "input_ids": forward_batch.input_ids.detach().cpu().clone(),
        "positions": forward_batch.positions.detach().cpu().clone(),
        "extend_seq_lens": (
            forward_batch.extend_seq_lens.detach().cpu().clone()
            if forward_batch.extend_seq_lens is not None
            else None
        ),
        "extend_seq_lens_cpu": (
            list(forward_batch.extend_seq_lens_cpu)
            if forward_batch.extend_seq_lens_cpu is not None
            else None
        ),
        "extend_prefix_lens": (
            forward_batch.extend_prefix_lens.detach().cpu().clone()
            if forward_batch.extend_prefix_lens is not None
            else None
        ),
    }


def save_gemma4_capture(record, path):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise RuntimeError(f"refusing to overwrite Gemma4 capture: {target}")
    temp = target.with_name(f"{target.name}.tmp.{os.getpid()}")
    if temp.exists():
        raise RuntimeError(f"capture temporary path already exists: {temp}")
    try:
        if target.suffix == ".manifest":
            with temp.open("x", encoding="utf-8") as stream:
                json.dump(record, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
        else:
            torch.save(record, temp)
        os.link(temp, target)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def _load_trace(target):
    path = Path(target)
    if path.exists():
        return path, torch.load(path, map_location="cpu", weights_only=False)
    return path, {"stages": {}}


def capture_g2_4k_attention_snapshot(layer, q, k_ext, v_ext, pool, kv_indptr, kv_indices, kv_descale, vv_descale, sliding_window_size, sm_scale, forward_batch):
    base = os.environ.get("G2_4K_ATTN_FILE")
    if os.environ.get("G2_4K_BOUNDARY_ALL") != "1":
        return
    if not base or torch.cuda.is_current_stream_capturing():
        return
    if os.environ.get("G2_4K_ATTN_SNAPSHOT") != "1":
        return
    if int(forward_batch.positions[0].item()) != 2048 or int(forward_batch.positions[-1].item()) != 4095:
        return
    if forward_batch.positions.numel() != 2048 or int(forward_batch.positions[0].item()) != 2048 or int(forward_batch.positions[-1].item()) != 4095:
        return
    layer_id = int(getattr(layer, "g2_logical_layer_id", layer.layer_id))
    wanted = {int(x) for x in os.environ.get("G2_4K_ATTN_LAYERS", "0,1,2,3,4").split(",") if x}
    if layer_id not in wanted:
        return
    selected_positions = {2048, 2558, 2559, 3069, 3070, 3580, 3581, 4091, 4092, 4095}
    rows = [i for i, pos in enumerate(forward_batch.positions.detach().cpu().tolist()) if int(pos) in selected_positions]
    if not rows:
        return
    ptr = kv_indptr.detach().cpu().tolist()
    slots = kv_indices[ptr[0]:ptr[1]].detach()
    kb, vb = pool.get_kv_buffer(layer.layer_id)
    rec = {
        "layer": layer_id, "positions": forward_batch.positions[rows].cpu(),
        "input_ids": forward_batch.input_ids[rows].cpu(), "q": q[rows].detach().cpu(),
        "prefix_slots": slots.cpu(), "prefix_k": kb[slots].detach().cpu(), "prefix_v": vb[slots].detach().cpu(),
        "prefix_k_dequant": (kb[slots].to(q.dtype) * float(kv_descale)).detach().cpu(),
        "prefix_v_dequant": (vb[slots].to(q.dtype) * float(vv_descale)).detach().cpu(),
        "prefix_is_fp8_storage": str(kb.dtype) == "torch.uint8" or str(kb.dtype) == "torch.float8_e5m2",
        "k_store_dtype": str(getattr(pool, "dtype", kb.dtype)),
        "current_k": k_ext.detach().cpu(), "current_v": v_ext.detach().cpu(),
        "kv_dtype": str(kb.dtype), "scale": float(sm_scale),
        "k_scale": float(kv_descale), "v_scale": float(vv_descale),
        "window": int(sliding_window_size),
        "logit_cap": float(getattr(layer, "logit_cap", 0.0) or 0.0),
        "logit_capping_method": str(getattr(layer, "logit_capping_method", "none")),
        "prefix_positions": torch.arange(int(forward_batch.extend_prefix_lens[0].item())-len(slots), int(forward_batch.extend_prefix_lens[0].item())),
        "current_start": int(forward_batch.extend_prefix_lens[0].item()),
    }
    save_gemma4_capture(rec, f"{base}.layer{layer_id}.pt")


def capture_g2_4k_current_kv(layer, loc, kbuf, vbuf, k, v, forward_batch):
    base = os.environ.get("G2_4K_KV_WRITE_FILE")
    if not base or torch.cuda.is_current_stream_capturing() or os.environ.get("G2_4K_BOUNDARY_ALL") != "1":
        return
    wanted_layers = {int(x) for x in os.environ.get("G2_4K_KV_LAYERS", "0,1,2,3,4").split(",") if x}
    layer_id = int(getattr(layer, "g2_logical_layer_id", layer.layer_id))
    if layer_id not in wanted_layers:
        return
    positions = forward_batch.positions.detach().cpu().tolist()
    wanted = {int(x) for x in os.environ.get("G2_4K_BOUNDARY_POSITIONS", "4095").split(",") if x}
    rows = [i for i, pos in enumerate(positions) if pos in wanted]
    physical = loc.detach().cpu().tolist()
    for i in rows:
        save_gemma4_capture({
            "layer": layer_id, "position": int(positions[i]),
            "physical_slot": int(physical[i]),
            "logical_slot": int(forward_batch.out_cache_loc[i].item()),
            "input_id": int(forward_batch.input_ids[i].item()),
            "kv_dtype": str(kbuf.dtype),
            "k_input": k[i:i+1].detach().cpu(),
            "v_input": v[i:i+1].detach().cpu(),
            "k_stored": kbuf[loc[i:i+1]].detach().cpu(),
            "v_stored": vbuf[loc[i:i+1]].detach().cpu(),
        }, f"{base}.layer{layer_id}.pos{positions[i]}")


def capture_g2_4k_attention_input(layer, q, k_ext, v_ext, pool, kv_indptr, kv_indices, kv_descale, vv_descale, sliding_window_size, sm_scale, forward_batch):
    """Persist selected query and current-chunk K/V rows from one 4K forward."""
    base = os.environ.get("G2_4K_ATTN_FILE")
    if not base or torch.cuda.is_current_stream_capturing() or os.environ.get("G2_4K_BOUNDARY_ALL") != "1":
        return
    layer_id = int(getattr(layer, "g2_logical_layer_id", layer.layer_id))
    if layer_id != int(os.environ.get("G2_4K_ATTN_LAYER", "4")):
        return
    positions = forward_batch.positions
    wanted = {int(x) for x in os.environ.get("G2_4K_BOUNDARY_POSITIONS", "4095").split(",") if x}
    rows = [i for i, pos in enumerate(positions.detach().cpu().tolist()) if pos in wanted]
    if not rows:
        return
    ptr = kv_indptr.detach().cpu().tolist()
    all_slots = kv_indices[ptr[0]:ptr[1]].detach()
    prefix_positions = list(range(int(forward_batch.extend_prefix_lens[0].item()) - all_slots.numel(), int(forward_batch.extend_prefix_lens[0].item())))
    wanted_positions = sorted(set(int(x) for x in positions[rows].detach().cpu().tolist()))
    selected_slots = []
    for query_pos in wanted_positions:
        first = max(0, query_pos - int(sliding_window_size))
        prefix_idx = [j for j, p in enumerate(prefix_positions) if first <= p < int(forward_batch.extend_prefix_lens[0].item())]
        selected_slots.extend(all_slots[prefix_idx].detach().cpu().tolist())
    slots = all_slots
    kbuf, vbuf = pool.get_kv_buffer(layer.layer_id)
    current_positions = positions.detach().cpu().tolist()
    extend_start_pos = int(forward_batch.extend_prefix_lens[0].item())
    k_current = torch.stack([k_ext[i] for i in range(k_ext.shape[0])]).detach().cpu()
    v_current = torch.stack([v_ext[i] for i in range(v_ext.shape[0])]).detach().cpu()
    # Retain the full current chunk and exact prefix pool sequence; each query
    # reference applies causal and sliding-window masks by logical position.
    record = {
        "schema": 1, "layer": layer_id,
        "positions": positions[rows].detach().cpu(),
        "all_current_positions": torch.arange(extend_start_pos, extend_start_pos + k_ext.shape[0]),
        "all_k_current": k_current, "all_v_current": v_current,
        "input_ids": forward_batch.input_ids[rows].detach().cpu(),
        "forward_mode": forward_batch.forward_mode.name,
        "model_identity": json.loads(os.environ.get("GEMMA4_MODEL_IDENTITY", "{}")),
        "q": q[rows].detach().cpu(),
        "k_prefix_raw": kbuf[slots].detach().cpu(), "v_prefix_raw": vbuf[slots].detach().cpu(),
        "k_prefix_dequant": (kbuf[slots].to(q.dtype) * float(kv_descale)).detach().cpu(),
        "v_prefix_dequant": (vbuf[slots].to(q.dtype) * float(vv_descale)).detach().cpu(),
        "k_extend": k_ext.detach().cpu(), "v_extend": v_ext.detach().cpu(),
        "kv_slots": slots.cpu(), "kv_indptr": ptr,
        "kv_dtype": str(kbuf.dtype), "k_scale": float(kv_descale),
        "v_scale": float(vv_descale), "sm_scale": float(sm_scale),
        "sliding_window_size": int(sliding_window_size),
        "query_positions": positions[rows].detach().cpu(),
        "extend_prefix_lens": forward_batch.extend_prefix_lens.detach().cpu().tolist(),
        "extend_seq_lens": forward_batch.extend_seq_lens.detach().cpu().tolist(),
    }
    save_gemma4_capture(record, f"{base}.layer{layer_id}.pt")


def capture_g2_4k_attention_output(layer, output, forward_batch):
    base = os.environ.get("G2_4K_ATTN_FILE")
    if not base or torch.cuda.is_current_stream_capturing() or os.environ.get("G2_4K_BOUNDARY_ALL") != "1":
        return
    layer_id = int(getattr(layer, "g2_logical_layer_id", layer.layer_id))
    if layer_id != int(os.environ.get("G2_4K_ATTN_LAYER", "4")):
        return
    wanted = {int(x) for x in os.environ.get("G2_4K_BOUNDARY_POSITIONS", "4095").split(",") if x}
    for row_index, position in enumerate(forward_batch.positions.detach().cpu().tolist()):
        if wanted is None or position in wanted:
            save_gemma4_capture({"layer": layer_id, "position": position, "output": output[row_index:row_index + 1].detach().float().cpu()}, f"{base}.layer{layer_id}.pos{position}.output.pt")


def capture_g2_4k_boundary(stage, layer_id, tensor, forward_batch):
    """Capture selected logical positions for the fixed 4K diagnostic request."""
    base = os.environ.get("G2_4K_BOUNDARY_FILE")
    if not base or torch.cuda.is_current_stream_capturing():
        return
    positions = forward_batch.positions
    if positions is None or positions.numel() == 0:
        return
    selected = {int(x) for x in os.environ.get("G2_4K_BOUNDARY_POSITIONS", "4095").split(",") if x}
    rows = [i for i, pos in enumerate(positions.detach().cpu().tolist()) if pos in selected]
    all_layers = {int(x) for x in os.environ.get("G2_4K_BOUNDARY_LAYERS", "0,1,2,3,4").split(",") if x}
    if os.environ.get("G2_4K_BOUNDARY_ALL") == "1" and int(layer_id) in all_layers and stage == "layer_output":
        requested = {int(x) for x in os.environ.get("G2_4K_BOUNDARY_POSITIONS", "4095").split(",") if x}
        selected_rows = [i for i, pos in enumerate(positions.detach().cpu().tolist()) if pos in requested]
    elif stage != "layer_output":
        selected_rows = rows
    else:
        requested = {int(x) for x in os.environ.get("G2_4K_BOUNDARY_POSITIONS", "4095").split(",") if x}
        selected_rows = [i for i, pos in enumerate(positions.detach().cpu().tolist()) if pos in requested]
    if tensor is None or tensor.shape[0] != positions.numel():
        raise RuntimeError(f"4K boundary {stage} is not aligned with positions")
    layer_id = int(layer_id)
    for row_index in selected_rows:
        position = int(positions[row_index].item())
        row = tensor[row_index:row_index + 1].detach().float().cpu()
        target = f"{base}.layer{layer_id:02d}.pos{position}.{stage}.pt"
        save_gemma4_capture({
            "schema": 1, "stage": stage, "layer": layer_id,
            "position": position,
            "input_id": int(forward_batch.input_ids[row_index].item()),
            "forward_mode": forward_batch.forward_mode.name,
            "model_identity": json.loads(os.environ.get("GEMMA4_MODEL_IDENTITY", "{}")),
            "shape": tuple(row.shape), "value": row,
        }, target)


def capture_g2_attention_operator_probe(
    layer, q, k, v, output, forward_batch, pool, kv_indptr, kv_indices,
    causal, sliding_window_size, sm_scale, logit_cap, k_scale, v_scale,
    window_kv_offsets=None, custom_mask=None, mask_indptr=None, qo_indptr=None,
    score_mod=None, aux_tensors=None, page_size=1, xai_temperature_len=-1,
):
    """Capture one explicitly selected extend-attention call for offline replay."""
    path = os.environ.get("G2_ATTN_OPERATOR_PROBE_FILE")
    if not path or torch.cuda.is_current_stream_capturing():
        return
    logical = int(getattr(layer, "g2_logical_layer_id", layer.layer_id))
    if logical != int(os.environ.get("G2_ATTN_OPERATOR_PROBE_LAYER", "0")):
        return
    if not forward_batch.rids or forward_batch.rids[0] != os.environ.get("G2_ATTN_OPERATOR_PROBE_RID"):
        return
    position = int(os.environ.get("G2_ATTN_OPERATOR_PROBE_POSITION", "1103"))
    positions = forward_batch.positions.detach().cpu().reshape(-1)
    rows = torch.nonzero(positions == position).reshape(-1)
    if rows.numel() != 1:
        return
    kb, vb = pool.get_kv_buffer(layer.layer_id)
    ptr = kv_indptr.detach().cpu()
    indices = kv_indices[:int(ptr[-1])].detach().cpu()
    used = torch.unique(indices, sorted=True)
    record = {
        "schema": 1, "layer": logical, "rid": list(forward_batch.rids),
        "position": position, "row": int(rows[0]),
        "input_ids": forward_batch.input_ids.detach().cpu(),
        "positions": positions,
        "q": q.detach().cpu(), "k_current": k.detach().cpu(),
        "v_current": v.detach().cpu(), "output": output.detach().cpu(),
        "pool_slots": used, "pool_k": kb[used.to(kb.device)].detach().cpu(),
        "pool_v": vb[used.to(vb.device)].detach().cpu(),
        "pool_k_shape": tuple(kb.shape), "pool_v_shape": tuple(vb.shape),
        "pool_k_stride": tuple(kb.stride()), "pool_v_stride": tuple(vb.stride()),
        "kv_indptr": ptr, "kv_indices": indices,
        "qo_indptr": None if qo_indptr is None else qo_indptr.detach().cpu(),
        "extend_prefix_lens": None if forward_batch.extend_prefix_lens is None
            else forward_batch.extend_prefix_lens.detach().cpu(),
        "extend_seq_lens": None if forward_batch.extend_seq_lens is None
            else forward_batch.extend_seq_lens.detach().cpu(),
        "causal": bool(causal), "sliding_window_size": int(sliding_window_size),
        "sm_scale": float(sm_scale),
        "max_len_extend": int(forward_batch.extend_seq_lens.max().item()),
        "logit_cap": float(logit_cap or 0.0), "k_scale": float(k_scale),
        "v_scale": float(v_scale),
        "window_kv_offsets": None if window_kv_offsets is None else window_kv_offsets.detach().cpu(),
        "custom_mask": custom_mask.detach().cpu() if isinstance(custom_mask, torch.Tensor) else custom_mask,
        "mask_indptr": None if mask_indptr is None else mask_indptr.detach().cpu(),
        "score_mod_present": score_mod is not None,
        "aux_tensors_present": aux_tensors is not None,
        "page_size": int(page_size),
        "xai_temperature_len": int(xai_temperature_len),
    }
    save_gemma4_capture(record, path)


def capture_g2_kv_stage(
    stage, layer, forward_batch, q, k=None, v=None, pool=None, allocator=None
):
    """Persist selected write/read boundaries for the fixed request fixture."""
    target = os.environ.get("G2_KV_TRACE")
    expected = os.environ.get("G2_KV_TRACE_INPUT_IDS")
    if not target or not expected or torch.cuda.is_current_stream_capturing():
        return
    ids = forward_batch.input_ids.detach().cpu().reshape(-1).tolist()
    if ids != json.loads(expected):
        return
    logical = int(getattr(layer, "g2_logical_layer_id", layer.layer_id))
    selected = {
        int(x) for x in os.environ.get("G2_KV_TRACE_LAYERS", "").split(",") if x
    }
    shared = bool(getattr(layer, "g2_is_kv_shared_layer", False))
    selection_id = logical if shared else int(getattr(layer, "g2_kv_owner_layer", layer.layer_id))
    if selected and selection_id not in selected:
        return
    physical = int(layer.layer_id)
    path, trace = _load_trace(target)
    slot = forward_batch.out_cache_loc.detach()[-1:]
    is_swa, pool_layer = False, logical
    if pool is not None:
        pool_layer, is_swa = pool.layers_mapping[physical]
        if is_swa:
            translate = getattr(allocator, "translate_loc_from_full_to_swa", None)
            if translate is None:
                translate = pool.translate_loc_from_full_to_swa
            slot = translate(slot)
    if stage == "pre_write" and k is not None and k.shape[0] > 1:
        q, k, v = q[-1:], k[-1:], v[-1:]
    if stage in ("attention_read", "attention_read_shared", "owner_read") and q.shape[0] > 1:
        q = q[-1:]
    record = {
        "stage": stage,
        "layer": logical,
        "owner": getattr(layer, "g2_kv_owner_layer", physical),
        "is_shared_consumer": shared,
        "physical_attention_layer": physical,
        "is_swa": is_swa,
        "pool_layer": pool_layer,
        "slot": slot.detach().cpu(),
        "positions": forward_batch.positions.detach().cpu()[-1:],
        "k_scale": getattr(layer, "k_scale_float", 1.0),
        "v_scale": getattr(layer, "v_scale_float", 1.0),
        "q": q.detach().cpu(),
    }
    if stage == "pre_write" and k is not None:
        record["k"] = k.detach().cpu()
        record["v"] = v.detach().cpu()
    if stage in ("attention_read", "attention_read_shared", "owner_read") and k is not None:
        record["attention_k"] = k.detach().cpu()
        record["attention_v"] = v.detach().cpu()
    if pool is not None:
        buffer_layer = (
            int(getattr(layer, "g2_kv_owner_layer", physical))
            if stage == "owner_read"
            else physical
        )
        kb, vb = pool.get_kv_buffer(buffer_layer)
        record["stored_k"] = kb[slot].detach().cpu()
        record["stored_v"] = vb[slot].detach().cpu()
    trace.setdefault("stages", {})[f"{stage}_layer_{logical}"] = record
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(trace, tmp)
    os.replace(tmp, path)


def _reference_for_layer(
    layer,
    q,
    k_ext,
    v_ext,
    kb,
    vb,
    qo_indptr,
    kv_indptr,
    kv_indices,
    causal,
    window,
    sm_scale,
    k_scale,
    v_scale,
):
    """Compute a simple FP32 reference for exact prefix+extend kernel inputs."""
    logical = int(getattr(layer, "g2_logical_layer_id", layer.layer_id))
    q_ptr = qo_indptr.detach().cpu().tolist()
    kv_ptr = kv_indptr.detach().cpu().tolist()
    indices = kv_indices.detach().cpu()
    q_cpu, k_cpu, v_cpu, mask_cpu, ref_cpu = [], [], [], [], []
    # The diagnostic fixture is one request; reject ragged/multisequence batches.
    if len(q_ptr) != 2 or len(kv_ptr) != 2:
        raise RuntimeError(f"Expected batch=1 for layer {logical}")
    qs, qe = q_ptr
    ks, ke = kv_ptr
    q_len, prefix_len = qe - qs, ke - ks
    q_device = q[qs:qe].float()
    if prefix_len:
        slots = indices[ks:ke].to(q.device)
        k_prefix = kb[slots].to(q.dtype) * float(k_scale)
        v_prefix = vb[slots].to(q.dtype) * float(v_scale)
    else:
        k_prefix = k_ext[:0]
        v_prefix = v_ext[:0]
    k_all = torch.cat((k_prefix, k_ext[qs:qe]), dim=0).float()
    v_all = torch.cat((v_prefix, v_ext[qs:qe]), dim=0).float()
    key_len = k_all.shape[0]
    outputs = []
    all_masks = []
    for head in range(q.shape[1]):
        kv_head = head // (q.shape[1] // k_ext.shape[1])
        qh = q_device[:, head]
        kh = k_all[:, kv_head]
        vh = v_all[:, kv_head]
        positions_q = prefix_len + torch.arange(q_len, device=q.device)
        positions_k = torch.arange(key_len, device=q.device)
        mask = positions_k[None, :] < positions_q[:, None] + 1
        if causal:
            mask = mask & (positions_k[None, :] <= positions_q[:, None])
        if window > 0:
            mask = mask & (positions_k[None, :] + window >= positions_q[:, None])
        scores = (qh @ kh.T) * float(sm_scale)
        scores.masked_fill_(~mask, float("-inf"))
        outputs.append(scores.softmax(dim=-1) @ vh)
        all_masks.append(mask)
    reference = torch.stack(outputs, dim=1)
    return {
        "layer": logical,
        "q": q_device.detach().cpu(),
        "k": k_all.detach().cpu(),
        "v": v_all.detach().cpu(),
        "mask": all_masks[0].detach().cpu(),
        "reference": reference.detach().cpu(),
        "prefix_len": prefix_len,
        "scale": float(sm_scale),
        "causal": bool(causal),
        "sliding_window": int(window),
    }


def capture_g2_attention_input(
    layer,
    q,
    k_ext,
    v_ext,
    kb,
    vb,
    qo_indptr,
    kv_indptr,
    kv_indices,
    causal,
    window,
    sm_scale,
    k_scale,
    v_scale,
):
    target = os.environ.get("G2_KV_TRACE")
    if not target or torch.cuda.is_current_stream_capturing():
        return
    logical = int(getattr(layer, "g2_logical_layer_id", layer.layer_id))
    selected = {
        int(x) for x in os.environ.get("G2_KV_TRACE_LAYERS", "").split(",") if x
    }
    if logical not in selected or q.shape[0] != 512:
        return
    record = _reference_for_layer(
        layer,
        q,
        k_ext,
        v_ext,
        kb,
        vb,
        qo_indptr,
        kv_indptr,
        kv_indices,
        causal,
        window,
        sm_scale,
        k_scale,
        v_scale,
    )
    path, trace = _load_trace(target)
    trace.setdefault("attention_kernel", {})[logical] = record
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(trace, tmp)
    os.replace(tmp, path)


def capture_g2_attention_output(layer, output):
    target = os.environ.get("G2_KV_TRACE")
    if not target or torch.cuda.is_current_stream_capturing():
        return
    logical = int(getattr(layer, "g2_logical_layer_id", layer.layer_id))
    selected = {
        int(x) for x in os.environ.get("G2_KV_TRACE_LAYERS", "").split(",") if x
    }
    if logical not in selected or output.shape[0] != 512:
        return
    path, trace = _load_trace(target)
    record = trace.get("attention_kernel", {}).get(logical)
    if record is None:
        raise RuntimeError(f"Missing N=512 attention input for layer {logical}")
    record["output"] = output.detach().cpu()
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(trace, tmp)
    os.replace(tmp, path)
