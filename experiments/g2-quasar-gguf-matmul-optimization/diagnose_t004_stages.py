#!/usr/bin/env python3
import hashlib, json
from pathlib import Path
import numpy as np, torch, gguf
from torch.utils.cpp_extension import load

ROOT = Path(__file__).resolve().parents[2]
BASE = Path("/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112")
NUM = Path("/data/sglang-hicache/g2-quasar-runs/20261112T-g2-quasar-q4-numeric-r1")
WEIGHTS = Path(
    "/data/sglang-hicache/g2-quasar-runs/20261112T-g2-quasar-q4-llama-mmq-compare-r1/weights"
)
MODEL = Path("/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf")


def rel(a, b):
    return (torch.linalg.vector_norm(a - b) / torch.linalg.vector_norm(b)).item()


def main():
    ext = load(
        name="t004_stage_diag",
        sources=[
            str(
                ROOT
                / "experiments/g2-quasar-gguf-matmul-optimization/t004_backend_binding.cpp"
            )
        ],
        extra_include_paths=[str(BASE / "ggml-pinned-source/include")],
        extra_cflags=["-O3", "-std=c++17", "-DGGML_BACKEND_SHARED"],
        extra_ldflags=[
            f"-L{BASE}/pinned-backend-build/src",
            f"-Wl,-rpath,{BASE}/pinned-backend-build/src",
            f"-L{BASE}/pinned-backend-build/src/ggml-cuda",
            f"-Wl,-rpath,{BASE}/pinned-backend-build/src/ggml-cuda",
            "-lggml-cuda",
            "-lggml-cpu",
            "-lggml",
            "-lggml-base",
            "-L/usr/local/cuda-12.9/lib64",
            "-lcudart",
        ],
        with_cuda=True,
        build_directory="/data/sglang-hicache/g2-quasar-runs/t004-backend-binding-build",
        verbose=False,
    )
    reader = gguf.GGUFReader(str(MODEL))
    results = []
    for name, key in [
        ("blk.0.ffn_gate.weight", "blk_0_ffn_gate_weight"),
        ("blk.0.attn_output.weight", "blk_0_attn_output_weight"),
        ("blk.0.attn_q.weight", "blk_0_attn_q_weight"),
    ]:
        t = next(t for t in reader.tensors if t.name == name)
        K, N = map(int, t.shape)
        wfile = WEIGHTS / (key + ".raw")
        xfile = NUM / (key + "_input_f32.raw")
        if not xfile.exists():
            xfile = WEIGHTS / (key + "_input_f32.raw")
        xf = torch.from_numpy(
            np.fromfile(xfile, dtype=np.float32).reshape(32, K)
        ).cuda()
        q = torch.from_numpy(t.data.copy()).cuda().reshape(N, K // 32 * 18)
        x = xf.to(torch.bfloat16).contiguous()
        h = ext.create(q, x)
        ref = (
            xf
            @ torch.from_numpy(
                gguf.quants.dequantize(t.data, gguf.GGMLQuantizationType.Q4_0).copy()
            )
            .cuda()
            .reshape(N, K)
            .float()
            .T
        )
        assert (
            hashlib.sha256(t.data.tobytes()).hexdigest()
            == hashlib.sha256(wfile.read_bytes()).hexdigest()
        )
        ext.prewarm(h)
        eager = ext.read_output(h)
        row = {
            "tensor": name,
            "input_sha256": hashlib.sha256(xf.cpu().numpy().tobytes()).hexdigest(),
            "eager_ref_rel_l2": rel(eager, ref),
            "eager_finite": bool(torch.isfinite(eager).all()),
        }
        cap = torch.cuda.Stream()
        cap.wait_stream(torch.cuda.current_stream())
        with torch.cuda.graph(g := torch.cuda.CUDAGraph(), stream=cap):
            ext.run(h)
        torch.cuda.current_stream().wait_stream(cap)
        g.replay()
        captured = ext.read_output(h)
        row["capture_matches_eager_rel_l2"] = rel(captured, eager)
        row["capture_ref_rel_l2"] = rel(captured, ref)
        row["capture_stream"] = cap.cuda_stream
        row["capture_exec"] = g.raw_cuda_graph_exec()
        g.replay()
        replay = ext.read_output(h)
        row["same_input_replay_rel_l2"] = rel(replay, captured)
        x.copy_(torch.roll(x, 1, 1))
        ext.update(h, x)
        g.replay()
        updated = ext.read_output(h)
        newref = (
            x.float()
            @ torch.from_numpy(
                gguf.quants.dequantize(t.data, gguf.GGMLQuantizationType.Q4_0).copy()
            )
            .cuda()
            .reshape(N, K)
            .float()
            .T
        )
        row["updated_input_ref_rel_l2"] = rel(updated, newref)
        row["updated_vs_old_rel_l2"] = rel(updated, ref)
        row["addresses"] = ext.info(h)
        results.append(row)
        del h, q, xf, x
    print(
        json.dumps({"gpu": torch.cuda.get_device_name(), "results": results}, indent=2)
    )


if __name__ == "__main__":
    main()
