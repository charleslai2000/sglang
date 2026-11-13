#!/usr/bin/env python3
"""Test the independently integrated pinned Q4_0 MMQ on random M=32 tensors."""

import json
import torch
import common_ops  # noqa: F401 - registers the AOT operator
from sgl_kernel.quantization import gguf_q4_0_llama_mmq_m32


def main():
    torch.manual_seed(17429)
    results = []
    for n, k in ((128, 512), (2048, 2048), (2560, 2560)):
        # Packed Q4_0 block format: fp16 scale followed by 32 4-bit values.
        weight = torch.empty((n, k // 32 * 18), device="cuda", dtype=torch.uint8)
        weight.random_(0, 256)
        x = torch.randn((32, k), device="cuda", dtype=torch.bfloat16)
        out = gguf_q4_0_llama_mmq_m32(weight, x)
        torch.cuda.synchronize()
        assert out.shape == (32, n) and out.dtype == torch.bfloat16
        assert torch.isfinite(out).all()
        graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):
            captured = gguf_q4_0_llama_mmq_m32(weight, x)
        graph.replay()
        torch.cuda.synchronize()
        eager_again = gguf_q4_0_llama_mmq_m32(weight, x)
        torch.cuda.synchronize()
        assert torch.equal(captured, eager_again), (n, k)
        results.append({"N": n, "K": k, "finite": True, "graph_equal": True})
    print(
        json.dumps({"gpu": torch.cuda.get_device_name(), "results": results}, indent=2)
    )


if __name__ == "__main__":
    main()
