#!/usr/bin/env python3
"""B0 forced-shape discrimination experiment patch (architect design 1.2).

Flags: /tmp/b0-fs/{split,nobranch,notrack} — file exists = active, else no-op.
Zero numerical-path pollution: flag check is a pure boolean os.path.exists.

Files:
  schedule_policy.py — helper + FS-2 (split)
  schedule_batch.py  — helper + FS-3 (nobranch) + FS-4 (notrack)
Backups: <file>.bak-b0fs (refuses to overwrite an existing backup)
Rollback: cp <file>.bak-b0fs <file> + md5 verify + docker restart sglang-b0.
unified_radix_cache.py is NOT touched (b2a probe md5 must stay b9868f3f0f3ec48c90ea9414b828d417).
"""
import hashlib
import os
import py_compile
import shutil
import sys

MANAGERS = "/sgl-workspace/sglang/python/sglang/srt/managers"
POLICY = f"{MANAGERS}/schedule_policy.py"
BATCH = f"{MANAGERS}/schedule_batch.py"

HELPER_DEF = '''

def _b0_fs_flag(name: str) -> bool:
    return os.path.exists(f"/tmp/b0-fs/{name}")
'''

PATCHES = [
    # (file, anchor, replacement, description)
    (
        POLICY,
        "import os\nimport random",
        "import os\nimport random" + HELPER_DEF,
        "P1 helper (_b0_fs_flag) in schedule_policy.py",
    ),
    (
        POLICY,
        """                # Non-chunked prefill — the whole sequence is committed this iter.
                req.set_extend_range(
                    len(req.prefix_indices), len(req.full_untruncated_fill_ids)
                )
                self.can_run_list.append(req)""",
        """                # Non-chunked prefill — the whole sequence is committed this iter.
                req.set_extend_range(
                    len(req.prefix_indices), len(req.full_untruncated_fill_ids)
                )
                # B0-FS: force last-grid-point split for mamba-hit requests (experiment).
                if _b0_fs_flag("split") and mamba_extra_buffer_enabled() and len(req.prefix_indices) > 0:
                    base = len(req.prefix_indices)
                    grid = mamba_checkpoint_grid(self.tree_cache.page_size)
                    last_track = base + (req.extend_range.length // grid) * grid
                    if last_track > base and last_track < base + req.extend_range.length:
                        req.set_extend_range(base, last_track)
                        self.new_chunked_req = req
                self.can_run_list.append(req)""",
        "P2 FS-2 split (force last-grid-point split for mamba-hit) in add_one_req",
    ),
    (
        BATCH,
        "import re\nimport sys",
        "import re\nimport os\nimport sys" + HELPER_DEF,
        "P3 helper (_b0_fs_flag) in schedule_batch.py",
    ),
    (
        BATCH,
        '            if req.mamba_branching_seqlen is not None:',
        '            if req.mamba_branching_seqlen is not None and not _b0_fs_flag("nobranch"):',
        "P4 FS-3 nobranch (gate branching-override)",
    ),
    (
        BATCH,
        "        mask = req.extend_range.length >= checkpoint_grid",
        """        mask = req.extend_range.length >= checkpoint_grid and not (
            _b0_fs_flag("notrack") and req.mamba_branching_seqlen is not None
        )""",
        "P5 FS-4 notrack (disable track for branching requests)",
    ),
]


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    # 1. Backup (refuse to overwrite)
    for p in (POLICY, BATCH):
        bak = p + ".bak-b0fs"
        if os.path.exists(bak):
            print(f"ABORT: backup already exists: {bak} (refusing to overwrite)")
            sys.exit(1)
        shutil.copy2(p, bak)
        print(f"backup created: {bak}")

    # 2. md5 before
    before = {p: md5(p) for p in (POLICY, BATCH)}
    print("md5 before:")
    for p, m in before.items():
        print(f"  {m}  {p}")

    # 3. Apply patches with anchor uniqueness assertion
    for path, anchor, repl, desc in PATCHES:
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        n = src.count(anchor)
        if n != 1:
            print(f"ABORT: anchor count != 1 ({n}) for [{desc}] in {path}")
            sys.exit(1)
        src = src.replace(anchor, repl)
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        print(f"OK: {desc} (anchor count was {n})")

    # 4. md5 after
    after = {p: md5(p) for p in (POLICY, BATCH)}
    print("md5 after:")
    for p, m in after.items():
        print(f"  {m}  {p}")

    # 5. py_compile
    for p in (POLICY, BATCH):
        try:
            py_compile.compile(p, doraise=True)
            print(f"py_compile OK: {p}")
        except py_compile.PyCompileError as e:
            print(f"py_compile FAILED: {p}: {e}")
            sys.exit(1)

    # 6. Anchor counts
    print("anchor counts:")
    for p in (POLICY, BATCH):
        with open(p, "r", encoding="utf-8") as f:
            src = f.read()
        print(f"  {p}: B0-FS={src.count('B0-FS')} _b0_fs_flag={src.count('_b0_fs_flag')}")

    print("DONE")


if __name__ == "__main__":
    main()
