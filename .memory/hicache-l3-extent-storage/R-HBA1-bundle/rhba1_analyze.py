#!/usr/bin/env python3
"""R-HBA1 analyzer: evaluate the frozen hard + effectiveness gates.

Reads the per-condition JSON written by rhba1_harness.py and prints one
condition report plus the cross-condition effectiveness verdict. Never
fabricates a missing value: a gate whose mark is absent is reported MISSING.
"""
import argparse
import glob
import json
import statistics


def pct(vals, q):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


def ms(ns):
    return None if ns is None else round(ns / 1e6, 3)


def eval_rep(rep, condition):
    m = rep.get("marks") or {}
    out = {"rep": rep.get("rep")}
    out["b_enqueue_ns"] = m.get("enqueue_ns")
    out["prefetch_issue_ns"] = m.get("prefetch_issue_ns")
    out["ready_host_ns"] = m.get("ready_host_ns")
    out["admission_ns"] = m.get("admission_ns")
    out["a_last_ns"] = rep.get("a_last_ns")
    out["b_first_ns"] = rep.get("b_first_ns")
    out["prefetch_slack_ms"] = ms(rep.get("prefetch_slack_ns"))
    out["stage_ms"] = ms(rep.get("stage_ns"))
    out["lead_ms"] = ms(rep.get("lead_ns"))
    out["tftt_ms"] = ms(rep.get("tftt_ns"))
    out["ready_before_admission_ms"] = ms(rep.get("ready_before_admission_ns"))
    out["D_req"] = rep.get("D_req")
    out["cached_total"] = rep.get("cached_total")
    out["avoidable_recompute"] = rep.get("avoidable_recompute")
    out["details"] = rep.get("b_details")
    out["completed_kv_tokens"] = m.get("completed_kv_tokens")
    out["restore_success_tokens"] = m.get("restore_success_tokens")
    out["finalize_result"] = m.get("finalize_result")
    out["restore_states"] = m.get("restore_states")
    out["required_aux_pools"] = m.get("required_aux_pools")
    out["completed_aux_units"] = m.get("completed_aux_units")
    out["hybrid_finalize"] = m.get("hybrid_finalize")
    out["b_finish"] = rep.get("b_finish")
    out["error"] = rep.get("error")

    # --- gate booleans (None = MISSING)
    is_hot = condition == "l3_hot"
    be, pf, rh, al = (
        out["b_enqueue_ns"], out["prefetch_issue_ns"],
        out["ready_host_ns"], out["a_last_ns"],
    )
    # `ordered_rh`: enqueue -> RH issue -> ready, all before A ends. RH-specific.
    if is_hot:
        out["ordered_rh"] = None
        out["sufficient_lead"] = None
    elif None in (be, pf, rh, al):
        out["ordered_rh"] = None
        out["sufficient_lead"] = None
    else:
        out["ordered_rh"] = bool(be < pf < rh <= al)
        out["sufficient_lead"] = out["ordered_rh"]
    # `hidden`: RH-independent; the stage finished while A was still computing.
    out["hidden"] = None if (rh is None or al is None) else bool(rh <= al)
    adm = out["admission_ns"]
    out["ready_before_admission"] = (
        None if (rh is None or adm is None) else bool(rh <= adm)
    )
    d_req = out["D_req"]
    if is_hot:
        out["restored_equals_Dreq"] = None
    else:
        out["restored_equals_Dreq"] = (
            None
            if (d_req is None or out["completed_kv_tokens"] is None)
            else bool(out["completed_kv_tokens"] == d_req)
        )
    hf = out["hybrid_finalize"] or {}
    if out["completed_aux_units"] is not None:
        out["mamba_complete"] = bool(
            "mamba" in (out["required_aux_pools"] or "")
            and "'mamba': 1" in out["completed_aux_units"]
        )
    elif hf:
        out["mamba_complete"] = bool(
            hf.get("mamba_expected") == hf.get("mamba_fetched")
            and hf.get("kv_expected") == hf.get("kv_fetched")
            and hf.get("result") == "accepted"
        )
    else:
        out["mamba_complete"] = None
    out["no_recompute"] = (
        None if out["avoidable_recompute"] is None
        else bool(out["avoidable_recompute"] == 0)
    )
    out["no_discard"] = (
        None
        if out["finalize_result"] is None
        else bool(out["finalize_result"] == "accepted"
                  and "DENIED_SHORT" not in (out["restore_states"] or []))
    )
    out["http_complete"] = bool(out["b_first_ns"] is not None)
    return out


def summarize(rows):
    n = len(rows)
    tftt = [r["tftt_ms"] for r in rows if r["tftt_ms"] is not None]
    slack = [r["prefetch_slack_ms"] for r in rows
             if r["prefetch_slack_ms"] is not None]
    stage = [r["stage_ms"] for r in rows if r["stage_ms"] is not None]
    return {
        "n": n,
        "ordered_rh_n": sum(1 for r in rows if r["ordered_rh"] is True),
        "sufficient_lead_n": sum(1 for r in rows if r["sufficient_lead"] is True),
        "hidden_n": sum(1 for r in rows if r["hidden"] is True),
        "restored_eq_Dreq_n": sum(1 for r in rows
                                  if r["restored_equals_Dreq"] is True),
        "no_recompute_n": sum(1 for r in rows if r["no_recompute"] is True),
        "mamba_complete_n": sum(1 for r in rows if r["mamba_complete"] is True),
        "no_discard_n": sum(1 for r in rows if r["no_discard"] is True),
        "tftt_ms_p50": pct(tftt, 0.5),
        "tftt_ms_p95": pct(tftt, 0.95) if n >= 20 else None,
        "tftt_ms_max": max(tftt) if tftt else None,
        "prefetch_slack_ms_p50": pct(slack, 0.5),
        "prefetch_slack_ms_max": max(slack) if slack else None,
        "stage_ms_p50": pct(stage, 0.5),
        "p95_eligible": n >= 20,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="dir with result-<cond>.json")
    args = ap.parse_args()

    conditions = ["l3_hot", "l3_off", "l3_on_short", "l3_on_long"]
    report = {"conditions": {}, "rows": {}}
    for cond in conditions:
        path = f"{args.dir}/result-{cond}.json"
        try:
            with open(path) as fh:
                data = json.load(fh)
        except FileNotFoundError:
            report["conditions"][cond] = {"present": False}
            continue
        rows = [eval_rep(r, cond) for r in data["replicates"]]
        report["conditions"][cond] = {
            "present": True,
            "counts": data.get("counts"),
            "summary": summarize(rows),
        }
        report["rows"][cond] = rows

    e = report
    hot = e["conditions"].get("l3_hot", {}).get("summary", {})
    off = e["conditions"].get("l3_off", {}).get("summary", {})
    long_ = e["conditions"].get("l3_on_long", {}).get("summary", {})
    short = e["conditions"].get("l3_on_short", {}).get("summary", {})

    def base(s):
        return s.get("tftt_ms_p95") if s.get("p95_eligible") else s.get("tftt_ms_p50")

    verdict = {}
    hot_b, off_b, long_b, short_b = base(hot), base(off), base(long_), base(short)
    verdict["hot_ref_ms"] = hot_b
    verdict["rh_off_ms"] = off_b
    verdict["rh_on_sufficient_ms"] = long_b
    verdict["rh_on_insufficient_ms"] = short_b
    if hot_b is not None and long_b is not None:
        band = max(100.0, 0.25 * hot_b)
        verdict["hot_band_ms"] = round(band, 3)
        verdict["within_hot_band"] = bool(long_b <= hot_b + band)
    else:
        verdict["within_hot_band"] = None
    if off_b is not None and long_b is not None:
        verdict["better_than_off"] = bool(long_b < off_b)
    else:
        verdict["better_than_off"] = None

    gates = ["ordered_rh_n", "hidden_n", "restored_eq_Dreq_n",
             "no_recompute_n", "mamba_complete_n", "no_discard_n"]
    n_long = long_.get("n")
    verdict["long_gate_counts"] = {g: long_.get(g) for g in gates}
    verdict["hard_gates_pass"] = bool(
        n_long and all(long_.get(g) == n_long for g in gates)
    )
    verdict["overall"] = (
        "PASS" if (verdict["hard_gates_pass"] and verdict["within_hot_band"]
                   and verdict["better_than_off"])
        else ("FAIL" if verdict["hard_gates_pass"] is False
              else "NOT_VERIFIED")
    )
    report["verdict"] = verdict

    outpath = f"{args.dir}/rhba1-report.json"
    with open(outpath, "w") as fh:
        json.dump(report, fh, indent=1)
    print(json.dumps(verdict, indent=1))
    print("report:", outpath)


if __name__ == "__main__":
    main()
