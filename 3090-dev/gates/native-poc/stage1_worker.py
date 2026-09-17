#!/usr/bin/env python3
"""Stage 1.4: true background std::thread worker, enqueue/poll, no Python callback.

Python enqueues N immutable payloads, does other work, then polls for N
completions and cross-checks every CRC against Python's own implementation.

The "no callback" property is demonstrated directly: the main thread holds the
GIL for a pure-Python spin (so no Python bytecode anywhere can run) while the
worker is mid-queue; worker completion still advances.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load_poc  # noqa: E402

FROZEN_SRC = "/opt/sglang/local-prod-v1.1-candidate/src/python"


def py_crc32c(data: bytes) -> int:
    sys.path.insert(0, FROZEN_SRC)
    from sglang.srt.mem_cache.storage.extent import extent_metadata as em

    return em.crc32c(data)


def main() -> None:
    module = load_poc()

    # Calibrate so the queue is still draining when the GIL is held below.
    worker = module.Worker(work_iters=2_000_000)
    probe = bytes(range(256)) * 1024
    worker.submit(probe)
    t = time.perf_counter()
    while worker.finished() < 1:
        time.sleep(0.0005)
    job_ms = (time.perf_counter() - t) * 1e3
    n_jobs = max(16, min(512, int(800.0 / max(job_ms, 0.05))))
    worker.shutdown()

    payloads = []
    for i in range(n_jobs):
        payloads.append(bytes(((i * 131 + j) & 0xFF) for j in range(256 * 1024)))

    worker = module.Worker(work_iters=2_000_000)
    t0 = time.perf_counter()
    ids = [worker.submit(p) for p in payloads]
    enqueue_ms = (time.perf_counter() - t0) * 1e3
    assert ids == list(range(n_jobs)), ids
    assert worker.submitted() == n_jobs

    # (a) Python does unrelated work while the worker drains.
    other = 0
    for i in range(50_000):
        other += i
    mid_finished = worker.finished()

    # (b) Hold the GIL in pure Python for ~200 ms: no Python can run at all,
    #     yet the worker must keep completing jobs (it never calls into Python).
    before_hold = worker.finished()
    assert before_hold < n_jobs, "queue drained before the GIL hold; recalibrate"
    hold_start = time.perf_counter()
    acc = 0
    while (time.perf_counter() - hold_start) < 0.2:
        for i in range(5_000):
            acc += i
    after_hold = worker.finished()
    del acc

    # (c) Poll until everything is done; no blocking, no callback.
    collected: list[tuple[int, int, int]] = []
    polls = 0
    deadline = time.perf_counter() + 60.0
    while len(collected) < n_jobs and time.perf_counter() < deadline:
        finished, drained = worker.poll()
        collected.extend(drained)
        polls += 1
        if len(collected) < n_jobs:
            time.sleep(0.001)

    assert len(collected) == n_jobs, len(collected)
    assert worker.finished() == n_jobs
    assert worker.pending() == 0

    mismatches = []
    for (job_id, crc, length) in collected:
        expected = py_crc32c(payloads[job_id])
        if crc != expected or length != len(payloads[job_id]):
            mismatches.append((job_id, hex(crc), hex(expected), length))
    assert not mismatches, mismatches[:5]

    worker.shutdown()
    report = {
        "job_ms_calibrated": job_ms,
        "jobs": n_jobs,
        "payload_bytes": 256 * 1024,
        "enqueue_ms_for_all_jobs": enqueue_ms,
        "finished_while_python_did_other_work": mid_finished,
        "finished_before_gil_hold": before_hold,
        "finished_after_200ms_pure_python_gil_hold": after_hold,
        "advanced_during_gil_hold": after_hold - before_hold,
        "polls_to_collect": polls,
        "crc_mismatches": len(mismatches),
    }
    print(json.dumps(report, indent=2))
    assert after_hold - before_hold > 0, report
    assert mid_finished > 0, report
    print("STAGE1_WORKER_OK")


if __name__ == "__main__":
    main()
