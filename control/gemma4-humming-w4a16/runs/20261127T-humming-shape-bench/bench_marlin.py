#!/home/ubuntu/venvs/sglang-3090/bin/python3
import json, pathlib, torch
from safetensors import safe_open
from sglang.srt.layers.parameter import PackedvLLMParameter
from sglang.srt.layers.parameter import permute_param_layout_
from sglang.kernels.ops.quantization.gptq_marlin_repack import gptq_marlin_repack
from sglang.srt.layers.quantization.marlin_utils import (
    marlin_permute_scales,
    marlin_make_workspace,
    apply_gptq_marlin_linear,
)
from sgl_kernel.scalar_type import scalar_types

ROOT = pathlib.Path("/data/sglang-hicache/gemma4/model")
OUT = pathlib.Path(__file__).parent
assert torch.cuda.is_available() and torch.cuda.get_device_capability() == (8, 6)
prefixes = [
    "model.language_model.layers.0.self_attn.q_proj",
    "model.language_model.layers.0.mlp.gate_proj",
    "model.language_model.layers.0.mlp.down_proj",
]
res = []
with safe_open(str(ROOT / "model.safetensors"), framework="pt", device="cpu") as f:
    for prefix in prefixes:
        w = f.get_tensor(prefix + ".weight_packed").clone().cuda()
        s = f.get_tensor(prefix + ".weight_scale").clone().cuda()
        shape = f.get_tensor(prefix + ".weight_shape").tolist()
        n, k = map(int, shape)
        param = PackedvLLMParameter(
            data=w, input_dim=1, output_dim=0, packed_dim=1, packed_factor=8, weight_loader=lambda *args, **kwargs: None
        )
        permute_param_layout_(param, input_dim=0, output_dim=1, packed_dim=0)
        q = gptq_marlin_repack(
            param.data.contiguous(),
            torch.empty(0, device="cuda", dtype=torch.int32),
            size_k=k,
            size_n=n,
            num_bits=4,
        )
        sp = marlin_permute_scales(s.T.contiguous(), size_k=k, size_n=n, group_size=32)
        ws = marlin_make_workspace(torch.device("cuda"))
        out = {"prefix": prefix, "N": n, "K": k, "dtype": "bf16", "shapes": []}
        for m in [8, 16, 32, 1024, 1280, 4096]:
            torch.manual_seed(20261127 + m)
            x = torch.randn((m, k), device="cuda", dtype=torch.bfloat16)
            y = apply_gptq_marlin_linear(
                input=x,
                weight=q,
                weight_scale=sp,
                weight_zp=torch.empty(0, device="cuda", dtype=torch.int32),
                g_idx=torch.empty(0, device="cuda", dtype=torch.int32),
                g_idx_sort_indices=torch.empty(0, device="cuda", dtype=torch.int32),
                workspace=ws,
                wtype=scalar_types.uint4b8,
                output_size_per_partition=n,
                input_size_per_partition=k,
                is_k_full=True,
                use_fp32_reduce=True,
            )
            torch.cuda.synchronize()
            times = []
            for _ in range(4):
                y = apply_gptq_marlin_linear(
                    input=x,
                    weight=q,
                    weight_scale=sp,
                    weight_zp=torch.empty(0, device="cuda", dtype=torch.int32),
                    g_idx=torch.empty(0, device="cuda", dtype=torch.int32),
                    g_idx_sort_indices=torch.empty(0, device="cuda", dtype=torch.int32),
                    workspace=ws,
                    wtype=scalar_types.uint4b8,
                    output_size_per_partition=n,
                    input_size_per_partition=k,
                    is_k_full=True,
                    use_fp32_reduce=True,
                )
            torch.cuda.synchronize()
            for _ in range(21):
                a = torch.cuda.Event(enable_timing=True)
                b = torch.cuda.Event(enable_timing=True)
                a.record()
                y = apply_gptq_marlin_linear(
                    input=x,
                    weight=q,
                    weight_scale=sp,
                    weight_zp=torch.empty(0, device="cuda", dtype=torch.int32),
                    g_idx=torch.empty(0, device="cuda", dtype=torch.int32),
                    g_idx_sort_indices=torch.empty(0, device="cuda", dtype=torch.int32),
                    workspace=ws,
                    wtype=scalar_types.uint4b8,
                    output_size_per_partition=n,
                    input_size_per_partition=k,
                    is_k_full=True,
                    use_fp32_reduce=True,
                )
                b.record()
                b.synchronize()
                times.append(a.elapsed_time(b))
            med = sorted(times)[len(times) // 2]
            out["shapes"].append(
                {
                    "M": m,
                    "marlin_ms_median": med,
                    "output_shape": list(y.shape),
                    "finite": bool(torch.isfinite(y).all().item()),
                }
            )
            print(
                json.dumps(
                    {"prefix": prefix, "N": n, "K": k, "M": m, "marlin_ms_median": med}
                ),
                flush=True,
            )
        res.append(out)
        del w, s, q, sp, ws
        torch.cuda.empty_cache()
(OUT / "marlin-results.json").write_text(
    json.dumps(
        {
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(),
            "capability": torch.cuda.get_device_capability(),
            "results": res,
        },
        indent=2,
    )
)
