"""Install opt-in Gemma4 DecoderLayer and attention operation captures."""

import importlib
import os
import runpy

if os.getenv("GEMMA4_RUNTIME_HOOK_ENABLE") == "1":
    root = os.environ["GEMMA4_RUNTIME_HOOK_PATH"]
    capture = runpy.run_path(os.path.join(root, "runtime-layer-components-capture.py"))[
        "capture"
    ]
    module = importlib.import_module("sglang.srt.models.gemma4_causal")

    configured_layers = os.getenv("GEMMA4_COMPONENT_LAYERS")
    component_layers = {int(x) for x in configured_layers.split(",")} if configured_layers else {int(os.getenv("GEMMA4_COMPONENT_LAYER", "-1"))}
    original_attention = module.Gemma4Attention.forward
    def wrapped_attention(self, positions, hidden_states, forward_batch, **kwargs):
        watched = self.layer_id in component_layers
        prior_logical_layer = getattr(forward_batch, "_gemma4_logical_attention_layer", None)
        forward_batch._gemma4_logical_attention_layer = int(self.layer_id)
        if watched:
            capture(self, "attention_norm_input", hidden_states, positions, forward_batch)
        if not watched:
            try:
                return original_attention(self, positions, hidden_states, forward_batch, **kwargs)
            finally:
                if prior_logical_layer is None:
                    del forward_batch._gemma4_logical_attention_layer
                else:
                    forward_batch._gemma4_logical_attention_layer = prior_logical_layer
        original_attn_forward = module.RadixAttention.forward
        def attention_with_capture(attn_layer, q, k, v, *args, **attn_kwargs):
            if self.layer_id in component_layers:
                capture(self, "q_after_rope_entering_attention", q, positions, forward_batch)
                if k is not None:
                    capture(self, "k_after_rope_entering_attention", k, positions, forward_batch)
                if v is not None:
                    capture(self, "v_entering_attention", v, positions, forward_batch)
            result = original_attn_forward(attn_layer, q, k, v, *args, **attn_kwargs)
            capture(self, "attention_output_heads", result, positions, forward_batch)
            return result
        module.RadixAttention.forward = attention_with_capture
        original_qkv_forward = module.QKVParallelLinear.forward
        def projection_with_capture(projection_layer, x):
            result = original_qkv_forward(projection_layer, x)
            capture(self, "qkv_projection_output", result[0], positions, forward_batch)
            return result
        module.QKVParallelLinear.forward = projection_with_capture
        original_norm = module.gemma_qkv_rmsnorm
        def norm_with_capture(q, k, v, q_weight, k_weight, **norm_kwargs):
            result = original_norm(q, k, v, q_weight, k_weight, **norm_kwargs)
            capture(self, "q_after_norm_before_rope", q, positions, forward_batch)
            if k is not None:
                capture(self, "k_after_norm_before_rope", k, positions, forward_batch)
                capture(self, "v_after_norm_before_rope", v, positions, forward_batch)
            return result
        module.gemma_qkv_rmsnorm = norm_with_capture
        try:
            return original_attention(self, positions, hidden_states, forward_batch, **kwargs)
        finally:
            module.QKVParallelLinear.forward = original_qkv_forward
            module.gemma_qkv_rmsnorm = original_norm
            module.RadixAttention.forward = original_attn_forward
            if prior_logical_layer is None:
                del forward_batch._gemma4_logical_attention_layer
            else:
                forward_batch._gemma4_logical_attention_layer = prior_logical_layer

    module.Gemma4Attention.forward = wrapped_attention

    original_layer = module.Gemma4DecoderLayer.forward

    def wrapped_layer(
        self, positions, hidden_states, per_layer_input, forward_batch, **kwargs
    ):
        watched = self.layer_id in component_layers
        if watched:
            capture(self, "decoder_layer_input", hidden_states, positions, forward_batch)
            capture(self, "ple_input", per_layer_input, positions, forward_batch)
        handles = []
        if watched:
            for name in (
                "post_attention_layernorm",
                "pre_feedforward_layernorm",
                "mlp",
                "post_feedforward_layernorm",
                "per_layer_input_gate",
                "per_layer_projection",
                "post_per_layer_input_norm",
            ):
                submodule = getattr(self, name, None)
                if submodule is not None:
                    def save_output(_module, _inputs, output, boundary=name):
                        capture(self, boundary, output[0] if isinstance(output, tuple) else output, positions, forward_batch)
                    handles.append(submodule.register_forward_hook(save_output))
        try:
            result = original_layer(
                self, positions, hidden_states, per_layer_input, forward_batch, **kwargs
            )
        finally:
            for handle in handles:
                handle.remove()
        if watched:
            if os.getenv("GEMMA4_CAPTURE_ALL_LAYER_OUTPUTS") != "1":
                capture(self, "decoder_layer_output", result[0], positions, forward_batch)
        if os.getenv("GEMMA4_CAPTURE_ALL_LAYER_OUTPUTS") == "1":
            capture(self, "decoder_layer_output", result[0], positions, forward_batch)
        return result

    module.Gemma4DecoderLayer.forward = wrapped_layer

    # Install after the component wrapper: that wrapper replaces Gemma4Attention.forward.
    runpy.run_path(
        os.path.join(root, "runtime-attention-capture.py"),
        run_name="__gemma4_attn_hook__",
    )
