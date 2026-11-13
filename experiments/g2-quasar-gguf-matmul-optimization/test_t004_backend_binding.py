#!/usr/bin/env python3
"""Exact-pin donor backend checks, including borrowed loaded-weight storage."""

import hashlib, json
from pathlib import Path
import numpy as np
import torch, gguf
from torch.utils.cpp_extension import load

ROOT = Path(__file__).resolve().parents[2]
BASE = Path("/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112")
NUM = Path("/data/sglang-hicache/g2-quasar-runs/20261112T-g2-quasar-q4-numeric-r1")
WEIGHTS = Path(
    "/data/sglang-hicache/g2-quasar-runs/20261112T-g2-quasar-q4-llama-mmq-compare-r1/weights"
)
MODEL = Path("/data/models/gemma4-quasar-q4_0/gemma-4-E4B-it-QUASAR-Q4_0.gguf")


def main():
    ext = load(
        name="t004_llama_backend",
        sources=[
            str(
                ROOT
                / "experiments/g2-quasar-gguf-matmul-optimization/t004_backend_binding.cpp"
            )
        ],
        extra_include_paths=[
            str(BASE / "ggml-pinned-source/include"),
            str(BASE / "ggml-pinned-source/src"),
        ],
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
    rows = []
    for name, key in [
        ("blk.0.ffn_gate.weight", "blk_0_ffn_gate_weight"),
        ("blk.0.attn_output.weight", "blk_0_attn_output_weight"),
        ("blk.0.attn_q.weight", "blk_0_attn_q_weight"),
    ]:
        t = next(t for t in reader.tensors if t.name == name)
        K, N = map(int, t.shape)
        wf = WEIGHTS / (key + ".raw")
        xf = NUM / (key + "_input_f32.raw")
        xf = xf if xf.exists() else WEIGHTS / (key + "_input_f32.raw")
        assert (
            hashlib.sha256(t.data.tobytes()).hexdigest()
            == hashlib.sha256(wf.read_bytes()).hexdigest()
        )
        q = torch.from_numpy(t.data.copy()).cuda().reshape(N, K // 32 * 18)
        xf32 = torch.from_numpy(np.fromfile(xf, dtype=np.float32).reshape(32, K)).cuda()
        x = xf32.to(torch.bfloat16).contiguous()
        h = ext.create_borrowed(q, x)
        addr = ext.info(h)
        assert addr[0] == q.data_ptr(), (
            f"GGML weight pointer {addr[0]:x} != loaded torch weight {q.data_ptr():x}"
        )
        ext.prewarm(h)
        cap = torch.cuda.Stream()
        cap.wait_stream(torch.cuda.current_stream())
        with torch.cuda.graph(g := torch.cuda.CUDAGraph(keep_graph=True), stream=cap):
            ext.run(h)
        torch.cuda.current_stream().wait_stream(cap)
        g.replay()
        g.replay()
        torch.cuda.synchronize()
        y1 = ext.read_output(h)
        x2 = torch.roll(x, 1, 1).contiguous()
        ext.update(h, x2)
        g.replay()
        y2 = ext.read_output(h)
        assert addr == ext.info(h)
        w = (
            torch.from_numpy(
                gguf.quants.dequantize(
                    t.data.reshape(-1, 18), gguf.GGMLQuantizationType.Q4_0
                ).copy()
            )
            .cuda()
            .reshape(N, K)
            .float()
            .T
        )
        ref1 = xf32 @ w
        ref2 = x2.float() @ w
        rel = lambda a, b: (
            torch.linalg.vector_norm(a - b) / torch.linalg.vector_norm(b)
        ).item()
        r1, r2 = rel(y1, ref1), rel(y2, ref2)
        assert (
            torch.isfinite(y1).all()
            and torch.isfinite(y2).all()
            and not torch.equal(y1, y2)
        )
        assert r1 < 0.01 and r2 < 0.01, (name, r1, r2)
        rows.append(
            {
                "tensor": name,
                "MKN": [32, N, K],
                "weight_ptr_equal": addr[0] == q.data_ptr(),
                "addresses": addr,
                "graph_capture_replay": True,
                "updated_input_changed": True,
                "rel_l2": [r1, r2],
            }
        )
        ext.destroy(h)
        del h, q, x, xf32, x2, y1, y2
    print(json.dumps({"gpu": torch.cuda.get_device_name(), "results": rows}, indent=2))


if __name__ == "__main__":
    main()
