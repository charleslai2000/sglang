"""Observe Gemma4 attention arguments, cache indexes, and returned attention output."""
import importlib
import os
import runpy

if os.getenv("GEMMA4_RUNTIME_HOOK_ENABLE") == "1":
    root = os.environ["GEMMA4_RUNTIME_HOOK_PATH"]
    capture = runpy.run_path(os.path.join(root, "runtime-layer-components-capture.py"))["capture"]
    backend_module = importlib.import_module("sglang.srt.layers.attention.triton_backend")
    original_extend = backend_module.TritonAttnBackend.forward_extend

    def wrapped_extend(self, q, k, v, layer, forward_batch, *args, **kwargs):
        watched = int(layer.layer_id) == int(os.getenv("GEMMA4_COMPONENT_LAYER", "-1"))
        if watched and os.getenv("GEMMA4_COMPONENT_STATE_FILE"):
            capture(layer, "q", q, forward_batch.positions, forward_batch)
            if k is not None:
                capture(layer, "k", k, forward_batch.positions, forward_batch)
            if v is not None:
                capture(layer, "v", v, forward_batch.positions, forward_batch)
        result = original_extend(self, q, k, v, layer, forward_batch, *args, **kwargs)
        if watched and os.getenv("GEMMA4_COMPONENT_STATE_FILE"):
            capture(layer, "attention_output", result, forward_batch.positions, forward_batch)
        return result

    backend_module.TritonAttnBackend.forward_extend = wrapped_extend
