"""Bounded out-of-serving-path proof that a replayed CUDA graph runs Humming GEMM.

Builds a real Humming layer from synthetic compressed-tensors packed weights via
the same schema conversion + transform the post-load branch uses, captures a CUDA
graph around it, replays the graph under torch.profiler, and records whether the
replay's kernels include the Humming GEMM template. Also compares the converted
GEMM with an FP32 dequantized reference.
"""

import json
import os
import sys

import torch

from humming.schema.compressed_tensors import CompressedTensorsWeightSchema
import sglang.srt.layers.quantization.humming as humming_method

humming_method._lazy_import_humming()

N, K = 1024, 2560
out_path = sys.argv[1]


class Layer(torch.nn.Module):
    pass


def build():
    torch.manual_seed(7)
    schema = CompressedTensorsWeightSchema(
        quant_method="compressed-tensors",
        format="pack-quantized",
        type="int",
        num_bits=4,
        strategy="group",
        symmetric=True,
        group_size=32,
    )
    packed = torch.randint(
        -(2**31), 2**31 - 1, (N, K // 8), dtype=torch.int32, device="cuda"
    )
    scale = torch.rand((N, K // 32), dtype=torch.bfloat16, device="cuda") * 0.02
    weight_schema, tensors = schema.convert_humming(
        tensors={"weight_packed": packed, "weight_scale": scale},
        shape_n_stacks=[512, 256, 256],
        shape_k_stacks=[K],
        param_dtype=torch.bfloat16,
    )
    layer = Layer()
    layer.output_partition_sizes = [512, 256, 256]
    layer.output_partition_sizes_sum = N
    layer.input_size_per_partition = K
    layer.with_bias = False
    layer.param_dtype = torch.bfloat16
    layer.weight = torch.nn.Parameter(tensors["weight"], requires_grad=False)
    layer.weight_scale = torch.nn.Parameter(
        tensors["weight_scale"], requires_grad=False
    )
    layer.register_buffer("locks", torch.zeros(1024, dtype=torch.int32, device="cuda"))
    humming_method.HummingMethod.prepare_layer_meta(
        layer=layer,
        shape_n=N,
        shape_k=K,
        weight_schema=weight_schema,
        input_schema=None,
        pad_n_to_multiple=256,
        pad_k_to_multiple=128,
        has_bias=False,
        torch_dtype=torch.bfloat16,
    )
    humming_method.HummingMethod.transform_humming_layer(layer)
    return layer, packed, scale


def main():
    layer, packed, scale = build()
    config = {"use_f16_accum": False, "gemm_type": "dense"}
    x = torch.randn(16, K, dtype=torch.bfloat16, device="cuda")
    out = humming_method.HummingMethod.forward_layer(
        layer=layer, inputs=x, compute_config=config
    )
    torch.cuda.synchronize()

    words = packed.to(torch.int64).unsqueeze(-1)
    shifts = torch.arange(0, 32, 4, dtype=torch.int64, device="cuda")
    codes = ((words >> shifts) & 0xF).reshape(N, K).to(torch.float32) - 8.0
    reference = x.to(torch.float32) @ (
        codes * scale.float().repeat_interleave(32, dim=1)
    ).transpose(0, 1)
    diff = (out.float() - reference).abs()

    graph = torch.cuda.CUDAGraph()
    static_out = torch.empty_like(out)
    with torch.cuda.graph(graph):
        static_out.copy_(
            humming_method.HummingMethod.forward_layer(
                layer=layer, inputs=x, compute_config=config
            )
        )
    graph.replay()
    torch.cuda.synchronize()
    with torch.profiler.profile(
        activities=[torch.profiler.ProfilerActivity.CUDA]
    ) as prof:
        graph.replay()
        torch.cuda.synchronize()
    names = [
        event.key for event in prof.key_averages() if event.self_device_time_total > 0
    ]
    humming_kernels = [name for name in names if name.startswith("void humming<")]

    result = {
        "layer_shape": [N, K],
        "group_size": 32,
        "gemm_max_abs": float(diff.max()),
        "gemm_rel_of_reference_mean": float(diff.max() / reference.abs().mean()),
        "replay_kernels": names[:8],
        "replay_humming_kernel_count": len(humming_kernels),
        "replay_executes_humming": len(humming_kernels) > 0,
    }
    with open(out_path, "w") as f:
        json.dump(result, f, indent=1, sort_keys=True)
    print(
        json.dumps({k: v for k, v in result.items() if k != "replay_kernels"}, indent=1)
    )
    assert result["replay_executes_humming"]
    assert result["gemm_rel_of_reference_mean"] < 0.05


if __name__ == "__main__":
    sys.exit(main())
