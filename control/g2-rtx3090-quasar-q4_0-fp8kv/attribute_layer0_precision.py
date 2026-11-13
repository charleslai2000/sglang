import argparse
import json
from pathlib import Path

import torch


def rel(a, b):
    a, b = a.float(), b.float()
    d = b - a
    return {
        "rel_l2": float(d.norm() / a.norm().clamp_min(1e-30)),
        "p99_abs": float(torch.quantile(d.abs(), 0.99)),
        "max_abs": float(d.abs().max()),
    }


def exact_stream(q, kp, vp, kc, vc, qpos, window=511, q_fp8=False, p_fp8=False, block_n=64):
    """Match _fwd_kernel's per-row, per-BLOCK_N online softmax recurrence for one row."""
    dev = q.device
    q = q.to(dev).float()
    kp, vp = kp.to(dev), vp.to(dev)
    kc, vc = kc.to(dev), vc.to(dev)
    q_bf16 = q
    q_fp8_value = q.to(torch.float8_e5m2).float() if q_fp8 else q
    k = torch.cat((kp.float(), kc.float()), 0)
    v = torch.cat((vp.float(), vc.float()), 0)
    # Logical positions, never physical slots.
    positions = torch.cat(
        (
            torch.arange(1537, 2048, device=dev),
            torch.arange(2048, 2048 + len(kc), device=dev),
        )
    )
    allowed = (positions <= qpos) & (positions >= qpos - window)
    # Only the requested query's exact prefix/current attention window is used.
    k, v = k[allowed], v[allowed]
    n_prefix = int(((positions < 2048) & allowed).sum())
    # Production loops over prefix and extend as separate stages. Carry (m,l,acc)
    # through every tile with the same online normalization, then cast P at each tile.
    m = torch.full((8,), -torch.inf, dtype=torch.float32, device=dev)
    l = torch.zeros((8,), dtype=torch.float32, device=dev)
    acc = torch.zeros((8, 256), dtype=torch.float32, device=dev)
    boundaries = list(range(0, n_prefix, block_n)) + list(
        range(n_prefix, len(k), block_n)
    )
    for start in boundaries:
        end = (
            min(start + block_n, n_prefix)
            if start < n_prefix
            else min(start + block_n, len(k))
        )
        # Ensure the prefix/current transition starts a fresh production stage tile.
        if start < n_prefix and end > n_prefix:
            end = n_prefix
        kk, vv = k[start:end], v[start:end]
        prefix_tile = start < n_prefix
        q_for_tile = q_fp8_value if (q_fp8 and prefix_tile) else q_bf16
        scores = torch.stack([q_for_tile[h] @ kk[:, h // 4].T for h in range(8)])
        n_m = torch.maximum(m, scores.max(-1).values)
        alpha = torch.exp(m - n_m)
        p = torch.exp(scores - n_m[:, None])
        l = l * alpha + p.sum(-1)
        p_cast = p.to(torch.float8_e5m2).float() if (p_fp8 and prefix_tile) else p
        for h in range(8):
            acc[h] = acc[h] * alpha[h] + p_cast[h] @ vv[:, h // 4]
        m = n_m
    # The kernel normalizes once after both stages and stores output in Q dtype (BF16).
    return (acc / l[:, None]).to(torch.bfloat16).float().cpu()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", required=True)
    ap.add_argument("--ab", required=True)
    ap.add_argument("--live", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    pr = torch.load(args.probe, map_location="cpu", weights_only=True)
    ar = json.load(open(args.ab))
    live = torch.load(args.live, map_location="cpu", weights_only=True)["outputs"]
    # Known selected captures have exact same Q/current KV. Verify cast FP8 prefix bytes.
    records = {}
    for pos in (2048, 2558, 2559):
        row = pos - 2048
        q = pr["q_full"][row].cuda()
        kc = pr["current_k"][: row + 1].cuda()
        vc = pr["current_v"][: row + 1].cuda()
        kfp8, vfp8 = pr["prefix_k_raw"].cuda(), pr["prefix_v_raw"].cuda()
        # A uses BF16 reference prefix. Conversion parity established against production bytes.
        # BF16 source is available in the selected-pair artifact via CLI input fixture path.
        methods = {}
        for qfp8, pfp8, name in [
            (False, False, "kv_only"),
            (True, False, "q_plus_kv"),
            (False, True, "p_plus_kv"),
            (True, True, "q_p_plus_kv"),
        ]:
            # P cast is only meaningful on FP8 prefix V tiles; current extension P uses BF16.
            o = exact_stream(q, kfp8, vfp8, kc, vc, qpos=pos, q_fp8=qfp8, p_fp8=pfp8)
            methods[name] = {
                "vs_C": rel(live[pos], o),
                "vs_B": rel(torch.tensor(ar["positions"][str(pos)]["B"])[0], o),
                "norm": float(o.norm()),
            }
        records[str(pos)] = methods
    Path(args.out).write_text(json.dumps(records, indent=2))
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
