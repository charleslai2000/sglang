"""Offline read-only WAL frame census (no benchmark, no server, no GPU).

Walks the extent WAL segment format documented in
sglang/srt/mem_cache/storage/extent/extent_metadata.py:
  header  = struct("<IHBBHIQ", magic, ver, frame_type, flags, reserved,
                    payload_len, seq)      -> 22 bytes
  then 4-byte crc32c, then payload_len bytes.  total = 26 + payload_len.
"""
import struct
import sys

FRAME_MAGIC = 0x484D3146
FRAME_HEADER_SIZE = 26
TYPES = {
    1: "FRAME_SET",
    2: "FRAME_BATCH_COMMIT",
    3: "FRAME_GROUP_COMMIT",
    4: "FRAME_DROP_SLOT",
    5: "FRAME_CLEAR",
    6: "FRAME_CHECKPOINT_MARK",
}


def main(path):
    with open(path, "rb") as fh:
        size = fh.fileno()
        import os

        total_size = os.fstat(size).st_size
        # skip segment header (28 bytes)
        off = 28
        fh.seek(off)
        counts = {}
        payload_sum = {}
        payload_max = {}
        n = 0
        while True:
            head = fh.read(FRAME_HEADER_SIZE)
            if len(head) < FRAME_HEADER_SIZE:
                break
            magic, ver, ftype, flags, res, plen, seq = struct.unpack(
                "<IHBBHIQ", head[:22]
            )
            if magic != FRAME_MAGIC:
                print("stop: bad magic at offset", off, hex(magic))
                break
            fh.seek(plen, 1)
            n += 1
            counts[ftype] = counts.get(ftype, 0) + 1
            payload_sum[ftype] = payload_sum.get(ftype, 0) + plen
            payload_max[ftype] = max(payload_max.get(ftype, 0), plen)
            off += FRAME_HEADER_SIZE + plen
        print("file_size", total_size, "frames", n, "bytes_walked", off)
        tot = sum(payload_sum.values())
        for t in sorted(counts):
            print(
                "%-22s frames=%-8d payload_bytes=%-12d avg=%-10.1f max=%d"
                % (
                    TYPES.get(t, str(t)),
                    counts[t],
                    payload_sum[t],
                    payload_sum[t] / counts[t],
                    payload_max[t],
                )
            )
        print("payload_bytes_total", tot, "crc_bytes_total(22+plen)", tot + 22 * n)


if __name__ == "__main__":
    main(sys.argv[1])
