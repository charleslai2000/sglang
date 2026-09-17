"""Integration probe: real ExtentFileBackend + tree spec head refresh."""
import ctypes
import hashlib
import struct
import sys
import tempfile
from array import array
from unittest.mock import patch

import torch

from sglang.srt.mem_cache.allocator import TokenToKVPoolAllocator
from sglang.srt.mem_cache.base_prefix_cache import InsertParams
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.memory_pool import MHATokenToKVPool, ReqToTokenPool
from sglang.srt.mem_cache.radix_cache import RadixKey
from sglang.srt.mem_cache.unified_cache.components import ComponentType
from sglang.srt.mem_cache.unified_radix_cache import UnifiedRadixCache
from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig, PoolName
from sglang.srt.mem_cache.storage.extent.extent_file_backend import ExtentFileBackend
from sglang.srt.mem_cache.storage.extent import extent_metadata as em

PAGE_BYTES = 5000


class _ZeroCopyPool:
    def __init__(self, page_bytes, slots):
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
    raw = token_ids.raw_token_ids() if hasattr(token_ids, "raw_token_ids") else token_ids
    tokens = list(raw)
    prior = prior_digest if prior_digest else None
    data = b"".join(struct.pack("<I", t & 0xFFFFFFFF) for t in tokens)
    out, has = [], prior is not None
    for start in range(0, len(tokens), page_size or len(tokens)):
        ctx = hashlib.sha256()
        if has:
            ctx.update(prior)
        ctx.update(data[start * 4 : (start + (page_size or len(tokens))) * 4])
        prior = ctx.digest()
        has = True
        out.append(prior.hex())
    return out[-1] if page_size is None else out


def _make_cache(cap_pages):
    kv_pool = MHATokenToKVPool(
        size=cap_pages, page_size=1, dtype=torch.float16, head_num=2, head_dim=8,
        layer_num=1, device="cpu", enable_memory_saver=False,
    )
    allocator = TokenToKVPoolAllocator(
        size=cap_pages, dtype=torch.float16, device="cpu", kvcache=kv_pool, need_sort=False,
    )
    req_pool = ReqToTokenPool(
        size=8, max_context_len=cap_pages + 64, device="cpu", enable_memory_saver=False,
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
        InsertParams(key=RadixKey(array("q", token_ids)), value=indices.to(torch.int64))
    ).last_device_node
    return cache.tree_core.node_by_id(node_id)


@patch("sglang.srt.mem_cache.utils.get_native_hash", _oracle_get_native_hash)
def main():
    tmp = tempfile.mkdtemp(prefix="f1_integ_")
    cfg = HiCacheStorageConfig(
        extra_config={"storage_dir": tmp, "extent_size": "16Ki", "file_size": "64Ki"},
        tp_rank=0, tp_size=1, pp_rank=0, pp_size=1,
        attn_cp_rank=0, attn_cp_size=1, is_mla_model=False,
        enable_storage_metrics=False, is_page_first_layout=True, model_name="f1integ",
    )
    backend = ExtentFileBackend(cfg)
    pool = _ZeroCopyPool(PAGE_BYTES, 64)
    backend.register_mem_pool_host(pool)

    toks = [11, 22, 33, 44, 55, 66, 77, 88]
    cache, _alloc = _make_cache(64)
    head = _insert(cache, _alloc, toks[:1])
    desc = _insert(cache, _alloc, toks)
    head.component_data[ComponentType.FULL].host_value = torch.tensor([0], dtype=torch.int64)
    desc.component_data[ComponentType.FULL].host_value = torch.tensor(
        list(range(10, 10 + len(desc.hash_value))), dtype=torch.int64
    )
    h = [head.hash_value[0]] + list(desc.hash_value)  # [h0,h1,h2]
    print("h0", h[0][:12], "n_chain", len(h))

    # Seed the store: write h0 into slot0 and h1,h2 into slot0 too.
    res = backend.batch_set_v1(h[:3], torch.tensor([0, 10, 11], dtype=torch.int64))
    print("seed write", res)
    print("exists h0", backend.exists(h[0]), "exists h1", backend.exists(h[1]))
    print("slot0 refs", {k[:6]: (v.extent_id, v.offset) for k, v in backend._allocator._index.items()})

    # Force the slot holding the head page to be recycled.
    backend._append_drops([(0, 1)])
    backend._allocator.apply_drops([(0, 1)])
    for key in list(backend._components):
        ref = backend._allocator._index.get(key)
        if ref is None and key not in backend._allocator._index:
            backend._components.pop(key, None)
    print("after drop exists h0", backend.exists(h[0]))
    print("batch_exists full", backend.batch_exists(h[:3], None))
    print("batch_exists from h1", backend.batch_exists(h[1:3], None))
    print("slot after", {k[:6]: (v.extent_id, v.offset) for k, v in backend._allocator._index.items()})

    # Re-write the DESC spec (patched tree prepends the head page).
    spec = cache.tree_core.build_storage_backup_spec(desc.id, False)
    print("spec head", spec.hash_value[0][:12], "== h0:", spec.hash_value[0] == h[0])
    res2 = backend.batch_set_v1(spec.hash_value, spec.host_value)
    print("rewrite", res2, "exists h0 after rewrite", backend.exists(h[0]))

    # WAL: find the SET containing h0 after the drop.
    with open(backend._wal_path(), "rb") as f:
        raw = f.read()
    off, seqs_h0, drop_seq = em.SEGMENT_HEADER_SIZE, [], None
    while off < len(raw):
        ftype, seq, payload, consumed = em.decode_frame(raw[off:])
        off += consumed
        if ftype == em.FRAME_DROP_SLOT:
            drop_seq = seq
        if ftype == em.FRAME_SET:
            p = em.decode_set_payload(payload)
            for e in p.entries:
                if e.storage_key.decode() == backend._storage_key(h[0]):
                    seqs_h0.append(seq)
    print("drop_seq", drop_seq, "h0_set_seqs", seqs_h0,
          "refreshed_after_drop", any(s > (drop_seq or -1) for s in seqs_h0))
    backend.close()


if __name__ == "__main__":
    main()
