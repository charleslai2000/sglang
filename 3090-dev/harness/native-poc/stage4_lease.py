#!/usr/bin/env python3
"""Stage 4: completion-ordering lease/generation invariants + negative control.

Charter AMENDMENT 1-C: while the native worker holds a raw page pointer,
`pool_host` must not reuse/overwrite/free that page before its `pwritev` completes.

The allocator is a STAND-IN (`LeaseRegistry`): one stable arena, monotonic slot
generations, leases a recycler must respect, and a release that is only legal
after the worker publishes completion. `LeaseGatherWorker` is a real background
`std::thread` whose copy is parked half-way through by a PoC-only rendezvous, so
the in-flight window is deterministic rather than a timing race.

Negative control: the same interleaving WITHOUT a lease must corrupt the bytes.

Also runs the pointer-range-validation negative control in a child process:
`--crash-probe` dereferences a null pointer through the unchecked path and is
expected to die on SIGSEGV, proving the checked path is what prevents that.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import load_poc  # noqa: E402

SLOT_BYTES = 65536
SLOT_COUNT = 4
REPS = 20


def address(buffer_obj) -> int:
    return ctypes.addressof(buffer_obj)


def crash_probe() -> None:
    """Deliberately violate the `read_iovec` caller contract (null source)."""
    module = load_poc()
    module.read_iovec([(0, 65536)], 65536)  # expected to segfault
    print("CRASH_PROBE_UNEXPECTEDLY_SURVIVED")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def one_rep(module, arena, arena_addr, incoming_addr, use_lease: bool, rep: int):
    """Run one submit -> park -> recycle-attempt -> resume -> collect cycle."""
    slot_addr = arena_addr
    # Fresh content for the page the worker will read (pattern A).
    ctypes.memset(slot_addr, 0xA0, SLOT_BYTES)
    snapshot = bytes(arena[0:SLOT_BYTES])
    expected_crc = module.crc32c(snapshot)

    # Content the "next request" will D2H into the reused page (pattern B).
    ctypes.memset(incoming_addr, 0xB0, SLOT_BYTES)

    registry = module.LeaseRegistry(arena_addr, SLOT_BYTES * SLOT_COUNT)
    slot, generation = registry.alloc_slot(slot_addr, SLOT_BYTES)
    registry.free_slot(slot)  # today's lazy free: the slot is now recyclable

    lease_id = None
    if use_lease:
        # Invariant 1: submit establishes a page lease bound to (slot, generation).
        lease_id = registry.submit_lease(slot, generation)

    worker = module.LeaseGatherWorker(registry)
    worker.submit(
        job_id=1,
        pairs=[(slot_addr, SLOT_BYTES)],
        total=SLOT_BYTES,
        lease_id=lease_id,
        split_at=SLOT_BYTES // 2,
    )
    parked = worker.wait_parked(1, 10.0)
    if not parked:
        worker.shutdown()
        raise SystemExit("worker never parked; rendezvous broken")

    # The worker now holds the raw pointer, half-way through its copy.
    # Invariant 2: this recycle must be refused while the lease is held.
    recycled = registry.try_recycle(
        slot, generation + 1000, incoming_addr, SLOT_BYTES
    )
    arena_after_recycle_attempt = bytes(arena[0:SLOT_BYTES])

    # Invariant 3: release before completion must be refused.
    release_before_completion_refused = False
    if use_lease:
        try:
            registry.commit_install_and_release(lease_id)
        except ValueError:
            release_before_completion_refused = True

    worker.resume()
    deadline = time.time() + 10.0
    completion = None
    while time.time() < deadline:
        drained = worker.poll()
        if drained:
            completion = drained[0]
            break
        time.sleep(0.001)
    if completion is None:
        worker.shutdown()
        raise SystemExit("worker never completed")
    job_id, crc, nbytes = completion
    staged = worker.take_result(job_id)

    # Invariant 3 (second half): release is legal once completion has arrived.
    released_after_completion = False
    recycle_after_release = None
    if use_lease:
        registry.commit_install_and_release(lease_id)
        released_after_completion = True
        recycle_after_release = registry.try_recycle(
            slot, generation + 2000, incoming_addr, SLOT_BYTES
        )
    worker.shutdown()

    differing = sum(1 for a, b in zip(staged, snapshot) if a != b)
    return {
        "use_lease": use_lease,
        "rep": rep,
        "parked": parked,
        "recycle_returned_true": recycled,
        "arena_unchanged_by_refused_recycle": arena_after_recycle_attempt == snapshot,
        "release_before_completion_refused": release_before_completion_refused,
        "released_after_completion": released_after_completion,
        "recycle_allowed_after_release": recycle_after_release,
        "bytes": nbytes,
        "crc_matches_snapshot": crc == expected_crc,
        "byte_identical_to_snapshot": staged == snapshot,
        "differing_bytes": differing,
        "staged_sha256": sha256(staged),
        "snapshot_sha256": sha256(snapshot),
        "stats": dict(registry.stats()),
    }


def main() -> None:
    module = load_poc()
    arena = bytearray(SLOT_BYTES * SLOT_COUNT)
    arena_ctype = (ctypes.c_char * (SLOT_BYTES * SLOT_COUNT)).from_buffer(arena)
    arena_addr = address(arena_ctype)
    incoming_addr = arena_addr + 2 * SLOT_BYTES

    report = {
        "arena_bytes": SLOT_BYTES * SLOT_COUNT,
        "slot_bytes": SLOT_BYTES,
        "reps": REPS,
        "rendezvous": "PoC-only control: the worker parks after half the copy so "
        "the in-flight window is deterministic",
        "without_lease": [],
        "with_lease": [],
    }

    for rep in range(REPS):
        report["without_lease"].append(
            one_rep(module, arena, arena_addr, incoming_addr, False, rep)
        )
    for rep in range(REPS):
        report["with_lease"].append(
            one_rep(module, arena, arena_addr, incoming_addr, True, rep)
        )

    no_lease = report["without_lease"]
    with_lease = report["with_lease"]
    report["summary"] = {
        "without_lease_corrupted": sum(
            1 for row in no_lease if not row["byte_identical_to_snapshot"]
        ),
        "without_lease_crc_mismatches": sum(
            1 for row in no_lease if not row["crc_matches_snapshot"]
        ),
        "with_lease_corrupted": sum(
            1 for row in with_lease if not row["byte_identical_to_snapshot"]
        ),
        "with_lease_crc_mismatches": sum(
            1 for row in with_lease if not row["crc_matches_snapshot"]
        ),
        "with_lease_recycle_refusals": sum(
            1 for row in with_lease if row["recycle_returned_true"] is False
        ),
        "with_lease_release_before_completion_refused": sum(
            1 for row in with_lease if row["release_before_completion_refused"]
        ),
        "with_lease_recycle_allowed_after_release": sum(
            1 for row in with_lease if row["recycle_allowed_after_release"] is True
        ),
        "without_lease_recycle_allowed": sum(
            1 for row in no_lease if row["recycle_returned_true"] is True
        ),
        "mean_differing_bytes_without_lease": (
            sum(row["differing_bytes"] for row in no_lease) / len(no_lease)
        ),
        "mean_differing_bytes_with_lease": (
            sum(row["differing_bytes"] for row in with_lease) / len(with_lease)
        ),
    }
    report["stats_with_lease_last_rep"] = dict(with_lease[-1]["stats"])

    # --- explicit invariant demonstrations (not part of the corruption reps) ---
    registry = module.LeaseRegistry(arena_addr, SLOT_BYTES * SLOT_COUNT)
    slot_a, gen_a = registry.alloc_slot(arena_addr, SLOT_BYTES)
    slot_b, gen_b = registry.alloc_slot(arena_addr + SLOT_BYTES, SLOT_BYTES)
    stale_refused = False
    try:
        registry.submit_lease(slot_a, gen_b)  # generation of a *different* slot
    except ValueError:
        stale_refused = True
    double_lease_refused = False
    lease_a = registry.submit_lease(slot_a, gen_a)
    try:
        registry.submit_lease(slot_a, gen_a)
    except ValueError:
        double_lease_refused = True
    out_of_range_refused = False
    try:
        registry.alloc_slot(arena_addr + SLOT_BYTES * SLOT_COUNT, SLOT_BYTES)
    except ValueError:
        out_of_range_refused = True
    report["invariant_1_lease_establishment"] = {
        "slots_allocated": 2,
        "generations_monotonic": gen_b > gen_a,
        "stale_generation_refused": stale_refused,
        "second_lease_on_same_slot_refused": double_lease_refused,
        "lease_info": list(registry.lease_info(lease_a)),
        "out_of_range_alloc_refused": out_of_range_refused,
    }

    # --- pointer-range validation, checked vs unchecked (child process) ---
    checked_rejected = False
    checked_message = None
    try:
        module.read_iovec_checked(
            [(0, 65536)], 65536, arena_addr, SLOT_BYTES * SLOT_COUNT
        )
    except ValueError as exc:
        checked_rejected = True
        checked_message = str(exc)

    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--crash-probe"],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=180,
    )
    report["pointer_range_validation"] = {
        "validate_range_valid": module.validate_range(
            arena_addr, SLOT_BYTES, arena_addr, SLOT_BYTES * SLOT_COUNT
        ),
        "validate_range_before_base": module.validate_range(
            arena_addr - 1, 1, arena_addr, SLOT_BYTES * SLOT_COUNT
        ),
        "validate_range_past_end": module.validate_range(
            arena_addr + SLOT_BYTES * SLOT_COUNT, 1, arena_addr, SLOT_BYTES * SLOT_COUNT
        ),
        "validate_range_overflow_len": module.validate_range(
            arena_addr, 2**64 - 1, arena_addr, SLOT_BYTES * SLOT_COUNT
        ),
        "validate_range_null_ptr": module.validate_range(
            0, 4096, arena_addr, SLOT_BYTES * SLOT_COUNT
        ),
        "checked_path_rejected_null": checked_rejected,
        "checked_path_message": checked_message,
        "unchecked_path_child_returncode": proc.returncode,
        "unchecked_path_child_killed_by_signal": proc.returncode < 0,
        "unchecked_path_negative_control": (
            "read_iovec() with a null source dies on SIGSEGV in a sandboxed child; "
            "read_iovec_checked() raises ValueError before any dereference"
        ),
        "unchecked_child_stderr_tail": proc.stderr.strip().splitlines()[-1:] or [],
    }

    print(json.dumps(report, indent=2))

    summary = report["summary"]
    assert summary["without_lease_corrupted"] == REPS, summary
    assert summary["without_lease_crc_mismatches"] == REPS, summary
    assert summary["with_lease_corrupted"] == 0, summary
    assert summary["with_lease_crc_mismatches"] == 0, summary
    assert summary["with_lease_recycle_refusals"] == REPS, summary
    assert summary["with_lease_release_before_completion_refused"] == REPS, summary
    assert summary["with_lease_recycle_allowed_after_release"] == REPS, summary
    assert report["pointer_range_validation"]["checked_path_rejected_null"]
    assert not report["pointer_range_validation"]["validate_range_null_ptr"]
    assert report["pointer_range_validation"]["unchecked_path_child_killed_by_signal"], (
        report["pointer_range_validation"]
    )
    print(
        "neg-control: without lease "
        f"{summary['without_lease_corrupted']}/{REPS} corrupted "
        f"(mean {summary['mean_differing_bytes_without_lease']:.0f} bytes); "
        f"with lease {summary['with_lease_corrupted']}/{REPS} corrupted"
    )
    print("STAGE4_LEASE_OK")


if __name__ == "__main__":
    if "--crash-probe" in sys.argv:
        crash_probe()
    else:
        main()
