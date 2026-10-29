#!/usr/bin/env python3
"""Compare matched residual/RMSNorm A/B captures and frozen HF CPU oracle."""

import argparse
import hashlib
import json
from pathlib import Path

import torch


def load(path):
    return torch.load(path, map_location="cpu", weights_only=True)


def metrics(actual, reference):
    a = actual.float()
    r = reference.float()
    d = a - r
    return {
        "max_abs": d.abs().max().item(),
        "mean_abs": d.abs().mean().item(),
        "rmse": d.square().mean().sqrt().item(),
        "rel_l2": (d.norm() / r.norm()).item(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--ids", type=Path, required=True)
    ap.add_argument("--positions", type=Path, required=True)
    ap.add_argument("--oracle", type=Path, required=True)
    ap.add_argument("--n", type=int, required=True)
    args = ap.parse_args()
    ids = json.loads(args.ids.read_text())
    positions = json.loads(args.positions.read_text())
    oracle = load(args.oracle)
    oracle_ids = oracle.get("input_ids")
    if isinstance(oracle_ids, torch.Tensor):
        oracle_ids = oracle_ids.tolist()
    oracle_positions = oracle.get("positions")
    if isinstance(oracle_positions, torch.Tensor):
        oracle_positions = oracle_positions.tolist()
    if (
        len(ids) != args.n
        or len(positions) != args.n
        or ids != oracle_ids
        or positions != oracle_positions
    ):
        raise SystemExit("frozen input/position differs from HF oracle")
    if len(oracle["hidden_states"]) != 43:
        raise SystemExit("expected HF hidden_states embeddings + 42 decoder outputs")

    arms = {}
    for arm in ("A", "B"):
        root = args.run / arm
        rid = (root / "request-rid.txt").read_text().strip()
        fid = (root / "forward-id.txt").read_text().strip()
        verified = json.loads((root / "verified-capture.json").read_text())
        if (
            verified.get("status") != "COMPLETE"
            or verified.get("rid") != rid
            or verified.get("forward_id") != fid
        ):
            raise SystemExit(f"{arm} validator identity mismatch")
        off = int((root / "input-token-offset.txt").read_text())
        prefix = f"layers.{fid}."
        record = lambda name: load(root / f"{prefix}{name}")
        if arm == "B" and (root / "residual-ab-enabled.txt").read_text().strip() != "1":
            raise SystemExit("B does not attest the diagnostic branch was enabled")
        outputs = [
            record(f"layer_output.{i}")["output"][off : off + args.n] for i in range(42)
        ]
        outputs.insert(0, outputs[0].new_zeros((args.n, outputs[0].shape[-1])))
        prenorm = record("prenorm")["output"][off : off + args.n]
        finalnorm = record("finalnorm")["output"][off : off + args.n]
        logits = record("logits")["output"][-1].float()
        arms[arm] = {
            "rid": rid,
            "forward_id": fid,
            "offset": off,
            "outputs": outputs,
            "prenorm": prenorm,
            "finalnorm": finalnorm,
            "logits": logits,
            "capture_sha256": verified["artifact_sha256"],
        }

    result = {
        "status": "NUMERICAL_COMPARISON_COMPLETE",
        "n": args.n,
        "input_ids_sha256": hashlib.sha256(
            json.dumps(ids, separators=(",", ":")).encode()
        ).hexdigest(),
        "positions": [positions[0], positions[-1]],
        "arms": {},
        "first_ab_layer_delta": None,
    }
    deltas = []
    for arm, data in arms.items():
        hs = oracle["hidden_states"]
        layer_metrics = []
        # SGLang layer_output.i is post-decoder-layer i; HF hidden_states[i+1] has that boundary.
        for i in range(42):
            ref = hs[i + 1].float().squeeze(0)
            got = data["outputs"][i + 1]
            layer_metrics.append({"layer": i, **metrics(got, ref)})
        final = metrics(data["finalnorm"], hs[42].float().squeeze(0))
        logits_ref = oracle["logits"].float().reshape(-1)
        logits_metrics = metrics(data["logits"], logits_ref)
        top = torch.topk(logits_ref, 2)
        svc_top = torch.topk(data["logits"], 2)
        result["arms"][arm] = {
            "rid": data["rid"],
            "forward_id": data["forward_id"],
            "input_token_offset": data["offset"],
            "capture_sha256": data["capture_sha256"],
            "per_layer_vs_cpu_hf": layer_metrics,
            "finalnorm_vs_cpu_hf": final,
            "logits_vs_cpu_hf": logits_metrics,
            "top1": {
                "service": int(data["logits"].argmax()),
                "oracle": int(logits_ref.argmax()),
                "service_top2": svc_top.indices.tolist(),
                "service_margin": float((svc_top.values[0] - svc_top.values[1]).item()),
                "oracle_top2": top.indices.tolist(),
                "oracle_margin": float((top.values[0] - top.values[1]).item()),
            },
            "prenorm_vs_oracle_layer41_pre_norm": "unavailable: frozen oracle does not contain an explicit layer41 pre-norm hook",
        }
    result["ab"] = {
        "per_layer": [],
        "finalnorm": metrics(arms["B"]["finalnorm"], arms["A"]["finalnorm"]),
        "logits": metrics(arms["B"]["logits"], arms["A"]["logits"]),
        "top1_equal": int(arms["A"]["logits"].argmax())
        == int(arms["B"]["logits"].argmax()),
    }
    for i in range(42):
        m = metrics(arms["B"]["outputs"][i + 1], arms["A"]["outputs"][i + 1])
        result["ab"]["per_layer"].append({"layer": i, **m})
        if result["first_ab_layer_delta"] is None and m["max_abs"] != 0:
            result["first_ab_layer_delta"] = i
    if result["arms"]["A"]["rid"] == result["arms"]["B"]["rid"]:
        raise SystemExit("A/B unexpectedly reused request RID")
    if result["arms"]["A"]["forward_id"] == result["arms"]["B"]["forward_id"]:
        raise SystemExit("A/B unexpectedly reused Forward UUID")
    out = args.run / f"comparison-n{args.n}.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "n": args.n,
                "first_ab_layer_delta": result["first_ab_layer_delta"],
                "ab_logits": result["ab"]["logits"],
                "top1": {k: v["top1"] for k, v in result["arms"].items()},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
