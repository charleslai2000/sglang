#!/usr/bin/env python3
"""P2-B0 GPU + server timeline sampler (read-only, CPU-side).

Contract: work/P2B0-EXECUTION-CONTRACT-20260912.md (sec. 5 "cache_induced_gpu_idle"
and sec. 6 "Measurement authorisation").  The only observation mechanisms are the
external, non-invasive ones the user explicitly authorised:

  * ``nvidia-smi --query-gpu=timestamp,utilization.gpu,utilization.memory,
    power.draw,clocks.sm --format=csv,noheader,nounits`` polled at
    ``--gpu-sample-ms`` (default 200) -> ``gpu.csv``.
  * the server's existing read-only ``/metrics`` endpoint polled each sample ->
    ``metrics.csv`` with raw ``num_queue_reqs``, ``num_running_reqs`` and
    ``realtime_tokens_total{mode="decode"}`` when present.

Both CSVs carry a ``mono_ns`` column (``time.monotonic_ns``) so the two
timelines join by nearest sample.  This module never raises out of the sampling
loop: every failed sample is recorded with rc/err.  It performs no server
control, imports no product code and writes only ``--out-dir``.

Metric names (verified against the running source):
  python/sglang/srt/observability/metrics_collector.py:292-299
      sglang:num_running_reqs  (Gauge)
      sglang:num_queue_reqs    (Gauge)
  python/sglang/srt/observability/metrics_collector.py:990-994 and :1350-1366
      sglang:realtime_tokens_total{mode="decode"}  (Counter)

The parser accepts both the ``sglang:``-prefixed and bare forms, handles
optional Prometheus label blocks ``{...}``, and returns an explicit
``present``/``err`` verdict per metric so a missing metric is never silently
written as 0.

Importable as ``from p2b0_sampler import Sampler`` (threaded) or runnable
standalone:

  python p2b0_sampler.py --out-dir DIR --duration-seconds 30
  python p2b0_sampler.py --from-csv /tmp/metrics.txt        # parser self-test
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

NVSMI_QUERY = "timestamp,utilization.gpu,utilization.memory,power.draw,clocks.sm"

# Prometheus text exposition: name{labels} value [timestamp]
RE_METRIC = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+"
    r"([0-9eE.+-]+|NaN|[+-]?Inf)(?:\s+[0-9.eE+-]+)?$"
)
RE_LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')

METRIC_RUNNING = "num_running_reqs"
METRIC_QUEUE = "num_queue_reqs"
METRIC_REALTIME = "realtime_tokens_total"
DECODE_MODE = "decode"

# metrics.csv column order (kept backward compatible: the original 8-column
# prefix is unchanged, new presence/err flags are appended).
METRICS_HEADER = (
    "mono_ns,num_queue_reqs,num_running_reqs,realtime_decode_tokens,"
    "realtime_decode_present,http,rc,err,"
    "num_queue_reqs_present,num_running_reqs_present,realtime_decode_err,"
    "num_queue_reqs_err,num_running_reqs_err"
)


def _to_float(s):
    if s is None:
        return None
    s = s.strip()
    if s in ("", "[N/A]", "N/A", "nan", "NaN", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return repr(v)


def _csv(s):
    if s is None:
        return ""
    return str(s).replace(",", ";").replace("\n", " ").strip()


def parse_prometheus(text):
    """Return {metric_name: [(labels_dict, float|None), ...]}.

    Handles the three real /metrics shapes:
      sglang:num_running_reqs 3
      sglang:num_running_reqs{k="v"} 3
      realtime_tokens_total{mode="decode"} 12345.0
    """
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = RE_METRIC.match(line)
        if not m:
            continue
        name, labels_s, val = m.group(1), m.group(2) or "", m.group(3)
        labels = dict(RE_LABEL.findall(labels_s))
        out.setdefault(name, []).append((labels, _to_float(val)))
    return out


def _iter_series(parsed, base):
    """Yield (name, labels, value) for the base metric under the bare and
    sglang: prefixed names, with and without the _total suffix."""
    for name in (base, "sglang:" + base, base + "_total",
                 "sglang:" + base + "_total"):
        for labels, val in parsed.get(name, []):
            yield name, labels, val


def lookup_metric(parsed, base, mode=None):
    """Return an explicit verdict for one metric.

    ``{"value": float|None, "present": bool, "n_series": int, "err": str|None}``
    where ``present`` means at least one matching series was found.  A series
    whose value cannot be parsed is reported as present with value None and an
    err, never silently as 0.
    """
    matched = 0
    total = 0.0
    has_val = False
    saw_mode_mismatch = False
    for _name, labels, val in _iter_series(parsed, base):
        if mode is not None and labels.get("mode") != mode:
            saw_mode_mismatch = True
            continue
        matched += 1
        if val is not None:
            total += val
            has_val = True
    if matched == 0:
        err = None
        if saw_mode_mismatch:
            err = "series present but mode=%s absent" % mode
        return {"value": None, "present": False, "n_series": 0, "err": err}
    if not has_val:
        return {"value": None, "present": True, "n_series": matched,
                "err": "series present but value unparseable"}
    return {"value": total, "present": True, "n_series": matched, "err": None}


def parse_metrics(text):
    """Parse raw Prometheus text into the three P2-B0 metric verdicts."""
    parsed = parse_prometheus(text)
    return {
        METRIC_QUEUE: lookup_metric(parsed, METRIC_QUEUE),
        METRIC_RUNNING: lookup_metric(parsed, METRIC_RUNNING),
        "realtime_decode_tokens": lookup_metric(
            parsed, METRIC_REALTIME, mode=DECODE_MODE),
    }


# ---- backward-compatible helpers (older callers/tests) --------------------
def _sum_metric(parsed, base):
    r = lookup_metric(parsed, base)
    return r["value"], r["present"]


def _decode_tokens(parsed):
    r = lookup_metric(parsed, METRIC_REALTIME, mode=DECODE_MODE)
    return r["value"], r["present"]


def _run_nvsmi(cmd, timeout):
    """Return (rows, rc, err) where rows = [(gpu_index, ts, util_gpu,
    util_mem, power, clocks), ...]."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # noqa: BLE001 - never raise out of sampler
        return [], "000", repr(e)[:300]
    if p.returncode != 0:
        return [], str(p.returncode), (p.stderr or "").strip()[:300]
    rows = []
    for idx, line in enumerate(p.stdout.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        parts = [x.strip() for x in line.split(",")]
        while len(parts) < 5:
            parts.append("")
        rows.append((
            idx, parts[0], _to_float(parts[1]), _to_float(parts[2]),
            _to_float(parts[3]), _to_float(parts[4]),
        ))
    return rows, "0", None


class Sampler(threading.Thread):
    """Background GPU + /metrics timeline sampler.

    Writes ``gpu.csv`` and ``metrics.csv`` under ``out_dir``.  ``mono_ns`` in
    both files is ``time.monotonic_ns()`` taken at the start of each sample.
    """

    def __init__(self, out_dir, base="http://127.0.0.1:30000",
                 gpu_sample_ms=200, gpu_index=None, nvsmi_timeout=5.0,
                 metrics_timeout=2.0, run_id=None):
        super().__init__(name="p2b0-sampler", daemon=True)
        self.out_dir = out_dir
        self.base = base.rstrip("/")
        self.gpu_sample_ms = max(1, int(gpu_sample_ms))
        self.gpu_index = gpu_index
        self.nvsmi_timeout = nvsmi_timeout
        self.metrics_timeout = metrics_timeout
        self.run_id = run_id
        # NOTE: do not name this ``_stop`` -- that shadows Thread._stop() and
        # breaks Thread.join().
        self._stop_evt = threading.Event()
        self.gpu_path = os.path.join(out_dir, "gpu.csv")
        self.metrics_path = os.path.join(out_dir, "metrics.csv")
        self.gpu_samples = 0
        self.metrics_samples = 0
        self.errors = []

    def stop(self):
        self._stop_evt.set()

    def run(self):
        os.makedirs(self.out_dir, exist_ok=True)
        cmd = ["nvidia-smi", "--query-gpu=" + NVSMI_QUERY,
               "--format=csv,noheader,nounits"]
        if self.gpu_index is not None:
            cmd += ["-i", str(self.gpu_index)]
        with open(self.gpu_path, "w", newline="") as gh, \
                open(self.metrics_path, "w", newline="") as mh:
            gh.write("mono_ns,gpu_index,timestamp,utilization_gpu,"
                     "utilization_memory,power_draw,clocks_sm,rc,err\n")
            mh.write(METRICS_HEADER + "\n")
            next_t = time.monotonic()
            while not self._stop_evt.is_set():
                self._sample_gpu(gh, cmd)
                self._sample_metrics(mh)
                next_t += self.gpu_sample_ms / 1000.0
                delay = next_t - time.monotonic()
                if delay > 0:
                    if self._stop_evt.wait(delay):
                        break
                else:
                    next_t = time.monotonic()
            gh.flush()
            mh.flush()

    def _sample_gpu(self, fh, cmd):
        mono = time.monotonic_ns()
        rows, rc, err = _run_nvsmi(cmd, self.nvsmi_timeout)
        if not rows:
            fh.write("%d,%d,%s,%s,%s,%s,%s,%s,%s\n" % (
                mono, -1, "", "", "", "", "", rc, _csv(err)))
        for idx, ts, ug, um, pw, ck in rows:
            fh.write("%d,%d,%s,%s,%s,%s,%s,%s,%s\n" % (
                mono, idx, _csv(ts), _fmt(ug), _fmt(um), _fmt(pw), _fmt(ck),
                rc, _csv(err)))
            self.gpu_samples += 1
        fh.flush()

    def _sample_metrics(self, fh):
        mono = time.monotonic_ns()
        http = "000"
        err = None
        text = None
        try:
            req = urllib.request.Request(
                self.base + "/metrics", headers={"Accept": "text/plain"})
            with urllib.request.urlopen(req, timeout=self.metrics_timeout) as r:
                http = str(r.status)
                text = r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001 - never raise out of sampler
            err = repr(e)[:300]
        q = {"value": None, "present": False, "err": None}
        r = {"value": None, "present": False, "err": None}
        dec = {"value": None, "present": False, "err": None}
        if text:
            try:
                verdicts = parse_metrics(text)
                q = verdicts[METRIC_QUEUE]
                r = verdicts[METRIC_RUNNING]
                dec = verdicts["realtime_decode_tokens"]
            except Exception as e:  # noqa: BLE001
                perr = ("parse:" + repr(e))[:300]
                err = perr if not err else (err + " | " + perr)
        fh.write("%d,%s,%s,%s,%d,%s,%s,%s,%d,%d,%s,%s,%s\n" % (
            mono, _fmt(q["value"]), _fmt(r["value"]), _fmt(dec["value"]),
            1 if dec["present"] else 0, http,
            "0" if http == "200" else http, _csv(err),
            1 if q["present"] else 0, 1 if r["present"] else 0,
            _csv(dec["err"]), _csv(q["err"]), _csv(r["err"])))
        self.metrics_samples += 1
        fh.flush()


def _print_parsed(path):
    if path == "-":
        text = sys.stdin.read()
    else:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    print(json.dumps(parse_metrics(text), indent=2, sort_keys=True))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="P2-B0 GPU + /metrics sampler")
    ap.add_argument("--out-dir", required=False, default=None)
    ap.add_argument("--base", default=os.environ.get(
        "P2B0_BASE", "http://127.0.0.1:30000"))
    ap.add_argument("--gpu-sample-ms", type=int, default=200)
    ap.add_argument("--gpu-index", type=int, default=None)
    ap.add_argument("--nvsmi-timeout", type=float, default=5.0)
    ap.add_argument("--metrics-timeout", type=float, default=2.0)
    ap.add_argument("--duration-seconds", type=float, default=0.0,
                    help="0 = sample until interrupted")
    ap.add_argument("--from-csv", "--parse-metrics", dest="parse_metrics",
                    default=None, metavar="PATH",
                    help="parse a Prometheus /metrics text file ('-' = stdin) "
                         "into the three metric verdicts and exit")
    args = ap.parse_args(argv)
    if args.parse_metrics:
        return _print_parsed(args.parse_metrics)
    if not args.out_dir:
        ap.error("--out-dir is required unless --from-csv is given")
    s = Sampler(args.out_dir, base=args.base,
                gpu_sample_ms=args.gpu_sample_ms, gpu_index=args.gpu_index,
                nvsmi_timeout=args.nvsmi_timeout,
                metrics_timeout=args.metrics_timeout)
    if args.duration_seconds and args.duration_seconds > 0:
        s.start()
        try:
            time.sleep(args.duration_seconds)
        except KeyboardInterrupt:
            pass
        s.stop()
        s.join(timeout=10)
    else:
        try:
            s.run()
        except KeyboardInterrupt:
            pass
    print("SAMPLER_DONE gpu=%d metrics=%d out=%s"
          % (s.gpu_samples, s.metrics_samples, args.out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
