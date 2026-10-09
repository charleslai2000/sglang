# DEVOPS-20260908-P0-V2-REMOTE-TEST-R2

Status: done

## Scope and authorization

- Remote: `root@175.155.64.171:24052`, checkout `/root/sglang-b1-continuity`.
- Python: `/root/miniconda3/envs/sglang-patch/bin/python`.
- Only the five specified product files were synchronized. Evidence was written under `/root/evidence-gate3-parked/p0-v2-remote-test-r2/`.
- No drivers, model, storage data, ledger, unrelated files, engine, or vehicle were touched.

## Commands and evidence

- `id -u` returned `0`.
- Local source MD5s were recorded before sync; remote MD5s were recorded before and after sync. Final remote hashes match local hashes:
  - `unified_radix_cache.py`: `19becb418b198480b3b8024636397cc0`
  - `hybrid_cache_controller.py`: `bbc9fcc868981885c42e4e6b939e12af`
  - `extent_file_backend.py`: `98215ecf8da93d1aeebd3e438064f7b3`
  - `extent_allocator.py`: `dfe02e61998b646bda28e65d97c8b10c`
  - `mamba_component.py`: `b5fb6f556013b6716af0d9c0b70e5656`
- Explicit Python `-m py_compile` over all five files exited `0`.
- Required direct command `cd /root/sglang-b1-continuity && /root/miniconda3/envs/sglang-patch/bin/python test/registered/unit/mem_cache/test_extent_file_backend_unit.py` exited `0`; `Ran 77 tests ... OK`.
- Process checks before and after were empty for matching `sglang|engine|driver|storage` processes.

## Evidence artifacts

Remote namespace:

`/root/evidence-gate3-parked/p0-v2-remote-test-r2/`

- `config-process-check.txt`
- `py_compile.stdout`, `py_compile.stderr`, `py_compile.exit`
- `extent-unit.stdout`, `extent-unit.stderr`, `extent-unit.exit`
- `final-check.txt`
- `MD5SUMS`

## Open issues and followups

None. The initial multi-source SCP attempt flattened basenames into the checkout root; those four unintended root-level copies were removed immediately, then each file was copied to its exact authorized destination and cleanup was verified with status `0`.
