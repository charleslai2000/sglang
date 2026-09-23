#!/usr/bin/env python3
"""Experimental IQ3_S -> signed-u 4-bit recode verifier.

This is not a GGUF/runtime converter. It consumes the pinned extracted tensor
fixture and emits an experimental 134-byte/block resident representation:
  uint8 codes[128] (two c=(u+15)//2 nibbles per byte), d[2], scales[4].
The original qh/sign planes are intentionally eliminated after decoding.
"""
import hashlib, json, re, struct
from pathlib import Path
import numpy as np

ROOT = Path(__file__).parent
SRC = ROOT / "k1_iq3s.cu"
RAW = ROOT / "iq3s_blk1_attn_qkv.bin"
OUT = ROOT / "iq3s_blk1_attn_qkv_u4x134.bin"
GRID = [int(x, 16) for x in re.findall(r"0x([0-9a-fA-F]+)u", SRC.read_text())]
assert len(GRID) == 512

def grid_bytes(x):
    return [(x >> (8*j)) & 255 for j in range(4)]

def decode_block(b):
    assert len(b) == 110
    d = np.frombuffer(b[:2], dtype='<f2')[0].item()
    qs, qh, signs, scales = b[2:66], b[66:74], b[74:106], b[106:110]
    out_u, out = [], []
    # This follows b496 dequantize_row_iq3_s ordering: two 32-value halves
    # per 64-element group, four groups per 256-element block.
    for ib32 in range(0, 8, 2):
        for half, db in ((0, d * (1 + 2*(scales[ib32//2] & 15))),
                         (1, d * (1 + 2*(scales[ib32//2] >> 4)))):
            qoff = (ib32//2)*16 + half*8
            hoff = (ib32//2)*2 + half
            soff = (ib32//2)*8 + half*4
            for l in range(4):
                i0 = qs[qoff + 2*l] | ((qh[hoff] << (8-2*l)) & 256)
                i1 = qs[qoff + 2*l+1] | ((qh[hoff] << (7-2*l)) & 256)
                g0, g1 = grid_bytes(GRID[i0]), grid_bytes(GRID[i1])
                sb = signs[soff+l]
                for j in range(4):
                    u0 = -g0[j] if sb & (1 << j) else g0[j]
                    u1 = -g1[j] if sb & (1 << (j+4)) else g1[j]
                    out_u += [u0, u1]
                    out += [db*u0, db*u1]
    assert len(out_u) == len(out) == 256
    return np.asarray(out_u, dtype=np.int16), np.asarray(out, dtype=np.float32)

def encode_block(b):
    u, _ = decode_block(b)
    assert np.all((u >= -15) & (u <= 15) & ((u & 1) != 0))
    c = ((u + 15)//2).astype(np.uint8)
    packed = bytearray(128)
    packed[:] = (c[0::2] | (c[1::2] << 4)).tobytes()
    return bytes(packed) + b[:2] + b[106:110]

def decode_recode(rb):
    assert len(rb) == 134
    c = np.empty(256, dtype=np.uint8)
    z = np.frombuffer(rb[:128], dtype=np.uint8)
    c[0::2], c[1::2] = z & 15, z >> 4
    u = c.astype(np.int16)*2 - 15
    d = np.frombuffer(rb[128:130], dtype='<f2')[0].item()
    scales = rb[130:134]
    vals = []
    for i, ui in enumerate(u):
        group = i // 64
        nib = scales[group//2] >> (4*(group&1)) & 15
        vals.append(d*(1+2*nib)*int(ui))
    return u, np.asarray(vals, dtype=np.float32)

raw = RAW.read_bytes()
assert len(raw) == 10240 * 2200
recode = bytearray()
max_abs = 0.0
u_mismatch = 0
blocks = len(raw)//110
for i in range(blocks):
    b = raw[i*110:(i+1)*110]
    u0, x0 = decode_block(b)
    rb = encode_block(b)
    u1, x1 = decode_recode(rb)
    u_mismatch += int(np.count_nonzero(u0 != u1))
    max_abs = max(max_abs, float(np.max(np.abs(x0-x1))))
    recode.extend(rb)
assert len(recode) == blocks*134
assert u_mismatch == 0 and max_abs == 0.0
OUT.write_bytes(recode)
manifest = {
    "status": "PASS",
    "experimental_only": True,
    "source_tensor": "blk.1.attn_qkv.weight",
    "source_shape_N_K": [10240, 5120],
    "source_type": "IQ3_S",
    "source_block_bytes": 110,
    "resident_block_bytes": 134,
    "source_bytes": len(raw),
    "resident_bytes": len(recode),
    "increase_ratio": len(recode)/len(raw),
    "blocks": blocks,
    "u_values": "signed odd integers -15..15; c=(u+15)//2",
    "u_mismatch_count": u_mismatch,
    "max_abs_decode_error": max_abs,
    "source_sha256": hashlib.sha256(raw).hexdigest(),
    "resident_sha256": hashlib.sha256(recode).hexdigest(),
}
(ROOT / "iq3s_recode_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
print(json.dumps(manifest, indent=2))
