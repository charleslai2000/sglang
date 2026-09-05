"""Research-only real GGUF representation gate; never used to load serving weights."""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from gguf import GGUFReader, GGMLQuantizationType
from gguf.quants import dequantize

from reference import gdn_layer_grouped, gdn_layer_tiled


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--output", default="real-oracle.json")
    args = parser.parse_args()
    torch.set_default_device(args.device)
    torch.set_num_threads(8)
    reader = GGUFReader(args.model)
    tensors = {t.name: t for t in reader.tensors}
    K, ratio, D, hidden, length = 16, 3, 128, 5120, 5
    V = K * ratio
    perm = np.arange(V).reshape(K, ratio).T.ravel()
    inverse = np.argsort(perm)
    blocks = (inverse[:, None] * D + np.arange(D)).ravel()
    rng = np.random.default_rng(0)
    x = rng.normal(size=(length, hidden))
    results = {"device": args.device, "torch": torch.__version__, "layers": {}}

    def read(name, shape):
        tensor = tensors[name]
        value = dequantize(tensor.data, tensor.tensor_type)
        assert value.shape == shape, (name, value.shape, shape)
        assert tuple(reversed(tensor.shape.tolist())) == shape
        assert np.isfinite(value).all(), name
        # Independent raw-byte validation, bypassing reader.data and dequantize.
        if tensor.tensor_type in (GGMLQuantizationType.F32, GGMLQuantizationType.BF16):
            dtype = "<f4" if tensor.tensor_type == GGMLQuantizationType.F32 else "<u2"
            raw = np.memmap(
                args.model,
                mode="r",
                dtype=dtype,
                offset=tensor.data_offset,
                shape=shape,
            )
            if tensor.tensor_type == GGMLQuantizationType.BF16:
                raw = (raw.astype(np.uint32) << 16).view(np.float32)
            np.testing.assert_array_equal(value, raw, err_msg=name)
        return value.astype(np.float64)

    for layer in (0, 5, 9, 13):
        prefix = f"blk.{layer}."
        qkv = read(prefix + "attn_qkv.weight", (2 * K * D + V * D, hidden))
        A = read(prefix + "ssm_a", (V,))
        assert (A < 0).all(), "Expected GGUF negative A, not HF A_log"
        A_log = np.log(-A)
        np.testing.assert_allclose(-np.exp(A_log), A, rtol=1e-14, atol=1e-14)
        tiled = dict(
            q=qkv[: K * D],
            k=qkv[K * D : 2 * K * D],
            v=qkv[2 * K * D :],
            z=read(prefix + "attn_gate.weight", (V * D, hidden)),
            a=read(prefix + "ssm_alpha.weight", (V, hidden)),
            b=read(prefix + "ssm_beta.weight", (V, hidden)),
            A_log=A_log,
            dt_bias=read(prefix + "ssm_dt.bias", (V,)),
            conv=read(prefix + "ssm_conv1d.weight", (2 * K * D + V * D, 4)),
            out=read(prefix + "ssm_out.weight", (hidden, V * D)),
            norm_w=read(prefix + "ssm_norm.weight", (D,)),
        )
        grouped = {key: value.copy() for key, value in tiled.items()}
        for name in ("v", "z"):
            grouped[name] = tiled[name][blocks]
        for name in ("a", "b", "A_log", "dt_bias"):
            grouped[name] = tiled[name][inverse]
        grouped["conv"][2 * K * D :] = tiled["conv"][2 * K * D :][blocks]
        grouped["out"] = tiled["out"][:, blocks]
        kw = dict(T=length, K=K, r=ratio, head_k=D, head_v=D, hidden=hidden)
        canonical = gdn_layer_grouped(x, grouped, **kw)
        candidate = gdn_layer_tiled(x, tiled, **kw)
        metrics = {}
        for name, expected in canonical.items():
            actual = candidate[name]
            if name in ("v_proj", "z_proj"):
                actual = actual[:, blocks]
            elif name in ("a_proj", "b_proj", "gate", "beta"):
                actual = actual[:, inverse]
            elif name in ("conv_in", "conv_out"):
                actual = torch.cat(
                    (actual[:, : 2 * K * D], actual[:, 2 * K * D :][:, blocks]), -1
                )
            elif name in ("v_conv", "state", "attn_out", "norm_out", "z_gated"):
                actual = actual[:, inverse]
            assert torch.isfinite(actual).all(), name
            torch.testing.assert_close(actual, expected, rtol=1e-9, atol=1e-9, msg=name)
            delta = (actual - expected).abs()
            metrics[name] = {
                "max_abs": delta.max().item(),
                "normalized_max": (
                    delta.max() / expected.abs().max().clamp_min(1e-12)
                ).item(),
            }
        metrics["A_range"] = [float(A.min()), float(A.max())]
        results["layers"][str(layer)] = metrics
        print(
            f"layer {layer}: ALL {len(canonical)} NODES PASS, out={metrics['out_proj']}",
            flush=True,
        )
    results["pass"] = True
    Path(args.output).write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
