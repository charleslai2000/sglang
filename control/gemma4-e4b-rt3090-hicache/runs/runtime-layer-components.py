"""Install opt-in Gemma4 component hooks; instantiated only in a diagnostic child."""
import json
import os
import runpy
import torch

if os.getenv("GEMMA4_RUNTIME_HOOK_ENABLE") == "1":
    root = os.environ["GEMMA4_RUNTIME_HOOK_PATH"]
    capture = runpy.run_path(os.path.join(root, "runtime-layer-components-capture.py"))["capture"]
    import importlib

    module = importlib.import_module("sglang.srt.models.gemma4_causal")
    runpy.run_path(os.path.join(root, "runtime-attention-capture.py"), run_name="__gemma4_attn_hook__")
    original = module.Gemma4Attention.forward

    layer_capture = runpy.run_path(os.path.join(root, "runtime-layer-components-capture.py"))["capture"]

    def wrapped_layer(self, positions, hidden_states, per_layer_input, forward_batch, **kwargs):
        watched = self.layer_id == int(os.getenv("GEMMA4_COMPONENT_LAYER", "-1"))
        result = original_layer(self, positions, hidden_states, per_layer_input, forward_batch, **kwargs)
        if watched:
            layer_capture(self, "decoder_layer_output", result[0], positions, forward_batch)
        return result

    original_layer = module.Gemma4DecoderLayer.forward
    module.Gemma4DecoderLayer.forward = wrapped_layer

    def wrapped(self, positions, hidden_states, forward_batch, **kwargs):
        wanted = self.layer_id == int(os.getenv("GEMMA4_COMPONENT_LAYER", "-1"))
        if wanted:
            capture(self, "attention_norm_input", hidden_states, positions, forward_batch)
        return original(self, positions, hidden_states, forward_batch, **kwargs)

    module.Gemma4Attention.forward = wrapped
