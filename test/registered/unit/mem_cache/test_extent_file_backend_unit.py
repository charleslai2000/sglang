"""
Unit tests for the ExtentFileBackend (circular extent allocator, aggregated
page IO, generation invalidation, watermark GC, crash-reopen semantics) and
its pure-logic allocator.

The bulk of the suite is driven with bytearray pages end-to-end (no torch
import): ``_page_byte_view`` treats byte-like buffers as raw bytes.  The
``TestExtentTensorPages`` cases additionally drive the real torch.Tensor
path (the engine's host-pool flat pages are torch tensors, bf16/fp16/fp32
CPU) and skip themselves when torch is not installed.

Run with:
    python3 -m pytest test/registered/unit/mem_cache/test_extent_file_backend_unit.py -v
"""

from sglang.test.ci.ci_register import register_cpu_ci

register_cpu_ci(est_time=20, suite="base-a-test-cpu")

import os
import shutil
import tempfile
import unittest
from unittest import mock

try:
    import torch
except ImportError:
    torch = None  # tensor cases skip; the bytearray suite stays torch-free

from sglang.srt.mem_cache.hicache_storage import (
    HiCacheStorageConfig,
    PoolHitPolicy,
    PoolName,
    PoolTransfer,
)
from sglang.srt.mem_cache.storage.extent.extent_allocator import (
    ExtentAllocator,
    ExtentRef,
)
from sglang.srt.mem_cache.storage.extent.extent_file_backend import (
    ExtentFileBackend,
    _page_byte_view,
)
from sglang.test.test_utils import CustomTestCase

_EXTENT = 4096


def _write(alloc: ExtentAllocator, key: str, length: int) -> ExtentRef:
    refs, passed = alloc.plan([(key, length)])
    assert refs[0] is not None, f"key {key} refused by allocator"
    alloc.commit([key], refs, passed)
    return refs[0]


class TestExtentAllocator(CustomTestCase):
    def _alloc(self, num_slots=4, extent_size=_EXTENT) -> ExtentAllocator:
        return ExtentAllocator(extent_size=extent_size, num_slots=num_slots)

    def test_extent_size_must_be_4096_aligned(self):
        for bad in (0, -1, 4095, 8191):
            with self.assertRaises(ValueError):
                ExtentAllocator(extent_size=bad, num_slots=2)
        ExtentAllocator(extent_size=4096, num_slots=2)  # must not raise

    def test_plan_is_pure_until_commit(self):
        # A failed pwrite must leave no state behind: plan() is read-only.
        alloc = self._alloc()
        refs, passed = alloc.plan([("k1", 100), ("k2", 100)])
        self.assertEqual(passed, [])
        self.assertIsNone(alloc.lookup("k1"))
        self.assertEqual(alloc.used_bytes, 0)
        # Ref gens are valid for a later commit.
        alloc.commit(["k1", "k2"], refs, passed)
        self.assertIsNotNone(alloc.lookup("k1"))
        self.assertEqual(alloc.used_bytes, 200)

    def test_pack_consecutive_keys_into_one_extent(self):
        alloc = self._alloc()
        refs, passed = alloc.plan([(f"k{i}", 1000) for i in range(4)])
        self.assertEqual(passed, [])
        self.assertEqual({r.extent_id for r in refs}, {0})
        self.assertEqual([r.offset for r in refs], [0, 1000, 2000, 3000])
        alloc.commit([f"k{i}" for i in range(4)], refs, passed)
        self.assertEqual(alloc.used_bytes, 4000)

    def test_circular_wrap_drops_oldest_slot_and_bumps_generation(self):
        # 4 keys per 4096 slot with 1000-byte pages: key 17 wraps into slot 0.
        alloc = self._alloc(num_slots=4)
        gen0 = []
        for i in range(17):
            ref = _write(alloc, f"k{i}", 1000)
            gen0.append(ref)
        wrapped = alloc.lookup("k16")
        self.assertEqual(wrapped.extent_id, 0)
        self.assertEqual(wrapped.offset, 0)
        self.assertEqual(wrapped.generation, 1)  # slot 0 reused -> gen++
        # Keys of the dropped slot are gone (miss), including via snapshot.
        self.assertIsNone(alloc.lookup("k0"))
        self.assertEqual(alloc.snapshot(["k0", "k1", "k16"]), [None, None, wrapped])
        # A ref captured before the wrap fails re-verification.
        self.assertEqual(alloc.verify(["k0"], [gen0[0]]), [False])
        self.assertEqual(alloc.verify(["k16"], [wrapped]), [True])

    def test_generation_invalidation_after_slot_reuse(self):
        alloc = self._alloc(num_slots=1, extent_size=_EXTENT)
        first = _write(alloc, "k", 1000)
        second = _write(alloc, "k", 1000)  # same key: cursor advances
        self.assertNotEqual(first.offset, second.offset)
        self.assertEqual(first.generation, second.generation)
        # Fill the single slot, then plan a page that no longer fits: the
        # entered slot is reused, so generations must bump and stale refs
        # must miss after commit.
        for i in range(14):
            _write(alloc, f"f{i}", 1000)
        refs, passed = alloc.plan([("other", 1000)])
        self.assertIn(0, passed)
        alloc.commit(["other"], refs, passed)
        self.assertEqual(alloc.verify(["k"], [second]), [False])
        self.assertEqual(alloc.lookup("k"), None)
        self.assertEqual(alloc.verify(["other"], [refs[0]]), [True])

    def test_same_key_rewrite_unlinks_old_slot_accounting(self):
        alloc = self._alloc(num_slots=2)
        old = _write(alloc, "k", 1000)  # slot 0
        _write(alloc, "j", 1000)  # slot 0, offset 1000
        new = _write(alloc, "k", 500)  # still fits slot 0 -> offset 2000
        self.assertEqual(old.extent_id, new.extent_id)
        self.assertEqual(alloc.used_bytes, 1000 + 500)  # old length unlinked
        self.assertEqual(alloc.verify(["k"], [old]), [False])
        self.assertEqual(alloc.lookup("k"), new)
        self.assertIsNotNone(alloc.lookup("j"))

    def test_page_larger_than_extent_refused(self):
        alloc = self._alloc()
        refs, _ = alloc.plan([("big", 5000)])
        self.assertIsNone(refs[0])
        self.assertEqual(alloc.used_bytes, 0)

    def test_batch_larger_than_whole_file_refused(self):
        alloc = self._alloc(num_slots=2, extent_size=_EXTENT)
        refs, _ = alloc.plan([(f"k{i}", 3000) for i in range(3)])
        # 9000 bytes > 8192 total: cannot place without self-overwrite.
        self.assertTrue(all(r is None for r in refs))
        self.assertEqual(alloc.used_bytes, 0)

    def test_evict_slot_lru_frees_oldest_slot(self):
        alloc = self._alloc(num_slots=4)
        for i in range(8):
            _write(alloc, f"k{i}", 1000)
        # k0..k3 in slot 0, k4..k7 in slot 1; k0 is the LRU key.
        freed = alloc.evict_slot_lru()
        self.assertEqual(freed, 4000)  # slot 0's live bytes
        self.assertEqual(alloc.used_bytes, 4000)
        self.assertIsNone(alloc.lookup("k0"))
        self.assertIsNotNone(alloc.lookup("k4"))
        # Slots holding newer keys survive; second evict takes slot 1.
        self.assertEqual(alloc.evict_slot_lru(), 4000)
        self.assertEqual(alloc.used_bytes, 0)
        self.assertEqual(alloc.evict_slot_lru(), 0)  # empty -> no-op

    def test_touch_reorders_recency(self):
        # 2500-byte pages force one key per 4096 slot; touching "old" makes
        # "new" the LRU victim, so the evicted slot must be the newer key's.
        alloc = self._alloc(num_slots=4, extent_size=_EXTENT)
        _write(alloc, "old", 2500)
        _write(alloc, "new", 2500)
        alloc.touch("old")
        self.assertEqual(alloc.evict_slot_lru(), 2500)
        self.assertIsNotNone(alloc.lookup("old"))
        self.assertIsNone(alloc.lookup("new"))

    def test_clear_resets_index_and_bytes(self):
        alloc = self._alloc()
        _write(alloc, "k1", 1000)
        _write(alloc, "k2", 1000)
        alloc.clear()
        self.assertEqual(alloc.used_bytes, 0)
        self.assertIsNone(alloc.lookup("k1"))
        # Post-clear writes start from slot 0 again.
        ref = _write(alloc, "k3", 1000)
        self.assertEqual((ref.extent_id, ref.offset), (0, 0))


class _PagePool:
    """Minimal torch-free host-pool stand-in (page_size + flat page APIs)."""

    def __init__(self, page_bytes: int, slots: int = 256):
        self.page_size = 1
        self._page_bytes = page_bytes
        self._pages = [bytearray(page_bytes) for _ in range(slots)]

    def get_data_page(self, index, flat=True):
        return self._pages[index]

    def get_dummy_flat_data_page(self):
        return bytearray(self._page_bytes)

    def set_from_flat_data_page(self, index, data_page):
        self._pages[index][:] = data_page


def _make_config(extra_config=None, **overrides) -> HiCacheStorageConfig:
    cfg = dict(
        tp_rank=0,
        tp_size=1,
        pp_rank=0,
        pp_size=1,
        attn_cp_rank=0,
        attn_cp_size=1,
        is_mla_model=False,
        enable_storage_metrics=False,
        is_page_first_layout=True,
        model_name="testmodel",
    )
    cfg.update(overrides)
    return HiCacheStorageConfig(extra_config=extra_config, **cfg)


class ExtentBackendTestBase(CustomTestCase):
    """Drive the real backend against bytearray pages in a temp dir."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="extent_unit_")
        self.backend = ExtentFileBackend(
            _make_config(
                extra_config={
                    "storage_dir": self.tmpdir,
                    "extent_size": "16Ki",
                    "file_size": "64Ki",
                }
            )
        )

    def tearDown(self):
        if hasattr(self, "backend") and self.backend is not None:
            self.backend.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @staticmethod
    def _page(data: bytes) -> bytearray:
        return bytearray(data)

    def _page_bytes(self, i: int, page_bytes: int = 1000) -> bytearray:
        return self._page(bytes([i % 251]) * page_bytes)

    def _make_keys(self, count: int, start: int = 0) -> list:
        return [f"k{i:04d}" for i in range(start, start + count)]

    def _write_keys(self, count: int, page_bytes: int = 1000) -> list:
        keys = self._make_keys(count)
        values = [self._page_bytes(i, page_bytes) for i in range(count)]
        self.assertTrue(self.backend.batch_set(keys, values))
        return keys

    def _assert_pages_equal(self, got, expected_values):
        self.assertEqual(len(got), len(expected_values))
        for g, e in zip(got, expected_values):
            self.assertIsNotNone(g)
            self.assertEqual(bytes(g), bytes(e))


class TestExtentV1(ExtentBackendTestBase):
    def test_single_key_round_trip(self):
        self.assertTrue(self.backend.set("k0", self._page_bytes(1)))
        self.assertTrue(self.backend.exists("k0"))
        target = bytearray(1000)
        got = self.backend.get("k0", target)
        self.assertIsNotNone(got)
        self.assertEqual(bytes(got), bytes(self._page_bytes(1)))
        self.assertFalse(self.backend.exists("missing"))

    def test_batch_round_trip(self):
        keys = self._make_keys(10)
        values = [self._page_bytes(i) for i in range(10)]
        self.assertTrue(self.backend.batch_set(keys, values))
        targets = [bytearray(1000) for _ in keys]
        got = self.backend.batch_get(keys, targets)
        self._assert_pages_equal(got, values)
        # Misses come back as None, in order.
        got = self.backend.batch_get(keys + ["nope"], targets + [bytearray(1000)])
        self.assertIsNone(got[-1])
        self.assertEqual(self.backend.batch_get([], []), [])

    def test_same_key_rewrite_returns_new_value(self):
        self.assertTrue(self.backend.set("k", bytearray(b"A" * 1000)))
        self.assertTrue(self.backend.set("k", bytearray(b"B" * 1000)))
        got = self.backend.get("k", bytearray(1000))
        self.assertEqual(bytes(got), b"B" * 1000)

    def test_get_size_mismatch_returns_none(self):
        self.assertTrue(self.backend.set("k", self._page_bytes(1)))
        self.assertIsNone(self.backend.get("k", bytearray(500)))

    def test_batch_exists_consecutive_count(self):
        self._write_keys(5)
        self.assertEqual(self.backend.batch_exists(self._make_keys(5) + ["x"]), 5)
        self.assertEqual(self.backend.batch_exists(["x", "k0000"]), 0)
        self.assertEqual(self.backend.batch_exists([]), 0)

    def test_aggregate_read_one_pread_per_extent(self):
        # One extent (128 KiB) holds the whole 100-key batch: batch_get must
        # issue exactly one pread (double-checked via stats and a syscall spy).
        backend = ExtentFileBackend(
            _make_config(
                extra_config={
                    "storage_dir": self.tmpdir,
                    "extent_size": "128Ki",
                    "file_size": "1Mi",
                }
            )
        )
        try:
            keys = self._make_keys(100)
            values = [self._page_bytes(i) for i in range(100)]
            self.assertTrue(backend.batch_set(keys, values))
            preads_before = backend.stats_snapshot()["preads"]
            with mock.patch.object(os, "preadv", wraps=os.preadv) as spy:
                targets = [bytearray(1000) for _ in keys]
                got = backend.batch_get(keys, targets)
            self.assertEqual(spy.call_count, 1)
            self.assertEqual(backend.stats_snapshot()["preads"] - preads_before, 1)
            self._assert_pages_equal(got, values)
        finally:
            backend.close()

    def test_aggregate_write_one_pwrite_per_extent(self):
        backend = ExtentFileBackend(
            _make_config(
                extra_config={
                    "storage_dir": self.tmpdir,
                    "extent_size": "128Ki",
                    "file_size": "1Mi",
                }
            )
        )
        try:
            keys = self._make_keys(100)
            values = [self._page_bytes(i) for i in range(100)]
            pwrites_before = backend.stats_snapshot()["pwrites"]
            with mock.patch.object(os, "pwritev", wraps=os.pwritev) as spy:
                self.assertTrue(backend.batch_set(keys, values))
            self.assertEqual(spy.call_count, 1)
            self.assertEqual(backend.stats_snapshot()["pwrites"] - pwrites_before, 1)
        finally:
            backend.close()

    def test_multi_extent_round_trip_over_128_keys(self):
        # 200 x 1000 B = 13 extents in a 256 KiB file: multiple pwritev
        # regions, but every page must come back byte-identical.
        backend = ExtentFileBackend(
            _make_config(
                extra_config={
                    "storage_dir": self.tmpdir,
                    "extent_size": "16Ki",
                    "file_size": "256Ki",
                }
            )
        )
        try:
            keys = self._make_keys(200)
            values = [self._page_bytes(i) for i in range(200)]
            self.assertTrue(backend.batch_set(keys, values))
            targets = [bytearray(1000) for _ in keys]
            got = backend.batch_get(keys, targets)
            self._assert_pages_equal(got, values)
            self.assertGreater(backend.stats_snapshot()["pwrites"], 1)
        finally:
            backend.close()

    def test_circular_wrap_drops_oldest_slot(self):
        # 16 KiB extents, 1000 B pages, 64 KiB file (4 slots): after 80 keys
        # in 4 batches, key 64 wraps into slot 0 and invalidates keys 0..15.
        for start in range(0, 80, 20):
            self._write_keys_into(self.backend, 20, start)
        self.assertFalse(self.backend.exists("k0000"))
        self.assertIsNone(self.backend.get("k0000", bytearray(1000)))
        self.assertTrue(self.backend.exists("k0016"))
        self.assertTrue(self.backend.exists("k0064"))
        got = self.backend.get("k0064", bytearray(1000))
        self.assertEqual(bytes(got), bytes(self._page_bytes(64)))
        self.assertEqual(self.backend._allocator.used_bytes, 64 * 1000)

    def test_watermark_gc_keeps_used_bytes_under_cap(self):
        backend = ExtentFileBackend(
            _make_config(
                extra_config={
                    "storage_dir": self.tmpdir,
                    "extent_size": "16Ki",
                    "file_size": "1Mi",
                    "max_size": "48Ki",
                    "eviction_ratio": 0.9,
                }
            )
        )
        try:
            # 40 KiB is below the 43.2 KiB watermark; 46 KiB crosses it, and
            # the next write evicts the oldest 16 KiB slot before planning.
            self._write_keys_into(backend, 40, start=0)
            self._write_keys_into(backend, 6, start=40)
            self._write_keys_into(backend, 2, start=46)
            self.assertFalse(backend.exists("k0000"))
            self.assertTrue(backend.exists("k0016"))
            self.assertTrue(backend.exists("k0047"))
            self.assertLessEqual(
                backend._allocator.used_bytes, int(48 * 1024 * 0.9)
            )
        finally:
            backend.close()

    def _write_keys_into(self, backend, count, start=0):
        keys = self._make_keys(count, start=start)
        values = [self._page_bytes(i) for i in range(start, start + count)]
        self.assertTrue(backend.batch_set(keys, values))

    def test_min_free_space_pressure_evicts_oldest(self):
        backend = ExtentFileBackend(
            _make_config(
                extra_config={
                    "storage_dir": self.tmpdir,
                    "extent_size": "16Ki",
                    "file_size": "1Mi",
                    "min_free_space": "1Ti",
                }
            )
        )
        try:
            # Unmeetable free-space watermark: every write evicts the oldest slot.
            self._write_keys_into(backend, 1, start=0)
            self._write_keys_into(backend, 1, start=1)
            self.assertFalse(backend.exists("k0000"))
            self.assertTrue(backend.exists("k0001"))
        finally:
            backend.close()

    def test_batch_set_refused_when_page_exceeds_extent(self):
        big = bytearray(20 * 1024)  # > 16 KiB extent
        self.assertFalse(self.backend.set("big", big))
        self.assertFalse(self.backend.exists("big"))
        # All-or-nothing: the batch must not register the good keys either.
        self.assertFalse(
            self.backend.batch_set(["a", "b"], [bytearray(1000), big])
        )
        self.assertFalse(self.backend.exists("a"))

    def test_clear_empties_then_reusable(self):
        keys = self._write_keys(5)
        self.assertTrue(self.backend.clear())
        for k in keys:
            self.assertFalse(self.backend.exists(k))
        # Storage is reusable after clear.
        self._write_keys(3)
        self.assertTrue(self.backend.exists("k0000"))

    def test_crash_reopen_all_cold(self):
        keys = self._write_keys(5)
        for k in keys:
            self.assertTrue(self.backend.exists(k))
        self.backend.close()
        # Reopen on the same directory: no metadata persistence, all cold.
        reopened = ExtentFileBackend(
            _make_config(
                extra_config={
                    "storage_dir": self.tmpdir,
                    "extent_size": "16Ki",
                    "file_size": "64Ki",
                }
            )
        )
        try:
            for k in keys:
                self.assertFalse(reopened.exists(k))
                self.assertIsNone(reopened.get(k, bytearray(1000)))
            stats = reopened.stats_snapshot()
            self.assertEqual(stats["preads"], 0)
            self.assertEqual(stats["pwrites"], 0)
            self.assertEqual(stats["opens"], 1)
            # New writes land in the same file without touching old pages.
            self.assertTrue(reopened.set("fresh", self._page_bytes(1)))
            self.assertTrue(reopened.exists("fresh"))
        finally:
            reopened.close()

    def test_stats_counters_accumulate(self):
        keys = self._write_keys(10)
        targets = [bytearray(1000) for _ in keys]
        self.backend.batch_get(keys, targets)
        stats = self.backend.stats_snapshot()
        self.assertEqual(stats["opens"], 1)
        self.assertGreaterEqual(stats["pwrites"], 1)
        self.assertGreaterEqual(stats["preads"], 1)
        self.assertEqual(stats["bytes_written"], 10 * 1000)
        self.assertEqual(stats["bytes_read"], 10 * 1000)

    def test_get_stats_matches_engine_contract(self):
        # Bug regression (3090 extent engine crash): the scheduler's
        # check_hicache_events assigns onto get_stats()'s return value, so it
        # must be None (or StorageMetrics) -- a bare dict raises
        # AttributeError.  The raw io counters live under stats_snapshot().
        self.assertIsNone(self.backend.get_stats())
        stats = self.backend.stats_snapshot()
        for key in ("opens", "preads", "pwrites", "bytes_read", "bytes_written"):
            self.assertIn(key, stats)


class TestExtentV2(ExtentBackendTestBase):
    def _register_pools(self, page_bytes=1000):
        kv = _PagePool(page_bytes)
        mamba = _PagePool(page_bytes)
        self.backend.register_mem_host_pool_v2(kv, PoolName.KV)
        self.backend.register_mem_host_pool_v2(mamba, PoolName.MAMBA)
        return kv, mamba

    def _transfer(self, name, keys, indices=None, hit_policy=None):
        return PoolTransfer(
            name=name,
            host_indices=indices if indices is not None else list(range(len(keys))),
            keys=list(keys),
            hit_policy=hit_policy,
        )

    def test_v2_round_trip_kv_pool(self):
        kv, _ = self._register_pools()
        keys = self._make_keys(4)
        values = [self._page_bytes(i) for i in range(4)]
        for i, v in enumerate(values):
            kv._pages[i][:] = v
        result = self.backend.batch_set_v2([self._transfer(PoolName.KV, keys)])
        self.assertEqual(result[PoolName.KV], [True] * 4)
        result = self.backend.batch_get_v2([self._transfer(PoolName.KV, keys)])
        self.assertEqual(result[PoolName.KV], [True] * 4)
        for i, v in enumerate(values):
            self.assertEqual(bytes(kv._pages[i]), bytes(v))

    def test_v2_sidecar_component_keys_do_not_share_index(self):
        _, mamba = self._register_pools()
        keys = self._make_keys(3)
        for i in range(3):
            mamba._pages[i][:] = self._page_bytes(i)
        result = self.backend.batch_set_v2(
            [self._transfer(PoolName.MAMBA, keys)]
        )
        self.assertEqual(result[PoolName.MAMBA], [True] * 3)
        # Component writes must not create KV index entries (and vice versa).
        for k in keys:
            self.assertFalse(self.backend.exists(k))
        # The MAMBA component keys carry the ".mamba" suffix in the index.
        suffix = self.backend.config_suffix
        for k in keys:
            self.assertIsNotNone(self.backend._allocator.lookup(k + ".mamba" + suffix))
        self.assertIsNone(self.backend._allocator.lookup(k + suffix))
        # v2 exists reports the KV prefix as absent while the mamba pool
        # transfer sees its component pages.
        result = self.backend.batch_exists_v2(
            keys, [self._transfer(PoolName.MAMBA, keys)]
        )
        self.assertEqual(result.kv_hit_pages, 0)

    def test_v2_prefix_semantics(self):
        kv, mamba = self._register_pools()
        keys = self._make_keys(5)
        for i in range(3):
            kv._pages[i][:] = self._page_bytes(i)
        for i in (1, 2):
            mamba._pages[i][:] = self._page_bytes(i)
        # KV transfer writes pages 0..2; MAMBA transfer writes components for
        # keys 1..2 only (page 0's component intentionally left absent).
        self.backend.batch_set_v2(
            [
                self._transfer(PoolName.KV, keys[:3]),
                self._transfer(PoolName.MAMBA, keys[1:3]),
            ]
        )
        # kv prefix is 3; mamba components exist for pages 1..2 only.
        all_pages = self.backend.batch_exists_v2(
            keys,
            [self._transfer(PoolName.MAMBA, keys[1:3], hit_policy=PoolHitPolicy.ALL_PAGES)],
        )
        # Missing page-0 component shrinks the usable prefix to 0 (fold
        # semantics: final_pages = min across pools).
        self.assertEqual(all_pages.kv_hit_pages, 0)
        self.assertEqual(all_pages.extra_pool_hit_pages[PoolName.KV], 3)
        # Boundary 0 is not recorded (HiCacheFile fold semantics).
        self.assertEqual(all_pages.extra_pool_hit_pages.get(PoolName.MAMBA, 0), 0)
        trailing = self.backend.batch_exists_v2(
            keys,
            [
                self._transfer(
                    PoolName.MAMBA, keys[1:3], hit_policy=PoolHitPolicy.TRAILING_PAGES
                )
            ],
        )
        # trailing = 2 (transfer.keys len): pages [1..2] all present -> 3.
        self.assertEqual(trailing.kv_hit_pages, 3)
        self.assertEqual(trailing.extra_pool_hit_pages[PoolName.MAMBA], 3)

    def test_v2_indices_length_mismatch(self):
        self._register_pools()
        keys = self._make_keys(3)
        result = self.backend.batch_get_v2(
            [self._transfer(PoolName.KV, keys, indices=[0])]
        )
        self.assertEqual(result[PoolName.KV], [False] * 3)


class _TensorPagePool:
    """Host-pool stand-in backed by real CPU tensors (engine flat pages)."""

    def __init__(self, page_bytes: int, slots: int = 256, dtype=None):
        self.page_size = 1
        self.dtype = dtype if dtype is not None else torch.bfloat16
        numel = page_bytes // torch.empty(0, dtype=self.dtype).element_size()
        self._pages = [torch.zeros(numel, dtype=self.dtype) for _ in range(slots)]

    def get_data_page(self, index, flat=True):
        return self._pages[index]

    def get_dummy_flat_data_page(self):
        return torch.zeros_like(self._pages[0])

    def set_from_flat_data_page(self, index, data_page):
        self._pages[index].copy_(data_page)


class TestExtentTensorPages(ExtentBackendTestBase):
    """Real torch.Tensor page round-trips (bf16/fp16/fp32 CPU).

    Bug regression (3090 M2 crash): ``_page_byte_view`` called ``.numpy()``
    on the engine's bf16 CPU flat pages, which raises
    ``TypeError: Got unsupported ScalarType BFloat16``; backup_thread died on
    its first batch_set, storage never filled, and restore served nothing.
    The byte view must be a bit-level uint8 reinterpretation (valid for any
    CPU dtype), and the read-back fill must restore the same dtype and bit
    pattern.  Requires torch; skips itself when torch is unavailable.
    """

    def _torch_or_skip(self):
        if torch is None:
            self.skipTest("torch not available")
        return torch

    def _transfer(self, name, keys, indices=None, hit_policy=None):
        return PoolTransfer(
            name=name,
            host_indices=indices if indices is not None else list(range(len(keys))),
            keys=list(keys),
            hit_policy=hit_policy,
        )

    def _assert_bit_equal(self, got, expected, torch):
        # dtype must survive the round trip, values must be numerically
        # equal, and the uint8 views must match byte for byte (contiguous()
        # first: view(dtype) needs a unit last stride).
        self.assertEqual(got.dtype, expected.dtype)
        self.assertTrue(torch.equal(got, expected))
        self.assertTrue(
            torch.equal(
                got.contiguous().view(torch.uint8),
                expected.contiguous().view(torch.uint8),
            )
        )

    def test_bf16_tensor_round_trip(self):
        torch_ = self._torch_or_skip()
        t = torch_.randn(4096, dtype=torch_.bfloat16)
        self.assertTrue(self.backend.set("tk", t))
        got = self.backend.get("tk", torch_.empty_like(t))
        self.assertIsNotNone(got)
        self._assert_bit_equal(got, t, torch_)

    def test_fp16_tensor_round_trip(self):
        torch_ = self._torch_or_skip()
        t = torch_.randn(4096, dtype=torch_.float16)
        self.assertTrue(self.backend.set("tk", t))
        got = self.backend.get("tk", torch_.empty_like(t))
        self.assertIsNotNone(got)
        self._assert_bit_equal(got, t, torch_)

    def test_fp32_tensor_round_trip(self):
        torch_ = self._torch_or_skip()
        t = torch_.randn(4096, dtype=torch_.float32)
        self.assertTrue(self.backend.set("tk", t))
        got = self.backend.get("tk", torch_.empty_like(t))
        self.assertIsNotNone(got)
        self._assert_bit_equal(got, t, torch_)

    def test_batch_mixed_dtype_tensors_round_trip(self):
        torch_ = self._torch_or_skip()
        keys = self._make_keys(9)
        values = [
            torch_.randn(64, dtype=dtype)
            for dtype in (
                torch_.bfloat16,
                torch_.float16,
                torch_.float32,
            ) * 3
        ]
        self.assertTrue(self.backend.batch_set(keys, values))
        targets = [torch_.empty_like(v) for v in values]
        got = self.backend.batch_get(keys, targets)
        self.assertEqual(len(got), len(values))
        for g, v in zip(got, values):
            self.assertIsNotNone(g)
            self._assert_bit_equal(g, v, torch_)

    def test_non_contiguous_tensor_round_trip(self):
        torch_ = self._torch_or_skip()
        # Write side: a strided (non-contiguous) page must be read by its
        # logical element order (contiguous() copies, then uint8 view).
        t = torch_.randn(8, 16, dtype=torch_.bfloat16).t()  # (16, 8), strided
        self.assertTrue(self.backend.set("nct", t))
        # Read back into a contiguous target (the engine's flat pages are
        # contiguous; a strided target cannot be filled in place).
        got = self.backend.get(
            "nct", torch_.empty(16, 8, dtype=torch_.bfloat16)
        )
        self.assertIsNotNone(got)
        self._assert_bit_equal(got, t, torch_)

    def test_tensor_page_view_is_zero_copy(self):
        torch_ = self._torch_or_skip()
        t = torch_.randn(4096, dtype=torch_.bfloat16)
        view = _page_byte_view(t)
        self.assertEqual(view.nbytes, t.numel() * t.element_size())
        # The byte view must alias the tensor storage, not copy it: the
        # exported numpy buffer and the tensor data pointer must agree
        # (a 20K-page batch would double memory if copied).
        self.assertEqual(
            view.obj.__array_interface__["data"][0], t.data_ptr()
        )

    def test_v2_bf16_tensor_pool_round_trip(self):
        torch_ = self._torch_or_skip()
        kv = _TensorPagePool(2000, dtype=torch_.bfloat16)
        self.backend.register_mem_host_pool_v2(kv, PoolName.KV)
        keys = self._make_keys(4)
        originals = [torch_.randn(1000, dtype=torch_.bfloat16) for _ in range(4)]
        for i, o in enumerate(originals):
            kv._pages[i][:] = o
        result = self.backend.batch_set_v2([self._transfer(PoolName.KV, keys)])
        self.assertEqual(result[PoolName.KV], [True] * 4)
        # Wipe the pages so a silent miss is not masked by stale bytes.
        for p in kv._pages[:4]:
            p.zero_()
        result = self.backend.batch_get_v2([self._transfer(PoolName.KV, keys)])
        self.assertEqual(result[PoolName.KV], [True] * 4)
        for i, o in enumerate(originals):
            self._assert_bit_equal(kv._pages[i], o, torch_)


class TestExtentFullFile(ExtentBackendTestBase):
    def test_multi_batch_round_trip_across_extents(self):
        # 3 batches of 128 keys (384 pages, 24 extents): the pack cursor
        # carries across batches and page spans cross batch boundaries.
        backend = ExtentFileBackend(
            _make_config(
                extra_config={
                    "storage_dir": self.tmpdir,
                    "extent_size": "16Ki",
                    "file_size": "1Mi",
                }
            )
        )
        try:
            keys_all, values_all = [], []
            for batch in range(3):
                start = batch * 128
                keys = self._make_keys(128, start=start)
                values = [self._page_bytes(i) for i in range(start, start + 128)]
                self.assertTrue(backend.batch_set(keys, values))
                keys_all += keys
                values_all += values
            targets = [bytearray(1000) for _ in keys_all]
            got = backend.batch_get(keys_all, targets)
            self._assert_pages_equal(got, values_all)
        finally:
            backend.close()


class TestExtentFactory(CustomTestCase):
    def test_factory_creates_real_extent_backend(self):
        from sglang.srt.mem_cache.storage.backend_factory import (
            StorageBackendFactory,
        )

        tmpdir = tempfile.mkdtemp(prefix="extent_factory_")
        try:
            backend = StorageBackendFactory.create_backend(
                "extent",
                _make_config(
                    extra_config={
                        "storage_dir": tmpdir,
                        "extent_size": "16Ki",
                        "file_size": "64Ki",
                    }
                ),
                None,
            )
            self.assertEqual(type(backend).__name__, "ExtentFileBackend")
            self.assertTrue(isinstance(backend, ExtentFileBackend))
            # The instance is fully functional, not a stub.
            self.assertTrue(backend.set("k", bytearray(b"x" * 1000)))
            self.assertTrue(backend.exists("k"))
            backend.close()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
