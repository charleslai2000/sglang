# G3-IQ3-NOCOPY-LAYOUT-IMPLEMENT-20260908

status: done
invocation_status: done
task_id: G3-IQ3-NOCOPY-LAYOUT-IMPLEMENT-20260908
epoch: E6
role: coder

## Scope

Implemented only the first IQ3 optimization in the local checkout: merged GGUF
shards are packed once into one flat allocation, and `GGUFLinearMethod.apply`
uses stable contiguous views into that allocation. No remote host, model,
kernel C++/CUDA file, benchmark, Mamba/cache/scheduler setting, or product
profile was changed.

## Changed files

- `python/sglang/srt/layers/quantization/gguf.py`
  - Added `_pack_gguf_shards`, which preserves caller-selected logical shard
    order, copies each shard once, and records logical and physical metadata.
  - Added `_gguf_shard_view`, which reconstructs a contiguous `as_strided`
    view from the flat packed allocation.
  - Replaced the rectangular padded merged-weight allocation in
    `GGUFLinearMethod._create_padded_weight_param` with the one-time packed
    layout. The original data container is cleared after packing, so the
    implementation does not permanently retain both layouts.
  - Changed `GGUFLinearMethod.apply` to use the packed view. A legacy fallback
    remains for old in-memory rectangular parameters without
    `shard_storage_map`; newly processed merged GGUF layers take the no-copy
    path.
- `test/registered/expert_pack/test_gguf_shard_layout.py`
  - CPU-only tests for exact shard bytes, logical output order, contiguous
    views, stable data pointers, and repeated `GGUFLinearMethod.apply` calls.

## Verification

Commands run from the repository root:

```text
python3 -m py_compile python/sglang/srt/layers/quantization/gguf.py test/registered/expert_pack/test_gguf_shard_layout.py
git diff --check
```

Both completed successfully. The local shell has `/usr/bin/python3` but no
`torch` module and no `pytest` module, so this environment could not execute
the new CPU tests. No CUDA graph or GPU-kernel compatibility is claimed.

## Correctness boundaries

- IQ3 bytes are copied unchanged; qtype and shard row/column dimensions are
  retained in metadata.
- `q/k/v` ordering continues to use `_ordered_gguf_shard_ids`; arbitrary
  non-QKV labels retain their existing checkpoint order.
- Physical shard starts are aligned to 256 bytes (converted to dtype elements)
  and each view uses row-major contiguous strides.
- This is a static post-load immutable layout change. CUDA graph replay,
  Tensor Parallel/offload reload, and end-to-end output equivalence still
  require verification in an environment with the deployed dependencies.

## Open issues / followups

- Run `test/registered/expert_pack/test_gguf_shard_layout.py` with the
  repository's torch/pytest environment.
- Perform the requested short GPU/operator and graph validation before any
  benchmark claim.
- The activation-quantization reuse and IQ3 small-batch kernel work remain
  separate tasks and were not changed here.

No extra work was performed; further changes require a fresh Task ID.
