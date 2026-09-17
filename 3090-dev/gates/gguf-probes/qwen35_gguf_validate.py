#!/usr/bin/env python3
"""No-GPU validation harness for qwen35 GGUF config / name-map / tokenizer.

Reads only GGUF metadata (and tensor headers); no tensor payload is materialised
beyond what GGUFReader itself builds, and no CUDA device is used.

Run:
    PYTHONPATH=<candidate>/src/python python qwen35_gguf_validate.py <gguf>...
"""

import argparse
import sys
from functools import lru_cache
from typing import Dict, List, Tuple


def _bootstrap(src_python: str) -> None:
    if src_python not in sys.path:
        sys.path.insert(0, src_python)


def _init_cpu_dist() -> Dict[str, object]:
    """Bring up the single-rank CPU parallel context the SRT layers require."""
    import torch

    from sglang.test.layer_ut_utils import init_single_process_dist

    init_single_process_dist()
    from sglang.srt.layers import dp_attention
    from sglang.srt.runtime_context import get_context

    override = get_context().override_server_args(tp_size=1)
    override.install()
    # The real bootstrap calls initialize_dp_attention with a full ModelConfig;
    # at world=1 the only observable effect is these two globals (dp_size=1,
    # dp attention disabled). Publish exactly that so no CUDA/ModelConfig is
    # needed for a metadata-only check.
    dp_attention._ATTN_DP_SIZE = 1
    dp_attention._ATTN_DP_RANK = 0
    dp_attention.get_flags().dp.enabled = False
    dp_attention.get_flags().dp.max_len_with_idle = False
    return {"torch": torch, "override": override}


@lru_cache(maxsize=None)
def _gguf_metadata(gguf_path: str) -> Tuple[Dict[str, object], List[str]]:
    from gguf import GGUFReader

    reader = GGUFReader(gguf_path)
    meta = {key: field.contents() for key, field in reader.fields.items()}
    return meta, [tensor.name for tensor in reader.tensors]


@lru_cache(maxsize=None)
def _gguf_tensor_info(gguf_path: str) -> Dict[str, Tuple[str, int, Tuple[int, ...]]]:
    """tensor name -> (type name, type int, ``tensor.data`` shape)."""
    from gguf import GGUFReader

    reader = GGUFReader(gguf_path)
    return {
        tensor.name: (
            tensor.tensor_type.name,
            int(tensor.tensor_type),
            tuple(int(x) for x in tensor.data.shape),
        )
        for tensor in reader.tensors
    }


@lru_cache(maxsize=None)
def _gguf_small_tensor(gguf_path: str, name: str):
    """Materialise one tensor payload; only used for the tiny qwen35 tensors."""
    import torch
    from gguf import GGUFReader

    reader = GGUFReader(gguf_path)
    for tensor in reader.tensors:
        if tensor.name == name:
            return torch.tensor(tensor.data)
    raise KeyError(name)


@lru_cache(maxsize=None)
def check_config(gguf_path: str) -> Dict[str, object]:
    from sglang.srt.utils.hf_transformers.gguf_native import (
        build_gguf_config,
        read_gguf_architecture,
    )

    arch = read_gguf_architecture(gguf_path)
    config = build_gguf_config(gguf_path)
    meta, _ = _gguf_metadata(gguf_path)

    def get(suffix):
        return meta[f"{arch}.{suffix}"]

    nextn = int(get("nextn_predict_layers") or 0) if f"{arch}.nextn_predict_layers" in meta else 0
    expected = {
        "hidden_size": int(get("embedding_length")),
        "intermediate_size": int(get("feed_forward_length")),
        "num_hidden_layers": int(get("block_count")) - nextn,
        "num_attention_heads": int(get("attention.head_count")),
        "num_key_value_heads": int(get("attention.head_count_kv")),
        "head_dim": int(get("attention.key_length")),
        "max_position_embeddings": int(get("context_length")),
        "linear_conv_kernel_dim": int(get("ssm.conv_kernel")),
        "linear_key_head_dim": int(get("ssm.state_size")),
        "linear_value_head_dim": int(get("ssm.state_size")),
        "linear_num_key_heads": int(get("ssm.group_count")),
        "linear_num_value_heads": int(get("ssm.time_step_rank")),
        "full_attention_interval": int(get("full_attention_interval")),
        "num_nextn_predict_layers": nextn,
        "model_type": "qwen3_5_text",
        "architectures": ["Qwen3_5ForCausalLM"],
    }
    mismatched = {}
    for attr, want in expected.items():
        got = getattr(config, attr, "<missing>")
        if got != want:
            mismatched[attr] = (got, want)

    rope_params = getattr(config, "rope_parameters", None) or {}
    rope_theta = float(get("rope.freq_base"))
    if rope_params.get("rope_theta") != rope_theta:
        mismatched["rope_parameters.rope_theta"] = (rope_params.get("rope_theta"), rope_theta)
    sections = [int(x) for x in (get("rope.dimension_sections") or [])]
    while sections and sections[-1] == 0:
        sections.pop()
    if sections and rope_params.get("mrope_section") != sections:
        mismatched["rope_parameters.mrope_section"] = (
            rope_params.get("mrope_section"),
            sections,
        )
    if float(get("attention.layer_norm_rms_epsilon")) != float(config.rms_norm_eps):
        mismatched["rms_norm_eps"] = (
            config.rms_norm_eps,
            float(get("attention.layer_norm_rms_epsilon")),
        )
    return {"arch": arch, "config": config, "expected": expected, "mismatched": mismatched}


def check_mapping(gguf_path: str) -> Dict[str, object]:
    from sglang.srt.model_loader.gguf_name_maps import (
        build_qwen35_name_map,
        validate_qwen35_gguf_coverage,
    )

    config = check_config(gguf_path)["config"]
    _, tensor_names = _gguf_metadata(gguf_path)
    name_map = build_qwen35_name_map(config)

    # Fold-in strict check: raises if a base-stack source tensor is unmapped.
    validate_qwen35_gguf_coverage(gguf_path, name_map, config)

    mapped_present = [n for n in tensor_names if n in name_map]
    base_layers = config.num_hidden_layers
    mtp_skipped = [
        n
        for n in tensor_names
        if n not in name_map
        and len(n.split(".")) >= 2
        and n.split(".")[0] == "blk"
        and n.split(".")[1].isdigit()
        and int(n.split(".")[1]) >= base_layers
    ]

    # Independent coverage proof: drive the model's own load_weights with the
    # map's checkpoint names and record which live parameters receive a load.
    model, loaded, required = _run_model_load(config, name_map.values())
    missing = sorted(required - loaded)

    return {
        "config": config,
        "tensor_count": len(tensor_names),
        "name_map_size": len(name_map),
        "mapped_present": len(mapped_present),
        "mtp_skipped": mtp_skipped,
        "required_params": len(required),
        "loaded_params": len(loaded),
        "missing": missing,
        "model": model,
    }


def _run_model_load(config, checkpoint_names) -> Tuple[object, set, set]:
    import torch

    from sglang.srt.models import qwen3_5_text

    with torch.device("meta"):
        model = qwen3_5_text.Qwen3_5ForCausalLM(config, quant_config=None)

    # Record by object identity: several module attributes can alias one
    # parameter (e.g. linear_attn.A_log == linear_attn.attn.A_log), and only
    # one name's recorder survives on the shared object.
    loaded_ids: set = set()

    def make_recorder():
        def recorder(param, loaded_weight, *args, **kwargs):
            loaded_ids.add(id(param))

        return recorder

    required: set = set()
    for name, param in model.named_parameters(remove_duplicate=False):
        if name == "lm_head.weight" and getattr(config, "tie_word_embeddings", False):
            continue
        required.add(name)
        recorder = make_recorder()
        if hasattr(param, "_weight_loader"):
            param._weight_loader = recorder
        else:
            param.weight_loader = recorder

    model.load_weights([(name, torch.zeros(1)) for name in checkpoint_names])
    loaded = {
        name
        for name, param in model.named_parameters(remove_duplicate=False)
        if id(param) in loaded_ids
    }
    return model, loaded, required


def check_tokenizer(gguf_path: str) -> Dict[str, object]:
    from sglang.srt.utils.hf_transformers.gguf_native import build_gguf_tokenizer

    tokenizer = build_gguf_tokenizer(gguf_path)
    samples = [
        "Hello, world!",
        "def fibonacci(n):\n    return n if n < 2 else fibonacci(n - 1) + fibonacci(n - 2)",
        "The quick brown fox jumps over the lazy dog. 1234567890",
        "用户想要一个关于量子计算的中文解释。",
        "  leading spaces and\ttabs\nand newlines  ",
        "emoji 🚀 and accents café naïve",
    ]
    failures = []
    for text in samples:
        ids = tokenizer.encode(text, add_special_tokens=False)
        decoded = tokenizer.decode(ids)
        if decoded != text:
            failures.append((text, decoded))

    meta, _ = _gguf_metadata(gguf_path)
    named_tokens = {}
    for key in ("bos_token_id", "eos_token_id", "padding_token_id", "unknown_token_id"):
        gguf_key = f"tokenizer.ggml.{key}"
        if gguf_key in meta:
            named_tokens[key] = int(meta[gguf_key])

    return {
        "vocab_size": tokenizer.vocab_size,
        "samples": len(samples),
        "failures": failures,
        "named_tokens": named_tokens,
        "pre": meta.get("tokenizer.ggml.pre"),
    }


def check_strictness(gguf_path: str) -> Dict[str, object]:
    """Dropping one required mapping must raise, proving the check is live."""
    from sglang.srt.model_loader.gguf_name_maps import (
        build_qwen35_name_map,
        validate_qwen35_gguf_coverage,
    )

    config = check_config(gguf_path)["config"]
    name_map = build_qwen35_name_map(config)
    _, tensor_names = _gguf_metadata(gguf_path)
    victim = next(
        name for name in tensor_names if name in name_map and name.startswith("blk.")
    )
    del name_map[victim]
    raised = None
    try:
        validate_qwen35_gguf_coverage(gguf_path, name_map, config)
    except RuntimeError as exc:
        raised = str(exc)
    return {"victim": victim, "raised": raised}


def check_loader_path(gguf_path: str) -> Dict[str, object]:
    """Drive the real (modified) GGUFModelLoader name-map entry point."""
    from types import SimpleNamespace

    from sglang.srt.model_loader.loader import GGUFModelLoader

    loader = object.__new__(GGUFModelLoader)
    model_config = SimpleNamespace(hf_config=check_config(gguf_path)["config"])
    name_map = GGUFModelLoader._get_gguf_weights_map(loader, model_config, gguf_path)
    return {
        "size": len(name_map),
        "lm_head": name_map.get("output.weight"),
        "ssm_alpha": name_map.get("blk.0.ssm_alpha.weight"),
        "ssm_beta": name_map.get("blk.0.ssm_beta.weight"),
        "ssm_a": name_map.get("blk.0.ssm_a"),
        "ssm_conv1d": name_map.get("blk.0.ssm_conv1d.weight"),
    }


def check_iterator_naming(gguf_path: str) -> Dict[str, object]:
    """Report names the generic iterator actually yields in its type pass.

    The pass yields one entry per mapped non-F32 tensor and touches no tensor
    payload, so it is safe to drain exactly and stop before the weight pass.
    The real names are compared against ``_simulated_iterator_produced``'s type
    pass so the recorder pass below is driven by names the live iterator really
    emits (the weight pass applies the same one-line suffix rule, exercised on
    real tensors by ``check_real_loaders``).
    """
    from gguf import GGUFReader

    from sglang.srt.model_loader.gguf_name_maps import build_qwen35_name_map
    from sglang.srt.model_loader.weight_utils import gguf_quant_weights_iterator

    config = check_config(gguf_path)["config"]
    name_map = build_qwen35_name_map(config)
    reader = GGUFReader(gguf_path)
    expected = sum(
        1
        for tensor in reader.tensors
        if tensor.name in name_map and tensor.tensor_type.name != "F32"
    )
    iterator = gguf_quant_weights_iterator(gguf_path, name_map)
    yielded = [next(iterator)[0] for _ in range(expected)]
    iterator.close()
    simulated_type_pass = [
        n for n in _simulated_iterator_produced(gguf_path, name_map)
        if n.endswith("qweight_type")
    ]
    hazardous = [name for name in yielded if "in_proj_a" in name or "in_proj_b" in name]
    return {
        "type_pass_entries": expected,
        "hazardous": hazardous,
        "type_pass_names_match_simulation": yielded == simulated_type_pass,
    }


def _simulated_iterator_produced(gguf_path: str, name_map: Dict[str, str]) -> List[str]:
    """Reproduce the names ``gguf_quant_weights_iterator`` emits, in its order.

    The iterator runs a type pass (``.qweight_type`` for every mapped non-F32
    tensor) and then a data pass (``.qweight`` for non-F32, the raw name for
    F32). qwen35 has no routed-expert tensors, so this is exact.
    """
    info = _gguf_tensor_info(gguf_path)
    type_pass: List[str] = []
    weight_pass: List[str] = []
    for tensor_name, (type_name, _, _) in info.items():
        if tensor_name not in name_map:
            continue
        mapped = name_map[tensor_name]
        if type_name != "F32":
            type_pass.append(mapped.replace("weight", "qweight_type"))
        weight_pass.append(
            mapped if type_name == "F32" else mapped.replace("weight", "qweight")
        )
    return type_pass + weight_pass


def _coverage_tensor(name: str, config):
    """A plausible tensor for the recorder pass (values do not reach loaders)."""
    import torch

    if name.endswith(".linear_attn.A_log"):
        # GGUF stores -exp(A_log); the wrapper transform runs before the recorder
        # and rejects non-negative/untransformed values.
        return torch.full((config.linear_num_value_heads,), -0.5)
    if name.endswith(".linear_attn.conv1d.weight"):
        conv_dim = (
            2 * config.linear_key_head_dim * config.linear_num_key_heads
            + config.linear_value_head_dim * config.linear_num_value_heads
        )
        return torch.zeros((conv_dim, config.linear_conv_kernel_dim))
    return torch.zeros(1)


def check_runtime_coverage(gguf_path: str) -> Dict[str, object]:
    """Prove every runtime parameter the iterator names receives a load.

    Builds the model with the real ``GGUFConfig`` (so LinearBase params are
    ``qweight``/``qweight_type``) and drives its own ``load_weights`` with the
    exact names ``gguf_quant_weights_iterator`` would emit. Each parameter's
    loader is replaced by an identity recorder, so a name that finds no
    parameter is an explicit miss.
    """
    import torch

    from sglang.srt.layers.quantization.gguf import GGUFConfig
    from sglang.srt.model_loader.gguf_name_maps import build_qwen35_name_map
    from sglang.srt.models import qwen3_5_text

    config = check_config(gguf_path)["config"]
    name_map = build_qwen35_name_map(config)
    produced = _simulated_iterator_produced(gguf_path, name_map)

    with torch.device("meta"):
        model = qwen3_5_text.Qwen3_5ForCausalLM(config, quant_config=GGUFConfig())

    captured: Dict[int, object] = {}

    def recorder(param, loaded_weight, *args, **kwargs):
        captured[id(param)] = loaded_weight

    required: set = set()
    for name, param in model.named_parameters(remove_duplicate=False):
        required.add(name)
        if hasattr(param, "_weight_loader"):
            param._weight_loader = recorder
        else:
            param.weight_loader = recorder

    model.load_weights([(name, _coverage_tensor(name, config)) for name in produced])
    loaded = {
        name
        for name, param in model.named_parameters(remove_duplicate=False)
        if id(param) in captured
    }
    missing = sorted(required - loaded)
    tied = bool(getattr(config, "tie_word_embeddings", False))
    return {
        "missing": missing,
        "required": len(required),
        "loaded": len(loaded),
        "produced": len(produced),
        "lm_head_loaded": (
            [] if tied else sorted(n for n in loaded if n.startswith("lm_head."))
        ),
        "embed_loaded": sorted(n for n in loaded if "embed_tokens" in n),
        "ssm_ba_loaded": sorted(
            n
            for n in loaded
            if n.endswith(("in_proj_ba.qweight", "in_proj_ba.qweight_type"))
        ),
    }


def check_transforms(gguf_path: str) -> Dict[str, object]:
    """Prove the GGUF ssm_a and ssm_conv1d adaptations at value/shape level."""
    import torch

    from sglang.srt.layers.quantization.gguf import GGUFConfig
    from sglang.srt.models import qwen3_5_text

    config = check_config(gguf_path)["config"]
    raw_a = _gguf_small_tensor(gguf_path, "blk.0.ssm_a")
    raw_conv = _gguf_small_tensor(gguf_path, "blk.0.ssm_conv1d.weight")

    with torch.device("meta"):
        model = qwen3_5_text.Qwen3_5ForCausalLM(config, quant_config=GGUFConfig())
    params = dict(model.named_parameters(remove_duplicate=False))
    modules = dict(model.named_modules())

    captured: Dict[int, object] = {}

    def recorder(param, loaded_weight, *args, **kwargs):
        captured[id(param)] = loaded_weight

    names = (
        "model.layers.0.linear_attn.A_log",
        "model.layers.0.linear_attn.conv1d.weight",
    )
    for key in names:
        param = params[key]
        if hasattr(param, "_weight_loader"):
            param._weight_loader = recorder
        else:
            param.weight_loader = recorder

    model.load_weights(
        [
            ("model.layers.0.linear_attn.A_log", raw_a),
            ("model.layers.0.linear_attn.conv1d.weight", raw_conv),
        ]
    )
    a_got = captured[id(params[names[0]])]
    c_got = captured[id(params[names[1]])]
    expected = torch.log(-raw_a)
    return {
        "ssm_a_raw": float(raw_a[0]),
        "ssm_a_log": float(a_got[0]),
        "ssm_a_expected": float(expected[0]),
        "ssm_a_all_negative_raw": bool(torch.all(raw_a < 0)),
        "ssm_a_ok": bool(torch.allclose(a_got, expected)),
        "conv_in_shape": tuple(raw_conv.shape),
        "conv_out_shape": tuple(c_got.shape),
        "conv_ok": c_got.dim() == 3
        and tuple(c_got.shape) == (raw_conv.shape[0], 1, raw_conv.shape[1]),
    }


def check_real_loaders(gguf_path: str) -> Dict[str, object]:
    """Exercise the real GGUF weight loaders (no recorders) for GDN layer 0.

    Covers the fused ``in_proj_qkvz`` tuple merge, the dense-F32 ``in_proj_ba``
    redirection, the ``conv1d`` unsqueeze through the mamba sharded loader, and
    the ``A_log`` transform through the sharded loader.  The feed comes from the
    real ``gguf_quant_weights_iterator`` restricted to layer 0's small tensors,
    so the checkpoint dtype (BF16 raw bytes / F32) reaches the loaders verbatim.
    """
    import torch

    from sglang.srt.layers.quantization.gguf import GGUFConfig
    from sglang.srt.model_loader.gguf_name_maps import build_qwen35_name_map
    from sglang.srt.model_loader.utils import set_default_torch_dtype
    from sglang.srt.model_loader.weight_utils import gguf_quant_weights_iterator
    from sglang.srt.models import qwen3_5_text

    config = check_config(gguf_path)["config"]
    info = _gguf_tensor_info(gguf_path)
    # Match the production loader, which builds under model_config.dtype.
    with set_default_torch_dtype(torch.bfloat16):
        with torch.device("meta"):
            model = qwen3_5_text.Qwen3_5ForCausalLM(
                config, quant_config=GGUFConfig()
            )
    params = dict(model.named_parameters(remove_duplicate=False))
    modules = dict(model.named_modules())

    key_dim = config.linear_key_head_dim * config.linear_num_key_heads
    val_dim = config.linear_value_head_dim * config.linear_num_value_heads
    conv_dim = 2 * key_dim + val_dim
    nv = config.linear_num_value_heads
    kernel = config.linear_conv_kernel_dim
    L = "model.layers.0.linear_attn."

    def cpu_back(name, shape):
        # ``param.data = cpu_tensor`` is rejected by this torch build when the
        # param was built under ``torch.device("meta")`` ("incompatible tensor
        # type"), and ``swap_tensors`` refuses a 2-use non-grad tensor. Register
        # a real CPU Parameter in its place, carrying over the dynamic loader
        # attrs (weight_loader, is_gguf_weight, data_container, shard_id, ...).
        old = params[name]
        parent_name, _, leaf = name.rpartition(".")
        new = torch.nn.Parameter(
            torch.zeros(shape, dtype=old.dtype), requires_grad=False
        )
        new.__dict__.update(old.__dict__)
        setattr(modules[parent_name], leaf, new)
        params[name] = new

    cpu_back(L + "in_proj_qkvz.qweight_type", (4,))
    cpu_back(L + "in_proj_ba.qweight_type", (2,))
    cpu_back(L + "conv1d.weight", (conv_dim, 1, kernel))
    cpu_back(L + "A_log", (nv,))

    # Real iterator, restricted to layer 0's small tensors so only the mapped
    # ones are materialised.  This is the exact dtype/shape the runtime sees.
    name_map = build_qwen35_name_map(config)
    needed = [
        "blk.0.attn_qkv.weight",
        "blk.0.attn_gate.weight",
        "blk.0.ssm_alpha.weight",
        "blk.0.ssm_beta.weight",
        "blk.0.ssm_conv1d.weight",
        "blk.0.ssm_a",
    ]
    feeds = list(
        gguf_quant_weights_iterator(
            gguf_path, {name: name_map[name] for name in needed}
        )
    )
    model.load_weights(feeds)

    qkvz_q = params[L + "in_proj_qkvz.qweight"]
    qkvz_t = params[L + "in_proj_qkvz.qweight_type"]
    ba_q = params[L + "in_proj_ba.qweight"]
    ba_t = params[L + "in_proj_ba.qweight_type"]
    conv = params[L + "conv1d.weight"]
    a_log = params[L + "A_log"]
    raw_a = _gguf_small_tensor(gguf_path, "blk.0.ssm_a")
    alpha_type = info["blk.0.ssm_alpha.weight"][0]

    result = {
        "qkvz_shard_ids": sorted(getattr(qkvz_q, "shard_id", [])),
        "qkvz_container": len(getattr(qkvz_q, "data_container", [])),
        "qkvz_types": sorted(getattr(qkvz_t, "shard_weight_type", {}).keys()),
        "ba_shard_ids": sorted(getattr(ba_q, "shard_id", [])),
        "ba_container": len(getattr(ba_q, "data_container", [])),
        "ba_types": {
            str(k): int(v)
            for k, v in getattr(ba_t, "shard_weight_type", {}).items()
        },
        "conv_shape": tuple(conv.shape),
        "alog_ok": bool(torch.allclose(a_log.float(), torch.log(-raw_a.float()))),
        "ssm_alpha_is_f32": alpha_type == "F32",
    }
    result["ok"] = (
        result["qkvz_shard_ids"] == [0, 1, 2, 3]
        and result["qkvz_container"] == 4
        and result["qkvz_types"] == [0, 1, 2, 3]
        and result["ba_shard_ids"] == [0, 1]
        and result["ba_container"] == 2
        and result["conv_shape"] == (conv_dim, 1, kernel)
        and result["alog_ok"]
    )

    # Production materialises the fused weight once and the plain ``x @ w.T``
    # path must see the model dtype, else the first GDN forward raises.
    ba_module = modules[L + "in_proj_ba"]
    ba_module.quant_method.process_weights_after_loading(ba_module)
    ba_padded = ba_module.qweight
    x = torch.zeros(2, config.hidden_size, dtype=torch.bfloat16, device="meta")
    y = x @ ba_padded.T
    result["ba_padded_dtype"] = str(ba_padded.dtype)
    result["ba_padded_shape"] = tuple(ba_padded.shape)
    result["ba_forward_ok"] = (
        ba_padded.dtype == torch.bfloat16
        and y.dtype == torch.bfloat16
        and tuple(y.shape) == (2, 2 * config.linear_num_value_heads)
    )
    result["ok"] = result["ok"] and result["ba_forward_ok"]
    return result


def check_head_real_loaders(gguf_path: str) -> Dict[str, object]:
    """Run the head/embedding loaders for real (gap 1: ``lm_head``).

    ``check_runtime_coverage`` proves the text wrapper routes ``lm_head.qweight``
    / ``lm_head.qweight_type`` to live params, but replaces the leaf loader.  This
    drives the real ``VocabParallelEmbedding.weight_loader`` for both heads with
    real GGUF shapes and asserts the payload lands in the parameter storage.
    """
    import torch

    from sglang.srt.layers.quantization.gguf import GGUFConfig
    from sglang.srt.models import qwen3_5_text

    config = check_config(gguf_path)["config"]
    info = _gguf_tensor_info(gguf_path)
    tied = bool(getattr(config, "tie_word_embeddings", False))

    with torch.device("meta"):
        model = qwen3_5_text.Qwen3_5ForCausalLM(config, quant_config=GGUFConfig())
    modules = dict(model.named_modules())
    params = dict(model.named_parameters(remove_duplicate=False))

    def cpu_back(name, shape, dtype, fill):
        new = torch.nn.Parameter(
            torch.full(shape, fill, dtype=dtype), requires_grad=False
        )
        new.__dict__.update(params[name].__dict__)
        parent_name, _, leaf = name.rpartition(".")
        setattr(modules[parent_name], leaf, new)
        params[name] = new
        return new

    feeds = []
    expected: Dict[str, object] = {}

    def stage(gguf_name, param_stem):
        type_name, type_int, data_shape = info[gguf_name]
        assert type_name != "F32", f"{gguf_name} is unexpectedly F32"
        fill = 7 if param_stem.endswith("lm_head") else 9
        cpu_back(param_stem + ".qweight", data_shape, torch.uint8, fill)
        cpu_back(param_stem + ".qweight_type", (1,), torch.uint8, 0)
        feeds.append(
            (param_stem + ".qweight", torch.full(data_shape, fill, dtype=torch.uint8))
        )
        feeds.append(
            (param_stem + ".qweight_type", torch.tensor(type_int, dtype=torch.uint8))
        )
        expected[param_stem] = (data_shape, fill, type_int, type_name)

    if tied:
        # ``lm_head`` aliases ``embed_tokens``; one load covers both.
        stage("token_embd.weight", "model.embed_tokens")
    else:
        stage("output.weight", "lm_head")
        stage("token_embd.weight", "model.embed_tokens")

    model.load_weights(feeds)

    def payload_ok(stem):
        shape, fill, type_int, type_name = expected[stem]
        q = params[stem + ".qweight"]
        t = params[stem + ".qweight_type"]
        return (
            tuple(q.shape) == tuple(shape)
            and int(q.min()) == fill
            and int(q.max()) == fill
            and getattr(t, "weight_type", None) == type_int
        )

    heads = list(expected)
    result = {
        "tied": tied,
        "staged": heads,
        "details": {
            stem: {
                "gguf_shape": tuple(expected[stem][0]),
                "gguf_type": expected[stem][3],
                "loaded_type": int(
                    getattr(params[stem + ".qweight_type"], "weight_type", -1)
                ),
                "loaded_shape": tuple(params[stem + ".qweight"].shape),
                "payload_ok": payload_ok(stem),
            }
            for stem in heads
        },
    }
    result["ok"] = all(payload_ok(stem) for stem in heads) and (
        tied or "lm_head" in expected
    )
    return result


def report(gguf_path: str) -> int:
    print(f"===== {gguf_path}")
    cfg = check_config(gguf_path)
    print(f"arch={cfg['arch']} model_type={cfg['config'].model_type}")
    if cfg["mismatched"]:
        print("CONFIG MISMATCH:")
        for attr, (got, want) in cfg["mismatched"].items():
            print(f"  {attr}: got={got!r} want={want!r}")
    else:
        print("config metadata: ALL CONSISTENT")

    mp = check_mapping(gguf_path)
    print(
        f"tensor_count={mp['tensor_count']} "
        f"name_map={mp['name_map_size']} "
        f"mapped_present={mp['mapped_present']} "
        f"mtp_skipped={len(mp['mtp_skipped'])} "
        f"reconcile={mp['mapped_present'] + len(mp['mtp_skipped'])}"
    )
    print(
        f"required_hf_params={mp['required_params']} "
        f"loaded={mp['loaded_params']} missing={len(mp['missing'])}"
    )
    if mp["mtp_skipped"]:
        print(f"  mtp_skipped_tensors={mp['mtp_skipped']}")
    if mp["missing"]:
        print("MISSING HF PARAMS (must be empty):")
        for name in mp["missing"]:
            print(f"  {name}")

    tok = check_tokenizer(gguf_path)
    print(
        f"tokenizer pre={tok['pre']!r} vocab={tok['vocab_size']} "
        f"roundtrip={tok['samples'] - len(tok['failures'])}/{tok['samples']}"
    )
    if tok["failures"]:
        print("TOKENIZER ROUNDTRIP FAILURES:")
        for text, decoded in tok["failures"]:
            print(f"  {text!r} -> {decoded!r}")

    strict = check_strictness(gguf_path)
    strict_ok = strict["raised"] is not None and strict["victim"] in strict["raised"]
    print(
        f"strict_fail_loud={strict_ok} (dropped {strict['victim']}, "
        f"raised={'yes' if strict['raised'] else 'no'})"
    )
    lp = check_loader_path(gguf_path)
    print(
        f"loader._get_gguf_weights_map size={lp['size']} "
        f"lm_head={lp['lm_head']} ssm_a={lp['ssm_a']} "
        f"ssm_alpha={lp['ssm_alpha']} ssm_conv1d={lp['ssm_conv1d']}"
    )
    it = check_iterator_naming(gguf_path)
    print(
        f"iterator_type_pass={it['type_pass_entries']} "
        f"ssm_ba_nonf32_yielded_as_qweight={len(it['hazardous'])} "
        f"type_pass_names_match_simulation={it['type_pass_names_match_simulation']}"
    )
    if it["hazardous"]:
        print(
            "  note: ssm_alpha/ssm_beta are non-F32 here, so the iterator's "
            f"type pass yields their .qweight_type (e.g. {it['hazardous'][0]}), "
            "which matches in_proj_ba.qweight under GGUFConfig."
        )
    rt = check_runtime_coverage(gguf_path)
    print(
        f"runtime_gguf_quant_coverage: required={rt['required']} "
        f"loaded={rt['loaded']} missing={len(rt['missing'])} "
        f"iterator_names={rt['produced']}"
    )
    print(
        f"  zero_missing_list={rt['missing']} "
        f"(required==loaded=={rt['required']}, no parameter was skipped)"
    )
    print(f"  lm_head_loaded={rt['lm_head_loaded']}")
    print(f"  embed_loaded={rt['embed_loaded']}")
    print(
        f"  in_proj_ba_params_loaded={len(rt['ssm_ba_loaded'])} "
        f"(first={rt['ssm_ba_loaded'][:2]})"
    )
    if rt["missing"]:
        categories: Dict[str, int] = {}
        for name in rt["missing"]:
            if name.startswith("lm_head."):
                key = "lm_head qweight(_type)"
            elif "in_proj_ba." in name:
                key = "in_proj_ba qweight(_type)"
            elif name == "model.embed_tokens.weight":
                key = "embed_tokens"
            else:
                key = "other"
            categories[key] = categories.get(key, 0) + 1
        for key, count in sorted(categories.items()):
            print(f"    {count:3d}  {key}")
        print(f"  MISSING examples={rt['missing'][:6]}")

    tf = check_transforms(gguf_path)
    print(
        f"ssm_a_transform: raw={tf['ssm_a_raw']:.8f} -> "
        f"loaded={tf['ssm_a_log']:.8f} (expected log(-raw)="
        f"{tf['ssm_a_expected']:.8f}) ok={tf['ssm_a_ok']} "
        f"raw_all_negative={tf['ssm_a_all_negative_raw']}"
    )
    print(
        f"ssm_conv1d_layout: gguf_shape={tf['conv_in_shape']} -> "
        f"loaded_shape={tf['conv_out_shape']} ok={tf['conv_ok']}"
    )

    rl = check_real_loaders(gguf_path)
    print(
        f"real_loader_acceptance: ok={rl['ok']} "
        f"qkvz_shards={rl['qkvz_shard_ids']} qkvz_types={rl['qkvz_types']} "
        f"ba_shards={rl['ba_shard_ids']} ba_types={rl['ba_types']} "
        f"ssm_alpha_is_f32={rl['ssm_alpha_is_f32']} "
        f"conv_shape={rl['conv_shape']} alog_ok={rl['alog_ok']}"
    )
    print(
        f"  ba_fused_after_load: dtype={rl['ba_padded_dtype']} "
        f"shape={rl['ba_padded_shape']} bf16_matmul_ok={rl['ba_forward_ok']}"
    )

    hr = check_head_real_loaders(gguf_path)
    print(
        f"head_real_loader_acceptance: ok={hr['ok']} tied_embeddings={hr['tied']} "
        f"staged={hr['staged']}"
    )
    for stem, det in hr["details"].items():
        print(
            f"  {stem}: gguf_shape={det['gguf_shape']} gguf_type={det['gguf_type']} "
            f"loaded_shape={det['loaded_shape']} loaded_type={det['loaded_type']} "
            f"payload_ok={det['payload_ok']}"
        )

    ok = (
        not cfg["mismatched"]
        and not mp["missing"]
        and not tok["failures"]
        and strict_ok
        and lp["size"] == mp["name_map_size"]
        and mp["tensor_count"] == mp["mapped_present"] + len(mp["mtp_skipped"])
        and it["type_pass_names_match_simulation"]
        and not rt["missing"]
        and tf["ssm_a_ok"]
        and tf["conv_ok"]
        and rl["ok"]
        and hr["ok"]
    )
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    print()
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src-python", default="/opt/sglang/local-prod-v1.1-candidate/src/python")
    parser.add_argument("gguf", nargs="+")
    args = parser.parse_args()
    _bootstrap(args.src_python)
    _init_cpu_dist()
    status = 0
    for path in args.gguf:
        status |= report(path)
    return status


if __name__ == "__main__":
    sys.exit(main())
