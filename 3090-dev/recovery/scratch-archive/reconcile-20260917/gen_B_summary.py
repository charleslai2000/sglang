import subprocess
import os

REPO = "/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt"
FROZEN = "/opt/sglang/local-prod-v1.1.2-candidate/src"
OUT = "/tmp/opencode/reconcile-20260917"

group_b = [
    "python/sglang/srt/configs/qwen3_5.py",
    "python/sglang/srt/layers/quantization/gguf.py",
    "python/sglang/srt/mem_cache/storage/extent/extent_allocator.py",
    "python/sglang/srt/model_loader/gguf_name_maps.py",
    "python/sglang/srt/model_loader/loader.py",
    "python/sglang/srt/model_loader/weight_utils.py",
    "python/sglang/srt/models/qwen3_5.py",
    "python/sglang/srt/models/qwen3_5_text.py",
    "python/sglang/srt/utils/hf_transformers/gguf_native.py",
]

# Read the B-frozen-only.patch to extract per-file diffs
with open(f"{OUT}/B-frozen-only.patch") as f:
    content = f.read()

# Split by file markers
sections = content.split("=" * 60)
file_diffs = {}
current_file = None
for section in sections:
    lines = section.strip().split('\n')
    for line in lines:
        if line.startswith("# FILE: "):
            current_file = line.replace("# FILE: ", "")
            file_diffs[current_file] = []
        elif current_file and line.startswith("diff -u") or line.startswith("---") or line.startswith("+++") or line.startswith("@@") or line.startswith("+") or line.startswith("-"):
            file_diffs[current_file].append(line)

# Generate per-file summaries
summaries = {}

# qwen3_5.py config
summaries["python/sglang/srt/configs/qwen3_5.py"] = {
    "what": "Adds Qwen3.5 model configuration support. Introduces Qwen3_5Config class with GGUF-specific config builder (from_gguf) that maps GGUF tensor names to HuggingFace naming convention. Adds qwen35 architecture registration so the model loader can instantiate the correct config class when encountering a Qwen3.5 GGUF checkpoint.",
    "option_c": "N/A",
}

# gguf.py quantization layer
summaries["python/sglang/srt/layers/quantization/gguf.py"] = {
    "what": "Extends GGUF quantization layer to handle BF16 weights stored as uint8 in GGUF format. Adds _match_dense_weight_dtype() method that casts unquantized GGUF weights to the layer's compute dtype (F32/BF16), enabling fused_mul_mat_gguf to consume checkpoint shards that store fused tensor shards in a compact dtype.",
    "option_c": "N/A",
}

# extent_allocator.py - OPTION C
summaries["python/sglang/srt/mem_cache/storage/extent/extent_allocator.py"] = {
    "what": "Implements Option-C: adds plan_relocation() method that computes a safe relocation plan for moving extent refs between slots. The method takes victim_slots, key_lengths, and excluded_slots, then produces an ordered list of (key, ExtentRef, component) tuples that can be durably replayed via the existing WAL SET+BATCH_COMMIT protocol. This enables cross-host extent migration without introducing new WAL frame types.",
    "option_c": "CONFIRMED: frozen v1.1.2 == /tmp/opencode/v1.1.2-optionC-20260917/ for this file (SHA256 match: fdbd9e4965b5f0613ff7e12c539995233403f9567d7e7b54f5bb4d93bef10d13)",
}

# gguf_name_maps.py
summaries["python/sglang/srt/model_loader/gguf_name_maps.py"] = {
    "what": "Adds GGUF-to-HF name mapping tables for Qwen3.5 architecture. Defines _QWEN35_GLOBAL_TENSORS dict mapping GGUF tensor names (token_embd.weight, output_norm.weight, output.weight) to HuggingFace parameter names (model.embed_tokens.weight, model.norm.weight, lm_head.weight). Also adds GGUF_HF_NAME_MAP_BUILDERS and GGUF_HF_NAME_MAP_VALIDATORS registries so the loader can look up the correct mapping by architecture name.",
    "option_c": "N/A",
}

# loader.py
summaries["python/sglang/srt/model_loader/loader.py"] = {
    "what": "Integrates GGUF name maps into the model loader. Modifies _get_gguf_weights_map() to import and use GGUF_HF_NAME_MAP_BUILDERS and GGUF_HF_NAME_MAP_VALIDATORS from gguf_name_maps. Adds qwen35 architecture dispatch so GGUF checkpoints with Qwen3.5 architecture are loaded with the correct name mapping and config class.",
    "option_c": "N/A",
}

# weight_utils.py
summaries["python/sglang/srt/model_loader/weight_utils.py"] = {
    "what": "Adds BF16 weight handling for GGUF uint8 quantized weights. When weight_type is BF16 and param dtype is uint8, the weight is reinterpreted as bfloat16 via param.view(torch.bfloat16). This handles GGUF checkpoints that store BF16 weights in a compressed uint8 container format.",
    "option_c": "N/A",
}

# qwen3_5.py model
summaries["python/sglang/srt/models/qwen3_5.py"] = {
    "what": "Implements Qwen3.5 model class with GGUF support. Adds GGUF weight loading path for Qwen3.5 architecture, including handling of fused QKV weights, gated MLP, and ssm_a (Mamba) parameters. Defines parameter name mappings for GGUF-to-model weight conversion and adds support for both dense and quantized GGUF weight formats.",
    "option_c": "N/A",
}

# qwen3_5_text.py model
summaries["python/sglang/srt/models/qwen3_5_text.py"] = {
    "what": "Implements Qwen3.5 text-only model variant. Adds _LM_HEAD_PARAM_NAMES tuple covering both standard and GGUF quantized lm_head parameter names. Implements _gguf_ssm_a_to_a_log() to undo llama.cpp's GGUF-time A_log -> -exp(A_log) storage transform for Mamba SSM parameters. Adds GGUF weight loading with proper dtype handling for text-only Qwen3.5 models.",
    "option_c": "N/A",
}

# gguf_native.py
summaries["python/sglang/srt/utils/hf_transformers/gguf_native.py"] = {
    "what": "Registers Qwen3.5 architecture in the GGUF-native HF transformers integration. Adds Qwen3_5TextConfig import and registers qwen35 architecture with from_gguf builder. Adds tokenizer pattern for Qwen3.5 BPE tokenization that handles the model's specific special token set and regex patterns.",
    "option_c": "N/A",
}

# Write summaries to JSON
with open(f"{OUT}/B-per-file-summary.json", "w") as f:
    import json
    json.dump(summaries, f, indent=2)

print("B per-file summaries written.")

