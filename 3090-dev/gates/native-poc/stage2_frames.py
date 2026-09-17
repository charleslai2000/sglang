#!/usr/bin/env python3
"""Stage 2: native crc32c + WAL frame bytes must be bit-identical to frozen v1.1.

Compares actual byte strings (and sha256 digests) against
`sglang.srt.mem_cache.storage.extent.extent_metadata` loaded from the frozen
v1.1 tree, including a real 1024-entry SetPayload frame.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _load import FROZEN_SRC, load_poc  # noqa: E402

sys.path.insert(0, FROZEN_SRC)
from sglang.srt.mem_cache.storage.extent import extent_metadata as em  # noqa: E402


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    module = load_poc()
    assert em.crc32c(b"123456789") == 0xE3069283

    rng = random.Random(20260916)
    payloads = {
        "empty": b"",
        "known_vector": b"123456789",
        "bytes_0_255": bytes(range(256)),
        "rand_4096": rng.randbytes(4096),
        "rand_42659": rng.randbytes(42659),          # avg WAL frame observed
        "rand_122920": rng.randbytes(122920),        # max WAL frame observed
        "rand_1MiB": rng.randbytes(1024 * 1024),     # large multi-KB payload
    }

    report: dict = {"crc32c": {}, "frames": {}, "real_set_payload": {}}

    # --- 2.1 crc32c equality (known vector, fixed buffers, incremental crc) ---
    for name, payload in payloads.items():
        py = em.crc32c(payload)
        rs = module.crc32c(payload)
        assert py == rs, (name, hex(py), hex(rs))
        report["crc32c"][name] = {"bytes": len(payload), "crc32c": f"0x{py:08X}"}
    for seed_crc in (0, 1, 0xDEADBEEF, 0xFFFFFFFF):
        payload = payloads["rand_4096"]
        py = em.crc32c(payload, seed_crc)
        rs = module.crc32c(payload, seed_crc)
        assert py == rs, (seed_crc, hex(py), hex(rs))
        report["crc32c"][f"incremental_from_0x{seed_crc:08X}"] = {
            "bytes": len(payload),
            "crc32c": f"0x{py:08X}",
        }

    # --- 2.2 full frame byte equality across types, seqs and payloads ---
    frame_types = (em.FRAME_SET, em.FRAME_BATCH_COMMIT, em.FRAME_GROUP_COMMIT)
    seqs = (0, 1, 2**32 - 1, 2**53 + 1, 2**64 - 1)
    compared = 0
    for ftype in frame_types:
        for seq in seqs:
            for name, payload in payloads.items():
                py_frame = em.encode_frame(ftype, seq, payload)
                rs_frame = module.encode_frame(ftype, seq, payload)
                assert py_frame == rs_frame, (ftype, seq, name)
                assert len(py_frame) == 26 + len(payload)
                compared += 1
                report["frames"][f"t{ftype}_s{seq}_{name}"] = {
                    "bytes": len(py_frame),
                    "sha256": digest(py_frame),
                }
    report["frames_compared"] = compared
    report["frames_byte_identical"] = compared

    # --- 2.3 real 1024-entry SetPayload frame (production-shaped payload) ---
    entries = [
        em.SetEntry(
            storage_key=b"k" * 32,
            extent_id=i,
            offset=i * 16384,
            length=16384,
            generation=1,
            component=1,
        )
        for i in range(1024)
    ]
    set_payload_obj = em.SetPayload(
        group_epoch=b"\x00" * 16,
        group_seq=0,
        batch_id=1,
        member_index=0,
        member_count=1,
        entries=entries,
    )
    set_payload_bytes = em.encode_set_payload(set_payload_obj)
    py_frame = em.encode_frame(em.FRAME_SET, 12345, set_payload_bytes)
    rs_frame = module.encode_frame(module.FRAME_SET, 12345, set_payload_bytes)
    assert py_frame == rs_frame
    report["real_set_payload"] = {
        "entries": 1024,
        "payload_bytes": len(set_payload_bytes),
        "frame_bytes": len(py_frame),
        "sha256": digest(py_frame),
        "byte_identical": True,
        "crc32c_header_plus_payload": f"0x{em.crc32c(py_frame[:22] + set_payload_bytes):08X}",
    }

    # --- 2.4 boundary behaviour mirrors Python's validation ---
    try:
        module.encode_frame(99, 0, b"x")
        raise AssertionError("native accepted unknown frame type")
    except ValueError:
        pass
    report["unknown_frame_type_rejected"] = True
    try:
        module.encode_frame(1, 0, b"x" * 16, 8)
        raise AssertionError("native accepted over-limit payload")
    except ValueError:
        pass
    report["payload_limit_rejected"] = True

    print(json.dumps(report, indent=2))
    print("STAGE2_FRAMES_OK")


if __name__ == "__main__":
    main()
