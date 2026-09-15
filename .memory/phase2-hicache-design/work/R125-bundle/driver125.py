#!/usr/bin/env python3
"""R125 P1 durable-prefix replay driver (Option A).

Derived from work/R121-bundle/driver121.py (sha256 9ae5320e...cc6d) with the
minimal changes needed for the R125 contract:
  - NONCE defaults to "p3" (the nonce whose deterministic prompts reproduce
    R121's durable L3 key set; verified offline: T key_set_sha256
    73e15a5f...dcb8, kv_hit_pages 27328).  The R125 contract text says "p1";
    that is a transcription error (R124 used p1 and produced fill_len=27170 /
    negative cache; R121's durable prefix is p3, fill_len=27340).  Using p1
    would by construction fail the contract's own mandatory Gate 0.
  - T is NOT rebuilt by default (R125_BUILD_T=0): R121's durable T prefix is
    already in the L3 file backend, so replay keeps T a pure non-resident,
    durable-restore candidate (no negative cache, must be RH-issued).
  - Server log defaults to the running r124 rebuilt server; HAE / host_alloc.v1
    events are captured.

Public HTTP only (health-independent: tokenize, completions); reads the existing
server log and probe log. No product imports, no instrumentation, no server
control, no repo edits.
"""
import hashlib, json, os, random, sys, threading, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:30000"
MODEL = "/mnt/data/models/qwen35-gptq"
SERVER_LOG = os.environ.get(
    "R125_SERVER_LOG",
    "/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r124.log",
)
PROBE_LOG = os.environ.get("R125_PROBE_LOG", "/tmp/t38c-probe.log")
OUT = os.environ.get(
    "R125_OUT",
    "/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/"
    "phase2-hicache-design/work/R125-bundle",
)
NONCE = os.environ.get("R125_NONCE", "p3")
_NH = int(hashlib.sha256(NONCE.encode()).hexdigest()[:8], 16)
KOFF = _NH % 48
SEEDBASE = _NH % 100000

F1_SESS = os.environ.get("R125_F1_SESS", f"r121-s-F1-{NONCE}")
F2_SESS = os.environ.get("R125_F2_SESS", f"r121-s-F2-{NONCE}")
T_SESS = os.environ.get("R125_T_SESS", f"r121-s-T-{NONCE}")
R_SESS = os.environ.get("R125_R_SESS", f"r121-s-R-{NONCE}")

BUILD_F1 = f"r121-{NONCE}-build-F1"
BUILD_F2 = f"r121-{NONCE}-build-F2"
BUILD_T = f"r121-{NONCE}-build-T"
R_F1 = f"r121-{NONCE}-R-F1"
R_F2 = f"r121-{NONCE}-R-F2"
R_T = f"r121-{NONCE}-R-T"
QN = int(os.environ.get("R125_PRESSURE_N", "5"))
USE_F2 = os.environ.get("R125_USE_F2", "1") == "1"
BUILD_T_FLAG = os.environ.get("R125_BUILD_T", "0") == "1"
BUILD_F1_FLAG = os.environ.get("R125_BUILD_F1", "1") == "1"

START_LINE = int(os.environ.get("R125_START_LINE", "0"))
PROBE_START_BYTES = int(os.environ.get("R125_PROBE_START_BYTES", "0"))
REPLAY_TIMEOUT = float(os.environ.get("R125_REPLAY_TIMEOUT", "600"))
KEEPALIVE = float(os.environ.get("R125_KEEPALIVE", "420"))
F1_WORDS = int(os.environ.get("R125_F1_WORDS", "11000"))
T_WORDS = int(os.environ.get("R125_T_WORDS", "7000"))
Q_WORDS = int(os.environ.get("R125_Q_WORDS", "11000"))
F1_K = int(os.environ.get("R125_F1_K", str(160 + KOFF)))
F2_K = int(os.environ.get("R125_F2_K", str(200 + KOFF)))
T_K = int(os.environ.get("R125_T_K", str(240 + KOFF)))
Q_K = int(os.environ.get("R125_Q_K", str(280 + KOFF)))
DUR_WAIT = float(os.environ.get("R125_DUR_WAIT", "20"))
DRAIN_SETTLE = float(os.environ.get("R125_DRAIN_SETTLE", "60"))
DRAIN_DEADLINE = float(os.environ.get("R125_DRAIN_DEADLINE", "300"))
PREWINDOW_SETTLE = float(os.environ.get("R125_PREWINDOW_SETTLE", "15"))
TRIGGERS = int(os.environ.get("R125_TRIGGERS", "4"))

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


def completion(rid, prompt, session, tag, max_tokens=1, timeout=900):
    code, resp, err, el = _post(BASE + "/v1/completions", {
        "model": MODEL, "prompt": prompt, "max_tokens": max_tokens,
        "temperature": 0, "stream": False,
        "session_id": session, "rid": rid,
    }, timeout=timeout)
    rec = {"tag": tag, "rid": rid, "session_id": session, "http": code,
           "elapsed_s": el, "err": err,
           "usage": (resp or {}).get("usage") if isinstance(resp, dict) else None,
           "ts": round(time.time(), 3)}
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


def wait_durability(probe_tail, ids_watch, deadline_s):
    seen = {k: {"persisted": 0, "barrier": 0, "completed": 0, "mamba_ok": 0}
            for k in ids_watch}
    watch_ids = set(ids_watch.values())
    end = time.time() + deadline_s
    while time.time() < end:
        for _, text in probe_tail.new_lines():
            with open(os.path.join(OUT, "probe.log"), "a") as h:
                h.write(text + "\n")
            if not any(w in text for w in watch_ids):
                continue
            try:
                d = json.loads(text)
            except Exception:
                continue
            ev = d.get("evt")
            sid = d.get("session_id")
            key = None
            for k, s in ids_watch.items():
                if sid == s:
                    key = k
                    break
            if key is None:
                continue
            if ev == "storage_persisted":
                seen[key]["persisted"] += 1
                seen[key]["completed"] = max(seen[key]["completed"],
                                             int(d.get("kv_completed_tokens") or 0))
                if d.get("mamba_durable"):
                    seen[key]["mamba_ok"] += 1
            elif ev == "durability_barrier":
                seen[key]["barrier"] += 1
                if d.get("mamba_durable"):
                    seen[key]["mamba_ok"] += 1
        if all(v["barrier"] > 0 for v in seen.values()):
            break
        time.sleep(2)
    return seen


def wait_idle(serv, settle_s):
    last_activity = time.time()
    idle_seen = False
    printed = False
    deadline = time.time() + DRAIN_DEADLINE
    while time.time() < deadline:
        got = serv.new_lines()
        for ln, text in got:
            with open(os.path.join(OUT, "server-capture.log"), "a") as h:
                h.write(f"{ln}\t{text}\n")
            is_health = "HEALTH_CHECK" in text
            if ("evt=admission" in text or "admission.v2" in text) and not is_health:
                last_activity = time.time()
            if "Prefill batch" in text and "#running-req: 0" in text \
                    and "#queue-req: 0" in text and "#pending-token: 0" in text:
                idle_seen = True
        if idle_seen and (time.time() - last_activity) >= settle_s:
            if not printed:
                print("DRAINED", round(time.time() - last_activity, 1), flush=True)
                printed = True
            return True
        time.sleep(2)
    return False


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in ("requests.jsonl", "state.jsonl", "server-capture.log",
              "probe.log", "watch.log"):
        open(os.path.join(OUT, f), "w").close()
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "driver_start",
          "start_line": START_LINE, "probe_start_bytes": PROBE_START_BYTES,
          "nonce": NONCE, "koff": KOFF, "seedbase": SEEDBASE,
          "f1_sess": F1_SESS, "t_sess": T_SESS,
          "r_sess": R_SESS, "build_f1": BUILD_F1, "build_t": BUILD_T,
          "r_f1": R_F1, "r_t": R_T, "pressure_n": QN,
          "use_f2": USE_F2, "build_t_flag": BUILD_T_FLAG,
          "build_f1_flag": BUILD_F1_FLAG})

    f1_text = make_prompt(SEEDBASE + 0xB121, F1_K, F1_WORDS)
    f2_text = make_prompt(SEEDBASE + 0xE121, F2_K, F1_WORDS)
    t_text = make_prompt(SEEDBASE + 0xC121, T_K, T_WORDS)
    q_texts = {f"q{i}": make_prompt(SEEDBASE + 0xD000 + i, Q_K + i * 3, Q_WORDS)
               for i in range(1, QN + 1)}
    plan = ([f1_text] + ([f2_text] if USE_F2 else []) + [t_text]
            + [q_texts[f"q{i}"] for i in range(1, QN + 1)])

    code, resp, err, el = tokenize(plan)
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "tokenize", "http": code,
          "elapsed_s": el, "err": err, "counts": (resp or {}).get("count")})
    print("TOKENIZE", code, (resp or {}).get("count"), el, flush=True)
    if code != 200:
        emit(os.path.join(OUT, "state.jsonl"), {"evt": "abort_tokenize", "err": err})
        return 2
    toks = resp["tokens"]
    idx = 0
    f1_ids = toks[idx]; idx += 1
    f2_ids = None
    if USE_F2:
        f2_ids = toks[idx]; idx += 1
    t_ids = toks[idx]; idx += 1
    q_ids = {f"q{i}": toks[idx + i - 1] for i in range(1, QN + 1)}
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "token_counts",
          "f1_tokens": len(f1_ids), "t_tokens": len(t_ids),
          "q_tokens": {k: len(v) for k, v in q_ids.items()}})
    print("TOKENS", len(f1_ids), len(t_ids),
          {k: len(v) for k, v in q_ids.items()}, flush=True)

    # ---- Phase 1: seed device/host (F1/F2); T is left untouched (durable L3) ----
    if BUILD_F1_FLAG:
        completion(BUILD_F1, f1_ids, F1_SESS, "build-F1", timeout=900)
    if USE_F2:
        completion(BUILD_F2, f2_ids, F2_SESS, "build-F2", timeout=900)
    if BUILD_T_FLAG:
        completion(BUILD_T, t_ids, T_SESS, "build-T", timeout=900)

    probe_tail = ByteTail(PROBE_LOG, PROBE_START_BYTES)
    ids_watch = {}
    if BUILD_F1_FLAG:
        ids_watch["F1"] = F1_SESS
    if USE_F2:
        ids_watch["F2"] = F2_SESS
    if BUILD_T_FLAG:
        ids_watch["T"] = T_SESS
    dur = wait_durability(probe_tail, ids_watch, DUR_WAIT) if ids_watch else {}
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "build_durability", "seen": dur})
    print("BUILD_DURABILITY", json.dumps(dur), flush=True)

    # ---- Phase 2: controlled pressure (preprocessing only) ----
    for i in range(1, QN + 1):
        completion(f"r121-{NONCE}-q{i}", q_ids[f"q{i}"], f"r121-s-q{i}-{NONCE}",
                   f"pressure-q{i}", timeout=900)
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "pressure_done", "n": QN})
    print("PRESSURE_DONE", QN, flush=True)

    for _, text in probe_tail.new_lines():
        with open(os.path.join(OUT, "probe.log"), "a") as h:
            h.write(text + "\n")

    # ---- Phase 3: drain pressure completely, then settle ----
    sline = server_line_count()
    serv = LineTail(SERVER_LOG, sline)
    drained = wait_idle(serv, DRAIN_SETTLE)
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "drain", "drained": drained,
          "settle_s": DRAIN_SETTLE})
    print("DRAIN", drained, flush=True)
    # Extra fixed quiescence before opening the window so the measured window
    # does not race residual pressure write-back/cleanup.
    time.sleep(PREWINDOW_SETTLE)

    # ---- Phase 4: measurement window ----
    sline = server_line_count()
    pbytes = os.path.getsize(PROBE_LOG)
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "replay_window_start",
          "server_line": sline, "probe_bytes": pbytes})
    print("REPLAY_WINDOW_START", sline, pbytes, flush=True)

    result = {}

    replay_rids = [R_F1] + ([R_F2] if USE_F2 else []) + [R_T]
    replay_prompts = [f1_ids] + ([f2_ids] if USE_F2 else []) + [t_ids]
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "batch_plan",
          "rids": replay_rids})

    def replay():
        result["r"] = _post(BASE + "/v1/completions", {
            "model": MODEL, "prompt": replay_prompts,
            "max_tokens": 1, "temperature": 0, "stream": False,
            "session_id": R_SESS, "rid": replay_rids,
        }, timeout=REPLAY_TIMEOUT)

    th = threading.Thread(target=replay, daemon=True)
    th.start()
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "batch_submitted", "rids": replay_rids})
    print("BATCH_SUBMITTED", replay_rids, flush=True)

    serv = LineTail(SERVER_LOG, sline)
    ptail = ByteTail(PROBE_LOG, pbytes)
    watch = set(replay_rids) | {BUILD_T, BUILD_F1, F1_SESS, T_SESS, NONCE}
    if USE_F2:
        watch |= {BUILD_F2, F2_SESS}
    keys = ("rh_preadmission_decision", "rh_match_prepare", "ready_stage",
            "restore_success", "restore_ready", "restore_recompute",
            "restore_host_alloc_wait", "restore_host_alloc_retry_result",
            "restore_host_alloc_wake_decision", "restore_host_alloc_state",
            "prefetch_issued", "prefetch_revoke", "prefetch_finalize",
            "admission", "restore_retry", "restore_disposition",
            "restore_state", "restore_backup", "ready_host", "rh_ready_host",
            "durability_barrier", "storage_persisted", "restore_hybrid_finalize",
            "ready_pool", "Prefill batch", "prefetch_io_done",
            "promotion_reserve", "promotion_transfer")
    probe_keys = ("pc_storage_query", "pc_outcome", "pc_l3_host", "pc_get",
                  "storage_persisted", "durability_barrier", "residency_detach",
                  "residency_release_enqueued", "residency_free_complete",
                  "build_complete", "backup_host_commit", "restore_hybrid_finalize")
    chain = {}
    park_at = None
    trig_n = 0
    next_trig = 0.0
    deadline = time.time() + KEEPALIVE
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
        for _, text in ptail.new_lines():
            with open(os.path.join(OUT, "probe.log"), "a") as h:
                h.write(text + "\n")
            if any(k in text for k in probe_keys) and any(w in text for w in watch):
                with open(os.path.join(OUT, "watch.log"), "a") as h:
                    h.write(f"P\t{text}\n")
                for k in probe_keys:
                    if k in text:
                        chain.setdefault("probe:" + k, []).append("probe")
        if park_at and trig_n < TRIGGERS and time.time() >= next_trig:
            if not any(k in chain for k in ("restore_success", "restore_ready")):
                trig_n += 1
                next_trig = time.time() + 20
                rid = f"r121-{NONCE}-trig-{trig_n}"
                threading.Thread(
                    target=completion,
                    args=(rid, f"trigger {NONCE} refill {trig_n} done", R_SESS,
                          f"trigger-{trig_n}"),
                    kwargs={"timeout": 300}, daemon=True).start()
        if not th.is_alive():
            break
        time.sleep(2)
    time.sleep(1)

    outcome = "still-pending"
    if "r" in result:
        code, resp, err, el = result["r"]
        rec = {"tag": "batch-replay", "rids": replay_rids, "session_id": R_SESS,
               "http": code, "elapsed_s": el,
               "usage": (resp or {}).get("usage") if isinstance(resp, dict) else None,
               "err": err,
               "choices": (resp or {}).get("choices") if isinstance(resp, dict) else None,
               "ts": round(time.time(), 3)}
        emit(os.path.join(OUT, "requests.jsonl"), rec)
        outcome = "completed" if code == 200 else f"http-{code}"
        print("BATCH_DONE", code, el, flush=True)
    else:
        rec = {"tag": "batch-replay", "rids": replay_rids, "session_id": R_SESS,
               "http": "000", "elapsed_s": KEEPALIVE,
               "err": "client-keepalive-timeout"}
        emit(os.path.join(OUT, "requests.jsonl"), rec)
        print("BATCH_STILL_PENDING", flush=True)
    end_line = server_line_count()
    emit(os.path.join(OUT, "state.jsonl"),
         {"t": round(time.time(), 3), "evt": "monitor_end", "outcome": outcome,
          "still_alive": th.is_alive(), "end_line": end_line, "chain": chain})
    print("MONITOR_END", outcome, "end_line", end_line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
