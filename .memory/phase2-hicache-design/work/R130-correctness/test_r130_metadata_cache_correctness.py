#!/usr/bin/env python3
"""R130 correctness gate for the HiCacheFile file-storage metadata cache.

Offline: no GPU, no server, no network. stdlib ``unittest`` only, plus the
minimal ``torch`` byte-tensor interface that ``HiCacheFile.set/get`` require.

The tests exercise the *real* product code paths in
``sglang/srt/mem_cache/hicache_storage.py`` and
``storage/file/lru_file_evictor.py``:

  (a) a successful write is immediately queryable from the RAM metadata index
      without touching the directory;
  (b) invalidation cannot produce a false hit: evictor ``on_evict`` drops the
      stem, TTL expiry fails closed then revalidates against ``os.path.exists``,
      ``get`` FileNotFound heals the entry, and ``clear`` empties everything;
  (c) a restart rebuild indexes exactly the rank/model ``.bin`` stems.

``_collect_existing_component_keys`` is additionally driven through a minimal
harness object so the real unbound method runs without constructing a full
``HiCacheFile`` (the "minimal fake with the same code path" the dispatch asks
for). The harness only supplies the three attributes the method reads.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

import torch

from sglang.srt.mem_cache import hicache_storage as hs
from sglang.srt.mem_cache.hicache_storage import (
    HiCacheFile,
    HiCacheStorageConfig,
    MetadataCache,
    PoolName,
)
from sglang.srt.mem_cache.storage.file.lru_file_evictor import LRUFileEvictor

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = "R130test"
# tp_size=1, pp_size=1, attn_cp_size=1, non-MLA -> config_suffix is stable.
SUFFIX = f"_{MODEL}_0_1"


def make_config(extra_config=None, **overrides) -> HiCacheStorageConfig:
    kwargs = dict(
        tp_rank=0,
        tp_size=1,
        pp_rank=0,
        pp_size=1,
        attn_cp_rank=0,
        attn_cp_size=1,
        is_mla_model=False,
        enable_storage_metrics=False,
        is_page_first_layout=False,
        model_name=MODEL,
        extra_config=extra_config,
    )
    kwargs.update(overrides)
    return HiCacheStorageConfig(**kwargs)


def meta_extra(ttl: float = -1.0, **extra) -> dict:
    cfg = {"enable_metadata_cache": True, "metadata_ttl": ttl, "min_free_space": 0}
    cfg.update(extra)
    return cfg


class TempStoreCase(unittest.TestCase):
    """Base: one isolated temp dir per test, cleaned up afterwards."""

    def setUp(self) -> None:
        os.makedirs(HERE, exist_ok=True)
        self.tmp = tempfile.mkdtemp(dir=HERE, prefix="_tmp_")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def storage(self, extra_config=None, **overrides) -> HiCacheFile:
        return HiCacheFile(make_config(extra_config, **overrides), file_path=self.tmp)

    def touch_bin(self, stem: str) -> str:
        path = os.path.join(self.tmp, f"{stem}.bin")
        with open(path, "wb"):
            pass
        return path

    def disc_path(self, suffixed_stem: str) -> str:
        """On-disk path for an already-suffixed stem (stem -> <stem>.bin)."""
        return os.path.join(self.tmp, f"{suffixed_stem}.bin")


class TestMetadataCacheDirect(unittest.TestCase):
    """Unit-level TTL/CRUD semantics of MetadataCache (no filesystem)."""

    def test_absent_key_returns_false(self):
        cache = MetadataCache(5.0)
        self.assertFalse(cache.contains("nope"))
        self.assertEqual(cache.cache, {})

    def test_add_then_contains_true_and_does_not_dup(self):
        cache = MetadataCache(5.0)
        cache.add("k")
        ts = cache.cache["k"]
        cache.add("k")  # must not overwrite / duplicate
        self.assertTrue(cache.contains("k"))
        self.assertEqual(cache.cache["k"], ts)
        self.assertEqual(len(cache.cache), 1)

    def test_remove_drops_key(self):
        cache = MetadataCache(5.0)
        cache.add("k")
        cache.remove("k")
        self.assertFalse(cache.contains("k"))
        cache.remove("k")  # idempotent

    def test_clear_empties(self):
        cache = MetadataCache(5.0)
        for i in range(100):
            cache.add(f"k{i}")
        cache.clear()
        self.assertEqual(cache.cache, {})
        self.assertFalse(cache.contains("k0"))

    def test_ttl_minus_one_never_expires(self):
        cache = MetadataCache(-1.0)
        cache.add("k")
        with mock.patch.object(hs.time, "monotonic", return_value=time.monotonic() + 1e9):
            self.assertTrue(cache.contains("k"))
            self.assertIn("k", cache.cache)

    def test_ttl_expiry_deletes_and_returns_false(self):
        cache = MetadataCache(5.0)
        with mock.patch.object(hs.time, "monotonic", return_value=10_000.0):
            cache.add("k")
        # exactly at the boundary is still live (> ttl is the condition)
        with mock.patch.object(hs.time, "monotonic", return_value=10_005.0):
            self.assertTrue(cache.contains("k"))
        # past the boundary: False and the entry is deleted (fails closed)
        with mock.patch.object(hs.time, "monotonic", return_value=10_005.0001):
            self.assertFalse(cache.contains("k"))
            self.assertNotIn("k", cache.cache)

    def test_ttl_real_sleep_expires(self):
        cache = MetadataCache(0.05)
        cache.add("k")
        self.assertTrue(cache.contains("k"))
        time.sleep(0.08)
        self.assertFalse(cache.contains("k"))

    def test_add_does_not_refresh_timestamp(self):
        """TTL is measured from first insertion, not last access.

        This is why the default 5 s TTL forces an eventual per-key revalidation
        even for hot keys: repeated sees do not extend the deadline.
        """
        cache = MetadataCache(5.0)
        with mock.patch.object(hs.time, "monotonic", return_value=1_000.0):
            cache.add("k")
        with mock.patch.object(hs.time, "monotonic", return_value=1_003.0):
            self.assertTrue(cache.contains("k"))
            cache.add("k")  # no refresh expected
        with mock.patch.object(hs.time, "monotonic", return_value=1_005.0001):
            self.assertFalse(cache.contains("k"))

    def test_contains_is_thread_safe_under_concurrency(self):
        import threading

        cache = MetadataCache(-1.0)
        errors = []

        def worker(start):
            try:
                for i in range(start, start + 2000):
                    cache.add(f"k{i}")
                    cache.contains(f"k{i}")
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(j * 2000,)) for j in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(cache.cache), 8000)


class TestHiCacheFileCorrectness(TempStoreCase):
    """(a)/(b) end-to-end against the real HiCacheFile backend."""

    VALUE = torch.arange(1024, dtype=torch.uint8)

    # ---- (a) new write immediately queryable, no directory scan ----------

    def test_a_new_write_immediately_queryable_without_scan(self):
        h = self.storage(meta_extra())
        self.assertTrue(h.set("pageA", self.VALUE))
        suffixed = h._get_suffixed_key("pageA")

        # RAM index was updated on the success path...
        self.assertTrue(h.metadata_cache.contains(suffixed))
        # ...and every query path resolves it from the index alone.
        with mock.patch("os.scandir", side_effect=AssertionError("scandir used")), \
             mock.patch("os.path.exists", side_effect=AssertionError("exists used")):
            self.assertTrue(h.exists("pageA"))
            collected = h._collect_existing_component_keys(["pageA"], None)
            result = h.batch_exists_v2(["pageA"], None)
        self.assertIn(f"{suffixed}.bin", collected)
        self.assertEqual(result.kv_hit_pages, 1)

    def test_a_set_fast_path_refreshes_then_skips_rewrite(self):
        h = self.storage(meta_extra())
        self.assertTrue(h.set("pageB", self.VALUE))
        mtime = os.path.getmtime(h._get_component_path("pageB"))
        time.sleep(0.01)
        # Second set() hits exists() -> True and must not rewrite the file.
        self.assertTrue(h.set("pageB", self.VALUE))
        self.assertEqual(os.path.getmtime(h._get_component_path("pageB")), mtime)

    # ---- (b) invalidation / GC cannot yield a false hit ------------------

    def test_b_evictor_on_evict_removes_stem_no_false_hit(self):
        # 1000 B values, 3000 B cap, ratio 0.9: writing a 4th key must evict.
        h = self.storage(meta_extra(ttl=-1.0, max_size=3000))
        for i in range(4):
            self.assertTrue(h.set(f"e{i}", self.VALUE))

        evicted = [h._get_suffixed_key(f"e{i}") for i in (0, 1)]
        kept = [h._get_suffixed_key(f"e{i}") for i in (2, 3)]
        for stem in evicted:
            self.assertFalse(h.metadata_cache.contains(stem))
            self.assertFalse(os.path.exists(self.disc_path(stem)))
            # No false hit: exists() must not resurrect it.
            self.assertFalse(h.exists(stem[:-len(SUFFIX)] if stem.endswith(SUFFIX) else stem))
        for stem in kept:
            self.assertTrue(h.metadata_cache.contains(stem))
        on_disk = [n for n in os.listdir(self.tmp) if n.endswith(".bin")]
        self.assertEqual(len(on_disk), 2)

    def test_b_evictor_on_evict_fires_on_filenotfound_too(self):
        """FileNotFoundError branch in _evict_one_lru_locked also calls on_evict."""
        cache = MetadataCache(-1.0)
        ev = LRUFileEvictor(
            self.tmp,
            SUFFIX,
            tp_rank=0,
            is_mla_model=False,
            extra_config={"max_size": 2000, "min_free_space": 0},
            on_evict=cache.remove,
        )
        # Reserve/commit index entries for files that do NOT exist on disk.
        stems = [f"a{SUFFIX}", f"b{SUFFIX}", f"c{SUFFIX}"]
        for stem in stems:
            cache.add(stem)
            self.assertTrue(ev.reserve(stem, 1000))
            ev.commit(stem)
        self.assertTrue(ev.reserve(f"d{SUFFIX}", 1000))
        # a and b were evicted via the FileNotFoundError branch; on_evict ran.
        self.assertFalse(cache.contains(f"a{SUFFIX}"))
        self.assertFalse(cache.contains(f"b{SUFFIX}"))

    def test_b_ttl_expiry_then_revalidate_existing_file(self):
        h = self.storage(meta_extra(ttl=0.05))
        self.assertTrue(h.set("t", self.VALUE))
        stem = h._get_suffixed_key("t")
        self.assertTrue(h.metadata_cache.contains(stem))

        time.sleep(0.08)
        self.assertFalse(h.metadata_cache.contains(stem))  # expired, fails closed

        real_exists = os.path.exists
        with mock.patch.object(
            hs.os.path, "exists", side_effect=real_exists
        ) as spy:
            self.assertTrue(h.exists("t"))  # file is on disk -> revalidated
        self.assertGreaterEqual(spy.call_count, 1)
        self.assertTrue(h.metadata_cache.contains(stem))  # re-added

    def test_b_ttl_expiry_then_missing_file_stays_false(self):
        h = self.storage(meta_extra(ttl=0.05))
        self.assertTrue(h.set("gone", self.VALUE))
        stem = h._get_suffixed_key("gone")
        os.remove(self.disc_path(stem))  # out-of-band delete, no on_evict
        time.sleep(0.08)
        self.assertFalse(h.exists("gone"))
        self.assertFalse(h.metadata_cache.contains(stem))

    def test_b_get_filenotfound_removes_stale_metadata(self):
        h = self.storage(meta_extra(ttl=-1.0))
        self.assertTrue(h.set("g", self.VALUE))
        stem = h._get_suffixed_key("g")
        os.remove(self.disc_path(stem))  # no callback: index is stale
        self.assertTrue(h.metadata_cache.contains(stem))  # documents the window

        target = torch.zeros(1024, dtype=torch.uint8)
        self.assertIsNone(h.get("g", target))
        self.assertFalse(h.metadata_cache.contains(stem))  # healed

    def test_b_clear_empties_files_and_metadata(self):
        h = self.storage(meta_extra(ttl=-1.0))
        for i in range(5):
            self.assertTrue(h.set(f"c{i}", self.VALUE))
        self.assertTrue(h.metadata_cache.cache)
        self.assertTrue(h.clear())
        self.assertEqual(h.metadata_cache.cache, {})
        self.assertEqual(os.listdir(self.tmp), [])
        for i in range(5):
            self.assertFalse(h.exists(f"c{i}"))

    # ---- (c) restart rebuild ---------------------------------------------

    def test_c_restart_rebuild_indexes_exact_stems(self):
        expected = set()
        for i in range(25):
            stem = f"page{i:03d}{SUFFIX}"
            self.touch_bin(stem)
            expected.add(stem)
        # different rank/model suffix must be excluded
        for i in range(8):
            self.touch_bin(f"other{i:03d}_OtherModel_1_4")
        # non-.bin must be excluded
        for i in range(4):
            with open(os.path.join(self.tmp, f"junk{i}.txt"), "w"):
                pass

        first = self.storage(meta_extra(ttl=-1.0))
        self.assertEqual(set(first.metadata_cache.cache), expected)

        # Simulate a process restart over the same directory.
        second = self.storage(meta_extra(ttl=-1.0))
        self.assertEqual(set(second.metadata_cache.cache), expected)
        # Every indexed stem is queryable with no filesystem probe.
        with mock.patch("os.path.exists", side_effect=AssertionError("probe used")):
            for stem in expected:
                raw = stem[: -len(SUFFIX)]
                self.assertTrue(second.exists(raw))

    def test_c_scan_indexes_dotbin_directory_with_matching_suffix(self):
        """Characterises current behavior: the rebuild scan does not isfile().

        A *directory* whose name matches ``<stem><config_suffix>.bin`` is
        indexed as if it were a file (and later re-validated by os.path.exists,
        which is also True for a directory). Not a required property; recorded
        so the orchestrator can judge whether it matters operationally.
        """
        ok = f"real{SUFFIX}.bin"
        self.touch_bin(f"real{SUFFIX}")
        os.mkdir(os.path.join(self.tmp, f"dirmasq{SUFFIX}.bin"))
        h = self.storage(meta_extra(ttl=-1.0))
        self.assertIn(f"real{SUFFIX}", h.metadata_cache.cache)
        self.assertIn(f"dirmasq{SUFFIX}", h.metadata_cache.cache)


class _CollectHarness:
    """Minimal stand-in supplying only what the real collect method reads."""

    def __init__(self, file_path, metadata_cache, suffix):
        self.file_path = file_path
        self.metadata_cache = metadata_cache
        self._suffix = suffix

    def _get_suffixed_key(self, key: str) -> str:
        return key + self._suffix

    def _get_component_key(self, key, component_name=None):
        if component_name is None or component_name in ("__default__", PoolName.KV):
            return self._get_suffixed_key(key)
        return self._get_suffixed_key(f"{key}.{component_name}")


class TestCollectExistingComponentKeys(TempStoreCase):
    """Drive the real unbound method via a minimal harness (both branches)."""

    def test_metadata_branch_never_scans_and_revalidates(self):
        # present: on disk + already indexed
        self.touch_bin(f"present{SUFFIX}")
        # fresh: on disk but not yet indexed (must be found via os.path.exists)
        self.touch_bin(f"fresh{SUFFIX}")
        cache = MetadataCache(-1.0)
        cache.add(f"present{SUFFIX}")
        harness = _CollectHarness(self.tmp, cache, SUFFIX)
        keys = ["present", "fresh", "missing"]

        with mock.patch("os.scandir", side_effect=AssertionError("scandir used")):
            found = HiCacheFile._collect_existing_component_keys(harness, keys, None)

        self.assertEqual(
            found, {f"present{SUFFIX}.bin", f"fresh{SUFFIX}.bin"}
        )
        self.assertTrue(cache.contains(f"fresh{SUFFIX}"))  # re-added
        self.assertFalse(cache.contains(f"missing{SUFFIX}"))

    def test_metadata_branch_expired_entry_revalidated(self):
        self.touch_bin(f"exp{SUFFIX}")
        cache = MetadataCache(0.05)
        cache.add(f"exp{SUFFIX}")
        time.sleep(0.08)
        harness = _CollectHarness(self.tmp, cache, SUFFIX)
        with mock.patch("os.scandir", side_effect=AssertionError("scandir used")):
            found = HiCacheFile._collect_existing_component_keys(
                harness, ["exp"], None
            )
        self.assertEqual(found, {f"exp{SUFFIX}.bin"})
        self.assertTrue(cache.contains(f"exp{SUFFIX}"))

    def test_none_branch_scans_directory(self):
        self.touch_bin(f"one{SUFFIX}")
        self.touch_bin(f"two{SUFFIX}")
        self.touch_bin("three_OtherModel_1_4")
        harness = _CollectHarness(self.tmp, None, SUFFIX)
        found = HiCacheFile._collect_existing_component_keys(
            harness, ["one", "two", "missing"], None
        )
        self.assertEqual(found, {f"one{SUFFIX}.bin", f"two{SUFFIX}.bin"})

    def test_component_keys_are_resolved(self):
        self.touch_bin(f"page{SUFFIX}")
        self.touch_bin(f"page.swa{SUFFIX}")
        cache = MetadataCache(-1.0)
        harness = _CollectHarness(self.tmp, cache, SUFFIX)
        transfer = mock.Mock()
        transfer.name = PoolName.SWA
        found = HiCacheFile._collect_existing_component_keys(
            harness, ["page"], [transfer]
        )
        self.assertEqual(found, {f"page{SUFFIX}.bin", f"page.swa{SUFFIX}.bin"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
