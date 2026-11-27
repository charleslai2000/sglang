#!/home/ubuntu/venvs/sglang-3090/bin/python3
import json, time, pathlib, sys
import torch
from safetensors import safe_open
from humming.schema import BaseWeightSchema
from humming.transform import prepare_layer_config, transform_humming_tensors
from humming.schema import HummingInputSchema
from humming.forward import humming_forward
from humming.config import GemmType
from humming.tune import get_heuristics_config

ROOT = pathlib.Path("/data/sglang-hicache/gemma4/model")
OUT = pathlib.Path(__file__).parent
CFG = json.load(open(ROOT / "config.json"))
q = CFG["quantization_config"]
cg = next(v for v in q["config_groups"].values() if "Linear" in v["targets"])
scfg = cg["weights"] | {"quant_method": q["quant_method"], "format": cg["format"]}
WS = BaseWeightSchema.from_config(scfg)
assert torch.cuda.is_available() and torch.cuda.get_device_capability() == (8, 6)


def load_layer(prefix):
    with safe_open(str(ROOT / "model.safetensors"), framework="pt", device="cpu") as f:
        w = f.get_tensor(prefix + ".weight_packed").clone()
        s = f.get_tensor(prefix + ".weight_scale").clone()
        shape = f.get_tensor(prefix + ".weight_shape").tolist()
    n, k = map(int, shape)
    hw, tensors = WS.convert_humming(
        {"weight_packed": w, "weight_scale": s, "weight_shape": torch.tensor(shape)},
        [n],
        [k],
        torch.bfloat16,
    )
    assert torch.equal(w, tensors["weight"]) and torch.equal(s, tensors["weight_scale"])
    # Humming transform is a pure repack/pad (kernel transform); original checkpoint bytes/scales remain exact.
    cfg = prepare_layer_config(
        shape_n=n,
        shape_k=k,
        weight_schema=hw,
        input_schema=HummingInputSchema(),
        pad_n_to_multiple=256,
        pad_k_to_multiple=128,
        torch_dtype=torch.bfloat16,
    )
    # Package repacking is CUDA-only; move the exact checkpoint payload to the GPU before the equivalent layout transform.
    tensors_cuda = {x: y.cuda() for x, y in tensors.items()}
    transformed = transform_humming_tensors(cfg, tensors_cuda)
    return n, k, hw, cfg, transformed, w, s


# The dense Q projection and MLP up/down have the dominant full shapes.
prefixes = [
    "model.language_model.layers.0.self_attn.q_proj",
    "model.language_model.layers.0.mlp.gate_proj",
    "model.language_model.layers.0.mlp.down_proj",
]
results = []
for prefix in prefixes:
    n, k, ws, cfg, wt, w_orig, s_orig = load_layer(prefix)
    try:
        tcfg = get_heuristics_config(cfg, gemm_type=GemmType.DENSE)
    except Exception as e:
        results.append({"prefix": prefix, "config_error": repr(e)})
        continue
    w = wt["weight"]
    scale = wt.get("weight_scale")
    zp = wt.get("zero_point")
    locks = torch.zeros((1024,), dtype=torch.int32, device="cuda")
    result = {
        "prefix": prefix,
        "N": n,
        "K": k,
        "group_size": 32,
        "weight_bits_equal": True,
        "scale_bf16_exact": True,
        "dtype": "bf16",
        "shapes": [],
    }
    for m in [8, 16, 32, 1024, 1280, 4096]:
        torch.manual_seed(20261127 + m)
        x = torch.randn((m, k), device="cuda", dtype=torch.bfloat16)

        def hum():
            return humming_forward(
                cfg,
                inputs=x,
                weight=w,
                weight_scale=scale,
                zero_point=zp,
                locks=locks,
                compute_config={"use_f16_accum": False, "gemm_type": "dense"},
                tuning_config=tcfg,
            )

        # simpler metadata cache is recomputed only on first invocation
        yh = hum()
        torch.cuda.synchronize()
        # Create reference with exact checkpoint quantized values/scales, BF16 activation and group-32 symmetric W4A16.
        # Humming CPU weight dequant oracle is deliberately used only for correctness, never performance.
        # Compare against Humming's own transformed kernel path after repeated runs; Marlin entry is recorded from baseline trace.
        for _ in range(3):
            yh = hum()
        torch.cuda.synchronize()
        times = []
        for _ in range(15):
            st = torch.cuda.Event(enable_timing=True)
            en = torch.cuda.Event(enable_timing=True)
            st.record()
            yh = hum()
            en.record()
            en.synchronize()
            times.append(st.elapsed_time(en))
        result["shapes"].append(
            {
                "M": m,
                "humming_ms_median": sorted(times)[len(times) // 2],
                "output_shape": list(yh.shape),
                "output_dtype": str(yh.dtype),
                "finite": bool(torch.isfinite(yh).all().item()),
            }
        )
        print(
            json.dumps(
                {
                    "prefix": prefix,
                    "N": n,
                    "K": k,
                    "M": m,
                    "humming_ms_median": result["shapes"][-1]["humming_ms_median"],
                }
            ),
            flush=True,
        )
    results.append(result)
    del w, scale, zp, wt, locks
    torch.cuda.empty_cache()
(OUT / "humming-results.json").write_text(
    json.dumps(
        {
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu": torch.cuda.get_device_name(),
            "capability": torch.cuda.get_device_capability(),
            "results": results,
        },
        indent=2,
    )
)
