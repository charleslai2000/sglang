#!/usr/bin/env python3
"""R118 P1 SPEC_BUDGET chain driver.

Public HTTP only (health, tokenize, completions). No product imports, no
instrumentation, no server control. Builds large L3 content for a target
session, evicts it with decoys, then submits a single input_ids BATCH
[issuer1, issuer2, target] so the ready-horizon pass sees all three in one
frontier; the first issue exhausts the speculative budget and the deferred
target is parked DeclineReason.SPEC_BUDGET.
"""
import json, os, random, sys, threading, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:30000"
MODEL = "/mnt/data/models/qwen35-gptq"
OUT = "/tmp/r118"
TRANSCRIPT = OUT + "/transcript.jsonl"
STATE = OUT + "/state.jsonl"
SERVER_LOG = "/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r112.log"
START_LINE = int(os.environ.get("R118_START_LINE", "1056603"))
NONCE = os.environ.get("R118_NONCE", str(int(time.time())))

WORD = "abcdefghijklmnopqrstuvwxyz"
_lock = threading.Lock()


def rw(rng):
    return "".join(rng.choice(WORD) for _ in range(rng.randint(4, 10)))


def rare_prefix(k):
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
        err = e.read().decode()[:800]
    except Exception as e:
        code = "000"
        err = repr(e)[:400]
    return code, resp, err, round(time.time() - t0, 3)


def tokenize(texts):
    code, resp, err, el = _post(BASE + "/v1/tokenize",
                                {"model": MODEL, "prompt": texts})
    return code, resp, err, el


def build(rid, ids, session, tag):
    code, resp, err, el = _post(BASE + "/v1/completions", {
        "model": MODEL, "prompt": ids, "max_tokens": 1, "temperature": 0,
        "stream": False, "session_id": session, "rid": rid,
    })
    rec = {"tag": tag, "rid": rid, "session_id": session,
           "prompt_tokens": (resp or {}).get("usage", {}).get("prompt_tokens"),
           "elapsed_s": el, "http": code, "err": err}
    emit(TRANSCRIPT, rec)
    print("BUILD", tag, code, rec["prompt_tokens"], el, rid, flush=True)
    return rec


def trigger(i):
    rid = f"r118-{NONCE}-trig-{i}"
    code, resp, err, el = _post(BASE + "/v1/completions", {
        "model": MODEL, "prompt": f"trigger {NONCE} refill {i} done",
        "max_tokens": 1, "temperature": 0, "stream": False,
        "session_id": SESS, "rid": rid,
    })
    emit(TRANSCRIPT, {"tag": f"trigger-{i}", "rid": rid, "http": code,
                      "elapsed_s": el, "err": err})
    print("TRIGGER", i, rid, code, el, flush=True)


class Tail:
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


def main():
    os.makedirs(OUT, exist_ok=True)
    emit(STATE, {"t": round(time.time(), 3), "evt": "driver_start",
                 "start_line": START_LINE})

    # Prompt plan: T target (~27k), F1/F2 issuers (~43k), D1..D3 decoys (~43k).
    plan = {
        "T":  (f"r118-{NONCE}-tk", 0x41, 7000),
        "F1": (f"r118-{NONCE}-f1k", 0x45, 11000),
        "F2": (f"r118-{NONCE}-f2k", 0x49, 11000),
        "D1": (f"r118-{NONCE}-d1k", 0x60, 11000),
        "D2": (f"r118-{NONCE}-d2k", 0x64, 11000),
        "D3": (f"r118-{NONCE}-d3k", 0x68, 11000),
    }
    texts = {k: make_prompt(seed, kk, n) for k, (seed, kk, n) in plan.items()}

    code, resp, err, el = tokenize([texts[k] for k in ["T", "F1", "F2", "D1", "D2", "D3"]])
    emit(STATE, {"t": round(time.time(), 3), "evt": "tokenize", "http": code,
                 "elapsed_s": el, "err": err,
                 "counts": (resp or {}).get("count")})
    print("TOKENIZE", code, (resp or {}).get("count"), el, flush=True)
    if code != 200:
        emit(STATE, {"evt": "abort_tokenize", "err": err})
        return 2
    toks = resp["tokens"]
    T = toks[0]
    F1 = toks[1]
    F2 = toks[2]
    D = toks[3:6]

    SESS = f"r118-s-{NONCE}"
    build(f"r118-{NONCE}-T", T, SESS, "build-T")
    build(f"r118-{NONCE}-F1", F1, SESS, "build-F1")
    build(f"r118-{NONCE}-F2", F2, SESS, "build-F2")
    for i, ids in enumerate(D, 1):
        build(f"r118-{NONCE}-D{i}", ids, f"r118-{NONCE}-d{i}", f"build-D{i}")

    # Snapshot offsets for the replay window.
    sline = sum(1 for _ in open(SERVER_LOG, "r", encoding="utf-8", errors="replace"))
    emit(STATE, {"t": round(time.time(), 3), "evt": "replay_window_start",
                 "server_line": sline})

    # Single input_ids batch -> one scheduler message -> same frontier pass.
    batch_rids = [f"r118-{NONCE}-R-F1", f"r118-{NONCE}-R-F2", f"r118-{NONCE}-R-T"]
    result = {}

    def replay():
        result["r"] = _post(BASE + "/v1/completions", {
            "model": MODEL, "prompt": [F1, F2, T], "max_tokens": 1,
            "temperature": 0, "stream": False, "session_id": SESS,
            "rid": batch_rids,
        })

    th = threading.Thread(target=replay, daemon=True)
    th.start()
    emit(STATE, {"t": round(time.time(), 3), "evt": "batch_submitted",
                 "rids": batch_rids})
    print("BATCH_SUBMITTED", batch_rids, flush=True)

    tail = Tail(SERVER_LOG, sline)
    target = f"r118-{NONCE}-R-T"
    watch = set(batch_rids)
    seen = []
    keys = ("rh_preadmission_decision", "rh_match_prepare", "ready_stage",
            "restore_success", "restore_ready", "restore_recompute",
            "restore_host_alloc_wait", "restore_host_alloc_wake_decision",
            "prefetch_issued", "prefetch_revoke", "admission",
            "restore_retry", "restore_disposition", "restore_state",
            "restore_backup", "durability_barrier", "storage_persisted")
    deadline = time.time() + 1500
    chain = {}
    adm_seen = set()
    park_at = None
    trig_n = 0
    next_trig = 0.0
    while time.time() < deadline:
        for ln, text in tail.new_lines():
            if not any(w in text for w in watch) and "r118-" not in text:
                continue
            if not any(k in text for k in keys):
                continue
            seen.append((ln, text))
            is_adm = "evt=admission" in text
            if is_adm:
                ar = text.split("rid=", 1)[-1].split(" ", 1)[0]
                if ar in adm_seen:
                    continue
                adm_seen.add(ar)
            with open(OUT + "/watch.log", "a") as h:
                h.write(text + "\n")
            if target in text:
                for k in keys:
                    if k in text:
                        chain.setdefault(k, []).append(ln)
                if "SPEC_BUDGET" in text and "negative_cache" in text and park_at is None:
                    park_at = time.time()
                    print("TARGET_PARKED", ln, flush=True)
            if len(chain) and any(k in chain for k in ("restore_success",)):
                emit(STATE, {"t": round(time.time(), 3), "evt": "target_restore_seen",
                             "chain": chain})
        if park_at and "restore_success" not in chain and trig_n < 8 and time.time() >= next_trig:
            trig_n += 1
            next_trig = time.time() + 8
            threading.Thread(target=trigger, args=(trig_n,), daemon=True).start()
        if "restore_success" in chain and "admission" in chain:
            break
        if not th.is_alive() and "restore_success" in chain:
            break
        time.sleep(2)
    emit(STATE, {"t": round(time.time(), 3), "evt": "monitor_end",
                 "chain": chain, "watch_lines": [ln for ln, _ in seen]})
    print("MONITOR_END", json.dumps(chain), flush=True)
    if result.get("r"):
        code, resp, err, el = result["r"]
        emit(TRANSCRIPT, {"tag": "batch-replay", "rids": batch_rids,
                          "session_id": SESS, "http": code, "elapsed_s": el,
                          "usage": (resp or {}).get("usage") if isinstance(resp, dict) else None,
                          "err": err})
        print("BATCH_DONE", code, el, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
