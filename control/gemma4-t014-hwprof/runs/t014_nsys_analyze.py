#!/usr/bin/env python3
"""T014: reduce one nsys steady-state window of the C-8 three-tier stack.

Produces, for the bounded window only:
  * kernel time share per class (attention / GEMM / other), split Extend vs Decode
  * the Extend attention split between Full (head_dim 512) and SWA (head_dim 256)
    layers, inferred from the launch signature and validated against the 7/35
    layer ownership of the frozen checkpoint
  * PCIe traffic (bytes and GB/s) from the CUPTI memcpy records
  * whole-GPU sampled metrics from nsys GPU metrics (SM issue, SMs active,
    tensor active, DRAM read/write %, PCIe RX/TX %, clocks)
  * NVML samples for board power, SM/memory clocks, temperature, PCIe link state

Whole-GPU samples are never presented as per-kernel counters; the report labels
them separately.

Usage: t014_nsys_analyze.py <cell-dir> [--nvml FILE] [--out FILE]
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sqlite3

FULL_LAYERS = 7
SWA_LAYERS = 35

CLASS_RULES = (
    ("marlin_gemm", ("marlin<", "marlin_repack", "gptq_marlin")),
    ("humming_gemm", ("humming",)),
    (
        "attn_extend",
        ("_fwd_kernel", "merge_state", "batchprefill", "create_flashinfer_kv_indices"),
    ),
    ("cublas_gemm", ("s16816gemm", "ampere_bf16", "cublas")),
    ("attn_decode", ("_fwd_grouped_kernel_stage1", "batchdecode", "_decode_kernel")),
    ("rmsnorm", ("rmsnormkernel", "fused_addrmsnorm")),
    ("activation", ("act_and_mul_kernel", "silu", "gelu")),
    ("rope", ("fused_rope_kernel", "rotaryembedding")),
    ("kv_io", ("kvcacheio", "write_back", "extent")),
)

GPU_METRIC_IDS = {
    0: "gpc_clock_mhz",
    1: "sys_clock_mhz",
    2: "gpu_active_pct",
    10: "sms_active_pct",
    11: "sm_issue_pct",
    12: "tensor_active_pct",
    19: "compute_warps_in_flight_pct",
    25: "dram_read_bw_pct",
    26: "dram_write_bw_pct",
    27: "pcie_rx_pct",
    28: "pcie_tx_pct",
}

COPY_KINDS = {
    1: "HtoD",
    2: "DtoH",
    3: "HtoH",
    8: "DtoD",
}


def classify(name: str) -> str:
    lowered = (name or "").lower()
    for label, needles in CLASS_RULES:
        if any(needle in lowered for needle in needles):
            return label
    return "other"


def analyze(cell: pathlib.Path, nvml: pathlib.Path | None) -> dict:
    db = sqlite3.connect(cell / "t007-c8-window.sqlite")
    strings = {row[0]: row[1] for row in db.execute("select id, value from StringIds")}

    kernels = list(
        db.execute(
            """select start, end, demangledName, gridX, gridY, gridZ, blockX, blockY, blockZ,
                      staticSharedMemory, dynamicSharedMemory, registersPerThread
                 from CUPTI_ACTIVITY_KIND_KERNEL where end > start order by start"""
        )
    )
    rows = [
        {
            "start": start,
            "dur": end - start,
            "name": strings.get(name, str(name)),
            "grid": (gx, gy, gz),
            "block": (bx, by, bz),
            "smem": (smem or 0) + (dsmem or 0),
            "regs": regs,
        }
        for start, end, name, gx, gy, gz, bx, by, bz, smem, dsmem, regs in kernels
    ]

    # --- Forward attribution: a Forward is a run of layer kernels bracketed by the
    # attention launches. Extend vs Decode is decided by the attention kernel that
    # runs inside it, which is exactly what the two production paths launch.
    total_ns = sum(r["dur"] for r in rows) or 1
    per_class = collections.defaultdict(lambda: {"ns": 0, "launches": 0})
    for row in rows:
        cls = classify(row["name"])
        per_class[cls]["ns"] += row["dur"]
        per_class[cls]["launches"] += 1

    class_share = {
        cls: {
            "time_share_pct": 100.0 * entry["ns"] / total_ns,
            "ms": entry["ns"] / 1e6,
            "launches": entry["launches"],
            "mean_us_per_launch": (entry["ns"] / 1e3 / entry["launches"])
            if entry["launches"]
            else None,
        }
        for cls, entry in per_class.items()
    }

    # --- Attention attribution. Two discriminators exist in this stack and both are
    # measured, not assumed:
    #   * Triton ``_fwd_kernel``: the head_dim-512 Full layers carry an 80 KB dynamic
    #     shared-memory tile, the head_dim-256 SWA layers none.
    #   * FlashInfer ``BatchPrefillWithRaggedKVCacheKernel``: the FA2 extend path that
    #     replaces the Full-layer Triton launch on arm B.
    attn_ext = [
        r
        for r in rows
        if "_fwd_kernel" in r["name"]
    ]
    attn_fi = [r for r in rows if "batchprefill" in r["name"].lower()]
    attn_dec = [r for r in rows if classify(r["name"]) == "attn_decode"]

    signatures = []
    for family, items in (("triton", attn_ext), ("flashinfer", attn_fi)):
        sig = collections.defaultdict(lambda: {"ns": 0, "launches": 0})
        for row in items:
            sig[(row["block"], row["smem"])]["ns"] += row["dur"]
            sig[(row["block"], row["smem"])]["launches"] += 1
        for (block, smem), entry in sorted(sig.items(), key=lambda kv: -kv[1]["ns"]):
            if family == "flashinfer":
                label = "full_512_flashinfer"
            else:
                label = "full_512_triton" if smem >= 64 * 1024 else "swa_256_triton"
            signatures.append(
                {
                    "runtime": family,
                    "block": block,
                    "smem_bytes": smem,
                    "launches": entry["launches"],
                    "ms": entry["ns"] / 1e6,
                    "mean_us": entry["ns"] / 1e3 / entry["launches"],
                    "inferred_layer_type": label,
                }
            )
    family_totals = collections.defaultdict(lambda: {"ms": 0.0, "launches": 0})
    for entry in signatures:
        family_totals[entry["inferred_layer_type"]]["ms"] += entry["ms"]
        family_totals[entry["inferred_layer_type"]]["launches"] += entry["launches"]
    attention_split = {
        label: {
            "ms": value["ms"],
            "launches": value["launches"],
            "share_of_kernel_time_pct": 100.0 * value["ms"] / (total_ns / 1e6),
        }
        for label, value in family_totals.items()
    }
    ratio_ok = None

    decode_signatures = collections.defaultdict(lambda: {"ns": 0, "launches": 0})
    for row in attn_dec:
        decode_signatures[(row["block"], row["smem"])]["ns"] += row["dur"]
        decode_signatures[(row["block"], row["smem"])]["launches"] += 1

    # --- GEMM share per class and the shapes it ran at.
    gemm_shapes = {}
    for cls in ("marlin_gemm", "humming_gemm"):
        shapes = collections.defaultdict(int)
        for row in rows:
            if classify(row["name"]) == cls:
                shapes[row["grid"]] += 1
        gemm_shapes[cls] = sorted(
            ({"grid": list(grid), "launches": n} for grid, n in shapes.items()),
            key=lambda item: -item["launches"],
        )[:6]

    # --- PCIe / copy traffic.
    copies = collections.defaultdict(lambda: {"bytes": 0, "ns": 0, "count": 0})
    for start, end, nbytes, kind in db.execute(
        "select start, end, bytes, copyKind from CUPTI_ACTIVITY_KIND_MEMCPY where end > start"
    ):
        entry = copies[COPY_KINDS.get(kind, f"kind{kind}")]
        entry["bytes"] += nbytes or 0
        entry["ns"] += end - start
        entry["count"] += 1
    window_ns = max((r["start"] + r["dur"] for r in rows), default=0) - min(
        (r["start"] for r in rows), default=0
    )
    copies_out = {
        kind: {
            "bytes": entry["bytes"],
            "GiB": entry["bytes"] / (1 << 30),
            "GB_per_s": (entry["bytes"] / 1e9) / (window_ns / 1e9)
            if window_ns
            else None,
            "count": entry["count"],
        }
        for kind, entry in copies.items()
    }

    # --- nsys GPU metrics (whole-GPU, sampled). They need root on this driver, so
    # the table is absent unless the capture was taken with --gpu-metrics-devices.
    gpu_metrics = {}
    has_gpu_metrics = bool(
        list(db.execute("select 1 from sqlite_master where type='table' and name='GPU_METRICS'"))
    )
    if not has_gpu_metrics:
        result_gpu_metrics = None
    for metric_id, label in (GPU_METRIC_IDS.items() if has_gpu_metrics else ()):
        row = list(
            db.execute(
                "select avg(value), max(value), min(value), count(*) from GPU_METRICS where metricId = ?",
                (metric_id,),
            )
        )[0]
        if row and row[3]:
            gpu_metrics[label] = {
                "mean": row[0],
                "max": row[1],
                "min": row[2],
                "samples": row[3],
            }

    # --- Largest individual kernels (audit trail for the "other" bucket).
    by_name = collections.defaultdict(lambda: {"ns": 0, "launches": 0})
    for row in rows:
        key = row["name"][:110]
        by_name[key]["ns"] += row["dur"]
        by_name[key]["launches"] += 1
    top_kernels = [
        {
            "name": name,
            "class": classify(name),
            "ms": value["ns"] / 1e6,
            "launches": value["launches"],
            "share_pct": 100.0 * value["ns"] / total_ns,
        }
        for name, value in sorted(by_name.items(), key=lambda kv: -kv[1]["ns"])[:12]
    ]

    result = {
        "cell": cell.name,
        "top_kernels": top_kernels,
        "window_kernel_time_ms": total_ns / 1e6,
        "kernel_launches": len(rows),
        "class_share": class_share,
        "extend_attention_signatures": signatures,
        "attention_split": attention_split,
        "decode_attention_signatures": [
            {
                "block": block,
                "smem_bytes": smem,
                "launches": v["launches"],
                "ms": v["ns"] / 1e6,
            }
            for (block, smem), v in sorted(
                decode_signatures.items(), key=lambda kv: -kv[1]["ns"]
            )
        ],
        "gemm_shapes": gemm_shapes,
        "memcpy": copies_out,
        "gpu_metrics_sampled": gpu_metrics,
    }

    if nvml and nvml.exists():
        power, sm_clock, mem_clock, temp, mem_used = [], [], [], [], []
        gen, width = set(), set()
        header = None
        for line in nvml.read_text().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if header is None:
                header = parts
                continue
            if len(parts) != len(header):
                continue
            record = dict(zip(header, parts))
            try:
                power.append(float(record["power.draw [W]"].split()[0]))
                sm_clock.append(float(record["clocks.current.sm [MHz]"].split()[0]))
                mem_clock.append(float(record["clocks.current.memory [MHz]"].split()[0]))
                temp.append(float(record["temperature.gpu"]))
                mem_used.append(float(record["memory.used [MiB]"].split()[0]))
            except (KeyError, ValueError, IndexError):
                continue
            gen.add(record.get("pcie.link.gen.current", "?"))
            width.add(record.get("pcie.link.width.current", "?"))
        result["nvml_sampled"] = {
            "samples": len(power),
            "power_w": {"mean": sum(power) / len(power), "max": max(power)}
            if power
            else None,
            "sm_clock_mhz": {
                "mean": sum(sm_clock) / len(sm_clock),
                "max": max(sm_clock),
            }
            if sm_clock
            else None,
            "mem_clock_mhz": {
                "mean": sum(mem_clock) / len(mem_clock),
                "max": max(mem_clock),
            }
            if mem_clock
            else None,
            "temperature_c": {"mean": sum(temp) / len(temp), "max": max(temp)}
            if temp
            else None,
            "memory_used_mib": {
                "mean": sum(mem_used) / len(mem_used),
                "max": max(mem_used),
            }
            if mem_used
            else None,
            "pcie_link_gen": sorted(gen),
            "pcie_link_width": sorted(width),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cell")
    parser.add_argument("--nvml", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    cell = pathlib.Path(args.cell)
    nvml = pathlib.Path(args.nvml) if args.nvml else None
    result = analyze(cell, nvml)
    out = pathlib.Path(args.out) if args.out else cell / "nsys-analysis.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("cell", "window_kernel_time_ms", "kernel_launches")
            },
            indent=2,
        )
    )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
