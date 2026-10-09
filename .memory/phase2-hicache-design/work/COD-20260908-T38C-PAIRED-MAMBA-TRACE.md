# COD-20260908-T38C-PAIRED-MAMBA-TRACE

## status

done

## artifacts

- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/unified_radix_cache.py`
- `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt/python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`

## summary

Implemented the gated diagnostic-only paired Mamba trace.  With `/tmp/t38c-on`
present, the write submission records node ID, final KV hash, whether a
`BACKUP_STORAGE` Mamba transfer exists, and its exact key.  The extent backend
records the resulting `batch_set_v2` boolean, paired by the same key and carried
node metadata.  The query records raw KV frontier, requested and actually
tested/matched trailing Mamba keys, presence, boundary, and final folded pages.
No token text or state bytes are logged.

The existing all-or-nothing `final_pages = min(final_pages, boundary)` fold is
unchanged.  No component removal/recycle hook was available in the authorized
files; query records state `removal_recycle_hook=not_added`.  No unit test file
was added or modified because it is outside the authorized two-file write scope.

## observed / assumed behavior

- Observed: Mamba `BACKUP_STORAGE` transfer construction occurs in
  `unified_radix_cache.py`; the actual `batch_set_v2` result is available in
  `ExtentFileBackend.batch_set_v2`.
- Observed: extent query performs the trailing scan against the current raw KV
  frontier and can report a zero boundary while retaining the raw KV witness.
- Assumed: the active diagnostic reproduction uses the extent backend, so the
  paired write acknowledgement is emitted there.

## verification

- PASS: `git diff --check`.
- PASS: `python3 -m py_compile python/sglang/srt/mem_cache/unified_radix_cache.py python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`.
- ATTEMPTED: `pytest -q test/registered/unit/mem_cache/test_extent_file_backend_unit.py`; unavailable because `pytest` is not installed.
- ATTEMPTED: `PYTHONPATH=python python3 test/registered/unit/mem_cache/test_extent_file_backend_unit.py`; could not start because `orjson` is missing (`ModuleNotFoundError`), so no assertion result was obtained.
- No GPU execution, deployment, remote-host change, or restore-semantic change was performed.

## followups

- Run the focused extent unit coverage and one S=25 warm-turn reproduction in
  the project runtime with dependencies installed and `/tmp/t38c-on` enabled.
- Pair `pc_mamba_write` and `pc_mamba_query` by `mamba_key` to classify omitted
  transfer, failed write, recycle/removal, or hash mismatch.

## open_issues

- Focused unit execution remains pending the missing pytest/orjson runtime.
- Removal/recycle remains uninstrumented because no keyed hook was exposed in
  the authorized files; the trace explicitly reports that no hook was added.
