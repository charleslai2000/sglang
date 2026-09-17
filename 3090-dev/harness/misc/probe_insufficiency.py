"""Faithful 3-node F1 model: A=[p0], B=[p1,p2], C=[p3..]; one-page head
refresh moves p0 out of the recycled slot but leaves p1,p2 lost, so the
predicate still stops at p1."""
import ctypes
import hashlib
import os
import struct
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
from sglang.srt.mem_cache.hicache_storage import HiCacheStorageConfig
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
        ptrs = [ctypes.addressof(ctypes.c_char.from_buffer(self._pages[i])) for i in idx]
        return ptrs, [self._page_bytes] * len(ptrs)


def _oracle_get_native_hash(token_ids, prior_digest, page_size=None):
    raw = token_ids.raw_token_ids() if hasattr(token_ids, "raw_token_ids") else token_ids
    tokens = list(raw)
    prior = prior_digest if prior_digest else None
    data = b"".join(struct.pack("<I", t & 0xFFFFFFFF) for t in tokens)
    out, has = [], prior is not None
    step = page_size or len(tokens)
    for start in range(0, len(tokens), step):
        ctx = hashlib.sha256()
        if has:
            ctx.update(prior)
        ctx.update(data[start * 4 : (start + step) * 4])
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
    tmp = tempfile.mkdtemp(prefix="f1_insuff_")
    cfg = HiCacheStorageConfig(
        extra_config={"storage_dir": tmp, "extent_size": "16Ki", "file_size": "64Ki"},
        tp_rank=0, tp_size=1, pp_rank=0, pp_size=1,
        attn_cp_rank=0, attn_cp_size=1, is_mla_model=False,
        enable_storage_metrics=False, is_page_first_layout=True, model_name="f1insuff",
    )
    backend = ExtentFileBackend(cfg)
    backend.register_mem_pool_host(_ZeroCopyPool(PAGE_BYTES, 64))

    toks = [11, 22, 33, 44, 55, 66, 77, 88]
    cache, alloc = _make_cache(64)
    a = _insert(cache, alloc, toks[:1])          # A = [p0]
    b = _insert(cache, alloc, toks[:3])          # A split -> B = [p1,p2]
    c = _insert(cache, alloc, toks)              # C = [p3..p7]
    print("A", len(a.hash_value), "B", len(b.hash_value), "C", len(c.hash_value),
          "B.parent_is_A", b.parent is a, "C.parent_is_B", c.parent is b)
    for n in (a, b, c):
        n.component_data[ComponentType.FULL].host_value = torch.tensor(
            list(range(10, 10 + len(n.hash_value))), dtype=torch.int64
        )
    chain = list(a.hash_value) + list(b.hash_value) + list(c.hash_value)
    print("chain", len(chain), [x[:6] for x in chain])

    seed = backend.batch_set_v1(chain, torch.tensor(list(range(8)), dtype=torch.int64))
    refs = {k[:6]: (v.extent_id, v.offset) for k, v in backend._allocator._index.items()}
    print("seed", seed, "refs", refs)

    backend._append_drops([(0, 1)])
    backend._allocator.apply_drops([(0, 1)])
    for key in list(backend._components):
        if key not in backend._allocator._index:
            backend._components.pop(key, None)
    print("after drop: batch_exists(chain) =", backend.batch_exists(chain, None),
          " batch_exists(chain[3:]) =", backend.batch_exists(chain[3:], None),
          " (len", len(chain), "/", len(chain[3:]), ")")

    spec = cache.tree_core.build_storage_backup_spec(c.id, False)
    print("spec for C: n_keys", len(spec.hash_value),
          "keys", [x[:6] for x in spec.hash_value],
          "head_prepended", spec.hash_value[0] == chain[0])
    backend.batch_set_v1(spec.hash_value, spec.host_value)
    print("AFTER FIX(rewrite spec): batch_exists(chain) =", backend.batch_exists(chain, None),
          " expected_full =", len(chain))
    print("p0", backend.exists(chain[0]), "p1", backend.exists(chain[1]),
          "p2", backend.exists(chain[2]), "p3", backend.exists(chain[3]))
    wal = em.segment_path(backend._storage_dir, backend.config_suffix, backend._wal_generation)
    raw = open(wal, "rb").read()
    off, drop_seq, h0_seqs = em.SEGMENT_HEADER_SIZE, None, []
    while off < len(raw):
        ft, seq, payload, consumed = em.decode_frame(raw[off:])
        off += consumed
        if ft == em.FRAME_DROP_SLOT:
            drop_seq = seq
        if ft == em.FRAME_SET:
            for e in em.decode_set_payload(payload).entries:
                if e.storage_key.decode() == backend._storage_key(chain[0]):
                    h0_seqs.append(seq)
    print("WAL drop_seq", drop_seq, "h0 SET seqs", h0_seqs,
          "h0_refreshed_after_drop", any(s > (drop_seq or -1) for s in h0_seqs))
    backend.close()


if __name__ == "__main__":
    main()
