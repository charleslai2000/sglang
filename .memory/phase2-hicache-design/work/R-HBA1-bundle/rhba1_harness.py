#!/usr/bin/env python3
"""R-HBA1 two-session task-switch harness (frozen contract 2026-09-12).

Conditions:
  l3_hot      D resident in L2 (device-cold, host-hit), built by filler eviction.
  l3_off      D L3-only, Ready Horizon OFF.
  l3_on_short D L3-only, RH ON, short A  (expected insufficient lead).
  l3_on_long  D L3-only, RH ON, long A   (expected sufficient lead).

Per replicate: build/keep D in L3 (or L2 for hot), then run Session A as a GPU
occupancy clock, enqueue B = D + ~128-token suffix right after A's first token,
and record marks on the shared CLOCK_MONOTONIC. Server-side marks are parsed
from the server log and correlated to B by the enqueue that follows B's send.

Observation only: this script never modifies the server or its profile.
"""
import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request


WORDS = (
    "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod "
    "tempor incididunt ut labore et dolore magna aliqua enim ad minim veniam "
    "quis nostrud exercitation ullamco laboris nisi aliquip ex ea commodo "
    "consequat duis aute irure in reprehenderit voluptate velit esse cillum "
    "eu fugiat nulla pariatur excepteur sint occaecat cupidatat non proident "
    "sunt culpa qui officia deserunt mollit anim id est laborum"
).split()


def make_text(n_words, nonce, suffix_words=0):
    text = "[%s] " % nonce + " ".join(
        WORDS[i % len(WORDS)] for i in range(n_words)
    )
    if suffix_words:
        text += "  " + " ".join(
            WORDS[(n_words + i) % len(WORDS)] for i in range(suffix_words)
        )
    return text


def now_ns():
    return time.monotonic_ns()


# ---------------------------------------------------------------- HTTP client
def _request(base, payload, timeout):
    req = urllib.request.Request(
        base + "/v1/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=timeout)


def complete(base, prompt, max_tokens, timeout, return_details=False, sink=None):
    """Stream a completion; if `sink` is given it is mutated live so a caller
    can observe first-token arrival before the stream ends."""
    payload = {
        "model": "x",
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "stream": True,
    }
    if return_details:
        payload["return_cached_tokens_details"] = True
    rec = sink if sink is not None else {}
    rec.setdefault("first_ns", None)
    rec.setdefault("last_ns", None)
    rec.setdefault("content_chunks", 0)
    rec.setdefault("usage", None)
    rec.setdefault("cached_tokens_details", None)
    rec.setdefault("finish_reason", None)
    with _request(base, payload, timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except Exception:
                continue
            ts = now_ns()
            if obj.get("usage"):
                rec["usage"] = obj["usage"]
            d = obj.get("cached_tokens_details")
            if d is None and isinstance(obj.get("sglext"), dict):
                d = obj["sglext"].get("cached_tokens_details")
            if d is not None:
                rec["cached_tokens_details"] = d
            ch = obj.get("choices") or []
            if ch:
                txt = ch[0].get("text") or ""
                if txt:
                    if rec["first_ns"] is None:
                        rec["first_ns"] = ts
                    rec["last_ns"] = ts
                    rec["content_chunks"] += 1
                if ch[0].get("finish_reason"):
                    rec["finish_reason"] = ch[0]["finish_reason"]
    return rec


def _get(base, path, timeout):
    with urllib.request.urlopen(base + path, timeout=timeout) as r:
        return r.read().decode()


def flush_until_ok(base, timeout, attempts=40, gap_s=2.0):
    for i in range(attempts):
        try:
            body = _get(base, "/flush_cache?timeout=60", timeout)
            return {"attempts": i + 1, "ok": True, "body": body}
        except urllib.error.HTTPError as e:
            last = {"attempts": i + 1, "ok": False, "status": e.code,
                    "body": e.read().decode("utf-8", "replace")}
        except Exception as e:  # noqa: BLE001
            last = {"attempts": i + 1, "ok": False, "body": repr(e)}
        time.sleep(gap_s)
    return last


# ------------------------------------------------------------- server log marks
RE_ENQ = re.compile(r"evt=enqueue_mono_ns rid=(\S+) enqueue_mono_ns=(\d+)")
RE_PF = re.compile(
    r"evt=prefetch_issued rid=(\S+) prefetch_length=(\d+) "
    r"prefetch_issue_mono_ns=(\d+)"
)
RE_RH = re.compile(
    r"evt=ready_host .*?rid=(\S+) .*?completed_kv_tokens=(\d+)"
    r" required_aux_pools=(\[.*?\]) completed_aux_units=(\{.*?\})"
    r" restore_state_before=\S+ restore_state_after=(\S+) finalize_result=(\S+)"
    r".*?ready_monotonic_ns=(\d+)"
)
RE_ADM = re.compile(
    r"evt=admission\.v2 .*?rid=(\S+) .*?ready_host_observed=(\S+) "
    r".*?admission_monotonic_ns=(\d+)"
)
RE_RS = re.compile(r"evt=restore_success rid=(\S+) n_tokens=(\d+)")
RE_RST = re.compile(r"evt=restore_state rid=(\S+) state=(\S+)")
RE_HYBRID = re.compile(
    r"evt=restore_hybrid_finalize.*?\"rid\": \"(\S+?)\".*?"
    r"\"kv_expected\": (\d+), \"kv_fetched\": (\d+).*?"
    r"\"mamba\": \{\"expected\": (\d+), \"fetched\": (\d+)\}.*?"
    r"\"result\": \"(\S+?)\""
)


def parse_marks(log_path):
    """Parse all [P2A]/[P3]/[HAE] marks from the server log into per-rid dicts."""
    marks = {}

    def rid_entry(rid):
        return marks.setdefault(
            rid,
            {
                "enqueue_ns": None,
                "prefetch_issue_ns": None,
                "prefetch_length": None,
                "ready_host_ns": None,
                "completed_kv_tokens": None,
                "restore_state_after": None,
                "finalize_result": None,
                "admission_ns": None,
                "ready_host_observed": None,
                "restore_success_tokens": None,
                "restore_states": [],
                "hybrid_finalize": None,
            },
        )

    if not os.path.exists(log_path):
        return marks
    with open(log_path, "r", errors="replace") as fh:
        for line in fh:
            if "HEALTH_CHECK" in line:
                continue
            m = RE_ENQ.search(line)
            if m:
                rid_entry(m.group(1))["enqueue_ns"] = int(m.group(2))
                continue
            m = RE_PF.search(line)
            if m:
                e = rid_entry(m.group(1))
                e["prefetch_length"] = int(m.group(2))
                e["prefetch_issue_ns"] = int(m.group(3))
                continue
            m = RE_RH.search(line)
            if m:
                e = rid_entry(m.group(1))
                e["completed_kv_tokens"] = int(m.group(2))
                e["required_aux_pools"] = m.group(3)
                e["completed_aux_units"] = m.group(4)
                e["restore_state_after"] = m.group(5)
                e["finalize_result"] = m.group(6)
                e["ready_host_ns"] = int(m.group(7))
                continue
            m = RE_ADM.search(line)
            if m:
                e = rid_entry(m.group(1))
                e["ready_host_observed"] = m.group(2)
                e["admission_ns"] = int(m.group(3))
                continue
            m = RE_RS.search(line)
            if m:
                e = rid_entry(m.group(1))
                e["restore_success_tokens"] = int(m.group(2))
                continue
            m = RE_RST.search(line)
            if m:
                e = rid_entry(m.group(1))["restore_states"].append(m.group(2))
                continue
            m = RE_HYBRID.search(line)
            if m:
                e = rid_entry(m.group(1))
                e["hybrid_finalize"] = {
                    "kv_expected": int(m.group(2)),
                    "kv_fetched": int(m.group(3)),
                    "mamba_expected": int(m.group(4)),
                    "mamba_fetched": int(m.group(5)),
                    "result": m.group(6),
                }
    return marks


def _count(log_path, pattern):
    if not os.path.exists(log_path):
        return 0
    n = 0
    with open(log_path, "r", errors="replace") as fh:
        for line in fh:
            if pattern in line:
                n += 1
    return n


def wait_log_quiet(log_path, needle, quiet_s, timeout_s):
    """Wait until `needle` count stops growing for quiet_s (or timeout)."""
    deadline = time.monotonic() + timeout_s
    last = _count(log_path, needle)
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        time.sleep(1.0)
        cur = _count(log_path, needle)
        if cur != last:
            last = cur
            last_change = time.monotonic()
        elif time.monotonic() - last_change >= quiet_s:
            return {"quiesced": True, "count": cur}
    return {"quiesced": False, "count": last}


def tokenize_counts(model, texts):
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model, trust_remote_code=True)
    out = []
    for t in texts:
        out.append(len(tok(t, add_special_tokens=False)["input_ids"]))
    return out


def pick_b_rid(marks, b_send_ns, tol_ns=30_000_000):
    cands = [
        (e["enqueue_ns"], rid)
        for rid, e in marks.items()
        if e["enqueue_ns"] is not None
        and e["enqueue_ns"] >= b_send_ns - tol_ns
    ]
    if not cands:
        return None
    return min(cands)[1]


# ------------------------------------------------------------------ main flow
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", required=True,
                    choices=["l3_hot", "l3_off", "l3_on_short", "l3_on_long"])
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--base", default="http://127.0.0.1:30000")
    ap.add_argument("--model", default="/mnt/data/models/qwen35-gptq")
    ap.add_argument("--server-log", required=True)
    ap.add_argument("--nonce", default=None)
    ap.add_argument("--words", type=int, default=21000)
    ap.add_argument("--suffix-words", type=int, default=96)
    ap.add_argument("--a-words", type=int, default=60)
    ap.add_argument("--filler-words", type=int, default=30000)
    ap.add_argument("--hot-mode", default="l2", choices=["l2", "l1l2"])
    ap.add_argument("--b-after-chunks", type=int, default=0,
                    help="enqueue B after A has emitted this many chunks "
                         "(0 = auto: 1 for sufficient, near-end for short)")
    ap.add_argument("--prime-max-tokens", type=int, default=16)
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--prime-quiet-s", type=float, default=6.0)
    ap.add_argument("--settle-s", type=float, default=1.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    nonce = args.nonce or ("%s-%d" % (args.condition, int(time.time())))
    a_max = 8 if args.condition == "l3_on_short" else 256
    hot = args.condition == "l3_hot"
    if args.b_after_chunks > 0:
        b_after = args.b_after_chunks
    elif args.condition == "l3_on_short":
        b_after = max(a_max - 3, 1)
    else:
        b_after = 1

    d_text = make_text(args.words, "D-" + nonce)
    b_text = make_text(args.words, "D-" + nonce, args.suffix_words)
    a_text = make_text(args.a_words, "A-" + nonce)
    f_text = make_text(args.filler_words, "F-" + nonce)

    counts = {}
    try:
        counts["D"], counts["B"], counts["A"], counts["F"] = tokenize_counts(
            args.model, [d_text, b_text, a_text, f_text]
        )
        counts["B_starts_with_D"] = counts["B"] > counts["D"]
    except Exception as e:  # noqa: BLE001
        counts["error"] = repr(e)

    result = {
        "condition": args.condition,
        "nonce": nonce,
        "a_max_tokens": a_max,
        "hot_mode": args.hot_mode if hot else None,
        "counts": counts,
        "server_log": args.server_log,
        "replicates": [],
    }

    # ---- build D (durable in L3) once.
    t0 = now_ns()
    prime = complete(args.base, d_text, args.prime_max_tokens, args.timeout)
    result["prime_s"] = (now_ns() - t0) / 1e9
    result["prime_usage"] = prime["usage"]
    result["prime_l3_quiet"] = wait_log_quiet(
        args.server_log, "evt=extent_write", args.prime_quiet_s, 180
    )
    if hot and args.hot_mode == "l2":
        # One filler to push D out of L1 into L2 before the first measured run.
        pass

    for rep in range(args.repeats):
        rep_rec = {"rep": rep}
        try:
            if hot:
                tF = now_ns()
                complete(args.base, f_text, 1, args.timeout)
                rep_rec["filler_s"] = (now_ns() - tF) / 1e9
                time.sleep(args.settle_s)
            else:
                rep_rec["flush"] = flush_until_ok(args.base, args.timeout)
                time.sleep(args.settle_s)

            a_rec = {}
            b_rec = {}

            def run_a():
                complete(args.base, a_text, a_max, args.timeout, sink=a_rec)

            th = threading.Thread(target=run_a, daemon=True)
            th.start()
            # wait until A has emitted `b_after` chunks (lead construction)
            deadline = time.monotonic() + args.timeout
            while (
                (a_rec.get("content_chunks") or 0) < b_after
                and time.monotonic() < deadline
            ):
                time.sleep(0.002)

            b_send_ns = now_ns()
            b_rec.update(
                complete(args.base, b_text, 1, args.timeout,
                         return_details=True)
            )
            th.join(timeout=args.timeout)

            rep_rec["a_first_ns"] = a_rec.get("first_ns")
            rep_rec["a_last_ns"] = a_rec.get("last_ns")
            rep_rec["a_chunks"] = a_rec.get("content_chunks")
            rep_rec["b_send_ns"] = b_send_ns
            rep_rec["b_first_ns"] = b_rec.get("first_ns")
            rep_rec["b_last_ns"] = b_rec.get("last_ns")
            rep_rec["b_details"] = b_rec.get("cached_tokens_details")
            rep_rec["b_usage"] = b_rec.get("usage")
            rep_rec["b_finish"] = b_rec.get("finish_reason")
        except Exception as e:  # noqa: BLE001
            rep_rec["error"] = repr(e)
        result["replicates"].append(rep_rec)

    # ---- correlate server marks (re-read the final log).
    marks = parse_marks(args.server_log)
    correlate(result, marks, hot)

    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=1)
    print(json.dumps({
        "condition": args.condition,
        "counts": counts,
        "reps": len(result["replicates"]),
        "out": args.out,
    }))


def correlate(result, marks, hot):
    """Attach server marks + derived metrics to each replicate (post-hoc)."""
    for rep_rec in result["replicates"]:
        b_send = rep_rec.get("b_send_ns")
        if b_send is None:
            continue
        rid = pick_b_rid(marks, b_send)
        rep_rec["b_rid"] = rid
        if rid is None:
            continue
        e = marks[rid]
        rep_rec["marks"] = e
        a_last = rep_rec.get("a_last_ns")
        b_first = rep_rec.get("b_first_ns")
        if a_last and e.get("ready_host_ns"):
            rep_rec["prefetch_slack_ns"] = a_last - e["ready_host_ns"]
        if a_last and e.get("admission_ns"):
            rep_rec["admission_vs_a_last_ns"] = e["admission_ns"] - a_last
        if e.get("ready_host_ns") and e.get("prefetch_issue_ns"):
            rep_rec["stage_ns"] = e["ready_host_ns"] - e["prefetch_issue_ns"]
        if a_last and e.get("enqueue_ns"):
            rep_rec["lead_ns"] = a_last - e["enqueue_ns"]
        if a_last and b_first:
            rep_rec["tftt_ns"] = b_first - a_last
        if e.get("admission_ns") and e.get("ready_host_ns"):
            rep_rec["ready_before_admission_ns"] = (
                e["admission_ns"] - e["ready_host_ns"]
            )
        det = rep_rec.get("b_details") or {}
        cached_total = sum(
            int(det.get(k) or 0) for k in ("device", "host", "storage")
        )
        rep_rec["cached_total"] = cached_total
        rep_rec["D_req"] = int(det.get("storage") or 0) if not hot else cached_total
        if rep_rec["D_req"]:
            rep_rec["avoidable_recompute"] = max(
                0, rep_rec["D_req"] - cached_total
            )


def reparse(result_path):
    """Re-derive marks/metrics from an existing result JSON (no GPU run)."""
    with open(result_path) as fh:
        result = json.load(fh)
    marks = parse_marks(result["server_log"])
    correlate(result, marks, result["condition"] == "l3_hot")
    with open(result_path, "w") as fh:
        json.dump(result, fh, indent=1)
    print(json.dumps({"reparsed": result_path,
                      "reps": len(result["replicates"])}))


if __name__ == "__main__":
    main()
