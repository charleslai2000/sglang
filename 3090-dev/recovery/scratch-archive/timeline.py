"""Read-only analysis of the existing INST probe timeline (1 s snapshots)."""
import json
import sys

PATH = (
    "/var/log/sglang/local-prod-v1/phase8/l3-v1-cpu-gate-20260916/"
    "inst/arm_C/l3-probe-timeline.jsonl"
)

recs = [json.loads(l) for l in open(PATH)]


def stat(rec, key):
    s = rec["stats"].get(key)
    if s is None:
        return None
    return s


print("t0 wall", recs[0]["wall"], "t_end", recs[-1]["wall"], "n", len(recs))

# find first/last nonzero extent-ish activity via hae_alloc_writeback & l3_submit
rows = []
for i in range(1, len(recs)):
    a, b = recs[i - 1], recs[i]
    dt = b["wall"] - a["wall"]
    L0 = a["stats"]["__scheduler_loop__"]
    L1 = b["stats"]["__scheduler_loop__"]
    dn = L1["n"] - L0["n"]
    dtot = L1["total"] - L0["total"]
    row = {
        "t": b["wall"] - recs[0]["wall"],
        "dt": dt,
        "iters": dn,
        "iter_ms": (dtot / dn * 1000) if dn else None,
        "calls_per_s": dn / dt if dt else 0,
    }
    for k in (
        "hae_alloc_writeback",
        "l3_submit",
        "flush_pending",
        "storage_drain",
        "lock_wait:extent._lock",
        "lock_wait:extent._write_gate",
        "lock_wait:extent_allocator._lock",
    ):
        x0, x1 = stat(a, k), stat(b, k)
        n0 = x0["n"] if x0 else 0
        n1 = x1["n"] if x1 else 0
        row[k + ".n"] = n1 - n0
        if x1 and x0:
            if "threads_total" in x1:
                row[k + ".s"] = round(
                    x1["threads_total"].get("Thread-9 (backup_thread_func)", 0.0)
                    - x0["threads_total"].get("Thread-9 (backup_thread_func)", 0.0),
                    4,
                )
    rows.append(row)

# locate the decode window: first second with writes, last second with writes
ws = [r for r in rows if r["hae_alloc_writeback.n"] > 0]
first = ws[0]["t"]
last = ws[-1]["t"]
print("first_write_second", first, "last_write_second", last)

sel = [r for r in rows if first - 2 <= r["t"] <= last + 6]
print(
    "%8s %5s %7s %9s %9s %7s %7s %8s %8s %8s"
    % (
        "t",
        "dt",
        "iters",
        "iter_ms",
        "alloc_wb",
        "l3sub",
        "flush_n",
        "ext.lock",
        "wg",
        "alloclck",
    )
)
for r in sel:
    print(
        "%8.1f %5.2f %7d %9s %9d %7d %7d %8.4f %8.4f %8.4f"
        % (
            r["t"],
            r["dt"],
            r["iters"],
            ("%.2f" % r["iter_ms"]) if r["iter_ms"] else "-",
            r["hae_alloc_writeback.n"],
            r["l3_submit.n"],
            r["flush_pending.n"],
            r.get("lock_wait:extent._lock.s", 0.0),
            r.get("lock_wait:extent._write_gate.s", 0.0),
            r.get("lock_wait:extent_allocator._lock.s", 0.0),
        )
    )
