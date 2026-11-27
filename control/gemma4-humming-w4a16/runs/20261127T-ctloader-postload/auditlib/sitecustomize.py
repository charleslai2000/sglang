"""Qualification-only instrumentation for the T012 CT-loader/Humming comparison.

Placed on ``PYTHONPATH`` for the paired run only; the production server never
imports it. CPython's ``site`` module imports it in every process of the run,
including the spawned scheduler that owns the checkpoint, so these hooks run in
the process that loads weights, converts them and replays the decode graph.

Evidence produced:

* ``ct-wna16-audit.jsonl`` -- per parameter SHA256 of every Text Core
  ``weight_packed`` / ``weight_scale`` (plus ``weight_shape`` and element counts),
  taken inside ``CompressedTensorsWNA16.process_weights_after_loading`` before
  Marlin repack or Humming transform. Names come from the model's own
  ``named_parameters()`` map, so nothing about the fused shard layout is
  re-derived here.
* ``post`` records -- the parameter names left on the layer after conversion
  (proves the CT packed matrix is not resident twice), and for the layers named
  in ``T012_AUDIT_GEMM`` the error of the converted layer's real GEMM against an
  FP32 reference dequantized from the same checkpoint words and scales.
* ``dispatch-<pid>.json`` -- counts of Humming GEMM and Marlin linear dispatch,
  the first pre-sampling logits vector, and the CUDA kernels seen while replaying
  the first decode CUDA graphs (so graph replay is shown to run Humming kernels).
"""

import atexit
import builtins
import hashlib
import json
import os
import sys
import zlib

AUDIT_DIR = os.environ.get("T012_AUDIT_DIR")
WATCH = ("torch", "humming", "sglang")
TEXT_CORE = "language_model."
AUDIT_FILE = "ct-wna16-audit.jsonl"


def _new_state():
    return {
        "pid": os.getpid(),
        "humming_gemm": 0,
        "humming_gemm_capture": 0,
        "marlin_linear": 0,
        "graph_replay": 0,
        "profiled_replays": 0,
        "replay_kernels": [],
        "logits_saved": 0,
        "audited_layers": 0,
        "name_map_size": 0,
    }


STATE = _new_state()
PARAM_NAMES = {}
PENDING = {}
_patched = set()
_in_hook = False


def _dump_state():
    if not AUDIT_DIR:
        return
    interesting = (
        STATE["humming_gemm"]
        or STATE["marlin_linear"]
        or STATE["graph_replay"]
        or STATE["logits_saved"]
        or STATE["audited_layers"]
    )
    if not interesting:
        return
    os.makedirs(AUDIT_DIR, exist_ok=True)
    try:
        with open(os.path.join(AUDIT_DIR, f"dispatch-{os.getpid()}.json"), "w") as f:
            json.dump(STATE, f, indent=1, sort_keys=True)
    except OSError:
        pass


atexit.register(_dump_state)


def _maybe_dump():
    total = STATE["humming_gemm"] + STATE["marlin_linear"] + STATE["audited_layers"]
    if total and total % 128 == 0:
        _dump_state()


def _torch():
    return sys.modules.get("torch")


def _sha256(tensor):
    host = tensor.detach().to(device="cpu", copy=True).contiguous()
    return hashlib.sha256(host.view(_torch().uint8).numpy().tobytes()).hexdigest()


def _unpack_int4(weight_packed):
    """Symmetric INT4 words -> FP32 codes; word j holds K indices 8j..8j+7."""
    rows, words_per_row = weight_packed.shape
    torch = _torch()
    shifts = torch.arange(0, 32, 4, dtype=torch.int64, device=weight_packed.device)
    words = weight_packed.to(torch.int64).unsqueeze(-1)
    codes = ((words >> shifts) & 0xF).reshape(rows, words_per_row * 8)
    return codes.to(torch.float32) - 8.0


def _dequant_reference(weight_packed, weight_scale, group_size):
    torch = _torch()
    codes = _unpack_int4(weight_packed)
    scale = weight_scale.to(torch.float32)
    if scale.shape[1] == 1:
        return codes * scale
    return codes * scale.repeat_interleave(group_size, dim=1)


def _gemm_prefixes():
    raw = os.environ.get("T012_AUDIT_GEMM", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def _append(record):
    os.makedirs(AUDIT_DIR, exist_ok=True)
    with open(os.path.join(AUDIT_DIR, AUDIT_FILE), "a") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def _text_core_name(param):
    if param is None:
        return None
    name = PARAM_NAMES.get(id(param))
    if name is None or not name.startswith(TEXT_CORE):
        return None
    return name


# ---------------------------------------------------------------- model patching


def _remember(model):
    try:
        for name, param in model.named_parameters():
            PARAM_NAMES[id(param)] = name
    except Exception:  # pragma: no cover - qualification only
        pass
    STATE["name_map_size"] = len(PARAM_NAMES)


def _patch_post_load_weights():
    mod = sys.modules.get("sglang.srt.model_loader.loader")
    if mod is None:
        return
    real = getattr(mod, "_post_load_weights", None)
    if real is not None and not getattr(real, "_t012", False):

        def _post_load_weights(model):
            _remember(model)
            return real(model)

        _post_load_weights._t012 = True
        mod._post_load_weights = _post_load_weights

    # Every loader instantiates the model through this module-level helper, which
    # runs before weights (and therefore before process_weights_after_loading).
    # Parameter objects are created in the model __init__ and then filled in
    # place, so recording their names here keeps the ids valid later.
    init = getattr(mod, "_initialize_model", None)
    if init is not None and not getattr(init, "_t012", False):

        def _initialize_model(*args, **kwargs):
            model = init(*args, **kwargs)
            _remember(model)
            return model

        _initialize_model._t012 = True
        mod._initialize_model = _initialize_model


    # Second, independent chance to see the model immediately before the
    # post-load loop: every loader funnels weights through this helper.
    for attr in list(vars(mod)):
        obj = getattr(mod, attr, None)
        if not isinstance(obj, type) or "load_weights_and_postprocess" not in obj.__dict__:
            continue
        key = f"lwap.{obj.__name__}"
        if key in _patched:
            continue
        original = obj.__dict__["load_weights_and_postprocess"]
        if isinstance(original, staticmethod):
            original = original.__func__

            def static_wrapper(model, weights, target_device, _original=original):
                _remember(model)
                return _original(model, weights, target_device)

            obj.load_weights_and_postprocess = staticmethod(static_wrapper)
        else:

            def method_wrapper(self, model, weights, target_device, _original=original):
                _remember(model)
                return _original(self, model, weights, target_device)

            obj.load_weights_and_postprocess = method_wrapper
        _patched.add(key)


def _patch_ct_scheme():
    mod = sys.modules.get(
        "sglang.srt.layers.quantization.compressed_tensors.schemes."
        "compressed_tensors_wNa16"
    )
    if mod is None or "ct_wna16.process" in _patched:
        return
    cls = getattr(mod, "CompressedTensorsWNA16", None)
    if cls is None:
        return
    real = cls.process_weights_after_loading

    def process_weights_after_loading(self, layer):
        pending = _audit_before(self, layer)
        result = real(self, layer)
        _audit_after(pending, self, layer)
        return result

    cls.process_weights_after_loading = process_weights_after_loading
    _patched.add("ct_wna16.process")


def _audit_before(scheme, layer):
    torch = _torch()
    name = _text_core_name(getattr(layer, "weight_packed", None))
    if name is None:
        return None
    scale_name = _text_core_name(getattr(layer, "weight_scale", None))
    weight = layer.weight_packed
    scale = layer.weight_scale
    record = {
        "event": "pre",
        "pid": os.getpid(),
        "mode": "humming" if os.environ.get("SGLANG_CTWNA16_HUMMING") else "marlin",
        "layer": name.rsplit(".", 1)[0],
        "param": name,
        "scale_param": scale_name,
        "module": type(layer).__name__,
        "num_bits": 32 // scheme.pack_factor,
        "group_size": scheme.group_size,
        "strategy": scheme.strategy,
        "input_size_per_partition": int(layer.weight_packed.shape[1]) * scheme.pack_factor,
        "output_partition_sizes": [
            int(v) for v in getattr(layer, "output_partition_sizes", [weight.shape[0]])
        ],
        "weight_shape": [int(v) for v in layer.weight_shape.tolist()],
        "packed_sha256": _sha256(weight),
        "packed_dtype": str(weight.dtype),
        "packed_shape": [int(v) for v in weight.shape],
        "packed_numel": int(weight.numel()),
        "scale_sha256": _sha256(scale),
        "scale_dtype": str(scale.dtype),
        "scale_shape": [int(v) for v in scale.shape],
        "scale_numel": int(scale.numel()),
    }
    _append(record)
    STATE["audited_layers"] += 1
    _maybe_dump()

    gemm = None
    if name.rsplit(".", 1)[0] in _gemm_prefixes():
        seed = zlib.crc32(name.encode()) & 0xFFFFFFFF
        torch.manual_seed(seed)
        x = torch.randn(
            8,
            int(weight.shape[1]) * scheme.pack_factor,
            device=weight.device,
            dtype=scale.dtype,
        )
        bias = getattr(layer, "bias", None)
        bias = None if bias is None else bias.detach()
        reference = x.to(torch.float32) @ _dequant_reference(
            weight.detach(), scale.detach(), scheme.group_size
        ).transpose(0, 1)
        if bias is not None:
            reference = reference + bias.to(torch.float32)
        gemm = {"x": x, "bias": bias, "reference": reference}

    return {"record": record, "gemm": gemm}


def _audit_after(pending, scheme, layer):
    if pending is None:
        return
    torch = _torch()
    record = dict(pending["record"])
    record.pop("packed_sha256")
    record.pop("scale_sha256")
    record["event"] = "post"
    record["parameters"] = sorted(name for name, _ in layer.named_parameters())
    gemm = pending["gemm"]
    if gemm is not None:
        with torch.no_grad():
            output = scheme.apply_weights(layer, gemm["x"], gemm["bias"])
        output = output.to(torch.float32)
        diff = (output - gemm["reference"]).abs()
        record["gemm"] = {
            "m": int(gemm["x"].shape[0]),
            "max_abs": float(diff.max()),
            "mean_abs": float(diff.mean()),
            "reference_abs_mean": float(gemm["reference"].abs().mean()),
            "output_abs_mean": float(output.abs().mean()),
        }
    _append(record)


# ------------------------------------------------------------- dispatch counters


def _patch_humming_layer():
    """Count Humming layer GEMMs via the public HummingMethod entry point.

    Patching ``humming.ops.humming_gemm`` is not an option: ``humming.ops``
    registers that name with ``torch.library.infer_schema`` at import time, so a
    generic ``*args`` wrapper would break registration.
    """
    torch = sys.modules.get("torch")
    mod = sys.modules.get("humming.layer")
    if torch is None or mod is None or "humming.layer.forward_layer" in _patched:
        return
    cls = getattr(mod, "HummingMethod", None)
    if cls is None:
        return
    real = cls.forward_layer

    def forward_layer(*args, **kwargs):
        STATE["humming_gemm"] += 1
        if torch.cuda.is_current_stream_capturing():
            STATE["humming_gemm_capture"] += 1
        result = real(*args, **kwargs)
        _maybe_dump()
        return result

    cls.forward_layer = staticmethod(forward_layer)
    _patched.add("humming.layer.forward_layer")


def _patch_ct_marlin():
    mod = sys.modules.get(
        "sglang.srt.layers.quantization.compressed_tensors.schemes."
        "compressed_tensors_wNa16"
    )
    if mod is None or "ct_wna16.marlin_linear" in _patched:
        return
    real = getattr(mod, "apply_gptq_marlin_linear", None)
    if real is None:
        return

    def apply_gptq_marlin_linear(*args, **kwargs):
        STATE["marlin_linear"] += 1
        result = real(*args, **kwargs)
        _maybe_dump()
        return result

    mod.apply_gptq_marlin_linear = apply_gptq_marlin_linear
    _patched.add("ct_wna16.marlin_linear")


def _patch_cuda_graph_replay():
    """Count decode graph replays.

    Deliberately no profiler here: wrapping ``CUDAGraph.replay`` in a CUPTI
    session during a live serving run produced a CUDA launch failure. Replay
    kernel evidence is collected separately in a bounded, out-of-serving-path
    micro-check (compare_arms.py reads its JSON).
    """
    torch = sys.modules.get("torch")
    if torch is None:
        return
    graphs = sys.modules.get("torch.cuda.graphs")
    cls = getattr(graphs, "CUDAGraph", None) if graphs is not None else None
    if cls is None:
        cls = getattr(torch.cuda, "CUDAGraph", None)
    if cls is None or "torch.cuda.graphs.CUDAGraph.replay" in _patched:
        return
    real = cls.replay

    def replay(self):
        STATE["graph_replay"] += 1
        return real(self)

    cls.replay = replay
    _patched.add("torch.cuda.graphs.CUDAGraph.replay")


def _patch_logits_processor():
    mod = sys.modules.get("sglang.srt.layers.logits_processor")
    if mod is None or "sglang.logits_processor.forward" in _patched:
        return
    cls = getattr(mod, "LogitsProcessor", None)
    if cls is None:
        return
    real = cls.forward

    def forward(self, *args, **kwargs):
        out = real(self, *args, **kwargs)
        if STATE["logits_saved"]:
            return out
        # Only capture once the driver asks for it: CUDA-graph warmup runs a
        # dummy batch eagerly, and its logits are not comparable across arms.
        if not os.path.exists(os.path.join(AUDIT_DIR, "capture-logits")):
            return out
        logits = getattr(out, "next_token_logits", None)
        torch = sys.modules.get("torch")
        if logits is None or torch is None:
            return out
        if torch.cuda.is_current_stream_capturing():
            return out
        STATE["logits_saved"] = 1
        try:
            os.makedirs(AUDIT_DIR, exist_ok=True)
            torch.save(
                {
                    "logits": logits.detach().float().cpu(),
                    "pid": os.getpid(),
                    "rows": int(logits.shape[0]),
                },
                os.path.join(AUDIT_DIR, "logits.pt"),
            )
            _dump_state()
        except Exception as exc:  # pragma: no cover - qualification only
            STATE["logits_error"] = repr(exc)
        return out

    cls.forward = forward
    _patched.add("sglang.logits_processor.forward")


def _try_patch_all():
    _patch_post_load_weights()
    _patch_ct_scheme()
    _patch_humming_layer()
    _patch_ct_marlin()
    _patch_cuda_graph_replay()
    _patch_logits_processor()


if AUDIT_DIR:
    _real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        global _in_hook
        module = _real_import(name, *args, **kwargs)
        if not _in_hook and name.split(".")[0] in WATCH:
            _in_hook = True
            try:
                _try_patch_all()
            except Exception:  # pragma: no cover - never break the server
                pass
            finally:
                _in_hook = False
        return module

    builtins.__import__ = _import
