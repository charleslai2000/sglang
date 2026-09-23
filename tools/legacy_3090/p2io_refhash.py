#!/usr/bin/env python3
"""Pure-Python reference implementation of the HiCache native hash.

Faithful to hash_binding.cpp (unit_width / is_bigram / page_size semantics):
each page's SHA256 = SHA256(prior_digest || uint32_le(tokens)); prior digest is
the previous page's digest (seeded by the caller's prior_hash for page 0).
Only the regular (non-bigram) path is implemented here -- the engine flow under
investigation (KV page chains, page_size=1) never uses bigram.
"""

import hashlib
import struct


def _hash_page(data: bytes, prior_digest: bytes, has_prior: bool) -> bytes:
    ctx = hashlib.sha256()
    if has_prior:
        ctx.update(prior_digest)
    if len(data) > 0:
        ctx.update(data)
    return ctx.digest()


def get_hash(raw_tokens, logical_len, unit_width, is_bigram, prior_digest,
             page_size=None):
    """Mimic the C++ get_hash entrypoint.

    raw_tokens: buffer-like (array) of uint32/uint64 little-endian ints.
    prior_digest: bytes or None (32-byte raw digest).
    page_size: None -> single hash over all tokens; int -> per-page list.
    """
    if is_bigram:
        raise NotImplementedError("bigram not needed for KV page chains")
    if unit_width != 1:
        raise NotImplementedError("unit_width>1 not needed for KV page chains")

    vals = list(raw_tokens)[:logical_len]
    # uint32 little-endian bytes
    data = b"".join(struct.pack("<I", v & 0xFFFFFFFF) for v in vals)

    has_prior = prior_digest is not None
    prior = bytes(prior_digest) if prior_digest is not None else None

    if page_size is None:
        d = _hash_page(data, prior, has_prior)
        return d.hex()

    num_pages = (logical_len + page_size - 1) // page_size
    out = []
    for start in range(0, logical_len, page_size):
        chunk = data[start * 4:(start + page_size) * 4]
        d = _hash_page(chunk, prior, has_prior)
        prior = d
        has_prior = True
        out.append(d.hex())
    return out
