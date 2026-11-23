"""Gemma4-specific map from logical attention layers to physical KV owners."""

from __future__ import annotations


def gemma4_kv_owner_layout(model_config):
    """Return ``(mapping, full_owner_ids, swa_owner_ids)`` for Gemma4.

    Shared logical layers alias the latest earlier owner with the same layer
    type, matching Gemma4 attention construction. Non-Gemma architectures return
    ``None`` so their existing pool topology is unchanged.
    """
    architectures = getattr(model_config.hf_config, "architectures", ()) or ()
    if not any("Gemma4" in architecture for architecture in architectures):
        return None
    text = model_config.hf_text_config
    num_layers = int(text.num_hidden_layers)
    num_shared = int(getattr(text, "num_kv_shared_layers", 0) or 0)
    layer_types = list(getattr(text, "layer_types", ()))
    if len(layer_types) != num_layers or not 0 <= num_shared < num_layers:
        raise ValueError(
            f"Invalid Gemma4 KV layout: layers={num_layers}, shared={num_shared}, "
            f"layer_types={len(layer_types)}"
        )
    first_shared = num_layers - num_shared
    full_owners = [i for i in range(first_shared) if layer_types[i] == "full_attention"]
    swa_owners = [
        i for i in range(first_shared) if layer_types[i] == "sliding_attention"
    ]
    owner_index = {
        "full_attention": {layer_id: i for i, layer_id in enumerate(full_owners)},
        "sliding_attention": {layer_id: i for i, layer_id in enumerate(swa_owners)},
    }
    latest_owner = {}
    for layer_id in range(first_shared):
        latest_owner[layer_types[layer_id]] = layer_id
    mapping = {}
    for layer_id, layer_type in enumerate(layer_types):
        if layer_type not in owner_index:
            raise ValueError(f"Unsupported Gemma4 layer type {layer_type!r}")
        owner_id = layer_id if layer_id < first_shared else latest_owner.get(layer_type)
        if owner_id is None:
            raise ValueError(f"No Gemma4 KV owner for shared layer {layer_id}")
        mapping[layer_id] = (
            owner_index[layer_type][owner_id],
            layer_type == "sliding_attention",
        )
    return mapping, full_owners, swa_owners
