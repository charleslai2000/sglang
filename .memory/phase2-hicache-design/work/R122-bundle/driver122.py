#!/usr/bin/env python3
"""R122 P1 controlled-eviction driver with an ENFORCED host-headroom drain gate.

Frozen contract: P1-R121-CONTROLLED-EVICTION-CONTRACT.md
  sha256 2ac86b5a54264fad46d049e2c32e3cc37c125f8c778a38dfb14e840a37be3b3b

Design (R121 recipe + mandatory drain gate):
  1. Build F1 (~41.5k tokens, > speculative limit 39321) and T (~24k tokens)
     with DISTINCT sessions and unique first tokens.
  2. Confirm build-side durable barriers exist.
  3. Apply CONTROLLED PRESSURE whose only purpose is to evict F1/T from GPU
     L1/L2 into L3. Pressure carries NO session id so its host pages become
     evictable instead of session-locked.
  4. DRAIN all pressure (terminal HTTP + idle server + no HOST_ALLOC waiter).
  5. FAIL-FAST GATE: poll read-only host headroom until
       free_units.kv + evictable_units.kv >= max_stage_required + margin
     is proven from published telemetry. If not met within the bounded
     attempts, STOP and return NOT_VERIFIED -- never open the window on a
     saturated host.
  6. Open the measurement window: ONE input_ids batch prompt=[[F1],[T]].

Public HTTP only (health, tokenize, completions); reads existing server and
probe logs. No product imports, no instrumentation, no synthetic events, no
server control, no repo edits.
"""
import hashlib, json, os, random, sys, threading, time, urllib.request, urllib.error

BASE = "http://127.0.0.1:30000"
MODEL = "/mnt/data/models/qwen35-gptq"
SERVER_LOG = "/mnt/data/neuron/sglang-3090-r112-20260911/sglang-server-r112.log"
PROBE_LOG = "/tmp/t38c-probe.log"
OUT = os.environ.get(
    "R122_OUT",
    "/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/.memory/"
    "phase2-hicache-design/work/R122-bundle",
)
NONCE = os.environ.get("R122_NONCE", "r122")
_NH = int(hashlib.sha256(NONCE.encode()).hexdigest()[:8], 16)
KOFF = _NH % 48
SEEDBASE = _NH % 100000

F1_SESS = os.environ.get("R122_F1_SESS", f"r122-s-F1-{NONCE}")
T_SESS = os.environ.get("R122_T_SESS", f"r122-s-T-{NONCE}")
R_SESS = os.environ.get("R122_R_SESS", f"r122-s-R-{NONCE}")

BUILD_F1 = f"r122-{NONCE}-build-F1"
BUILD_T = f"r122-{NONCE}-build-T"
R_F1 = f"r122-{NONCE}-R-F1"
R_T = f"r122-{NONCE}-R-T"

QN = int(os.environ.get("R122_PRESSURE_N", "4"))
Q_SESSION = os.environ.get("R122_Q_SESSION", "0") == "1"

START_LINE = int(os.environ.get("R122_START_LINE", "0"))
PROBE_START_BYTES = int(os.environ.get("R122_PROBE_START_BYTES", "0"))
REPLAY_TIMEOUT = float(os.environ.get("R122_REPLAY_TIMEOUT", "900"))
KEEPALIVE = float(os.environ.get("R122_KEEPALIVE", "700"))
F1_WORDS = int(os.environ.get("R122_F1_WORDS", "10650"))
T_WORDS = int(os.environ.get("R122_T_WORDS", "6150"))
Q_WORDS = int(os.environ.get("R122_Q_WORDS", "11000"))
F1_K = int(os.environ.get("R122_F1_K", str(160 + KOFF)))
T_K = int(os.environ.get("R122_T_K", str(240 + KOFF)))
Q_K = int(os.environ.get("R122_Q_K", str(280 + KOFF)))
DUR_WAIT = float(os.environ.get("R122_DUR_WAIT", "180"))
DRAIN_SETTLE = float(os.environ.get("R122_DRAIN_SETTLE", "60"))
TRIGGERS = int(os.environ.get("R122_TRIGGERS", "3"))

# --- mandatory drain gate ---
GATE_MARGIN = int(os.environ.get("R122_GATE_MARGIN", "2048"))
GATE_MAX_ATTEMPTS = int(os.environ.get("R122_GATE_MAX_ATTEMPTS", "24"))
GATE_INTERVAL = float(os.environ.get("R122_GATE_INTERVAL", "15"))
GATE_MIN_FREE = int(os.environ.get("R122_GATE_MIN_FREE", "0"))

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
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
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


def _get(url, timeout=30):
    req = urllib.request.Request(url)
    t0 = time.time()
    code = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception:
        code = "000"
    return code, round(time.time() - t0, 3)


def tokenize(texts):
    return _post(BASE + "/v1/tokenize", {"model": MODEL, "prompt": texts})


def completion(rid, prompt, session, tag, max_tokens=1, timeout=900):
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
        "rid": rid,
    }
    if session is not None:
        payload["session_id"] = session
    code, resp, err, el = _post(BASE + "/v1/completions", payload, timeout=timeout)
    rec = {
        "tag": tag,
        "rid": rid,
        "session_id": session,
        "http": code,
        "elapsed_s": el,
        "err": err,
        "usage": (resp or {}).get("usage") if isinstance(resp, dict) else None,
        "ts": round(time.time(), 3),
    }
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


def _count_lines(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except FileNotFoundError:
        return 0


def server_line_count():
    return _count_lines(SERVER_LOG)


def wait_durability(probe_tail, ids_watch, deadline_s):
    seen = {
        k: {"persisted": 0, "barrier": 0, "completed": 0, "mamba_ok": 0}
        for k in ids_watch
    }
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
                seen[key]["completed"] = max(
                    seen[key]["completed"], int(d.get("kv_completed_tokens") or 0)
                )
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
    deadline = time.time() + 240
    while time.time() < deadline:
        got = serv.new_lines()
        for ln, text in got:
            with open(os.path.join(OUT, "server-capture.log"), "a") as h:
                h.write(f"{ln}\t{text}\n")
            is_health = "HEALTH_CHECK" in text
            if "evt=admission" in text and not is_health:
                last_activity = time.time()
            if (
                "Prefill batch" in text
                and "#running-req: 0" in text
                and "#queue-req: 0" in text
                and "#pending-token: 0" in text
            ):
                idle_seen = True
        if idle_seen and (time.time() - last_activity) >= settle_s:
            if not printed:
                print("DRAINED", round(time.time() - last_activity, 1), flush=True)
                printed = True
            return True
        time.sleep(2)
    return False


def _parse_host_headroom(text):
    i = text.find("host_headroom=")
    if i < 0:
        return None
    j = i + len("host_headroom=")
    k = j
    while k < len(text) and text[k].isdigit():
        k += 1
    return int(text[j:k]) if k > j else None


def _parse_kv_evictable_change(text):
    if '"evt": "host_allocability_change"' not in text:
        return None
    try:
        d = json.loads(text.split("[HAE] ", 1)[1])
    except Exception:
        return None
    if d.get("pool") != "kv":
        return None
    return {
        "evictable_after": d.get("evictable_after"),
        "evictable_before": d.get("evictable_before"),
        "returned_units": d.get("returned_units"),
        "cause": d.get("cause"),
        "ts_wall_ms": d.get("ts_wall_ms"),
    }


def _parse_alloc_snapshot(text):
    """free/evictable from a host_alloc.v1 wait or wake decision line."""
    for evt in ("restore_host_alloc_wait", "restore_host_alloc_wake_decision",
                "restore_host_alloc_retry_result"):
        if f'"evt": "{evt}"' not in text:
            continue
        try:
            d = json.loads(text.split("[HAE] ", 1)[1])
        except Exception:
            return None
        fu = d.get("free_units") or {}
        ev = d.get("evictable_units") or {}
        return {
            "evt": evt,
            "rid": d.get("rid"),
            "free_kv": fu.get("kv"),
            "evictable_kv": ev.get("kv"),
            "requested": d.get("requested_primary_tokens"),
            "decision": d.get("decision"),
            "ts_wall_ms": d.get("ts_wall_ms"),
        }
    return None


def main():
    os.makedirs(OUT, exist_ok=True)
    for f in ("requests.jsonl", "state.jsonl", "server-capture.log",
              "probe.log", "watch.log", "gate_evidence.jsonl"):
        open(os.path.join(OUT, f), "w").close()
    emit(
        os.path.join(OUT, "state.jsonl"),
        {
            "t": round(time.time(), 3),
            "evt": "driver_start",
            "start_line": START_LINE,
            "probe_start_bytes": PROBE_START_BYTES,
            "nonce": NONCE,
            "f1_sess": F1_SESS,
            "t_sess": T_SESS,
            "r_sess": R_SESS,
            "build_f1": BUILD_F1,
            "build_t": BUILD_T,
            "r_f1": R_F1,
            "r_t": R_T,
            "pressure_n": QN,
            "pressure_session": Q_SESSION,
            "gate_margin": GATE_MARGIN,
            "gate_max_attempts": GATE_MAX_ATTEMPTS,
        },
    )

    f1_text = make_prompt(SEEDBASE + 0xB122, F1_K, F1_WORDS)
    t_text = make_prompt(SEEDBASE + 0xC122, T_K, T_WORDS)
    q_texts = {
        f"q{i}": make_prompt(SEEDBASE + 0xD000 + i, Q_K + i * 3, Q_WORDS)
        for i in range(1, QN + 1)
    }
    plan = [f1_text, t_text] + [q_texts[f"q{i}"] for i in range(1, QN + 1)]

    code, resp, err, el = tokenize(plan)
    emit(
        os.path.join(OUT, "state.jsonl"),
        {
            "t": round(time.time(), 3),
            "evt": "tokenize",
            "http": code,
            "elapsed_s": el,
            "err": err,
            "counts": (resp or {}).get("count"),
        },
    )
    print("TOKENIZE", code, (resp or {}).get("count"), el, flush=True)
    if code != 200:
        emit(os.path.join(OUT, "state.jsonl"), {"evt": "abort_tokenize", "err": err})
        return 2
    toks = resp["tokens"]
    f1_ids = toks[0]
    t_ids = toks[1]
    q_ids = {f"q{i}": toks[1 + i] for i in range(1, QN + 1)}
    emit(
        os.path.join(OUT, "state.jsonl"),
        {
            "t": round(time.time(), 3),
            "evt": "token_counts",
            "f1_tokens": len(f1_ids),
            "t_tokens": len(t_ids),
            "q_tokens": {k: len(v) for k, v in q_ids.items()},
        },
    )
    print(
        "TOKENS",
        len(f1_ids),
        len(t_ids),
        {k: len(v) for k, v in q_ids.items()},
        flush=True,
    )

    # ---- Phase 1: build F1 and T full, distinct sessions, unique first token ----
    completion(BUILD_F1, f1_ids, F1_SESS, "build-F1", timeout=900)
    completion(BUILD_T, t_ids, T_SESS, "build-T", timeout=900)

    probe_tail = ByteTail(PROBE_LOG, PROBE_START_BYTES)
    ids_watch = {"F1": F1_SESS, "T": T_SESS}
    dur = wait_durability(probe_tail, ids_watch, DUR_WAIT)
    emit(
        os.path.join(OUT, "state.jsonl"),
        {"t": round(time.time(), 3), "evt": "build_durability", "seen": dur},
    )
    print("BUILD_DURABILITY", json.dumps(dur), flush=True)
    f1_req = int(dur["F1"].get("completed") or 0) or (len(f1_ids) - 15)
    t_req = int(dur["T"].get("completed") or 0) or (len(t_ids) - 12)

    # ---- Phase 2: CONTROLLED PRESSURE (preprocessing only; evict from L1/L2) ----
    for i in range(1, QN + 1):
        qsession = f"r122-s-q{i}-{NONCE}" if Q_SESSION else None
        completion(
            f"r122-{NONCE}-q{i}",
            q_ids[f"q{i}"],
            qsession,
            f"pressure-q{i}",
            timeout=900,
        )
    emit(
        os.path.join(OUT, "state.jsonl"),
        {"t": round(time.time(), 3), "evt": "pressure_done", "n": QN},
    )
    print("PRESSURE_DONE", QN, flush=True)

    for _, text in probe_tail.new_lines():
        with open(os.path.join(OUT, "probe.log"), "a") as h:
            h.write(text + "\n")

    # ---- Phase 3: DRAIN pressure completely, then settle ----
    sline = server_line_count()
    serv = LineTail(SERVER_LOG, sline)
    drained = wait_idle(serv, DRAIN_SETTLE)
    emit(
        os.path.join(OUT, "state.jsonl"),
        {
            "t": round(time.time(), 3),
            "evt": "drain",
            "drained": drained,
            "settle_s": DRAIN_SETTLE,
        },
    )
    print("DRAIN", drained, flush=True)
    time.sleep(5)

    # ---- Phase 4: MANDATORY FAIL-FAST DRAIN GATE (read-only) ----
    gate_tail = LineTail(SERVER_LOG, server_line_count())
    last_evictable = None
    last_evictable_ref = None
    last_evictable_ts = 0
    last_alloc_snapshot = None
    alloc_snapshot_ref = None
    last_alloc_snapshot_ts = 0
    pressure_admissions_after_drain = 0
    gate = {
        "achieved": False,
        "gap_required": None,
        "gap_margin": GATE_MARGIN,
        "attempts": 0,
        "polls": [],
    }
    # peak single-stage reservation (sequential chain fallback per task ruling)
    peak_stage = max(f1_req, t_req)
    gate_required = peak_stage + GATE_MARGIN

    for attempt in range(1, GATE_MAX_ATTEMPTS + 1):
        gate["attempts"] = attempt
        # fresh health -> published host free (host_headroom)
        hcode, hel = _get(BASE + "/health", timeout=20)
        time.sleep(1.0)
        free = None
        free_ref = None
        health_ref = None
        new = gate_tail.new_lines()
        for ln, text in new:
            if "HEALTH_CHECK" in text:
                health_ref = ln
                hh = _parse_host_headroom(text)
                if hh is not None:
                    free = hh
                    free_ref = ln
            ev = _parse_kv_evictable_change(text)
            if ev is not None:
                last_evictable = ev["evictable_after"]
                last_evictable_ref = ln
                last_evictable_ts = ev.get("ts_wall_ms") or 0
            snap = _parse_alloc_snapshot(text)
            if snap is not None:
                last_alloc_snapshot = snap
                alloc_snapshot_ref = ln
                last_alloc_snapshot_ts = snap.get("ts_wall_ms") or 0
            if "evt=admission" in text and "HEALTH_CHECK" not in text:
                pressure_admissions_after_drain += 1

        # Prefer the freshest published host evictable: either an
        # host_allocability_change event or a host_alloc.v1 snapshot.
        if (
            last_alloc_snapshot
            and last_alloc_snapshot.get("evictable_kv") is not None
            and last_alloc_snapshot_ts >= last_evictable_ts
        ):
            last_evictable = last_alloc_snapshot["evictable_kv"]
            last_evictable_ref = alloc_snapshot_ref

        allocable = None
        if free is not None and last_evictable is not None:
            allocable = free + last_evictable
        ok = allocable is not None and allocable >= gate_required
        poll = {
            "attempt": attempt,
            "t": round(time.time(), 3),
            "http": hcode,
            "health_elapsed_s": hel,
            "host_free": free,
            "host_free_ref": free_ref,
            "health_ref": health_ref,
            "host_evictable": last_evictable,
            "host_evictable_ref": last_evictable_ref,
            "host_allocable": allocable,
            "gate_required": gate_required,
            "peak_stage_required": peak_stage,
            "margin": GATE_MARGIN,
            "ok": ok,
            "pressure_admissions_after_drain": pressure_admissions_after_drain,
        }
        gate["polls"].append(poll)
        emit(os.path.join(OUT, "gate_evidence.jsonl"), poll)
        print(
            "GATE",
            attempt,
            "free=",
            free,
            "evictable=",
            last_evictable,
            "allocable=",
            allocable,
            "required=",
            gate_required,
            "OK=",
            ok,
            flush=True,
        )
        if ok and pressure_admissions_after_drain == 0:
            gate["achieved"] = True
            gate["free"] = free
            gate["free_ref"] = free_ref
            gate["evictable"] = last_evictable
            gate["evictable_ref"] = last_evictable_ref
            gate["allocable"] = allocable
            gate["required"] = gate_required
            gate["required_with_sum"] = f1_req + t_req + GATE_MARGIN
            break
        time.sleep(GATE_INTERVAL)

    emit(
        os.path.join(OUT, "state.jsonl"),
        {"t": round(time.time(), 3), "evt": "gate_result",
         "achieved": gate["achieved"], "required": gate.get("required"),
         "allocable": gate.get("allocable"),
         "attempts": gate["attempts"]},
    )
    if not gate["achieved"]:
        print("GATE_FAILED", json.dumps(gate["polls"][-1]), flush=True)
        emit(
            os.path.join(OUT, "state.jsonl"),
            {
                "t": round(time.time(), 3),
                "evt": "abort_gate",
                "reason": "host headroom precondition not met within bounded attempts",
                "last_poll": gate["polls"][-1],
            },
        )
        return 3

    # ---- Phase 5: open the measurement window ----
    sline = server_line_count()
    pbytes = os.path.getsize(PROBE_LOG)
    emit(
        os.path.join(OUT, "state.jsonl"),
        {
            "t": round(time.time(), 3),
            "evt": "replay_window_start",
            "server_line": sline,
            "probe_bytes": pbytes,
            "gate": {
                "free": gate.get("free"),
                "free_ref": gate.get("free_ref"),
                "evictable": gate.get("evictable"),
                "evictable_ref": gate.get("evictable_ref"),
                "allocable": gate.get("allocable"),
                "required": gate.get("required"),
                "margin": GATE_MARGIN,
            },
        },
    )
    print("REPLAY_WINDOW_START", sline, pbytes, flush=True)

    result = {}
    replay_rids = [R_F1, R_T]
    replay_prompts = [f1_ids, t_ids]
    emit(
        os.path.join(OUT, "state.jsonl"),
        {"t": round(time.time(), 3), "evt": "batch_plan", "rids": replay_rids},
    )

    def replay():
        result["r"] = _post(
            BASE + "/v1/completions",
            {
                "model": MODEL,
                "prompt": replay_prompts,
                "max_tokens": 1,
                "temperature": 0,
                "stream": False,
                "session_id": R_SESS,
                "rid": replay_rids,
            },
            timeout=REPLAY_TIMEOUT,
        )

    th = threading.Thread(target=replay, daemon=True)
    th.start()
    emit(
        os.path.join(OUT, "state.jsonl"),
        {"t": round(time.time(), 3), "evt": "batch_submitted", "rids": replay_rids},
    )
    print("BATCH_SUBMITTED", replay_rids, flush=True)

    serv = LineTail(SERVER_LOG, sline)
    ptail = ByteTail(PROBE_LOG, pbytes)
    watch = set(replay_rids) | {BUILD_T, BUILD_F1, F1_SESS, T_SESS, NONCE}
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
                if R_T in text and (
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
        if park_at and trig_n < TRIGGERS and time.time() >= next_trig:
            if not any(k in chain for k in ("restore_success", "restore_ready")):
                trig_n += 1
                next_trig = time.time() + 25
                rid = f"r122-{NONCE}-trig-{trig_n}"
                threading.Thread(
                    target=completion,
                    args=(
                        rid,
                        f"trigger {NONCE} refill {trig_n} done",
                        R_SESS,
                        f"trigger-{trig_n}",
                    ),
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
        code, resp, err, el = result["r"]
        rec = {
            "tag": "batch-replay",
            "rids": replay_rids,
            "session_id": R_SESS,
            "http": code,
            "elapsed_s": el,
            "usage": (resp or {}).get("usage") if isinstance(resp, dict) else None,
            "err": err,
            "choices": (resp or {}).get("choices") if isinstance(resp, dict) else None,
            "ts": round(time.time(), 3),
        }
        emit(os.path.join(OUT, "requests.jsonl"), rec)
        outcome = "completed" if code == 200 else f"http-{code}"
        print("BATCH_DONE", code, el, flush=True)
    else:
        rec = {
            "tag": "batch-replay",
            "rids": replay_rids,
            "session_id": R_SESS,
            "http": "000",
            "elapsed_s": KEEPALIVE,
            "err": "client-keepalive-timeout",
        }
        emit(os.path.join(OUT, "requests.jsonl"), rec)
        print("BATCH_STILL_PENDING", flush=True)
    emit(
        os.path.join(OUT, "state.jsonl"),
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
