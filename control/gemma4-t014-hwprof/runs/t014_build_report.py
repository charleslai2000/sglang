#!/usr/bin/env python3
"""T014: build the unified hardware-utilisation tables from the collected cells.

Input  : <ncu-dir>/analysis/summary.json   (per-cell, per-kernel-class counters)
         <nsys-dir>/tiers-*/nsys-analysis.json (service window shares)
Output : markdown with one table per hardware group, plus a per-class appendix.

Forward-level values are the profiled-launch-time weighted average over the
kernel classes present in that cell; the per-class appendix keeps them auditable.
A metric the collected sections did not expose renders as ``n.c.`` and is listed
in the limitations section — never as a zero.
"""

from __future__ import annotations

import argparse
import json
import pathlib

GROUP_ROWS = (
    (
        "1. SM / occupancy",
        (
            ("SM throughput [% peak]", "sm_throughput_pct"),
            ("SM warps active [% peak]", "sm_warps_active_pct"),
            ("Issue active [% peak]", "issue_active_pct"),
            ("Achieved occupancy [%]", "occupancy_pct"),
            ("Waves per SM", "waves_per_sm"),
        ),
    ),
    (
        "2. Compute pipes [% of peak active]",
        (
            ("Tensor (all)", "pipe_tensor_pct"),
            ("Tensor HMMA (BF16)", "pipe_tensor_hmma_pct"),
            ("Tensor IMMA (INT)", "pipe_tensor_imma_pct"),
            ("FP32/FMA", "pipe_fma_pct"),
            ("FP32 heavy", "pipe_fmaheavy_pct"),
            ("ALU/INT", "pipe_alu_pct"),
            ("FP64", "pipe_fp64_pct"),
            ("L1TEX LSU wavefronts [% peak]", "l1tex_lsu_wavefronts_pct"),
            ("MIO inst issued", "mio_inst_issued_pct"),
            ("MIO queue read cycles", "mio_pq_read_pct"),
        ),
    ),
    (
        "3. DRAM",
        (
            ("DRAM bandwidth [GB/s]", "dram_GB_per_s"),
            ("DRAM active cycles [% of peak]", "dram_active_cycles_pct"),
        ),
    ),
    (
        "4. L1 / L2",
        (
            ("L1TEX hit rate [%]", "l1_hit_rate_pct"),
            ("L1TEX throughput [% peak]", "l1tex_throughput_pct"),
            ("L2 hit rate [%]", "l2_hit_rate_pct"),
            ("L2 throughput [% peak]", "lts_throughput_pct"),
        ),
    ),
    (
        "5. Warps / registers / shared memory",
        (
            ("Registers per thread", "registers_per_thread"),
            ("Shared memory per block [KB]", "smem_per_block_bytes"),
            ("Block size", "block_size"),
        ),
    ),
)

PERCENT_METRICS = {"duration_us_sum"}


def fmt(value) -> str:
    if value is None:
        return "n.c."
    if isinstance(value, str):
        return value
    if value >= 1e9:
        return f"{value / 1e9:.2f}G"
    if value >= 1e6:
        return f"{value / 1e6:.2f}M"
    if value >= 1000:
        return f"{value:,.0f}"
    if value >= 100:
        return f"{value:.1f}"
    return f"{value:.2f}"


STRING_METRICS = {"block_size", "grid_size"}


def dominant_string(cell: dict, metric: str):
    """Launch-geometry metrics are categorical: report the value of the class that
    owns most of the profiled time instead of averaging strings."""
    best = None
    for klass in cell["classes"].values():
        duration = klass.get("duration_weight_raw") or 0.0
        value = klass.get(metric)
        if value and (best is None or duration > best[0]):
            best = (duration, value)
    return best[1] if best else None


def weighted(cell: dict, metric: str):
    total = 0.0
    acc = 0.0
    for klass in cell["classes"].values():
        weight = klass.get("duration_weight_raw") or 0.0
        value = klass.get(metric)
        if value is None or weight <= 0 or not isinstance(value, (int, float)):
            continue
        acc += value * weight
        total += weight
    return (acc / total) if total else None


def column_label(name: str, cell: dict) -> str:
    meta = cell["meta"]
    stage = meta.get("stage")
    if stage == "prefill":
        return f"{name} P{meta.get('input_len')}"
    if stage == "prefix":
        return (
            f"{name} E{int(meta.get('prefix_len') or 0) // 1024}K+{meta.get('new_len')}"
        )
    return f"{name} D{meta.get('batch')}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ncu-dir", default="/data/sglang-hicache/gemma4/runs/20261128T-t014-ncu"
    )
    parser.add_argument(
        "--nsys-dir", default="/data/sglang-hicache/gemma4/runs/20261128T-t014-nsys"
    )
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    ncu_dir = pathlib.Path(args.ncu_dir)
    summary = json.loads((ncu_dir / "analysis" / "summary.json").read_text())
    order = [
        "A-prefill1024",
        "A-prefill4096",
        "A-prefix16k",
        "A-decode8",
        "A-decode16",
        "A-decode32",
        "B-prefill1024",
        "B-prefill4096",
        "B-prefix16k",
        "B-decode8",
        "B-decode16",
        "B-decode32",
    ]
    # The first B-prefix cell used a 120-launch budget that stopped before the
    # FlashInfer ragged-prefill kernels; the 200-launch re-run is authoritative.
    alias = {"B-prefix16k": "B-prefix16k-fa2kernels"}
    cells = []
    for name in order:
        source = alias.get(name, name)
        if source in summary and not source.endswith("-instr"):
            cells.append((name, summary[source]))
    labels = [column_label(name, cell) for name, cell in cells]

    lines = []
    lines.append("<!-- generated by t014_build_report.py -->")
    for group, rows in GROUP_ROWS:
        lines.append(f"### {group}\n")
        lines.append("| metric | " + " | ".join(labels) + " |")
        lines.append("| --- | " + " | ".join("---:" for _ in labels) + " |")
        for label, metric in rows:
            getter = dominant_string if metric in STRING_METRICS else weighted
            values = [fmt(getter(cell, metric)) for _, cell in cells]
            lines.append(f"| {label} | " + " | ".join(values) + " |")
        lines.append("")

    # Top stall reason per cell (per class, then the widest contributor).
    lines.append("### Stall reasons per class (top 2, duration-weighted)\n")
    lines.append("| cell | class | top stalls |")
    lines.append("| --- | --- | --- |")
    for name, cell in cells:
        for klass, entry in sorted(
            cell["classes"].items(), key=lambda kv: -(kv[1].get("duration_weight_raw") or 0)
        )[:4]:
            stalls = ", ".join(
                f"{s} {v:.2f}" for s, v in entry.get("stall_top", [])[:2]
            )
            lines.append(
                f"| {column_label(name, cell)} | {klass} | {stalls or 'n.c.'} |"
            )
    lines.append("")

    # Per-class appendix for the two most informative shapes of each arm.
    lines.append("### Per-class appendix (SM/tensor/DRAM/L2)\n")
    lines.append("| cell | class | launches | SM% | tensor% | DRAM GB/s | L2 hit% |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for name, cell in cells:
        for klass, entry in sorted(
            cell["classes"].items(), key=lambda kv: -(kv[1].get("duration_weight_raw") or 0)
        ):
            lines.append(
                "| {} | {} | {} | {} | {} | {} | {} |".format(
                    column_label(name, cell),
                    klass,
                    entry["instances"],
                    fmt(entry.get("sm_throughput_pct")),
                    fmt(entry.get("pipe_tensor_pct")),
                    fmt(entry.get("dram_GB_per_s")),
                    fmt(entry.get("l2_hit_rate_pct")),
                )
            )
    lines.append("")

    # Supplement cells: instruction-pipe split and DRAM byte-percentage counters
    # that the main section set does not expose.
    supp_rows = (
        ("LSU (inst pipe) [% peak]", "inst_executed_pipe_lsu_pct"),
        ("SFU/XU (inst pipe) [% peak]", "inst_executed_pipe_xu_pct"),
        ("TEX (inst pipe) [% peak]", "inst_executed_pipe_tex_pct"),
        ("ADU (inst pipe) [% peak]", "inst_executed_pipe_adu_pct"),
        ("DRAM read [% of peak]", "dram_read_peak_pct"),
        ("DRAM write [% of peak]", "dram_write_peak_pct"),
        ("L1TEX LSU wavefronts [% peak]", "l1tex_lsu_wavefronts_pct"),
    )
    supp_cells = [(name, summary[name]) for name in sorted(summary) if name.endswith("-instr")]
    if supp_cells:
        lines.append("### Supplement: instruction pipes and DRAM percentages (per class)\n")
        lines.append("| cell | class | " + " | ".join(label for label, _ in supp_rows) + " |")
        lines.append("| --- | --- | " + " | ".join("---:" for _ in supp_rows) + " |")
        for name, cell in supp_cells:
            for klass, entry in sorted(
                cell["classes"].items(), key=lambda kv: -(kv[1].get("duration_weight_raw") or 0)
            ):
                values = [fmt(entry.get(metric)) for _, metric in supp_rows]
                lines.append(
                    f"| {column_label(name, cell)} | {klass} | " + " | ".join(values) + " |"
                )
        lines.append("")

    # Service window summary.
    nsys_dir = pathlib.Path(args.nsys_dir)
    analyses = sorted(nsys_dir.glob("tiers-*/nsys-analysis.json"))
    if analyses:
        lines.append("### C-8 three-tier service window (nsys)\n")
        lines.append("| item | " + " | ".join(a.parent.name for a in analyses) + " |")
        lines.append("| --- | " + " | ".join("---:" for _ in analyses) + " |")
        data = [json.loads(a.read_text()) for a in analyses]
        for metric in ("window_kernel_time_ms", "kernel_launches"):
            lines.append(
                f"| {metric} | " + " | ".join(fmt(d.get(metric)) for d in data) + " |"
            )
        for klass in (
            "attn_extend",
            "attn_decode",
            "marlin_gemm",
            "humming_gemm",
            "other",
        ):
            row = []
            for d in data:
                share = d["class_share"].get(klass)
                row.append(fmt(share["time_share_pct"]) if share else "n.c.")
            lines.append(f"| time share {klass} [%] | " + " | ".join(row) + " |")
        for metric in (
            "sms_active_pct",
            "sm_issue_pct",
            "tensor_active_pct",
            "dram_read_bw_pct",
            "dram_write_bw_pct",
            "pcie_rx_pct",
            "pcie_tx_pct",
            "gpc_clock_mhz",
        ):
            row = []
            for d in data:
                entry = d["gpu_metrics_sampled"].get(metric)
                row.append(fmt(entry["mean"]) if entry else "n.c.")
            lines.append(f"| {metric} (mean, whole GPU) | " + " | ".join(row) + " |")
        for metric in (
            "power_w",
            "sm_clock_mhz",
            "mem_clock_mhz",
            "temperature_c",
            "memory_used_mib",
        ):
            row = []
            for d in data:
                entry = (d.get("nvml_sampled") or {}).get(metric)
                row.append(fmt(entry["max"]) if entry else "n.c.")
            lines.append(f"| {metric} (max, NVML) | " + " | ".join(row) + " |")
        for kind in ("HtoD", "DtoH", "DtoD"):
            row = []
            for d in data:
                entry = d["memcpy"].get(kind)
                row.append(fmt(entry["GB_per_s"]) if entry else "n.c.")
            lines.append(f"| memcpy {kind} [GB/s] | " + " | ".join(row) + " |")
        lines.append("")

    text = "\n".join(lines) + "\n"
    out = pathlib.Path(args.out) if args.out else ncu_dir / "analysis" / "tables.md"
    out.write_text(text)
    print(text[:4000])
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
