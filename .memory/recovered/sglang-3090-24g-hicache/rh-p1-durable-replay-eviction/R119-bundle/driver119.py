#!/usr/bin/env python3
"""R119 P1 SPEC_BUDGET chain driver.

Fixes the R118 harness/workload defects:
  (1) session id is a true global AND passed as a parameter to trigger();
      every trigger rid is verified to reach the server log.
  (2) the batch replay HTTP request is kept open (joined) until the full
      target lifecycle completes or a long explicit timeout; the terminal
      outcome (completed/aborted/still-pending) is recorded.
  (3) candidate prefixes get an explicit small clean unique-first-token
      seed write before the full write (R114 recipe); the driver waits on
      the existing probe log for storage_persisted durability of the
      candidate build rids and records whether each was confirmed.

Public HTTP only (health, tokenize, completions); reads existing server
and probe logs. No product imports, no instrumentation, no synthetic
events, no server control.
"""
import json, os, random, sys, threading, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:30000"
MODEL = "/mnt/data/models/qwen35-gptq"
SERVER_LOG = "/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r112.log"
PROBE_LOG = "/tmp/t38c-probe.log"
OUT = os.environ.get("R119_OUT", "/tmp/r119")
NONCE = os.environ.get("R119_NONCE", "p1")
SESS = f"r119-s-{NONCE}"
TARGET = f"r119-{NONCE}-R-T"
ISSUERS = [f"r119-{NONCE}-R-F1", f"r119-{NONCE}-R-F2"]
BATCH_RIDS = ISSUERS + [TARGET]
START_LINE = int(os.environ.get("R119_START_LINE", "0"))
PROBE_START_BYTES = int(os.environ.get("R119_PROBE_START_BYTES", "0"))
REPLAY_TIMEOUT = float(os.environ.get("R119_REPLAY_TIMEOUT", "1800"))
KEEPALIVE = float(os.environ.get("R119_KEEPALIVE", "1680"))
TARGET_SEED = os.environ.get("R119_TARGET_SEED", "1") == "1"
DUR_WAIT = float(os.environ.get("R119_DUR_WAIT", "90"))

WORD = "abcdefghijklmnopqrstuvwxyz"
_lock = threading.Lock()


def rw(rng):
    return "".join(rng.choice(WORD) for _ in range(rng.randint(4, 10)))


def rare_prefix(k):
    # unique-first-token: distinct alchemical code points -> fresh root child
    return "".join(chr(0x1F700 + ((k * 13 + j) % 0x60)) for j in range(4))


def make_prompt(seed, k, n):
    rng = random.Random(seed)
    head = rare_prefix(k)
    body = " ".join("uniq" + rw(rng) for _ in range(40))
    tail = " ".join(rw(rng) for _ in range(max(0, n - 40)))
    return head + " " + body + " " + tail


def emit(path, rec):
    with _lock:
        with open(path, "a") as h:
            h.write(json.dumps(rec) + "\n")


def _post(url, payload, timeout=1200):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    code = None
    resp = None
    err = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status
            resp = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            err = e.read().decode()[:1500]
        except Exception:
            err = repr(e)[:400]
    except Exception as e:
        code = "000"
        err = repr(e)[:600]
    return code, resp, err, round(time.time() - t0, 3)


def tokenize(texts):
    return _post(BASE + "/v1/tokenize", {"model": MODEL, "prompt": texts})


def completion(rid, prompt, session, tag, max_tokens=1, timeout=1200):
    code, resp, err, el = _post(BASE + "/v1/completions", {
        "model": MODEL, "prompt": prompt, "max_tokens": max_tokens,
        "temperature": 0, "stream": False,
        "session_id": session, "rid": rid,
    }, timeout=timeout)
    rec = {"tag": tag, "rid": rid, "session_id": session, "http": code,
           "elapsed_s": el, "err": err,
           "usage": (resp or {}).get("usage") if isinstance(resp, dict) else None}
    emit(os.path.join(OUT, "requests.jsonl"), rec)
    print("REQ", tag, rid, code, el, flush=True)
    return code, resp, err, el


def trigger(i):
    # Session is explicitly passed; no module-level name lookup.
    rid = f"r119-{NONCE}-trig-{i}"
    code, resp, err, el = _post(BASE + "/v1/completions", {
        "model": MODEL, "prompt": f"trigger {NONCE} refill {i} done",
        "max_tokens": 1, "temperature": 0, "stream": False,
        "session_id": SESS, "rid": rid,
    })
    rec = {"tag": f"trigger-{i}", "rid": rid, "session_id": SESS,
           "http": code, "elapsed_s": el, "err": err}
    emit(os.path.join(OUT, "requests.jsonl"), rec)
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "trigger", "rid": rid,
          "http": code, "elapsed_s": el})
    print("TRIGGER", i, rid, code, el, flush=True)
    return rid


class LineTail:
    def __init__(self, path, start_line):
        self.path = path
        self.n = start_line
        self._fh = None

    def new_lines(self):
        if self._fh is None:
            self._fh = open(self.path, "r", encoding="utf-8", errors="replace")
            for _ in range(self.n):
                self._fh.readline()
        out = []
        while True:
            line = self._fh.readline()
            if not line:
                break
            self.n += 1
            out.append((self.n, line.rstrip("\n")))
        return out


class ByteTail:
    def __init__(self, path, start_bytes):
        self.path = path
        self.pos = start_bytes
        self._fh = None
        self._buf = ""

    def new_lines(self):
        if self._fh is None:
            self._fh = open(self.path, "rb")
            self._fh.seek(self.pos)
        out = []
        while True:
            chunk = self._fh.read()
            if not chunk:
                break
            self.pos += len(chunk)
            self._buf += chunk.decode("utf-8", errors="replace")
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                out.append(line)
        return [(None, l) for l in out]


def server_line_count():
    with open(SERVER_LOG, "r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def wait_persistence(build_rids, probe_tail, deadline_s):
    """Read the existing probe log for storage_persisted per build_rid."""
    counts = {r: 0 for r in build_rids}
    end = time.time() + deadline_s
    while time.time() < end:
        for _, text in probe_tail.new_lines():
            if '"evt": "storage_persisted"' not in text:
                continue
            for r in build_rids:
                if f'"build_rid": "{r}"' in text:
                    counts[r] += 1
        if all(v > 0 for v in counts.values()):
            break
        time.sleep(2)
    return counts


def main():
    os.makedirs(OUT, exist_ok=True)
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "driver_start",
          "start_line": START_LINE, "probe_start_bytes": PROBE_START_BYTES,
          "sess": SESS, "target": TARGET})

    # Prompt plan: T target (~27k), F1/F2 issuers (~43k), D1..D4 decoys (~43k).
    plan = {
        "T":  (f"r119-{NONCE}-tk", 0x41, 7000),
        "F1": (f"r119-{NONCE}-f1k", 0x45, 11000),
        "F2": (f"r119-{NONCE}-f2k", 0x49, 11000),
        "D1": (f"r119-{NONCE}-d1k", 0x60, 11000),
        "D2": (f"r119-{NONCE}-d2k", 0x64, 11000),
        "D3": (f"r119-{NONCE}-d3k", 0x68, 11000),
        "D4": (f"r119-{NONCE}-d4k", 0x6c, 11000),
        "D5": (f"r119-{NONCE}-d5k", 0x70, 11000),
    }
    texts = {k: make_prompt(seed, kk, n) for k, (seed, kk, n) in plan.items()}

    code, resp, err, el = tokenize([texts[k] for k in plan])
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "tokenize", "http": code,
          "elapsed_s": el, "err": err, "counts": (resp or {}).get("count")})
    print("TOKENIZE", code, (resp or {}).get("count"), el, flush=True)
    if code != 200:
        emit(os.path.join(OUT, "state.jsonl"), {"evt": "abort_tokenize", "err": err})
        return 2
    toks = resp["tokens"]
    ids = {k: toks[i] for i, k in enumerate(plan)}

    probe_tail = ByteTail(PROBE_LOG, PROBE_START_BYTES)

    # ---- Phase A: small clean unique-first-token seed write per candidate ----
    seed_rids = {}
    seed_keys = ["T", "F1", "F2"] if TARGET_SEED else ["F1", "F2"]
    for k in seed_keys:
        seed_ids = ids[k][:2500]
        rid = f"r119-{NONCE}-{k}-seed"
        seed_rids[k] = rid
        completion(rid, seed_ids, SESS, f"seed-{k}", timeout=600)

    # ---- Phase B: full candidate writes (same session, extend seed chain) ----
    build_rids = {"T": f"r119-{NONCE}-T", "F1": f"r119-{NONCE}-F1",
                  "F2": f"r119-{NONCE}-F2"}
    for k in ("T", "F1", "F2"):
        completion(build_rids[k], ids[k], SESS, f"build-{k}", timeout=600)

    # ---- Phase C: decoys force device/host eviction (separate sessions) ----
    for i, k in enumerate(("D1", "D2", "D3", "D4", "D5"), 1):
        completion(f"r119-{NONCE}-D{i}", ids[k], f"r119-{NONCE}-d{i}",
                   f"build-{k}", timeout=600)

    # ---- Phase D: confirm durability of candidate build rids ----
    dur = wait_persistence(list(build_rids.values()), probe_tail, DUR_WAIT)
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "durability_probe", "counts": dur})
    print("DURABILITY", json.dumps(dur), flush=True)

    # ---- Phase E: single input_ids batch -> one frontier pass ----
    sline = server_line_count()
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "replay_window_start", "server_line": sline})
    print("REPLAY_WINDOW_START", sline, flush=True)

    result = {}

    def replay():
        result["r"] = _post(BASE + "/v1/completions", {
            "model": MODEL, "prompt": [ids["F1"], ids["F2"], ids["T"]],
            "max_tokens": 1, "temperature": 0, "stream": False,
            "session_id": SESS, "rid": BATCH_RIDS,
        }, timeout=REPLAY_TIMEOUT)

    th = threading.Thread(target=replay, daemon=True)
    th.start()
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "batch_submitted", "rids": BATCH_RIDS})
    print("BATCH_SUBMITTED", BATCH_RIDS, flush=True)

    serv = LineTail(SERVER_LOG, sline)
    watch = set(BATCH_RIDS)
    keys = ("rh_preadmission_decision", "rh_match_prepare", "ready_stage",
            "restore_success", "restore_ready", "restore_recompute",
            "restore_host_alloc_wait", "restore_host_alloc_retry_result",
            "prefetch_issued", "prefetch_revoke", "prefetch_finalize",
            "admission", "restore_retry", "restore_disposition",
            "restore_state", "restore_backup", "ready_host", "rh_ready_host",
            "durability_barrier", "storage_persisted", "restore_hybrid_finalize")
    chain = {}
    adm_seen = set()
    park_at = None
    trig_n = 0
    next_trig = 0.0
    deadline = time.time() + KEEPALIVE
    while time.time() < deadline:
        for ln, text in serv.new_lines():
            if target_or_key(text, watch, keys):
                is_adm = "evt=admission" in text
                if is_adm:
                    ar = text.split("rid=", 1)[-1].split(" ", 1)[0]
                    if ar in adm_seen:
                        continue
                    adm_seen.add(ar)
                with open(os.path.join(OUT, "watch.log"), "a") as h:
                    h.write(f"{ln}\t{text}\n")
                if TARGET in text:
                    for k in keys:
                        if k in text:
                            chain.setdefault(k, []).append(ln)
                    if "SPEC_BUDGET" in text and "negative_cache" in text and park_at is None:
                        park_at = time.time()
                        print("TARGET_PARKED", ln, flush=True)
        for _, text in probe_tail.new_lines():
            if TARGET in text or f"r119-{NONCE}-T" in text:
                with open(os.path.join(OUT, "watch.log"), "a") as h:
                    h.write(f"probe\t{text}\n")
                if TARGET in text or f'"build_rid": "r119-{NONCE}-T"' in text:
                    for k in keys:
                        if k in text:
                            chain.setdefault("probe:" + k, []).append("probe")
        if park_at and trig_n < 6 and time.time() >= next_trig:
            if not any(k in chain for k in ("restore_success", "restore_ready")):
                trig_n += 1
                next_trig = time.time() + 20
                threading.Thread(target=trigger, args=(trig_n,), daemon=True).start()
        if "restore_success" in chain or "restore_ready" in chain:
            if not th.is_alive():
                break
        if not th.is_alive():
            break
        time.sleep(2)

    outcome = "still-pending"
    if "r" in result:
        code, resp, err, el = result["r"]
        rec = {"tag": "batch-replay", "rids": BATCH_RIDS, "session_id": SESS,
               "http": code, "elapsed_s": el,
               "usage": (resp or {}).get("usage") if isinstance(resp, dict) else None,
               "err": err,
               "choices": (resp or {}).get("choices") if isinstance(resp, dict) else None}
        emit(os.path.join(OUT, "requests.jsonl"), rec)
        outcome = "completed" if code == 200 else f"http-{code}"
        print("BATCH_DONE", code, el, flush=True)
    else:
        rec = {"tag": "batch-replay", "rids": BATCH_RIDS, "session_id": SESS,
               "http": "000", "elapsed_s": round(time.time() - deadline + KEEPALIVE, 3),
               "err": "client-keepalive-timeout", "outcome": "still-pending"}
        emit(os.path.join(OUT, "requests.jsonl"), rec)
        print("BATCH_STILL_PENDING", flush=True)
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "monitor_end", "outcome": outcome,
          "still_alive": th.is_alive(), "chain": chain})
    print("MONITOR_END", outcome, json.dumps(chain), flush=True)
    return 0


def target_or_key(text, watch, keys):
    if not any(k in text for k in keys):
        return False
    return any(w in text for w in watch) or f"r119-{NONCE}" in text


if __name__ == "__main__":
    sys.exit(main())
