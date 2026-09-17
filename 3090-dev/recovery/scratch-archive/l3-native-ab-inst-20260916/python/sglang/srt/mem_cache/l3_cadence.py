"""L3 scheduler-cadence forensic probe -- THROWAWAY instrumented copy only.

Task: l3-128k-scheduler-cadence-forensics-20260916

Enabled only when ``L3_CADENCE=1``.  This module is imported by the throwaway
copy of the tree only; the frozen v1 tree never imports it.  It is fail-open:
every entry point swallows its own exceptions so it can never raise into the
engine path, and when disabled every hook returns immediately.

What it records (one JSON object per line in ``$L3_CADENCE_DIR/cadence-events.jsonl``):

  * ``H``  header: pid/tid, python, thread inventory, switch interval.
  * ``I``  one per scheduler-loop iteration:
             wall (time.time at loop top), iter_ms (wall time of the iteration),
             cpu_ms (scheduler-thread CLOCK_THREAD_CPUTIME_ID delta),
             phases{recv,schedule,batch_build,fwd_dispatch,post,tail} in ms,
             nested{cache_hicache_events,ready_horizon,reconcile_restore,
                    out_pop,out_pop_disable,sample_launch} in ms,
             fwd (bool: an overlap forward was submitted this iteration),
             bs / mode of that forward, tid.
  * ``F``  one per overlap forward, emitted when its CUDA end event completes
           (never blocks: ``Event.query()`` is a non-blocking predicate):
             mode (decode/prefill/other), bs, backend (fwd/sample),
             submit_wall (time.time at dispatch),
             gpu_ms (elapsed_time(start_ev, end_ev) on the forward stream),
             gpu_gap_ms (elapsed_time(previous end_ev, this start_ev) -- the
                         forward-stream idle gap between adjacent forwards).

Design notes:
  * counter writes are a single ``os.write`` of a small JSON line (O_APPEND),
    so the probe neither buffers nor holds a Python lock in the hot loop;
  * CUDA events are recorded on the *current* stream, which inside
    ``run_batch``'s ``forward_stream_ctx`` is the forward stream;
  * event readings are deferred until the end event has completed, so the
    scheduler thread is never synchronised by the probe.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

_ENABLED = os.environ.get("L3_CADENCE", "0") == "1"
_DIR = os.environ.get("L3_CADENCE_DIR", "/tmp/l3-cadence")
_OUT = os.path.join(_DIR, "cadence-events.jsonl")
_MAX_INFLIGHT = 8  # cap on not-yet-complete forward records (unresolved kept)

_fd = None
_fd_lock = threading.Lock()
_state = threading.local()
_pending = []          # forward records waiting for their end event
_last_end_event = None
_anchor_event = None   # GPU-timeline origin (forward stream), for cross-forward gaps
_ev_pool = []          # recycled (start, end) CUDA event pairs (depth <= _MAX_INFLIGHT)
_iter_no = 0
_hdr_done = False


def enabled() -> bool:
    return _ENABLED


def _fd_get():
    global _fd
    if _fd is None:
        with _fd_lock:
            if _fd is None:
                try:
                    os.makedirs(_DIR, exist_ok=True)
                except Exception:
                    pass
                _fd = os.open(_OUT, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    return _fd


def _emit(obj) -> None:
    if not _ENABLED:
        return
    try:
        os.write(_fd_get(), (json.dumps(obj, default=str) + "\n").encode())
    except Exception:
        pass


def _inventory() -> list:
    out = []
    try:
        for th in threading.enumerate():
            out.append({"name": th.name, "native_id": th.native_id,
                        "alive": th.is_alive(), "daemon": th.daemon})
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- loop hooks

def loop_begin() -> None:
    """Start a scheduler iteration: reset phase/nested accumulators."""
    global _hdr_done
    if not _ENABLED:
        return
    try:
        st = _state
        now = time.perf_counter()
        st.t_prev = now
        st.t0 = now
        st.phases = {}
        st.nested = {}
        st.nb = {}
        st.bs = 0
        st.mode = "none"
        st.fwd_submitted = False
        st.pending = None
        try:
            st.cpu0 = time.thread_time()
        except Exception:
            st.cpu0 = 0.0
        st.wall0 = time.time()
        if not _hdr_done:
            _hdr_done = True
            try:
                # Lets the external driver start its zero-interference /proc
                # thread sampler without scanning for the scheduler process.
                with open(os.path.join(_DIR, "sched-pid"), "w") as _pf:
                    _pf.write(str(os.getpid()))
            except Exception:
                pass
            _emit({
                "t": "H", "wall": st.wall0, "mono": time.monotonic(),
                "pid": os.getpid(), "tid": threading.get_native_id(),
                "python": sys.version.split()[0],
                "switchinterval": sys.getswitchinterval(),
                "getcheckinterval": getattr(sys, "getcheckinterval", lambda: None)(),
                "threads": _inventory(),
            })
    except Exception:
        pass


def phase(name: str) -> None:
    """Close the current phase and attribute the elapsed time to `name`."""
    if not _ENABLED:
        return
    try:
        st = _state
        now = time.perf_counter()
        st.phases[name] = st.phases.get(name, 0.0) + (now - st.t_prev)
        st.t_prev = now
    except Exception:
        pass


def nested(name: str, dt: float) -> None:
    """Accumulate a sub-phase time for the current iteration (if any)."""
    if not _ENABLED:
        return
    try:
        st = _state
        st.nested[name] = st.nested.get(name, 0.0) + dt
    except Exception:
        pass


def nested_begin(name: str) -> None:
    if not _ENABLED:
        return
    try:
        st = _state
        st.nb[name] = time.perf_counter()
    except Exception:
        pass


def nested_end(name: str) -> None:
    if not _ENABLED:
        return
    try:
        st = _state
        t0 = st.nb.pop(name, None)
        if t0 is not None:
            nested(name, time.perf_counter() - t0)
    except Exception:
        pass


def forward_begin(mode: str, bs: int, backend: str = "fwd") -> None:
    """Record a CUDA start event immediately before a forward dispatch."""
    global _anchor_event
    if not _ENABLED:
        return
    try:
        import torch

        st = _state
        if _anchor_event is None:
            _anchor_event = torch.cuda.Event(enable_timing=True)
            _anchor_event.record()
        if _ev_pool:
            ev0, ev1 = _ev_pool.pop()
        else:
            ev0 = torch.cuda.Event(enable_timing=True)
            ev1 = torch.cuda.Event(enable_timing=True)
        ev0.record()
        st.pending = {
            "mode": mode, "bs": int(bs), "backend": backend,
            "ev0": ev0, "ev1": ev1,
            "anchor": _anchor_event,
            "submit_perf": time.perf_counter(),
            "submit_wall": time.time(),
            "submit_mono": time.monotonic(),
        }
        if backend == "fwd":
            # Only the main forward is the iteration's "primary" launch; the
            # delayed-sample launch is recorded as an extra `F` record but must
            # not overwrite the iteration's mode/batch attribution.
            st.mode = mode
            st.bs = int(bs)
            st.fwd_submitted = True
    except Exception:
        pass


def forward_end() -> None:
    """Record the CUDA end event and queue the record for deferred resolution."""
    if not _ENABLED:
        return
    try:
        st = _state
        rec = st.pending
        st.pending = None
        if rec is None:
            return
        rec["ev1"].record()
        rec["end_perf"] = time.perf_counter()
        rec["iter"] = getattr(st, "iter_no", -1)
        if len(_pending) < _MAX_INFLIGHT:
            _pending.append(rec)
    except Exception:
        pass


def loop_end() -> None:
    """Close the iteration, emit its record, and resolve completed forwards."""
    global _iter_no
    if not _ENABLED:
        return
    try:
        st = _state
        phase("tail")
        now = time.perf_counter()
        try:
            cpu1 = time.thread_time()
        except Exception:
            cpu1 = st.cpu0
        _iter_no += 1
        st.iter_no = _iter_no
        _emit({
            "t": "I", "i": _iter_no, "wall": st.wall0,
            "mono": time.monotonic(),
            "iter_ms": (now - st.t0) * 1e3,
            "cpu_ms": (cpu1 - st.cpu0) * 1e3,
            "phases": {k: v * 1e3 for k, v in st.phases.items()},
            "nested": {k: v * 1e3 for k, v in st.nested.items()},
            "fwd": st.fwd_submitted, "bs": st.bs, "mode": st.mode,
            "tid": threading.get_native_id(),
        })
        _resolve()
    except Exception:
        pass


def _resolve() -> None:
    """Emit `F` records for forwards whose end event has completed."""
    global _last_end_event
    while _pending:
        rec = _pending[0]
        try:
            ready = bool(rec["ev1"].query())
        except Exception:
            _pending.pop(0)
            continue
        if not ready:
            return
        _pending.pop(0)
        out = {
            "t": "F", "i": rec.get("iter"), "mode": rec["mode"],
            "bs": rec["bs"], "backend": rec["backend"],
            "submit_wall": rec["submit_wall"],
            "submit_mono": rec["submit_mono"],
            "submit_perf": rec["submit_perf"],
            "end_perf": rec["end_perf"],
        }
        try:
            # Absolute GPU-timeline offsets from the forward-stream anchor, so
            # the analyzer can pair any two forwards (gaps included) without
            # the probe having to know which pair the analyzer will want.
            out["start_off_ms"] = rec["anchor"].elapsed_time(rec["ev0"])
            out["end_off_ms"] = rec["anchor"].elapsed_time(rec["ev1"])
            out["gpu_ms"] = out["end_off_ms"] - out["start_off_ms"]
        except Exception as exc:
            out["gpu_ms"] = None
            out["gpu_err"] = repr(exc)
        _emit(out)
        try:
            _ev_pool.append((rec["ev0"], rec["ev1"]))
        except Exception:
            pass


def wrap_method(cls, name: str, tag: str) -> None:
    """Wrap ``cls.name`` to accumulate its wall time as nested sub-phase `tag`."""
    if not _ENABLED:
        return
    try:
        orig = getattr(cls, name, None)
        if orig is None or getattr(orig, "__l3_cad__", False):
            return

        def _wrapped(self, *args, **kwargs):
            t0 = time.perf_counter()
            try:
                return orig(self, *args, **kwargs)
            finally:
                try:
                    nested(tag, time.perf_counter() - t0)
                except Exception:
                    pass

        _wrapped.__name__ = name
        _wrapped.__l3_cad__ = True
        _wrapped.__wrapped__ = orig
        setattr(cls, name, _wrapped)
    except Exception:
        pass
