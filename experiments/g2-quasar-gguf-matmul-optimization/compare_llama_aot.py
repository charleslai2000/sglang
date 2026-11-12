#!/usr/bin/env python3
"""Compare AOT MMQ_A8 and pinned llama.cpp MMQ for the same Q4_0 weights/input."""

from pathlib import Path
import importlib.util, json, statistics, subprocess, sys, torch, gguf, os, hashlib

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "python/sglang/kernels/aot/python/sgl_kernel/quantization/gguf.py"
spec = importlib.util.spec_from_file_location("sgl_kernel_gguf_wrapper", WRAPPER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
AOT = Path(
    "/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/sgl_kernel/sm86/common_ops.abi3.so"
)
MODEL = Path("/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf")
HARNESS = Path(
    "/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112/harness/llama_mmq_harness"
)
OUT = Path(os.environ.get(
    "G2_LLAMA_MMQ_RUN_DIR",
    "/data/sglang-hicache/g2-quasar-runs/20261112T-g2-quasar-q4-llama-mmq-compare-r1",
))
SHAPES = [
    ("blk.0.ffn_gate.weight", 32),
    ("blk.0.attn_output.weight", 32),
    ("blk.0.attn_q.weight", 32),
]


def event_ms(fn, n=50, warm=10):
    for _ in range(warm):
        fn()
    torch.cuda.synchronize()
    vals = []
    for _ in range(n):
        a = torch.cuda.Event(enable_timing=True)
        b = torch.cuda.Event(enable_timing=True)
        a.record()
        fn()
        b.record()
        b.synchronize()
        vals.append(a.elapsed_time(b))
    return {
        "median_ms": statistics.median(vals),
        "p10_ms": sorted(vals)[int(0.1 * (n - 1))],
        "p90_ms": sorted(vals)[int(0.9 * (n - 1))],
        "n": n,
    }


def main():
    torch.ops.load_library(str(AOT))
    r = gguf.GGUFReader(str(MODEL))
    results = []
    (OUT / "weights").mkdir(parents=True, exist_ok=True)
    for name, m in SHAPES:
        t = next(x for x in r.tensors if x.name == name)
        torch.manual_seed(20261112 + len(results))
        K, N = map(int, t.shape)
        block, bpb = gguf.GGML_QUANT_SIZES[t.tensor_type]
        packed = K // block * bpb
        q = torch.from_numpy(t.data.copy()).to("cuda").reshape(N, packed)
        raw = OUT / "weights" / (name.replace(".", "_") + ".raw")
        if raw.exists():
            assert raw.read_bytes() == t.data.tobytes()
        else:
            raw.write_bytes(t.data.tobytes())
        x = torch.randn((m, K), device="cuda", dtype=torch.bfloat16)
        # Match the same BF16 bit patterns in llama.cpp's F32 input tensor.
        xf = x.float().cpu().contiguous()
        xfile = OUT / "weights" / (name.replace(".", "_") + "_input_f32.raw")
        xf.numpy().tofile(xfile)
        aot = mod.ggml_mul_mat_a8(q, x, 2, N)
        torch.cuda.synchronize()
        aot_ms = event_ms(lambda: mod.ggml_mul_mat_a8(q, x, 2, N))
        cmd = [str(HARNESS), str(raw), str(K), str(N), str(m), str(xfile)]
        env = __import__("os").environ.copy()
        env["LD_LIBRARY_PATH"] = (
            "/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112/bin:/usr/local/cuda-12.9/lib64:"
            + env.get("LD_LIBRARY_PATH", "")
        )
        # Caller must hold the project GPU lock; harness reports direct GPU backend MMQ timings.
        llama = json.loads(
            subprocess.check_output(cmd, text=True, env=env, stderr=subprocess.PIPE)
        )
        llama_timing = {
            "median_ms": llama.pop("median_ms"),
            "p10_ms": llama.pop("p10_ms"),
            "p90_ms": llama.pop("p90_ms"),
            "n": 30,
        }
        y = torch.tensor(llama["output"], device="cuda", dtype=torch.float32).reshape(
            m, N
        )
        d = (aot.float() - y).abs()
        rel = (
            torch.linalg.vector_norm(aot.float() - y)
            / torch.linalg.vector_norm(y).clamp_min(1e-30)
        ).item()
        results.append(
            {
                "tensor": name,
                "MKN": [m, N, K],
                "aot_including_q8_1_ms": aot_ms,
                "llama_cpp_including_q8_1_ms": llama_timing,
                "parity": {
                    "max_abs": d.max().item(),
                    "rel_l2": rel,
                    "argmax_equal": torch.equal(aot.float().argmax(-1), y.argmax(-1)),
                },
                "input_sha256": hashlib.sha256(xfile.read_bytes()).hexdigest(),
                "weight_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
                "llama_cpp_output_first": llama["output"][:8],
            }
        )
    print(
        json.dumps({"gpu": torch.cuda.get_device_name(), "results": results}, indent=2)
    )


if __name__ == "__main__":
    main()
