# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to SGLang project

"""ExtentFileBackend: HiCacheStorage over a single preallocated sparse file.

Replaces HiCacheFile's per-key .bin files (a 20K-page restore is ~63K
open/read/close syscalls) with aggregated IO: a batch of consecutive page
writes packs into fixed-size extents (default 64 MiB), so one preadv/pwritev
covers the whole batch. The RAM index (``ExtentAllocator``) maps storage key
-> ExtentRef{extent_id, offset, length, generation}; slot reuse or watermark
GC bumps the generation and any stale entry fails the read-side re-verify
(generation mismatch = miss).

Durability contract is unchanged from HiCacheFile: the tree layer only trusts
the ACK, and ACK here means pwrite success + index registration (no fsync,
matching the current semantics; a crash leaves the file orphaned and the
restart starts cold -- no metadata persistence). v1 is the main KV path
(controller batches at STORAGE_BATCH_SIZE=128); v2 keeps the sidecar-pool
semantics with per-pool component keys (``key.<pool>``) packed into their own
extents.

First slice uses buffered IO; ``SGLANG_HICACHE_EXTENT_BACKEND_DIRECT_IO`` is
reserved for the O_DIRECT calibration tier -- page lengths are not 4KiB
aligned, so only whole-extent aligned IO could use O_DIRECT safely.
"""

from __future__ import annotations

import logging
import os
import threading
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
        page = self._read_pages([key])[0]
        if page is None or target_location is None:
            return None
        view = _target_byte_view(target_location)
        if len(view) != len(page):
            logger.warning(
                f"ExtentFileBackend: size mismatch for {key}: "
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
        return self._write_pages([key], [value])

    def exists(self, key: str) -> bool:
        with self._lock:
            return self._allocator.lookup(key) is not None

    # ---- v1: batched surface (main KV path) ----

    def batch_get(
        self,
        keys: List[str],
        target_locations: Optional[Any] = None,
        target_sizes: Optional[Any] = None,
    ) -> List[Any]:
        pages = self._read_pages(keys)
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

    def batch_set(
        self,
        keys: List[str],
        values: Optional[Any] = None,
        target_locations: Optional[Any] = None,
        target_sizes: Optional[Any] = None,
    ) -> bool:
        if values is None or len(values) != len(keys):
            return False
        return self._write_pages(keys, values)

    def batch_exists(
        self, keys: List[str], extra_info: Optional[HiCacheStorageExtraInfo] = None
    ) -> int:
        with self._lock:
            for i, key in enumerate(keys):
                if self._allocator.lookup(key) is None:
                    return i
            return len(keys)

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
                if transfer.hit_policy == PoolHitPolicy.ALL_PAGES:
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
        return results

    # ---- core aggregated IO ----

    def _read_pages(self, keys: List[str]) -> List[Optional[memoryview]]:
        """Aggregate-read pages: one pread per extent, page slices returned.

        Snapshot refs under the lock -> pread the extent span without the
        lock -> re-verify generation under the lock (a slot reused in between
        fails verification, and its half-read data is discarded = miss).
        """
        with self._lock:
            refs = self._allocator.snapshot(keys)
        groups: dict = {}
        for i, ref in enumerate(refs):
            if ref is None:
                continue
            groups.setdefault(ref.extent_id, []).append(i)
        scratch: dict = {}
        for extent_id, idxs in groups.items():
            first = min(refs[i].offset for i in idxs)
            last = max(refs[i].offset + refs[i].length for i in idxs)
            buf = bytearray(last - first)
            if (
                self._pread_full(buf, extent_id * self._extent_size + first)
                != len(buf)
            ):
                logger.error(
                    f"ExtentFileBackend: short pread for extent {extent_id}"
                )
                scratch[extent_id] = None
            else:
                scratch[extent_id] = (first, buf)
        with self._lock:
            ok = self._allocator.verify(keys, refs)
            for i, key in enumerate(keys):
                if ok[i]:
                    self._allocator.touch(key)
        out: List[Optional[memoryview]] = [None] * len(keys)
        for i, ref in enumerate(refs):
            if ref is None or not ok[i]:
                continue
            entry = scratch.get(ref.extent_id)
            if entry is None:
                continue
            first, buf = entry
            start = ref.offset - first
            out[i] = memoryview(buf)[start : start + ref.length]
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

    def _pwritev(self, offset: int, buffers: List[memoryview]) -> bool:
        try:
            total = sum(len(b) for b in buffers)
            written = os.pwritev(self._fd, buffers, offset)
        except OSError as e:
            logger.error(f"ExtentFileBackend: pwrite failed at {offset}: {e}")
            self._stats["pwrites"] += 1
            return False
        self._stats["pwrites"] += 1
        self._stats["bytes_written"] += written
        return written == total
