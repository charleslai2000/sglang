#!/usr/bin/env python3
"""Staged eager/PyTorch-CUDA-Graph diagnostics for the pinned GGML backend."""

import hashlib, json
from pathlib import Path
import numpy as np, torch, gguf
from gguf import quants
from inspect_cuda_graph import inspect
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
        extra_include_paths=[str(BASE / "ggml-pinned-source/include"), str(BASE / "ggml-pinned-source/src")],
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
        wf = WEIGHTS / (key + ".raw")
        xfpath = NUM / (key + "_input_f32.raw")
        xfpath = xfpath if xfpath.exists() else WEIGHTS / (key + "_input_f32.raw")
        raw = xfpath.read_bytes()
        assert (
            hashlib.sha256(t.data.tobytes()).hexdigest()
            == hashlib.sha256(wf.read_bytes()).hexdigest()
        )
        xf = torch.from_numpy(
            np.frombuffer(raw, dtype=np.float32).copy().reshape(32, K)
        ).cuda()
        q = torch.from_numpy(t.data.copy()).cuda().reshape(N, K // 32 * 18)
        x = xf.to(torch.bfloat16).contiguous()
        h = ext.create_borrowed(q, x)
        w = (
            torch.from_numpy(
                quants.dequantize(t.data.reshape(-1, 18), gguf.GGMLQuantizationType.Q4_0).copy()
            )
            .cuda()
            .reshape(N, K)
            .float()
            .T
        )
        ref = xf @ w
        ext.prewarm(h)
        eager = ext.read_output(h)
        row = {
            "tensor": name,
            "input_sha256": hashlib.sha256(raw).hexdigest(),
            "eager_fp32_rel_l2": rel(eager, ref),
            "eager_finite": bool(torch.isfinite(eager).all()),
        }
        cap = torch.cuda.Stream()
        cap.wait_stream(torch.cuda.current_stream())
        with torch.cuda.graph(g := torch.cuda.CUDAGraph(keep_graph=True), stream=cap):
            capture_info = ext.capture_info(h)
            capture_graph = ext.graph_capture(h)
        torch.cuda.current_stream().wait_stream(cap)
        row["capture_stream_info"] = capture_info
        row["graph_nodes"] = inspect(capture_graph)
        graph_stream = torch.cuda.Stream()
        graph_stream.wait_stream(torch.cuda.current_stream())
        with torch.cuda.stream(graph_stream):
            g.replay()
        torch.cuda.current_stream().wait_stream(graph_stream)
        captured = ext.read_output(h)
        row["capture_equals_eager"] = torch.equal(captured, eager)
        row["capture_fp32_rel_l2"] = rel(captured, ref)
        row["capture_stream_ptr"] = cap.cuda_stream
        with torch.cuda.stream(graph_stream):
            g.replay()
        torch.cuda.current_stream().wait_stream(graph_stream)
        same = ext.read_output(h)
        row["replay_equals_capture"] = torch.equal(same, captured)
        x.copy_(torch.roll(x, 1, 1))
        ext.update(h, x)
        with torch.cuda.stream(graph_stream):
            g.replay()
        torch.cuda.current_stream().wait_stream(graph_stream)
        updated = ext.read_output(h)
        row["updated_input_fp32_rel_l2"] = rel(updated, x.float() @ w)
        row["updated_input_changed"] = not torch.equal(updated, captured)
        row["addresses"] = ext.info(h)
        results.append(row)
        del h, q, x, xf, eager, captured, same, updated
    out = {"gpu": torch.cuda.get_device_name(), "results": results}
    print(json.dumps(out, indent=2))
    Path(
        "/data/sglang-hicache/g2-quasar-runs/20261113T-t004-stage-diagnostic.json"
    ).write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main()
