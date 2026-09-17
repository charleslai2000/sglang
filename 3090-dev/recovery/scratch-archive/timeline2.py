"""Per-pid, read-only analysis of the existing INST probe timeline."""
import json

PATH = (
    "/var/log/sglang/local-prod-v1/phase8/l3-v1-cpu-gate-20260916/"
    "inst/arm_C/l3-probe-timeline.jsonl"
)

bypid = {}
for line in open(PATH):
    r = json.loads(line)
    bypid.setdefault(r["pid"], []).append(r)

for pid, recs in bypid.items():
    L0 = recs[0]["stats"]["__scheduler_loop__"]
    L1 = recs[-1]["stats"]["__scheduler_loop__"]
    span = recs[-1]["wall"] - recs[0]["wall"]
    print(
        "pid=%s records=%d span=%.1fs loop_n=%d loop_total=%.1fs max=%.3fs -> mean=%.2f ms"
        % (
            pid,
            len(recs),
            span,
            L1["n"] - L0["n"],
            L1["total"] - L0["total"],
            L1["max"],
            (L1["total"] - L0["total"]) / max(1, (L1["n"] - L0["n"])) * 1000,
        )
    )

    # per-second deltas for this pid only, monotonic gaps
    print("%8s %7s %9s %9s %7s %7s %9s" % ("t", "iters", "iter_ms", "alloc_wb", "l3sub", "flush", "drn(main)"))
    rows = []
    for i in range(1, len(recs)):
        a, b = recs[i - 1], recs[i]
        La, Lb = a["stats"]["__scheduler_loop__"], b["stats"]["__scheduler_loop__"]
        dn = Lb["n"] - La["n"]
        dtot = Lb["total"] - La["total"]
        if dn < 0 or dtot < 0:
            continue
        row = dict(
            t=b["wall"] - recs[0]["wall"],
            dn=dn,
            ms=(dtot / dn * 1000) if dn else 0.0,
            dt=b["wall"] - a["wall"],
        )
        for k in ("hae_alloc_writeback", "l3_submit", "flush_pending", "storage_drain"):
            xa, xb = a["stats"].get(k), b["stats"].get(k)
            row[k] = (xb["n"] if xb else 0) - (xa["n"] if xa else 0)
        xa, xb = a["stats"].get("lock_wait:extent._lock"), b["stats"].get("lock_wait:extent._lock")
        row["lockwait"] = 0.0
        if xa and xb:
            row["lockwait"] = xb["threads_total"].get(
                "Thread-9 (backup_thread_func)", 0.0
            ) - xa["threads_total"].get("Thread-9 (backup_thread_func)", 0.0)
        rows.append(row)
    for r in rows:
        print(
            "%8.1f %7d %9.2f %9d %7d %7d %9d %9.4f"
            % (
                r["t"],
                r["dn"],
                r["ms"],
                r["hae_alloc_writeback"],
                r["l3_submit"],
                r["flush_pending"],
                r["storage_drain"],
                r["lockwait"],
            )
        )
