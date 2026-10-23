"""Observe Gemma4 attention arguments, cache indexes, and returned attention output."""
import importlib
import os
import runpy
import torch

if os.getenv("GEMMA4_RUNTIME_HOOK_ENABLE") == "1":
    root = os.environ["GEMMA4_RUNTIME_HOOK_PATH"]
    capture = runpy.run_path(os.path.join(root, "runtime-layer-components-capture.py"))["capture"]
    backend_module = importlib.import_module("sglang.srt.layers.attention.triton_backend")
    original_backend_forward = backend_module.TritonAttnBackend.forward_extend

    def capture_kernel_inputs(self, layer, forward_batch, kernel_name, original_kernel, kernel_args, kernel_kwargs):
        for name, index in (("kernel_q",0),("kernel_k",1),("kernel_v",2),("kernel_qo_indptr",6),("kernel_kv_indptr",7),("kernel_kv_indices",8),("kernel_custom_mask",9),("kernel_mask_indptr",11)):
            value = kernel_args[index] if len(kernel_args) > index else kernel_kwargs.get(name)
            if isinstance(value, torch.Tensor):
                capture(layer, kernel_name + "." + name, value, forward_batch.positions, forward_batch)
        scalar_indices = (("causal",10),("max_extend_len",12),("k_descale",13),("v_descale",14),("sm_scale",15))
        scalars = {key: kernel_args[i] if len(kernel_args)>i else kernel_kwargs.get(key) for key,i in scalar_indices}
        scalars.update({key:kernel_kwargs.get(key) for key in ("sliding_window_size","window_kv_offsets","window_start_pos","page_size","logit_cap")})
        import json
        from pathlib import Path
        target = Path(os.environ["GEMMA4_COMPONENT_STATE_FILE"]) / f"{kernel_name}.params.{forward_batch.rids[0]}.{forward_batch.gemma4_forward_id}.layer{layer.layer_id}.json"
        target.write_text(json.dumps(scalars, default=str, indent=2) + "\n")
        return original_kernel(*kernel_args, **kernel_kwargs)

    def wrapped_backend_forward(self, q, k, v, layer, forward_batch, *args, **kwargs):
        target_layer = int(os.getenv("GEMMA4_COMPONENT_LAYER", "-1"))
        logical_layer = getattr(forward_batch, "_gemma4_logical_attention_layer", int(layer.layer_id))
        watched = logical_layer == target_layer
        enabled = watched and bool(os.getenv("GEMMA4_COMPONENT_STATE_FILE")) and forward_batch.forward_mode.is_extend()
        capture_layer = layer
        if enabled and logical_layer != int(layer.layer_id):
            capture_layer = type("Gemma4LogicalLayerCapture", (), {"layer_id": logical_layer})()
        original_kernel = self.extend_attention_fwd
        if enabled:
            capture(capture_layer, "q_entering_triton_backend", q, forward_batch.positions, forward_batch)
            if k is not None:
                capture(capture_layer, "k_fresh_entering_triton_backend", k, forward_batch.positions, forward_batch)
            if v is not None:
                capture(capture_layer, "v_fresh_entering_triton_backend", v, forward_batch.positions, forward_batch)
            if k is None and v is None and forward_batch.forward_mode.is_extend():
                pool = self.token_to_kv_pool
                owner_layer = int(layer.layer_id)
                cache_loc = forward_batch.out_cache_loc
                from sglang.srt.model_executor.forward_context import get_req_to_token_pool
                request_pool = get_req_to_token_pool()
                row = forward_batch.req_pool_indices[0]
                prefix_len = int(forward_batch.extend_prefix_lens[0])
                total_len = int(forward_batch.seq_lens[0])
                req_to_token_row = request_pool.req_to_token[row, :total_len]
                layer_mapping = getattr(pool, "layers_mapping", {}).get(owner_layer)
                if layer_mapping is not None and layer_mapping[1]:
                    owner_pool_layer = layer_mapping[0]
                    owner_pool = pool.swa_kv_pool
                    req_to_token_row = pool.translate_loc_from_full_to_swa(req_to_token_row)
                    cache_loc = pool.translate_loc_from_full_to_swa(cache_loc)
                elif layer_mapping is not None:
                    owner_pool_layer = layer_mapping[0]
                    owner_pool = pool.full_kv_pool
                elif getattr(pool, "layers_mapping", None) is not None and hasattr(pool, "full_kv_pool"):
                    owner_pool_layer = getattr(pool, "layers_mapping", {}).get(owner_layer, (owner_layer, False))[0]
                    owner_pool = pool.full_kv_pool
                    if getattr(self, "_translate_kv_loc", None) is not None:
                        req_to_token_row = self._translate_kv_loc(req_to_token_row)
                        cache_loc = self._translate_kv_loc(cache_loc)
                else:
                    owner_pool_layer = owner_layer
                    owner_pool = pool
                key_buffer, value_buffer = owner_pool.get_kv_buffer(owner_pool_layer)
                request_slots = req_to_token_row[prefix_len:total_len]
                capture(capture_layer, "shared_kv_read_slots", request_slots, forward_batch.positions, forward_batch)
                capture(capture_layer, "shared_kv_values_at_owner_slots", key_buffer[request_slots], forward_batch.positions, forward_batch)
                capture(capture_layer, "shared_v_values_at_owner_slots", value_buffer[request_slots], forward_batch.positions, forward_batch)
                capture(capture_layer, "shared_kv_values_at_write_slots", key_buffer[cache_loc], forward_batch.positions, forward_batch)
                capture(capture_layer, "shared_v_values_at_write_slots", value_buffer[cache_loc], forward_batch.positions, forward_batch)
            original_unified_kernel = self.extend_attention_fwd_unified
            def kernel_capture(*kernel_args, **kernel_kwargs):
                return capture_kernel_inputs(self, capture_layer, forward_batch, "extend_attention_fwd", original_kernel, kernel_args, kernel_kwargs)
            def unified_kernel_capture(*kernel_args, **kernel_kwargs):
                return capture_kernel_inputs(self, capture_layer, forward_batch, "extend_attention_fwd_unified", original_unified_kernel, kernel_args, kernel_kwargs)
            bound = self.extend_attention_fwd
            bound_fn = getattr(bound, "_torchdynamo_orig_callable", None)
            if bound_fn is None:
                bound_fn = getattr(bound, "__wrapped__", None)
            if bound_fn is None:
                bound_fn = getattr(bound, "__func__", None)
            if bound_fn is not None and getattr(bound_fn, "__name__", "") == "extend_attention_fwd":
                kernel_capture.__wrapped__ = original_kernel
                self.extend_attention_fwd = torch.compiler.disable(kernel_capture)
            else:
                self.extend_attention_fwd = kernel_capture
            bound_unified = self.extend_attention_fwd_unified
            unified_fn = getattr(bound_unified, "_torchdynamo_orig_callable", None)
            if unified_fn is None:
                unified_fn = getattr(bound_unified, "__wrapped__", None)
            if unified_fn is None:
                unified_fn = getattr(bound_unified, "__func__", None)
            if unified_fn is not None and getattr(unified_fn, "__name__", "") == "extend_attention_fwd_unified":
                unified_kernel_capture.__wrapped__ = original_unified_kernel
                self.extend_attention_fwd_unified = torch.compiler.disable(unified_kernel_capture)
            else:
                self.extend_attention_fwd_unified = unified_kernel_capture
        try:
            result = original_backend_forward(self, q, k, v, layer, forward_batch, *args, **kwargs)
        except BaseException as exc:
            if enabled:
                import traceback
                from pathlib import Path
                (Path(os.environ["GEMMA4_COMPONENT_STATE_FILE"])/f"hook-error.{forward_batch.rids[0]}.{forward_batch.gemma4_forward_id}.layer{logical_layer}.txt").write_text(traceback.format_exc())
            raise
        finally:
            if enabled:
                self.extend_attention_fwd = original_kernel
                self.extend_attention_fwd_unified = original_unified_kernel
        if enabled:
            output = result[0] if isinstance(result, tuple) else result
            capture(capture_layer, "attention_output", output, forward_batch.positions, forward_batch)
        return result

    backend_module.TritonAttnBackend.forward_extend = wrapped_backend_forward
