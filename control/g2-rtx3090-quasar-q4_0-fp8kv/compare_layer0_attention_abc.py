import argparse
import json
from pathlib import Path

import torch


def metrics(a, b):
    a, b = a.float(), b.float()
    d = b - a
    return {
        "rel_l2": float(d.norm() / a.norm().clamp_min(1e-30)),
        "p99_abs": float(torch.quantile(d.abs(), 0.99)),
        "max_abs": float(d.abs().max()),
        "nonzero": int(torch.count_nonzero(d)),
    }


def reference(q, kp, vp, kc, vc, qpos, prefix_start, scale, window):
    dev = q.device
    k = torch.cat((kp, kc), 0).float().to(dev)
    v = torch.cat((vp, vc), 0).float().to(dev)
    q = q.float().to(dev)
    prefix_pos = torch.arange(prefix_start, prefix_start + len(kp), device=dev)
    current_start = 2048
    current_pos = torch.arange(current_start, current_start + len(kc), device=dev)
    pos = torch.cat((prefix_pos, current_pos))
    mask = (pos <= qpos) & (pos >= qpos - window)
    vals = []
    for h in range(q.shape[1]):
        kh = h // (q.shape[1] // k.shape[1])
        scores = (q[0, h] @ k[:, kh].T) * scale
        vals.append(torch.softmax(scores.masked_fill(~mask, -torch.inf), -1) @ v[:, kh])
    return torch.stack(vals).unsqueeze(0).cpu()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bf16", required=True)
    ap.add_argument("--production-probe", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--production-forward", required=True)
    args = ap.parse_args()
    bf = torch.load(args.bf16, map_location="cpu", weights_only=True)
    pr = torch.load(args.production_probe, map_location="cpu", weights_only=True)
    live_full = torch.load(args.production_forward, map_location="cpu", weights_only=True)
    assert pr["kv_dtype"] == "torch.float8_e5m2" and pr["sliding_window_size"] == 511
    assert pr["sm_scale"] == pr["k_scale"] == pr["v_scale"] == 1.0
    assert pr["window_kv_indices"].numel() == 511 and pr["window_offsets"].tolist() == [
        1537
    ]
    slot_map = {int(s): i for i, s in enumerate(pr["prefix_slots"].tolist())}
    window_rows = torch.tensor(
        [slot_map[int(s)] for s in pr["window_kv_indices"].tolist()], dtype=torch.long
    )
    kraw, vraw = pr["prefix_k_raw"][window_rows], pr["prefix_v_raw"][window_rows]
    bf_slots = {int(s): i for i, s in enumerate(bf["kv_slots"])}
    bf_rows = torch.tensor([bf_slots[int(s)] for s in pr["window_kv_indices"].tolist()], dtype=torch.long)
    bf_kraw, bf_vraw = bf["k_prefix_raw"][bf_rows], bf["v_prefix_raw"][bf_rows]
    if not torch.equal(bf_kraw.to(torch.float8_e5m2), kraw):
        raise RuntimeError("BF16 K prefix cast does not match captured production E5M2 bytes")
    if not torch.equal(bf_vraw.to(torch.float8_e5m2), vraw):
        raise RuntimeError("BF16 V prefix cast does not match captured production E5M2 bytes")
    if not torch.equal(bf["all_k_current"], pr["current_k"]) or not torch.equal(
        bf["all_v_current"], pr["current_v"]
    ):
        raise RuntimeError("BF16 and E5M2 captures do not share identical current K/V")
    kdq, vdq = kraw.to(torch.bfloat16), vraw.to(torch.bfloat16)
    kpos = torch.arange(1537, 2048)
    query_rows = [int(p) - 2048 for p in pr["positions"].tolist()]
    dev = "cuda"
    # C must replay the complete production Extend batch. A selected-row probe
    # cannot reproduce block-level kernel behavior or index into the output safely.
    if "q_full" not in pr or pr["q_full"].shape[0] != int(pr["extend_lens"][0]):
        raise RuntimeError("probe lacks complete 2048-row Q; do not replay selected-row Q as a full batch")
    call = pr["production_call"]
    qfull = pr["q_full"].to(dev).contiguous()
    kfull = pr["current_k"].to(dev).contiguous()
    vfull = pr["current_v"].to(dev).contiguous()
    qptr = pr["qo_indptr"].to(dev)
    kvptr = pr["window_kv_indptr"].to(dev)
    kvindices = pr["window_kv_indices"].to(dev)
    # Production window indices are physical pool slots; place captured real bytes
    # at those exact slot IDs rather than renumbering them in an undersized buffer.
    nslots = int(pr["pool_k_shape"][0])
    raw_k = torch.zeros(pr["pool_k_shape"], dtype=kraw.dtype, device=dev)
    raw_v = torch.zeros(pr["pool_v_shape"], dtype=vraw.dtype, device=dev)
    raw_k[kvindices] = kraw.to(dev)
    raw_v[kvindices] = vraw.to(dev)
    outbuf = torch.empty(
        (len(kfull), qfull.shape[1], vfull.shape[-1]), dtype=qfull.dtype, device=dev
    )
    from sglang.kernels.ops.attention.extend_attention import extend_attention_fwd

    extend_attention_fwd(
        qfull,
        kfull,
        vfull,
        outbuf,
        raw_k,
        raw_v,
        qptr,
        kvptr,
        kvindices,
        {} if call["custom_mask"] else None,
        call["causal"],
        None,
        max_len_extend=int(pr["extend_lens"][0]),
        k_scale=pr["k_scale"],
        v_scale=pr["v_scale"],
        sm_scale=pr["sm_scale"],
        logit_cap=call["logit_cap"],
        sliding_window_size=pr["sliding_window_size"],
        skip_prefix_custom_mask=pr["production_call"].get("skip_prefix_custom_mask", True),
        sinks=None,
        window_kv_offsets=pr["window_offsets"].to(dev) if call["custom_mask"] else None,
        xai_temperature_len=call["xai_temperature_len"],
        page_size=call["page_size"],
        score_mod=None,
        aux_tensors=None,
        extend_seq_lens_cpu=[int(pr["extend_lens"][0])],
    )
    torch.cuda.synchronize()
    Cfull = outbuf.float().cpu()
    result = {
        "metadata": {
            "window": 511,
            "offset": 1537,
            "prefix_indices": pr["window_kv_indices"].tolist(),
            "scale": 1.0,
            "FP8_scales": [pr["k_scale"], pr["v_scale"]],
            "causal": True,
            "production_full_extend_replay": True,
        },
        "positions": {},
    }
    live_outputs = live_full["outputs"]
    positions = pr["positions"].tolist()
    positions = sorted(positions, key=lambda pos: [2559, 2558, 2048].index(pos))
    for pos in positions:
        i = pr["positions"].tolist().index(pos)
        row = query_rows[i]
        bf_row = bf["positions"].tolist().index(pos)
        q = pr["q_full"][row : row + 1]
        if not torch.equal(bf["q"][bf_row], q[0]):
            raise RuntimeError(f"BF16 and E5M2 query differ at logical position {pos}")
        kc = pr["current_k"][: pos - 2047]
        vc = pr["current_v"][: pos - 2047]
        A = reference(
            q,
            bf_kraw,
            bf_vraw,
            kc,
            vc,
            pos,
            1537,
            pr["sm_scale"],
            pr["sliding_window_size"],
        )
        B = reference(
            q,
            kdq,
            vdq,
            kc,
            vc,
            pos,
            1537,
            pr["sm_scale"],
            pr["sliding_window_size"],
        )
        C = Cfull[row : row + 1]
        live = live_outputs[pos].float()
        result["positions"][str(pos)] = {
            "A_to_B": metrics(A, B),
            "B_to_C": metrics(B.to(torch.bfloat16).float(), C),
            "C_to_live": metrics(live, C),
            "A_to_C": metrics(A, C),
            "A": A.tolist(),
            "B": B.tolist(),
            "C": C.tolist(),
            "live": live.tolist(),
        }
    Path(args.output).write_text(json.dumps(result, separators=(",", ":")))
    print(
        json.dumps(
            {
                p: {
                    k: v
                    for k, v in r.items()
                    if k in ("A_to_B", "B_to_C", "C_to_live", "A_to_C")
                }
                for p, r in result["positions"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
