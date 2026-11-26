# T009 Code Review: SWA release synchronization and sliding-window metadata

**Status:** T009 remains ACTIVE. Performance reruns are paused by user direction. This is a source review and evidence recovery only; no GPU workload was started.

**Review base/current source:** base `cb0132a6f6b0875b07eea6a911e02ef053d87f83`; current production tree `308e7d6b9b9e5c8674942fbfa2f8a76d7563c007`. `git diff cb0132a6f6 -- python/sglang/srt` shows exactly one production file changed: `python/sglang/srt/layers/attention/triton_backend.py`. `allocator/swa.py` was not changed between the T009 base and current HEAD; its relevant release implementation and actual callers are included in full below as requested. The four +/- edits below are the complete production diff (unchanged surrounding lines omitted only where explicitly shown by unified diff context).

## 1. Complete production diff from `cb0132a6f6`

```diff
diff --git a/python/sglang/srt/layers/attention/triton_backend.py b/python/sglang/srt/layers/attention/triton_backend.py
index 179a862ec2..8eca8f97c2 100644
--- a/python/sglang/srt/layers/attention/triton_backend.py
+++ b/python/sglang/srt/layers/attention/triton_backend.py
@@ -740,8 +740,12 @@ class TritonAttnBackend(AttentionBackend):
             self.cuda_graph_kv_indices[:n_kv] = self._translate_kv_loc(
                 self.cuda_graph_kv_indices[:n_kv]
             )
-        # SWA window read path. window_kv_indptr[bs] == sum(min(seq_len, window)).
+        # SWA window read path. The buffer is maximum-capacity while
+        # window_kv_indptr delimits the live prefix, so both the exact live
+        # length (CPU mirror) and the fixed capacity are correct. Never read the
+        # device prefix sum here: that was a per-step blocking D2H.
         if self.sliding_window_size is not None and self.sliding_window_size > 0:
+            buf = self.cuda_graph_window_kv_indices
             if have_cpu_mirror:
                 n_win = int(
                     forward_batch.seq_lens_cpu[:bs]
@@ -749,12 +753,14 @@ class TritonAttnBackend(AttentionBackend):
                     .sum()
                 )
             else:
-                n_win = int(self.window_kv_indptr[bs].item())
+                # No trusted mirror (gpu_only batch): translate the whole
+                # fixed-capacity buffer. The tail is outside indptr and unused,
+                # and the window builder zero-initializes it to the sink, so the
+                # translate gather stays in-bounds.
+                n_win = buf.shape[0]
             if n_win > 0:
-                self.cuda_graph_window_kv_indices[:n_win] = (
-                    self.token_to_kv_pool.translate_loc_from_full_to_swa(
-                        self.cuda_graph_window_kv_indices[:n_win]
-                    )
+                buf[:n_win] = self.token_to_kv_pool.translate_loc_from_full_to_swa(
+                    buf[:n_win]
                 )
         # Full-attention write path: translate out_cache_loc -> physical into the
         # capture-stable buffer and RETURN the [:n] view.
@@ -2177,14 +2183,15 @@ def update_sliding_window_buffer(
     )
     window_kv_indptr[1 : bs + 1] = torch.cumsum(window_kv_lens, dim=0)
     window_kv_indptr = window_kv_indptr[: bs + 1]
-    # Reading the token total off the prefix sums is a device->host sync. Read it
-    # once and reuse it for both the buffer size and the translate slice.
-    total_tokens = None
+    # The sum of window lengths is data-dependent on device. Allocate maximum
+    # capacity and let indptr delimit the live prefix; never read the prefix sum
+    # back to size a Python tensor/slice. Clear it because reused eager buffers
+    # may otherwise retain stale ids in the unused tail.
     if window_kv_indices is None:
         window_kv_indices = torch.empty(
-            total_tokens, dtype=torch.int64, device=device
+            bs * sliding_window_size, dtype=torch.int64, device=device
         )
+    window_kv_indices.zero_()
     window_kv_start_idx = seq_lens - window_kv_lens
     create_flashinfer_kv_indices_triton[(bs,)](
         req_to_token,
@@ -2198,11 +2205,9 @@ def update_sliding_window_buffer(
     if not skip_full_to_swa_translation and hasattr(
         token_to_kv_pool, "translate_loc_from_full_to_swa"
     ):
-        if total_tokens is None:
-            total_tokens = int(window_kv_indptr[-1])
-        window_kv_indices[:total_tokens] = (
-            token_to_kv_pool.translate_loc_from_full_to_swa(
-                window_kv_indices[:total_tokens]
-            )
+        # Unused capacity was initialized to the sink above, so translating
+        # the fixed-capacity buffer cannot observe stale indices beyond indptr.
+        window_kv_indices[:] = token_to_kv_pool.translate_loc_from_full_to_swa(
+            window_kv_indices
         )
     return window_kv_indptr, window_kv_indices, window_kv_lens, window_kv_start_idx
```

No T009 production diff changes allocator release semantics, synchronization dependencies, or the SWA tombstone filter. The sync-removal change is maximum-capacity window metadata plus removal of a device scalar read.

## 2. `allocator/swa.py`: complete relevant release functions and callers

The functions below are the current implementations in `python/sglang/srt/mem_cache/allocator/swa.py`. The hybrid allocator's `free` and `free_swa` map full token indices to SWA-owned indices; `free_group_end` preserves enqueue-time ownership snapshots and applies the padding filter once per group. `PureSWATokenToKVPoolAllocator` separately filters padding because it has no full/SWA peer map.

```python
    def free(self, free_index: torch.Tensor):
        if free_index.numel() == 0:
            return

        # NOTE: the API is not idempotent.
        if self.free_group is None:
            self.full_attn_allocator.free(free_index)
            self.free_swa(free_index)
        else:
            self.free_group.append(self._copy_for_free_group(free_index))
        assert (
            self.full_attn_allocator.available_size() <= self.full_attn_allocator.size
        )
        assert self.swa_attn_allocator.available_size() <= self.swa_attn_allocator.size

    def free_swa(self, free_index: torch.Tensor):
        if free_index.numel() == 0:
            return

        if self.page_size == 1:
            mapping_indices = free_index
        else:
            mapping_indices = self._expand_to_full_pages(free_index)

        swa_indices = self.full_to_swa_index_mapping[mapping_indices]
        self.clear_full_to_swa_mapping(mapping_indices)

        if self.free_group is not None:
            # Resolve ownership now. A cache action later in this group may
            # install a new mapping for the same full index. Keep the mapping
            # exactly as read at this instant (padding included): the padding
            # filter is a mask kernel per call, and applying it once over the
            # concatenated group frees the same set of slots.
            self.swa_free_group.append(swa_indices)
            return

        # A tombstoned range's entries read as the padding slot, so the filter
        # has to stay on this path: the caller cannot prove every mapping here
        # is a live SWA slot, and freeing slot 0 would corrupt the free list.
        self.swa_attn_allocator.free(swa_indices[swa_indices > 0])

    def free_full(self, free_index: torch.Tensor):
        if free_index.numel() == 0:
            return

        if self.free_group is None:
            # Full side only: a tombstoned range's mapping entries read as the
            # padding slot, so `free` would push slot 0 into the SWA free list.
            self.full_attn_allocator.free(free_index)
        else:
            self.full_free_group.append(self._copy_for_free_group(free_index))
        assert (
            self.full_attn_allocator.available_size() <= self.full_attn_allocator.size
        )

    def free_group_begin(self):
        super().free_group_begin()
        self.swa_free_group = []
        self.full_free_group = []

    def free_group_end(self):
        super().free_group_end()
        if self.swa_free_group:
            swa_free_group = self.swa_free_group
            self.swa_free_group = []
            freed = torch.cat(swa_free_group)
            # One padding filter for the whole group instead of one per
            # release; entries that read as 0 (tombstone/padding) are dropped
            # here exactly as they were dropped per call before.
            self.swa_attn_allocator.free(freed[freed > 0])
        if self.full_free_group:
            full_free_group = self.full_free_group
            self.full_free_group = []
            self.free_full(torch.cat(full_free_group))
```

The separate pure-SWA implementation is also a real release function:

```python
    def free(self, free_index: torch.Tensor):
        if free_index.numel() == 0:
            return
        if self.free_group is None:
            self.swa_attn_allocator.free(free_index[free_index > 0])
        else:
            self.free_group.append(self._copy_for_free_group(free_index))
        assert self.swa_attn_allocator.available_size() <= self.swa_attn_allocator.size

    def free_swa(self, free_index: torch.Tensor):
        if free_index.numel() == 0:
            return
        if self.free_group is None:
            self.swa_attn_allocator.free(free_index[free_index > 0])
        else:
            self.free_group.append(self._copy_for_free_group(free_index))

    def free_full(self, free_index: torch.Tensor):
        # All-SWA models have no full-attention pool, so there is nothing to
        # release once the SWA side is gone.
        return

    # Not inherited: the SWA parent's hooks drive swa_free_group and
    # full_free_group, which this pure-SWA variant does not have.
    def free_group_begin(self):
        self.free_group = []

    def free_group_end(self):
        pending, self.free_group = self.free_group, None
        if pending:
            self.free(torch.cat(pending))
```

### Direct call sites

1. **Out-of-window request allocation release** — `python/sglang/srt/mem_cache/common.py`, `free_swa_out_of_window_slots(req, ...)`: obtains request slots in `[swa_evicted_seqlen:new_swa_evicted_seqlen]`, calls `token_to_kv_pool_allocator.free_swa(free_slots)`, then advances `req.kv.swa_evicted_seqlen`. This is not a cache-node liveness proof; request history may include already tombstoned/missing mapping slots, so zeros can be present.
2. **SWA radix eviction** — `python/sglang/srt/mem_cache/swa_radix_cache.py`, `SWARadixCache.evict`: for an internal node or a leaf still full-locked, calls `free_swa(x.value)` and tombstones/removes the SWA side. The node can remain in the full radix structure after insert-time/out-of-window tombstoning, so `x.value` can include slots whose mapping has already been cleared. This is the demonstrated reason a generic caller contract “all mappings are live” is false.
3. **SWA early lock release** — `SWARadixCache.dec_swa_lock_only`: when the final SWA lock on a leaf drops while the full lock remains, calls `free_swa(node.value)`, removes it from SWA LRU, and marks the node tombstoned; the full-side KV and radix value remain until full unlock.
4. **Unified-cache component actions** — `python/sglang/srt/mem_cache/unified_cache/components/swa_component.py`, `apply_component_action(FreeComponentDeviceSlot)`: dispatches each action index tensor to allocator `free_swa`. Components are applied during cache action commit/reconciliation, where the allocator must honor existing mappings/tombstones.
5. **Indirect shared allocator call** — `SWATokenToKVPoolAllocator.free` calls `self.free_swa(free_index)` when not grouped. It is used where both Full and SWA ownership is to be released; `free_full` is the distinct Full-only path for tombstoned nodes.
6. `PureSWATokenToKVPoolAllocator.free_swa` is used through the same cache abstractions for all-SWA models; its filter is the independent pure-pool slot-zero guard.

The `>0` selection generates a data-dependent result length (`nonzero`/DeviceSelect); for the hybrid path this is necessary because tombstones resolve to the sink mapping 0. Grouping reduces filter count but does not eliminate it. A peer-live call-site shortcut was tested and rejected: ranges can contain tombstoned values even when represented by a cache node, leading to lost SWA ownership/backup and host-pressure drops.

## 3. Sliding-window metadata: complete implementation, callers, graph metadata, and gather kernel

### Complete `update_sliding_window_buffer`

```python
def update_sliding_window_buffer(
    window_kv_indptr,
    req_to_token,
    sliding_window_size,
    seq_lens,
    req_pool_indices,
    bs,
    device=None,
    token_to_kv_pool=None,
    window_kv_indices=None,
    skip_full_to_swa_translation=False,
):
    """Fill window KV buffers for sliding-window attention.

    Pass ``window_kv_indices`` to write into a pre-allocated buffer (CUDA-graph
    path); omit it (or pass ``None``) to allocate a fresh tensor (eager path,
    requires ``device``).

    ``skip_full_to_swa_translation=True`` leaves ``window_kv_indices`` as VIRTUAL
    full-token ids (no eager full->swa translate). The unified-memory-pool cuda-graph
    builder passes this so the window translate is deferred to
    ``TritonAttnBackend._translate_cuda_graph_shared_pool_locs`` (run in
    ``init_forward_metadata_out_graph``, BEFORE ``graph.replay()``), which reads
    the live v2p and rewrites the static window buffer to swa-physical in place;
    baseline SWA leaves it False (eager).
    """
    window_kv_lens = torch.minimum(
        seq_lens,
        _window_size_tensor(sliding_window_size, seq_lens.device),
    )
    window_kv_indptr[1 : bs + 1] = torch.cumsum(window_kv_lens, dim=0)
    window_kv_indptr = window_kv_indptr[: bs + 1]
    # The sum of window lengths is data-dependent on device. Allocate maximum
    # capacity and let indptr delimit the live prefix; never read the prefix sum
    # back to size a Python tensor/slice. Clear it because reused eager buffers
    # may otherwise retain stale ids in the unused tail.
    if window_kv_indices is None:
        window_kv_indices = torch.empty(
            bs * sliding_window_size, dtype=torch.int64, device=device
        )
    window_kv_indices.zero_()
    window_kv_start_idx = seq_lens - window_kv_lens
    create_flashinfer_kv_indices_triton[(bs,)](
        req_to_token,
        req_pool_indices,
        window_kv_lens,
        window_kv_indptr,
        window_kv_start_idx,
        window_kv_indices,
        req_to_token.stride(0),
    )
    if not skip_full_to_swa_translation and hasattr(
        token_to_kv_pool, "translate_loc_from_full_to_swa"
    ):
        # Unused capacity was initialized to the sink above, so translating
        # the fixed-capacity buffer cannot observe stale indices beyond indptr.
        window_kv_indices[:] = token_to_kv_pool.translate_loc_from_full_to_swa(
            window_kv_indices
        )
    return window_kv_indptr, window_kv_indices, window_kv_lens, window_kv_start_idx
```

### Actual callers

- `_update_decode_kv_buffers`: CUDA Graph decode/idle preparation, writes into `cuda_graph_window_kv_indices`; a unified memory pool passes `skip_full_to_swa_translation=True` and translates during replay preparation before graph replay.
- `_update_target_verify_buffers`: graph capture/replay target-verify path, fills static CUDA Graph window indices, lengths and per-request offsets; virtual-to-SWA translation defaults to eager in this helper, followed by the normal shared-pool replay translation when applicable.
- `init_forward_metadata`, decode/idle without spec-provided KV metadata: eager call with newly allocated index buffer and optional split lengths.
- `init_forward_metadata`, target-verify mode: eager call; returns window offsets used with the custom mask.
- `init_forward_metadata`, extend/prefill mode: eager call with `extend_prefix_lens`; returned window metadata feeds the attention forward path.

### CUDA Graph buffer allocation and metadata ownership

Graph buffers are allocated in `TritonAttnBackend.init_cuda_graph_state` (around lines 1088–1103): `cuda_graph_window_kv_indices` is fixed-capacity `max_num_tokens * sliding_window_size` (or a compatible shared `kv_indices_buf` shape), int64, zero initialized; `cuda_graph_window_num_kv_splits` is `[max_num_tokens]` int32; `cuda_graph_window_kv_offsets` is `[max_bs]` int32. `window_kv_indptr` is static backend state; callers return its batch view, and it remains the authoritative live-prefix delimiter. `_build_cuda_graph_forward_metadata` passes the same stable CUDA buffers and `window_kv_indptr[:bs+1]` in decode/idle and verify metadata. During `init_forward_metadata_out_graph`, `_apply_cuda_graph_metadata` refreshes indices/indptr before capture/replay, `_translate_cuda_graph_shared_pool_locs` (when shared unified memory is active) does the pre-replay v2p translation, and `_build_cuda_graph_forward_metadata` exposes the buffers to captured attention kernels. No captured consumer is allowed to infer live length from `window_kv_indices.shape`; each row’s live extent is `window_kv_indptr[i+1]-window_kv_indptr[i]`.

For shared-pool replay, `seq_lens_sum is not None` is the reliable signal that a host mirror is valid. The CPU mirror length is `sum(min(seq_lens_cpu[:bs], sliding_window_size))`; otherwise the fixed full capacity is translated. `window_kv_indptr` is deliberately not read to host. Full KV indices still use `seq_lens_sum` or, for gpu-only batches, an independent `kv_indptr[bs].item()` fallback; the T009 window change does not remove that separate full-KV fallback.

### Relevant gather kernel

The actual gather used by the builder is `create_flashinfer_kv_indices_triton` in `python/sglang/kernels/ops/kvcache/kv_indices.py`. Full implementation:

```python
@triton.jit
def create_flashinfer_kv_indices_triton(
    req_to_token_ptr,  # [max_batch, max_context_len]
    req_pool_indices_ptr,
    page_kernel_lens_ptr,
    kv_indptr,
    kv_start_idx,
    kv_indices_ptr,
    req_to_token_ptr_stride: tl.constexpr,
):
    BLOCK_SIZE: tl.constexpr = 512
    pid = tl.program_id(axis=0)

    # find the req pool idx, this is for batch to token
    req_pool_index = tl.load(req_pool_indices_ptr + pid)
    kv_indices_offset = tl.load(kv_indptr + pid)

    kv_start = 0
    kv_end = 0
    if kv_start_idx:
        kv_start = tl.load(kv_start_idx + pid).to(tl.int32)
        kv_end = kv_start
    kv_end += tl.load(page_kernel_lens_ptr + pid).to(tl.int32)

    num_loop = tl.cdiv(kv_end - kv_start, BLOCK_SIZE)
    for i in range(num_loop):
        # index into req_to_token_ptr needs to be int64
        offset = tl.arange(0, BLOCK_SIZE).to(tl.int64) + i * BLOCK_SIZE
        mask = offset < kv_end - kv_start
        data = tl.load(
            req_to_token_ptr
            + req_pool_index * req_to_token_ptr_stride
            + kv_start
            + offset,
            mask=mask,
        )
        tl.store(kv_indices_ptr + kv_indices_offset + offset, data, mask=mask)
```

This kernel writes only each row’s live range into the flat destination; the fixed-capacity tail is therefore explicitly zeroed before the launch (and outside `indptr` regardless). The returned `window_kv_start_idx = seq_lens - window_kv_lens` selects the suffix of each request’s token table. The gather grid is `(bs,)`; each program uses the row’s `indptr` base and a masked loop up to the per-row length.

## 4. Upstream PR #36723: adaptation and concrete unresolved blocker

The upstream change is present in this repository’s history as commit `19c7679e9e9c6f36e0ede15c0900ab3c63fafdd5` (`[mem_cache] Make free_swa sync-free on page_size == 1 (#36723)`). Its central contract is: when `page_size == 1`, do not boolean-filter a mapped-index tensor; instead assert every supplied full index has a live SWA peer (`swa_indices > 0`) with an invariant. Then release the whole tensor. For paged pools, it expands full indices and keeps the positive-index filter because a page can include unmapped slots; group release filters once. It additionally checks `free_full` sees mappings already cleared, and adjusts grouped Full release not to invoke that check after a later group action can remap the slot.

This repository has that commit in `git` history, but the live T009 base/current implementation does **not** contain its page-size-1 assertion. T009’s acceptance fixture is Gemma hybrid SWA with page size 1, but the observed cache semantics invalidate the upstream caller premise: `insert-time/out-of-window` tombstoning clears `full_to_swa_index_mapping` while the full radix value can remain; request out-of-window release, SWA eviction, early SWA lock release, and unified `FreeComponentDeviceSlot` actions may therefore pass a range containing mapping zeros. A fatal invariant would turn an existing legal tombstone into a runtime failure. Simply removing the check and releasing all returned indices would insert slot 0 into the free list and permit duplicate allocation/corrupt KV ownership. Experimental evidence: a T009 caller peer-live variant produced 494.41 TPS, 108,800 host-pressure dropped tokens, and SWA backup tokens fell from 617,477 to 166,413; it was reverted.

**Concrete unresolved obstacle:** the safe result must preserve (a) slot 0 as the sink and never free it; (b) filtering of data-dependent tombstone zeros without host-side shape synchronization; (c) exact-once release and ownership snapshots across grouped cache actions where the same full index can be remapped before group flush; (d) paged HiCache load-back, where full and SWA mappings can be offset/unmapped within expanded pages; and (e) immediately usable allocator capacity under the 65,536-slot SWA budget. A caller-liveness contract is not true globally. No allocator-level compaction/bitset/free-list design has yet been implemented or proven to satisfy these simultaneously; that is the outstanding T009 code obstacle, not missing knowledge of the upstream patch.

## 5. Recovered payload comparison evidence (no GPU replay)

No prior run hash log remained under `/data` or the worktree: the current run directory had only the new `20261126T-t009-c8-acceptance-r3/hashes.jsonl`. The official benchmark inputs are nevertheless reconstructible from the archived fixture inputs and deterministic command contract: local Gemma tokenizer/model at `/data/sglang-hicache/gemma4/model`, dataset `/data/sglang-hicache/datasets/ShareGPT_V3_unfiltered_cleaned_split.json`, 40 clients × 20 rounds, input 1,024/output 256, Poisson 8, seed 42, `--fixed-history-tokens`, and the benchmark’s deterministic `(client,round)` subquestion assignment. I reconstructed the 800 input-id rows offline using the same `sample_random_requests` and `WorkloadGenerator` path, fixed seed initialization, per-client fixed-history RNG, and request hash algorithm; compared `(client,len,sha)` records as a multiset against the run’s 800-line `hashes.jsonl`. Result: **800 reconstructed, 800 observed, exact multiset equality: true**. This is CPU/offline fixture recovery; no server, CUDA, or GPU workload was invoked. Earlier accepted same-payload references are independently recorded in `tasks/T007-gpu-throughput-scheduling.md` and the T007 C-8 baseline report. The full recovered request hash artifact is the exact 800 records already present at `/data/sglang-hicache/gemma4/runs/20261126T-t009-c8-acceptance-r3/hashes.jsonl`; no extra copy or run directory was created.

## Verification and status

- `git diff cb0132a6f6 -- python/sglang/srt` confirms the complete production diff shown in §1 and no allocator production edit.
- The C-8 rerun was not repeated. Latest available outcome remains 570.88 official output TPS, 800/800, zero failures, below the ≥600 gate. Gate unmet; T009 remains ACTIVE.
- No GPU load, experiment, or new run directory was created for this review or payload recovery.
