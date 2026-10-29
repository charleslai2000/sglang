#!/usr/bin/env python3
"""Select one complete EXTEND Forward by exact request RID and caller-supplied tokens."""

import argparse
import json
import sys
from pathlib import Path

import torch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "base", type=Path, help="Capture base path, e.g. /run/A/forward"
    )
    parser.add_argument("rid")
    parser.add_argument("--ids", required=True, help="JSON integer array")
    parser.add_argument("--positions", required=True, help="JSON integer array")
    args = parser.parse_args()
    ids = json.loads(args.ids)
    positions = json.loads(args.positions)
    if not ids or len(ids) != len(positions):
        raise SystemExit("input IDs and positions must be non-empty and equal length")
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in ids + positions):
        raise SystemExit("input IDs and positions must contain integers")

    base = args.base
    found = []
    for path in base.parent.glob(f"{base.name}.*.layer_output.0"):
        try:
            record = torch.load(path, map_location="cpu", weights_only=True)
        except Exception:
            continue
        if record.get("rid") != [args.rid] or record.get("forward_mode") != "EXTEND":
            continue
        if not isinstance(record.get("input_ids"), torch.Tensor) or not isinstance(record.get("positions"), torch.Tensor):
            continue
        actual_ids = record["input_ids"].tolist()
        actual_positions = record["positions"].tolist()
        if actual_ids == ids and actual_positions == positions:
            offset = 0
        elif (
            actual_ids[-len(ids) :] == ids
            and actual_positions[-len(positions) :] == positions
        ):
            offset = len(actual_ids) - len(ids)
        else:
            continue
        fid = record.get("forward_id")
        if not isinstance(fid, str) or path.name != f"{base.name}.{fid}.layer_output.0":
            continue
        manifest_path = base.parent / f"{base.name}.{fid}.manifest"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text())
        if (
            manifest.get("status") != "COMPLETE"
            or manifest.get("forward_id") != fid
            or manifest.get("rid") != [args.rid]
            or manifest.get("input_ids") != actual_ids
            or manifest.get("positions") != actual_positions
            or manifest.get("forward_mode") != "EXTEND"
            or manifest.get("layer_indices") != list(range(42))
        ):
            continue
        required = [
            *(f"{base.name}.{fid}.layer_output.{i}" for i in range(42)),
            f"{base.name}.{fid}.prenorm",
            f"{base.name}.{fid}.finalnorm",
            f"{base.name}.{fid}.logits",
            f"{base.name}.{fid}.manifest",
        ]
        if all((base.parent / name).is_file() for name in required):
            try:
                if any(
                    torch.load(base.parent / f"{base.name}.{fid}.layer_output.{i}", map_location="cpu", weights_only=True).get("layer") != i
                    for i in range(42)
                ):
                    continue
                logits = torch.load(base.parent / f"{base.name}.{fid}.logits", map_location="cpu", weights_only=True)
                if logits.get("forward_id") != fid or logits.get("rid") != [args.rid]:
                    continue
            except Exception:
                continue
            found.append((fid, offset))
    if len(found) != 1:
        raise SystemExit(
            f"expected exactly one complete target Forward, got {len(found)}"
        )
    print(found[0][0], found[0][1])


if __name__ == "__main__":
    main()
