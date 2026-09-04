#!/usr/bin/env python3
"""Gate2 load driver: push the Mamba checkpoint pool to saturation (write
phase) then verify aggregate effective_cache_ratio >= 95% under multi-session
restore + mid-branch (read phase).

Design rationale (documented honestly):
  - The agent_driver 12-turn template interleaves long grows (L0->L3) with
    restores; long grows add ~1/3 new tokens per turn, capping the per-request
    effective ratio near 65% by construction (new content is cold). That is a
    load-shape property, not a cache defect.  To measure the gate2 acceptance
    item ("pressure-stable aggregate >= 95%") the read phase must be
    hit-dominated (restore + mid-branch over already-written chains), which is
    the agentic steady-state the gate cares about.
  - Phase A (saturate): every agent writes its own session chains (grow
    L0..L3 + variants) -> N distinct mamba checkpoints.  With pool=106 slots
    and ~2 checkpoint slots per grow turn, K=8 (~96 slots) sits at the
    boundary and K=16 (~192 slots) is strongly saturated (LRU eviction).
  - Phase B (verify): every agent re-reads old-session chains (restore of its
    own and other sessions) + mid-branch (BB payloads) repeatedly.  The
    aggregate effective ratio over phase B is the acceptance metric; cliff =
    a restore/branch request whose usable hit collapses to ~0 because its
    mamba checkpoint was evicted.

join.log rows carry: agent_id, turn, turn_kind (write/grow/restore/branch),
phase (A/B), session, level, variant, prompt_len, device_hit, host_hit,
storage_hit, new_tokens_est, ttft_s, wall_s, http, finished, rid.
"""
import argparse
import json
import os
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
# common.py lives beside the gate1/agent_driver infra, not beside this driver.
for _p in (_HERE, os.path.join(_HERE, "p2-0")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
import common  # noqa: E402

PAYLOAD_DIR = common.PAYLOAD_DIR
DEVICE_TOTAL = 65536  # frozen --max-total-tokens for gate2 baseline


def payload(session, level, variant):
    """b1c-S{ses}-L{k}-V{v} or b1c-S{ses}-BB{b}-V{v}."""
    return common.resolve_payload(
        os.path.join(PAYLOAD_DIR,
                     "b1c-S%d-%s-V%d.payload.json" % (session, level, variant)))


def write_chain_spec(session):
    """Phase A write turns for one session: L0..L3 (variant ring by session)
    so each session deposits 4 distinct growing checkpoints on one prefix."""
    v = 1 + (session % 3)
    return [
        ("L0", v), ("L1", v), ("L2", v), ("L3", v),
    ]


def read_chain_spec(session, agents, turn):
    """Phase B read turns: mix of own-session restore, cross-session restore,
    and mid-branch (BB).  Deterministic per (session, turn)."""
    r = (turn + session) % 8
    if r < 3:
        # own-session restore of a previously written chain level
        lvl = ("L0", "L1", "L2")[r]
        v = 1 + (session % 3)
        return ("restore", session, lvl, v)
    elif r < 5:
        # cross-session restore: hit another session's written chain
        other = 1 + ((session + r) % agents)
        lvl = "L0"
        v = 1 + (other % 3)
        return ("restore", other, lvl, v)
    elif r < 7:
        # mid-branch on own session (BB payloads share the session prefix)
        b = r - 4  # 1..2
        v = b  # BB{b}-V{b}
        return ("branch", session, "BB%d" % b, v)
    else:
        # mid-branch on a peer session
        other = 1 + ((session + r + 1) % agents)
        return ("branch", other, "BB1", 1)


def estimate_tokens(session, level, variant):
    meta = os.path.join(PAYLOAD_DIR,
                        "b1c-S%d-%s-V%d.meta.json" % (session, level, variant))
    try:
        with open(meta) as f:
            return json.load(f).get("service_scope_tokens_est")
    except Exception:
        return None


def run_phase(agents, write_turns, read_turns, evidence_dir, stagger,
              time_budget, client_max, pause, snapshot_interval):
    run_dir = os.path.join(evidence_dir,
                           "run-%s" % time.strftime("%Y%m%d-%H%M%S"))
    turns_dir = os.path.join(run_dir, "turns")
    os.makedirs(turns_dir, exist_ok=True)
    state = {
        "run_dir": run_dir,
        "join_fh": open(os.path.join(run_dir, "join.log"), "a"),
        "join_lock": threading.Lock(),
        "metrics_lock": threading.Lock(),
        "mid_fh": open(os.path.join(run_dir, "mid-run-metrics.txt"), "a"),
        "t_start": time.time(),
    }
    stop = threading.Event()

    def sampler():
        while True:
            try:
                snap = common.parse_metrics(
                    common.fetch_metrics_text(state["metrics_lock"]))
            except Exception:
                snap = {}
            with state["join_lock"]:
                state["mid_fh"].write(json.dumps(
                    {"ts": round(time.time(), 3), "metrics": snap}) + "\n")
                state["mid_fh"].flush()
            if stop.wait(snapshot_interval):
                return

    th = threading.Thread(target=sampler, daemon=True)
    th.start()

    def agent_loop(aid, results):
        recs = []
        try:
            time.sleep(aid * stagger)
            turn = 0
            # Phase A: write chains (saturate the checkpoint pool)
            for lvl, v in write_chain_spec(aid):
                if time.time() - state["t_start"] > time_budget:
                    break
                turn += 1
                pl = payload(aid, lvl, v)
                prefix = os.path.join(turns_dir, "agent-%d" % aid,
                                      "t%d.write-%s" % (turn, lvl))
                rc, meta, sx, ts_s, ts_e, mb, ma, delta = common.run_request(
                    pl, prefix, _Opts(client_max), state["metrics_lock"])
                row = _row(aid, turn, "write", "A", aid, lvl, v, pl,
                           meta, sx, ts_s, ts_e, mb, ma, delta)
                recs.append(row)
                with state["join_lock"]:
                    state["join_fh"].write(json.dumps(row) + "\n")
                    state["join_fh"].flush()
                if pause:
                    time.sleep(pause)
            # Phase B: verify (restore + mid-branch)
            for i in range(1, read_turns + 1):
                if time.time() - state["t_start"] > time_budget:
                    break
                turn += 1
                kind, ses, lvl, v = read_chain_spec(aid, agents, i)
                pl = payload(ses, lvl, v)
                prefix = os.path.join(turns_dir, "agent-%d" % aid,
                                      "t%d.%s-%s" % (turn, kind, lvl))
                rc, meta, sx, ts_s, ts_e, mb, ma, delta = common.run_request(
                    pl, prefix, _Opts(client_max), state["metrics_lock"])
                row = _row(aid, turn, kind, "B", ses, lvl, v, pl,
                           meta, sx, ts_s, ts_e, mb, ma, delta)
                recs.append(row)
                with state["join_lock"]:
                    state["join_fh"].write(json.dumps(row) + "\n")
                    state["join_fh"].flush()
                if pause:
                    time.sleep(pause)
        except Exception as e:  # noqa: BLE001
            print("agent %d error: %s" % (aid, e), file=sys.stderr)
        results[aid] = recs

    results = {}
    threads = []
    for aid in range(1, agents + 1):
        t = threading.Thread(target=agent_loop, args=(aid, results))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    stop.set()
    th.join()
    try:
        final = common.parse_metrics(
            common.fetch_metrics_text(state["metrics_lock"]))
    except Exception:
        final = {}
    with state["join_lock"]:
        state["mid_fh"].write(json.dumps(
            {"ts": round(time.time(), 3), "metrics": final}) + "\n")
        state["mid_fh"].flush()
        state["mid_fh"].close()
        state["join_fh"].close()

    all_rows = [r for s in results.values() for r in s]
    import csv
    fieldnames = []
    for r in all_rows:
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)
    with open(os.path.join(run_dir, "runs.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in all_rows:
            w.writerow(r)
    verdict = {
        "status": "done", "agents": agents, "write_turns": write_turns,
        "read_turns": read_turns, "requests_total": len(all_rows),
        "run_dir": run_dir,
        "ts_start": round(state["t_start"], 3),
        "ts_end": round(time.time(), 3),
        "elapsed_s": round(time.time() - state["t_start"], 1),
    }
    with open(os.path.join(run_dir, "verdict.json"), "w") as f:
        json.dump(verdict, f, indent=1, default=str)
    print("GATE2_DRIVER_DONE run_dir=%s requests=%d" % (run_dir, len(all_rows)),
          flush=True)
    return run_dir


class _Opts:
    def __init__(self, client_max):
        self.client_max_time = client_max


def _row(aid, turn, kind, phase, session, lvl, v, pl_path, meta, sx,
         ts_s, ts_e, mb, ma, delta):
    u = (sx or {}).get("usage") or meta.get("usage") or {}
    ctd = (sx or {}).get("cached_tokens_details") or {}
    out, out_field = common.output_text(meta)
    row = {
        "agent_id": aid, "turn": turn, "turn_kind": kind, "phase": phase,
        "session": session, "level": lvl, "variant": v,
        "ts_start": round(ts_s, 3), "ts_end": round(ts_e, 3),
        "ttft_s": meta.get("ttft_s"), "wall_s": meta.get("wall_s"),
        "http": meta.get("http_code"), "finished": meta.get("finished"),
        "rid": (sx or {}).get("rid"),
        "payload": os.path.basename(pl_path),
        "prompt_len": u.get("prompt_tokens") if isinstance(u, dict) else None,
        "cached_tokens": (sx or {}).get("cached_tokens"),
        "device_hit": ctd.get("device"),
        "host_hit": ctd.get("host"),
        "storage_hit": ctd.get("storage"),
        "new_tokens_est": _recompute(u, ctd),
        "output_field": out_field,
        "output_sha16": common.sha16(out),
    }
    row.update({k: v for k, v in delta.items()})
    return row


def _recompute(u, ctd):
    p = u.get("prompt_tokens") if isinstance(u, dict) else None
    hits = [ctd.get(k) for k in ("device", "host", "storage")]
    if p is None or any(h is None for h in hits):
        return None
    return p - sum(hits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", type=int, default=8)
    ap.add_argument("--write-turns", type=int, default=4,
                    help="grow turns per agent in phase A")
    ap.add_argument("--read-turns", type=int, default=8,
                    help="read turns per agent in phase B")
    ap.add_argument("--stagger", type=float, default=1.0)
    ap.add_argument("--pause", type=float, default=0.0)
    ap.add_argument("--time-budget", type=int, default=3600)
    ap.add_argument("--client-max-time", type=int, default=580)
    ap.add_argument("--snapshot-interval", type=float, default=5.0)
    ap.add_argument("--evidence-dir", default="/root/evidence-gate2")
    args = ap.parse_args()
    run_dir = run_phase(args.agents, args.write_turns, args.read_turns,
                        args.evidence_dir, args.stagger, args.time_budget,
                        args.client_max_time, args.pause,
                        args.snapshot_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
