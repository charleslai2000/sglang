#!/usr/bin/env python3
"""R120 P1 SPEC_BUDGET full-chain driver (single F1 + single T, NO decoys).

Workload (frozen R117 profile, public HTTP only):
  - F1: one full request, prefix ~43000 tokens (> speculative limit 39321),
        unique first token (R114 recipe: fresh root child -> L3 root-promote),
        session r120-s-F1, rid r120-build-F1.
  - T : one full request, prefix ~27000 tokens, unique first token,
        session r120-s-T, rid r120-build-T.
  - wait for L3 durability (storage_persisted for each build_rid).
  - replay: ONE input_ids batch prompt=[[F1],[T]], rid=[R-F1,R-T],
    session = R120_BATCH_SESS.
  - keep the batch HTTP client connected until terminal outcome; capture the
    target T lifecycle from the existing server log and /tmp/t38c-probe.log.

No product imports, no instrumentation, no synthetic events, no server control.
"""
import json, os, random, sys, threading, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:30000"
MODEL = "/mnt/data/models/qwen35-gptq"
SERVER_LOG = "/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r112.log"
PROBE_LOG = "/tmp/t38c-probe.log"
OUT = os.environ.get("R120_OUT", "/tmp/r120")
NONCE = os.environ.get("R120_NONCE", "p1")
F1_SESS = os.environ.get("R120_F1_SESS", f"r120-s-F1")
T_SESS = os.environ.get("R120_T_SESS", f"r120-s-T")
BATCH_SESS = os.environ.get("R120_BATCH_SESS", f"r120-s-R")
BUILD_F1 = f"r120-{NONCE}-build-F1"
BUILD_T = f"r120-{NONCE}-build-T"
R_F1 = f"r120-{NONCE}-R-F1"
R_T = f"r120-{NONCE}-R-T"
START_LINE = int(os.environ.get("R120_START_LINE", "0"))
PROBE_START_BYTES = int(os.environ.get("R120_PROBE_START_BYTES", "0"))
REPLAY_TIMEOUT = float(os.environ.get("R120_REPLAY_TIMEOUT", "1800"))
KEEPALIVE = float(os.environ.get("R120_KEEPALIVE", "1680"))
DUR_WAIT = float(os.environ.get("R120_DUR_WAIT", "180"))
F1_WORDS = int(os.environ.get("R120_F1_WORDS", "11000"))
T_WORDS = int(os.environ.get("R120_T_WORDS", "7000"))
F1_K = int(os.environ.get("R120_F1_K", "128"))
T_K = int(os.environ.get("R120_T_K", "144"))
SEED = os.environ.get("R120_SEED", "0") == "1"
SEED_LEN = int(os.environ.get("R120_SEED_LEN", "2000"))

WORD = "abcdefghijklmnopqrstuvwxyz"
_lock = threading.Lock()


def rw(rng):
    return "".join(rng.choice(WORD) for _ in range(rng.randint(4, 10)))


def rare_prefix(k):
    # distinct rare alchemical code points -> fresh root child (R114 recipe)
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
    code = resp = None
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
    counts = {r: 0 for r in build_rids}
    tokens = {r: 0 for r in build_rids}
    barriers = {r: 0 for r in build_rids}
    end = time.time() + deadline_s
    while time.time() < end:
        for _, text in probe_tail.new_lines():
            if '"evt": "storage_persisted"' in text:
                try:
                    d = json.loads(text)
                except Exception:
                    continue
                br = d.get("build_rid")
                if br in counts:
                    counts[br] += 1
                    tokens[br] = max(tokens[br], int(d.get("kv_completed_tokens") or 0))
            elif '"evt": "durability_barrier"' in text:
                try:
                    d = json.loads(text)
                except Exception:
                    continue
                br = d.get("build_rid")
                if br in barriers:
                    barriers[br] += 1
        if all(v > 0 for v in counts.values()):
            break
        time.sleep(2)
    return counts, tokens, barriers


def main():
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "watch.log"), "w").close()
    open(os.path.join(OUT, "requests.jsonl"), "w").close()
    open(os.path.join(OUT, "state.jsonl"), "w").close()
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "driver_start",
          "start_line": START_LINE, "probe_start_bytes": PROBE_START_BYTES,
          "f1_sess": F1_SESS, "t_sess": T_SESS, "batch_sess": BATCH_SESS,
          "build_f1": BUILD_F1, "build_t": BUILD_T, "r_f1": R_F1, "r_t": R_T})

    f1_text = make_prompt(0xB120, F1_K, F1_WORDS)
    t_text = make_prompt(0xC120, T_K, T_WORDS)

    code, resp, err, el = tokenize([f1_text, t_text])
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "tokenize", "http": code,
          "elapsed_s": el, "err": err, "counts": (resp or {}).get("count")})
    print("TOKENIZE", code, (resp or {}).get("count"), el, flush=True)
    if code != 200:
        emit(os.path.join(OUT, "state.jsonl"), {"evt": "abort_tokenize", "err": err})
        return 2
    toks = resp["tokens"]
    f1_ids, t_ids = toks[0], toks[1]
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "token_counts",
          "f1_tokens": len(f1_ids), "t_tokens": len(t_ids)})
    print("TOKENS", len(f1_ids), len(t_ids), flush=True)

    probe_tail = ByteTail(PROBE_LOG, PROBE_START_BYTES)

    # ---- Build F1 full (unique first token) ----
    if SEED:
        completion(f"r120-{NONCE}-seed-F1", f1_ids[:SEED_LEN], F1_SESS,
                   "seed-F1", timeout=600)
    completion(BUILD_F1, f1_ids, F1_SESS, "build-F1", timeout=900)

    # ---- Build T full (unique first token) ----
    if SEED:
        completion(f"r120-{NONCE}-seed-T", t_ids[:SEED_LEN], T_SESS,
                   "seed-T", timeout=600)
    completion(BUILD_T, t_ids, T_SESS, "build-T", timeout=900)

    # ---- Confirm durability of each build_rid ----
    counts, tokens, barriers = wait_persistence(
        [BUILD_F1, BUILD_T], probe_tail, DUR_WAIT)
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "durability_probe",
          "counts": counts, "max_tokens": tokens, "barriers": barriers})
    print("DURABILITY", json.dumps({"counts": counts, "tokens": tokens,
                                    "barriers": barriers}), flush=True)

    # ---- Single input_ids batch -> one frontier pass ----
    sline = server_line_count()
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "replay_window_start",
          "server_line": sline})
    print("REPLAY_WINDOW_START", sline, flush=True)

    result = {}

    def replay():
        result["r"] = _post(BASE + "/v1/completions", {
            "model": MODEL, "prompt": [f1_ids, t_ids],
            "max_tokens": 1, "temperature": 0, "stream": False,
            "session_id": BATCH_SESS, "rid": [R_F1, R_T],
        }, timeout=REPLAY_TIMEOUT)

    th = threading.Thread(target=replay, daemon=True)
    th.start()
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "batch_submitted",
          "rids": [R_F1, R_T]})
    print("BATCH_SUBMITTED", [R_F1, R_T], flush=True)

    serv = LineTail(SERVER_LOG, sline)
    watch = {R_F1, R_T, BUILD_T, BUILD_F1}
    keys = ("rh_preadmission_decision", "rh_match_prepare", "ready_stage",
            "restore_success", "restore_ready", "restore_recompute",
            "restore_host_alloc_wait", "restore_host_alloc_retry_result",
            "prefetch_issued", "prefetch_revoke", "prefetch_finalize",
            "admission", "restore_retry", "restore_disposition",
            "restore_state", "restore_backup", "ready_host", "rh_ready_host",
            "durability_barrier", "storage_persisted", "restore_hybrid_finalize",
            "ready_pool", "Prefill batch", "prefetch_io_done")
    deadline = time.time() + KEEPALIVE
    while time.time() < deadline:
        for ln, text in serv.new_lines():
            if any(k in text for k in keys) and any(w in text for w in watch):
                with open(os.path.join(OUT, "watch.log"), "a") as h:
                    h.write(f"{ln}\t{text}\n")
        for _, text in probe_tail.new_lines():
            if any(w in text for w in watch):
                with open(os.path.join(OUT, "watch.log"), "a") as h:
                    h.write(f"probe\t{text}\n")
        if not th.is_alive():
            break
        time.sleep(2)

    outcome = "still-pending"
    if "r" in result:
        code, resp, err, el = result["r"]
        rec = {"tag": "batch-replay", "rids": [R_F1, R_T],
               "session_id": BATCH_SESS, "http": code, "elapsed_s": el,
               "usage": (resp or {}).get("usage") if isinstance(resp, dict) else None,
               "err": err,
               "choices": (resp or {}).get("choices") if isinstance(resp, dict) else None}
        emit(os.path.join(OUT, "requests.jsonl"), rec)
        outcome = "completed" if code == 200 else f"http-{code}"
        print("BATCH_DONE", code, el, flush=True)
    else:
        rec = {"tag": "batch-replay", "rids": [R_F1, R_T],
               "session_id": BATCH_SESS, "http": "000",
               "elapsed_s": KEEPALIVE, "err": "client-keepalive-timeout"}
        emit(os.path.join(OUT, "requests.jsonl"), rec)
        print("BATCH_STILL_PENDING", flush=True)
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "monitor_end", "outcome": outcome,
          "still_alive": th.is_alive()})
    print("MONITOR_END", outcome, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
