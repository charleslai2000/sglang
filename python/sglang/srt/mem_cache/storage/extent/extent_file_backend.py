# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to SGLang project

"""ExtentFileBackend: HiCacheStorage over a single preallocated sparse file.

Replaces HiCacheFile's per-key .bin files (a 20K-page restore is ~63K
open/read/close syscalls) with aggregated IO: a batch of consecutive page
writes packs into fixed-size extents (default 64 MiB), so one pwritev covers
the whole batch.  The extent is an *allocation* unit, not a read unit: a
batch read sorts its requested refs by offset and preads each merged exact
range (adjacent ranges with a gap of at most one 4KiB sector merge), so only
the bytes the request covers are read.  The RAM index (``ExtentAllocator``)
maps storage key -> ExtentRef{extent_id, offset, length, generation}; slot
reuse or watermark GC bumps the generation and any stale entry fails the
read-side re-verify (generation mismatch = miss).

Durability contract is unchanged from HiCacheFile: the tree layer only trusts
the ACK, and ACK here means pwrite success + index registration (no fsync,
matching the current semantics; a crash leaves the file orphaned and the
restart starts cold -- no metadata persistence). v1 is the main KV path
(controller batches at STORAGE_BATCH_SIZE=1024): the batch_get_v1/batch_set_v1
zero-copy surface pread/pwrite directly into the host pool buffers that
``get_page_buffer_meta`` describes (k/v dual blocks per page_first MHA page,
one syscall per merged exact range), so the engine-side dummy-page allocation
and per-page scatter loops disappear. v2 keeps the sidecar-pool semantics with
per-pool component keys (``key.<pool>``) packed into their own extents.

First slice uses buffered IO; ``SGLANG_HICACHE_EXTENT_BACKEND_DIRECT_IO`` is
reserved for the O_DIRECT calibration tier -- page lengths are not 4KiB
aligned, so only whole-extent aligned IO could use O_DIRECT safely.
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
from typing import Any, List, Optional

from sglang.srt.environ import envs
from sglang.srt.mem_cache.hicache_storage import (
    HiCacheStorage,
    HiCacheStorageConfig,
    HiCacheStorageExtraInfo,
    PoolHitPolicy,
    PoolName,
    PoolTransfer,
    PoolTransferResult,
)
from sglang.srt.mem_cache.storage.extent.extent_allocator import ExtentAllocator
from sglang.srt.mem_cache.storage.file.lru_file_evictor import _parse_size_to_bytes

logger = logging.getLogger(__name__)

# B1 fixed default (ledger: 64MiB tier of the 64/128 decision); env-switchable.
_DEFAULT_EXTENT_SIZE = 64 << 20
# B3 single-file layout: 64 GiB sparse preallocation per rank/suffix.
_DEFAULT_FILE_SIZE = 64 << 30
# Read-side merge threshold: adjacent requested ranges whose gap is at most
# one 4KiB sector are merged into a single exact pread.  Absorbing a <=4KiB
# dead gap is bounded amplification (<= 1.13x on a ~31KB page) and keeps
# contiguous page clusters at one syscall; larger gaps stay separate
# exact-range reads so sparse requests never drag in extent fill.
_MERGE_GAP_THRESHOLD = 4096
# Linux caps iovecs per readv/pwritev syscall at IOV_MAX = UIO_MAXIOV =
# 1024 (measured on the 3090 box and locally: 1024 iovecs OK, 1025 EINVAL).
# The v1 batch packs 2 blocks per page, so a 1024-page batch is 2048 iovecs
# and the IO helpers shard at this boundary.
_IOV_MAX = 1024


def _merge_requested_ranges(items):
    """Coalesce requested (offset, length, index) refs into exact pread ranges.

    Items are sorted by offset; the running range [start, end) absorbs the
    next item when the gap (item.start - end) is at most _MERGE_GAP_THRESHOLD
    bytes.  Returns a list of (start, end, [index...]) where each returned
    range is the exact byte span one pread must cover -- never a whole
    extent, never a span over unrequested bytes beyond the threshold.
    """
    ranges = []
    for offset, length, idx in sorted(items):
        start, end = offset, offset + length
        if ranges and start - ranges[-1][1] <= _MERGE_GAP_THRESHOLD:
            prev = ranges[-1]
            prev[1] = max(prev[1], end)
            prev[2].append(idx)
        else:
            ranges.append([start, end, [idx]])
    return ranges


def _page_byte_view(value) -> memoryview:
    """Zero-copy raw-byte view of a page value.

    torch CPU tensors (the host pool's flat pages) share memory via a
    bit-level uint8 reinterpretation -- ``contiguous().cpu().view(torch.uint8)``
    aliases the storage without copying, and unlike a bare ``.numpy()`` it
    also accepts bf16/fp16 (numpy raises ``TypeError: Got unsupported
    ScalarType BFloat16`` on those dtypes; M2 crash).  Non-CPU tensors are
    copied to CPU only if needed; byte-like buffers are used as-is.
    No torch import at module top.
    """
    if isinstance(value, (bytes, bytearray, memoryview)):
        return memoryview(value)
    if hasattr(value, "contiguous"):
        # torch.Tensor (or tensor-like): bit-level uint8 view, zero-copy for
        # contiguous CPU tensors (the host pool's flat pages).  Same path as
        # HiCacheFile.set (hicache_storage.py), which writes
        # value.contiguous().view(dtype=torch.uint8).numpy().
        import torch

        value = value.contiguous().cpu().view(torch.uint8)
    arr = value.numpy()
    if not arr.flags["C_CONTIGUOUS"]:
        arr = arr.copy()
    return memoryview(arr).cast("B")


def _target_byte_view(target) -> memoryview:
    """Writable zero-copy byte view of a flat page target."""
    if isinstance(target, (bytearray, memoryview)):
        return memoryview(target)
    if hasattr(target, "contiguous"):
        # torch.Tensor target: bit-level uint8 view so the stored bytes can
        # be filled back into a bf16/fp16/fp32 flat page (mirror of the
        # write side; HiCacheFile.get fills the same way).  Writable for
        # contiguous no-grad CPU tensors.
        import torch

        target = target.contiguous().cpu().view(torch.uint8)
    arr = target.numpy()
    if not arr.flags["C_CONTIGUOUS"]:
        arr = arr.copy()
    return memoryview(arr).cast("B")


def _config_value(extra: dict, key: str, env_field):
    """extra_config (per-backend) takes precedence over the env var."""
    val = extra.get(key)
    return env_field.get() if val is None else val


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


class ExtentFileBackend(HiCacheStorage):
    def __init__(self, storage_config: HiCacheStorageConfig, file_path=None):
        extra = storage_config.extra_config or {}
        # --- config_suffix: exact replica of HiCacheFile (hicache_storage.py) ---
        tp_rank, tp_size, pp_rank, pp_size = (
            storage_config.tp_rank,
            storage_config.tp_size,
            storage_config.pp_rank,
            storage_config.pp_size,
        )
        attn_cp_rank = storage_config.attn_cp_rank
        attn_cp_size = storage_config.attn_cp_size
        model_name = storage_config.model_name
        is_mla_model = storage_config.is_mla_model
        model_name = "-".join(model_name.split("/")) if model_name else ""
        enable_pp = pp_size > 1
        self.config_suffix = f"_{model_name}"
        if not is_mla_model:
            self.config_suffix += f"_{tp_rank}_{tp_size}"
        if enable_pp:
            self.config_suffix += f"_{pp_size}_{pp_rank}"
        # Under NSA context parallel each CP rank holds a disjoint slice of
        # every page, so give each rank its own file to avoid a cross-rank
        # write race (same isolation rationale as HiCacheFile's key suffix).
        if attn_cp_size > 1:
            self.config_suffix += f"_cp{attn_cp_rank}_{attn_cp_size}"

        self._storage_dir = (
            _config_value(
                extra, "storage_dir", envs.SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR
            )
            or file_path
            or "/tmp/hicache"
        )
        if not os.path.exists(self._storage_dir) and tp_rank == 0 and attn_cp_rank == 0:
            os.makedirs(self._storage_dir)
            logger.info(
                f"Created ExtentFileBackend storage directory at {self._storage_dir}"
            )

        extent_size = (
            _parse_size_to_bytes(
                _config_value(
                    extra, "extent_size", envs.SGLANG_HICACHE_EXTENT_BACKEND_EXTENT_SIZE
                )
            )
            or _DEFAULT_EXTENT_SIZE
        )
        file_size = (
            _parse_size_to_bytes(
                _config_value(
                    extra, "file_size", envs.SGLANG_HICACHE_EXTENT_BACKEND_FILE_SIZE
                )
            )
            or _DEFAULT_FILE_SIZE
        )
        if extent_size % 4096 != 0:
            raise ValueError(
                f"extent_size must be a multiple of 4096, got {extent_size}"
            )
        if file_size < extent_size:
            raise ValueError(
                f"file_size {file_size} must be >= extent_size {extent_size}"
            )
        self._extent_size = extent_size
        self._file_size = file_size
        self._max_size_bytes = _parse_size_to_bytes(
            _config_value(extra, "max_size", envs.SGLANG_HICACHE_EXTENT_BACKEND_MAX_SIZE)
        )
        self._min_free_bytes = _parse_size_to_bytes(
            _config_value(
                extra, "min_free_space", envs.SGLANG_HICACHE_EXTENT_BACKEND_MIN_FREE_SPACE
            )
        )
        ratio_raw = extra.get("eviction_ratio")
        try:
            self._eviction_ratio = float(ratio_raw) if ratio_raw is not None else 0.9
        except (TypeError, ValueError):
            self._eviction_ratio = 0.9
        self._direct_io = _as_bool(
            _config_value(
                extra, "direct_io", envs.SGLANG_HICACHE_EXTENT_BACKEND_DIRECT_IO
            )
        )
        if self._direct_io:
            logger.warning(
                "SGLANG_HICACHE_EXTENT_BACKEND_DIRECT_IO is reserved for the "
                "O_DIRECT calibration tier; this slice uses buffered IO."
            )

        # One data file per rank/config suffix: ranks never share an allocator.
        self._data_path = os.path.join(
            self._storage_dir, f"hicache.data{self.config_suffix}"
        )
        self._lock = threading.Lock()
        self._stats = {
            "opens": 0,
            "preads": 0,
            "pwrites": 0,
            "bytes_read": 0,
            "bytes_written": 0,
            # Read-amplification accounting (P0 fix: exact-range reads).
            # requested_bytes = ref lengths of read batches; physical_bytes_read
            # = merged pread spans; the ratio target is < 1.2x.  prefetch_bytes_read
            # stays 0: this backend has no prefetch logic, every pread is
            # request-driven (engine-side proactive prefetch arrives as ordinary
            # batch_get/batch_get_v2 and is counted like any other read).
            "requested_bytes": 0,
            "physical_bytes_read": 0,
            "prefetch_bytes_read": 0,
            "last_batch_requested_bytes": 0,
            "last_batch_physical_bytes": 0,
            "last_batch_preads": 0,
        }
        self._fd = os.open(self._data_path, os.O_CREAT | os.O_RDWR, 0o644)
        self._stats["opens"] += 1
        os.ftruncate(self._fd, self._file_size)
        self._allocator = ExtentAllocator(extent_size, self._file_size // extent_size)
        logger.info(
            f"ExtentFileBackend: file={self._data_path} extent={extent_size} B "
            f"slots={self._file_size // extent_size} "
            f"max_size={self._max_size_bytes} min_free={self._min_free_bytes}"
        )

    # ---- key scoping (same semantics as HiCacheFile) ----
    # v1 and v2 share the same transform: the engine writes via v1 batch_set
    # and queries via v2 batch_exists_v2, so both sides must produce the same
    # storage key (bare keys on one side only = storage_hit always 0).

    def _storage_key(self, key: str) -> str:
        return key + self.config_suffix

    def _component_key(self, pool_name, key: str) -> str:
        if pool_name is None or pool_name == "__default__" or pool_name == PoolName.KV:
            return self._storage_key(key)
        return self._storage_key(f"{key}.{pool_name}")

    # ---- v1: single-key surface ----

    def get(
        self,
        key: str,
        target_location: Optional[Any] = None,
        target_sizes: Optional[Any] = None,
    ):
        storage_key = self._storage_key(key)
        page = self._read_pages([storage_key])[0]
        if page is None or target_location is None:
            return None
        view = _target_byte_view(target_location)
        if len(view) != len(page):
            logger.warning(
                f"ExtentFileBackend: size mismatch for {storage_key}: "
                f"stored {len(page)} B vs target {len(view)} B"
            )
            return None
        view[:] = page
        return target_location

    def set(
        self,
        key: str,
        value: Optional[Any] = None,
        target_location: Optional[Any] = None,
        target_sizes: Optional[Any] = None,
    ) -> bool:
        if value is None:
            return False
        return self._write_pages([self._storage_key(key)], [value])

    def exists(self, key: str) -> bool:
        with self._lock:
            return self._allocator.lookup(self._storage_key(key)) is not None

    # ---- v1: batched surface (main KV path) ----

    def batch_get(
        self,
        keys: List[str],
        target_locations: Optional[Any] = None,
        target_sizes: Optional[Any] = None,
    ) -> List[Any]:
        storage_keys = [self._storage_key(key) for key in keys]
        pages = self._read_pages(storage_keys)
        targets = target_locations or [None] * len(keys)
        out = []
        for page, target in zip(pages, targets):
            if page is None or target is None:
                out.append(None)
                continue
            view = _target_byte_view(target)
            if len(view) != len(page):
                logger.warning(
                    f"ExtentFileBackend: size mismatch for a page: "
                    f"stored {len(page)} B vs target {len(view)} B"
                )
                out.append(None)
                continue
            view[:] = page
            out.append(target)
        return out

    def _log_extent_write(
        self, component, node_id, storage_keys, sizes
    ) -> None:
        """[P3] extent_write instrumentation: one record per successful
        extent (component) batch. ``sizes`` are the per-key byte lengths.
        Node identity comes from the caller's extra_info (instrumentation-
        only; the write path ignores it)."""
        try:
            total = sum(len(v) for v in sizes)
        except TypeError:
            total = sum(sizes)
        logger.info(
            "[P3] ts_ms=%d evt=extent_write node=%s component=%s "
            "keys_n=%d bytes=%d",
            int(time.time() * 1000),
            node_id,
            component,
            len(storage_keys),
            total,
        )

    def batch_set(
        self,
        keys: List[str],
        values: Optional[Any] = None,
        target_locations: Optional[Any] = None,
        target_sizes: Optional[Any] = None,
    ) -> bool:
        if values is None or len(values) != len(keys):
            return False
        storage_keys = [self._storage_key(key) for key in keys]
        ok = self._write_pages(storage_keys, values)
        if ok:
            self._log_extent_write("kv", None, storage_keys, values)
        return ok

    def batch_exists(
        self, keys: List[str], extra_info: Optional[HiCacheStorageExtraInfo] = None
    ) -> int:
        with self._lock:
            for i, key in enumerate(keys):
                if self._allocator.lookup(self._storage_key(key)) is None:
                    return i
            return len(keys)

    # ---- v1: zero-copy surface (anchor KV pool, direct-to-buffer IO) ----

    def batch_get_v1(
        self,
        keys: List[str],
        host_indices,
        extra_info: Optional[HiCacheStorageExtraInfo] = None,
    ) -> List[bool]:
        """Zero-copy read: preadv merged exact ranges into the host pool.

        The target buffers come from ``get_page_buffer_meta(host_indices)``;
        the stored flat page bytes are the concatenation of the per-page
        blocks in pool order (k block then v block for a page_first MHA
        pool), so one preadv per merged exact range scatters the whole batch
        into the pool with no intermediate page buffers.  Dead gap bytes
        inside a merged range land in scratch bytearrays and are discarded.
        A generation mismatch (slot reused since the snapshot) or a short
        read marks the affected keys as misses; the engine never consumes
        those host slots, so partially written bytes are harmless.  Returns
        one bool per key; never raises, never returns None.
        """
        if len(keys) == 0:
            return []
        meta = self._v1_buffer_meta(keys, host_indices, "batch_get_v1")
        if meta is None:
            return [False] * len(keys)
        ptr_list, size_list, blocks_per_page, _ = meta
        storage_keys = [self._storage_key(k) for k in keys]
        page_lens = [
            sum(size_list[i * blocks_per_page : (i + 1) * blocks_per_page])
            for i in range(len(keys))
        ]
        blocks = self._v1_host_blocks(ptr_list, size_list, blocks_per_page)
        with self._lock:
            refs = self._allocator.snapshot(storage_keys)
        # A ref whose length differs from the current pool layout was written
        # under a different layout; refusing beats scattering bytes into the
        # wrong blocks.
        items = [
            (ref.offset, ref.length, i)
            for i, ref in enumerate(refs)
            if ref is not None and ref.length == page_lens[i]
        ]
        groups: dict = {}
        for offset, length, i in items:
            groups.setdefault(refs[i].extent_id, []).append((offset, length, i))
        ok = [False] * len(keys)
        requested = 0
        physical = 0
        preads = 0
        for extent_id, triples in groups.items():
            requested += sum(t[1] for t in triples)
            for start, end, idx_list in _merge_requested_ranges(triples):
                iovecs = []
                prev_end = start
                for i in idx_list:
                    ref = refs[i]
                    gap = ref.offset - prev_end
                    if gap > 0:
                        iovecs.append(bytearray(gap))
                    iovecs.extend(blocks[i])
                    prev_end = ref.offset + ref.length
                if (
                    self._preadv_full(extent_id * self._extent_size + start, iovecs)
                    != end - start
                ):
                    logger.error(
                        f"ExtentFileBackend: short pread for extent {extent_id}"
                    )
                    continue
                physical += end - start
                preads += 1
                for i in idx_list:
                    ok[i] = True
        with self._lock:
            verify_ok = self._allocator.verify(storage_keys, refs)
            for i, key in enumerate(storage_keys):
                if ok[i] and verify_ok[i]:
                    self._allocator.touch(key)
        self._stats["requested_bytes"] += requested
        self._stats["physical_bytes_read"] += physical
        self._stats["last_batch_requested_bytes"] = requested
        self._stats["last_batch_physical_bytes"] = physical
        self._stats["last_batch_preads"] = preads
        return [o and v for o, v in zip(ok, verify_ok)]

    def batch_set_v1(
        self,
        keys: List[str],
        host_indices,
        extra_info: Optional[HiCacheStorageExtraInfo] = None,
    ) -> List[bool]:
        """Zero-copy write: pwritev the host pool blocks into packed extents.

        The per-page blocks (k block then v block for page_first MHA) are
        pwritten in pool order at each ref, reconstructing the flat page
        bytes the read paths and the engine's flat-page API expect.  The
        plan -> pwrite -> commit sequence holds the index lock (same
        all-or-nothing semantics as ``_write_pages``); a refused batch
        returns all False.
        """
        if len(keys) == 0:
            return []
        meta = self._v1_buffer_meta(keys, host_indices, "batch_set_v1")
        if meta is None:
            return [False] * len(keys)
        ptr_list, size_list, blocks_per_page, _ = meta
        storage_keys = [self._storage_key(k) for k in keys]
        page_lens = [
            sum(size_list[i * blocks_per_page : (i + 1) * blocks_per_page])
            for i in range(len(keys))
        ]
        blocks = self._v1_host_blocks(ptr_list, size_list, blocks_per_page)
        with self._lock:
            self._gc_evict()
            refs, passed = self._allocator.plan(list(zip(storage_keys, page_lens)))
            if any(r is None for r in refs):
                logger.warning(
                    "ExtentFileBackend: batch_set_v1 of %s pages refused "
                    "(page larger than extent_size %s B)",
                    len(keys),
                    self._extent_size,
                )
                return [False] * len(keys)
            groups: dict = {}
            for i, ref in enumerate(refs):
                groups.setdefault(ref.extent_id, []).append(i)
            for extent_id, idxs in groups.items():
                ordered = sorted(idxs, key=lambda i: refs[i].offset)
                first = refs[ordered[0]].offset
                iovecs = []
                for i in ordered:
                    iovecs.extend(blocks[i])
                if not self._pwritev(extent_id * self._extent_size + first, iovecs):
                    return [False] * len(keys)
            self._allocator.commit(storage_keys, refs, passed)
            self._log_extent_write(
                "kv", getattr(extra_info, "node_id", None), storage_keys, page_lens
            )
            return [True] * len(keys)

    def _v1_buffer_meta(self, keys, host_indices, op_name):
        """Resolve the v1 host-pool buffer contract; None on any violation.

        v1 targets the anchor KV pool (``register_mem_pool_host``): the pool
        must expose ``get_page_buffer_meta``, host_indices must carry
        page_size slots per key, and the per-key block count must divide
        evenly.  The scatter relies on the flat page bytes being the
        concatenation of the blocks in pool order -- true for the
        page-first family (MHA k/v dual blocks, Mamba temporal+conv, MLA
        single block) but not for layer_first, which interleaves per-layer
        k/v blocks; layer_first is refused rather than corrupted.
        """
        pool = getattr(self, "mem_pool_host", None)
        if pool is None or not callable(getattr(pool, "get_page_buffer_meta", None)):
            logger.error(
                "ExtentFileBackend %s: no host pool with get_page_buffer_meta "
                "registered (register_mem_pool_host).",
                op_name,
            )
            return None
        page_size = getattr(pool, "page_size", 1) or 1
        if len(host_indices) != len(keys) * page_size:
            logger.error(
                "ExtentFileBackend %s: host_indices length %s != keys %s x "
                "page_size %s",
                op_name,
                len(host_indices),
                len(keys),
                page_size,
            )
            return None
        if getattr(pool, "layout", "") == "layer_first":
            logger.error(
                "ExtentFileBackend %s: layer_first pool layout is not "
                "supported by the v1 flat-page scatter; refusing.",
                op_name,
            )
            return None
        try:
            ptr_list, size_list = pool.get_page_buffer_meta(host_indices)
        except Exception as e:
            logger.error(
                "ExtentFileBackend %s: get_page_buffer_meta failed: %s", op_name, e
            )
            return None
        if not ptr_list or len(ptr_list) != len(size_list):
            logger.error(
                "ExtentFileBackend %s: empty or mismatched buffer meta", op_name
            )
            return None
        blocks_per_page = len(ptr_list) // len(keys)
        if len(ptr_list) % len(keys) != 0 or blocks_per_page == 0:
            logger.error(
                "ExtentFileBackend %s: %s buffer blocks for %s keys is not a "
                "whole per-key count",
                op_name,
                len(ptr_list),
                len(keys),
            )
            return None
        return ptr_list, size_list, blocks_per_page, page_size

    def _v1_host_blocks(self, ptr_list, size_list, blocks_per_page):
        """ctypes arrays aliasing the host pool blocks for direct fd IO."""
        blocks = []
        for i in range(0, len(ptr_list), blocks_per_page):
            blocks.append(
                [
                    (ctypes.c_char * size_list[i + j]).from_address(ptr_list[i + j])
                    for j in range(blocks_per_page)
                ]
            )
        return blocks

    # ---- v2: sidecar-pool surface ----

    def batch_exists_v2(
        self,
        keys: List[str],
        pool_transfers: Optional[List[PoolTransfer]] = None,
        extra_info: Optional[HiCacheStorageExtraInfo] = None,
    ) -> PoolTransferResult:
        with self._lock:

            def present(key: str) -> bool:
                return self._allocator.lookup(key) is not None

            kv_pages = next(
                (i for i in range(len(keys)) if not present(self._storage_key(keys[i]))),
                len(keys),
            )
            hit_count: dict = {PoolName.KV: kv_pages} if kv_pages else {}
            final_pages = kv_pages
            for transfer in pool_transfers or []:
                if final_pages == 0:
                    break
                name = transfer.name
                # A PREFETCH transfer's keys are placeholders at build time
                # (mamba_component / swa_component write node-last checkpoints;
                # the real trailing hashes are filled only after the hit query
                # by _sync_trailing_keys).  Such a transfer must use the
                # TRAILING scan: these pools store only a trailing window, so
                # reading them as ALL_PAGES -- the PoolTransfer default, which
                # takes over when a transfer reconstruction drops the policy --
                # fails at the first non-window page and clamps kv_hit to 0
                # (live 3090 M4, storage_hit=0 for every hybrid prefetch).
                placeholder_keys = bool(transfer.keys) and all(
                    k == "__placeholder__" for k in transfer.keys
                )
                if transfer.hit_policy == PoolHitPolicy.ALL_PAGES and not placeholder_keys:
                    boundary = next(
                        (
                            i
                            for i in range(kv_pages)
                            if not present(self._component_key(name, keys[i]))
                        ),
                        kv_pages,
                    )
                else:  # trailing_pages
                    trailing = max(1, len(transfer.keys) if transfer.keys else 1)
                    boundary = 0
                    for prefix_len in range(kv_pages, 0, -1):
                        if all(
                            present(self._component_key(name, keys[i]))
                            for i in range(max(0, prefix_len - trailing), prefix_len)
                        ):
                            boundary = prefix_len
                            break
                if boundary:
                    hit_count[name] = boundary
                final_pages = min(final_pages, boundary)
        return PoolTransferResult(final_pages, hit_count)

    def batch_get_v2(
        self,
        transfers: List[PoolTransfer],
        extra_info: Optional[HiCacheStorageExtraInfo] = None,
    ) -> dict:
        results = {}
        for transfer in transfers:
            host_pool = self.registered_pools[transfer.name]
            keys = transfer.keys or []
            page_size = getattr(host_pool, "page_size", 1) or 1
            host_indices = transfer.host_indices
            if host_indices is None or len(host_indices) != len(keys) * page_size:
                logger.error(
                    "batch_get_v2 indices length mismatch for %s: "
                    "expected %s, got %s",
                    transfer.name,
                    len(keys) * page_size,
                    len(host_indices) if host_indices is not None else 0,
                )
                results[transfer.name] = [False] * len(keys)
                continue
            storage_keys = [self._component_key(transfer.name, k) for k in keys]
            pages = self._read_pages(storage_keys)
            dummy = host_pool.get_dummy_flat_data_page()
            per_key = []
            for i, page in enumerate(pages):
                if page is None:
                    per_key.append(False)
                    continue
                dummy_view = _target_byte_view(dummy)
                if len(dummy_view) != len(page):
                    per_key.append(False)
                    continue
                dummy_view[:] = page
                host_pool.set_from_flat_data_page(
                    int(host_indices[i * page_size]), dummy
                )
                per_key.append(True)
            results[transfer.name] = per_key
        return results

    def batch_set_v2(
        self,
        transfers: List[PoolTransfer],
        extra_info: Optional[HiCacheStorageExtraInfo] = None,
    ) -> dict:
        results = {}
        for transfer in transfers:
            host_pool = self.registered_pools[transfer.name]
            keys = transfer.keys or []
            page_size = getattr(host_pool, "page_size", 1) or 1
            host_indices = transfer.host_indices
            if host_indices is None or len(host_indices) != len(keys) * page_size:
                logger.error(
                    "batch_set_v2 indices length mismatch for %s: "
                    "expected %s, got %s",
                    transfer.name,
                    len(keys) * page_size,
                    len(host_indices) if host_indices is not None else 0,
                )
                results[transfer.name] = [False] * len(keys)
                continue
            storage_keys = [self._component_key(transfer.name, k) for k in keys]
            values = [
                host_pool.get_data_page(int(host_indices[i * page_size]), flat=True)
                for i in range(len(keys))
            ]
            ok = self._write_pages(storage_keys, values)
            results[transfer.name] = [ok] * len(keys)
            if ok:
                self._log_extent_write(
                    transfer.name,
                    getattr(extra_info, "node_id", None),
                    storage_keys,
                    values,
                )
        return results

    # ---- core aggregated IO ----

    def _read_pages(self, keys: List[str]) -> List[Optional[memoryview]]:
        """Aggregate-read pages: one pread per merged exact range.

        Snapshot refs under the lock -> pread each merged range without the
        lock -> re-verify generation under the lock (a slot reused in between
        fails verification, and its half-read data is discarded = miss).

        Read amplification fix (P0, expert ruling): the extent is an
        allocation unit, not a read unit.  Requested refs are sorted by
        offset within each extent and merged only when the gap between
        adjacent ranges is at most ``_MERGE_GAP_THRESHOLD`` bytes; each
        merged range is pread exactly, so dead bytes between requested slots
        are no longer read (M3 measured ~30x physical/requested with the
        previous whole-extent-span read).
        """
        with self._lock:
            refs = self._allocator.snapshot(keys)
        groups: dict = {}
        for i, ref in enumerate(refs):
            if ref is None:
                continue
            groups.setdefault(ref.extent_id, []).append(i)
        requested = 0
        physical = 0
        preads = 0
        scratch: dict = {}
        for extent_id, idxs in groups.items():
            items = sorted((refs[i].offset, refs[i].length, i) for i in idxs)
            ranges = _merge_requested_ranges(items)
            requested += sum(length for _, length, _ in items)
            found: dict = {}
            for start, end, idx_list in ranges:
                buf = bytearray(end - start)
                if (
                    self._pread_full(buf, extent_id * self._extent_size + start)
                    != len(buf)
                ):
                    logger.error(
                        f"ExtentFileBackend: short pread for extent {extent_id}"
                    )
                    # Whole extent misses (same semantics as before); the
                    # ranges read so far are discarded with `found`.
                    found = {}
                    break
                physical += end - start
                preads += 1
                for i in idx_list:
                    found[i] = (buf, refs[i].offset - start)
            scratch.update(found)
        with self._lock:
            ok = self._allocator.verify(keys, refs)
            for i, key in enumerate(keys):
                if ok[i]:
                    self._allocator.touch(key)
        out: List[Optional[memoryview]] = [None] * len(keys)
        for i, ref in enumerate(refs):
            if ref is None or not ok[i]:
                continue
            entry = scratch.get(i)
            if entry is None:
                continue
            buf, start = entry
            out[i] = memoryview(buf)[start : start + ref.length]
        # Read-amplification accounting (physical/requested < 1.2x target).
        self._stats["requested_bytes"] += requested
        self._stats["physical_bytes_read"] += physical
        self._stats["last_batch_requested_bytes"] = requested
        self._stats["last_batch_physical_bytes"] = physical
        self._stats["last_batch_preads"] = preads
        return out

    def _write_pages(self, keys: List[str], values: List[Any]) -> bool:
        """Pack pages into extents and pwrite, all-or-nothing.

        Watermark GC runs first (under the lock); the whole plan->pwrite->
        commit sequence holds the index lock, so readers cannot snapshot a
        half-applied write and no state is mutated if a pwrite fails (ACK =
        pwrite success + index registration).
        """
        if len(keys) != len(values) or any(v is None for v in values):
            return False
        with self._lock:
            self._gc_evict()
            views = [_page_byte_view(v) for v in values]
            refs, passed = self._allocator.plan(
                list(zip(keys, [len(v) for v in views]))
            )
            if any(r is None for r in refs):
                logger.warning(
                    "ExtentFileBackend: batch of %s pages refused (page "
                    "larger than extent_size %s B)",
                    len(keys),
                    self._extent_size,
                )
                return False
            groups: dict = {}
            for i, ref in enumerate(refs):
                groups.setdefault(ref.extent_id, []).append(i)
            for extent_id, idxs in groups.items():
                first = refs[idxs[0]].offset
                bufs = [views[i] for i in idxs]
                if not self._pwritev(extent_id * self._extent_size + first, bufs):
                    return False
            self._allocator.commit(keys, refs, passed)
            return True

    # ---- GC / lifecycle ----

    def _gc_evict(self) -> None:
        """Lazy watermark GC: evict LRU slots until under both watermarks.

        Pressure = live bytes above max_size x eviction_ratio, or free disk
        below min_free_space; eviction is synchronous on the write path, no
        background daemon.
        """
        if self._max_size_bytes <= 0 and self._min_free_bytes <= 0:
            return
        while True:
            pressure = (
                self._max_size_bytes > 0
                and self._allocator.used_bytes
                > int(self._max_size_bytes * self._eviction_ratio)
            )
            if not pressure and self._min_free_bytes > 0:
                st = os.statvfs(self._storage_dir)
                if st.f_bavail * st.f_frsize < self._min_free_bytes:
                    pressure = True
            if not pressure:
                return
            if self._allocator.evict_slot_lru() == 0:
                return

    def clear(self) -> bool:
        with self._lock:
            self._allocator.clear()
        logger.info("Cleared all entries in ExtentFileBackend storage.")
        return True

    def get_stats(self):
        # Engine contract (unified_radix_cache.check_hicache_events): must be
        # None or StorageMetrics; a dict crashes the scheduler with
        # AttributeError on the prefetch_stats assignment (3090 repro).  The
        # raw io counters live under stats_snapshot().
        return None

    def stats_snapshot(self) -> dict:
        """Raw io counters (opens/preads/pwrites/bytes_*) for tests/tooling."""
        with self._lock:
            return dict(self._stats)

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    # ---- raw fd IO (explicit offsets, thread-safe on a shared fd) ----

    def _pread_full(self, buf: bytearray, offset: int) -> int:
        mv = memoryview(buf)
        total = 0
        try:
            while total < len(mv):
                got = os.preadv(self._fd, [mv[total:]], offset + total)
                if got == 0:
                    break
                total += got
        except OSError as e:
            logger.error(f"ExtentFileBackend: pread failed at {offset}: {e}")
            return 0
        self._stats["preads"] += 1
        self._stats["bytes_read"] += total
        return total

    def _preadv_full(self, offset: int, buffers: List[Any]) -> int:
        """preadv ``buffers`` sequentially at ``offset`` until full or EOF.

        Buffers mix ctypes arrays aliasing host-pool memory (v1 zero-copy
        targets) and plain bytearrays (merged-range gap scratch); a partial
        read resumes past the already-consumed bytes.  Each syscall is
        capped at IOV_MAX iovecs (defensive: a merged range holds 2 blocks
        per page, so batches beyond 512 pages per range would otherwise
        fail with EINVAL; today's batches stay well under).
        """
        total = sum(len(b) for b in buffers)
        done = 0
        try:
            while done < total:
                iov = []
                skip = done
                for b in buffers:
                    if skip >= len(b):
                        skip -= len(b)
                        continue
                    if len(iov) >= _IOV_MAX:
                        break
                    iov.append(memoryview(b)[skip:])
                    skip = 0
                got = os.preadv(self._fd, iov, offset + done)
                if got == 0:
                    break
                done += got
        except OSError as e:
            logger.error(f"ExtentFileBackend: pread failed at {offset}: {e}")
            return 0
        self._stats["preads"] += 1
        self._stats["bytes_read"] += done
        return done

    def _pwritev(self, offset: int, buffers: List[memoryview]) -> bool:
        """pwritev ``buffers`` at ``offset``, sharded past the IOV_MAX cap.

        One syscall takes at most IOV_MAX(1024) iovecs (measured: 1024 OK,
        1025 EINVAL); the v1 path packs 2 blocks per page, so a 1024-page
        batch is 2048 iovecs and must split into consecutive shards whose
        offsets advance by the bytes already written.  Each shard is its
        own syscall and failure point: a short or failed shard returns
        False and the caller refuses the whole batch (all-or-nothing
        semantics unchanged).
        """
        total = sum(len(b) for b in buffers)
        written = 0
        try:
            for start in range(0, len(buffers), _IOV_MAX):
                chunk = buffers[start : start + _IOV_MAX]
                got = os.pwritev(self._fd, chunk, offset + written)
                self._stats["pwrites"] += 1
                if got != sum(len(b) for b in chunk):
                    logger.error(
                        f"ExtentFileBackend: short pwrite at {offset + written}"
                    )
                    return False
                written += got
        except OSError as e:
            logger.error(
                f"ExtentFileBackend: pwrite failed at {offset + written}: {e}"
            )
            self._stats["pwrites"] += 1
            return False
        self._stats["bytes_written"] += written
        return written == total
