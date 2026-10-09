#!/usr/bin/env python3
"""R122 phase-2: mandatory drain gate + measurement window.

The phase-1 driver (driver122.py) built F1 (~41507 tok) and T (~24186 tok)
durably and applied+drained controlled pressure, but was stopped before the
window because its gate sizing was wrong (it used the storage_persisted
`kv_completed_tokens` last-chunk value instead of the full build token count).

This runner re-generates the exact same F1/T prompts (same nonce), enforces the
drain gate on the published host telemetry, and only then opens the window.
"""
import json, os, sys, time, threading, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import driver122 as d  # noqa: E402

OUT = d.OUT
SERVER_LOG = d.SERVER_LOG
PROBE_LOG = d.PROBE_LOG


def latest_kv_evictable():
    ev = None
    ref = None
    try:
        with open(SERVER_LOG, "r", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                e = d._parse_kv_evictable_change(line)
                if e is not None:
                    ev = e["evictable_after"]
                    ref = i
    except FileNotFoundError:
        pass
    return ev, ref


def loads():
    try:
        with urllib.request.urlopen(
            d.BASE + "/v1/loads", timeout=20
        ) as r:
            j = json.loads(r.read().decode())
        ld = j["loads"][0]
        return {
            "num_running_reqs": ld.get("num_running_reqs"),
            "num_waiting_reqs": ld.get("num_waiting_reqs"),
            "num_waiting_uncached_tokens": ld.get("num_waiting_uncached_tokens"),
            "queues": ld.get("queues"),
        }
    except Exception as e:
        return {"err": repr(e)[:200]}


def emit(path, rec):
    d.emit(os.path.join(OUT, path), rec)


def main():
    # regenerated prompts must reproduce build identities from phase 1
    f1_text = d.make_prompt(d.SEEDBASE + 0xB122, d.F1_K, d.F1_WORDS)
    t_text = d.make_prompt(d.SEEDBASE + 0xC122, d.T_K, d.T_WORDS)
    code, resp, err, el = d.tokenize([f1_text, t_text])
    if code != 200:
        print("ABORT tokenize", code, err, flush=True)
        return 2
    f1_ids, t_ids = resp["tokens"][0], resp["tokens"][1]
    f1_req = len(f1_ids) - 15
    t_req = len(t_ids) - 12
    peak_stage = max(f1_req, t_req)
    gate_required = peak_stage + d.GATE_MARGIN
    sum_required = f1_req + t_req + d.GATE_MARGIN
    emit(
        "state.jsonl",
        {
            "t": round(time.time(), 3),
            "evt": "phase2_start",
            "f1_tokens": len(f1_ids),
            "t_tokens": len(t_ids),
            "f1_required": f1_req,
            "t_required": t_req,
            "peak_stage_required": peak_stage,
            "sum_required": sum_required,
            "gate_required": gate_required,
            "gate_margin": d.GATE_MARGIN,
        },
    )
    print(
        "PHASE2",
        "f1=", len(f1_ids),
        "t=", len(t_ids),
        "gate_required(peak)=", gate_required,
        "sum_required=", sum_required,
        flush=True,
    )

    # ---- mandatory drain gate ----
    ev0, ev0_ref = latest_kv_evictable()
    gate_tail = d.LineTail(SERVER_LOG, d.server_line_count())
    last_evictable = ev0
    last_evictable_ref = ev0_ref
    last_evictable_ts = 0
    last_alloc_snapshot = None
    alloc_snapshot_ref = None
    last_alloc_snapshot_ts = 0
    non_health_admissions = 0
    gate_ok = False
    gate_polls = []
    for attempt in range(1, d.GATE_MAX_ATTEMPTS + 1):
        load = loads()
        hcode, _ = d._get(d.BASE + "/health", timeout=20)
        time.sleep(1.0)
        free = None
        free_ref = None
        for ln, text in gate_tail.new_lines():
            if "HEALTH_CHECK" in text:
                hh = d._parse_host_headroom(text)
                if hh is not None:
                    free = hh
                    free_ref = ln
            e = d._parse_kv_evictable_change(text)
            if e is not None:
                last_evictable = e["evictable_after"]
                last_evictable_ref = ln
                last_evictable_ts = e.get("ts_wall_ms") or 0
            snap = d._parse_alloc_snapshot(text)
            if snap is not None:
                last_alloc_snapshot = snap
                alloc_snapshot_ref = ln
                last_alloc_snapshot_ts = snap.get("ts_wall_ms") or 0
            if "evt=admission" in text and "HEALTH_CHECK" not in text:
                non_health_admissions += 1
        if (
            last_alloc_snapshot
            and last_alloc_snapshot.get("evictable_kv") is not None
            and last_alloc_snapshot_ts >= last_evictable_ts
        ):
            last_evictable = last_alloc_snapshot["evictable_kv"]
            last_evictable_ref = alloc_snapshot_ref
        allocable = (
            free + last_evictable
            if (free is not None and last_evictable is not None)
            else None
        )
        idle = (
            load.get("num_running_reqs") == 0
            and load.get("num_waiting_reqs") == 0
        )
        ok = (
            allocable is not None
            and allocable >= gate_required
            and idle
            and non_health_admissions == 0
        )
        poll = {
            "attempt": attempt,
            "t": round(time.time(), 3),
            "http": hcode,
            "host_free": free,
            "host_free_ref": free_ref,
            "host_evictable": last_evictable,
            "host_evictable_ref": last_evictable_ref,
            "host_allocable": allocable,
            "gate_required_peak": gate_required,
            "sum_required": sum_required,
            "margin": d.GATE_MARGIN,
            "load": load,
            "non_health_admissions": non_health_admissions,
            "ok": ok,
        }
        gate_polls.append(poll)
        d.emit(os.path.join(OUT, "gate_evidence.jsonl"), poll)
        print(
            "GATE", attempt, "free=", free, "evictable=", last_evictable,
            "allocable=", allocable, "required=", gate_required,
            "idle=", idle, "OK=", ok, flush=True,
        )
        if ok:
            gate_ok = True
            break
        time.sleep(d.GATE_INTERVAL)

    emit(
        "state.jsonl",
        {
            "t": round(time.time(), 3),
            "evt": "gate_result",
            "achieved": gate_ok,
            "attempts": len(gate_polls),
            "last": gate_polls[-1] if gate_polls else None,
        },
    )
    if not gate_ok:
        print("GATE_FAILED", json.dumps(gate_polls[-1] if gate_polls else {}),
              flush=True)
        return 3

    # ---- window ----
    sline = d.server_line_count()
    pbytes = os.path.getsize(PROBE_LOG)
    emit(
        "state.jsonl",
        {
            "t": round(time.time(), 3),
            "evt": "replay_window_start",
            "server_line": sline,
            "probe_bytes": pbytes,
            "gate": gate_polls[-1],
        },
    )
    print("REPLAY_WINDOW_START", sline, pbytes, flush=True)

    result = {}
    replay_rids = [d.R_F1, d.R_T]
    replay_prompts = [f1_ids, t_ids]
    emit("state.jsonl", {"t": round(time.time(), 3), "evt": "batch_plan",
                         "rids": replay_rids})

    def replay():
        result["r"] = d._post(
            d.BASE + "/v1/completions",
            {
                "model": d.MODEL,
                "prompt": replay_prompts,
                "max_tokens": 1,
                "temperature": 0,
                "stream": False,
                "session_id": d.R_SESS,
                "rid": replay_rids,
            },
            timeout=d.REPLAY_TIMEOUT,
        )

    th = threading.Thread(target=replay, daemon=True)
    th.start()
    emit("state.jsonl", {"t": round(time.time(), 3), "evt": "batch_submitted",
                         "rids": replay_rids})
    print("BATCH_SUBMITTED", replay_rids, flush=True)

    serv = d.LineTail(SERVER_LOG, sline)
    ptail = d.ByteTail(PROBE_LOG, pbytes)
    watch = set(replay_rids) | {d.BUILD_T, d.BUILD_F1, d.F1_SESS, d.T_SESS,
                                d.NONCE}
    keys = (
        "rh_preadmission_decision", "rh_match_prepare", "ready_stage",
        "restore_success", "restore_ready", "restore_recompute",
        "restore_host_alloc_wait", "restore_host_alloc_retry_result",
        "restore_host_alloc_wake_decision",
        "prefetch_issued", "prefetch_revoke", "prefetch_finalize",
        "admission", "restore_retry", "restore_disposition",
        "restore_state", "restore_backup", "ready_host", "rh_ready_host",
        "durability_barrier", "storage_persisted", "restore_hybrid_finalize",
        "ready_pool", "Prefill batch", "prefetch_io_done",
        "promotion_reserve", "promotion_transfer", "promotion_release",
    )
    probe_keys = (
        "pc_storage_query", "pc_outcome", "pc_l3_host", "pc_get",
        "storage_persisted", "durability_barrier", "residency_detach",
        "residency_release_enqueued", "residency_free_complete",
        "build_complete", "backup_host_commit",
    )
    chain = {}
    park_at = None
    trig_n = 0
    next_trig = 0.0
    t_terminal = False
    deadline = time.time() + d.KEEPALIVE
    while time.time() < deadline:
        for ln, text in serv.new_lines():
            if any(k in text for k in keys) and any(w in text for w in watch):
                with open(os.path.join(OUT, "watch.log"), "a") as h:
                    h.write(f"S{ln}\t{text}\n")
                for k in keys:
                    if k in text:
                        chain.setdefault(k, []).append(ln)
                if "SPEC_BUDGET" in text and park_at is None:
                    park_at = time.time()
                    print("TARGET_PARKED", ln, flush=True)
                if d.R_T in text and (
                    "restore_hybrid_finalize" in text
                    or "restore_success" in text
                    or "restore_recompute" in text
                ):
                    t_terminal = True
        for _, text in ptail.new_lines():
            with open(os.path.join(OUT, "probe.log"), "a") as h:
                h.write(text + "\n")
            if any(k in text for k in probe_keys) and any(w in text for w in watch):
                with open(os.path.join(OUT, "watch.log"), "a") as h:
                    h.write(f"P\t{text}\n")
                for k in probe_keys:
                    if k in text:
                        chain.setdefault("probe:" + k, []).append("probe")
        if park_at and trig_n < d.TRIGGERS and time.time() >= next_trig:
            if not any(k in chain for k in ("restore_success", "restore_ready")):
                trig_n += 1
                next_trig = time.time() + 25
                rid = f"r122-{d.NONCE}-trig-{trig_n}"
                threading.Thread(
                    target=d.completion,
                    args=(rid, f"trigger {d.NONCE} refill {trig_n} done",
                          d.R_SESS, f"trigger-{trig_n}"),
                    kwargs={"timeout": 300},
                    daemon=True,
                ).start()
        if not th.is_alive():
            break
        if t_terminal:
            break
        time.sleep(2)
    time.sleep(1)
    th.join(timeout=30)

    outcome = "still-pending"
    if "r" in result:
        rcode, rresp, rerr, rel = result["r"]
        rec = {
            "tag": "batch-replay",
            "rids": replay_rids,
            "session_id": d.R_SESS,
            "http": rcode,
            "elapsed_s": rel,
            "usage": (rresp or {}).get("usage") if isinstance(rresp, dict) else None,
            "err": rerr,
            "choices": (rresp or {}).get("choices") if isinstance(rresp, dict) else None,
            "ts": round(time.time(), 3),
        }
        d.emit(os.path.join(OUT, "requests.jsonl"), rec)
        outcome = "completed" if rcode == 200 else f"http-{rcode}"
        print("BATCH_DONE", rcode, rel, flush=True)
    else:
        d.emit(
            os.path.join(OUT, "requests.jsonl"),
            {
                "tag": "batch-replay",
                "rids": replay_rids,
                "session_id": d.R_SESS,
                "http": "000",
                "elapsed_s": d.KEEPALIVE,
                "err": "client-keepalive-timeout",
            },
        )
        print("BATCH_STILL_PENDING", flush=True)
    emit(
        "state.jsonl",
        {
            "t": round(time.time(), 3),
            "evt": "monitor_end",
            "outcome": outcome,
            "still_alive": th.is_alive(),
            "chain": chain,
        },
    )
    print("MONITOR_END", outcome, json.dumps(chain), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
