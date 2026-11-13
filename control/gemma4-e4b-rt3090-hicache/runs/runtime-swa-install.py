"""Install opt-in one-shot Gemma4 SWA slot and owner-KV observations."""
import importlib
import os
import runpy

if os.getenv("GEMMA4_RUNTIME_HOOK_ENABLE") == "1":
    hook_path = os.path.join(
        os.environ["GEMMA4_RUNTIME_HOOK_PATH"], "runtime-swa-slot-capture.py"
    )
    namespace = runpy.run_path(hook_path)
    capture_hook = namespace["capture"]
    backend_module = importlib.import_module("sglang.srt.layers.attention.triton_backend")
    original_forward_extend = backend_module.TritonAttnBackend.forward_extend

    def wrapped_forward_extend(self, q, k, v, layer, forward_batch, *args, **kwargs):
        result = original_forward_extend(self, q, k, v, layer, forward_batch, *args, **kwargs)
        capture_hook(self, forward_batch, layer)
        return result

    backend_module.TritonAttnBackend._gemma4_original_forward_extend = original_forward_extend
    backend_module.TritonAttnBackend.forward_extend = wrapped_forward_extend
