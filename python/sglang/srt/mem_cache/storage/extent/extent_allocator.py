# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to SGLang project

"""Pure-logic circular extent allocator for the ExtentFileBackend.

File layout contract (the backend's pwrite target):

    slot s occupies file bytes [s * extent_size, (s + 1) * extent_size);
    a key's bytes live at [slot_base + ref.offset, + ref.length).

The allocator owns all in-memory state: per-slot generations, the pack
cursor, the key -> ExtentRef index, per-slot bookkeeping, and the LRU
recency order. It never touches the filesystem and holds no lock -- the
backend serializes every call under a single index lock and performs the
page IO outside that lock.

Allocation is two-phase so a failed pwrite leaves no state behind:
``plan`` computes refs purely (zero mutation), ``commit`` applies them once
the write succeeded. Reusing a slot (the circular cursor wrapping into a
slot that cannot hold another page) or watermark GC eviction bumps the
slot's generation, so any index entry captured before the reuse fails the
read-side re-verification (generation mismatch = miss).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import List, Optional, Sequence, Tuple

import msgspec


class ExtentRef(msgspec.Struct, frozen=True):
    extent_id: int
    offset: int
    length: int
    generation: int


class ExtentAllocator:
    """Circular extent allocator with generation-based invalidation.

    All methods require the caller to hold the backend's index lock; there
    is no internal synchronization.
    """

    def __init__(self, extent_size: int, num_slots: int):
        if extent_size <= 0 or extent_size % 4096 != 0:
            # 4KiB sector alignment: the reserved O_DIRECT calibration tier
            # can only touch whole extents, so slot geometry must stay aligned.
            raise ValueError(
                f"extent_size must be a positive multiple of 4096, got {extent_size}"
            )
        if num_slots <= 0:
            raise ValueError(f"num_slots must be positive, got {num_slots}")
        self.extent_size = extent_size
        self.num_slots = num_slots
        self._generations = [0] * num_slots
        self._next_slot = 0
        self._cursors = [0] * num_slots
        self._slot_keys: List[set] = [set() for _ in range(num_slots)]
        self._slot_bytes = [0] * num_slots
        self._index: dict = {}
        self._recency: OrderedDict = OrderedDict()

    # ---- read side ----

    @property
    def used_bytes(self) -> int:
        return sum(self._slot_bytes)

    def lookup(self, key: str) -> Optional[ExtentRef]:
        ref = self._index.get(key)
        if ref is None:
            return None
        if ref.generation != self._generations[ref.extent_id]:
            # Stale entry that survived a slot drop; treat as absent.
            self._index.pop(key, None)
            self._recency.pop(key, None)
            return None
        return ref

    def snapshot(self, keys: Sequence[str]) -> List[Optional[ExtentRef]]:
        return [self.lookup(k) for k in keys]

    def verify(
        self, keys: Sequence[str], refs: Sequence[Optional[ExtentRef]]
    ) -> List[bool]:
        """Re-validate that each key still maps to its exact snapshot ref.

        Slot reuse since the snapshot (eviction, cursor wrap, rewrite) changes
        the entry or its generation; the snapshot data must not be served.
        """
        ok: List[bool] = []
        for key, ref in zip(keys, refs):
            ok.append(ref is not None and self._index.get(key) == ref)
        return ok

    def touch(self, key: str) -> None:
        if key in self._index:
            self._recency.pop(key, None)
            self._recency[key] = None

    # ---- write side ----

    def plan(
        self, key_lengths: Sequence[Tuple[str, int]]
    ) -> Tuple[List[Optional[ExtentRef]], List[int]]:
        """Compute placement for a batch of (key, byte length) without mutating.

        Returns ``(refs, passed)`` where ``passed`` lists the slots the pack
        cursor enters that cannot fit the batch and are therefore dropped
        and reset (circular reuse; their old data is the oldest in the
        file); ``commit`` applies those drops plus the new index entries.
        A key longer than ``extent_size`` yields None (cannot be stored),
        as does a batch larger than the whole file.
        """
        refs: List[Optional[ExtentRef]] = []
        passed: List[int] = []
        packed: set = set()
        slot = self._next_slot
        cursor = self._cursors[slot]
        for _key, length in key_lengths:
            if length > self.extent_size:
                refs.append(None)
                continue
            while cursor + length > self.extent_size:
                slot = (slot + 1) % self.num_slots
                if slot in packed:
                    # Batch larger than the whole file: placement would
                    # overwrite this plan's own pages; refuse the batch.
                    return [None] * len(key_lengths), []
                cursor = self._cursors[slot]
                if cursor + length > self.extent_size:
                    passed.append(slot)
                    cursor = 0
            packed.add(slot)
            refs.append(
                ExtentRef(
                    slot,
                    cursor,
                    length,
                    self._generations[slot] + passed.count(slot),
                )
            )
            cursor += length
        return refs, passed

    def commit(self, keys: Sequence[str], refs: Sequence[ExtentRef], passed: List[int]) -> None:
        """Apply a plan after its pwrite succeeded (the backend's ACK point)."""
        for slot in passed:
            self._drop_slot(slot)
        for key, ref in zip(keys, refs):
            if ref is None:
                continue
            old = self._index.get(key)
            if old is not None:
                self._slot_keys[old.extent_id].discard(key)
                self._slot_bytes[old.extent_id] -= old.length
            self._index[key] = ref
            self._slot_keys[ref.extent_id].add(key)
            self._slot_bytes[ref.extent_id] += ref.length
            self._cursors[ref.extent_id] = ref.offset + ref.length
            self._recency.pop(key, None)
            self._recency[key] = None
            self._next_slot = ref.extent_id

    # ---- GC ----

    def evict_slot_lru(self) -> int:
        """Drop the slot holding the least-recently-used key; returns the
        number of live bytes freed (0 when there is nothing to evict)."""
        if not self._recency:
            return 0
        oldest_key = next(iter(self._recency))
        oldest = self._index.get(oldest_key)
        if oldest is None:
            self._recency.pop(oldest_key, None)
            return 0
        return self._drop_slot(oldest.extent_id)

    def clear(self) -> None:
        self._index.clear()
        self._recency.clear()
        for slot in range(self.num_slots):
            self._slot_keys[slot].clear()
            self._slot_bytes[slot] = 0
            self._cursors[slot] = 0
        # Generations stay monotonic; any slot reuse still invalidates.

    # ---- internals ----

    def _drop_slot(self, slot: int) -> int:
        freed = self._slot_bytes[slot]
        for key in self._slot_keys[slot]:
            self._index.pop(key, None)
            self._recency.pop(key, None)
        self._slot_keys[slot].clear()
        self._slot_bytes[slot] = 0
        self._cursors[slot] = 0
        self._generations[slot] += 1
        return freed
