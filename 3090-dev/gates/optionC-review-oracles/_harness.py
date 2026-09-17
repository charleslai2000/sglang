# SPDX-License-Identifier: Apache-2.0
"""Clean-room falsification harness for the extent-slot "live-ref relocation"
change (F1 Option-C).

This module is deliberately independent of any test code that ships with the
tree under test.  It drives only:

  * the public ``HiCacheStorage`` surface (batch_set / batch_get / batch_set_v1
    / batch_get_v1 / batch_set_v2 / batch_get_v2 / batch_exists / batch_exists_v2
    / open_group / commit_group / checkpoint / close), and
  * the frozen ``ExtentAllocator`` bookkeeping fields (``_index``,
    ``_generations``, ``_slot_keys``, ``_slot_bytes``, ``_cursors``,
    ``_next_slot``, ``_recency``) purely as *observation* of the allocator's
    own published state.

Every oracle:

  * takes ``--tree`` (default: the frozen production candidate),
  * asserts ``sglang.__file__`` really resolves inside the requested tree,
  * writes a JSON result with per-check PASS/FAIL/INVALID detail,
  * returns a deterministic exit code (PASS=0, FAIL=1, INVALID=2, ERROR=3).

Semantics used throughout (from the review contract):

  victim slot      a slot selected for generation bump / reuse.
  live index ref   an ``ExtentAllocator._index`` entry whose generation matches
                   its slot generation (i.e. ``lookup`` returns it).
  destination      a non-victim slot that received relocated bytes.
  feasible         at the trigger there exists enough non-victim free space to
                   hold every victim live ref (first-fit-decreasing over the
                   non-victim free tail gaps, plus fully-empty non-victim
                   slots).  Feasibility only classifies expectation; the safety
                   invariant is checked unconditionally.

NOTE ON SYNTHETIC PRESTATES: ``build_capacity_scenario`` produces a state whose
hole arises from a real same-key rewrite (delete-then-reinsert) and whose
wrap is produced by real writes.  It is not a synthetic allocator injection.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time

# ---------------------------------------------------------------------------
# tree loading
# ---------------------------------------------------------------------------

DEFAULT_TREE = "/opt/sglang/local-prod-v1.1-candidate"


def resolve_python_root(tree: str) -> str:
    """Return the directory that must be on sys.path to import this tree."""
    candidates = [
        os.path.join(tree, "src", "python"),
        os.path.join(tree, "python"),
        tree,
    ]
    for cand in candidates:
        if os.path.isdir(os.path.join(cand, "sglang")):
            return os.path.abspath(cand)
    raise SystemExit(
        f"could not find sglang package under {tree!r}; tried {candidates}"
    )


_TREE_INFO = {}


def load_tree(tree: str = DEFAULT_TREE):
    """Import the tree under test and bind its classes into this module.

    Returns a dict with the resolved root and the imported module objects.
    """
    root = resolve_python_root(tree)
    if root not in sys.path:
        sys.path.insert(0, root)
    import sglang  # noqa: PLC0415

    sglang_file = os.path.abspath(sglang.__file__)
    if not sglang_file.startswith(root + os.sep):
        raise SystemExit(
            "tree identity violation: sglang imported from "
            f"{sglang_file!r}, not under requested tree root {root!r}"
        )
    from sglang.srt.mem_cache.hicache_storage import (  # noqa: PLC0415
        HiCacheStorageConfig,
        PoolHitPolicy,
        PoolName,
        PoolTransfer,
        PoolTransferResult,
    )
    from sglang.srt.mem_cache.storage.extent import (  # noqa: PLC0415
        extent_allocator as alloc_mod,
    )
    from sglang.srt.mem_cache.storage.extent import (  # noqa: PLC0415
        extent_file_backend as backend_mod,
    )
    from sglang.srt.mem_cache.storage.extent import (  # noqa: PLC0415
        extent_metadata as meta_mod,
    )

    g = globals()
    g["sglang"] = sglang
    g["HiCacheStorageConfig"] = HiCacheStorageConfig
    g["PoolHitPolicy"] = PoolHitPolicy
    g["PoolName"] = PoolName
    g["PoolTransfer"] = PoolTransfer
    g["PoolTransferResult"] = PoolTransferResult
    g["ExtentRef"] = alloc_mod.ExtentRef
    g["ExtentAllocator"] = alloc_mod.ExtentAllocator
    g["ExtentFileBackend"] = backend_mod.ExtentFileBackend
    g["backend_mod"] = backend_mod
    g["meta_mod"] = meta_mod
    _TREE_INFO.clear()
    _TREE_INFO.update(
        {
            "tree": os.path.abspath(tree),
            "python_root": root,
            "sglang_file": sglang_file,
            "sglang_version": getattr(sglang, "__version__", None),
        }
    )
    return dict(_TREE_INFO)


def tree_info() -> dict:
    return dict(_TREE_INFO)


# ---------------------------------------------------------------------------
# backend construction
# ---------------------------------------------------------------------------

def make_config(
    storage_dir: str,
    *,
    extent_size: str = "16Ki",
    file_size: str = "64Ki",
    model_name: str = "reviewmodel",
    tp_rank: int = 0,
    tp_size: int = 1,
    is_mla_model: bool = False,
    max_size: str | None = None,
    min_free_space: str | None = None,
    eviction_ratio: float | None = None,
    wal_checkpoint_bytes: int = 0,
):
    extra = {
        "storage_dir": storage_dir,
        "extent_size": extent_size,
        "file_size": file_size,
        "wal_checkpoint_bytes": wal_checkpoint_bytes,
    }
    if max_size is not None:
        extra["max_size"] = max_size
    if min_free_space is not None:
        extra["min_free_space"] = min_free_space
    if eviction_ratio is not None:
        extra["eviction_ratio"] = eviction_ratio
    return HiCacheStorageConfig(
        extra_config=extra,
        tp_rank=tp_rank,
        tp_size=tp_size,
        pp_rank=0,
        pp_size=1,
        attn_cp_rank=0,
        attn_cp_size=1,
        is_mla_model=is_mla_model,
        enable_storage_metrics=False,
        is_page_first_layout=True,
        model_name=model_name,
    )


def make_backend(storage_dir: str, **kwargs):
    return ExtentFileBackend(make_config(storage_dir, **kwargs))


# ---------------------------------------------------------------------------
# host-pool stubs (torch-free v2, optional torch v1 zero-copy)
# ---------------------------------------------------------------------------

class PagePool:
    """torch-free host pool stand-in for the flat/v2 surfaces."""

    def __init__(self, page_bytes: int, slots: int = 256):
        self.page_size = 1
        self._page_bytes = page_bytes
        self._pages = [bytearray(page_bytes) for _ in range(slots)]
        self.layout = "page_first"

    def set_page(self, index: int, data: bytes) -> None:
        assert len(data) == self._page_bytes, (len(data), self._page_bytes)
        self._pages[index][:] = data

    def read_page(self, index: int) -> bytes:
        return bytes(self._pages[index])

    def get_data_page(self, index, flat=True):
        return self._pages[index]

    def get_dummy_flat_data_page(self):
        return bytearray(self._page_bytes)

    def set_from_flat_data_page(self, index, data_page):
        self._pages[index][:] = data_page


class V1Pool:
    """Minimal zero-copy host pool for ``batch_get_v1`` / ``batch_set_v1``.

    Layout model: ``blocks_per_page`` contiguous blocks per page, each
    ``block_bytes`` long; the stored flat page is the concatenation of the
    blocks in order (page_first MHA / MLA shape).  Distinct per-block fill
    patterns detect a block-order swap.  Requires torch for a stable CPU
    buffer address; the oracle marks the v1 sub-check INVALID when torch is
    unavailable.
    """

    def __init__(self, num_pages: int, blocks_per_page: int = 2, block_bytes: int = 600):
        import torch  # noqa: PLC0415

        self._torch = torch
        self.page_size = 1
        self.layout = "page_first"
        self.blocks_per_page = blocks_per_page
        self.block_bytes = block_bytes
        self.num_pages = num_pages
        self._buf = torch.zeros(
            num_pages * blocks_per_page * block_bytes, dtype=torch.uint8
        )

    @property
    def page_bytes(self) -> int:
        return self.blocks_per_page * self.block_bytes

    def _offset(self, page: int, block: int) -> int:
        return (page * self.blocks_per_page + block) * self.block_bytes

    def set_page(self, page: int, data: bytes) -> None:
        assert len(data) == self.page_bytes, (len(data), self.page_bytes)
        for b in range(self.blocks_per_page):
            src = data[b * self.block_bytes : (b + 1) * self.block_bytes]
            a = self._offset(page, b)
            self._buf[a : a + self.block_bytes] = self._torch.tensor(
                list(src), dtype=self._torch.uint8
            )

    def read_page(self, page: int) -> bytes:
        out = bytearray()
        for b in range(self.blocks_per_page):
            a = self._offset(page, b)
            out += bytes(self._buf[a : a + self.block_bytes].numpy().tobytes())
        return bytes(out)

    def host_indices(self, pages) -> list:
        return list(range(pages[0], pages[-1] + 1))

    def get_page_buffer_meta(self, host_indices):
        ptrs, sizes = [], []
        base = self._buf.data_ptr()
        for idx in host_indices:
            for b in range(self.blocks_per_page):
                ptrs.append(base + self._offset(int(idx), b))
                sizes.append(self.block_bytes)
        return ptrs, sizes


# ---------------------------------------------------------------------------
# content + byte comparison
# ---------------------------------------------------------------------------

def content(tag: str, size: int) -> bytes:
    """Deterministic, non-repeating page bytes (checksum-sensitive)."""
    out = bytearray()
    counter = 0
    while len(out) < size:
        out += hashlib.sha256(f"{tag}:{counter}".encode()).digest()
        counter += 1
    return bytes(out[:size])


def sha256_hex(data) -> str:
    return hashlib.sha256(bytes(data)).hexdigest()


def bytes_equal_exact(got, expected) -> bool:
    if got is None:
        return False
    return bytes(got) == bytes(expected)


# ---------------------------------------------------------------------------
# allocator observation helpers
# ---------------------------------------------------------------------------

def storage_suffix(backend) -> str:
    return backend.config_suffix


def strip_suffix(storage_key: str, suffix: str) -> str:
    if suffix and storage_key.endswith(suffix):
        return storage_key[: -len(suffix)]
    return storage_key


def require_allocator_fields(backend) -> str | None:
    alloc = getattr(backend, "_allocator", None)
    if alloc is None:
        return "backend._allocator missing"
    for name in ("_index", "_generations", "_slot_keys", "_slot_bytes", "_cursors"):
        if not hasattr(alloc, name):
            return f"allocator.{name} missing"
    return None


def index_snapshot(backend) -> dict:
    """storage_key -> ref dict, taken under the backend index lock."""
    alloc = backend._allocator
    with backend._lock:
        return {
            k: {
                "extent_id": r.extent_id,
                "offset": r.offset,
                "length": r.length,
                "generation": r.generation,
            }
            for k, r in alloc._index.items()
        }


def generations_snapshot(backend) -> list:
    alloc = backend._allocator
    with backend._lock:
        return list(alloc._generations)


def slot_bytes(backend) -> list:
    alloc = backend._allocator
    with backend._lock:
        return list(alloc._slot_bytes)


def free_tails(backend) -> dict:
    """slot -> free bytes at the append cursor (frozen allocator model)."""
    alloc = backend._allocator
    extent = alloc.extent_size
    with backend._lock:
        return {s: extent - alloc._cursors[s] for s in range(alloc.num_slots)}


def lookup_ref(backend, storage_key: str):
    alloc = backend._allocator
    with backend._lock:
        return alloc.lookup(storage_key)


def read_logical_flat(backend, logical_key: str, length: int) -> bytes | None:
    """Read via the public flat path; returns None on miss/short."""
    target = bytearray(length)
    try:
        got = backend.batch_get([logical_key], [target])[0]
    except Exception:
        return None
    if got is None:
        return None
    return bytes(got) if len(got) == length else bytes(got)


def feasible_relocation(free_by_slot: dict, victim_slots, refs_by_slot: dict) -> dict:
    """First-fit-decreasing packing of victim refs into non-victim free tails.

    ``free_by_slot`` values are the append-cursor free bytes (holes behind the
    cursor are NOT counted; an implementation with a hole free-list may do
    better, which is why infeasibility only classifies expectation).
    """
    victim = set(victim_slots)
    dest_free = {s: f for s, f in free_by_slot.items() if s not in victim}
    refs = [r for s in victim for r in refs_by_slot.get(s, [])]
    total_ref = sum(r["length"] for r in refs)
    total_dest = sum(dest_free.values())
    max_ref = max((r["length"] for r in refs), default=0)
    max_dest = max(dest_free.values(), default=0)
    # greedy first-fit-decreasing
    bins = sorted(dest_free.values(), reverse=True)
    ok = True
    for r in sorted(refs, key=lambda x: -x["length"]):
        placed = False
        for i, b in enumerate(bins):
            if b >= r["length"]:
                bins[i] = b - r["length"]
                placed = True
                break
        if not placed:
            ok = False
            break
    return {
        "packable": ok,
        "total_ref_bytes": total_ref,
        "total_dest_free": total_dest,
        "max_ref_bytes": max_ref,
        "max_dest_free": max_dest,
        "dest_free": dest_free,
    }


# ---------------------------------------------------------------------------
# scenarios (natural write history, no allocator injection)
# ---------------------------------------------------------------------------

def build_capacity_scenario(backend, *, mixed_mamba: bool = False):
    """Build: victim slot 0 holds live refs; slot 1 has a large free tail;
    the next single-page write wraps into slot 0 and overwrites its bytes.

    Natural history:
      H 8000 -> slot0 [0,8000)
      H  100 -> slot0 [8000,8100)   (same-key rewrite leaves a hole)
      [mixed: a 1000 KV, m 1200 MAMBA, b 1000 KV -> slot0]
      s 8300 -> slot1 (slot0's free 8284 cannot take it)
      B1 16300 -> slot2; B2 16300 -> slot3
      trigger T 9000 -> slot3 full, slot0 free 8284 < 9000 -> passed victim 0

    Returns a dict describing the live keys to preserve and the trigger while
    leaving the backend positioned immediately before the trigger.
    """
    suffix = storage_suffix(backend)
    live: dict = {}          # read_key (logical, incl. .mamba) -> bytes
    writes = []              # (kind, key, value)
    hbig = content("H-big", 8000)
    hsmall = content("H-small", 100)
    writes.append(("flat", "H", hbig))
    writes.append(("flat", "H", hsmall))
    if mixed_mamba:
        a = content("a", 1000)
        b = content("b", 1000)
        m = content("m", 1200)
        writes.append(("flat", "a", a))
        writes.append(("mamba", "m", m))
        writes.append(("flat", "b", b))
        live["a"] = a
        live["m.mamba"] = m
        live["b"] = b
    else:
        a = content("a", 1000)
        b = content("b", 1000)
        writes.append(("flat", "a", a))
        writes.append(("flat", "b", b))
        live["a"] = a
        live["b"] = b
    live["H"] = hsmall
    writes.append(("flat", "s", content("s", 8300)))
    writes.append(("flat", "B1", content("B1", 16300)))
    writes.append(("flat", "B2", content("B2", 16300)))

    for kind, key, value in writes:
        _scenario_write(backend, kind, key, value)

    return {
        "suffix": suffix,
        "live": live,
        "all_keys": {k: v for k, v in live.items()},
        "trigger_key": "T",
        "trigger_value": content("T-trigger", 9000),
        "trigger_kind": "flat",
    }


def build_v1_scenario(backend, pool: "V1Pool", *, pages_per_slot: int, num_keys: int):
    """v1 zero-copy scenario with the surface's mandatory uniform page length.

    ``batch_get_v1`` refuses a ref whose length differs from the current pool
    page length, so every key uses the same page length (the real engine
    contract).  We fill every slot so the next page wraps into victim slot 0
    with no non-victim capacity (tail model); a relocating implementation must
    either fail closed or preserve the victim refs.
    """
    suffix = storage_suffix(backend)
    live = {}
    keys = [f"v{i:03d}" for i in range(num_keys)]
    for i, key in enumerate(keys):
        value = content(key, pool.page_bytes)
        pool.set_page(i, value)
        ok = backend.batch_set_v1([key], [i])
        if not ok or ok[0] is not True:
            raise RuntimeError(f"v1 scenario write failed for {key}: {ok!r}")
        live[key] = value
    trig = content("VT-trigger", pool.page_bytes)
    pool.set_page(num_keys, trig)
    return {
        "suffix": suffix,
        "live": live,
        "trigger_key": "VT",
        "trigger_value": trig,
        "trigger_kind": "v1",
        "page_ids": {"VT": num_keys},
    }


def _scenario_write(backend, kind: str, key: str, value: bytes) -> None:
    if kind == "flat":
        ok = backend.batch_set([key], [bytearray(value)])
        if not ok:
            raise RuntimeError(f"scenario flat write refused for {key}")
    elif kind == "mamba":
        pool = getattr(backend, "_scenario_mamba_pool", None)
        if pool is None:
            pool = PagePool(len(value))
            backend._scenario_mamba_pool = pool
            backend.register_mem_host_pool_v2(pool, PoolName.MAMBA)
        pool._page_bytes = len(value)
        pool._pages[0] = bytearray(value)
        result = backend.batch_set_v2(
            [PoolTransfer(name=PoolName.MAMBA, host_indices=[0], keys=[key])]
        )
        if not result.get(PoolName.MAMBA, [False])[0]:
            raise RuntimeError(f"scenario mamba write refused for {key}: {result!r}")
    else:
        raise ValueError(f"unknown scenario write kind {kind!r}")


def build_nocapacity_scenario(backend):
    """Fill every slot completely so the wrap victim has no non-victim room."""
    suffix = storage_suffix(backend)
    live = {}
    # extent 16Ki / 1000 B pages -> 16 pages fill a slot, 64 pages fill 4 slots.
    for i in range(64):
        key = f"n{i:03d}"
        value = content(key, 1000)
        ok = backend.batch_set([key], [bytearray(value)])
        if not ok:
            raise RuntimeError(f"nocapacity priming refused for {key}")
        live[key] = value
    return {
        "suffix": suffix,
        "live": live,
        "trigger_key": "NTRIG",
        "trigger_value": content("NTRIG", 1000),
        "trigger_kind": "flat",
    }


# ---------------------------------------------------------------------------
# trigger execution + invariant checks
# ---------------------------------------------------------------------------

def run_trigger(backend, scen, *, v1_pool=None):
    """Snapshot, fire the trigger, return an observation record."""
    pre_index = index_snapshot(backend)
    pre_gen = generations_snapshot(backend)
    pre_free = free_tails(backend)
    pre_slot_bytes = slot_bytes(backend)
    stats_before = dict(backend.stats_snapshot()) if hasattr(backend, "stats_snapshot") else {}

    kind = scen["trigger_kind"]
    if kind == "v1":
        ok = backend.batch_set_v1(
            [scen["trigger_key"]], [scen["page_ids"][scen["trigger_key"]]]
        )
        ok = bool(ok and ok[0] is True)
    else:
        ok = bool(backend.batch_set([scen["trigger_key"]], [bytearray(scen["trigger_value"])]))

    post_index = index_snapshot(backend)
    post_gen = generations_snapshot(backend)
    post_free = free_tails(backend)
    stats_after = dict(backend.stats_snapshot()) if hasattr(backend, "stats_snapshot") else {}

    victims = [s for s, (a, b) in enumerate(zip(pre_gen, post_gen)) if b > a]
    refs_by_slot: dict = {}
    for skey, ref in pre_index.items():
        refs_by_slot.setdefault(ref["extent_id"], []).append(ref)
    feasibility = feasible_relocation(pre_free, victims, refs_by_slot)

    return {
        "ok": ok,
        "victims": victims,
        "pre_gen": pre_gen,
        "post_gen": post_gen,
        "pre_index": pre_index,
        "post_index": post_index,
        "pre_free": pre_free,
        "post_free": post_free,
        "pre_slot_bytes": pre_slot_bytes,
        "feasibility": feasibility,
        "stats_before": stats_before,
        "stats_after": stats_after,
    }


def victim_live_keys(obs, scen) -> dict:
    """storage_key -> pre ref for live refs inside a generation-bumped slot."""
    victims = set(obs["victims"])
    return {
        k: r for k, r in obs["pre_index"].items() if r["extent_id"] in victims
    }


def verify_pre_key_bytes(backend, scen, storage_key: str, expected: bytes) -> dict:
    """Read a (possibly relocated) victim key back and compare checksums."""
    suffix = scen["suffix"]
    logical = strip_suffix(storage_key, suffix)
    ref = lookup_ref(backend, storage_key)
    got = read_logical_flat(backend, logical, len(expected))
    return {
        "storage_key": storage_key,
        "resolves": ref is not None,
        "ref": (
            None
            if ref is None
            else {
                "extent_id": ref.extent_id,
                "offset": ref.offset,
                "length": ref.length,
                "generation": ref.generation,
            }
        ),
        "expected_sha256": sha256_hex(expected),
        "got_sha256": None if got is None else sha256_hex(got),
        "length_ok": got is not None and len(got) == len(expected),
        "bytes_ok": bytes_equal_exact(got, expected),
    }


# ---------------------------------------------------------------------------
# WAL frame logging (crash matrix)
# ---------------------------------------------------------------------------

def install_frame_log(backend) -> list:
    """Wrap ``_append_wal_frame`` to record (type, seq, byte offset)."""
    import base64  # noqa: PLC0415

    log: list = []
    orig = backend._append_wal_frame

    def hooked(frame_type, payload):
        log.append(
            {
                "type": int(frame_type),
                "seq": int(getattr(backend, "_wal_next_seq", -1)),
                "offset": int(getattr(backend, "_wal_offset", -1)),
                "wal_generation": getattr(backend, "_wal_generation", None),
                "payload_b64": base64.b64encode(bytes(payload)).decode("ascii"),
            }
        )
        return orig(frame_type, payload)

    backend._append_wal_frame = hooked
    return log


FRAME_NAMES = {1: "SET", 2: "BATCH_COMMIT", 3: "GROUP_COMMIT", 4: "DROP_SLOT", 5: "CLEAR", 6: "CHECKPOINT_MARK"}


def frame_name(frame_type: int) -> str:
    return FRAME_NAMES.get(int(frame_type), f"UNKNOWN({frame_type})")


# ---------------------------------------------------------------------------
# result protocol
# ---------------------------------------------------------------------------

class OracleResult:
    def __init__(self, oracle: str, mode: str = "candidate"):
        self.oracle = oracle
        self.mode = mode
        self.checks: list = []
        self.notes: list = []
        self.started = time.time()
        self.error: str | None = None

    def check(self, cid: str, question: str, ok, detail: str = "", required: bool = True, evidence=None):
        """ok: True (pass), False (fail), None (could not evaluate -> INVALID)."""
        self.checks.append(
            {
                "id": cid,
                "question": question,
                "ok": ok,
                "required": required,
                "detail": detail,
                "evidence": evidence,
            }
        )
        return ok

    def note(self, text: str):
        self.notes.append(text)

    @property
    def status(self) -> str:
        if self.error:
            return "ERROR"
        required = [c for c in self.checks if c["required"]]
        if any(c["ok"] is False for c in required):
            return "FAIL"
        if any(c["ok"] is None for c in required):
            return "INVALID"
        if not required:
            return "INVALID"
        return "PASS"

    @property
    def exit_code(self) -> int:
        return {"PASS": 0, "FAIL": 1, "INVALID": 2, "ERROR": 3}[self.status]

    def to_dict(self) -> dict:
        failed = [c["id"] for c in self.checks if c["ok"] is False]
        invalid = [c["id"] for c in self.checks if c["ok"] is None and c["required"]]
        return {
            "oracle": self.oracle,
            "status": self.status,
            "mode": self.mode,
            "tree": tree_info(),
            "started_ts": self.started,
            "finished_ts": time.time(),
            "checks": self.checks,
            "failed_checks": failed,
            "invalid_checks": invalid,
            "notes": self.notes,
            "error": self.error,
            "python": sys.version,
            "env": {
                "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
            },
        }

    def finish(self, out_path: str | None = None, argv=None) -> int:
        payload = self.to_dict()
        if argv is not None:
            payload["argv"] = list(argv)
        if out_path:
            os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
            with open(out_path, "w") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return self.exit_code


def add_common_args(parser):
    parser.add_argument("--tree", default=DEFAULT_TREE, help="tree under test")
    parser.add_argument("--out", default=None, help="JSON result path")
    parser.add_argument(
        "--mode",
        default="candidate",
        choices=["candidate", "frozen-control"],
        help="candidate (expect PASS/INVALID) or frozen-control (expect FAIL)",
    )
    parser.add_argument("--keep-tmp", action="store_true")
    return parser


def make_tmproot(prefix: str, keep: bool = False) -> str:
    import tempfile  # noqa: PLC0415

    root = tempfile.mkdtemp(prefix=prefix)
    if not keep:
        import atexit  # noqa: PLC0415

        atexit.register(shutil.rmtree, root, True)
    return root
