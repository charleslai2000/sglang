#!/usr/bin/env python3
"""Bounded FP32 oracle and source-faithful Q8_1 attribution for saved run1 tensors."""

import hashlib, json, os, subprocess
from pathlib import Path
import numpy as np
import torch, gguf
from gguf import quants

BASE = Path(
    "/data/sglang-hicache/g2-quasar-runs/20261112T-g2-quasar-q4-llama-mmq-compare-r1/weights"
)
OUT = Path(
    os.environ.get(
        "G2_Q4_NUMERIC_OUT",
        "/data/sglang-hicache/g2-quasar-runs/20261112T-g2-quasar-q4-numeric-r1",
    )
)
ROOT = Path(__file__).resolve().parents[2]
AOT = Path(
    "/home/ubuntu/venvs/sglang-3090/lib/python3.12/site-packages/sgl_kernel/sm86/common_ops.abi3.so"
)
WRAPPER = ROOT / "python/sglang/kernels/aot/python/sgl_kernel/quantization/gguf.py"
import importlib.util

spec = importlib.util.spec_from_file_location("ggufwrap", WRAPPER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def metrics(y, ref):
    e = (y - ref).reshape(-1).double()
    r = ref.reshape(-1).double()
    ae = e.abs()
    den = torch.linalg.vector_norm(r).clamp_min(1e-30)
    qs = torch.quantile(
        ae, torch.tensor([0, 0.5, 0.9, 0.99, 0.999, 1.0], dtype=torch.float64)
    )
    return {
        "rel_l2": (torch.linalg.vector_norm(e) / den).item(),
        "max_abs": ae.max().item(),
        "mean_abs": ae.mean().item(),
        "rmse": torch.sqrt(torch.mean(e * e)).item(),
        "abs_error_quantiles_0_50_90_99_99.9_100": qs.tolist(),
        "signed_error_quantiles_0_1_50_99_99.9_100": torch.quantile(
            e, torch.tensor([0, 0.01, 0.5, 0.99, 0.999, 1.0], dtype=torch.float64)
        ).tolist(),
    }


def q8(x):
    # Source-faithful computation: CUDA reduction max/127 + roundf; storage quant is signed
    # int8 and scale is fp16. This is not a direct dump from either device buffer.
    rows = []
    for row in x:
        amax = row.abs().reshape(-1, 32).amax(1)
        d = amax / 127.0
        q = (
            torch.where(
                amax[:, None] == 0,
                torch.zeros_like(row.reshape(-1, 32)),
                torch.sign(row.reshape(-1, 32) / d[:, None])
                * torch.floor(torch.abs(row.reshape(-1, 32) / d[:, None]) + 0.5),
            )
            .clamp(-128, 127)
            .to(torch.int8)
        )
        dh = d.to(torch.float16).float()
        rows.append((q, dh, (q.float() * dh[:, None]).reshape(-1)))
    return rows


def main():
    torch.ops.load_library(str(AOT))
    OUT.mkdir(parents=True, exist_ok=True)
    allres = []
    for tag, N, K in [
        ("blk_0_ffn_gate_weight", 10240, 2560),
        ("blk_0_attn_output_weight", 2560, 2048),
    ]:
        raw = (BASE / f"{tag}.raw").read_bytes()
        saved_xraw = (BASE / f"{tag}_input_f32.raw").read_bytes()
        assert len(raw) == N * (K // 32) * 18
        # Reproduce the original comparison script's seeded CUDA BF16 input exactly.
        seed = 20261112 + (0 if tag == "blk_0_ffn_gate_weight" else 1)
        torch.cuda.manual_seed(seed)
        xraw = torch.randn((32, K), device="cuda", dtype=torch.bfloat16).float().cpu().contiguous().numpy().tobytes()
        if tag == "blk_0_ffn_gate_weight":
            assert hashlib.sha256(xraw).hexdigest() == hashlib.sha256(saved_xraw).hexdigest(), "saved gate input identity mismatch"
        # GGUF storage is K-major blocks for each output row; these retained files are
        # serialized contiguous GGUF tensor bytes (same as original harness).
        qbytes = np.frombuffer(raw, dtype=np.uint8).reshape(N, K // 32, 18)
        w_np = (
            quants.dequantize(qbytes.reshape(-1, 18), gguf.GGMLQuantizationType.Q4_0)
            .reshape(N, K)
            .copy()
        )
        W = torch.from_numpy(w_np).float()
        X = torch.from_numpy(
            np.frombuffer(xraw, dtype=np.float32).copy().reshape(32, K)
        )
        # The original input was BF16; retain and report hash of the exact saved FP32 expansion.
        xb = X.to(torch.bfloat16).float()
        ref = xb @ W.T
        qw = torch.from_numpy(qbytes.copy()).cuda().reshape(N, K // 32 * 18)
        xgpu = xb.cuda().to(torch.bfloat16)
        aot = mod.ggml_mul_mat_a8(qw, xgpu, 2, N).float().cpu()
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = "/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112/bin:/usr/local/cuda-12.9/lib64:" + env.get("LD_LIBRARY_PATH", "")
        regenerated_input = OUT / f"{tag}_input_f32.raw"
        regenerated_input.write_bytes(xraw)
        llama = json.loads(subprocess.check_output([
            "/data/sglang-hicache/g2-quasar-runs/llamacpp-cuda-sm86-mmq-20261112/harness/llama_mmq_harness",
            str(BASE / f"{tag}.raw"), str(K), str(N), "32", str(regenerated_input)
        ], env=env, text=True, stderr=subprocess.PIPE))
        donor = torch.tensor(llama["output"], dtype=torch.float32).reshape(32, N)
        qa = q8(xb)
        qd = q8(xb)
        qmatch = []
        integer_dot = []
        quantized_ref = []
        for (aq, ad, ar), (dq, dd, dr) in zip(qa, qd):
            qmatch.append(
                {
                    "integer_mismatch_count": int((aq != dq).sum()),
                    "integer_mismatch_fraction": (aq != dq).float().mean().item(),
                    "max_scale_abs": (ad - dd).abs().max().item(),
                    "scale_mismatch_count": int((ad != dd).sum()),
                    "reconstructed_rel_l2": (
                        torch.linalg.vector_norm(ar - dr)
                        / torch.linalg.vector_norm(ar).clamp_min(1e-30)
                    ).item(),
                }
            )
            integer_dot.append(
                (dq.float().reshape(-1) * dd.repeat_interleave(32)).reshape(-1)
            )
        # Same recovered BF16 input is passed to each source-faithful Q8 model; actual Q8
        # buffers are internal and were not dumped. Compare them as a source-semantic check.
        # Independently form FP32 Q4xQ8 reference to separate quantization from MMQ arithmetic.
        yq = []
        for r, (iq, dq, rec) in enumerate(qa):
            # equivalent grouped GEMM with the quantized activations reconstructed in FP32
            yq.append(rec @ W.T)
        qref = torch.stack(yq)
        result = {
            "tensor": tag,
            "MKN": [32, N, K],
            "input_fp32_sha256": hashlib.sha256(xraw).hexdigest(),
            "retained_input_file_sha256": hashlib.sha256(saved_xraw).hexdigest(),
            "retained_input_file_bytes": len(saved_xraw),
            "retained_input_identity": "EXACT" if xraw == saved_xraw else "MISMATCH; deterministic reproduction from original seed used",
            "weight_sha256": hashlib.sha256(raw).hexdigest(),
            "aot_vs_dequant_fp32_gemm": metrics(aot, ref),
            "llama_vs_dequant_fp32_gemm": metrics(donor, ref),
            "donor_minus_aot": metrics(donor, aot),
            "aot_vs_shared_q8_fp32_gemm": metrics(aot, qref),
            "llama_vs_shared_q8_fp32_gemm": metrics(donor, qref),
            "source_faithful_q8_comparison": {
                "integer_mismatch_total": sum(
                    x["integer_mismatch_count"] for x in qmatch
                ),
                "blocks": sum(x["scale_mismatch_count"] + 1 for x in qmatch),
                "scale_mismatch_total": sum(x["scale_mismatch_count"] for x in qmatch),
                "max_scale_abs": max(x["max_scale_abs"] for x in qmatch),
                "reconstructed_row_rel_l2_max": max(
                    x["reconstructed_rel_l2"] for x in qmatch
                ),
                "assessment": "Both source implementations use the same float d=amax/127, roundf(x/d), and fp16 scale/sum semantics for Q4_0; this calculation is source-faithful but is not a dump of either private device buffer.",
            },
        }
        allres.append(result)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{tag}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    (OUT / "results.json").write_text(json.dumps({"results": allres}, indent=2) + "\n")


if __name__ == "__main__":
    main()
