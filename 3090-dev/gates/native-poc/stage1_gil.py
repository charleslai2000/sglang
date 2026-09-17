#!/usr/bin/env python3
"""Stage 1.3: is the heavy native region genuinely GIL-free?

Method: a dense pure-Python counter thread (the victim) records iterations and
the maximum contiguous gap between iterations while the main thread runs native
work. A Python-level victim holds the GIL whenever it is running, so if the
native region holds the GIL the victim stops dead; if the native region
detaches, the victim keeps running.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load_poc  # noqa: E402


class Busy(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.stop = False
        self.ready = threading.Event()
        self.reset()

    def reset(self) -> None:
        self.iters = 0
        self.max_gap_ns = 0

    def run(self) -> None:
        last = time.perf_counter_ns()
        self.ready.set()
        while not self.stop:
            n = 0
            # Inner batch keeps the hot loop pure Python and GIL-bound.
            for _ in range(200):
                n += 1
            self.iters += n
            now = time.perf_counter_ns()
            gap = now - last
            if gap > self.max_gap_ns:
                self.max_gap_ns = gap
            last = now

    def snap(self):
        return {"iters": self.iters, "max_gap_ms": self.max_gap_ns / 1e6}


def measure(native, duration_ms: int, busy: Busy, reps: int = 3):
    rows = []
    for _ in range(reps):
        busy.reset()
        started = time.perf_counter_ns()
        native(duration_ms)
        wall_ms = (time.perf_counter_ns() - started) / 1e6
        snap = busy.snap()
        rows.append(
            {
                "wall_ms": wall_ms,
                "victim_iters": snap["iters"],
                "victim_max_gap_ms": snap["max_gap_ms"],
                "victim_iters_per_ms": snap["iters"] / wall_ms,
            }
        )
    return rows


def main() -> None:
    module = load_poc()
    busy = Busy()
    busy.start()
    busy.ready.wait()

    # Baseline victim rate with the main thread idle.
    time.sleep(0.3)
    busy.reset()
    time.sleep(0.5)
    base = busy.snap()
    baseline = {
        "window_ms": 500.0,
        "victim_iters": base["iters"],
        "victim_iters_per_ms": base["iters"] / 500.0,
        "victim_max_gap_ms": base["max_gap_ms"],
    }

    free = measure(module.burn_gil_free, 300, busy)
    held = measure(module.burn_holding_gil, 300, busy)
    busy.stop = True
    busy.join(2.0)

    report = {
        "python": sys.executable,
        "switchinterval_s": sys.getswitchinterval(),
        "baseline_idle": baseline,
        "burn_gil_free_300ms": free,
        "burn_holding_gil_300ms": held,
    }
    print(json.dumps(report, indent=2))
    free_median = sorted(r["victim_iters_per_ms"] for r in free)[len(free) // 2]
    held_median = sorted(r["victim_iters_per_ms"] for r in held)[len(held) // 2]
    print(f"victim_rate_free={free_median:.1f}/ms victim_rate_held={held_median:.1f}/ms "
          f"baseline={baseline['victim_iters_per_ms']:.1f}/ms")
    assert free_median > 0.5 * baseline["victim_iters_per_ms"], (free_median, baseline)
    assert held_median < 0.05 * baseline["victim_iters_per_ms"], (held_median, baseline)
    print("STAGE1_GIL_OK")


if __name__ == "__main__":
    main()
