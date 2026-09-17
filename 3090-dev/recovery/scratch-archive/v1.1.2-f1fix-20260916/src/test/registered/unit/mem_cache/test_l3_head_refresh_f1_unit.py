# SPDX-License-Identifier: Apache-2.0
"""F1 regression: L3 chain-head write-once -> restore false negative.

``ExtentFileBackend.batch_exists`` returns the index of the FIRST absent key,
and ``CacheController._storage_hit_query`` breaks on the first short batch.  So
when the shared prompt-head pages are never re-written and the circular extent
allocator recycles the slot that holds them, every later query from page 0
reports a fully-present chain as ``storage_hit=0``.

This file reproduces that on a real ``ExtentFileBackend`` (real allocator, real
WAL, real ``batch_exists``) over the faithful 3-node incident shape:

    A = [p0]        written once, in slot 0
    B = [p1, p2]    written once, in slot 0
    C = [p3 .. p7]  written in slots 1+

and asserts the fix under review: an ordinary backup of C now re-submits the
anchor chain's head page p0 (a SET frame with a seq later than the DROP_SLOT
that recycled p0's slot), so p0 stops being write-once.

Runs CPU-only (``CUDA_VISIBLE_DEVICES`` must be a non-GPU ordinal, e.g. 999:
the frozen ``sglang.test.test_utils`` indexes ``CUDA_VISIBLE_DEVICES[0]``).
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
import struct
import tempfile
import unittest
from array import array
from unittest.mock import patch

import torch

from sglang.srt.mem_cache.allocator import TokenToKVPoolAllocator
from sglang.srt.mem_cache.base_prefix_cache import InsertParams
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool, ReqToTokenPool
from sglang.srt.mem_cache.radix_cache import RadixKey
from sglang.srt.mem_cache.storage.extent import extent_metadata as em
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend
from sglang.srt.mem_cache.unified_cache.components import ComponentType
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache
from sglang.test.test_utils import CustomTestCase

PAGE_BYTES = 5000  # 3 pages fit in the 16 KiB extent -> p0,p1,p2 share slot 0


class _ZeroCopyPool:
    """Minimal host pool exposing the v1 zero-copy buffer contract."""

    def __init__(self, page_bytes: int, slots: int):
        self.page_size = 1
        self._page_bytes = page_bytes
        self._pages = [bytearray(page_bytes) for _ in range(slots)]

    def get_page_buffer_meta(self, indices):
        idx = indices.tolist() if hasattr(indices, "tolist") else list(indices)
        ptrs = [
            ctypes.addressof(ctypes.c_char.from_buffer(self._pages[i])) for i in idx
        ]
        return ptrs, [self._page_bytes] * len(ptrs)


def _oracle_get_native_hash(token_ids, prior_digest, page_size=None):
    """Deterministic SHA256 page chain (patches out the C++ hash extension)."""
    raw = (
        token_ids.raw_token_ids()
        if hasattr(token_ids, "raw_token_ids")
        else token_ids
    )
    tokens = list(raw)
    data = b"".join(struct.pack("<I", t & 0xFFFFFFFF) for t in tokens)
    prior = prior_digest if prior_digest else None
    has_prior = prior is not None
    out = []
    step = page_size or len(tokens)
    for start in range(0, len(tokens), step):
        ctx = hashlib.sha256()
        if has_prior:
            ctx.update(prior)
        ctx.update(data[start * 4 : (start + step) * 4])
        prior = ctx.digest()
        has_prior = True
        out.append(prior.hex())
    return out[-1] if page_size is None else out


def _make_cache(cap_pages):
    kv_pool = MHATokenToKVPool(
        size=cap_pages, page_size=1, dtype=torch.float16, head_num=2, head_dim=8,
        layer_num=1, device="cpu", enable_memory_saver=False,
    )
    allocator = TokenToKVPoolAllocator(
        size=cap_pages, dtype=torch.float16, device="cpu", kvcache=kv_pool,
        need_sort=False,
    )
    req_pool = ReqToTokenPool(
        size=8, max_context_len=cap_pages + 64, device="cpu",
        enable_memory_saver=False,
    )
    params = CacheInitParams(
        disable=False, req_to_token_pool=req_pool,
        token_to_kv_pool_allocator=allocator, page_size=1,
        eviction_policy="lru", tree_components=(ComponentType.FULL,),
    )
    cache = UnifiedRadixCache(params)
    cache.enable_storage = True
    return cache, allocator


def _insert(cache, allocator, token_ids):
    indices = allocator.alloc(len(token_ids))
    node_id = cache.insert(
        InsertParams(
            key=RadixKey(array("q", token_ids)), value=indices.to(torch.int64)
        )
    ).last_device_node
    return cache.tree_core.node_by_id(node_id)


@patch("sglang.srt.mem_cache.utils.get_native_hash", _oracle_get_native_hash)
class TestHeadRefreshF1(CustomTestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="f1_head_refresh_")
        self.backend = ExtentFileBackend(
            HiCacheStorageConfig(
                extra_config={
                    "storage_dir": self.tmpdir,
                    "extent_size": "16Ki",
                    "file_size": "64Ki",
                },
                tp_rank=0, tp_size=1, pp_rank=0, pp_size=1,
                attn_cp_rank=0, attn_cp_size=1, is_mla_model=False,
                enable_storage_metrics=False, is_page_first_layout=True,
                model_name="f1head",
            )
        )
        self.backend.register_mem_pool_host(_ZeroCopyPool(PAGE_BYTES, 64))
        toks = [11, 22, 33, 44, 55, 66, 77, 88]
        self.cache, alloc = _make_cache(64)
        self.a = _insert(self.cache, alloc, toks[:1])   # A = [p0]
        self.b = _insert(self.cache, alloc, toks[:3])   # B = [p1, p2]
        self.c = _insert(self.cache, alloc, toks)       # C = [p3 .. p7]
        for n in (self.a, self.b, self.c):
            n.component_data[ComponentType.FULL].host_value = torch.tensor(
                list(range(10, 10 + len(n.hash_value))), dtype=torch.int64
            )
        self.chain = (
            list(self.a.hash_value) + list(self.b.hash_value) + list(self.c.hash_value)
        )
        self.assertEqual(
            (len(self.a.hash_value), len(self.b.hash_value), len(self.c.hash_value)),
            (1, 2, 5),
        )

    def tearDown(self):
        if getattr(self, "backend", None) is not None:
            self.backend.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _seed_and_recycle_head_slot(self):
        """Write the whole chain (p0,p1,p2 land in slot 0; p3+ in later slots),
        then drop slot 0 as the allocator's circular cursor does at wrap."""
        self.assertTrue(
            all(
                self.backend.batch_set_v1(
                    self.chain, torch.tensor(list(range(len(self.chain))))
                )
            )
        )
        refs = {
            k[:6]: v.extent_id for k, v in self.backend._allocator._index.items()
        }
        self.assertTrue(
            refs[self.chain[0][:6]] == refs[self.chain[1][:6]] == refs[self.chain[2][:6]]
        )
        self.assertNotEqual(refs[self.chain[3][:6]], refs[self.chain[0][:6]])
        self.backend._append_drops([(0, 1)])
        self.backend._allocator.apply_drops([(0, 1)])
        for key in list(self.backend._components):
            if key not in self.backend._allocator._index:
                self.backend._components.pop(key, None)

    def _h0_set_seqs(self):
        wal = em.segment_path(
            self.backend._storage_dir,
            self.backend.config_suffix,
            self.backend._wal_generation,
        )
        with open(wal, "rb") as handle:
            raw = handle.read()
        off, drop_seq, seqs = em.SEGMENT_HEADER_SIZE, None, []
        want = self.backend._storage_key(self.chain[0])
        while off < len(raw):
            ftype, seq, payload, consumed = em.decode_frame(raw[off:])
            off += consumed
            if ftype == em.FRAME_DROP_SLOT:
                drop_seq = seq
            elif ftype == em.FRAME_SET:
                for entry in em.decode_set_payload(payload).entries:
                    if entry.storage_key.decode() == want:
                        seqs.append(seq)
        return drop_seq, seqs

    def test_head_loss_reproduces_false_negative(self):
        """The runtime predicate: 0 hits from page 0, the full run from page 3."""
        self._seed_and_recycle_head_slot()
        self.assertEqual(self.backend.batch_exists(self.chain, None), 0)
        self.assertEqual(
            self.backend.batch_exists(self.chain[3:], None), len(self.chain) - 3
        )

    def test_backup_spec_refreshes_chain_head_page(self):
        """The fix: an ordinary backup of C re-submits p0 so it stops being
        write-once (SET for p0 with a later seq than the DROP_SLOT of its slot).
        Fails on the unpatched tree: the spec starts at p3, p0 is never
        re-written, and the refresh SET below is absent."""
        self._seed_and_recycle_head_slot()
        spec = self.cache.tree_core.build_storage_backup_spec(self.c.id, False)
        self.assertEqual(spec.hash_value[0], self.chain[0])
        self.assertEqual(len(spec.host_value), len(spec.hash_value))
        self.assertTrue(
            all(self.backend.batch_set_v1(spec.hash_value, spec.host_value))
        )
        self.assertTrue(self.backend.exists(self.chain[0]))
        drop_seq, seqs = self._h0_set_seqs()
        self.assertIsNotNone(drop_seq)
        self.assertTrue(
            any(seq > drop_seq for seq in seqs),
            f"p0 was not re-SET after the slot DROP_SLOT (seqs={seqs}, drop={drop_seq})",
        )

    def test_single_page_refresh_leaves_head_run_unrefreshed(self):
        """KNOWN F1 GAP (blocker): refreshing only p0 does not restore the
        chain. p1,p2 (node B) share the recycled slot and stay write-once, so
        batch_exists still stops at p1 and the query is still a false miss.
        This test pins the observed residual so the gap cannot regress
        silently; it passes only once the whole write-once head run is
        refreshed (or the head slot is pinned)."""
        self._seed_and_recycle_head_slot()
        spec = self.cache.tree_core.build_storage_backup_spec(self.c.id, False)
        self.backend.batch_set_v1(spec.hash_value, spec.host_value)
        self.assertTrue(self.backend.exists(self.chain[0]))
        self.assertFalse(self.backend.exists(self.chain[1]))
        self.assertEqual(self.backend.batch_exists(self.chain, None), 1)
        self.assertLess(
            self.backend.batch_exists(self.chain, None),
            len(self.chain),
            "F1 persists: the single-page head refresh leaves p1,p2 write-once",
        )


if __name__ == "__main__":
    unittest.main()
