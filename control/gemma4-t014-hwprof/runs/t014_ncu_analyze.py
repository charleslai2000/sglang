#!/usr/bin/env python3
"""T014: reduce the NCU ApplicationReplay reports into per-kernel-class hardware facts.

Each cell is one production Forward shape of one arm. For every cell the report is
imported to CSV (``ncu --import --csv --page raw``), kernels are grouped into
classes, and every class gets a duration-weighted average of the requested
hardware counters. Nothing is invented: a metric that the collected sections did
not expose is reported as ``None`` and printed as ``NOT COLLECTED``.

Usage:  t014_ncu_analyze.py [--cells-dir DIR] [--out DIR] [cell ...]
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import pathlib
import subprocess

NCU = "/usr/local/cuda-12.9/bin/ncu"

# ---------------------------------------------------------------- kernel classes
# Ordered: first match wins. Names are the demangled CUPTI kernel names that the
# frozen stack actually launches for this model.
CLASS_RULES = (
    ("marlin_gemm", ("Marlin<", "marlin_repack", "gptq_marlin")),
    ("humming_gemm", ("humming",)),
    (
        "attn_extend",
        ("_fwd_kernel", "BatchPrefill", "merge_state", "create_flashinfer_kv_indices"),
    ),
    ("cublas_gemm", ("s16816gemm", "ampere_bf16", "cublas")),
    ("attn_decode", ("_fwd_grouped_kernel_stage1", "_decode_kernel", "BatchDecode")),
    ("rmsnorm", ("RMSNormKernel", "FusedAddRMSNorm")),
    ("activation", ("act_and_mul_kernel", "silu", "gelu")),
    ("rope", ("fused_rope_kernel", "RotaryEmbedding")),
    ("kv_io", ("kvcacheio", "write_back", "extent", "cudaMemcpyAsync")),
)

# --------------------------------------------------------------- metric mapping
# (label, column, weight) — weight "time" means duration-weighted.
METRICS = (
    ("duration_weight_raw", "gpu__time_duration.sum", None),
    ("sm_throughput_pct", "sm__throughput.avg.pct_of_peak_sustained_elapsed", "time"),
    (
        "sm_warps_active_pct",
        "sm__warps_active.avg.pct_of_peak_sustained_active",
        "time",
    ),
    ("issue_active_pct", "smsp__issue_active.avg.pct_of_peak_sustained_active", "time"),
    ("occupancy_pct", "sm__warps_active.avg.pct_of_peak_sustained_active", "time"),
    ("waves_per_sm", "launch__waves_per_multiprocessor", "time"),
    (
        "pipe_alu_pct",
        "sm__pipe_alu_cycles_active.avg.pct_of_peak_sustained_active",
        "time",
    ),
    (
        "pipe_fma_pct",
        "sm__pipe_fma_cycles_active.avg.pct_of_peak_sustained_active",
        "time",
    ),
    (
        "pipe_fmaheavy_pct",
        "sm__pipe_fmaheavy_cycles_active.avg.pct_of_peak_sustained_active",
        "time",
    ),
    (
        "pipe_tensor_pct",
        "sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active",
        "time",
    ),
    (
        "pipe_tensor_hmma_pct",
        "sm__pipe_tensor_op_hmma_cycles_active.avg.pct_of_peak_sustained_active",
        "time",
    ),
    (
        "pipe_tensor_imma_pct",
        "sm__pipe_tensor_op_imma_cycles_active.avg.pct_of_peak_sustained_active",
        "time",
    ),
    (
        "pipe_fp64_pct",
        "sm__pipe_fp64_cycles_active.avg.pct_of_peak_sustained_active",
        "time",
    ),
    (
        "mio_inst_issued_pct",
        "sm__mio_inst_issued.avg.pct_of_peak_sustained_elapsed",
        "time",
    ),
    (
        "mio_pq_read_pct",
        "sm__mio_pq_read_cycles_active.avg.pct_of_peak_sustained_elapsed",
        "time",
    ),
    (
        "mio_writeback_pct",
        "sm__mio2rf_writeback_active.avg.pct_of_peak_sustained_elapsed",
        "time",
    ),
    (
        "l1tex_throughput_pct",
        "l1tex__throughput.avg.pct_of_peak_sustained_active",
        "time",
    ),
    ("l1_hit_rate_pct", "l1tex__t_sector_hit_rate.pct", "time"),
    ("lts_throughput_pct", "lts__throughput.avg.pct_of_peak_sustained_elapsed", "time"),
    ("l2_hit_rate_pct", "lts__t_sector_hit_rate.pct", "time"),
    # DRAM counters are only exposed by MemoryWorkloadAnalysis_Tables (supplement
    # cells); the total-bandwidth alias is already printed in GB/s by NCU here.
    ("dram_GB_per_s", "dram__bytes.sum.per_second", "time"),
    ("dram_peak_pct", "dram__throughput.avg.pct_of_peak_sustained_elapsed", "time"),
    ("dram_active_cycles_pct", "dram__cycles_active.avg.pct_of_peak_sustained_elapsed", "time"),
    # Absolute byte columns are excluded: NCU applies a per-report display scale to
    # them, so they are not comparable between cells. Peak percentages and GB/s are.
    ("dram_read_peak_pct", "dram__bytes_read.sum.pct_of_peak_sustained_elapsed", "time"),
    ("dram_write_peak_pct", "dram__bytes_write.sum.pct_of_peak_sustained_elapsed", "time"),
    ("l1tex_lsu_wavefronts_pct", "l1tex__data_pipe_lsu_wavefronts.avg.pct_of_peak_sustained_elapsed", "time"),
    ("registers_per_thread", "launch__registers_per_thread", "time"),
    ("smem_per_block_bytes", "launch__shared_mem_per_block", "time"),
    ("block_size", "Block Size", "mode"),
    ("grid_size", "Grid Size", "mode"),
    (
        "inst_executed_pipe_lsu_pct",
        "sm__inst_executed_pipe_lsu.avg.pct_of_peak_sustained_elapsed",
        "time",
    ),
    (
        "inst_executed_pipe_xu_pct",
        "sm__inst_executed_pipe_xu.avg.pct_of_peak_sustained_elapsed",
        "time",
    ),
    (
        "inst_executed_pipe_tex_pct",
        "sm__inst_executed_pipe_tex.avg.pct_of_peak_sustained_elapsed",
        "time",
    ),
    (
        "inst_executed_pipe_adu_pct",
        "sm__inst_executed_pipe_adu.avg.pct_of_peak_sustained_elapsed",
        "time",
    ),
)

STALL_PREFIX = "smsp__average_warps_issue_stalled_"
STALL_SUFFIX = "_per_issue_active.ratio"


def classify(name: str) -> str:
    lowered = name or ""
    for label, needles in CLASS_RULES:
        if any(needle in lowered for needle in needles):
            return label
    return "other"


def import_report(report: pathlib.Path, cache: pathlib.Path) -> list[dict]:
    if not cache.exists() or cache.stat().st_size == 0:
        with cache.open("w") as handle:
            subprocess.run(
                ["sudo", "-n", NCU, "--import", str(report), "--csv", "--page", "raw"],
                check=True,
                stdout=handle,
                stderr=subprocess.DEVNULL,
            )
    with cache.open() as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader if row.get("Kernel Name")]


def as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def aggregate(rows: list[dict]) -> dict:
    by_class = collections.defaultdict(list)
    for row in rows:
        by_class[classify(row.get("Kernel Name", ""))].append(row)

    stalls = (
        [
            key
            for key in rows[0]
            if key and key.startswith(STALL_PREFIX) and key.endswith(STALL_SUFFIX)
        ]
        if rows
        else []
    )

    out = {}
    for klass, items in by_class.items():
        entry = {"instances": len(items)}
        for label, column, weight in METRICS:
            if column not in items[0]:
                entry[label] = None
                continue
            if weight == "mode":
                counts = collections.Counter(
                    item.get(column) for item in items if item.get(column)
                )
                entry[label] = counts.most_common(1)[0][0] if counts else None
                continue
            if weight is None:
                total = 0.0
                for item in items:
                    value = as_float(item.get(column))
                    if value is not None:
                        total += value
                entry[label] = total
                continue
            num = den = 0.0
            for item in items:
                value = as_float(item.get(column))
                dur = as_float(item.get("gpu__time_duration.sum")) or 0.0
                if value is None:
                    continue
                num += value * dur
                den += dur
            entry[label] = (num / den) if den else None
        top = []
        for key in stalls:
            num = den = 0.0
            for item in items:
                value = as_float(item.get(key))
                dur = as_float(item.get("gpu__time_duration.sum")) or 0.0
                if value is None:
                    continue
                num += value * dur
                den += dur
            if den:
                name = key[len(STALL_PREFIX) : -len(STALL_SUFFIX)]
                top.append((name, num / den))
        top.sort(key=lambda pair: pair[1], reverse=True)
        entry["stall_top"] = top[:4]
        entry["kernel_names"] = sorted({item["Kernel Name"][:120] for item in items})[
            :4
        ]
        out[klass] = entry
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cells-dir", default="/data/sglang-hicache/gemma4/runs/20261128T-t014-ncu"
    )
    parser.add_argument("--out", default=None)
    parser.add_argument("cells", nargs="*")
    args = parser.parse_args()

    cells_dir = pathlib.Path(args.cells_dir)
    out_dir = pathlib.Path(args.out) if args.out else cells_dir / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    names = args.cells or [
        p.name[: -len(".ncu-rep")] for p in sorted(cells_dir.glob("*.ncu-rep"))
    ]
    summary_path = out_dir / "summary.json"
    summary = {}
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text())
        except json.JSONDecodeError:
            summary = {}
    for name in names:
        report = cells_dir / f"{name}.ncu-rep"
        if not report.exists():
            print(f"skip {name}: no report")
            continue
        rows = import_report(report, out_dir / f"{name}.raw.csv")
        meta = {}
        meta_path = cells_dir / f"{name}.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        summary[name] = {
            "meta": {
                key: meta.get(key)
                for key in (
                    "stage",
                    "arm",
                    "attn",
                    "batch",
                    "input_len",
                    "prefix_len",
                    "new_len",
                    "decode_context",
                    "extend_tokens",
                    "prefix_tokens",
                    "tokens",
                    "max_total_num_tokens",
                    "kv_pool_geometry",
                    "fa2_enabled_in_backend",
                    "fa2_stats_after",
                )
            },
            "kernel_rows": len(rows),
            "classes": aggregate(rows),
        }
        print(f"analyzed {name}: {len(rows)} kernel instances")
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {summary_path}")


if __name__ == "__main__":
    main()
