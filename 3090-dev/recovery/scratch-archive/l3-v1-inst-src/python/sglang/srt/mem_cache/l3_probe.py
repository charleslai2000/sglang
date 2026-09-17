"""Aggregate-only low-overhead L3 CPU-gate probe (task l3-v1-cpu-gate-instrumentation-20260916).

Enabled only when L3_INST_PROBE=1.  This module is imported by the throwaway
instrumented copy of the source tree only; it is never imported by the frozen
v1 tree.

Design constraints (per the task):
  * counters and elapsed-time accumulators only
  * no per-event logging, no per-request tracing, no syscall interception
  * must never raise into the engine path

A daemon thread snapshots the whole counter set to L3_INST_PROBE_OUT (jsonl)
once per second, so a run gets a wall-clock timeline that can be sliced to the
write-back window afterwards.
"""
from __future__ import annotations

import json
import os
import threading
import time

_ENABLED = os.environ.get("L3_INST_PROBE", "0") == "1"
_OUT = os.environ.get("L3_INST_PROBE_OUT", "/tmp/l3-inst-probe.jsonl")
_INTERVAL = float(os.environ.get("L3_INST_PROBE_INTERVAL", "1.0"))

_lock = threading.Lock()
_stats: dict = {}

# scheduler-loop stall accumulators (single-writer: the scheduler thread)
_loop_last = None
_loop_n = 0
_loop_total = 0.0
_loop_max = 0.0
_loop_max_thread = None

_thread = None


def enabled() -> bool:
    return _ENABLED


def _blank() -> dict:
    return {
        "n": 0,
        "total": 0.0,
        "max": 0.0,
        "max_ctx": None,
        "iters": 0,
        "threads": {},
        "threads_total": {},
    }


def record(name: str, dt: float = 0.0, count_inc: int = 1, extra=None) -> None:
    """Accumulate one timed entry for `name`."""
    if not _ENABLED:
        return
    try:
        tname = threading.current_thread().name
        with _lock:
            s = _stats.get(name)
            if s is None:
                s = _blank()
                _stats[name] = s
            s["n"] += 1
            if count_inc and count_inc > 0:
                s["iters"] += count_inc
            s["total"] += dt
            s["threads"][tname] = s["threads"].get(tname, 0) + 1
            s["threads_total"][tname] = s["threads_total"].get(tname, 0.0) + dt
            if dt > s["max"]:
                s["max"] = dt
                s["max_ctx"] = {"thread": tname, "extra": extra}
    except Exception:
        pass


def observe(name: str, value: float, extra=None) -> None:
    """Record a max-only observation (e.g. a queue depth); no time contribution."""
    if not _ENABLED:
        return
    try:
        tname = threading.current_thread().name
        with _lock:
            s = _stats.get(name)
            if s is None:
                s = _blank()
                _stats[name] = s
            s["n"] += 1
            s["threads"][tname] = s["threads"].get(tname, 0) + 1
            if value > s["max"]:
                s["max"] = value
                s["max_ctx"] = {"thread": tname, "extra": extra}
    except Exception:
        pass


def loop_tick() -> None:
    """Scheduler-loop iteration boundary.

    Records the gap (stall) since the previous tick.  Called once per scheduler
    loop iteration; the caller is the scheduler thread.
    """
    if not _ENABLED:
        return
    global _loop_last, _loop_n, _loop_total, _loop_max, _loop_max_thread
    try:
        now = time.perf_counter()
        if _loop_last is not None:
            gap = now - _loop_last
            _loop_n += 1
            _loop_total += gap
            if gap > _loop_max:
                _loop_max = gap
                _loop_max_thread = threading.current_thread().name
        _loop_last = now
    except Exception:
        pass


def snapshot() -> dict:
    with _lock:
        out = {
            k: {
                "n": v["n"],
                "total": v["total"],
                "max": v["max"],
                "max_ctx": v["max_ctx"],
                "iters": v["iters"],
                "threads": dict(v["threads"]),
                "threads_total": dict(v["threads_total"]),
            }
            for k, v in _stats.items()
        }
    out["__scheduler_loop__"] = {
        "n": _loop_n,
        "total": _loop_total,
        "max": _loop_max,
        "max_ctx": _loop_max_thread,
        "threads": {},
    }
    return out


def _dumper() -> None:
    while True:
        try:
            rec = {
                "wall": time.time(),
                "mono": time.monotonic(),
                "pid": os.getpid(),
                "stats": snapshot(),
            }
            with open(_OUT, "a") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
        except Exception:
            pass
        time.sleep(_INTERVAL)


def _start() -> None:
    global _thread
    if not _ENABLED or _thread is not None:
        return
    t = threading.Thread(target=_dumper, name="l3-probe-dumper", daemon=True)
    _thread = t
    t.start()


class TrackedLock:
    """Drop-in lock wrapper that accumulates acquisition-wait time.

    `__enter__`/`acquire` time the wait for the underlying lock and record it
    under `lock_wait:<name>`.  Used to replace extent/hicache/controller locks
    in the instrumented copy so lock-wait magnitude stops being UNAVAILABLE.
    """

    __slots__ = ("_l", "_name")

    def __init__(self, name: str, rlock: bool = False):
        self._l = threading.RLock() if rlock else threading.Lock()
        self._name = name

    def acquire(self, *args, **kwargs):
        if not _ENABLED:
            return self._l.acquire(*args, **kwargs)
        t0 = time.perf_counter()
        got = self._l.acquire(*args, **kwargs)
        record("lock_wait:" + self._name, time.perf_counter() - t0)
        return got

    def release(self):
        return self._l.release()

    def __enter__(self):
        if not _ENABLED:
            self._l.acquire()
            return self
        t0 = time.perf_counter()
        self._l.acquire()
        record("lock_wait:" + self._name, time.perf_counter() - t0)
        return self

    def __exit__(self, *exc):
        self._l.release()
        return False

    def locked(self):
        return self._l.locked()


def wrap_method(cls, name: str, tag: str) -> None:
    """Wrap `cls.name` to accumulate elapsed time and None-returns (HAE counts).

    Idempotent per (cls, name): a class method is wrapped at most once.
    """
    if not _ENABLED:
        return
    orig = getattr(cls, name, None)
    if orig is None or getattr(orig, "__l3wrapped__", False):
        return

    def _wrapped(self, *args, **kwargs):
        t0 = time.perf_counter()
        r = None
        try:
            r = orig(self, *args, **kwargs)
        finally:
            try:
                record("hae_" + tag, time.perf_counter() - t0)
                if r is None:
                    record("hae_" + tag + "_fail", 0.0)
            except Exception:
                pass
        return r

    _wrapped.__name__ = name
    _wrapped.__l3wrapped__ = True
    _wrapped.__wrapped__ = orig
    setattr(cls, name, _wrapped)


_start()
