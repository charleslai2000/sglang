#!/usr/bin/env python3
"""Opt-in single-position Layer-5 operator capture for bounded G2 requests."""

import json
import os
import torch


def _enabled(layer_id, forward_batch):
    if os.environ.get("G2_L5_CAPTURE") != "1" or int(layer_id) != 5:
        return False
    if torch.cuda.is_current_stream_capturing():
        return False
    expected = os.environ.get("G2_L5_CAPTURE_RID")
    return bool(forward_batch.rids and forward_batch.rids[0] == expected)


def _store(stage, value, layer_id, forward_batch, **extra):
    if not _enabled(layer_id, forward_batch):
        return
    positions = forward_batch.positions.detach().cpu().reshape(-1)
    ids = forward_batch.input_ids.detach().cpu().reshape(-1)
    out = os.environ["G2_L5_CAPTURE_FILE"]
    for row in range(len(positions)):
        rec = {
            "schema": 1,
            "stage": stage,
            "layer": 5,
            "forward_id": forward_batch.gemma4_forward_id,
            "rid": list(forward_batch.rids),
            "forward_mode": forward_batch.forward_mode.name,
            "position": int(positions[row]),
            "input_id": int(ids[row]),
            "model_sha256": json.loads(os.environ["GEMMA4_MODEL_IDENTITY"])[
                "model_sha256"
            ],
            "value": value[row].detach().float().cpu().clone(),
            **extra,
        }
        path = f"{out}.{rec['forward_id']}.layer5.pos{rec['position']}.{stage}.pt"
        from sglang.srt.utils.gemma4_capture import save_gemma4_capture

        save_gemma4_capture(rec, path)


def capture_block_input(layer_id, value, forward_batch):
    _store("block_input", value, layer_id, forward_batch)


def capture_normed_input(layer_id, value, forward_batch):
    _store("attn_normed_input", value, layer_id, forward_batch)


def capture_projection(layer_id, stage, value, forward_batch):
    _store(stage, value, layer_id, forward_batch)


def capture_rope(layer_id, q, k, positions, forward_batch, layer):
    if not _enabled(layer_id, forward_batch):
        return
    _store(
        "q_rope",
        q,
        layer_id,
        forward_batch,
        q_heads=layer.num_heads,
        kv_heads=layer.num_kv_heads,
        head_dim=layer.head_dim,
        rotary_dim=layer.rotary_emb.rotary_dim,
        rope_base=layer.rotary_emb.base,
        rope_type="proportional" if layer.head_dim == 512 else "default",
    )
    if k is not None:
        _store(
            "k_rope",
            k.flatten(-2, -1),
            layer_id,
            forward_batch,
            q_heads=layer.num_heads,
            kv_heads=layer.num_kv_heads,
            head_dim=layer.head_dim,
            rotary_dim=layer.rotary_emb.rotary_dim,
            rope_base=layer.rotary_emb.base,
            rope_type="proportional" if layer.head_dim == 512 else "default",
        )


def capture_attention_output(layer_id, value, forward_batch):
    _store("attention_output", value, layer_id, forward_batch)


def capture_block_boundary(stage, layer_id, value, forward_batch):
    _store(stage, value, layer_id, forward_batch)
