# G5-L3-PERFORMANCE-CODE-REVIEW.md

**External architecture review package.** Read-only white-box source review. It includes full bodies of selected current hot-path functions, exact paths and one-based line ranges, historical commits, runtime identities and measured evidence. Curated code bundle, not a repository copy. No production code or workload was changed/run for this report.

## 1. Source identity and runtime differences

- Review repository `/home/ubuntu/workspaces/3rdparty/sglang-hicache`, branch `3090-24g-hicache`, HEAD `06f89994845f0e41c779950924064c16ebfbd956` (`T007: continue HiCache throughput investigation`, 2026-11-25 05:49:05 UTC). That commit changes control/report/harness only, not production Python.
- Current dirty production code: **none** (`git status --porcelain -- python/sglang/srt` empty). Unrelated dirty/untracked files elsewhere are excluded.
- Actual L1+L2 601.36 TPS run source HEAD `cfacaedeb3b1369c7a762f81d2a46751704321ea`; actual full L1+L2+L3 132.724 TPS run source HEAD `035c12fae61f2f5e9934ff15db710a4a8873f25b`. Both runtime module fingerprints equal the reviewed sources: scheduler SHA256 `781ddd07115cd5ff791bf21c4fef82fb89822d91ba72c59f01dd630afd055ec0`; UnifiedRadixCache SHA256 `6962104de869368695cb2835e2de4dd05f3002af51e015aaa1e19169c6af8043`. Though their Git HEAD labels differ, the primary Scheduler and unified radix modules are byte-identical to review HEAD.
- Runtime identity manifests: `/data/sglang-hicache/gemma4/runs/20261125T-t007-l1l2/source-identity.json` and `/data/sglang-hicache/gemma4/runs/20261125T-t007-c8-chunk4096-profile-r3/source-identity.json`.
- Storage: `findmnt -T /`, `/data`, `/mnt/data` all `/dev/sda1` ext4; 484G total, ~411MiB free. `/mnt/data` is on root and not separate. `/dev/shm` is 16G tmpfs, non-durable and prohibited for large Extent by user. No other block device or free LVM volume found. No historical archives were deleted. This blocks another large L3 run pending durable capacity.

## 2. Measured run configs and results

### L1+L2: 601.36 tok/s

Official `benchmark/hicache/bench_multiturn.py`, 40 clients ×20 rounds, nominal 1024 input/256 output, Poisson 8 req/s, seed42, max-parallel64, fixed-history payloads. 800/800 responses, each 256 tokens, zero retractions. Hash log SHA256 `c485aca4659efe60f8a1ce290e308e9145c6d425342bd511413f07933b9d5cd0`.

```text
--model-path /data/sglang-hicache/gemma4/model --trust-remote-code --host 127.0.0.1 --port 31401 --context-length 131072 --max-running-requests 32 --mem-fraction-static .94 --kv-cache-dtype fp8_e5m2 --attention-backend triton --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 32 --log-level info --enable-metrics --decode-log-interval 40 --export-metrics-to-file --export-metrics-to-file-dir /dev/shm/t007-l1l2-run/request-metrics --skip-server-warmup --enable-hierarchical-cache --hicache-size 8 --hicache-write-policy write_through --hicache-io-backend kernel --hicache-mem-layout page_first --hicache-host-memory-mode cache --chunked-prefill-size 4096
```

Online output TPS601.36, input TPS30,970.25, request rate2.35/s, mean latency15.17s, reported cache hit rate0.903883; wrapper/client exit0. Owner-only W4A16/FP8 E5M2; Full/SWA pools1,441,580/65,536. FPM span392s: decode147.4s + extend167.5s = 80.33% aggregate DeviceTimer forward duty. Host pool peak876,807. Prompt counters L1=9,533,440, L2=0, L3=0, newly-prefilled=1,013,760. All request HiCache telemetry outcome=`partial`, authority=`unknown`, prefetch origin=`EAGER_RH_OFF`; not evidence of L2 hit or restored-token correctness. Raw `/data/sglang-hicache/gemma4/runs/20261125T-t007-l1l2/`; report `runs/T007-L1L2-20261125.md`. Nsight: model compute dominates; HiCache relayout ~10.5ms; aggregate D2H459.4ms un-attributed to cache/write-through. Logged capture interval includes profiler start/stop overhead.

### Full L1+L2+L3: 132.724 tok/s

Same official C8 request multiset; 800/800, zero failures/retractions. Exact server argv from `/data/sglang-hicache/gemma4/runs/20261125T-t007-c8-chunk4096-profile-r3/launch-argv.txt`:

```text
--model-path /data/sglang-hicache/gemma4/model --trust-remote-code --host 127.0.0.1 --port 31401 --context-length 131072 --max-running-requests 32 --mem-fraction-static .94 --kv-cache-dtype fp8_e5m2 --attention-backend triton --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 32 --log-level info --enable-metrics --decode-log-interval 40 --export-metrics-to-file --export-metrics-to-file-dir /data/sglang-hicache/gemma4/runs/20261125T-t007-c8-chunk4096-profile-r3/request-metrics --skip-server-warmup --enable-hierarchical-cache --hicache-size 8 --hicache-write-policy write_through --hicache-io-backend kernel --hicache-mem-layout page_first --hicache-host-memory-mode cache --hicache-storage-backend extent --hicache-storage-backend-extra-config {"storage_dir":"/data/sglang-hicache/gemma4/runs/20261125T-t007-c8-chunk4096-profile-r3/l3-extent","extent_size":67108864,"file_size":34359738368,"max_size":34359738368,"min_free_space":1073741824} --hicache-storage-prefetch-policy wait_complete --chunked-prefill-size 4096
```

Online output TPS132.724; duration1543.05s; Full/SWA1,441,580/65,536. DeviceTimer decode215.6s + extend415.3s over1598.1s =39.48% forward duty. NVML mean/p95/max24.08/100/100%. Nsight event span40.809s: GPU busy union14.283s (35.00%), idle26.526s (65.00%). Prompt telemetry L1=9,176,320; L2=167,936; L3=0; new=1,202,944; telemetry remains partial. Raw evidence `/data/sglang-hicache/gemma4/runs/20261125T-t007-c8-chunk4096-profile-r3/`.

Representative same-run log around lines1616–1687: RIDs enter `WAIT_CAPACITY reason=HOST_ALLOC`, allocator generations change, then `HOST_ALLOC_WAKE decision=grant`. Nsight summary: 40.809s span, 26.526s idle, 294 gaps>10ms, max636.7ms; inclusive NVTX `get_next_batch_to_run`9.080s/1849 calls, `run_batch`29.973s/294, `process_batch_result`5.012s/292. 34 FRONTIER and43 HOST_ALLOC intervals overlap window; unique capacity-wait/idle overlap26.526s. Temporal correlation is not proof any waiter alone blocked an admissible batch.

**Comparison caveats:** L1+L2 has zero L2 prompt tokens and no official L1-only TPS was saved. 601.36 vs132.724 is an observed cross-run performance difference, not a controlled causal estimate of L3-only loss. Qwen service uses a different model, load, pool, backend configuration and metric denominator.

## 3. Qwen3.5-9B history: what can and cannot be compared

Local historical evidence: `/home/ubuntu/workspaces/3rdparty/sglang/.pi/experiments/legacy-3090/README.md` and `handover-22151.md`. Qwen3.5-9B GPTQ W4A16 (32 layers,24 Mamba), CUDA13, GPU/Host/NVMe HiCache, separate `/data` L3, Extent160G/min-free10G, `write_back`, prefetch `wait_complete`, Host ratio1.5, max-total-tokens65536, max-running8, pool64, decode graph max8, Ready Horizon off. Gate5 records a short 3.24s decode window: 2048 generated tokens/3.24s=631.4 tok/s; previous p64-c8 short baseline596.5 tok/s. The README calls it noisy and requests longer confirmation. This is not current Gemma4 40×20 official online output TPS.

The exact Qwen deployed tree/SHA and frozen launch script are absent. Handover names remote `/root/sglang-b1-continuity`; we cannot line-diff that source here. **No claim is made that Qwen used different Scheduler semantics.** Exact old source provenance is required for a real historical semantic comparison.

Current history anchors, inspect `git show <sha>`:
- `5f65626b4c`: process HiCache write-through events while Scheduler idle.
- `55ff0b2f0d`: drain deferred storage writes without re-entry.
- `2d5587ef36`: stop L3 gap writes after ancestor backup failure.
- `29d0e1a4e2`, `452d583f17`, `7d4186945d`, `8d03974630`, `f1477f3615`, `87ff0f046b`: retry/frontier wake, per-anchor durability version, current-suffix capacity gate, prefetch-budget wait wake, positive-hit preservation. Review diffs; do not infer exact impact from title.
- `7ea2670bd2`: Extent L3 reclaim under full-file pressure and live-ref relocation.
- `13d1b3263d`: Full Host duplicate reclaim under write-through.
- `c58cf9d5ce`: ACK drain + bounded backup recovery.
- `dbf2a6a244`: Host staging allocation/reclaim event correlation (mainly observability).

These current history commits do not prove the Qwen deploy lacked them; historical line-by-line semantic comparison is **NOT REPRODUCIBLE** until source SHA/tree is obtained.

## 4. Source bundle provenance

All function blocks below are complete definitions copied from current source at review HEAD `06f89994845f0e41c779950924064c16ebfbd956`. Runtime module hash identity matches §1. Each heading gives owner, file path, and one-based line span. This is a selected hot-path code bundle, not every transitive helper; callers/types/constants remain at their cited paths.

## 4. Complete hot-path source: `python/sglang/srt/managers/scheduler.py`

Source version: `06f89994845f0e41c779950924064c16ebfbd956`.


### `Scheduler._prefetch_kvcache` — `python/sglang/srt/managers/scheduler.py:3195-3242` (48 lines)

```python
    def _prefetch_kvcache(
        self,
        req: Req,
        *,
        origin: HiCachePrefetchOrigin,
        demand_restore: bool = False,
        prepared_match: Optional[_ReadyHorizonPreparedMatch] = None,
    ) -> PrefetchIssueResult:
        attempt_id = self._claim_prefetch(req, origin)
        if attempt_id is None:
            active_origin = getattr(
                req, "hicache_prefetch_active_origin", None
            ) or origin
            state = self._prefetch_state_name(
                getattr(req, "hicache_restore_state", None)
            )
            return PrefetchIssueResult(
                HiCachePrefetchIssueStatus.SKIPPED_ACTIVE,
                getattr(req, "hicache_prefetch_active_attempt_id", None),
                active_origin,
                "active_attempt",
                state,
                state,
            )
        try:
            impl_kwargs = {
                "origin": origin,
                "demand_restore": demand_restore,
            }
            if prepared_match is not None:
                impl_kwargs["prepared_match"] = prepared_match
            result = self._prefetch_kvcache_impl(req, **impl_kwargs)
        except Exception:
            self._release_prefetch_claim(req, attempt_id, "exception")
            raise
        result_status = (
            result.status
            if isinstance(result, PrefetchIssueResult)
            else result
        )
        if result_status is HiCachePrefetchIssueStatus.ISSUED:
            return result
        self._release_prefetch_claim(
            req,
            attempt_id,
            result.reason if isinstance(result, PrefetchIssueResult) else "declined",
        )
        return result
```


### `Scheduler._prefetch_kvcache_impl` — `python/sglang/srt/managers/scheduler.py:3244-3530` (287 lines)

```python
    def _prefetch_kvcache_impl(
        self,
        req: Req,
        *,
        origin: HiCachePrefetchOrigin,
        demand_restore: bool = False,
        prepared_match: Optional[_ReadyHorizonPreparedMatch] = None,
    ) -> PrefetchIssueResult:
        state_before_value = getattr(req, "hicache_restore_state", None)
        state_before = (
            state_before_value.name if state_before_value is not None else "null"
        )

        def result(status, reason):
            state_after_value = getattr(req, "hicache_restore_state", None)
            return PrefetchIssueResult(
                status=status,
                attempt_id=getattr(
                    req, "hicache_prefetch_active_attempt_id", None
                ),
                origin=origin,
                reason=reason,
                state_before=state_before,
                state_after=(
                    state_after_value.name
                    if state_after_value is not None
                    else "null"
                ),
            )

        try:
            _t38c_log({"evt": "pc_prefetch_enter", "phase": "entry",
                       "rid": req.rid,
                       "attempt_id": req.hicache_prefetch_active_attempt_id,
                       "origin": origin.name,
                       "l3_enabled": bool(self.enable_hicache_storage)})
        except Exception:
            pass
        if self.enable_hicache_storage:
            if origin is HiCachePrefetchOrigin.READY_HORIZON:
                pass_seq = getattr(self, "_rh_pass_seq", 0)
                prepared_valid = (
                    prepared_match is not None
                    and self._rh_prepared_match_valid(
                        req, prepared_match, pass_seq
                    )
                )
                if not prepared_valid:
                    self._emit_rh_match_prepare(
                        req,
                        pass_seq=pass_seq,
                        result="invalidated",
                        reason=(
                            "ticket_missing"
                            if prepared_match is None
                            else "ticket_stale"
                        ),
                        prepared=prepared_match,
                        fallback_rematch=True,
                        match_count_for_pass=1,
                    )
                    mamba_before = self._rh_mamba_snapshot(req)
                    match_started_ns = time.monotonic_ns()
                    try:
                        req.init_next_round_input(
                            self.tree_cache, cow_mamba=False
                        )
                    except Exception:
                        match_duration_us, mamba_delta = (
                            self._rh_match_observation(
                                req, mamba_before, match_started_ns
                            )
                        )
                        self._emit_rh_match_prepare(
                            req,
                            pass_seq=pass_seq,
                            result="failed",
                            reason="fallback_rematch_failed",
                            match_duration_us=match_duration_us,
                            mamba_delta=mamba_delta,
                            fallback_rematch=True,
                            match_count_for_pass=2,
                        )
                        return result(
                            HiCachePrefetchIssueStatus.FAILED_BEFORE_ISSUE,
                            "match_prepare_failed",
                        )
                    match_duration_us, mamba_delta = self._rh_match_observation(
                        req, mamba_before, match_started_ns
                    )
                    if not self._rh_current_match_anchors_valid(req):
                        self._emit_rh_match_prepare(
                            req,
                            pass_seq=pass_seq,
                            result="failed",
                            reason="fallback_anchor_unknown",
                            match_duration_us=match_duration_us,
                            mamba_delta=mamba_delta,
                            fallback_rematch=True,
                            match_count_for_pass=2,
                        )
                        return result(
                            HiCachePrefetchIssueStatus.FAILED_BEFORE_ISSUE,
                            "match_prepare_failed",
                        )
                    self._emit_rh_match_prepare(
                        req,
                        pass_seq=pass_seq,
                        result="prepared",
                        reason="fallback_rematch",
                        match_duration_us=match_duration_us,
                        mamba_delta=mamba_delta,
                        fallback_rematch=True,
                        match_count_for_pass=2,
                    )
            else:
                req.init_next_round_input(self.tree_cache, cow_mamba=False)
            tree_cache = self.tree_cache
            buffer_mode = self.server_args.hicache_host_memory_mode == "buffer_only"
            last_host_node = req.last_host_node
            # Buffer mode host-backups nothing, so match_prefix anchors at
            # root; re-anchor on the deepest device node. The anchor is only
            # read for hash/extra-key context here (never locked), so a device
            # node serves. Cache mode keeps the is_backuped gate below: its
            # write-through prefix is contiguous from root, so an unbacked
            # anchor means a guaranteed storage miss.
            if (
                buffer_mode
                and tree_cache.is_root(last_host_node)
                and not tree_cache.is_root(req.last_node)
            ):
                last_host_node = req.last_node

            try:
                _t38c_matched_len = len(req.prefix_indices) + req.host_hit_length
                _t38c_match_end = req._compute_max_prefix_len(
                    len(req.full_untruncated_fill_ids)
                )
                _t38c_anchor_hash = tree_cache.get_last_hash_value(last_host_node)
                _t38c_log({"evt": "pc_prefetch_enter", "phase": "gate",
                           "rid": req.rid,
                           "matched_len": _t38c_matched_len,
                           "match_end": _t38c_match_end,
                           "suffix_len": max(0, _t38c_match_end - _t38c_matched_len),
                           "anchor": {
                               "is_root": bool(tree_cache.is_root(last_host_node)),
                               "is_backuped": bool(tree_cache.is_backuped(last_host_node)),
                               "last_hash": _t38c_anchor_hash or "",
                           },
                           "buffer_mode": buffer_mode,
                           "gate_pass": bool(
                               tree_cache.prefetch_gate_ok(
                                   last_host_node, buffer_mode
                               )
                           )})
            except Exception:
                pass

            if tree_cache.prefetch_gate_ok(last_host_node, buffer_mode):
                matched_len = len(req.prefix_indices) + req.host_hit_length
                match_end = req._compute_max_prefix_len(
                    len(req.full_untruncated_fill_ids)
                )
                new_input_tokens = req.full_untruncated_fill_ids[matched_len:match_end]
                prefix_keys = (
                    tree_cache.get_prefix_hash_values(last_host_node)
                    if tree_cache.hicache_storage_pass_prefix_keys
                    else None
                )
                # Publish the producer-owned lifecycle_key before the
                # cache-side forfeit/finalize producers can read it back, so
                # every cache HOST_ALLOC event carries the scheduler's
                # authoritative key even on the very first issue.
                self._record_host_alloc_lineage(req)
                prefetch_kwargs = {
                    "matched_prefix_tokens": req.full_untruncated_fill_ids[:matched_len],
                    "demand_restore": demand_restore,
                    "host_alloc_attempt_id": getattr(
                        req, "hicache_host_alloc_attempt_id", None
                    ),
                    "prefetch_attempt_id": getattr(
                        req, "hicache_prefetch_active_attempt_id", None
                    ),
                }
                if getattr(req, "hicache_telemetry_enabled", False):
                    prefetch_kwargs["telemetry_enabled"] = True
                    prefetch_kwargs["session_generation"] = getattr(
                        req, "session_generation", None
                    )
                outcome = tree_cache.prefetch_from_storage(
                    req.rid,
                    last_host_node,
                    new_input_tokens,
                    tree_cache.get_last_hash_value(last_host_node),
                    prefix_keys,
                    **prefetch_kwargs,
                )
                # P2-1 M1b: feed the issue outcome into the restore state
                # machine (T1 issued / T2-T4 declines). declined_too_short
                # only enters WAIT[REVALIDATE] when the prompt can ever
                # qualify for a storage prefetch -- a can-never-qualify
                # decline is terminal (plain recompute), and re-issuing it
                # per pass is the capacity loop.
                if outcome == "issued":
                    self._apply_restore_event(req, RestoreEvent.PREFETCH_ISSUED)
                    return result(HiCachePrefetchIssueStatus.ISSUED, "issued")
                elif outcome == "declined_rate_limited":
                    self._apply_restore_event(req, RestoreEvent.DENIED_RATE)
                elif outcome == "forfeited_alloc_failed":
                    self._apply_restore_event(req, RestoreEvent.DENIED_ALLOC)
                    self._capture_host_alloc_wait(req)
                elif outcome == "revoked_alloc_failed":
                    self._apply_restore_event(req, RestoreEvent.DENIED_ALLOC)
                elif outcome == "declined_too_short":
                    # WAIT[REVALIDATE] is the device-match-decay bet, whose
                    # only re-issue source is the paced retry (step 2 below,
                    # gated on the poll interval). With the poll disabled
                    # (M2 default 0) the wait has no wake path and idles
                    # out the full T13 clock (e13 K=1 t5 60s): the first
                    # decline is then terminal, and the request recomputes
                    # immediately (no restore intent is armed).
                    short_tail = short_tail_recompute_allowed(
                        device_prefix_tokens=len(req.prefix_indices),
                        host_hit_tokens=req.host_hit_length,
                        suffix_tokens=max(0, match_end - matched_len),
                        page_size=self.page_size,
                        prefetch_threshold=tree_cache.prefetch_threshold,
                    )
                    if short_tail:
                        # The L1/L2 prefix is already resident; no storage
                        # event can make the current match longer. Consume
                        # the marker set by prefetch_from_storage so the
                        # paced retry cannot re-enter REVALIDATE, then use
                        # the state machine's immediate tail-admit path.
                        tree_cache.pop_storage_prefetch_miss(req.rid)
                        decision = self._apply_restore_event(
                            req,
                            RestoreEvent.DENIED_SHORT,
                            short_tail_recompute=True,
                        )
                        if decision is RestoreDecision.ADMIT_RECOMPUTE:
                            self._log_restore_recompute(req, "too_short_resident_tail")
                    elif self._restore_potential_for(req) and too_short_wait_armed(
                        get_memory().hicache_storage_prefetch_retry_poll_interval
                    ):
                        self._apply_restore_event(req, RestoreEvent.DENIED_SHORT)
            else:
                # Gate skip: the anchor is not a storage anchor yet. Cache
                # mode registers a frontier wait (M2 T5) and marks
                # WAIT[FRONTIER]; buffer mode reads by hash, never by anchor
                # backup, so a skip there is final and the request recomputes.
                # A prompt too short to ever qualify for a storage prefetch
                # skips the wait too: no restore intent, and the frontier
                # can never turn it into a restore (T13 would only delay the
                # recompute).
                if not buffer_mode and self.tree_cache.prompt_can_qualify_for_prefetch(
                    len(req.full_untruncated_fill_ids), req.host_hit_length
                ):
                    # phase2-peranchor no-material fast-forward: the anchor is
                    # not gate-ok (not root / not L3-durable / not backuped).
                    # If it has NO recoverable material at all AND nothing in
                    # flight can ever make it durable (no pending write ack, no
                    # deferred-ACK descendant for the P3 reconcile, no in-flight
                    # restore), the frontier wait is zero-expectation and would
                    # only idle out the full 60s T13 (the 9d8b5428 shape).
                    # Recompute forward immediately. This is distinct from
                    # prompt_can_qualify_for_prefetch (suffix-geometry): a
                    # candidate can qualify yet still have no material to wait
                    # on. Any in-flight producer / deferred descendant keeps the
                    # normal P3 reconcile + frontier wait path.
                    if self._no_material_fast_forward_for(req, last_host_node):
                        self._log_restore_recompute(req, "no_material")
                        return result(
                            HiCachePrefetchIssueStatus.SKIPPED_STATE,
                            "no_material",
                        )
                    self._apply_restore_event(req, RestoreEvent.GATE_SKIP_FRONTIER)
                    tree_cache.register_frontier_waiter(req.rid, last_host_node)
                    logger.info(
                        "[P2A] ts_ms=%d evt=frontier_wait rid=%s node=%s",
                        int(time.time() * 1000),
                        req.rid,
                        last_host_node,
                    )
                return result(HiCachePrefetchIssueStatus.HELD, "frontier")
            return result(HiCachePrefetchIssueStatus.HELD, outcome)
        return result(HiCachePrefetchIssueStatus.SKIPPED_STATE, "storage_disabled")
```


### `Scheduler._reconcile_restore_states` — `python/sglang/srt/managers/scheduler.py:4105-4322` (218 lines)

```python
    def _reconcile_restore_states(self):
        """Per-pass restore-state reconciliation (P2-1 M1b/M2; evolved from
        _retry_missed_storage_prefetches). Feeds terminal prefetch outcomes
        into the request state machine (T8 finalize / T9 miss revoke / T10
        terminated revoke), consumes M2 frontier wakes (T12), re-issues
        prefetches for WAIT requests whose capacity predicate now passes
        (T11), and degrades timed-out waits to recompute (T13)."""
        if not self.waiting_queue:
            arbiter = getattr(self, "_host_alloc_wake_arbiter", None)
            for rid in arbiter.ordered_rids() if arbiter is not None else ():
                self._remove_host_alloc_waiter(
                    rid, terminal_state="ABANDONED", reason="empty_waiting_queue"
                )
            return

        # 1) Terminal outcomes recorded by the drain this pass (same thread).
        for req in self.waiting_queue:
            self._feed_restore_terminal(req)

        # 2) Legacy paced retry (REVALIDATE fallback when interval > 0).
        interval = get_memory().hicache_storage_prefetch_retry_poll_interval
        if interval > 0:
            max_attempts = get_memory().hicache_storage_prefetch_retry_max_attempts
            for req in self.waiting_queue:
                if self.tree_cache.pop_storage_prefetch_miss(req.rid):
                    req.storage_prefetch_retry_pending = True
                    req.storage_prefetch_retry_wait_polls = 0
                if (
                    not req.storage_prefetch_retry_pending
                    or req.storage_prefetch_retry_attempts >= max_attempts
                ):
                    continue
                req.storage_prefetch_retry_wait_polls += 1
                if req.storage_prefetch_retry_wait_polls <= interval:
                    continue
                req.storage_prefetch_retry_pending = False
                req.storage_prefetch_retry_attempts += 1
                logger.debug(
                    "HiCache storage prefetch retry req=%s attempt=%d",
                    req.rid,
                    req.storage_prefetch_retry_attempts,
                )
                self._prefetch_kvcache(req, origin=HiCachePrefetchOrigin.DEMAND_RETRY)

        # 3) M2: frontier-ACK wakes (T12). The ack drain moved the waiter
        # into the ready set earlier in this same event pass.
        for req in self.waiting_queue:
            if not self.tree_cache.pop_frontier_ready(req.rid):
                continue
            if req.hicache_restore_state is not RestoreState.WAIT_CAPACITY:
                self.tree_cache.discard_frontier_waiter(req.rid)
                continue  # state changed since the wake (e.g. timed out)
            was_backup_pending = (
                req.hicache_restore_wait_reason is RestoreWaitReason.BACKUP_PENDING
            )
            if was_backup_pending and not self._restore_backup_wake_ready(req):
                # A T12 wake for a still-parked backup wait: the chain's
                # durable frontier has not crossed the request's end (or
                # the demand ticket pool is full). Consume the wake and
                # hold the re-issue -- the per-pass T11 predicate re-checks
                # the frontier, so the request is not lost, and the parked
                # span stays armed.
                continue
            self.tree_cache.discard_frontier_waiter(req.rid)
            decision = self._apply_restore_event(req, RestoreEvent.FRONTIER_READY)
            if decision is RestoreDecision.RETRY_PREFETCH:
                logger.info(
                    "[P2A] ts_ms=%d evt=restore_retry rid=%s cause=frontier",
                    int(time.time() * 1000),
                    req.rid,
                )
                self._prefetch_kvcache(
                    req,
                    origin=HiCachePrefetchOrigin.DEMAND_RETRY,
                    demand_restore=self.enable_ready_horizon or was_backup_pending,
                )
                if req.hicache_restore_state is RestoreState.NONE:
                    # The wake re-issue was declined too-short: terminal
                    # (T4 on the re-issue leg), released to recompute now
                    # instead of idling out the T13 clock.
                    self._log_restore_recompute(req, "too_short")

        # 4) M1: WAIT timeout (T13) and per-pass capacity wakes (T11).
        timeout_s = self.server_args.hicache_restore_wait_timeout_s
        now = time.perf_counter()
        if not hasattr(self, "_host_alloc_attempt_seq"):
            self._host_alloc_attempt_seq = 0
        host_alloc_grant = self._select_host_alloc_waiter()
        for req in self.waiting_queue:
            if req.hicache_restore_state is not RestoreState.WAIT_CAPACITY:
                continue
            if timeout_s > 0 and now - req.hicache_restore_state_ts > timeout_s:
                self.tree_cache.discard_frontier_waiter(req.rid)
                decision = self._apply_restore_event(req, RestoreEvent.TIMEOUT)
                if decision is RestoreDecision.ADMIT_RECOMPUTE:
                    self._log_restore_recompute(req, "timeout")
                continue
            if not capacity_wake_applies(req.hicache_restore_wait_reason):
                # REVALIDATE is not testable by the capacity predicate:
                # re-issuing would be declined identically every pass. It
                # leaves only via the paced retry or the T13 timeout.
                continue
            if req.hicache_restore_wait_reason is RestoreWaitReason.HOST_ALLOC:
                worker, rank = self._host_alloc_telemetry_identity()
                cursor = getattr(req, "hicache_host_alloc_wait_cursor", None)
                current = self._host_alloc_snapshot_for_req(req)
                current_generations = (
                    dict(current.generation_by_pool) if current is not None else {}
                )
                captured_generations = (
                    dict(cursor.snapshot.generation_by_pool) if cursor else {}
                )
                vector = (
                    current.generation_vector() if current is not None else None
                )
                if req.rid != host_alloc_grant:
                    decision_name = self._host_alloc_skip_decision(req)
                    _log_host_alloc_telemetry(
                        "restore_host_alloc_wake_decision",
                        worker=worker,
                        rank=rank,
                        rid=req.rid,
                        attempt_id=getattr(
                            req, "hicache_host_alloc_attempt_id", None
                        ),
                        cache_instance_id=(
                            current.cache_instance_id if current is not None else None
                        ),
                        trace_context=self._host_alloc_trace_context(req),
                        decision=decision_name,
                        captured_generations=captured_generations,
                        current_generations=current_generations,
                        blocked_domains=sorted(
                            map(str, cursor.blocked_domains)
                        )
                        if cursor
                        else [],
                        required_aux_units=(
                            dict(cursor.required_aux_units) if cursor else {}
                        ),
                        requested_primary_tokens=(
                            int(cursor.requested_primary_tokens) if cursor else 0
                        ),
                        fifo_sequence=cursor.fifo_sequence if cursor else None,
                        generation_vector_id=self._host_alloc_generation_vector_id(
                            vector
                        ),
                        global_grant_used=decision_name == "hold_global_grant_used",
                        budget_available=decision_name != "hold_budget",
                        free_units=(
                            dict(current.free_units_by_pool) if current is not None else {}
                        ),
                        evictable_units=(
                            dict(current.evictable_units_by_pool)
                            if current is not None
                            else {}
                        ),
                        retry_grant=False,
                        retry_skip=decision_name != "grant",
                        retry_outcome=decision_name,
                        lifecycle_key=self._host_alloc_lifecycle_key(req),
                        wait_id=getattr(req, "hicache_host_alloc_wait_id", None),
                        wake_event_id=None,
                        attempt_number=0,
                        attempt_origin="HOST_ALLOC_WAKE_HOLD",
                    )
                    continue
                self._emit_host_alloc_wake_grant(req)
            if not self._restore_wait_capacity_fits(req):
                continue
            # Captured before _apply_restore_event clears the reason: a
            # BACKUP_PENDING wake re-issues with its DEMAND_RESTORE ticket
            # (past the speculative PREFETCH_BUDGET only).
            was_backup_pending = (
                req.hicache_restore_wait_reason is RestoreWaitReason.BACKUP_PENDING
            )
            if req.hicache_restore_wait_reason in (
                RestoreWaitReason.FRONTIER,
                RestoreWaitReason.BACKUP_PENDING,
            ):
                self.tree_cache.discard_frontier_waiter(req.rid)
            decision = self._apply_restore_event(
                req, RestoreEvent.CAPACITY_FITS, capacity_fits=True
            )
            if decision is RestoreDecision.RETRY_PREFETCH:
                self._host_alloc_attempt_seq += 1
                req.hicache_host_alloc_attempt_id = (
                    f"{req.rid}:{self._host_alloc_attempt_seq}"
                )
                req.hicache_host_alloc_attempt_number = (
                    getattr(req, "hicache_host_alloc_attempt_number", 0) + 1
                )
                req.hicache_host_alloc_attempt_snapshot = (
                    self._host_alloc_snapshot_for_req(req)
                )
                # Publish the attempt identity so the cache's retry_result and
                # the terminal READY join to the granted wake event.
                self._record_host_alloc_lineage(
                    req,
                    attempt_number=req.hicache_host_alloc_attempt_number,
                    origin="HOST_ALLOC_WAKE",
                )
                logger.info(
                    "[P2A] ts_ms=%d evt=restore_retry rid=%s cause=capacity attempt_id=%s",
                    int(time.time() * 1000),
                    req.rid,
                    req.hicache_host_alloc_attempt_id,
                )
                self._prefetch_kvcache(
                    req,
                    origin=HiCachePrefetchOrigin.DEMAND_RETRY,
                    demand_restore=self.enable_ready_horizon or was_backup_pending,
                )
                if req.hicache_restore_state is RestoreState.NONE:
                    # Same terminal rule as the T12 wake leg: a capacity
                    # wake whose re-issued prefetch is declined too-short
                    # releases the request to recompute immediately.
                    self._log_restore_recompute(req, "too_short")
```


### `Scheduler._feed_restore_terminal` — `python/sglang/srt/managers/scheduler.py:4324-4626` (303 lines)

```python
    def _feed_restore_terminal(self, req) -> None:
        """Consume a terminal prefetch outcome (finalize T8 / revoke T9/T10)
        recorded by the drain into the request's restore state machine."""
        terminal = self.tree_cache.pop_storage_prefetch_terminal(req.rid)
        if terminal is None:
            return
        if isinstance(terminal, tuple):
            terminal_attempt_id, outcome = terminal
        else:
            # Legacy test doubles may still provide an uncorrelated outcome.
            # Real cache terminals always carry the attempt ID.
            terminal_attempt_id, outcome = None, terminal
        active_attempt_id = getattr(req, "hicache_prefetch_active_attempt_id", None)
        if terminal_attempt_id is not None and terminal_attempt_id != active_attempt_id:
            logger.warning(
                "[P3] evt=prefetch_terminal_stale rid=%s terminal_attempt_id=%s active_attempt_id=%s",
                req.rid,
                terminal_attempt_id,
                active_attempt_id,
            )
            if getattr(req, "hicache_telemetry_enabled", False):
                req.hicache_invalid_reason = "attempt_mismatch"
                for field in (
                    "hicache_prefetch_issue_mono_ns",
                    "hicache_storage_query_start_mono_ns",
                    "hicache_storage_query_end_mono_ns",
                    "hicache_completed_kv_tokens",
                    "hicache_required_aux_pools",
                    "hicache_completed_aux_units",
                    "hicache_hybrid_restore_complete",
                    "hicache_durable_reusable_prefix_tokens",
                    "hicache_ready_mono_ns",
                ):
                    setattr(req, field, None)
            return
        completion = None
        discarded_finalization = False
        if outcome == "finalized":
            completion = getattr(
                self.tree_cache,
                "pop_storage_prefetch_completion",
                lambda _rid: None,
            )(req.rid) or {}
            discarded_finalization = completion.get("finalize_result") in (
                "discarded",
                "rejected",
            )
            if discarded_finalization:
                # The finalizer rejected/discarded the all-or-nothing hybrid
                # material. Keep the terminal handoff, but release the
                # request to recompute instead of treating it as READY.
                event, genuine_miss = RestoreEvent.DENIED_SHORT, False
            else:
                event, genuine_miss = RestoreEvent.FINALIZED, False
        elif outcome == "revoked_terminated":
            event, genuine_miss = RestoreEvent.REVOKED_TERMINATED, False
        elif outcome == "revoked_backup_pending":
            event, genuine_miss = RestoreEvent.BACKUP_PENDING, False
        elif outcome == "revoked_alloc_failed":
            event, genuine_miss = RestoreEvent.DENIED_ALLOC, False
        else:  # "revoked_miss"
            event, genuine_miss = RestoreEvent.REVOKED_MISS, True
        if event is RestoreEvent.REVOKED_MISS and genuine_miss:
            # P1 sticky-miss evidence (phase2-peranchor): record the ANCHOR's
            # per-anchor storage_version at which this request's prefix was
            # proven L3-missing, plus the anchor node and the identity
            # (session generation). The admission re-arm (T6) refuses to
            # re-enter WAIT while that SAME anchor's version is unchanged and
            # the generation matches -- the same-probe restore churn gate.
            # Only THIS anchor's substantive durability change (or a
            # generation/prefix/anchor change) overrides the miss: an
            # unrelated chain's write ack bumps only the global diagnostic
            # counter and never re-arms. `anchor` is the deepest durable
            # ancestor the miss probe covered (the request's last_host_node /
            # the restore target anchor it was revoked on); `anchor_version`
            # is defensive when the anchor is gone (self-heal to re-match).
            anchor = getattr(req, "last_host_node", None)
            req.hicache_restore_miss_epoch = self._anchor_version_or_zero(anchor)
            req.hicache_restore_miss_anchor = anchor
            req.hicache_restore_miss_generation = getattr(
                req, "session_generation", None
            )
        failure = (
            self.tree_cache.pop_host_alloc_failure(req.rid)
            if event is RestoreEvent.DENIED_ALLOC
            else None
        )
        restore_state_before = self._prefetch_state_name(
            getattr(req, "hicache_restore_state", None)
        )
        attempt_id = getattr(req, "hicache_prefetch_active_attempt_id", None)
        attempt_origin = getattr(req, "hicache_prefetch_active_origin", None)
        self._apply_restore_event(
            req,
            event,
            genuine_miss=genuine_miss,
            short_tail_recompute=discarded_finalization,
        )
        if event is RestoreEvent.DENIED_ALLOC:
            self._capture_host_alloc_wait(req, failure)
        if terminal_attempt_id is not None:
            self._release_prefetch_claim(
                req, terminal_attempt_id, outcome
            )
        if event is RestoreEvent.FINALIZED:
            last_origin = getattr(req, "hicache_prefetch_last_origin", None)
            staged_tokens = getattr(
                self.tree_cache, "peek_prefetch_loaded_tokens", lambda _rid: None
            )(req.rid)
            completion = completion or {}
            # READY must carry the same producer-owned identity and lineage as
            # the HOST_ALLOC family so the live-chain oracle can join the
            # terminal READY back to the park/wake without trusting the
            # harness.  All values are produced here, never caller-supplied.
            ready_context = producer_context(component="ready")
            ready_event_id = next_event_id("ready")
            completion_generation = completion.get("session_generation")
            generation_valid = completion_generation == getattr(
                req, "session_generation", None
            )
            if (
                req.hicache_telemetry_enabled
                and not discarded_finalization
                and (
                    terminal_attempt_id is None
                    or terminal_attempt_id == attempt_id
                )
            ):
                if generation_valid:
                    req.hicache_telemetry_session_generation = completion_generation
                    req.hicache_prefetch_issue_mono_ns = completion.get(
                        "prefetch_issue_mono_ns"
                    )
                    req.hicache_storage_query_start_mono_ns = completion.get(
                        "storage_query_start_mono_ns"
                    )
                    req.hicache_storage_query_end_mono_ns = completion.get(
                        "storage_query_end_mono_ns"
                    )
                    req.hicache_completed_kv_tokens = completion.get(
                        "completed_kv_tokens"
                    )
                    req.hicache_required_aux_pools = completion.get(
                        "required_aux_pools", []
                    )
                    req.hicache_completed_aux_units = completion.get(
                        "completed_aux_units"
                    )
                    req.hicache_hybrid_restore_complete = completion.get(
                        "hybrid_restore_complete"
                    )
                    req.hicache_matched_prefix_tokens = completion.get(
                        "matched_prefix_tokens"
                    )
                    req.hicache_matched_prefix_l3_proof = completion.get(
                        "matched_prefix_l3_proof"
                    )
                    req.hicache_durable_reusable_prefix_tokens = completion.get(
                        "durable_reusable_prefix_tokens"
                    )
                    req.hicache_ready_mono_ns = time.monotonic_ns()
                else:
                    req.hicache_invalid_reason = "generation_mismatch"
                    req.hicache_telemetry_session_generation = completion_generation
                    for field in (
                        "hicache_prefetch_issue_mono_ns",
                        "hicache_storage_query_start_mono_ns",
                        "hicache_storage_query_end_mono_ns",
                        "hicache_completed_kv_tokens",
                        "hicache_required_aux_pools",
                        "hicache_completed_aux_units",
                        "hicache_hybrid_restore_complete",
                        "hicache_matched_prefix_tokens",
                        "hicache_matched_prefix_l3_proof",
                        "hicache_durable_reusable_prefix_tokens",
                        "hicache_ready_mono_ns",
                    ):
                        setattr(req, field, None)
            ready_snapshot = self._host_alloc_snapshot_for_req(req)
            # Read the scheduler-owned lineage back from the producer registry
            # so READY joins to the exact grant record (wake_event_id) and
            # lifecycle_key the HOST_ALLOC family published.
            ready_lineage = host_alloc_lineage(req.rid)
            ready_lifecycle_key = (
                ready_lineage.get("lifecycle_key")
                or self._host_alloc_lifecycle_key(req)
            )
            ready_wait_id = ready_lineage.get("wait_id") or getattr(
                req, "hicache_host_alloc_wait_id", None
            )
            ready_wake_event_id = ready_lineage.get("wake_event_id") or getattr(
                req, "hicache_host_alloc_wake_event_id", None
            )
            ready_predecessor_wait_id = ready_lineage.get("predecessor_wait_id")
            ready_predecessor_terminal_event_id = ready_lineage.get(
                "predecessor_terminal_event_id"
            )
            ready_predecessor_terminal_state = ready_lineage.get(
                "predecessor_terminal_state"
            )
            logger.info(
                "[P3] ts_ns=%d evt=ready_host schema=rh_ready_host.v1 rid=%s "
                "attempt_id=%s issue_origin=%s completed_kv_tokens=%s "
                "required_aux_pools=%s completed_aux_units=%s "
                "restore_state_before=%s restore_state_after=%s "
                "finalize_result=%s ready_monotonic_ns=%d "
                "event_id=%s run_id=%s process_id=%s profile_id=%s "
                "source_build=%s deployment_manifest_digest=%s "
                "lifecycle_key=%s wait_id=%s wake_event_id=%s "
                "predecessor_wait_id=%s predecessor_terminal_event_id=%s "
                "predecessor_terminal_state=%s "
                "cache_instance_id=%s generation_vector_id=%s",
                time.monotonic_ns(),
                req.rid,
                attempt_id
                or getattr(req, "hicache_prefetch_last_attempt_id", None),
                (attempt_origin or last_origin).name
                if (attempt_origin or last_origin) is not None
                else "null",
                completion.get("completed_kv_tokens", staged_tokens),
                completion.get("required_aux_pools"),
                completion.get("completed_aux_units"),
                restore_state_before,
                req.hicache_restore_state.name
                if req.hicache_restore_state is not None
                else "null",
                completion.get("finalize_result", "null"),
                time.monotonic_ns(),
                ready_event_id,
                ready_context["run_id"],
                ready_context["process_id"],
                ready_context["profile_id"],
                ready_context["source_build"],
                ready_context["deployment_manifest_digest"],
                ready_lifecycle_key,
                ready_wait_id,
                ready_wake_event_id,
                ready_predecessor_wait_id,
                ready_predecessor_terminal_event_id,
                ready_predecessor_terminal_state,
                ready_snapshot.cache_instance_id
                if ready_snapshot is not None
                else None,
                self._host_alloc_generation_vector_id(
                    ready_snapshot.generation_vector()
                    if ready_snapshot is not None
                    else None
                ),
            )
        if (
            event is RestoreEvent.REVOKED_MISS
            and genuine_miss
            and self.enable_ready_horizon
        ):
            # P3 M3 (user adjudication) + phase2-peranchor: a deterministic
            # miss means the full requested prefix is not in L3. The ready
            # horizon records the NO_L3 negative-cache park keyed on the
            # ANCHOR's per-anchor storage_version (not the global l3_publish
            # diagnostic counter) so this NONE request is not re-probed next
            # pass -- the miss is not transient and its revoke just released
            # the budget (the e7 spin arm). Only THAT anchor's substantive
            # durability change, an identity change (prefix/generation/anchor),
            # or the fuse expiry clears it; an unrelated chain's write ack
            # does not.
            anchor = getattr(req, "last_host_node", None)
            self._ready_horizon_negatives[req.rid] = NegativeCacheEntry(
                reason=DeclineReason.NO_L3,
                epoch_cursor=self._anchor_version_or_zero(anchor),
                fuse_expiry=time.perf_counter()
                + self.ready_horizon.safety_fuse_s,
                prefix_len=(
                    len(req.full_untruncated_fill_ids)
                    if req.full_untruncated_fill_ids is not None
                    else 0
                ),
                generation=getattr(req, "session_generation", None),
                anchor=anchor,
            )
        if event is RestoreEvent.BACKUP_PENDING:
            # The lookup found the chain mid-backup: park on the M2 frontier
            # wait, keyed by the anchor (the parked span is stored in the
            # cache at the revoke). Registering also requests the chain's
            # persistence (write_backup_storage), so the wait is
            # self-arming; the per-pass wake predicate (_restore_backup_wake_ready
            # -- durable frontier crossed the request end plus a free
            # DEMAND_RESTORE ticket) then wakes the request for one
            # re-lookup into the full chain instead of the per-pass
            # re-issue loop. Bounded by the T13 timeout.
            if (
                req.hicache_restore_state is RestoreState.WAIT_CAPACITY
                and req.last_host_node is not None
            ):
                self.tree_cache.register_frontier_waiter(
                    req.rid, req.last_host_node
                )
        if event is RestoreEvent.REVOKED_MISS:
            self._log_restore_recompute(req, "miss")
        elif req.hicache_restore_state is RestoreState.READY:
            logger.info(
                "[P2A] ts_ms=%d evt=restore_ready rid=%s",
                int(time.time() * 1000),
                req.rid,
            )
```


### `Scheduler._apply_restore_event` — `python/sglang/srt/managers/scheduler.py:4653-4727` (75 lines)

```python
    def _apply_restore_event(
        self,
        req,
        event,
        *,
        capacity_fits: bool = False,
        genuine_miss: bool = False,
        rearm_allowed: bool = True,
        short_tail_recompute: bool = False,
    ) -> RestoreDecision:
        """Feed a restore event into the request's state machine and apply
        the transition (Req fields only; the decision is returned for the
        caller to execute). Scheduler thread only -- the drain, the
        reconciliation and the admission loop all run on it, so there is no
        concurrent write."""
        prev_state = req.hicache_restore_state
        next_state, decision = next_restore(
            req.hicache_restore_state,
            event,
            capacity_fits=capacity_fits,
            genuine_miss=genuine_miss,
            rearm_allowed=rearm_allowed,
            short_tail_recompute=short_tail_recompute,
        )
        if next_state is req.hicache_restore_state and decision is RestoreDecision.NONE:
            return decision
        if (
            prev_state is RestoreState.WAIT_CAPACITY
            and req.hicache_restore_wait_reason is RestoreWaitReason.HOST_ALLOC
        ):
            if not (
                next_state is RestoreState.WAIT_CAPACITY
                and wait_reason_for(event, genuine_miss=genuine_miss)
                is RestoreWaitReason.HOST_ALLOC
            ):
                terminal_state = self._host_alloc_terminal_state_for(
                    event, next_state
                )
                self._remove_host_alloc_waiter(
                    req.rid,
                    terminal_state=terminal_state,
                    reason=f"restore_event:{event.name}",
                    req=req,
                )
                req.hicache_host_alloc_wait_cursor = None
        req.hicache_restore_state = next_state
        if next_state is RestoreState.WAIT_CAPACITY:
            req.hicache_restore_wait_reason = wait_reason_for(
                event, genuine_miss=genuine_miss
            )
        else:
            req.hicache_restore_wait_reason = None
        if next_state is not RestoreState.MISS_RECOMPUTE:
            # P1: leaving the sticky-miss state (a re-arm override, an
            # abort, a forward READY, or a re-issued restore) drops the
            # negative evidence -- the miss no longer binds the request.
            req.hicache_restore_miss_epoch = None
            req.hicache_restore_miss_generation = None
            req.hicache_restore_miss_anchor = None
        # The wait clock is armed at the first WAIT entry of the episode and
        # never re-armed by a re-decline: re-arming was what let the
        # capacity loop evade the T13 timeout (state_ts reset every pass).
        req.hicache_restore_state_ts = wait_clock_next(
            prev_state, next_state, req.hicache_restore_state_ts, time.perf_counter()
        )
        logger.info(
            "[P2A] ts_ms=%d evt=restore_state rid=%s state=%s reason=%s",
            int(time.time() * 1000),
            req.rid,
            next_state.name,
            req.hicache_restore_wait_reason.name
            if req.hicache_restore_wait_reason is not None
            else "none",
        )
        return decision
```


### `Scheduler._restore_wait_capacity_fits` — `python/sglang/srt/managers/scheduler.py:5764-5887` (124 lines)

```python
    def _restore_wait_capacity_fits(self, req) -> bool:
        """Per-pass WAIT wake predicate (design §2.3): device capacity for
        the incremental charge (same formula as the admission gates, minus
        the adder's running offsets -- strictly permissive, never stricter),
        the host prefetch budget, and for FRONTIER waiters the anchor
        fallback (persisted, or deleted and re-matchable). The admission
        gates stay authoritative: a too-permissive wake only costs a
        re-issued prefetch."""
        if req.hicache_restore_wait_reason is RestoreWaitReason.FRONTIER:
            anchor = req.last_host_node
            if anchor is None:
                return False
            # L3-readiness only: the host copy commits at D->H submission,
            # before the L3 write, and a wake there re-issues the prefetch
            # into an empty L3 (the M2 premature wake that kept
            # frontier_wake at zero). The predicate mirrors the ACK wake.
            return self.tree_cache.frontier_anchor_ready(anchor)
        if req.hicache_restore_wait_reason is RestoreWaitReason.BACKUP_PENDING:
            # The wait ends when the chain's durable frontier crosses the
            # request's end AND a DEMAND_RESTORE ticket is free: the wake
            # re-issues one prefetch that re-looks-up into the full chain.
            # The frontier advances only on ACK drains (re-read every
            # pass), so the wake is ACK-driven, not a poll; a failed
            # write that never crosses the frontier leaves the request to
            # the T13 timeout (bounded).
            return self._restore_backup_wake_ready(req)
        if req.hicache_restore_wait_reason is RestoreWaitReason.HOST_ALLOC:
            cc = self.tree_cache.cache_controller
            if cc is None or req.full_untruncated_fill_ids is None:
                return False
            if cc.prefetch_rate_limited():
                return False
            # Generation admission is handled by the FIFO arbiter.  Do not
            # require the complete span to be already free: the authoritative
            # retry must be allowed to run alloc -> evict_host -> alloc.
            return True
        cc = self.tree_cache.cache_controller
        if cc is not None and cc.prefetch_rate_limited():
            return False
        if req.hicache_restore_wait_reason is RestoreWaitReason.PREFETCH_BUDGET:
            # A budget wake only re-issues the L3->host prefetch, whose
            # capacity gate is the host prefetch limiter above. Device
            # admission remains authoritative after the restore reaches
            # READY; requiring its charge here strands this waiter while an
            # unrelated running request still occupies the device.
            return True
        # too_short churn (independent P, defense-in-depth): a DEVICE_QUOTA
        # waiter whose current restore suffix is already sub-threshold AND
        # can never grow back above it (the can-never-qualify prompt -- the
        # theoretical-max suffix is sub-threshold too) must not be woken by
        # the capacity predicate. Waking re-issues an inevitably
        # declined_too_short prefetch (granted=0) and re-parks on the next
        # pass's capacity check -- the tight wake->re-issue->declined->re-WAIT
        # loop. The request is released to recompute its tail directly
        # instead (the admission main fix already keeps it out of this WAIT
        # on the forward path; this predicate is the defense for any
        # DEVICE_QUOTA waiter that entered before the fix). REVALIDATE /
        # device-match-decay semantics are untouched: a prompt that CAN grow
        # its suffix above the threshold keeps its capacity wake.
        if req.hicache_restore_wait_reason is RestoreWaitReason.DEVICE_QUOTA:
            if req.full_untruncated_fill_ids is not None:
                if not (
                    self.tree_cache.prompt_can_qualify_for_prefetch(
                        len(req.full_untruncated_fill_ids), req.host_hit_length
                    )
                ):
                    return False
                # P4 gate (no-heuristic): the CURRENT actually-prefetchable
                # suffix must also clear the threshold. The can-never-qualify
                # gate above uses the theoretical-max suffix
                # (prompt_len - host_hit_length, after the device match has
                # fully decayed); a REVALIDATE-bet / never-case-residue
                # waiter passes it (max suffix >= threshold) yet its current
                # suffix (match_end - (prefix match + host match)) is still
                # sub-threshold. Capacity-waking such a waiter re-issues an
                # inevitably declined_too_short prefetch every pass (the
                # tight wake->re-issue->declined->re-WAIT loop); capacity
                # release does not change that result, so capacity is not a
                # wake source for it. Its only legal re-trigger is the
                # current suffix growing past the threshold (device match
                # decay, observed on the fresh-geometry re-entry after the
                # bounded T13 recompute) or the T13 fallback recompute
                # itself. REVALIDATE-bet restore potential is untouched
                # (has_restore_potential is not modified) -- only the
                # capacity wake is suppressed. population A (current suffix
                # already qualifies) is not held.
                if self._current_prefetch_suffix_lt_threshold(req):
                    return False
        # P2-1c promotion-budget item (design §3.4): a DEVICE_QUOTA waiter
        # whose next step is a FULL-KV promotion (host material ready) must
        # not wake while the device promotion budget cannot hold it --
        # waking re-issues prefetch -> finalize -> admission -> re-deny,
        # burning a full prefetch cycle per wake. host_hit_length == 0
        # waiters (T6 sources whose material is still staging) are not
        # budgeted: their next step is the unrestricted L3->H prefetch. The
        # predicate re-reads every pass, so a reservation release is visible
        # the same pass (drain runs before this reconciliation).
        if promotion_wait_blocked(
            req.hicache_restore_wait_reason,
            req.host_hit_length,
            promotion_budget_fits(
                device_locked_tokens(
                    self.tree_cache.token_to_kv_pool_allocator, self.tree_cache
                ),
                self.tree_cache.inflight_promotion_reserved,
                req.host_hit_length,
                self.tree_cache.token_to_kv_pool_allocator.size_full,
                self.server_args.hicache_promotion_margin_tokens,
            ),
        ):
            return False
        max_new = min(
            max(req.sampling_params.max_new_tokens - len(req.output_ids), 0),
            CLIP_MAX_NEW_TOKENS,
        )
        charge = device_charge(
            len(req.full_untruncated_fill_ids),
            len(req.prefix_indices),
            max_new,
            self.page_size,
        )
        return charge < available_and_evictable_tokens(
            self.req_to_token_pool, self.tree_cache
        )
```


### `Scheduler._restore_potential_for` — `python/sglang/srt/managers/scheduler.py:5911-5920` (10 lines)

```python
    def _restore_potential_for(self, req) -> bool:
        """Design §2.5-1 restore potential plus the can-never-qualify prompt
        gate; the shared entry condition for T4/T5/T6 (a quota or gate
        denial only becomes a WAIT when restore material exists)."""
        return self.tree_cache.has_restore_potential(
            req.rid,
            req.last_host_node,
            req.host_hit_length,
            len(req.full_untruncated_fill_ids),
        )
```


### `Scheduler.get_next_batch_to_run` — `python/sglang/srt/managers/scheduler.py:6488-6635` (148 lines)

```python
    def get_next_batch_to_run(
        self, running_batch: ScheduleBatch, last_batch: Optional[ScheduleBatch]
    ) -> NextBatchPlan:
        self.process_pending_chunked_abort()

        if self.enable_fpm:
            self._fpm_batch_t0 = time.monotonic()
        self._abort_on_waiting_timeout()
        self._abort_on_running_timeout(running_batch)
        if self.dllm_config is not None:
            self.dllm_manager.filter_finished_reqs()

        # Merge the prefill batch into the running batch
        chunked_req_to_exclude = set()

        if self.dllm_config is not None and self.dllm_manager.any_staging_reqs():
            chunked_req_to_exclude.update(self.dllm_manager.staging_queue)
            for req in self.dllm_manager.staging_queue:
                if self.dllm_config.first_done_first_out_mode:
                    if not req.dllm_incomplete_ids:
                        self.stash_chunked_request(req)
                        self.req_to_token_pool.free(req)
                    # Otherwise, keep req slot/KV for reuse.
                else:
                    self.stash_chunked_request(req)

        if self.chunked_req is not None:
            # Move the chunked request out of the batch so that we can merge
            # only finished requests to running_batch.
            chunked_req_to_exclude.add(self.chunked_req)

            # Stash (cache) the previous chunk only when it produced new KV
            # beyond what is already cached. A parked chunk (add_chunked_req
            # hybrid-SWA early-return) leaves extend_range.end ==
            # len(prefix_indices), so there is nothing new to cache and
            # stashing would be a no-op.
            if self.chunked_req.extend_range.end > len(self.chunked_req.prefix_indices):
                self.stash_chunked_request(self.chunked_req)

        # HiSparse has its own prefill-to-decode transition; skip last_batch merge.
        if self.enable_hisparse:
            ready_reqs = self.hisparse_coordinator.collect_ready_reqs()
            if len(ready_reqs) > 0:
                new_batch = self._build_hisparse_decode_batch(ready_reqs)
                if running_batch.is_empty():
                    running_batch = new_batch
                else:
                    running_batch.merge_batch(new_batch)
                running_batch.hisparse_coordinator = self.hisparse_coordinator
            # Reset batch_is_full so the scheduler can schedule more prefills.
            running_batch.batch_is_full = False

        if (
            not self.enable_hisparse
            and last_batch
            and last_batch.forward_mode.is_extend()
        ):
            if last_batch.chunked_req is not None:
                # In the context pipeline parallelism, after the last chunk, the current microbatch still track outdated chunked_req.
                # We need to discard it.
                chunked_req_to_exclude.add(last_batch.chunked_req)

            if self.dllm_config is not None and last_batch.reqs:
                chunked_req_to_exclude.update(last_batch.reqs)

            # Filter batch
            last_bs = last_batch.batch_size()
            last_batch.filter_batch(chunked_req_to_exclude=list(chunked_req_to_exclude))
            if last_batch.batch_size() < last_bs:
                running_batch.batch_is_full = False

            # Merge the new batch into the running batch.
            if not last_batch.is_empty():
                if running_batch.is_empty():
                    running_batch = last_batch
                else:
                    # Merge running_batch with prefill batch
                    running_batch.merge_batch(last_batch)

        # For prefill-only batch, filter out finished requests since they
        # won't go through the decode step. This keeps running_batch accurate
        # for load reporting (num_running_reqs via /v1/loads).
        # Runs outside the last_batch block so stale requests are cleaned
        # even when no new batches arrive (e.g. traffic stops).
        if running_batch.is_prefill_only:
            running_batch.filter_batch()
            if running_batch.is_empty():
                running_batch.batch_is_full = False

        if self.dllm_config is not None:
            new_batch = self.get_new_batch_dllm(running_batch)
        elif self._should_defer_prefill():
            new_batch = None
        else:
            prefill_plan = self.get_new_batch_prefill(running_batch)
            new_batch = prefill_plan.batch_to_run
            running_batch = prefill_plan.running_batch

        need_mlp_sync = self.require_mlp_sync
        if (
            need_mlp_sync
            and not self.spec_algorithm.is_none()
            and not get_spec().speculative_skip_dp_mlp_sync
        ):
            # NOTE: This branch makes sure prefill and decode batches will not be mixed when spec and dp-attn is enabled.
            # Before merging the new batch into running batch:
            # 1. All new batches are none -> need_mlp_sync remains true (sync is needed for decode batch).
            # 2. All new batches are some (prefill / idle) -> we do not need prepare mlp sync one more time.
            new_batch = self.dp_attn_adapter.maybe_prepare_mlp_sync_batch(new_batch)
            need_mlp_sync = new_batch is None

        if new_batch is not None:
            # Run prefill first if possible
            ret = new_batch
        else:
            # Run decode (skip for prefill-only batches)
            if not running_batch.is_empty() and not running_batch.is_prefill_only:
                running_batch = self.update_running_batch(running_batch)
                ret = running_batch if not running_batch.is_empty() else None
            else:
                ret = None

        # Handle DP attention and log stats
        ret = self.dp_attn_adapter.maybe_prepare_mlp_sync_batch(
            ret, need_sync=need_mlp_sync
        )
        # Decode->extend conversion keeps a heterogeneous dp step replayable.
        converted = self.dp_attn_adapter.maybe_convert_decode_to_extend(ret)
        if converted is running_batch and converted.forward_mode.is_extend():
            # The converted batch re-enters via the last_batch extend-merge
            # next iteration; empty running_batch or it merges with itself.
            running_batch = ScheduleBatch(
                reqs=[], batch_is_full=running_batch.batch_is_full
            )
        ret = converted
        self._arm_prefill_decode_interval(ret)

        # Handle ngram embedding
        ret = self.ngram_embedding_manager.prepare_for_forward(
            ret, chunked_req=self.chunked_req
        )

        if ret:
            set_schedule_time_batch(ret)
            if self.enable_fpm:
                ret.fpm_start_time = self._fpm_batch_t0

        return NextBatchPlan(batch_to_run=ret, running_batch=running_batch)
```


### `Scheduler._get_new_batch_prefill_raw` — `python/sglang/srt/managers/scheduler.py:6684-7100` (417 lines)

```python
    def _get_new_batch_prefill_raw(
        self,
        prefill_delayer_single_pass: Optional[PrefillDelayerSinglePassExecutor],
        running_batch: ScheduleBatch,
    ) -> Tuple[Optional[ScheduleBatch], ScheduleBatch]:
        # Check if the grammar is ready in the grammar queue
        if self.grammar_manager.has_waiting_grammars():
            ready_grammar_requests = self.grammar_manager.get_ready_grammar_requests()
            for req in ready_grammar_requests:
                self._add_request_to_queue(req)

        if self.enable_hierarchical_cache or get_memory().enable_flexkv:
            self.tree_cache.check_hicache_events()
            if self.enable_hicache_storage:
                self._reconcile_restore_states()
                # P3 Ready Horizon v0 (3.2): maintain the READY_HOST pool
                # after the restore reconciliation (event-driven, M3).
                self._ready_horizon_pass()

        # [P2A] Periodic aggregate of admission-deny reasons; per-attempt
        # denies are counters in schedule_policy, not log lines.
        deny_now = time.time()
        if deny_now - self._last_deny_stats_ts >= 30.0:
            self._last_deny_stats_ts = deny_now
            deny_stats = prefill_deny_snapshot()
            if deny_stats:
                logger.info(
                    "[P2A] ts_ms=%d evt=prefill_deny_summary reasons=%s",
                    int(deny_now * 1000),
                    deny_stats,
                )

        # Reset batch_is_full to retry admission with a prefill adder.
        if running_batch.batch_is_full:
            _p2a_trace("[P2A] ts_ms=%d evt=bif_reset", int(time.time() * 1000))
        running_batch.batch_is_full = False

        if (
            running_batch.batch_is_full or len(self.waiting_queue) == 0
        ) and self.chunked_req is None:
            return None, running_batch

        running_bs = len(running_batch.reqs)
        # Skipped during a chunked prefill: that pass must proceed regardless.
        if (
            self.min_free_slots_delayer is not None
            and self.chunked_req is None
            and self.min_free_slots_delayer.should_delay(
                running_bs=running_bs,
                num_allocatable_reqs=self.get_num_allocatable_reqs(
                    running_bs, running_batch=running_batch
                ),
            )
        ):
            return None, running_batch

        # Ignore the check if self.chunked_req is not None.
        # In the non-PP case, when self.chunked_req is not None, num_allocatable_reqs should always be greater than 0,
        # as the space for the chunked requests has just been released.
        # In PP case, chunked requests (or dllm requests) can start in one microbatch and end in another microbatch, so the max_running_requests per microbatch should not be strict.
        # Instead, we should always allow chunked requests to be added, otherwise, there will be a memory leak.
        if (
            self.get_num_allocatable_reqs(running_bs, running_batch=running_batch) <= 0
            and self.chunked_req is None
            and not self.enable_priority_preemption
        ):
            running_batch.batch_is_full = True
            _p2a_trace("[P2A] ts_ms=%d evt=bif_set reason=allocatable", int(time.time() * 1000))
            return None, running_batch

        # Get priority queue
        self.policy.calc_priority(self.waiting_queue, running_batch)

        if TEST_RETRACT and running_bs > TEST_RETRACT_NO_PREFILL_BS:
            # If we are testing retraction and the running batch size exceeds
            # TEST_RETRACT_NO_PREFILL_BS, we skip the prefill to keep the requests
            # in the waiting queue.
            return None, running_batch

        if self.enable_ready_horizon:
            # M4 READY-first: stable partition, explicit priority > READY
            # > base policy; off = the calc_priority order unchanged.
            self.waiting_queue = self.ready_horizon.partition_ready_first(
                self.waiting_queue,
                tree=self.tree_cache,
                buffer_mode=self.server_args.hicache_host_memory_mode == "buffer_only",
                priority=self.enable_priority_scheduling,
            )

        # Determine chunked_prefill_size for this batch
        chunked_prefill_size = self.chunked_prefill_size
        if self.chunked_req is not None and self.enable_dynamic_chunking:
            history_len = len(self.chunked_req.prefix_indices)
            dynamic_size = self.predict_next_chunk_size(history_len)
            if dynamic_size is not None:
                chunked_prefill_size = dynamic_size

        # Prefill policy
        # Get BLOCK_M from the backend for tile-budget admission logic
        attn_backend = self.tp_worker.model_runner.attn_backend
        if hasattr(attn_backend, "extend_attention_block_m"):
            prefill_tile_block_m = attn_backend.extend_attention_block_m
        else:
            prefill_tile_block_m = 64  # Fallback for non-Triton backends

        adder = PrefillAdder(
            self.page_size,
            self.tree_cache,
            self.token_to_kv_pool_allocator,
            running_batch,
            self.new_token_ratio_tracker.current,
            self.max_prefill_tokens,
            chunked_prefill_size,
            running_bs if self.is_mixed_chunk else 0,
            self.priority_scheduling_preemption_threshold,
            max_prefill_bs=int(self.max_prefill_bs),
            max_running_requests=self.max_running_requests,
            prefill_max_requests=get_schedule().prefill_max_requests,
            prefill_delayer_single_pass=prefill_delayer_single_pass,
            dllm_config=self.dllm_config,
            waiting_queue_len=len(self.waiting_queue),
            prefill_tile_block_m=prefill_tile_block_m,
        )

        if self.chunked_req is not None:
            self.chunked_req.init_next_round_input()
            self.chunked_req = adder.add_chunked_req(self.chunked_req)

        if self.enable_lora:
            running_loras = {
                req.lora_id for req in running_batch.reqs if not req.finished()
            }
            # Account for LoRAs that are already loaded in the adder, such as chunked requests
            running_loras.update(req.lora_id for req in adder.can_run_list)

            if self.lora_drainer:
                self.lora_drainer.update_draining_state(
                    self.waiting_queue,
                    running_batch.reqs,
                )

        mamba_allocator = getattr(self.req_to_token_pool, "mamba_allocator", None)
        if mamba_allocator is not None:
            mamba_allocator.alloc_group_begin(len(self.waiting_queue))
        # Get requests from the waiting queue to a new prefill batch
        for req in self.waiting_queue:
            if self.enable_lora and not self._can_schedule_lora_req(req, running_loras):
                continue

            running_bs = len(running_batch.reqs)
            _p2a_trace("[P2A] ts_ms=%d evt=admission rid=%s pos=%d qlen=%d running_bs=%d can_run=%d", int(time.time() * 1000), req.rid, self.waiting_queue.index(req), len(self.waiting_queue), running_bs, len(adder.can_run_list))
            candidate_beam_width = (
                req.beam_group.beam_width if req.beam_group is not None else None
            )
            if len(adder.can_run_list) >= self.get_num_allocatable_reqs(
                running_bs,
                candidate_beam_width,
                running_batch=running_batch,
            ):
                running_batch.batch_is_full = True
                _p2a_trace("[P2A] ts_ms=%d evt=bif_set reason=can_run rid=%s", int(time.time() * 1000), req.rid)
            if self.disaggregation_mode == DisaggregationMode.PREFILL:
                # In prefill mode, prealloc queue and transfer queue can also take memory,
                # so we need to check if the available size for the actual available size.
                if len(adder.can_run_list) >= self.req_to_token_pool.available_size():
                    running_batch.batch_is_full = True
                    _p2a_trace("[P2A] ts_ms=%d evt=bif_set reason=disagg rid=%s", int(time.time() * 1000), req.rid)

            if running_batch.batch_is_full:
                if (
                    not self.enable_priority_preemption
                    or not adder.preempt_to_schedule(req, self.server_args)
                ):
                    break

            if self.enable_hicache_storage:
                prefetch_done = self.tree_cache.check_prefetch_progress(req.rid)
                if not prefetch_done:
                    # skip staging requests that are ongoing prefetch
                    continue
                # P2-1 M1b: consume a terminal prefetch outcome recorded by
                # the drain or by check_prefetch_progress itself (finalize /
                # revoke) before the WAIT skip below.
                self._feed_restore_terminal(req)
                if req.hicache_restore_state is RestoreState.WAIT_CAPACITY:
                    # Restore intent denied for capacity: keep waiting for a
                    # wake (T11/T12) instead of admitting into a full
                    # recompute; bounded by the WAIT timeout (T13).
                    continue
                # Pop the number of tokens loaded from storage (L3 hits)
                loaded_tokens = self.tree_cache.pop_prefetch_loaded_tokens(req.rid)
                if loaded_tokens > 0:
                    req.storage_hit_length = loaded_tokens
                    # [P2A] restore "satisfied": the issued prefetch's
                    # requested span is served from the restored KV this
                    # admission (loaded_tokens > 0), not merely IO-complete
                    # to host. This is the issued->satisfied service marker
                    # for the B_ep/B_fin per-finish windows (metric_compare
                    # pairs it against the last prefetch_issued of the same
                    # rid). The write-back reserve fix (writeback consumes
                    # the reserve) is what lets a chain persist to L3 so a
                    # later episode can satisfy at all.
                    logger.info(
                        "[P2A] ts_ms=%d evt=restore_success rid=%s n_tokens=%d",
                        int(time.time() * 1000),
                        req.rid,
                        loaded_tokens,
                    )
            req.init_next_round_input(self.tree_cache)
            if (
                self.enable_hicache_storage
                and self.server_args.hicache_host_memory_mode == "buffer_only"
            ):
                # Buffer mode: surface a staged prefetch as the request's host
                # hit (consumed through init_load_back) plus its SWA window,
                # which consumption allocates and the request lock pins —
                # uncharged, the batch alloc can OOM. Set AFTER
                # init_next_round_input (which recomputes host_hit). Mamba
                # (fenced in init_hicache) will need the same charge via
                # mamba_host_hit_length.
                held_tokens = self.tree_cache.staged_prefetch_tokens(req.rid)
                if held_tokens > 0:
                    req.host_hit_length = held_tokens
                    req.swa_host_hit_length = (
                        self.tree_cache.staged_prefetch_swa_tokens(req.rid)
                    )
            res = adder.add_one_req(
                req,
                has_chunked_req=(self.chunked_req is not None),
                truncation_align_size=self.truncation_align_size,
            )
            if res == AddReqResult.CONTINUE:
                if req.hicache_telemetry_enabled:
                    req.hicache_admission_mono_ns = time.monotonic_ns()
                origin = getattr(req, "hicache_prefetch_last_origin", None)
                logger.info(
                    "[P3] ts_ns=%d evt=admission.v2 schema=rh_admission.v2 "
                    "rid=%s rh_decision_id=%s hicache_prefetch_attempt_id=%s "
                    "hicache_prefetch_origin=%s ready_host_observed=%s "
                    "admission_monotonic_ns=%d can_run=%s",
                    time.monotonic_ns(),
                    req.rid,
                    getattr(req, "hicache_last_rh_decision_id", None),
                    getattr(req, "hicache_prefetch_last_attempt_id", None),
                    origin.name if origin is not None else "null",
                    (
                        "true"
                        if req.hicache_restore_state is RestoreState.READY
                        else "null"
                    ),
                    time.monotonic_ns(),
                    "true",
                )

            if self.enable_lora:
                running_loras.add(req.lora_id)

            if res != AddReqResult.CONTINUE:
                if res == AddReqResult.NO_TOKEN:
                    if self.enable_hicache_storage and self._restore_potential_for(req):
                        # P2-1 M1b (T6): quota deny with restore material:
                        # mark WAIT[DEVICE_QUOTA] and keep scanning (no
                        # batch_is_full -- the request is not admitted and
                        # does not stall the queue behind it; the WAIT skip
                        # above holds it until a T11 wake).
                        #
                        # P1 restore re-arm churn gate (phase2-peranchor): a
                        # request parked in MISS_RECOMPUTE (proven L3-missing
                        # this episode) MUST NOT re-enter WAIT[DEVICE_QUOTA]
                        # while the ANCHOR's per-anchor storage version is
                        # unchanged and the generation matches -- re-arming
                        # would re-probe the same missing prefix and miss
                        # again (the ~13ms WAIT -> RESTORING -> revoked:miss
                        # -> ADMISSION_DENY -> WAIT churn). Only THIS anchor's
                        # substantive durability change (write ack promotion /
                        # restore read-back / durable-belief clear), a change
                        # of the anchor itself (re-anchored to a different
                        # node / deleted-anchor self-heal to a new candidate),
                        # or a generation change overrides the sticky miss
                        # (re-armable -- this candidate's L3 coverage may
                        # really cover the prefix now). An unrelated chain's
                        # write ack advances only the global diagnostic
                        # counter and never re-arms.
                        #
                        # P4-round2 (点3): same-anchor version advance is the
                        # causal signal of a durability event, but clear
                        # (durable-belief removed) and evict-rebuild both bump
                        # the version WITHOUT leaving recoverable L3 material
                        # -- re-probing those is a structural guaranteed miss
                        # (the revoked:miss churn). The same-anchor re-arm
                        # therefore additionally requires the anchor chain to
                        # now actually hold durable L3 material
                        # (_miss_rearm_durable_coverage, O(depth) structural
                        # existence check -- no counters/TTL). Re-anchor and
                        # generation change keep re-arming unconditionally.
                        miss_rearm = self._miss_rearm_decision(req)
                        self._apply_restore_event(
                            req,
                            RestoreEvent.ADMISSION_DENY,
                            rearm_allowed=miss_rearm,
                        )
                        self._cleanup_not_added_req(req, adder)
                        continue
                    _p2a_trace("[P2A] ts_ms=%d evt=no_token rid=%s res=%s can_run=%d", int(time.time() * 1000), req.rid, res, len(adder.can_run_list))
                    if self.enable_hierarchical_cache:
                        # Set batch_is_full after making sure there are requests that can be served
                        running_batch.batch_is_full = len(adder.can_run_list) > 0 or (
                            not running_batch.is_empty()
                        )
                        _p2a_trace("[P2A] ts_ms=%d evt=bif_set reason=no_token_hicache rid=%s", int(time.time() * 1000), req.rid)
                    else:
                        running_batch.batch_is_full = True
                        _p2a_trace("[P2A] ts_ms=%d evt=bif_set reason=no_token rid=%s", int(time.time() * 1000), req.rid)
                elif res == AddReqResult.RESTORE_DENIED:
                    # P2-1 M1b (T7): host material exists but the device
                    # quota for load-back was transiently unavailable: mark
                    # WAIT[DEVICE_QUOTA] and keep scanning (design C4).
                    logger.info(
                        "[P2A] ts_ms=%d evt=restore_loadback_fail rid=%s",
                        int(time.time() * 1000),
                        req.rid,
                    )
                    self._apply_restore_event(req, RestoreEvent.LOAD_BACK_FAIL)
                    self._cleanup_not_added_req(req, adder)
                    continue
                self._cleanup_not_added_req(req, adder)
                break

        if mamba_allocator is not None:
            mamba_allocator.alloc_group_end()

        # Update waiting queue
        can_run_list: List[Req] = adder.can_run_list
        if len(can_run_list) == 0:
            return None, running_batch

        can_run_set = set(can_run_list)
        self.waiting_queue = [x for x in self.waiting_queue if x not in can_run_set]
        if adder.preempt_list:
            for req in adder.preempt_list:
                self._add_request_to_queue(req)

        if adder.new_chunked_req is not None:
            # Update chunked prefill
            assert self.chunked_req is None
            self.chunked_req = adder.new_chunked_req

        if self.chunked_req is not None:
            self.chunked_req.inflight_middle_chunks += 1

        set_time_batch(can_run_list, "set_forward_entry_time")

        # Create a new batch
        new_batch = ScheduleBatch.init_new(
            can_run_list,
            self.req_to_token_pool,
            self.token_to_kv_pool_allocator,
            self.tree_cache,
            self.model_config,
            self.enable_overlap,
            self.spec_algorithm,
            chunked_req=self.chunked_req,
        )

        new_batch.contains_last_prefill_chunk = (
            self.chunked_req is None or len(can_run_list) != 1
        )

        if self.enable_hierarchical_cache:
            # todo (zhiqiang): disable cuda graph execution if hicache loading triggered
            new_batch.hicache_consumer_index = (
                self.tree_cache.ready_to_load_host_cache()
            )

        new_batch.prepare_for_extend()

        if self.tp_worker.model_runner.prefill_aware_swa:
            for req in can_run_list:
                req.swa_evict_floor = req.extend_range.end

        # Record prefill stats for logging after forward.
        new_batch.prefill_stats = PrefillStats.from_adder(
            adder,
            running_batch.reqs,
            self.enable_priority_scheduling,
            num_pending_tokens=self.load_inquirer._get_num_pending_tokens(
                chunk_deduct=(
                    self.chunked_req.extend_range.length
                    if self.chunked_req is not None
                    else 0
                ),
            ),
        )

        # Mixed-style chunked prefill
        if (
            self.is_mixed_chunk
            and not running_batch.is_empty()
            and not (new_batch.return_logprob or running_batch.return_logprob)
            # mix_with_running cats input_ids but not input_embeds — shapes would mismatch
            and new_batch.input_embeds is None
            # Beam member rows are not supported inside a mixed extend batch.
            and all(r.beam_group is None for r in running_batch.reqs)
        ):
            # TODO (lianmin): support return_logprob + mixed chunked prefill
            running_batch.filter_batch()
            if not running_batch.is_empty():
                running_batch.prepare_for_decode()
                new_batch.mix_with_running(running_batch)
                new_batch.decoding_reqs = running_batch.reqs
            running_batch = ScheduleBatch(
                reqs=[], batch_is_full=running_batch.batch_is_full
            )
        else:
            new_batch.decoding_reqs = None

        return new_batch, running_batch
```


## 4. Complete hot-path source: `python/sglang/srt/mem_cache/unified_radix_cache.py`

Source version: `06f89994845f0e41c779950924064c16ebfbd956`.


### `UnifiedRadixCache.match_prefix` — `python/sglang/srt/mem_cache/unified_radix_cache.py:2989-3021` (33 lines)

```python
    def match_prefix(self, params: MatchPrefixParams) -> MatchResult:
        if durable_trace_enabled() and params.req is not None:
            session_id = self._t38c_req_session_id(params.req)
            session_generation = getattr(params.req, "session_generation", None)
            warm = (
                session_id is not None
                and session_generation is not None
                and (str(session_id), session_generation)
                in self._t38c_session_builds
            )
            context = self._t38c_trace_context_for_req(params.req, warm=warm)
            if context is not None:
                self._t38c_request_contexts[
                    (
                        context["session_id"],
                        context["session_generation"],
                        str(params.req.rid),
                    )
                ] = dict(context)
        result = self.session.try_match_prefix(params)
        if result is not None:
            return result
        if self.disable:
            return self.tree_core.empty_match_result
        result = self.tree_core.match_prefix(params)
        # Apply the walk's actions (e.g. a pending write-through relocation on
        # a split) before the finalizers, which can evict or raise.
        self._apply_cache_actions(result.cache_actions)
        for component in self._components_tuple:
            result = component.finalize_match_result_in_cache(params, result)
        # Finalizers must not emit actions; the walk's were applied above.
        assert not result.cache_actions
        return result
```


### `UnifiedRadixCache._drain_acks_and_reclaim_host` — `python/sglang/srt/mem_cache/unified_radix_cache.py:4175-4191` (17 lines)

```python
    def _drain_acks_and_reclaim_host(self, num_tokens: int) -> int:
        """Drain finished storage acks, then retry host eviction once.

        Mirrors the F1 recovery already used by ``_execute_kv_backup``: a
        completed L3 write keeps ``host_lock_ref`` on its node until the ack is
        consumed, so staging can be refused while reclaimable slots are still
        pinned behind the ack backlog.  Bounded to one drain and one eviction
        pass so the staging path cannot loop.
        """
        if num_tokens <= 0:
            return 0
        try:
            self.drain_storage_control_queues_local()
        except Exception:  # pragma: no cover - best-effort recovery
            logger.warning("host staging: ack drain failed", exc_info=True)
            return 0
        return int(self.evict_host(num_tokens) or 0)
```


### `UnifiedRadixCache._track_write_through_node` — `python/sglang/srt/mem_cache/unified_radix_cache.py:4521-4529` (9 lines)

```python
    def _track_write_through_node(
        self,
        node_id: NodeId,
        lock_params: Optional[DecLockRefParams],
    ) -> None:
        self.tree_core.mark_write_through_pending(node_id)
        self.ongoing_write_through[node_id] = _OngoingWriteThrough(
            node_id, lock_params, [node_id]
        )
```


### `UnifiedRadixCache._finish_write_through_ack` — `python/sglang/srt/mem_cache/unified_radix_cache.py:4557-4574` (18 lines)

```python
    def _finish_write_through_ack(self, ack_id: int) -> None:
        if self.buffer_pipeline is not None:
            self.buffer_pipeline.finish_backup_ack(ack_id)
            return

        lock_node_id, lock_params, publish_node_ids = self.ongoing_write_through.pop(
            ack_id
        )
        self.tree_core.finish_write_through(publish_node_ids, ack_id)
        if lock_params is not None:
            self.dec_lock_ref(lock_node_id, lock_params)
        if self.enable_storage:
            # Back up each fragment: after a split, lock_node only holds the
            # suffix; the prefix fragment must be persisted as well. Deferred:
            # the gap-fill wait would re-enter the running drain (unbounded
            # recursion); _flush_pending_storage_writes persists the nodes
            # once the drain returns.
            self._pending_storage_writes.extend(publish_node_ids)
```


### `UnifiedRadixCache._promotion_budget_fits` — `python/sglang/srt/mem_cache/unified_radix_cache.py:4593-4602` (10 lines)

```python
    def _promotion_budget_fits(self, new_restore: int) -> bool:
        """Promotion budget predicate (design §3.1):
        locked + reserved + new_restore <= capacity - margin."""
        return promotion_budget_fits(
            locked=self._device_locked_tokens(),
            reserved=self.inflight_promotion_reserved,
            new_restore=new_restore,
            capacity=self.token_to_kv_pool_allocator.size_full,
            margin=self.promotion_margin_tokens,
        )
```


### `UnifiedRadixCache._finalize_load_back_entry` — `python/sglang/srt/mem_cache/unified_radix_cache.py:4698-4710` (13 lines)

```python
    def _finalize_load_back_entry(self, entry: _OngoingLoadBack, cause: str) -> None:
        """Release a registered load-back entry's residual reservation and
        locks exactly once (expert ② finalizer: success ACK, failure, cancel,
        fatal, and shutdown all terminate here or in the pre-registration
        release paths). The caller pops the entry from ongoing_load_back
        before invoking this, so exactly-once is structural.
        """
        if entry.reserved_tokens > 0:
            self._release_promotion_reservation(
                entry.reserved_tokens, entry.node_id, cause
            )
        self.dec_lock_ref(entry.node_id, entry.lock_params)
        self.dec_host_lock_ref(entry.node_id, entry.host_lock_params)
```


### `UnifiedRadixCache.load_back` — `python/sglang/srt/mem_cache/unified_radix_cache.py:4720-4784` (65 lines)

```python
    def load_back(
        self,
        node_id: NodeId,
        mem_quota: Optional[int] = None,
        req=None,
    ) -> bool:
        """Load evicted KV data from host back to device (H→D)."""
        if self.cache_controller is None:
            return False

        # P2-1c checkpoint 1 (entry gate; design §3.2): reserve-before-lock
        # admission. The budget holds `locked + reserved + est <= capacity -
        # margin`; est is the host-only span about to be promoted (the
        # request's device prefix is already inside the derived locked term,
        # so no double/lost count here). Rejecting before any lock costs
        # nothing (no host anchor, no chain lock, no spec build) and flows
        # into the existing RESTORE_DENIED -> WAIT[DEVICE_QUOTA] path (M1b).
        # est == 0 (pure aux restore) skips the FULL-KV budget: aux pools
        # have their own budget (rem_swa_tokens).
        est = (
            req.host_hit_length
            if (req is not None and req.host_hit_length > 0)
            else 0
        )
        if est > 0 and not self._promotion_budget_fits(est):
            self._promotion_denied_count += 1
            logger.info(
                "[P2A] ts_ms=%d evt=promotion_denied rid=%s est=%d locked=%d "
                "reserved=%d margin=%d%s",
                int(time.time() * 1000),
                req.rid if req is not None else None,
                est,
                self._device_locked_tokens(),
                self.inflight_promotion_reserved,
                self.promotion_margin_tokens,
                self._promotion_pool_observation(),
            )
            return False

        host_anchor_params = self.inc_host_lock_ref(node_id).to_dec_params()

        # Lock the path before building transfers (the aux build can evict).
        result = self.inc_lock_ref(node_id)
        ancestor_lock_params = result.to_dec_params()

        # Let each component pre-allocate per-request state for the load-back;
        # the finally below lets components recover it unless the load succeeds.
        preps: dict[ComponentType, PrepareLoadBackResult] = {
            comp.component_type: comp.prepare_load_back(node_id, req=req)
            for comp in self._components_tuple
        }
        success = False
        try:
            success = self._load_back_transfers(
                node_id=node_id,
                mem_quota=mem_quota,
                req=req,
                result=result,
                ancestor_lock_params=ancestor_lock_params,
                host_anchor_params=host_anchor_params,
            )
            return success
        finally:
            for comp in self._components_tuple:
                comp.finalize_load_back(req, preps[comp.component_type], success)
```


### `UnifiedRadixCache._flush_pending_storage_writes` — `python/sglang/srt/mem_cache/unified_radix_cache.py:4978-4991` (14 lines)

```python
    def _flush_pending_storage_writes(self) -> None:
        """Drain deferred storage writes without recursive re-entry.

        write_backup_storage may itself finish D->H acknowledgements, which
        queue more nodes and call this method. The outer drain owns the queue;
        nested drains must return so the outer loop can consume those entries.
        """
        if getattr(self, "_pending_storage_flush_active", False):
            return
        self._pending_storage_flush_active = True
        try:
            self._flush_pending_storage_writes_inner()
        finally:
            self._pending_storage_flush_active = False
```


### `UnifiedRadixCache._flush_pending_storage_writes_inner` — `python/sglang/srt/mem_cache/unified_radix_cache.py:4993-5026` (34 lines)

```python
    def _flush_pending_storage_writes_inner(self) -> None:
        """Persist every node whose D->H write acked while its chain was not
        yet written to L3. The ack path only defers (see
        _finish_write_through_ack), so this runs outside any drain. Nodes
        deleted since their deferral (eviction/drop/tombstone cleanup) are
        skipped, not persisted."""
        while self._pending_storage_writes:
            node_id = self._pending_storage_writes.pop(0)
            if not self.tree_core.node_exists(node_id):
                self._skip_stale_storage_persist(node_id)
                continue
            try:
                self.write_backup_storage(node_id)
            except KeyError:
                # Backstop: the node or a gap ancestor died between the
                # existence check and the arena lookups; nothing to persist.
                self._skip_stale_storage_persist(node_id)
        # P3 (phase2-p3-fix): deferred-ACK reconciliation. A node whose L3
        # write acked while its parent chain was not persisted is left
        # deferred (storage_acked && !storage_persisted) by
        # advance_storage_persisted. If its parent chain is later cleared
        # (revoke-miss clear_storage_durable) or physically deleted
        # (eviction/tombstone), nothing re-promotes it without a fresh IO
        # -- the permanent frontier HOL (T13 60s timeout). This pass
        # rescans deferred_acked_nodes each drain and re-fills each
        # surviving node's chain from the nearest persisted ancestor / root
        # (collect_storage_gap), then re-promotes through a real write ack.
        # Idempotent: collect_storage_gap skips already-written nodes,
        # write_backup_storage skips is_storage_written / dead nodes, and
        # advance_storage_persisted returns early for persisted nodes; a
        # single pass re-fills each broken chain once. Reconciliation never
        # sets storage_persisted itself -- promotion stays a real-ack /
        # real-restore fact.
        self._reconcile_deferred_acked()
```


### `UnifiedRadixCache._reconcile_deferred_acked` — `python/sglang/srt/mem_cache/unified_radix_cache.py:5028-5044` (17 lines)

```python
    def _reconcile_deferred_acked(self) -> None:
        """P3 A3: re-fill and re-promote every deferred-ACK node (acked but
        not persisted) whose chain is broken by a cleared / deleted parent.
        One ancestors-first sweep per outermost _flush_pending_storage_writes;
        per-node gap fill is idempotent (see _flush_pending_storage_writes).
        Re-entrancy guarded: write_backup_storage itself calls
        _flush_pending_storage_writes at its tail, so without a depth guard a
        deferred node that is not resolved in one fill (ack in flight, or an
        unfillable chain) would re-enter this scan from inside itself,
        unboundedly."""
        if getattr(self, "_reconcile_depth", 0) > 0:
            return
        self._reconcile_depth = getattr(self, "_reconcile_depth", 0) + 1
        try:
            self._reconcile_deferred_acked_inner()
        finally:
            self._reconcile_depth -= 1
```


### `UnifiedRadixCache._reconcile_deferred_acked_inner` — `python/sglang/srt/mem_cache/unified_radix_cache.py:5046-5082` (37 lines)

```python
    def _reconcile_deferred_acked_inner(self) -> None:
        if not self.enable_storage or self.cache_controller is None:
            return
        deferred = self.tree_core.deferred_acked_nodes()
        if not deferred:
            return
        for node_id in deferred:
            if not self.tree_core.node_exists(node_id):
                self._skip_stale_storage_persist(node_id)
                continue
            try:
                # 1) Fill any broken parent gap: re-write the nodes whose
                #    parent chain was physically deleted (tombstone / host
                #    eviction) from the nearest persisted ancestor / root.
                #    collect_storage_gap skips already-written nodes, so this
                #    is a no-op for a node whose write is already complete.
                self.write_backup_storage(node_id)
            except KeyError:
                # A gap ancestor died between the scan and the arena lookups.
                self._skip_stale_storage_persist(node_id)
                continue
            # 2) Re-run promotion on the already-acked node. Its write is
            #    real and acked; it was only deferred because the parent
            #    chain was not contiguous when the ack arrived. Now that the
            #    chain is contiguous (parent persisted, or the node re-anchored
            #    to root after its parent was deleted), re-invoking the same
            #    promotion entry the ack drain uses promotes the node and its
            #    acked descendants. This is the reverse-path repair -- it does
            #    not fabricate durability (advance_storage_persisted only
            #    promotes when the parent chain is contiguous), and it is
            #    idempotent (advance returns early for an already-persisted
            #    node). Waking frontier waiters mirrors the ack drain: a
            #    freshly promoted anchor can serve its waiters, closing the
            #    loop that the T13 timeout path used to cut short.
            promoted = self.tree_core.advance_storage_persisted(node_id)
            for promoted_id in promoted:
                self._wake_frontier_waiters(promoted_id)
```


### `UnifiedRadixCache.write_backup_storage` — `python/sglang/srt/mem_cache/unified_radix_cache.py:5089-5163` (75 lines)

```python
    def write_backup_storage(self, node_id: NodeId) -> None:
        """Persist node_id's KV chain to L3, completing ancestor gaps first.

        L3 reads only hit when every page hash from the recoverable anchor
        down to the node exists in storage. write_back evicts leaves without
        ever backing up their ancestors, so writing only the leaf would
        persist a suffix with a missing prefix. Fill the anchor->node gap:
        host-backup the unbacked gap nodes, wait out their D->H acks (their
        ack path re-enters this method per node and submits those L3 writes),
        then submit the remaining gap nodes in ancestors-first order."""
        if not self.enable_storage or self.cache_controller is None:
            return
        gap = self.tree_core.collect_storage_gap(node_id)
        # Gap nodes may have been deleted since the deferral: the arena
        # lookup below would KeyError on a dead id. Nodes deleted by this
        # loop's own D->H backups are re-filtered per iteration.
        gap = [nid for nid in gap if self.tree_core.node_exists(nid)]
        if not gap:
            return
        for nid in gap:
            if not self.tree_core.node_exists(nid):
                self._skip_stale_storage_persist(nid)
                continue
            if not self.tree_core.is_backuped(nid):
                # P0 (phase2-backupassert): a gap node may be unbacked AND
                # host-only (device value already released by an eviction /
                # hollow / forced-miss, or inserted host-only). `is_backuped`
                # alone cannot distinguish "unbacked with a device value"
                # (needs a D->H backup) from "unbacked host-only" (device
                # value gone; host copy is the only KV). Do not run the D->H
                # backup when there is no device value to copy -- the
                # _build_backup_spec assert would fire. Skip and let the
                # storage-write loop below persist the host copy to L3.
                if self.tree_core.get_component_device_value(
                    nid, BASE_COMPONENT_TYPE
                ) is None:
                    self._storage_gap_skipped_d2h_count += 1
                    continue
                backed_up_tokens = self._execute_and_commit_kv_backup(
                    BackupKV([nid]), write_back=False
                )
                if backed_up_tokens <= 0 and not self.tree_core.is_backuped(nid):
                    # Do not persist descendants past an ancestor whose D->H
                    # transfer failed; retry the gap after capacity recovers.
                    return
        # The D->H backups above evict_host when host space is tight; host
        # eviction deletes host-only leaves, which may be gap nodes. Re-filter
        # before the drain and L3 writes.
        gap = [nid for nid in gap if self.tree_core.node_exists(nid)]
        # Blocking, but only in the write_back path, which already blocks on
        # D->H acks in writing_check; the write_through path never has an
        # unbacked gap node. Ack completion only defers L3 persists (see
        # _finish_write_through_ack), so the drain never re-enters here.
        while any(nid in self.ongoing_write_through for nid in gap):
            self._drain_write_through_acks()
        for nid in gap:
            if not self.tree_core.node_exists(nid):
                self._skip_stale_storage_persist(nid)
                continue
            if not self.tree_core.is_backuped(nid):
                # P0 (phase2-backupassert): a gap node with neither a device
                # value nor a host copy (a forced-miss tombstone / hollow with
                # no KV in any tier) has nothing to persist. It must not be
                # written to L3 as if it carried content (would fabricate a
                # durable chain for a node that holds no KV) -- skip it as the
                # explicit invalid / un-backupable state and record the reason.
                self._storage_gap_skipped_nokv_count += 1
                continue
            if not self.tree_core.is_storage_written(nid):
                self._write_backup_storage_node(nid)
        # Nodes deferred by the acks drained above completed their D->H DMAs;
        # persist them now, before a later eviction can reclaim their host
        # copies. Their chains were either just submitted or are filled by
        # the nested calls.
        self._flush_pending_storage_writes()
```


### `UnifiedRadixCache._write_backup_storage_node` — `python/sglang/srt/mem_cache/unified_radix_cache.py:5165-5268` (104 lines)

```python
    def _write_backup_storage_node(self, node_id: NodeId) -> None:
        """Submit one node's KV to L3 and register its ack entry."""
        cc = self.cache_controller
        if cc is not None and cc.storage_failure_reason is not None:
            # Storage degraded: keep the node host-only (no L3 write, no ack
            # entry); the next persist flush skips it again at this gate.
            return
        spec = self.tree_core.build_storage_backup_spec(
            node_id, self.hicache_storage_pass_prefix_keys
        )
        if spec is None:
            return

        kv_xfer = PoolTransfer(
            name=PoolName.KV,
            host_indices=spec.host_value,
            keys=spec.hash_value,
        )
        sidecar_xfers = self._build_sidecar_transfers(
            CacheTransferPhase.BACKUP_STORAGE, kv_xfer, spec.comp_xfers
        )
        aux_xfers = [x for xfers in spec.comp_xfers.values() for x in xfers]
        aux_xfers.extend(sidecar_xfers)
        mamba_transfers = [
            transfer for transfer in aux_xfers if transfer.name == PoolName.MAMBA
        ]
        trace_context = self._t38c_trace_context_for_node(node_id)
        # Carry write-side identity only for the gated diagnostic.  The
        # storage backend emits the eventual batch_set_v2 result, while this
        # submission record distinguishes an omitted BACKUP_STORAGE transfer.
        for transfer in mamba_transfers:
            transfer._t38c_node_id = str(node_id)
            transfer._t38c_final_kv_hash = (
                spec.hash_value[-1] if spec.hash_value else ""
            )

        # T38C-PROBE (L3 write-chain observation; log-only, gated on
        # /tmp/t38c-on). Records the write chain's full-64-hex seed and first
        # page hash so a live run can be compared byte-for-byte against the
        # read-side pc_prefetch_enter / pc_storage_query (full 64-hex). The
        # write chain is seeded by the parent's last hash
        # (compute_node_hash_values -> parent.hash_value[-1]).
        try:
            _wparent = self.tree_core.node_by_id(node_id).parent
            _wseed = (
                _wparent.get_last_hash_value()
                if _wparent is not None
                else None
            )
            _t38c_log({
                "evt": "pc_write_seed",
                "node_id": str(node_id),
                "write_seed": _wseed or "",
                "page0_hash": spec.hash_value[0] if spec.hash_value else "",
                "page1_hash": spec.hash_value[1] if len(spec.hash_value or []) > 1 else "",
                "n_pages": len(spec.hash_value or []),
                "final_kv_hash": spec.hash_value[-1] if spec.hash_value else "",
                "mamba_transfer_exists": bool(mamba_transfers),
                "mamba_key": (
                    mamba_transfers[0].keys[-1]
                    if mamba_transfers and mamba_transfers[0].keys
                    else ""
                ),
            })
        except Exception:
            pass

        operation_id = self.cache_controller.write_storage(
            spec.host_value,
            spec.token_ids,
            spec.hash_value,
            spec.prefix_keys,
            extra_pools=aux_xfers or None,
            node_id=node_id,
            trace_context=trace_context,
        )
        _t38c_durable_log(
            {
                "evt": "backup_submit",
                "trace_context": trace_context,
                "operation_id": operation_id,
                "attempt_id": f"storage-{operation_id}",
                "node_id": str(node_id),
                "final_kv_hash": spec.hash_value[-1] if spec.hash_value else "",
                "kv_transfer": bool(spec.host_value is not None and spec.hash_value),
                "kv_pages": len(spec.hash_value or []),
                "mamba_transfer": bool(mamba_transfers),
                "mamba_pages": len(mamba_transfers[0].keys or [])
                if mamba_transfers
                else 0,
                "mamba_key": (
                    mamba_transfers[0].keys[-1]
                    if mamba_transfers and mamba_transfers[0].keys
                    else ""
                ),
            }
        )
        self.ongoing_backup[operation_id] = (
            node_id,
            self.inc_host_lock_ref(node_id).to_dec_params(),
        )
        # Dedupe guard at submission: the re-entrant gap walk must not
        # resubmit a node whose write is already in flight.
        self.tree_core.mark_storage_written(node_id)
```


### `UnifiedRadixCache.prefetch_gate_ok` — `python/sglang/srt/mem_cache/unified_radix_cache.py:5273-5285` (13 lines)

```python
    def prefetch_gate_ok(self, node_id: NodeId, buffer_mode: bool = False) -> bool:
        """P2-1 M2 prefetch gate: an anchor is prefetch-issuable when it is
        host-backuped (the cache-mode write-through contiguity), the root, or
        L3-durable (the durable copy the T11/T12 wake predicates rely on;
        P2-1 e14 extends it from written+acked to restored chains).
        Gate and wake must agree or every wake re-registers the wait (the
        frontier spin). Buffer mode reads by hash, never by anchor backup."""
        return (
            self.is_backuped(node_id)
            or self.is_root(node_id)
            or self.is_l3_durable(node_id)
            or (buffer_mode and self.get_last_hash_value(node_id) is not None)
        )
```


### `UnifiedRadixCache._prefetch_budget_denied` — `python/sglang/srt/mem_cache/unified_radix_cache.py:5541-5556` (16 lines)

```python
    def _prefetch_budget_denied(self, demand_restore: bool) -> bool:
        """P3 Ready Horizon (M1): the two-track inflight-budget admission.

        SPECULATIVE issues are bounded by the physical inflight budget
        (prefetch_rate_limited, all kinds) and, under Ready Horizon, by
        the speculative sub-budget. DEMAND restores are bounded by the
        physical budget only, and only under Ready Horizon -- off-mode
        keeps the pre-P3 T15 ticket semantics (demand bypasses the budget
        entirely, speculative checks the single physical track)."""
        cc = self.cache_controller
        physical_full = cc.prefetch_rate_limited()
        if demand_restore:
            return self.enable_ready_horizon and physical_full
        return physical_full or (
            self.enable_ready_horizon and cc.prefetch_speculative_rate_limited()
        )
```


### `UnifiedRadixCache.prefetch_from_storage` — `python/sglang/srt/mem_cache/unified_radix_cache.py:5558-5894` (337 lines)

```python
    def prefetch_from_storage(
        self,
        req_id: str,
        last_host_node_id: NodeId,
        new_input_tokens: list[int],
        last_hash: Optional[str] = None,
        prefix_keys: Optional[list[str]] = None,
        matched_prefix_tokens: Optional[list[int]] = None,
        demand_restore: bool = False,
        host_alloc_attempt_id: Optional[str] = None,
        prefetch_attempt_id: Optional[str] = None,
        telemetry_enabled: bool = False,
        session_generation: Optional[int] = None,
    ) -> Optional[str]:
        """Returns an outcome code for the P2-1 M1b state machine:
        "issued" / "declined_rate_limited" / "declined_too_short" /
        "forfeited_alloc_failed" / "skipped_no_l3" / "skipped_dup" (None
        pre-M1b semantics preserved as the skip codes).

        demand_restore marks a T15 wake re-issue (P2-IO R2): it holds a
        DEMAND_RESTORE ticket, bypassing only the speculative
        PREFETCH_BUDGET check -- every other gate (host staging alloc,
        cancellation, admission) applies as for any prefetch. The ticket
        is granted at issue and released when the prefetch leaves
        ongoing_prefetch."""
        if (
            not self.enable_storage
            or self.cache_controller is None
            or self.cache_controller.storage_failure_reason is not None
        ):
            try:
                _t38c_log({"evt": "pc_outcome", "phase": "entry",
                           "rid": req_id,
                           "outcome": "skipped_no_l3",
                           "storage_enabled": bool(self.enable_storage)})
            except Exception:
                pass
            return "skipped_no_l3"

        buffer_mode = self.host_memory_mode == "buffer_only"
        extra_key, cache_salt = self.tree_core.prefetch_anchor_info(last_host_node_id)
        prefetch_key = RadixKey(
            new_input_tokens,
            extra_key=extra_key,
            is_bigram=self.tree_core.is_eagle,
            cache_salt=cache_salt,
        ).page_aligned(self.page_size)
        prefetch_length = len(prefetch_key)
        stats = self._prefetch_outcome_stats
        if prefetch_length > 0:
            stats["attempts"] += 1
        try:
            _t38c_log({"evt": "pc_outcome", "phase": "issue", "rid": req_id,
                       "outcome": "attempt",
                       "prefetch_length": prefetch_length,
                       "prefetch_threshold": self.prefetch_threshold,
                       "suffix_len": len(new_input_tokens),
                       "counters": dict(stats)})
        except Exception:
            pass
        if prefetch_length < self.prefetch_threshold:
            if prefetch_length > 0:
                stats["declined_too_short"] += 1
            try:
                _t38c_log({"evt": "pc_outcome", "phase": "issue", "rid": req_id,
                           "outcome": "declined_too_short",
                           "counters": dict(stats)})
            except Exception:
                pass
            # A too-short/fully-matched suffix can become a full recompute if
            # the device match evicts while queued; arm the paced retry.
            self._storage_prefetch_missed_rids.add(req_id)
            _log_restore_disposition(req_id, "RECOMPUTE", prefetch_length, 0, "too_short")
            return "declined_too_short"
        if not buffer_mode and self._prefetch_budget_denied(demand_restore):
            stats["declined_rate_limited"] += 1
            try:
                _t38c_log({"evt": "pc_outcome", "phase": "issue", "rid": req_id,
                           "outcome": "declined_rate_limited", "site": "issue",
                           "counters": dict(stats)})
            except Exception:
                pass
            self._storage_prefetch_missed_rids.add(req_id)
            # The state machine parks the rid in WAIT[PREFETCH_BUDGET]
            # (T2): the T11 capacity wake re-issues when the budget frees,
            # so this decline is retryable, not a recompute (the e13
            # disposition label contradicted the observed restore_retry
            # cause=capacity wakes).
            _log_restore_disposition(req_id, "WAIT", prefetch_length, 0, "denied_rate_limit")
            return "declined_rate_limited"
        if req_id in self.ongoing_prefetch or (
            buffer_mode and self.buffer_pipeline.has_staged(req_id)
        ):
            try:
                _t38c_log({"evt": "pc_outcome", "phase": "issue", "rid": req_id,
                           "outcome": "skipped_dup",
                           "counters": dict(stats)})
            except Exception:
                pass
            # A fetch (or an unconsumed hold) already exists for this rid;
            # overwriting would leak its staging slots.
            return "skipped_dup"

        # Buffer mode holds no tree state during the fetch: buffers are
        # operation-owned, so the anchor needs no identity record.
        anchor_lock_params = (
            None
            if buffer_mode
            else self.inc_host_lock_ref(last_host_node_id).to_dec_params()
        )
        # The anchor may be evicted while the storage query is in flight (a
        # host lock only pins an extant host slot). Record its last page hash:
        # hashes chain every ancestor, so equality at completion proves both
        # that the node survived and that it still holds this exact prefix.
        anchor_last_hash = (
            None if buffer_mode else self.tree_core.get_last_hash_value(last_host_node_id)
        )
        comp_xfers: dict[ComponentType, list[PoolTransfer]] = {}
        alloc_failed = False
        for ct in self.tree_components:
            if ct == BASE_COMPONENT_TYPE:
                continue
            # Pre-allocate the component's prefetch host buffer so the build stays pure.
            prep = self.components[ct].prepare_prefetch(
                last_host_node_id, prefetch_tokens=len(prefetch_key)
            )
            if prep.alloc_failed:
                alloc_failed = True
                break
            if prep.host_indices is None:
                continue
            transfers = self.tree_core.build_hicache_transfers(
                ct,
                last_host_node_id,
                CacheTransferPhase.PREFETCH,
                token_ids=prefetch_key.token_ids,
                prefetch_tokens=len(prefetch_key),
                last_hash=last_hash,
                host_indices=prep.host_indices,
            )
            if transfers:
                comp_xfers[ct] = transfers
        kv_xfer = PoolTransfer(name=PoolName.KV, host_indices=None)
        sidecar_xfers = self._build_sidecar_transfers(
            CacheTransferPhase.PREFETCH, kv_xfer, comp_xfers
        )
        if alloc_failed:
            # The whole storage fetch is forfeited over one aux staging
            # alloc (e.g. a single SWA window) — count it, or write-burst
            # starvation of the aux pool reads as generic hit-rate loss.
            if (
                self.enable_storage_metrics
                and self.storage_metrics_collector is not None
            ):
                self.storage_metrics_collector.log_prefetch_aux_alloc_failed_tokens(
                    len(prefetch_key)
                )
            failed_pool = self._host_allocability_pool_for_component(ct)
            required_aux_units = self._host_alloc_required_aux_units(
                comp_xfers, failed_component=ct
            )
            self._release_aux_transfers_before_host_alloc_snapshot(
                comp_xfers, causal_rid=req_id
            )
            if anchor_lock_params is not None:
                self.dec_host_lock_ref(last_host_node_id, anchor_lock_params)
            snapshot = self.host_allocability_snapshot(
                [PoolName.KV.value, *required_aux_units]
            )
            telemetry_pools = {
                PoolName.KV.value: len(prefetch_key),
                **required_aux_units,
            }
            _log_host_alloc_telemetry(
                "restore_host_alloc_retry_result",
                rid=req_id,
                attempt_id=host_alloc_attempt_id,
                cache_instance_id=snapshot.cache_instance_id,
                trace_context=None,
                generation_vector_id=snapshot.generation_vector(),
                captured_generations=dict(snapshot.generation_by_pool),
                current_generations=dict(snapshot.generation_by_pool),
                full_frontier_tokens=int(len(prefetch_key)),
                crop_attempted=False,
                lower_checkpoint_queried=False,
                per_pool={
                    pool: {
                        "required": int(required),
                        "free_before": int(snapshot.free_units_by_pool.get(pool, 0)),
                        "evictable_before": int(
                            snapshot.evictable_units_by_pool.get(pool, 0)
                        ),
                        "alloc1": None,
                        "reclaimed": 0,
                        "alloc2": None,
                        "free_after": int(snapshot.free_units_by_pool.get(pool, 0)),
                        "evictable_after": int(
                            snapshot.evictable_units_by_pool.get(pool, 0)
                        ),
                    }
                    for pool, required in telemetry_pools.items()
                },
                failed_domains=[str(failed_pool)],
                retry_grant=host_alloc_attempt_id is not None,
                retry_skip=False,
                retry_outcome="forfeited_alloc_failed",
                terminal="forfeited_alloc_failed",
                genuine_miss=False,
                captured_generations_after=dict(snapshot.generation_by_pool),
                reservation_released=True,
                **_host_alloc_join_fields(req_id),
                attempt_number=1 if host_alloc_attempt_id is not None else 0,
                attempt_origin=(
                    "HOST_ALLOC_WAKE" if host_alloc_attempt_id is not None else "HOST_ALLOC_WAIT"
                ),
            )
            self.record_host_alloc_failure(
                req_id,
                HostAllocFailure(
                    requested_primary_tokens=len(prefetch_key),
                    required_aux_units=required_aux_units,
                    failed_domains=frozenset({failed_pool}),
                    positive_hit_tokens=0,
                    sidecar_hit_pages={},
                    allocability_snapshot=snapshot,
                ),
            )
            # Forfeited over transient staging pressure; retryable (T3
            # parks the rid in WAIT[HOST_ALLOC], woken by T11).
            self._storage_prefetch_missed_rids.discard(req_id)
            _log_restore_disposition(req_id, "WAIT", prefetch_length, 0, "aux_alloc_failed")
            try:
                _t38c_log({"evt": "pc_outcome", "phase": "issue", "rid": req_id,
                           "outcome": "forfeited_alloc_failed",
                           "prefetch_length": prefetch_length,
                           "counters": dict(stats)})
            except Exception:
                pass
            return "forfeited_alloc_failed"

        aux_xfers = [x for xfers in comp_xfers.values() for x in xfers]
        aux_xfers.extend(sidecar_xfers)
        trace_context = self._t38c_trace_context_for_prefetch(
            req_id, last_host_node_id
        )
        operation = self.cache_controller.prefetch(
            req_id,
            prefetch_key,
            last_hash,
            prefix_keys,
            extra_pools=aux_xfers or None,
            trace_context=trace_context,
            telemetry_enabled=telemetry_enabled,
            session_generation=session_generation,
            prefetch_attempt_id=prefetch_attempt_id,
            matched_prefix_l3_proof=self._matched_prefix_l3_proof(
                req_id,
                last_host_node_id,
                len(matched_prefix_tokens or []),
                prefetch_attempt_id,
                session_generation,
                last_hash,
            ),
            matched_prefix_tokens=len(matched_prefix_tokens or []),
        )
        # Operation-local layout fact: the required L3 component set the
        # matched-prefix proof/suffix completeness must cover.  Carried on the
        # existing operation handoff; no new registry or global state.
        operation.required_l3_components = self._required_l3_component_set()
        operation.host_alloc_attempt_id = host_alloc_attempt_id
        stats["issued"] += 1
        if _p2a_enabled():
            _p2a_block_start = time.monotonic_ns()
            _p2a_identity = _p2a_probe_identity(operation, trace_context)
            if _p2a_identity.get("node_id") is None:
                _p2a_identity["node_id"] = last_host_node_id
            _p2a_probe_ns = time.monotonic_ns() - _p2a_block_start
            _p2a_emit(
                _p2a_block_start,
                "prefetch_issued",
                _p2a_probe_ns,
                rid=req_id,
                prefetch_length=prefetch_length,
                prefetch_issue_mono_ns=_p2a_block_start,
                attempt_id=prefetch_attempt_id,
                **_p2a_identity,
            )
        else:
            logger.info("[P2A] ts_ms=%d evt=prefetch_issued rid=%s prefetch_length=%d", int(time.time() * 1000), req_id, prefetch_length)
        try:
            _t38c_log({"evt": "pc_outcome", "phase": "issue", "rid": req_id,
                       "outcome": "issued",
                       "prefetch_length": prefetch_length,
                       "counters": dict(stats)})
        except Exception:
            pass
        # Snapshots for the L3 miss accounting at the query outcome (the
        # hit/revoke drains): requested span and total prompt length.
        operation.stats_requested_tokens = prefetch_length
        operation.stats_total_tokens = prefetch_length + len(
            matched_prefix_tokens or []
        )
        self.ongoing_prefetch[req_id] = _OngoingPrefetch(
            last_host_node_id,
            prefetch_key,
            None,
            operation,
            anchor_lock_params,
            comp_xfers,
            anchor_last_hash,
        )
        if demand_restore:
            # The T15 wake re-issue is issued: grant its DEMAND_RESTORE
            # ticket (the bounded-concurrency grant, anti-thundering-herd
            # for a backup-complete wake batch). Released with the prefetch
            # at each ongoing_prefetch removal point.
            self._demand_restore_rids.add(req_id)
        if buffer_mode:
            self.buffer_pipeline.set_prefix_ctx(req_id, matched_prefix_tokens)
            # Pin the just-matched anchor now: deferred to hit-alloc it is
            # often already deleted under churn (silent unlocked launch).
            # The hit-alloc call remains as an idempotent second chance.
            self.buffer_pipeline.try_lock_anchor(req_id, last_host_node_id)
        else:
            # Cache mode reserves the requested span up front; buffer mode
            # grants occupancy later at hit-alloc time, sized to the hit.
            self.cache_controller.prefetch_tokens_occupied += len(prefetch_key)
            if self.enable_ready_horizon:
                # M1/M5: classify the issue -- wake re-issues are demand
                # restores, everything else (entry issues, paced retries)
                # is speculative staging -- and record its budget charge.
                self.reserve_prefetch(
                    req_id,
                    len(prefetch_key),
                    PrefetchKind.DEMAND if demand_restore else PrefetchKind.SPECULATIVE,
                )
        return "issued"
```


### `UnifiedRadixCache._handle_prefetch_result` — `python/sglang/srt/mem_cache/unified_radix_cache.py:6049-6287` (239 lines)

```python
    def _handle_prefetch_result(self, operation: PrefetchOperation) -> None:
        # This function **owns**:
        # - host_indices[0 : completed_tokens]
        # - sidecar pool hits if operation.pool_transfers_done is true
        #
        # That is, when this function returns the host memory referenced must be inserted
        # into the radix tree or released to pool.
        logger.info("[P2A] ts_ms=%d evt=prefetch_finalize rid=%s completed_tokens=%d mode=%s", int(time.time() * 1000), operation.request_id, int(operation.completed_tokens or 0), self.host_memory_mode)
        try:
            _t38c_log({"evt": "pc_l3_host",
                       "rid": operation.request_id,
                       "completed_tokens": int(operation.completed_tokens or 0),
                       "requested_tokens": int(getattr(operation, "stats_requested_tokens", 0) or 0)})
        except Exception:
            pass

        req_id = operation.request_id
        completed_tokens = operation.completed_tokens
        hash_value = operation.hash_value
        sidecar_counts = self._host_alloc_hybrid_sidecar_counts(operation)

        (
            last_host_node_id,
            prefetch_key,
            host_indices,
            _,
            anchor_lock_params,
            comp_xfers,
            anchor_last_hash,
        ) = self.ongoing_prefetch[req_id]

        # All PP/TP ranks will get the same `min_completed_tokens`, because `completed_tokens`
        # and `pool_hits` in their operations are same.  No need to sync cross-rank here.
        anchor_still_valid = (
            self.buffer_pipeline is not None
            or self._prefetch_anchor_is_valid(last_host_node_id, anchor_last_hash)
        )
        if not anchor_still_valid or not self._check_hybrid_prefetch_result(
            req_id,
            operation,
            completed_tokens,
            hash_value,
            host_indices,
            last_host_node_id,
            anchor_lock_params,
            prefetch_key,
        ):
            if not anchor_still_valid:
                return self._discard_prefetch_stale_anchor(
                    operation=operation,
                    req_id=req_id,
                    completed_tokens=completed_tokens,
                    prefetch_key=prefetch_key,
                    host_indices=host_indices,
                    comp_xfers=comp_xfers,
                    anchor_node_id=last_host_node_id,
                    anchor_lock_params=anchor_lock_params,
                    sidecar_counts=sidecar_counts,
                )
            _log_host_alloc_telemetry(
                "restore_hybrid_finalize",
                rid=req_id,
                attempt_id=getattr(operation, "host_alloc_attempt_id", None),
                cache_instance_id=getattr(self, "_host_allocability_instance_id", 0),
                trace_context=getattr(operation, "trace_context", None),
                kv_expected=int(len(hash_value) * self.page_size),
                kv_fetched=int(completed_tokens),
                sidecars=sidecar_counts,
                per_sidecar=sidecar_counts,
                all_or_nothing=self._host_alloc_hybrid_is_all_or_nothing(operation),
                result="discarded",
                # The terminal handoff remains "finalized" so the scheduler
                # can consume the authoritative discarded completion and
                # release the request to recompute without entering READY.
                restore_state_after="NONE",
                **_host_alloc_join_fields(req_id),
            )
            self.record_storage_prefetch_completion(
                req_id,
                self._host_alloc_hybrid_completion(
                    operation, completed_tokens, "discarded", sidecar_counts
                ),
                getattr(operation, "prefetch_attempt_id", None),
            )
            # Hybrid all-or-nothing check failed; result already discarded.
            _log_restore_disposition(
                req_id,
                "RECOMPUTE",
                operation.stats_requested_tokens or 0,
                completed_tokens,
                "hybrid_discard",
            )
            return

        _log_host_alloc_telemetry(
            "restore_hybrid_finalize",
            rid=req_id,
            attempt_id=getattr(operation, "host_alloc_attempt_id", None),
            cache_instance_id=getattr(self, "_host_allocability_instance_id", 0),
            trace_context=getattr(operation, "trace_context", None),
            kv_expected=int(len(hash_value) * self.page_size),
            kv_fetched=int(completed_tokens),
            sidecars=sidecar_counts,
            per_sidecar=sidecar_counts,
            all_or_nothing=self._host_alloc_hybrid_is_all_or_nothing(operation),
            result="accepted",
            restore_state_after="READY",
            **_host_alloc_join_fields(req_id),
            attempt_number=1 if getattr(operation, "host_alloc_attempt_id", None) else 0,
            attempt_origin=(
                "HOST_ALLOC_WAKE"
                if getattr(operation, "host_alloc_attempt_id", None)
                else "HOST_ALLOC_INITIAL"
            ),
        )
        self.record_storage_prefetch_completion(
            req_id,
            self._host_alloc_hybrid_completion(
                operation, completed_tokens, "accepted", sidecar_counts
            ),
            getattr(operation, "prefetch_attempt_id", None),
        )

        requested = operation.stats_requested_tokens or 0
        if completed_tokens <= 0:
            disposition, disposition_reason = "RECOMPUTE", "miss"
        elif completed_tokens < requested:
            disposition, disposition_reason = "PARTIAL", "shortfall"
        else:
            disposition, disposition_reason = "RESTORE", "full"
        _log_restore_disposition(
            req_id, disposition, requested, completed_tokens, disposition_reason
        )

        if self.buffer_pipeline is not None:
            # No graft: release the rank-local tail beyond the synced usable
            # length, then park the bounce for admission-time consumption.
            self.record_storage_prefetch_terminal(
                req_id, "finalized", getattr(operation, "prefetch_attempt_id", None)
            )
            return self.buffer_pipeline.stage_completed_prefetch(
                req_id, completed_tokens, hash_value
            )

        # Commit boundary: this runs on the scheduler thread inside the ACK
        # drain, so no tree mutation can interleave between the identity
        # check and the graft. An anchor that was evicted (or whose id was
        # reused) discards this outcome instead of grafting under a foreign
        # prefix; the request then re-matches and schedules normally.
        if not self._prefetch_anchor_is_valid(last_host_node_id, anchor_last_hash):
            return self._discard_prefetch_stale_anchor(
                operation=operation,
                req_id=req_id,
                completed_tokens=completed_tokens,
                prefetch_key=prefetch_key,
                host_indices=host_indices,
                comp_xfers=comp_xfers,
                anchor_node_id=last_host_node_id,
                anchor_lock_params=anchor_lock_params,
                sidecar_counts=sidecar_counts,
            )

        fetched_key = prefetch_key[:completed_tokens]
        insert_result = self.tree_core.insert_host(
            last_host_node_id,
            fetched_key,
            host_indices[:completed_tokens],
            hash_value[: completed_tokens // self.page_size],
        )

        # Apply the host-insert walk's actions before the transfer commit.
        self._apply_cache_actions(insert_result.cache_actions)

        if insert_result.host_insert_dropped:
            self.cache_controller.append_host_mem_release(
                host_indices=host_indices[:completed_tokens],
                extra_pools=[x for xfers in comp_xfers.values() for x in xfers],
            )
            loaded_from_storage = 0
        else:
            commit_actions: list[CacheAction | ComponentAction] = []
            self.tree_core.commit_hicache_transfers(
                last_host_node_id,
                CacheTransferPhase.PREFETCH,
                comp_xfers,
                cache_actions=commit_actions,
                insert_result=insert_result,
                pool_storage_result=operation.pool_storage_result,
            )
            self._apply_cache_actions(commit_actions)
            # The commit emits via commit_actions only; the walk's were applied above.
            assert not insert_result.cache_actions

            # The restored span's KV is confirmed in L3 -- it was just read
            # from there -- so mark the inserted node durable like a
            # written+acked chain. Without this a restored chain never
            # qualifies for the hollow fallback or the prefetch gates
            # (P2-1 e14: the K=32 evict deadlock). A shortfall inserted
            # exactly prefetch_key[:completed_tokens], so the inserted node
            # spans precisely the durable range.
            if insert_result.inserted_host_node is not None:
                self.tree_core.mark_storage_restored(
                    insert_result.inserted_host_node
                )

            released = self.cache_controller.mem_pool_host.free(
                host_indices[: insert_result.prefix_len]
            )
            self._bump_host_allocability(
                PoolName.KV.value,
                "direct_free",
                int(released or insert_result.prefix_len),
                causal_rid=req_id,
                trace_context=getattr(operation, "trace_context", None),
            )
            loaded_from_storage = completed_tokens - insert_result.prefix_len

        self.dec_host_lock_ref(last_host_node_id, anchor_lock_params)
        self.release_prefetch(req_id, "finalize")
        del self.ongoing_prefetch[req_id]
        self._demand_restore_rids.discard(req_id)
        self.cache_controller.prefetch_tokens_occupied -= len(prefetch_key)
        self.record_storage_prefetch_terminal(
            req_id, "finalized", getattr(operation, "prefetch_attempt_id", None)
        )

        self.prefetch_loaded_tokens_by_reqid[req_id] = loaded_from_storage
        logger.info(
            "HiCache prefetch %s req=%s completed=%d matched=%d loaded=%d occupied=%d",
            "dropped" if insert_result.host_insert_dropped else "success",
            req_id,
            completed_tokens,
            insert_result.prefix_len,
            loaded_from_storage,
            self.cache_controller.prefetch_tokens_occupied,
        )
        if self.enable_storage_metrics and self.storage_metrics_collector is not None:
            self.storage_metrics_collector.log_prefetched_tokens(loaded_from_storage)
        return
```


### `UnifiedRadixCache._check_hybrid_prefetch_result` — `python/sglang/srt/mem_cache/unified_radix_cache.py:6521-6640` (120 lines)

```python
    def _check_hybrid_prefetch_result(
        self,
        req_id: str,
        operation: PrefetchOperation,
        completed_tokens: int,
        hash_value: list[str],
        host_indices: torch.Tensor,
        last_host_node_id: NodeId,
        anchor_lock_params: DecLockRefParams,
        prefetch_key: RadixKey,
    ) -> bool:
        """Decide the length of usable prefix.

        Two strategies depending on the hybrid layout:

        * DSA-style (Full attention + KV-derived ALL_PAGES sidecar such as the
          DSA / MiniMax indexer): *clamp* to the minimum fetched prefix shared by
          the Full KV pool and every sidecar. A partial prefix is still usable
          because the sidecar is page-aligned with KV and required for every page.
        * Everything else (SWA / Mamba components, mixed DeepSeekV4 stacks):
          *all-or-nothing*. Their pools only cover a window / tail and cannot be
          truncated page by page, so any shortfall discards the whole prefetch.

        Returns true if prefetch success, or false when an all-or-nothing prefetch
        was discarded (the caller should then treat the prefetch as finished).
        """
        # Sync completed tokens and per-pool hit pages across ATTN groups, taking
        # the minimum so every rank agrees on the same usable prefix length.
        #
        # Skip KV-derived pools, which do not report hits in operation.pool_storage_result.
        # Their hit lengths are stored in completed_tokens.
        pool_transfers = [
            transfer
            for transfer in getattr(operation, "pool_transfers", None) or []
            if getattr(transfer, "indices_from_pool", None) != PoolName.KV
        ]
        hit_pages = (
            getattr(
                getattr(operation, "pool_storage_result", None),
                "extra_pool_hit_pages",
                {},
            )
            if pool_transfers
            else {}
        )
        try:
            pool_hit_pages = [
                hit_pages.get(getattr(t, "name", None), 0)
                for t in pool_transfers
            ]
        except (AttributeError, TypeError):
            pool_hit_pages = [0 for _ in pool_transfers]
        completed_tokens = operation.completed_tokens
        # If its anchor vanished, no hybrid host insertion can be committed;
        # defer to the caller's stale-anchor cleanup, which owns all staging.
        if self.buffer_pipeline is None and not self._prefetch_anchor_is_valid(
            last_host_node_id, self.ongoing_prefetch[req_id].anchor_last_hash
        ):
            return True
        # Hybrid cache state is all-or-nothing: every extra pool (SWA / Mamba / ...)
        # must cover the same fetched prefix. If any pool falls short the whole
        # prefetch result is unusable, so discard it and release everything.
        expected_tokens = len(hash_value) * self.page_size
        all_succeeded = completed_tokens == expected_tokens and all(
            getattr(transfer, "keys", None) is not None
            and count == len(getattr(transfer, "keys"))
            for transfer, count in zip(pool_transfers, pool_hit_pages)
        )
        if pool_transfers and not all_succeeded:
            # Drop the KV beliefs from the first page any pool failed to serve;
            # the next insert then re-writes that span through one FULL check,
            # restoring the missing aux pages.
            keep_pages = completed_tokens // self.page_size
            for transfer, count in zip(pool_transfers, pool_hit_pages):
                keys = getattr(transfer, "keys", None)
                if keys is None:
                    keep_pages = 0
                elif count < len(keys):
                    # Aux transfers key the chain's trailing pages.
                    keep_pages = min(
                        keep_pages, max(0, len(hash_value) - len(keys))
                    )
            self.storage_existence_cache.invalidate_beyond(
                PoolName.KV, hash_value, keep_pages=keep_pages
            )
            # The controller's prefetch IO thread already releases the untransferred
            # tail (host_indices[completed_tokens:])
            self.cache_controller.append_host_mem_release(
                host_indices=host_indices[:completed_tokens],
                extra_pools=(
                    pool_transfers
                    if getattr(operation, "pool_transfers_done", False)
                    else None
                ),
            )
            if anchor_lock_params is not None:
                self.dec_host_lock_ref(last_host_node_id, anchor_lock_params)
            if self.buffer_pipeline is not None:
                self.buffer_pipeline.pop_prefix_ctx(req_id)
                self.buffer_pipeline.release_anchor_lock(req_id)
            self.release_prefetch(req_id, "hybrid_discard")
            del self.ongoing_prefetch[req_id]
            self._demand_restore_rids.discard(req_id)
            self.cache_controller.prefetch_tokens_occupied -= (
                self._prefetch_occupied_span(prefetch_key, host_indices)
            )
            self.prefetch_loaded_tokens_by_reqid[req_id] = 0
            self.record_storage_prefetch_terminal(
                req_id, "finalized", getattr(operation, "prefetch_attempt_id", None)
            )
            logger.warning(
                "HiCache hybrid prefetch discarded req=%s completed=%d requested=%d "
                "kv_beliefs_kept_pages=%d",
                req_id,
                completed_tokens,
                expected_tokens,
                keep_pages,
            )
            return False
        return True
```


### `UnifiedRadixCache.register_frontier_waiter` — `python/sglang/srt/mem_cache/unified_radix_cache.py:6670-6695` (26 lines)

```python
    def register_frontier_waiter(self, req_id: str, node_id: NodeId) -> None:
        """Record a frontier wait for req_id keyed by its anchor node (the
        scheduler's gate else-branch, design T5), and request that node's
        chain persistence (write_back only writes L3 on eviction, so the
        wait itself must advance the frontier). Re-registration overwrites
        the previous key: arrival retries are idempotent. The wait ends when
        the node's L3 write ack promotes it to storage_persisted
        (_wake_frontier_waiters), when the per-pass frontier predicate passes,
        or on cleanup (discard_frontier_waiter)."""
        for existing, waiters in self._storage_frontier_waiters.items():
            if req_id in waiters:
                waiters.discard(req_id)
                if not waiters:
                    del self._storage_frontier_waiters[existing]
                break
        self._storage_frontier_waiters.setdefault(node_id, set()).add(req_id)
        # A re-registered waiter is no longer pending wakeup.
        self._storage_frontier_ready.discard(req_id)
        # The wait itself advances the storage frontier: write_back only
        # writes L3 on eviction, so without this the anchor chain would
        # never reach storage_persisted and the wait would sleep until the
        # T13 timeout (the 42ms-gap wake=0 bug). The gap fill dedupes by
        # is_backuped / is_storage_written; a deleted anchor is skipped
        # (its waiter self-heals through the re-match predicate).
        if self.tree_core.node_exists(node_id):
            self.write_backup_storage(node_id)
```


### `UnifiedRadixCache._wake_frontier_waiters` — `python/sglang/srt/mem_cache/unified_radix_cache.py:6720-6742` (23 lines)

```python
    def _wake_frontier_waiters(self, node_id: NodeId) -> None:
        """Move the waiters of a freshly durable node into the ready set
        (called after advance_storage_persisted in the ack drain; the
        predicate accepts restored chains too, P2-1 e14). Set membership
        only -- zero queue consumption, zero callbacks, zero write path --
        so the F2 exactly-once ack semantics are untouched. Stale or
        un-durable nodes are skipped, never dereferenced."""
        waiters = self._storage_frontier_waiters.get(node_id)
        if not waiters:
            return
        if not self.tree_core.node_exists(node_id):
            return
        if not self.tree_core.is_l3_durable(node_id):
            return
        self._storage_frontier_ready.update(waiters)
        del self._storage_frontier_waiters[node_id]
        for req_id in waiters:
            logger.info(
                "[P2A] ts_ms=%d evt=frontier_wake rid=%s node=%s",
                int(time.time() * 1000),
                req_id,
                node_id,
            )
```


### `UnifiedRadixCache.has_restore_potential` — `python/sglang/srt/mem_cache/unified_radix_cache.py:6756-6795` (40 lines)

```python
    def has_restore_potential(
        self,
        req_id: str,
        anchor_node_id: NodeId,
        host_hit_length: int,
        prompt_len: Optional[int] = None,
    ) -> bool:
        """P2-1 M1b (T6): whether a quota-denied request has recoverable
        restore material (design §2.5-1): host material, an in-flight or
        registered restore intent, or an L3-queryable anchor chain. A prompt
        too short to ever qualify for a storage prefetch has no restore
        intent (declined_too_short is terminal for it).

        too_short churn (independent P): the never-case gate applies even
        when host material is present. When BOTH the current restore suffix
        and the theoretical-max suffix are below the prefetch threshold (a
        can-never-qualify prompt), no storage prefetch can ever be granted,
        so parking WAIT[DEVICE_QUOTA] would only re-issue an inevitably
        declined_too_short prefetch on every capacity wake (the tight
        wake -> re-issue -> declined -> re-WAIT loop). Host material alone
        no longer wins there -- the request recomputes its tail directly.
        The device-match-decay REVALIDATE bet is preserved: a prompt whose
        max suffix still reaches the threshold (prompt_can_qualify True)
        keeps its restore potential, because its current sub-threshold
        suffix may grow back above threshold once the device match decays."""
        if prompt_len is not None and not self.prompt_can_qualify_for_prefetch(
            prompt_len, host_hit_length
        ):
            return False
        if host_hit_length > 0:
            return True
        if req_id in self.ongoing_prefetch or req_id in self._storage_prefetch_missed_rids:
            return True
        if not self.tree_core.node_exists(anchor_node_id):
            return False
        return (
            self.tree_core.is_backuped(anchor_node_id)
            or self.tree_core.is_root(anchor_node_id)
            or self.tree_core.is_l3_durable(anchor_node_id)
        )
```


### `UnifiedRadixCache._drain_storage_control_queues_impl` — `python/sglang/srt/mem_cache/unified_radix_cache.py:7277-8063` (787 lines)

```python
    def _drain_storage_control_queues_impl(
        self,
        n_storage_hit: Optional[int],
        n_ack_prefetch: Optional[int],
        n_backup: Optional[int],
        n_release: Optional[int],
        extra_release_counts: Optional[dict[PoolName, int]],
        log_metrics: bool,
        aggregate_rank_acks: bool = True,
    ) -> None:
        cc = self.cache_controller

        def _drain_queue(q: Queue[T], n: Optional[int]) -> Iterator[T]:
            """If n is None, consume all items from the queue.
            Otherwise, consume n items from the queue.  Blocking if there are no enough n items.

            In TP, each rank consumes the a minimal number of items of all ranks.
            In PP, each rank consumes the exact number of items of PP0.  Refer to _pp_sync for more details.

            This prevents TP/PP divergence.
            """
            if n is None:
                while not q.empty():
                    item = q.get()
                    yield item
            else:
                for _ in range(n):
                    # Block when there are not enough elements.
                    # All TP/PP ranks must consume the same number of elements.
                    item = q.get()
                    yield item

        buffer_mode = self.host_memory_mode == "buffer_only"

        def _try_alloc_storage_hit(operation) -> bool:
            """Allocate the hit-sized bounce and launch the transfer.
            Returns False when staging pressure defers the allocation
            (buffer mode parks and retries; cache mode revokes)."""
            req_id = operation.request_id
            info = self.ongoing_prefetch.get(req_id)
            if info is None:
                return True  # aborted/cleaned; nothing to retry
            if operation.is_terminated():
                self.revoke_pending_prefetch(req_id)
                return True

            if buffer_mode and cc.prefetch_rate_limited():
                # Pool is load-saturated: hold the KNOWN hit until staged
                # prefetches ahead of us are consumed. The op stays in
                # ongoing_prefetch, so wait_complete keeps gating admission.
                return False
            alloc_len = operation.storage_hit_count
            telemetry_snapshot = None
            snapshot_fn = getattr(self, "host_allocability_snapshot", None)
            if snapshot_fn is not None:
                pool_names = [PoolName.KV.value]
                pool_names.extend(
                    getattr(transfer.name, "value", transfer.name)
                    for transfer in getattr(operation, "pool_transfers", None) or []
                    if transfer.indices_from_pool is None
                )
                telemetry_snapshot = snapshot_fn(pool_names)
            alloc1_started_ns = time.monotonic_ns()
            host_indices = cc.mem_pool_host.alloc(alloc_len)
            alloc1_ns = time.monotonic_ns() - alloc1_started_ns
            alloc1_succeeded = host_indices is not None
            reclaimed_units = 0
            reclaim_ns = 0
            alloc2_ns = 0
            drain_ns = 0
            crop_ns = 0
            alloc2_succeeded = False
            granted_len = alloc_len
            if host_indices is None:
                # P3 M2: speculative staging eats free/soft-reserved host
                # headroom only -- an alloc failure declines it silently,
                # never forcing host eviction (staging must not push a
                # warm chain out of Host). Demand restores, and the
                # Ready-Horizon-off baseline (no reservation), still evict.
                reservation = self._prefetch_reservations.get(req_id)
                if reservation is None or reservation.kind is PrefetchKind.DEMAND:
                    reclaim_context = {
                        "rid": req_id,
                        "attempt_id": getattr(operation, "host_alloc_attempt_id", None),
                        "allocation": "prefetch_staging",
                        "pool": PoolName.KV.value,
                        "requested": int(alloc_len),
                    }
                    previous_context = getattr(self.tree_core, "_host_reclaim_context", None)
                    self.tree_core._host_reclaim_context = reclaim_context
                    reclaim_started_ns = time.monotonic_ns()
                    try:
                        reclaimed_units = int(self.evict_host(alloc_len) or 0)
                    finally:
                        reclaim_ns += time.monotonic_ns() - reclaim_started_ns
                        self.tree_core._host_reclaim_context = previous_context
                    alloc2_started_ns = time.monotonic_ns()
                    host_indices = cc.mem_pool_host.alloc(alloc_len)
                    alloc2_ns += time.monotonic_ns() - alloc2_started_ns
                    alloc2_succeeded = host_indices is not None
                if host_indices is None:
                    # F1 symmetry with _execute_kv_backup: a finished L3 write
                    # keeps its host slots pinned (host_lock_ref) until its ack
                    # is consumed, so one drain + retry can still free capacity
                    # before the staging request is given up.
                    drain_started_ns = time.monotonic_ns()
                    reclaimed_units += self._drain_acks_and_reclaim_host(
                        alloc_len - reclaimed_units
                    )
                    drain_ns += time.monotonic_ns() - drain_started_ns
                    alloc2_started_ns = time.monotonic_ns()
                    host_indices = cc.mem_pool_host.alloc(alloc_len)
                    alloc2_ns += time.monotonic_ns() - alloc2_started_ns
                    alloc2_succeeded = host_indices is not None
                if host_indices is None:
                    # Capacity crop: stage the prefix that fits instead of
                    # revoking the whole validated hit (r60 C-8: 525 demand
                    # staging failures requested 3.8-13.8 K tokens against a
                    # pool whose only free units were 0.2-0.9 K, so every one
                    # of them was revoked and recomputed).
                    # _storage_hit_crop_is_safe keeps a TRAILING_PAGES
                    # frontier un-cropped, which is why the predicate exists.
                    free_now = int(cc.mem_pool_host.available_size())
                    crop_len = _staging_crop_length(
                        operation, alloc_len, free_now, self.page_size
                    )
                    if crop_len:
                        crop_started_ns = time.monotonic_ns()
                        host_indices = cc.mem_pool_host.alloc(crop_len)
                        crop_ns += time.monotonic_ns() - crop_started_ns
                        if host_indices is not None:
                            granted_len = crop_len
                            _log_restore_disposition(
                                req_id, "PARTIAL", alloc_len, crop_len,
                                "cropped_to_staging",
                            )
            operation._host_alloc_retry_details = {
                "snapshot": telemetry_snapshot,
                "required": alloc_len,
                "alloc1": alloc1_succeeded,
                "reclaimed": reclaimed_units,
                "alloc2": alloc2_succeeded,
                "crop_granted": granted_len if granted_len != alloc_len else 0,
                "alloc1_ns": int(alloc1_ns),
                "reclaim_ns": int(reclaim_ns),
                "drain_ns": int(drain_ns),
                "alloc2_ns": int(alloc2_ns),
                "crop_ns": int(crop_ns),
            }
            if host_indices is None:
                if buffer_mode:
                    return False
                self.revoke_pending_prefetch(req_id, alloc_failed=True)
                return True

            operation.storage_hit_count = granted_len
            operation.hash_value = operation.hash_value[: granted_len // self.page_size]
            operation.host_indices = host_indices
            self.ongoing_prefetch[req_id] = info._replace(host_indices=host_indices)
            if buffer_mode:
                cc.prefetch_tokens_occupied += granted_len
                # IO commit: pin the anchor until consumption. Do not read
                # attributes off `operation` here — alternative cache
                # controllers may expose a narrower surface.
                self.buffer_pipeline.try_lock_anchor(req_id, info.anchor_node_id)
            cc.prefetch_buffer.put(operation)
            return True

        def _drain_and_alloc_storage_hit():
            # Parked hits first (FIFO fairness with retries; buffer only).
            if buffer_mode:
                parked = self.buffer_pipeline.pending_hit_allocs
                while parked:
                    if not _try_alloc_storage_hit(parked[0]):
                        break
                    parked.popleft()
            for operation in _drain_queue(cc.prefetch_hit_queue, n_storage_hit):
                req_id = operation.request_id
                info = self.ongoing_prefetch.get(req_id)
                if info is None:
                    # Request already aborted/cleaned up; still flush the
                    # query's absent-hash feedback.
                    self._invalidate_absent_from_hit_query(operation)
                    continue
                if operation.is_terminated():
                    # Controller-side miss termination (retryable) or an abort
                    # race (abort cleanup discards the marker).
                    self._storage_prefetch_missed_rids.add(req_id)
                    self.revoke_pending_prefetch(req_id)
                    try:
                        _t38c_log({"evt": "pc_outcome", "phase": "drain", "rid": req_id,
                                   "outcome": "terminated_revoke",
                                   "counters": dict(self._prefetch_outcome_stats)})
                    except Exception:
                        pass
                    continue
                if operation.storage_hit_count < self.prefetch_threshold:
                    # Below-threshold hit: classify + feed the L3 miss
                    # accounting, then revoke (not enough benefit).
                    self._account_prefetch_outcome(operation, revoked=True)
                    try:
                        _t38c_log({"evt": "pc_outcome", "phase": "drain", "rid": req_id,
                                   "outcome": ("revoked_insufficient" if operation.storage_hit_count > 0
                                               else "revoked_full_miss"),
                                   "storage_hit_count": int(operation.storage_hit_count),
                                   "requested_tokens": int(getattr(operation, "stats_requested_tokens", 0) or 0),
                                   "counters": dict(self._prefetch_outcome_stats)})
                    except Exception:
                        pass
                    self._storage_prefetch_missed_rids.add(req_id)
                    self.revoke_pending_prefetch(req_id)
                    continue
                self._invalidate_absent_from_hit_query(operation)
                self._account_prefetch_outcome(operation, revoked=False)
                if self._backup_park_applies(info.anchor_node_id, operation):
                    # Partial hit at or above the threshold with the chain's
                    # backup pipeline targeted to cover the request's end
                    # while the durable frontier is still behind it: park
                    # on the T15 wait instead of restoring the partial
                    # span. Each partial restore was denied at admission
                    # while the device stayed full, re-issuing the lookup
                    # per pass (the e13 retry loop); the backup-completion
                    # wake re-looks-up once and restores the full chain.
                    self._storage_prefetch_missed_rids.add(req_id)
                    self.revoke_pending_prefetch(req_id)
                    continue
                if not _try_alloc_storage_hit(operation):
                    # Counted once at first parking, not per retry tick.
                    self._prefetch_outcome_stats["declined_rate_limited"] += 1
                    try:
                        _t38c_log({"evt": "pc_outcome", "phase": "drain", "rid": req_id,
                                   "outcome": "declined_rate_limited", "site": "drain",
                                   "counters": dict(self._prefetch_outcome_stats)})
                    except Exception:
                        pass
                    self.buffer_pipeline.pending_hit_allocs.append(operation)

        def _drain_ack_prefetch():
            for ack in _drain_queue(cc.ack_prefetch_queue, n_ack_prefetch):
                operation = ack.operation
                if ack.completed_tokens is not None:
                    if operation.request_id in self.ongoing_prefetch:
                        assert operation.completed_tokens <= ack.completed_tokens
                        operation.completed_tokens = ack.completed_tokens
                if ack.pool_hits is not None:
                    if operation.request_id in self.ongoing_prefetch:
                        operation.pool_storage_result.update_extra_pool_hit_pages(
                            ack.pool_hits
                        )
                        operation.pool_transfers_done = True
                if ack.completed_req:
                    logger.info("[P2A] ts_ms=%d evt=prefetch_io_done rid=%s completed=%s", int(time.time() * 1000), operation.request_id, ack.completed_tokens)
                    if operation.request_id in self.ongoing_prefetch:
                        # check_prefetch_progress() is not called for this rid yet.
                        # Let us insert the prefetch result into the radix tree.
                        self._handle_prefetch_result(operation)
                    cc.append_host_mem_release(
                        operation.host_indices[operation.completed_tokens :],
                        (
                            getattr(operation, "pool_transfers", None)
                            if not getattr(operation, "pool_transfers_done", False)
                            else None
                        ),
                        trace_context=getattr(operation, "trace_context", None),
                    )

        def _drain_backup():
            drained = 0
            for operation in _drain_queue(cc.ack_backup_queue, n_backup):
                drained += 1
                _ack_node_id = getattr(operation, "node_id", None)
                _ack_transfers = getattr(operation, "pool_transfers", None) or []
                _ack_mamba_transfers = [
                    transfer
                    for transfer in _ack_transfers
                    if transfer.name == PoolName.MAMBA
                ]
                _ack_mamba_keys = [
                    key
                    for transfer in _ack_mamba_transfers
                    for key in (transfer.keys or [])
                ]
                _ack_mamba_key_set_digest, _ack_mamba_key_count = (
                    ordered_key_set_digest(_ack_mamba_keys)
                )
                _ack_mamba_expected_pages = _ack_mamba_key_count
                _ack_mamba_succeeded_pages = (
                    operation.pool_storage_result.extra_pool_hit_pages.get(
                        PoolName.MAMBA,
                        operation.pool_storage_result.extra_pool_hit_pages.get(
                            PoolName.MAMBA.value, 0
                        ),
                    )
                )
                _ack_mamba_local_durable = (
                    _ack_mamba_key_count > 0
                    and _ack_mamba_succeeded_pages == _ack_mamba_expected_pages
                )
                _ack_final_kv_hash = (
                    operation.hash_value[-1] if operation.hash_value else ""
                )
                (
                    _ack_expected_rank_set,
                    _ack_observed_rank_set,
                    _ack_rank_set_unavailable,
                    _ack_mamba_all_rank_durable,
                ) = self._t38c_mamba_rank_proof(
                    operation,
                    node_id=_ack_node_id,
                    final_kv_hash=_ack_final_kv_hash,
                    key_set_digest=_ack_mamba_key_set_digest,
                    key_count=_ack_mamba_key_count,
                    local_mamba_durable=_ack_mamba_local_durable,
                    aggregate_rank_acks=aggregate_rank_acks,
                )
                _t38c_durable_log(
                    {
                        "evt": "backup_ack_drain",
                        "trace_context": getattr(
                            operation, "trace_context", None
                        ),
                        "operation_id": operation.id,
                        "attempt_id": f"storage-{operation.id}",
                        "node_id": str(_ack_node_id)
                        if _ack_node_id is not None
                        else "",
                        "final_kv_hash": (
                            operation.hash_value[-1]
                            if operation.hash_value
                            else ""
                        ),
                        "kv_transfer": bool(operation.hash_value),
                        "mamba_transfer": any(
                            transfer.name == PoolName.MAMBA
                            for transfer in _ack_transfers
                        ),
                        "kv_durable": operation.completed_tokens
                        >= len(operation.host_indices),
                        "mamba_durable": _ack_mamba_local_durable,
                        "mamba_all_rank_durable": _ack_mamba_all_rank_durable,
                        "mamba_expected_pages": _ack_mamba_expected_pages,
                        "mamba_succeeded_pages": _ack_mamba_succeeded_pages,
                        "mamba_key_count": _ack_mamba_key_count,
                        "mamba_key_set_digest": _ack_mamba_key_set_digest,
                        "expected_rank_set": _ack_expected_rank_set,
                        "observed_ack_rank_set": _ack_observed_rank_set,
                        "observed_ack_rank_count": len(_ack_observed_rank_set),
                        "rank_set_unavailable": _ack_rank_set_unavailable,
                        "operation": operation.id,
                        "attempt": getattr(
                            operation, "trace_id", f"storage-{operation.id}"
                        ),
                        "completed_tokens": int(operation.completed_tokens),
                        "requested_tokens": int(
                            len(operation.host_indices)
                            if operation.host_indices is not None
                            else 0
                        ),
                        "result": "complete"
                        if operation.host_indices is not None
                        and operation.completed_tokens >= len(operation.host_indices)
                        else "partial",
                    }
                )
                if buffer_mode:
                    # Storage write acked: free the staging.
                    self.buffer_pipeline.finish_storage_write_ack(operation.id)
                else:
                    entry = self.ongoing_backup.pop(operation.id, None)
                    if entry is not None:
                        node_id, lock_params = entry
                        self.dec_host_lock_ref(node_id, lock_params)
                        # [P3] restore_backup: the storage write ACK'd for
                        # this node. Frontier attribution for the NEVER/
                        # PARTIAL/FULL_THEN_LOST differential: requested =
                        # this operation's span; durable = the persisted
                        # frontier after the ack (0 if this op was partial
                        # -- then the node is not promoted below).
                        _log_restore_backup(
                            operation,
                            node_id,
                            durable_frontier=(
                                operation.completed_tokens
                                if operation.completed_tokens
                                >= len(operation.host_indices)
                                else 0
                            ),
                            requested_frontier=len(operation.host_indices),
                        )
                        if operation.completed_tokens >= len(
                            operation.host_indices
                        ):
                            mamba_transfers = _ack_mamba_transfers
                            mamba_expected_pages = _ack_mamba_expected_pages
                            mamba_succeeded_pages = _ack_mamba_succeeded_pages
                            mamba_key_set_digest = _ack_mamba_key_set_digest
                            mamba_key_count = _ack_mamba_key_count
                            expected_rank_set = _ack_expected_rank_set
                            attempt_id = getattr(
                                operation, "trace_id", f"storage-{operation.id}"
                            )
                            operation_context = getattr(
                                operation, "trace_context", None
                            )
                            final_kv_hash = (
                                operation.hash_value[-1]
                                if operation.hash_value
                                else ""
                            )
                            candidate_context = (
                                dict(operation_context) if operation_context else None
                            )
                            if candidate_context is not None:
                                candidate_context.setdefault("node_id", str(node_id))
                                candidate_context.setdefault(
                                    "final_kv_hash", final_kv_hash
                                )
                            attempt_key = (
                                str(node_id),
                                str(operation.id),
                                str(attempt_id),
                            )
                            candidate = {
                                "operation_id": operation.id,
                                "attempt_id": attempt_id,
                                "trace_context": candidate_context,
                                "node_id": str(node_id),
                                "final_kv_hash": final_kv_hash,
                                "kv_durable": True,
                                "kv_completed_tokens": int(
                                    operation.completed_tokens
                                ),
                                "kv_requested_tokens": int(
                                    len(operation.host_indices)
                                ),
                                "mamba_durable": _ack_mamba_all_rank_durable,
                                "mamba_expected_pages": mamba_expected_pages,
                                "mamba_succeeded_pages": mamba_succeeded_pages,
                                "mamba_key_count": mamba_key_count,
                                "mamba_key_set_digest": mamba_key_set_digest,
                                "expected_rank_set": expected_rank_set,
                                "observed_ack_rank_set": _ack_observed_rank_set,
                                "observed_ack_rank_count": len(
                                    _ack_observed_rank_set
                                ),
                                "rank_set_unavailable": _ack_rank_set_unavailable,
                                "tree_write_generation": getattr(
                                    operation, "_t38c_tree_write_generation", None
                                ),
                            }
                            # Keep every outstanding attempt. Promotion must
                            # select from this node-owned set, never a mutable
                            # per-node "current" pointer.
                            node_evidence = self._t38c_durability_evidence.setdefault(
                                str(node_id), {}
                            )
                            node_evidence[attempt_key] = candidate
                            # The write is durable: promote the node to a
                            # persisted anchor when its parent chain is.
                            # Promoted is every node that became persisted
                            # here, including descendants acked before
                            # their parent chain (retroactive promotion).
                            promoted = self.tree_core.advance_storage_persisted(
                                node_id
                            )
                            for promoted_id in promoted:
                                promoted_node = self.tree_core.node_by_id(promoted_id)
                                promoted_attempt_key, promoted_evidence = (
                                    self._t38c_select_promoted_candidate(
                                        promoted_id,
                                        promoted_node.get_last_hash_value() or "",
                                    )
                                )
                                promoted_context = (
                                    promoted_evidence.get("trace_context")
                                    if promoted_evidence is not None
                                    else None
                                )
                                context_complete = complete_trace_context(
                                    promoted_context,
                                    promoted_id,
                                    promoted_node.get_last_hash_value() or "",
                                )
                                _t38c_durable_log(
                                    {
                                        "evt": "storage_persisted",
                                        "trace_context": promoted_context,
                                        "operation_id": (
                                            promoted_evidence.get("operation_id")
                                            if promoted_evidence
                                            else None
                                        ),
                                        "attempt_id": (
                                            promoted_evidence.get("attempt_id")
                                            if promoted_evidence
                                            else None
                                        ),
                                        "node_id": str(promoted_id),
                                        "anchor_id": str(node_id),
                                        "final_kv_hash": (
                                            promoted_node.get_last_hash_value() or ""
                                        ),
                                        "frontier_end": len(
                                            promoted_node.hash_value or []
                                        )
                                        * self.page_size,
                                        "storage_version": self.tree_core.anchor_storage_version(
                                            promoted_id
                                        ),
                                        "l3_publish_epoch": self.tree_core.l3_publish_epoch(),
                                        "kv_durable": bool(
                                            promoted_evidence
                                            and promoted_evidence.get("kv_durable")
                                        ),
                                        "mamba_durable": bool(
                                            promoted_evidence
                                            and promoted_evidence.get("mamba_durable")
                                        ),
                                        "kv_completed_tokens": (
                                            promoted_evidence.get(
                                                "kv_completed_tokens"
                                            )
                                            if promoted_evidence
                                            else None
                                        ),
                                        "mamba_succeeded_pages": (
                                            promoted_evidence.get(
                                                "mamba_succeeded_pages"
                                            )
                                            if promoted_evidence
                                            else None
                                        ),
                                        "result": bool(
                                            promoted_evidence and context_complete
                                        ),
                                        "context_complete": context_complete,
                                    }
                                )
                                if (
                                    promoted_evidence is not None
                                    and context_complete
                                    and promoted_evidence.get("kv_durable")
                                    and promoted_evidence.get("mamba_durable")
                                ):
                                    final_kv_hash = promoted_evidence.get(
                                        "final_kv_hash", ""
                                    )
                                    durability_event_id = _t38c_durable_log(
                                        {
                                            "evt": "durability_barrier",
                                            "trace_context": promoted_evidence.get(
                                                "trace_context"
                                            ),
                                            "operation_id": promoted_evidence.get(
                                                "operation_id"
                                            ),
                                            "attempt_id": promoted_evidence.get(
                                                "attempt_id"
                                            ),
                                            "node_id": str(promoted_id),
                                            "final_kv_hash": final_kv_hash,
                                            "kv_durable": True,
                                            "mamba_durable": True,
                                            "kv_completed_tokens": promoted_evidence.get(
                                                "kv_completed_tokens"
                                            ),
                                            "kv_requested_tokens": promoted_evidence.get(
                                                "kv_requested_tokens"
                                            ),
                                            "mamba_expected_pages": promoted_evidence.get(
                                                "mamba_expected_pages"
                                            ),
                                            "mamba_succeeded_pages": promoted_evidence.get(
                                                "mamba_succeeded_pages"
                                            ),
                                            "mamba_key_count": promoted_evidence.get(
                                                "mamba_key_count"
                                            ),
                                            "mamba_key_set_digest": promoted_evidence.get(
                                                "mamba_key_set_digest"
                                            ),
                                            "expected_rank_set": promoted_evidence.get(
                                                "expected_rank_set"
                                            ),
                                            "observed_ack_rank_set": promoted_evidence.get(
                                                "observed_ack_rank_set"
                                            ),
                                            "observed_ack_rank_count": promoted_evidence.get(
                                                "observed_ack_rank_count"
                                            ),
                                            "rank_set_unavailable": promoted_evidence.get(
                                                "rank_set_unavailable", True
                                            ),
                                            "combined_durable": True,
                                            "result": True,
                                            "reason": "kv_ack_mamba_ack_frontier",
                                        }
                                    )
                                    if durability_event_id is not None:
                                        durability_identity = _t38c_residency_identity(
                                            promoted_evidence.get("trace_context"),
                                            promoted_id,
                                            final_kv_hash,
                                        )
                                        if durability_identity is not None:
                                            self._t38c_durability_ready.add(
                                                durability_identity
                                            )
                                            lifecycle = self._t38c_residency_lifecycle.setdefault(
                                                durability_identity,
                                                {
                                                    "state": "BUILD_CREATED",
                                                    "build_event_id": None,
                                                    "durability_event_id": None,
                                                    "component_snapshot": None,
                                                    "queue_snapshot": None,
                                                    "publication_event_id": None,
                                                    "retirement_reason": None,
                                                    "reconcile_attempt_count": 0,
                                                    "reason_attempt_counts": {},
                                                    "diagnostic_reason_set": set(),
                                                    "suppressed_diagnostic_count": 0,
                                                    "first_failure_reason": None,
                                                    "first_failure_event_id": None,
                                                    "first_attempt_ts_mono_ns": None,
                                                    "last_attempt_ts_mono_ns": None,
                                                    "first_attempt_event_id": None,
                                                    "last_attempt_event_id": None,
                                                    "terminal_event_id": None,
                                                    "detach_expectations_registered": False,
                                                    "detach_manifest": set(),
                                                },
                                            )
                                            lifecycle["durability_event_id"] = (
                                                durability_event_id
                                            )
                                            _t38c_residency_reconcile(
                                                self,
                                                durability_identity,
                                                "durability_ready",
                                            )
                                # Promotion consumes this exact attempt's
                                # evidence even when Mamba was absent/failed;
                                # a later write must never join against it.
                                if promoted_attempt_key is not None:
                                    promoted_candidates = self._t38c_durability_evidence.get(
                                        str(promoted_id), {}
                                    )
                                    promoted_candidates.pop(promoted_attempt_key, None)
                                    if not promoted_candidates:
                                        self._t38c_durability_evidence.pop(
                                            str(promoted_id), None
                                        )
                            # P2-1 M2: a freshly persisted anchor can serve
                            # its frontier waiters. Set membership only --
                            # no queue consumption, no callbacks, no write
                            # path -- so the F2 exactly-once ack semantics
                            # are untouched.
                            for promoted_id in promoted:
                                self._wake_frontier_waiters(promoted_id)
                        else:
                            # Partial write (a page batch failed): L3 holds
                            # no durable copy, so the node must not become
                            # an anchor (hollow would release the last
                            # complete copy on its word). Clear the
                            # submission dedupe guard so the next gap fill
                            # rewrites the node; the host lock ref was
                            # released above and re-acquired on resubmit.
                            logger.warning(
                                "[P2A] partial backup ack: node %d got %d/%d "
                                "tokens; will rewrite",
                                node_id,
                                operation.completed_tokens,
                                len(operation.host_indices),
                            )
                            self.tree_core.clear_storage_written(node_id)
                if (
                    log_metrics
                    and self.enable_storage_metrics
                    and self.storage_metrics_collector is not None
                ):
                    self.storage_metrics_collector.log_backuped_tokens(
                        operation.completed_tokens
                    )
            return drained

        def _drain_release():
            release_pairs = []
            while n_release is None or len(release_pairs) < n_release:
                pair = cc._t38c_pop_host_mem_release_pair(
                    cc.host_mem_release_queue, PoolName.KV
                )
                if pair is None:
                    break
                release_pairs.append(pair)
            host_indices_list = [page for page, _token in release_pairs]
            released_tokens = 0
            for host_indices in host_indices_list:
                released_tokens += len(host_indices)
            if host_indices_list:
                cc.mem_pool_host.free(torch.cat(host_indices_list, dim=0))
                self._bump_host_allocability(
                    PoolName.KV.value,
                    "queued_release_drain",
                    released_tokens,
                )
                for host_indices, token in release_pairs:
                    digest = _t38c_slot_digest(PoolName.KV, [host_indices])
                    trace_context = slot_context_for_token(token)
                    _t38c_note_completion(
                        self, PoolName.KV.value, "host", digest, token=token
                    )
                    _t38c_durable_log(
                        {
                            "evt": "residency_free_complete",
                            "trace_context": trace_context,
                            "pool": PoolName.KV.value,
                            "tier": "host",
                            "slot_count": int(host_indices.numel()),
                            "slot_digest": digest,
                            "result": True,
                            "reason": "queued_release_drain_returned",
                        }
                    )
            return len(host_indices_list), released_tokens

        def _drain_extra_release():
            drained: dict[PoolName, tuple[int, int]] = {}
            if not extra_release_counts:
                return drained
            for pool_name, limit in extra_release_counts.items():
                release_queue = cc.extra_host_mem_release_queues.get(pool_name)
                if release_queue is None:
                    continue
                release_pairs = []
                while limit is None or len(release_pairs) < limit:
                    pair = cc._t38c_pop_host_mem_release_pair(
                        release_queue, pool_name
                    )
                    if pair is None:
                        break
                    release_pairs.append(pair)
                host_indices_list = [page for page, _token in release_pairs]
                released_tokens = 0
                for host_indices in host_indices_list:
                    released_tokens += len(host_indices)
                if host_indices_list:
                    cc.mem_pool_host.free(
                        torch.cat(host_indices_list, dim=0), pool=pool_name
                    )
                    self._bump_host_allocability(
                        pool_name.value,
                        "queued_release_drain",
                        released_tokens,
                    )
                    pool_label = getattr(pool_name, "value", pool_name)
                    for host_indices, token in release_pairs:
                        digest = _t38c_slot_digest(pool_label, [host_indices])
                        trace_context = slot_context_for_token(token)
                        _t38c_note_completion(
                            self, pool_label, "host", digest, token=token
                        )
                        _t38c_durable_log(
                            {
                                "evt": "residency_free_complete",
                                "trace_context": trace_context,
                                "pool": pool_label,
                                "tier": "host",
                                "slot_count": int(host_indices.numel()),
                                "slot_digest": digest,
                                "result": True,
                                "reason": "queued_release_drain_returned",
                            }
                        )
                drained[pool_name] = (len(host_indices_list), released_tokens)
            return drained

        _drain_and_alloc_storage_hit()
        _drain_ack_prefetch()
        _drain_backup()
        _drain_release()
        _drain_extra_release()
        if self.cache_controller is not None:
            self._drain_extent_evictions()
        # The owning drain transaction is the authoritative queue-empty
        # trigger. Polling remains an optional watchdog, never liveness.
        _t38c_residency_release_queues_drained(self)
```


### `UnifiedRadixCache._drain_write_through_acks` — `python/sglang/srt/mem_cache/unified_radix_cache.py:8241-8275` (35 lines)

```python
    def _drain_write_through_acks(self) -> None:
        """One pass over one generation of the D->H ack queue: sync each DMA
        and ack every pending write-through entry (write_back entries
        included)."""
        cc = self.cache_controller
        if self._drain_write_through_depth:
            # Re-entered from an ACK callback: the enclosing drain owns this
            # round. Defer one more nonblocking pass so newly enqueued ACKs are
            # consumed only after the current generation is fully processed.
            self._drain_write_through_retry_pending = True
            return
        self._drain_write_through_depth += 1
        try:
            while True:
                if not cc.ack_write_queue:
                    break
                # Claim the whole generation up front so every ack is popped
                # exactly once before its callback runs; callbacks may request
                # another pass, but cannot consume this generation again.
                self._drain_write_through_retry_pending = False
                batch = list(cc.ack_write_queue)
                cc.ack_write_queue.clear()
                for ack in batch:
                    ack.finish_event.synchronize()
                    acked = False
                    for ack_id in ack.node_ids:
                        if ack_id in self.ongoing_write_through:
                            self._finish_write_through_ack(ack_id)
                            acked = True
                    if acked:
                        self._log_write_ack_metrics(ack)
                if not self._drain_write_through_retry_pending:
                    break
        finally:
            self._drain_write_through_depth -= 1
```


## 4. Complete hot-path source: `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py`

Source version: `06f89994845f0e41c779950924064c16ebfbd956`.


### `UnifiedTreeCore.match_prefix` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:984-1009` (26 lines)

```python
    def match_prefix(self, params: MatchPrefixParams) -> MatchResult:
        key = params.key
        key, _ = key.maybe_to_bigram_view(self.is_eagle)
        if len(key) == 0:
            return self._empty_match_result
        key = key.page_aligned(self.page_size)
        if len(key) == 0:
            return self._empty_match_result

        (
            value,
            best_match_node,
            best_match_device_node,
            best_match_device_value_len,
            full_kv_hit_length,
            action,
        ) = self._match_prefix_helper(key)
        return self._match_post_processor(
            params,
            value,
            best_match_node,
            best_match_device_node,
            best_match_device_value_len,
            full_kv_hit_length,
            action,
        )
```


### `UnifiedTreeCore._match_prefix_helper` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:1011-1096` (86 lines)

```python
    def _match_prefix_helper(self, key: RadixKey) -> tuple[
        list[torch.Tensor],
        UnifiedTreeNode,
        UnifiedTreeNode,
        int,
        int,
        Optional[CacheAction | ComponentAction],
    ]:
        # Non-HiCache mode has only device-resident matches, so the scheduler
        # device anchor follows the best match. In HiCache mode, host-backed
        # nodes can also match, so we separately track the best device-resident
        # match for scheduler prefix indices and locking.
        node = self.root_node
        child_key = key.child_key(self.page_size)
        value: list[torch.Tensor] = []
        best_match_node = node
        best_match_device_node = node
        best_match_device_value_len = 0
        full_kv_hit_length = 0
        action: Optional[CacheAction | ComponentAction] = None
        separate_device_match = self.enable_hicache
        if separate_device_match:
            validators = tuple(
                comp.create_match_validator() for comp in self.components
            )
            device_validators = tuple(
                comp.create_match_validator(match_device_only=True)
                for comp in self.components
            )
        else:
            validators = tuple(
                comp.create_match_validator(match_device_only=True)
                for comp in self.components
            )

        def _all_valid(validators, node):
            return all([v(node) for v in validators])

        def _update_best_if_valid(node):
            nonlocal best_match_node
            nonlocal best_match_device_value_len, best_match_device_node
            matched = _all_valid(validators, node)
            if matched:
                best_match_node = node

            if not separate_device_match:
                if matched:
                    best_match_device_value_len = len(value)
                    best_match_device_node = node
                return
            if _all_valid(device_validators, node):
                best_match_device_value_len = len(value)
                best_match_device_node = node

        while len(key) > 0 and child_key in node.children:
            child = node.children[child_key]

            # HiCache: dead node (evicted + not backuped) — stop traversal
            if child.evicted and not child.backuped:
                break

            prefix_len = child.key.match(key, page_size=self.page_size)
            full_kv_hit_length += prefix_len
            if prefix_len < len(child.key):
                node, action = self._split_node(child.key, child, prefix_len)
                if not node.evicted:
                    value.append(node.component_data[BASE_COMPONENT_TYPE].value)
                _update_best_if_valid(node)
                break

            if not child.evicted:
                value.append(child.component_data[BASE_COMPONENT_TYPE].value)
            node = child
            _update_best_if_valid(node)
            key = key[prefix_len:]
            if len(key):
                child_key = key.child_key(self.page_size)

        return (
            value,
            best_match_node,
            best_match_device_node,
            best_match_device_value_len,
            full_kv_hit_length,
            action,
        )
```


### `UnifiedTreeCore._match_post_processor` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:1098-1154` (57 lines)

```python
    def _match_post_processor(
        self,
        params: MatchPrefixParams,
        value: list[torch.Tensor],
        best_match_node: UnifiedTreeNode,
        best_match_device_node: UnifiedTreeNode,
        best_match_device_value_len: int,
        full_kv_hit_length: int,
        action: Optional[CacheAction | ComponentAction],
    ) -> MatchResult:
        node_update = best_match_node
        for comp in self.components:
            if comp.component_type == BASE_COMPONENT_TYPE:
                continue  # Full uses last_access_time, not LRU
            comp.refresh_lru(LRURefreshPhase.MATCH_END, node_update, self.root_node)

        cur_time = get_and_increase_time_counter()
        while node_update:
            node_update.last_access_time = cur_time
            cur_time -= 0.00001
            node_update = node_update.parent

        # last_host_node will be used as the starting node for the subsequent
        # `prefetch_from_storage` flow. We directly use best_match_node here,
        # because best_match_node represents the node where all components
        # have reached consensus on both device & host availability.
        last_host_node = (
            best_match_node if self.enable_hicache else best_match_device_node
        )

        if best_match_device_value_len > 0:
            device_indices = torch.cat(value[:best_match_device_value_len])
        else:
            device_indices = self._empty_match_result.device_indices
        result = MatchResult(
            device_indices=device_indices,
            last_device_node=best_match_device_node,
            last_host_node=last_host_node,
            best_match_node=best_match_node,
            host_hit_length=0,
            full_kv_hit_length=full_kv_hit_length,
        )

        for component in self.components:
            result = component.finalize_match_result_in_tree_core(
                result=result,
                params=params,
                value_chunks=value,
                best_value_len=best_match_device_value_len,
            )
        # Expose only NodeIds outside TreeCore.
        return result._replace(
            last_device_node=result.last_device_node.id,
            last_host_node=result.last_host_node.id,
            best_match_node=result.best_match_node.id,
            cache_actions=[action] if action is not None else [],
        )
```


### `UnifiedTreeCore._reclaim_full_host_duplicates` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:1936-2033` (98 lines)

```python
    def _reclaim_full_host_duplicates(
        self,
        num_tokens: int,
        tracker: dict[ComponentType, int],
        device_frees: dict[ComponentType, list[torch.Tensor]],
        host_frees: dict[ComponentType, list[torch.Tensor]],
        *,
        require_host_subtree_leaf: bool = False,
    ) -> None:
        """Reclaim Full host duplicates until num_tokens are freed; pass 1
        spares evictable D-leaves (imminent free demotes), pass 2 takes them.

        With *require_host_subtree_leaf* (``write_through``) a node's Full host
        layer is released only once none of its children holds one: the write
        policy keeps the host copy set prefix-closed (``sanity_check`` rejects a
        backed-up child under a non-backed-up parent, and restore walks it as a
        contiguous chain), so the hosts must be released bottom-up.  Repeating
        the walk lets an ancestor become a leaf in the next pass, which keeps the
        release O(passes x nodes) without sorting the whole duplicate set.
        """
        passes = _HOST_DUPLICATE_RECLAIM_MAX_PASSES if require_host_subtree_leaf else 1
        debug = None
        if _HOST_RECLAIM_DEBUG:
            debug = {
                "passes": passes,
                "tracked": len(self.full_host_duplicates),
                "scanned": 0,
                "spared": 0,
                "stale": 0,
                "locked": 0,
                "pending_dma": 0,
                "write_through_pending": 0,
                "load_back_pending": 0,
                "subtree_blocked": 0,
                "other_ineligible": 0,
                "released": 0,
                "want": int(num_tokens),
                "reclaim_context": getattr(self, "_host_reclaim_context", None),
                "_started_ns": time.monotonic_ns(),
            }
        for _pass in range(passes):
            if tracker[BASE_COMPONENT_TYPE] >= num_tokens:
                break
            swept_ids: list[NodeId] = []
            released = False
            for spare_imminent_demotes in (True, False):
                if tracker[BASE_COMPONENT_TYPE] >= num_tokens:
                    break
                for node in self.full_host_duplicates.values():
                    if tracker[BASE_COMPONENT_TYPE] >= num_tokens:
                        break
                    cd = node.component_data[BASE_COMPONENT_TYPE]
                    if debug is not None:
                        debug["scanned"] += 1
                    if cd.value is None or cd.host_value is None:
                        swept_ids.append(node.id)  # stale entry
                        if debug is not None:
                            debug["stale"] += 1
                        continue
                    if spare_imminent_demotes and node in self.evictable_device_leaves:
                        if debug is not None:
                            debug["spared"] += 1
                        continue
                    if not self._can_reclaim_full_host_duplicate(
                        node, require_host_subtree_leaf
                    ):
                        if debug is not None:
                            if node.write_through_pending_id is not None:
                                debug["write_through_pending"] += 1
                            elif node.load_back_pending_id is not None:
                                debug["load_back_pending"] += 1
                            elif cd.host_lock_ref != 0:
                                debug["locked"] += 1
                            elif require_host_subtree_leaf and any(
                                child.backuped for child in node.children.values()
                            ):
                                debug["subtree_blocked"] += 1
                            else:
                                debug["other_ineligible"] += 1
                        continue
                    self._release_full_host_duplicate(
                        node,
                        tracker,
                        device_frees,
                        host_frees,
                        require_host_subtree_leaf=require_host_subtree_leaf,
                    )
                    swept_ids.append(node.id)  # released -> no longer a duplicate
                    released = True
                    if debug is not None:
                        debug["released"] += 1
            # Sweep after the walk: the dict must not be mutated mid-iteration.
            for nid in swept_ids:
                self.full_host_duplicates.pop(nid, None)
            if not released:
                break
        if debug is not None:
            self._log_host_reclaim_debug(debug, tracker)
```


### `UnifiedTreeCore._can_reclaim_full_host_duplicate` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:2053-2075` (23 lines)

```python
    def _can_reclaim_full_host_duplicate(
        self, node: UnifiedTreeNode, require_host_subtree_leaf: bool = False
    ) -> bool:
        """Full on both tiers, no in-flight DMA, no Full host lock; checked
        live because tracking may be stale."""
        cd = node.component_data[BASE_COMPONENT_TYPE]
        if node is self.root_node or cd.value is None or cd.host_value is None:
            return False
        if (
            node.write_through_pending_id is not None
            or node.load_back_pending_id is not None
        ):
            return False
        if cd.host_lock_ref != 0:
            return False
        if require_host_subtree_leaf and any(
            child.backuped for child in node.children.values()
        ):
            # Releasing this host layer first would leave a backed-up child
            # under a non-backed-up parent, which the write_through prefix
            # invariant forbids (and the L2 restore chain would break there).
            return False
        return True
```


### `UnifiedTreeCore._evict_host_leaf` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:2106-2134` (29 lines)

```python
    def _evict_host_leaf(
        self,
        node: UnifiedTreeNode,
        tracker: dict[ComponentType, int],
        device_frees: dict[ComponentType, list[torch.Tensor]],
        host_frees: dict[ComponentType, list[torch.Tensor]],
    ) -> None:
        """Atomically evict all components on a host leaf.

        All freed tokens are accumulated into *tracker*."""
        assert self._is_host_leaf(node), f"node {node.id} is not an H-leaf"

        self.kv_events.record_remove(node, medium=StorageMedium.CPU)
        before_host = node.backuped
        for comp in self.components:
            _, hf = self._evict_component_and_detach_lru(
                node,
                comp,
                target=EvictLayer.ALL,
                tracker=None,
                device_frees=device_frees,
                host_frees=host_frees,
            )
            tracker[comp.component_type] += hf
        self._trace_full_host_transition("host_leaf_evict", node, before_host)
        self._trace_check_full_host_invariant("host_leaf_evict")
        self.evictable_host_leaves.discard(node)
        self._remove_leaf_from_parent(node)
        self._iteratively_delete_tombstone_leaf(node, tracker, device_frees, host_frees)
```


### `UnifiedTreeCore.build_storage_backup_spec` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:2518-2543` (26 lines)

```python
    def build_storage_backup_spec(
        self, node_id: NodeId, pass_prefix_keys: bool
    ) -> Optional[StorageBackupSpec]:
        """Gather a node's device->storage backup spec; None if the node is not backuped."""
        node = self.node_by_id(node_id)
        if not node.backuped:
            return None
        prefix_keys = None
        if pass_prefix_keys:
            prefix_keys = node.get_prefix_hash_values(node.parent)
        comp_xfers: dict[ComponentType, list[PoolTransfer]] = {}
        for comp in self.components:
            if comp.component_type == BASE_COMPONENT_TYPE:
                continue
            transfers = comp.build_hicache_transfers(
                node, CacheTransferPhase.BACKUP_STORAGE
            )
            if transfers:
                comp_xfers[comp.component_type] = transfers
        return StorageBackupSpec(
            host_value=node.component_data[BASE_COMPONENT_TYPE].host_value,
            token_ids=node.key.token_ids,
            hash_value=node.hash_value,
            prefix_keys=prefix_keys,
            comp_xfers=comp_xfers,
        )
```


### `UnifiedTreeCore.advance_storage_persisted` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:2725-2743` (19 lines)

```python
    def advance_storage_persisted(self, node_id: NodeId) -> list[NodeId]:
        """Record a node's L3 write ack; it becomes a persisted anchor when
        its parent already is (the root always is). Returns every node whose
        storage_persisted turned True here, node first then descendants:
        children acked before their parent chain became contiguous are
        promoted retroactively (chain promotion must not depend on ack
        order)."""
        node = self.node_by_id(node_id)
        node.storage_written = True
        node.storage_acked = True
        if node.storage_persisted:
            return []
        if (
            node.parent is None
            or node.parent is self.root_node
            or node.parent.storage_persisted
        ):
            return self._promote_persisted_subtree(node)
        return []
```


### `UnifiedTreeCore.persisted_chain_frontier` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:2810-2842` (33 lines)

```python
    def persisted_chain_frontier(
        self,
        node_id: NodeId,
        pos: dict[str, int],
        requested_pages: int,
    ) -> int:
        """The durable frontier of the persisted chain under node_id, in
        request coordinates: the deepest persisted page end on the request
        branch (the backup-completion wait's durable_frontier).

        Persistence needs a contiguous parent chain, so the persisted nodes
        under the anchor form a connected prefix of the chain; the frontier
        is the max block end over them. The walk enters a child only when
        its parent is persisted (an unpromoted child can have no persisted
        descendants -- advance_storage_persisted promotes exactly the acked
        descendants of a persisted node), and prunes branches whose first
        page is not on the request. The anchor itself (persisted, pages
        before the request start) contributes 0 and lets the walk through
        to its children."""
        if not self.node_exists(node_id):
            return 0

        def walk(node: UnifiedTreeNode) -> int:
            end = 0
            if node.storage_persisted:
                block = self.page_block_in_request(node.id, pos, requested_pages)
                if block is not None:
                    end = block[1]
                for child in node.children.values():
                    end = max(end, walk(child))
            return end

        return walk(self.node_by_id(node_id))
```


### `UnifiedTreeCore.commit_backup` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:2954-2981` (28 lines)

```python
    def commit_backup(
        self,
        node_id: NodeId,
        host_indices: torch.Tensor,
        comp_xfers: dict[ComponentType, list[PoolTransfer]],
    ) -> None:
        """Commit a successful backup to the node."""
        node = self.node_by_id(node_id)
        cache_actions: list[CacheAction | ComponentAction] = []
        if host_indices.numel() > 0:
            before_host = node.backuped
            kv_xfer = PoolTransfer(name=PoolName.KV, host_indices=host_indices)
            self.components_by_type[BASE_COMPONENT_TYPE].commit_hicache_transfer(
                node,
                CacheTransferPhase.BACKUP_HOST,
                transfers=[kv_xfer],
                cache_actions=cache_actions,
            )
            self._trace_full_host_transition("backup_commit", node, before_host)
            self._trace_check_full_host_invariant("backup_commit")
        for ct, xfers in comp_xfers.items():
            self.components_by_type[ct].commit_hicache_transfer(
                node,
                CacheTransferPhase.BACKUP_HOST,
                transfers=xfers,
                cache_actions=cache_actions,
            )
        assert not cache_actions  # BACKUP_HOST emits no actions
```


### `UnifiedTreeCore.commit_load_back` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:2983-3022` (40 lines)

```python
    def commit_load_back(
        self,
        node_id: NodeId,
        device_indices: torch.Tensor,
        kv_xfer: PoolTransfer,
        comp_xfers: dict[ComponentType, list[PoolTransfer]],
    ) -> list[CacheAction | ComponentAction]:
        """Commit a successful H->D load-back onto the node; the SWA full->swa mapping
        rebuild is deferred to the orchestration layer."""
        node = self.node_by_id(node_id)
        cache_actions: list[CacheAction | ComponentAction] = []
        if self.is_write_back:
            # Pin Full KV host slots against duplicate reclaim until the ack.
            # Auxiliary pools have independent host locks and may legitimately
            # load the same radix node under a different anchor.
            for nid in kv_xfer.nodes_to_load or ():
                pinned = self.node_by_id(nid)
                assert pinned.load_back_pending_id in (None, node_id), (
                    f"node {nid} pinned by load-back "
                    f"{pinned.load_back_pending_id}, new anchor {node_id}"
                )
                pinned.load_back_pending_id = node_id
        kv_xfer.device_indices = device_indices
        self.components_by_type[BASE_COMPONENT_TYPE].commit_hicache_transfer(
            node,
            CacheTransferPhase.LOAD_BACK,
            [kv_xfer],
            cache_actions=cache_actions,
        )
        for nid in kv_xfer.nodes_to_load or ():
            self.kv_events.record_store(self.node_by_id(nid), medium=StorageMedium.GPU)
        for ct, xfers in comp_xfers.items():
            self.components_by_type[ct].commit_hicache_transfer(
                node,
                CacheTransferPhase.LOAD_BACK,
                xfers,
                cache_actions=cache_actions,
            )
        self._update_evictable_leaf_sets(node)
        return cache_actions
```


### `UnifiedTreeCore.finish_load_back` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:3024-3040` (17 lines)

```python
    def finish_load_back(self, anchor_node_id: NodeId) -> None:
        """Finalize H->D load-back state along the anchor's root path.

        Write-back clears source-node pins at ack time. Write-through does not
        use those pins, but still refreshes duplicate tracking after the device
        copies become visible. Split fragments stay on the path, so the walk
        covers them.
        """
        node = self.node_by_id(anchor_node_id)
        while node is not None and node is not self.root_node:
            if self.is_write_back:
                if node.load_back_pending_id != anchor_node_id:
                    node = node.parent
                    continue
                node.load_back_pending_id = None
            self._update_duplicate_tracking(node)
            node = node.parent
```


### `UnifiedTreeCore.mark_write_through_pending` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:3042-3045` (4 lines)

```python
    def mark_write_through_pending(self, node_id: NodeId) -> None:
        """Mark a node as having an in-flight write-through backup."""
        node = self.node_by_id(node_id)
        node.write_through_pending_id = node_id
```


### `UnifiedTreeCore.finish_write_through` — `python/sglang/srt/mem_cache/unified_cache/unified_tree_core.py:3047-3056` (10 lines)

```python
    def finish_write_through(self, node_ids: list[NodeId], ack_id: int) -> None:
        """Clear the write-through-pending mark (when it matches ack_id) and record the
        host store event for each acked node."""
        for node_id in node_ids:
            node = self.node_by_id(node_id)
            if node.write_through_pending_id == ack_id:
                node.write_through_pending_id = None
                # The backed-up copy becomes a tracked duplicate only now.
                self._update_duplicate_tracking(node)
            self.kv_events.record_store(node, medium=StorageMedium.CPU)
```


## 4. Complete hot-path source: `python/sglang/srt/managers/cache_controller.py`

Source version: `06f89994845f0e41c779950924064c16ebfbd956`.


### `HiCacheController._start_storage_threads` — `python/sglang/srt/managers/cache_controller.py:492-524` (33 lines)

```python
    def _start_storage_threads(self):
        """Start storage prefetch/backup threads and their queues.

        This is used by runtime attach, and also by reset when storage is enabled.
        """
        assert self.enable_storage
        assert not self.storage_stop_event.is_set()

        self.prefetch_thread = threading.Thread(
            target=self.prefetch_thread_func, daemon=True
        )
        self.prefetch_io_aux_thread = threading.Thread(
            target=self.prefetch_io_aux_func, daemon=True
        )
        self.prefetch_sync_thread = threading.Thread(
            target=self.prefetch_sync_thread_func, daemon=True
        )
        self.backup_thread = threading.Thread(
            target=self.backup_thread_func, daemon=True
        )
        self.prefetch_queue = Queue()
        self.backup_queue = Queue()
        self.prefetch_buffer = Queue()
        self.prefetch_sync_queue = Queue()
        self.prefetch_hit_queue = Queue()
        self.ack_prefetch_queue = Queue()
        self.ack_backup_queue = Queue()
        self.host_mem_release_queue = Queue()

        self.prefetch_thread.start()
        self.prefetch_io_aux_thread.start()
        self.prefetch_sync_thread.start()
        self.backup_thread.start()
```


### `HiCacheController._stop_storage_threads` — `python/sglang/srt/managers/cache_controller.py:526-574` (49 lines)

```python
    def _stop_storage_threads(self):
        """Stop storage prefetch/backup threads and drain internal queues.

        Caller should ensure no in-flight requests.
        """
        # Always request stop. This is safe even when storage is already disabled,
        # and makes detach truly idempotent (previous partial detach may have left
        # threads alive).
        # NOTE: do NOT clear storage_stop_event unless threads have fully stopped; otherwise
        # a still-alive thread may resume and touch released state.
        self.storage_stop_event.set()

        # Best-effort wakeups so threads exit promptly even if blocked on queues.
        try:
            if hasattr(self, "prefetch_queue"):
                self.prefetch_queue.put_nowait(None)
            if hasattr(self, "backup_queue"):
                self.backup_queue.put_nowait(None)
            if hasattr(self, "prefetch_buffer"):
                self.prefetch_buffer.put_nowait(None)
            if hasattr(self, "prefetch_sync_queue"):
                self.prefetch_sync_queue.put_nowait(None)
        except Exception:
            pass

        # Best-effort joins (threads are daemon, but join keeps state clean).
        threads = []
        if hasattr(self, "prefetch_thread"):
            threads.append(self.prefetch_thread)
        if hasattr(self, "backup_thread"):
            threads.append(self.backup_thread)
        if hasattr(self, "prefetch_io_aux_thread"):
            threads.append(self.prefetch_io_aux_thread)
        if hasattr(self, "prefetch_sync_thread"):
            threads.append(self.prefetch_sync_thread)

        for t in threads:
            try:
                t.join(timeout=10)
            except Exception:
                pass

        alive = [t for t in threads if getattr(t, "is_alive", lambda: False)()]
        if alive:
            logger.error(
                "Failed to stop HiCache storage threads cleanly: %s",
                [getattr(t, "name", repr(t)) for t in alive],
            )
            raise RuntimeError("Failed to stop HiCache storage threads cleanly.")
```


### `HiCacheController.write` — `python/sglang/srt/managers/cache_controller.py:884-905` (22 lines)

```python
    def write(
        self,
        device_indices: torch.Tensor,
        priority: Optional[int] = None,
        node_id: int = -1,
    ) -> Optional[torch.Tensor]:
        """
        Back up KV caches from device memory to host memory.
        """
        # D->H write-back staging: the channel the P3 write-back reserve
        # protects. May use the reserved host space (alloc_writeback), so a
        # backup always has a landing zone even when the working set fills
        # the pool to the reserve floor.
        alloc = getattr(self.mem_pool_host, "alloc_writeback", self.mem_pool_host.alloc)
        host_indices = alloc(len(device_indices))
        if host_indices is None:
            return None
        self.write_queue.append(
            CacheOperation(host_indices, device_indices, node_id, priority)
        )
        self.start_writing()
        return host_indices
```


### `HiCacheController.load` — `python/sglang/srt/managers/cache_controller.py:937-952` (16 lines)

```python
    def load(
        self,
        host_indices: torch.Tensor,
        priority: Optional[int] = None,
        node_id: int = -1,
    ) -> Optional[torch.Tensor]:
        """
        Load KV caches from host memory to device memory.
        """
        device_indices = self.mem_pool_device_allocator.alloc(len(host_indices))
        if device_indices is None:
            return None
        self.load_queue.append(
            CacheOperation(host_indices, device_indices, node_id, priority)
        )
        return device_indices
```


### `HiCacheController.prefetch` — `python/sglang/srt/managers/cache_controller.py:1068-1082` (15 lines)

```python
    def prefetch(
        self,
        request_id: str,
        new_input_tokens: List[int],
        last_hash: Optional[str] = None,
        prefix_keys: Optional[List[str]] = None,
    ) -> PrefetchOperation:
        """
        Prefetch KV caches from storage backend to host memory.
        """
        operation = PrefetchOperation(
            request_id, new_input_tokens, last_hash, prefix_keys
        )
        self.prefetch_queue.put(operation)
        return operation
```


### `HiCacheController._page_transfer` — `python/sglang/srt/managers/cache_controller.py:1145-1197` (53 lines)

```python
    def _page_transfer(self, operation: PrefetchOperation) -> int:
        # Transfer batch by batch
        prefix_keys = operation.prefix_keys
        kv_derived_transfers = [
            transfer
            for transfer in getattr(operation, "pool_transfers", None) or []
            if transfer.indices_from_pool == PoolName.KV
        ]
        all_success = True
        completed_pages = 0
        for i in range(0, len(operation.hash_value), STORAGE_BATCH_SIZE):
            # When an error is occurred, we should keep looping and produce the same number of
            # PrefetchAck as other ranks do, because prefetch_sync_thread (i.e. consumer of
            # prefetch_sync_queue) perform reduce on the results.  This is so tricky.
            if all_success and operation.is_terminated():
                all_success = False
            if all_success:
                batch_hashes = operation.hash_value[i : i + STORAGE_BATCH_SIZE]
                batch_host_indices = operation.host_indices[
                    i * self.page_size : (i + len(batch_hashes)) * self.page_size
                ]

                # Get one batch token, and update the completed_tokens if succeed
                extra_info = HiCacheStorageExtraInfo(
                    prefix_keys=prefix_keys,
                    extra_info={
                        "rid": operation.request_id,
                        "attempt_id": getattr(operation, "prefetch_attempt_id", None),
                        "operation": "prefetch_restore",
                        "pool": "kv",
                    },
                )

                hit_pages = self._page_transfer_kv_batch(
                    operation,
                    batch_hashes,
                    batch_host_indices,
                    extra_info,
                    kv_derived_transfers,
                )
                # Check termination
                if hit_pages != len(batch_hashes):
                    all_success = False
                if prefix_keys and len(prefix_keys) > 0:
                    prefix_keys += batch_hashes
                completed_pages += hit_pages
            ack = PrefetchAck(
                rid=operation.request_id,
                completed_tokens=completed_pages * self.page_size,
                operation=operation,
            )
            self.prefetch_sync_queue.put(ack)
        return completed_pages
```


### `HiCacheController.prefetch_thread_func` — `python/sglang/srt/managers/cache_controller.py:1329-1364` (36 lines)

```python
    def prefetch_thread_func(self):
        """
        Manage prefetching operations from storage backend to host memory.
        """
        while (not self.storage_stop_event.is_set()) or not self.prefetch_queue.empty():
            try:
                operation = self.prefetch_queue.get(block=True, timeout=1)
                if operation is None:
                    continue
                if operation.is_terminated():
                    hash_value, storage_hit_count = [], 0
                else:
                    hash_value, storage_hit_count = self._storage_hit_query(operation)
                storage_hit_count_tensor = torch.tensor(
                    storage_hit_count, dtype=torch.int
                )
                self._all_reduce(
                    storage_hit_count_tensor,
                    torch.distributed.ReduceOp.MIN,
                    self.prefetch_hits_sync_groups,
                )
                storage_hit_count = storage_hit_count_tensor.item()

                # Record the TP-synced hit count; the scheduler thread decides
                # at drain time whether to revoke (below threshold) or allocate.
                operation.hash_value = hash_value[
                    : (storage_hit_count // self.page_size)
                ]
                operation.storage_hit_count = storage_hit_count
                self.prefetch_hit_queue.put(operation)

            except Empty:
                continue
            except Exception as e:
                self._storage_thread_fatal("prefetch_thread_func", e)
                return
```


### `HiCacheController._page_set_for_operation` — `python/sglang/srt/managers/cache_controller.py:1392-1415` (24 lines)

```python
    def _page_set_for_operation(
        self, hash_values, host_indices, extra_info, operation
    ) -> bool:
        """Write one KV batch, preserving the operation's transient group."""
        group_id = getattr(operation, "group_id", None)
        if group_id is None:
            return self.page_set_func(hash_values, host_indices, extra_info)

        transfer = PoolTransfer(
            name=PoolName.KV,
            host_indices=host_indices,
            keys=hash_values,
        )
        results = self.storage_backend.batch_set_v2(
            [transfer], extra_info=extra_info, group_id=group_id
        )
        result = results.get(transfer.name)
        if result is None:
            result = results.get(transfer.name.value)
        return (
            isinstance(result, (list, tuple))
            and len(result) == len(hash_values)
            and all(bool(ok) for ok in result)
        )
```


### `HiCacheController._page_backup` — `python/sglang/srt/managers/cache_controller.py:1423-1448` (26 lines)

```python
    def _page_backup(self, operation):
        # Backup batch by batch
        prefix_keys = operation.prefix_keys
        success = True
        for i in range(0, len(operation.hash_value), STORAGE_BATCH_SIZE):
            batch_hashes = operation.hash_value[i : i + STORAGE_BATCH_SIZE]
            batch_host_indices = operation.host_indices[
                i * self.page_size : (i + len(batch_hashes)) * self.page_size
            ]
            # Set one batch token, and record if success.
            # todo: allow partial success
            extra_info = HiCacheStorageExtraInfo(prefix_keys=prefix_keys)
            batch_success = self._page_set_for_operation(
                batch_hashes, batch_host_indices, extra_info, operation
            )
            if not batch_success:
                success = False
                logger.warning(
                    f"Write page to storage: {len(batch_hashes)} pages failed."
                )
                break

            if prefix_keys and len(prefix_keys) > 0:
                prefix_keys += batch_hashes
            operation.completed_tokens += self.page_size * len(batch_hashes)
        return success
```


### `HiCacheController.backup_thread_func` — `python/sglang/srt/managers/cache_controller.py:1450-1468` (19 lines)

```python
    def backup_thread_func(self):
        """
        Manage backup operations from host memory to storage backend.
        """
        while not self.storage_stop_event.is_set():
            try:
                operation = self.backup_queue.get(block=True, timeout=1)
                if operation is None:
                    continue

                if not self.backup_skip:
                    self._page_backup(operation)
                self.ack_backup_queue.put(operation)

            except Empty:
                continue
            except Exception as e:
                self._storage_thread_fatal("backup_thread_func", e)
                return
```


### `HiCacheController.prefetch_sync_thread_func` — `python/sglang/srt/managers/cache_controller.py:1470-1483` (14 lines)

```python
    def prefetch_sync_thread_func(self):
        """Synchronize prefetch results across all PP and TP ranks."""
        while not self.storage_stop_event.is_set():
            try:
                ack = self.prefetch_sync_queue.get(block=True, timeout=1)
                if ack is None:
                    continue
                self._reduce_prefetch_ack(ack)
                self.ack_prefetch_queue.put(ack)
            except Empty:
                continue
            except Exception as e:
                self._storage_thread_fatal("prefetch_sync_thread_func", e)
                return
```


### `HiCacheController._reduce_prefetch_ack` — `python/sglang/srt/managers/cache_controller.py:1485-1497` (13 lines)

```python
    def _reduce_prefetch_ack(self, ack: PrefetchAck) -> None:
        """Synchronize all ranks to agree on a PrefetchAck."""
        if ack.completed_tokens is not None:
            # Determine the minimal successful prefix of tokens.
            completed_tokens_tensor = torch.tensor(
                ack.completed_tokens, dtype=torch.int
            )
            self._all_reduce(
                completed_tokens_tensor,
                torch.distributed.ReduceOp.MIN,
                self.prefetch_completion_sync_groups,
            )
            ack.completed_tokens = completed_tokens_tensor.item()
```


## 4. Complete hot-path source: `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py`

Source version: `06f89994845f0e41c779950924064c16ebfbd956`.


### `HybridCacheController.write` — `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:573-608` (36 lines)

```python
    def write(
        self,
        device_indices: torch.Tensor,
        priority: Optional[int] = None,
        node_id: int = -1,
        extra_pools: Optional[list[PoolTransfer]] = None,
    ) -> Optional[torch.Tensor]:
        # D->H write-back staging: may use the P3 write-back reserve.
        alloc = getattr(self.mem_pool_host, "alloc_writeback", self.mem_pool_host.alloc)
        host_indices = alloc(len(device_indices))
        if host_indices is None:
            return None
        pool_transfers = self.mem_pool_host.resolve_host_transfers(
            extra_pools,
            primary_device_indices=device_indices,
            primary_host_indices=host_indices,
            writeback=True,
        )
        if pool_transfers is None and extra_pools:
            self.mem_pool_host.free(host_indices)
            callback = getattr(self, "host_allocability_change_fn", None)
            if callback is not None:
                callback(PoolName.KV.value, "direct_free", len(host_indices))
            return None

        self.write_queue.append(
            CacheOperation(
                host_indices,
                device_indices,
                node_id,
                priority,
                pool_transfers=pool_transfers or None,
            )
        )
        self.start_writing()
        return host_indices
```


### `HybridCacheController.load` — `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:770-810` (41 lines)

```python
    def load(
        self,
        host_indices: torch.Tensor,
        priority: Optional[int] = None,
        node_id: int = -1,
        extra_pools: Optional[list[PoolTransfer]] = None,
    ) -> Optional[torch.Tensor]:
        need_load_kv = host_indices.numel() > 0

        full_allocator = getattr(
            self.mem_pool_device_allocator,
            "full_attn_allocator",
            self.mem_pool_device_allocator,
        )
        if not need_load_kv:
            device_indices = torch.empty((0,), dtype=torch.int64, device=self.device)
        else:
            device_indices = full_allocator.alloc(len(host_indices))
            if device_indices is None:
                return None

        pool_transfers = self._resolve_device_transfers(
            extra_pools,
            kv_device_indices=device_indices,
            kv_host_indices=host_indices,
        )
        if pool_transfers is None and extra_pools:
            if need_load_kv:
                full_allocator.free(device_indices)
            return None

        self.load_queue.append(
            CacheOperation(
                host_indices,
                device_indices,
                node_id,
                priority,
                pool_transfers=pool_transfers or None,
            )
        )
        return device_indices
```


### `HybridCacheController.prefetch` — `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:812-848` (37 lines)

```python
    def prefetch(
        self,
        request_id: str,
        new_input_tokens: List[int],
        last_hash: Optional[str] = None,
        prefix_keys: Optional[List[str]] = None,
        extra_pools: Optional[list[PoolTransfer]] = None,
        trace_context: Optional[dict] = None,
        telemetry_enabled: bool = False,
        session_generation: Optional[int] = None,
        prefetch_attempt_id: Optional[str] = None,
        matched_prefix_l3_proof: Optional[dict] = None,
        matched_prefix_tokens: Optional[int] = None,
    ) -> PrefetchOperation:
        operation = PrefetchOperation(
            request_id,
            new_input_tokens,
            last_hash,
            prefix_keys=prefix_keys,
            pool_transfers=extra_pools,
            trace_context=trace_context,
        )
        operation.telemetry_enabled = telemetry_enabled
        operation.telemetry_session_generation = (
            session_generation if telemetry_enabled else None
        )
        operation.prefetch_attempt_id = prefetch_attempt_id
        operation.matched_prefix_l3_proof = matched_prefix_l3_proof
        operation.stats_matched_prefix_tokens = matched_prefix_tokens
        for transfer in extra_pools or []:
            transfer._t38c_trace_context = operation.trace_context
        if telemetry_enabled:
            # This is the controller-owned acceptance/publication seam.  Keep
            # the value immutable after this point: workers only observe it.
            operation.prefetch_issue_mono_ns = time.monotonic_ns()
        self.prefetch_queue.put(operation)
        return operation
```


### `HybridCacheController._page_backup` — `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:1129-1233` (105 lines)

```python
    def _page_backup(self, operation):
        # MLA KV is replicated across TP ranks and should still be written only
        # by TP0. Rank-sharded sidecars still need every TP rank.
        backup_transfers = [
            transfer
            for transfer in operation.pool_transfers or []
            if self.should_backup(transfer)
        ]
        has_sidecar = any(bool(transfer.keys) for transfer in backup_transfers)
        has_kv = bool(operation.hash_value) and not self.backup_skip
        group_api = all(
            callable(getattr(self.storage_backend, method, None))
            for method in ("open_group", "commit_group", "abort_group")
        )
        group_id = None
        committed = False

        try:
            if group_api and (has_kv or has_sidecar):
                group_id = self.storage_backend.open_group()
                operation.group_id = group_id
            sidecar_ok = True
            if backup_transfers:
                self._resolve_sidecar_kv_derived_pool_transfers(operation)
                self._resolve_sidecar_nonkv_derived_pool_transfers(operation)
                results = (
                    self.storage_backend.batch_set_v2(
                        backup_transfers, group_id=group_id
                    )
                    if group_id is not None
                    else self.storage_backend.batch_set_v2(backup_transfers)
                )
                operation.pool_storage_result.update_extra_pool_hit_pages(
                    count_pool_hits(results)
                )
                for transfer in backup_transfers:
                    result = results.get(transfer.name)
                    if result is None:
                        result = results.get(transfer.name.value)
                    expected = len(transfer.keys or [])
                    if expected == 0 and transfer.host_indices is not None:
                        expected = int(transfer.host_indices.numel())
                    sidecar_ok = sidecar_ok and (
                        isinstance(result, (list, tuple))
                        and len(result) == expected
                        and all(bool(ok) for ok in result)
                    )
                if not sidecar_ok:
                    return self._fail_backup(operation, "sidecar_set_failed")

            kv_ok = True
            if has_kv:
                previous_context = getattr(
                    self.storage_backend, "_t38c_durable_context", None
                )
                try:
                    self.storage_backend._t38c_durable_context = {
                        **(operation.trace_context or {}),
                        "operation_id": operation.id,
                        "attempt_id": getattr(
                            operation, "trace_id", f"storage-{operation.id}"
                        ),
                        "node_id": str(getattr(operation, "node_id", "") or ""),
                        "final_kv_hash": operation.hash_value[-1]
                        if operation.hash_value
                        else "",
                        "pool": "kv",
                    }
                except Exception:
                    previous_context = None
                try:
                    kv_ok = super()._page_backup(operation)
                finally:
                    try:
                        if previous_context is None:
                            del self.storage_backend._t38c_durable_context
                        else:
                            self.storage_backend._t38c_durable_context = previous_context
                    except Exception:
                        pass
            elif self.backup_skip:
                operation.completed_tokens = (
                    len(operation.hash_value) * self.page_size if has_sidecar else 0
                )

            if not kv_ok:
                return self._fail_backup(operation, "kv_set_failed")
            if group_id is not None:
                committed = bool(self.storage_backend.commit_group(group_id))
                if not committed:
                    return self._fail_backup(operation, "group_commit_failed")
                return True
            if not sidecar_ok:
                return self._fail_backup(operation, "sidecar_set_failed")
            return True
        except Exception as exc:
            return self._fail_backup(
                operation,
                f"exception:{type(exc).__name__}: {exc}",
                exc_info=True,
            )
        finally:
            if group_id is not None and not committed:
                self.storage_backend.abort_group(group_id)
            operation.group_id = None
```


### `HybridCacheController.backup_thread_func` — `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:1257-1385` (129 lines)

```python
    def backup_thread_func(self):
        """Back up rank-sharded sidecars on every TP rank.

        The base implementation skips the entire operation on non-zero MLA TP
        ranks. That optimization is valid for replicated MLA KV, but not for
        hybrid rank-sharded pools such as Kimi-K3 Mamba state.
        """
        while not self.storage_stop_event.is_set():
            try:
                operation = self.backup_queue.get(block=True, timeout=1)
                if operation is None:
                    continue
                if not self._page_backup(operation):
                    # A failed L3 write did NOT commit, so its submit-time
                    # host pin has no ack coming. Surface the reason through
                    # the existing storage-failure ownership path: the raise
                    # is handled below by _storage_thread_fatal, and the
                    # scheduler's check_hicache_events -> _handle_storage_failure
                    # then releases every unacked ongoing_backup pin in-run,
                    # exactly once, and gates further L3 writes for the run.
                    # The backup thread must stop (it must not retry a
                    # degraded backend) and must never enqueue an ack for a
                    # write that did not commit.
                    reason = getattr(
                        operation, "backup_failure_reason", "unknown"
                    )
                    raise RuntimeError(f"backup did not commit: {reason}")
                transfers = operation.pool_transfers or []
                mamba_transfers = [
                    transfer
                    for transfer in transfers
                    if transfer.name == PoolName.MAMBA
                ]
                mamba_keys = [
                    key
                    for transfer in mamba_transfers
                    for key in (transfer.keys or [])
                ]
                mamba_key_set_digest, mamba_key_count = ordered_key_set_digest(
                    mamba_keys
                )
                mamba_expected_pages = mamba_key_count
                mamba_succeeded_pages = operation.pool_storage_result.extra_pool_hit_pages.get(
                    PoolName.MAMBA,
                    operation.pool_storage_result.extra_pool_hit_pages.get(
                        PoolName.MAMBA.value, 0
                    ),
                )
                expected_rank_set = getattr(
                    operation, "_t38c_expected_rank_set",
                    self._t38c_expected_rank_set,
                )
                if expected_rank_set is None:
                    expected_rank_set = next(
                        (
                            getattr(transfer, "_t38c_expected_rank_set", None)
                            for transfer in mamba_transfers
                            if getattr(transfer, "_t38c_expected_rank_set", None)
                            is not None
                        ),
                        None,
                    )
                expected_rank_set = (
                    sorted(str(rank) for rank in expected_rank_set)
                    if expected_rank_set
                    else list(self._t38c_expected_rank_set)
                )
                observed_ack_rank_set = [
                    str(
                        torch.distributed.get_rank(group=self.tp_group)
                        if torch.distributed.is_available()
                        and torch.distributed.is_initialized()
                        else os.environ.get("RANK", "0")
                    )
                ]
                _t38c_durable_log(
                    {
                        "evt": "backup_ack_enqueue",
                        "trace_context": getattr(
                            operation, "trace_context", None
                        ),
                        "operation_id": operation.id,
                        "attempt_id": getattr(
                            operation, "trace_id", f"storage-{operation.id}"
                        ),
                        "node_id": str(getattr(operation, "node_id", "") or ""),
                        "final_kv_hash": (
                            operation.hash_value[-1]
                            if operation.hash_value
                            else ""
                        ),
                        "kv_transfer": bool(operation.hash_value),
                        "mamba_transfer": any(
                            transfer.name == PoolName.MAMBA for transfer in transfers
                        ),
                        "kv_durable": operation.completed_tokens
                        >= len(operation.hash_value) * self.page_size,
                        "mamba_durable": mamba_key_count > 0
                        and mamba_succeeded_pages == mamba_expected_pages,
                        "mamba_expected_pages": mamba_expected_pages,
                        "mamba_succeeded_pages": mamba_succeeded_pages,
                        "mamba_key_count": mamba_key_count,
                        "mamba_key_set_digest": mamba_key_set_digest,
                        "expected_rank_set": expected_rank_set,
                        "observed_ack_rank_set": observed_ack_rank_set,
                        "observed_ack_rank_count": len(observed_ack_rank_set),
                        "rank_set_unavailable": not expected_rank_set,
                        "operation": operation.id,
                        "attempt": getattr(
                            operation, "trace_id", f"storage-{operation.id}"
                        ),
                        "completed_tokens": int(operation.completed_tokens),
                        "result": "complete"
                        if operation.completed_tokens
                        >= len(operation.hash_value) * self.page_size
                        else "partial",
                    }
                )
                self.ack_backup_queue.put(operation)
            except Empty:
                continue
            except Exception as exc:
                # Base-controller semantics (managers/cache_controller.py
                # backup_thread_func): an unexpected per-op exception is a
                # terminal storage-thread failure. Without this the hybrid
                # thread died silently, never set storage_failure_reason, and
                # left every in-flight ongoing_backup pin held until shutdown.
                self._storage_thread_fatal("backup_thread_func", exc)
                return
```


### `HybridCacheController._reduce_prefetch_ack` — `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py:1528-1546` (19 lines)

```python
    def _reduce_prefetch_ack(self, ack: PrefetchAck) -> None:
        # Handle KV-derived pool.
        super()._reduce_prefetch_ack(ack)

        # Handle other sidecar pools, e.g. SWA, Mamba.
        if ack.pool_hits is not None:
            # "for ... in PoolName" ensures the same order across all ranks.
            # On prefetch failure, pool_hits may be empty dict.
            packed = torch.tensor(
                [ack.pool_hits.get(pool.value, 0) for pool in PoolName],
                dtype=torch.int,
            )
            self._all_reduce(
                packed,
                torch.distributed.ReduceOp.MIN,
                self.prefetch_completion_sync_groups,
            )
            for i, pool in enumerate(PoolName):
                ack.pool_hits[pool.value] = packed[i].item()
```


## 4. Complete hot-path source: `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py`

Source version: `06f89994845f0e41c779950924064c16ebfbd956`.


### `_NativePageSource.__init__` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:232-235` (4 lines)

```python
    def __init__(self, length, blocks=None, buffers=None):
        self.length = length
        self.blocks = blocks
        self.buffers = buffers
```


### `ExtentFileBackend.__init__` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:494-718` (225 lines)

```python
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

        threshold_raw = extra.get("wal_checkpoint_bytes")
        if threshold_raw is not None:
            threshold_source = "extra_config"
        elif envs.SGLANG_HICACHE_EXTENT_BACKEND_WAL_CHECKPOINT_BYTES.is_set():
            threshold_raw = envs.SGLANG_HICACHE_EXTENT_BACKEND_WAL_CHECKPOINT_BYTES.get()
            threshold_source = "env"
        else:
            threshold_raw = _DEFAULT_WAL_CHECKPOINT_BYTES
            threshold_source = "default"
        self._wal_checkpoint_bytes = _parse_wal_checkpoint_bytes(
            threshold_raw, threshold_source
        )
        self._wal_checkpoint_source = threshold_source
        self._wal_checkpoint_requested = threshold_raw

        # One data file per rank/config suffix: ranks never share an allocator.
        self._data_path = os.path.join(
            self._storage_dir, f"hicache.data{self.config_suffix}"
        )
        self._manifest_path = manifest_path(self._storage_dir, self.config_suffix)
        self._wal_current_path = current_path(self._storage_dir, self.config_suffix)
        self._meta_lock_path = lock_path(self._storage_dir, self.config_suffix)
        # The lock is itself persistent metadata.  Capture its pre-open
        # existence so the lock file created by this constructor cannot make a
        # genuinely fresh namespace look like a prior initialized one.
        self._meta_lock_existed_before_open = os.path.exists(self._meta_lock_path)
        self._meta_lock_fd = None
        self._meta_lock_owner = False
        self._fd = None
        self._wal_fd = None
        self._wal_generation = None
        self._wal_offset = 0
        self._wal_next_seq = 1
        self._next_batch_id = 1
        self._next_group_seq = 1
        self._staged_groups = {}
        self._staged_reserved = {}
        self._file_uuid = self._new_file_uuid()
        self._namespace_epoch = self._new_nonzero_epoch()
        self._components = {}
        # Cache entries invalidated by durable DROP_SLOT commits are consumed
        # by the scheduler to clear the corresponding Radix L3 beliefs.
        self._evicted_storage_keys = []
        self._constructor_complete = False
        self._closed = False
        self._lifecycle_state = "OPENING"
        self._lifecycle_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._checkpoint_event = threading.Event()
        self._checkpoint_stop = threading.Event()
        self._checkpoint_thread = None
        self._lock = threading.Lock()
        # Lock order is deliberately fixed at _write_gate -> _lock.  The gate
        # quiesces writers while checkpoint rotates and reclaims WAL segments;
        # reads continue to use _lock only.
        self._write_gate = threading.RLock()
        # Native write-path A/B switch (arm A = 0, the Python reference path).
        # The worker is created lazily on the first arm-B write, so an arm-A
        # run neither builds nor imports the Rust extension.
        self._native_write_path = _native_write_path_enabled()
        self._native_writer = None
        self._native_writer_lock = threading.Lock()
        self._native_registered_arenas = set()
        self._stats = {
            "opens": 0,
            "preads": 0,
            "pwrites": 0,
            "bytes_read": 0,
            "bytes_written": 0,
            # Read-amplification accounting (P0 fix: exact-range reads).
            # requested_bytes = ref lengths of read batches; physical_bytes_read
            # = merged pread spans; the ratio target is < 1.2x.  prefetch_bytes_read
            # stays 0: this backend has no prefetch logic, every pread is
            # request-driven (engine-side proactive prefetch arrives as ordinary
            # batch_get/batch_get_v2 and is counted like any other read).
            "requested_bytes": 0,
            "physical_bytes_read": 0,
            "prefetch_bytes_read": 0,
            "last_batch_requested_bytes": 0,
            "last_batch_physical_bytes": 0,
            "last_batch_preads": 0,
            "wal_checkpoint_bytes": self._wal_checkpoint_bytes,
            "wal_checkpoint_requested_bytes": self._wal_checkpoint_requested,
            "wal_checkpoint_source": self._wal_checkpoint_source,
            "wal_active_bytes": 0,
            "wal_checkpoint_requested": 0,
            "wal_checkpoint_successes": 0,
            "wal_checkpoint_failures": 0,
            "wal_checkpoint_retries": 0,
            "wal_checkpoint_last_error": None,
            # Native seam (arm B) failure accounting (H2).
            "native_write_failures": 0,
            "native_write_last_error": None,
        }
        try:
            (
                self._meta_lock_fd,
                self._meta_lock_owner,
                geometry_matches,
            ) = self._acquire_backend_meta_lock()
            self._fd = os.open(self._data_path, os.O_CREAT | os.O_RDWR, 0o644)
            self._stats["opens"] += 1
            os.ftruncate(self._fd, self._file_size)
            self._allocator = ExtentAllocator(
                extent_size, self._file_size // extent_size
            )
            if geometry_matches:
                self._startup_metadata()
            self._open_active_wal()
            self._constructor_complete = True
            self._lifecycle_state = "OPEN"
            self._start_checkpoint_worker()
            logger.info(
                f"ExtentFileBackend: file={self._data_path} extent={extent_size} B "
                f"slots={self._file_size // extent_size} "
                f"max_size={self._max_size_bytes} min_free={self._min_free_bytes} "
                f"wal_checkpoint_bytes={self._wal_checkpoint_bytes} "
                f"wal_checkpoint_requested={self._wal_checkpoint_requested!r} "
                f"wal_checkpoint_source={self._wal_checkpoint_source}"
            )
        except Exception:
            self._checkpoint_stop.set()
            self._checkpoint_event.set()
            if self._checkpoint_thread is not None:
                self._checkpoint_thread.join()
                self._checkpoint_thread = None
            if self._wal_fd is not None:
                os.close(self._wal_fd)
                self._wal_fd = None
            self._release_backend_meta_lock()
            if self._fd is not None:
                try:
                    os.close(self._fd)
                finally:
                    self._fd = None
            raise
```


### `ExtentFileBackend._checkpoint_worker` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:731-766` (36 lines)

```python
    def _checkpoint_worker(self) -> None:
        while not self._checkpoint_stop.is_set():
            if not self._checkpoint_event.wait(0.5):
                continue
            # Clear the request under the same lifecycle lock used by the
            # signaler.  A signal that arrives during checkpoint processing is
            # not cleared afterward, so it remains a distinct retry request.
            with self._lifecycle_lock:
                self._checkpoint_event.clear()
                if self._lifecycle_state != "OPEN":
                    return
            if self._checkpoint_stop.is_set():
                return
            self._stats["wal_checkpoint_requested"] += 1
            succeeded = False
            for attempt in range(_WAL_CHECKPOINT_MAX_RETRIES):
                if self._checkpoint_stop.is_set():
                    return
                try:
                    # checkpoint() takes _write_gate itself; no backend lock is
                    # held across this call, preserving the existing lock order.
                    if not self.checkpoint(preserve_incomplete_groups=True):
                        break
                    self._stats["wal_checkpoint_successes"] += 1
                    self._stats["wal_active_bytes"] = max(
                        0, self._wal_offset - SEGMENT_HEADER_SIZE
                    )
                    succeeded = True
                    break
                except Exception as exc:
                    self._stats["wal_checkpoint_failures"] += 1
                    self._stats["wal_checkpoint_last_error"] = repr(exc)
                    if attempt + 1 < _WAL_CHECKPOINT_MAX_RETRIES:
                        self._stats["wal_checkpoint_retries"] += 1
                        if self._checkpoint_stop.wait(_WAL_CHECKPOINT_RETRY_DELAY):
                            return
```


### `ExtentFileBackend._acquire_backend_meta_lock` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:794-810` (17 lines)

```python
    def _acquire_backend_meta_lock(self):
        """Acquire the per-namespace fence for this backend instance."""
        with _PROCESS_META_LOCKS_LOCK:
            held = _PROCESS_META_LOCKS.get(self._meta_lock_path)
            if held is not None:
                raise RecoveryError(
                    "metadata lock is already held by this process",
                    path=self._meta_lock_path,
                    failure_class="lock-busy",
                )
            fd = acquire_meta_lock(self._meta_lock_path)
            _PROCESS_META_LOCKS[self._meta_lock_path] = (
                fd,
                1,
                (self._extent_size, self._file_size),
            )
            return fd, True, True
```


### `ExtentFileBackend._release_backend_meta_lock` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:812-826` (15 lines)

```python
    def _release_backend_meta_lock(self) -> None:
        fd = self._meta_lock_fd
        if fd is None:
            return
        self._meta_lock_fd = None
        with _PROCESS_META_LOCKS_LOCK:
            owner_fd, count, geometry = _PROCESS_META_LOCKS[self._meta_lock_path]
            count -= 1
            if fd != owner_fd:
                os.close(fd)
            if count == 0:
                _PROCESS_META_LOCKS.pop(self._meta_lock_path, None)
                os.close(owner_fd)
            else:
                _PROCESS_META_LOCKS[self._meta_lock_path] = (owner_fd, count, geometry)
```


### `ExtentFileBackend._restore_allocator` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:848-943` (96 lines)

```python
    def _restore_allocator(self, state: ManifestState, replay) -> None:
        num_slots = self._file_size // self._extent_size
        if len(replay.generations) != num_slots:
            raise RecoveryError(
                "replay generation geometry mismatch",
                path=self._manifest_path,
                failure_class="wal-replay-state",
            )
        refs = []
        keys = []
        slot_keys = [set() for _ in range(num_slots)]
        slot_bytes = [0] * num_slots
        cursors = [0] * num_slots
        index = {}
        component_map = {}
        for entry in replay.entries:
            try:
                key = entry.storage_key.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RecoveryError(
                    "WAL storage key is not valid UTF-8",
                    path=self._manifest_path,
                    failure_class="wal-replay-corruption",
                ) from exc
            if not 0 <= entry.extent_id < num_slots:
                raise RecoveryError(
                    "replayed entry is outside allocator geometry",
                    path=self._manifest_path,
                    failure_class="wal-replay-state",
                )
            if (
                entry.offset < 0
                or entry.length < 0
                or entry.offset + entry.length > self._extent_size
                or entry.generation != replay.generations[entry.extent_id]
            ):
                raise RecoveryError(
                    "replayed entry does not match allocator state",
                    path=self._manifest_path,
                    failure_class="wal-replay-state",
                )
            ref = ExtentRef(
                entry.extent_id, entry.offset, entry.length, entry.generation
            )
            index[key] = ref
            component_map[key] = entry.component

        for key, ref in index.items():
            slot_keys[ref.extent_id].add(key)
            slot_bytes[ref.extent_id] += ref.length
            cursors[ref.extent_id] = max(cursors[ref.extent_id], ref.offset + ref.length)

        if slot_bytes != list(replay.slot_bytes) or cursors != list(replay.cursors):
            raise RecoveryError(
                "replayed allocator accounting mismatch",
                path=self._manifest_path,
                failure_class="wal-replay-state",
            )
        if not 0 <= state.next_slot < num_slots:
            raise RecoveryError(
                "manifest next_slot is outside allocator geometry",
                path=self._manifest_path,
                failure_class="manifest-corruption",
            )

        recency = []
        seen = set()
        for entry_index in state.recency_order:
            if not 0 <= entry_index < len(replay.entries):
                raise RecoveryError(
                    "manifest recency entry is outside the entry table",
                    path=self._manifest_path,
                    failure_class="manifest-corruption",
                )
            try:
                key = replay.entries[entry_index].storage_key.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RecoveryError(
                    "manifest recency key is not valid UTF-8",
                    path=self._manifest_path,
                    failure_class="manifest-corruption",
                ) from exc
            if key in index and key not in seen:
                recency.append(key)
                seen.add(key)
        recency.extend(key for key in index if key not in seen)

        with self._allocator._lock:
            self._allocator._generations = list(replay.generations)
            self._allocator._cursors = cursors
            self._allocator._slot_bytes = slot_bytes
            self._allocator._slot_keys = slot_keys
            self._allocator._index = index
            self._allocator._next_slot = state.next_slot
            self._allocator._recency = OrderedDict((key, None) for key in recency)
        self._components = component_map
```


### `ExtentFileBackend.batch_get_v2` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:1924-1981` (58 lines)

```python
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
                if transfer.name == PoolName.MAMBA:
                    _t38c_log(
                        {
                            "evt": "pc_mamba_write",
                            "node_id": getattr(transfer, "_t38c_node_id", ""),
                            "final_kv_hash": getattr(
                                transfer, "_t38c_final_kv_hash", ""
                            ),
                            "mamba_transfer_exists": True,
                            "mamba_key": keys[-1] if keys else "",
                            "batch_set_v2": False,
                        }
                    )
                continue
            storage_keys = [self._component_key(transfer.name, k) for k in keys]
            pages = self._read_pages(
                storage_keys,
                read_context=_extent_read_context(
                    extra_info, getattr(transfer.name, "value", transfer.name)
                ),
            )
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
```


### `ExtentFileBackend.batch_set_v2` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:1983-2091` (109 lines)

```python
    def batch_set_v2(
        self,
        transfers: List[PoolTransfer],
        extra_info: Optional[HiCacheStorageExtraInfo] = None,
        group_id=None,
    ) -> dict:
        if group_id is not None:
            try:
                group_id = self._validate_group_id(group_id)
            except ValueError:
                return {transfer.name: [False] * len(transfer.keys or []) for transfer in transfers}
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
                _t38c_durable_log(
                    {
                        "evt": "batch_set_result",
                        "trace_context": getattr(
                            transfer, "_t38c_trace_context", None
                        ),
                        "operation_id": getattr(transfer, "_t38c_operation_id", None),
                        "attempt_id": getattr(transfer, "_t38c_attempt_id", None),
                        "node_id": getattr(transfer, "_t38c_node_id", ""),
                        "final_kv_hash": getattr(
                            transfer, "_t38c_final_kv_hash", ""
                        ),
                        "pool": getattr(transfer.name, "value", transfer.name),
                        "requested_pages": len(keys),
                        "succeeded_pages": 0,
                        "result": False,
                        "reason": "host_index_geometry",
                    }
                )
                continue
            storage_keys = [self._component_key(transfer.name, k) for k in keys]
            page_sources = None
            if self._native_write_path:
                page_sources = self._native_page_sources_from_meta(
                    host_pool, host_indices, len(keys), page_size
                )
            values = None
            if page_sources is None:
                values = [
                    host_pool.get_data_page(int(host_indices[i * page_size]), flat=True)
                    for i in range(len(keys))
                ]
            trace_context = {
                **(
                    getattr(transfer, "_t38c_trace_context", None) or {}
                ),
                "operation_id": getattr(transfer, "_t38c_operation_id", None),
                "attempt_id": getattr(transfer, "_t38c_attempt_id", None),
                "node_id": getattr(transfer, "_t38c_node_id", ""),
                "final_kv_hash": getattr(transfer, "_t38c_final_kv_hash", ""),
                "pool": getattr(transfer.name, "value", transfer.name),
            }
            ok = self._write_pages(
                storage_keys,
                values,
                trace_context,
                group_id=group_id,
                component=component_from_pool_name(transfer.name),
                page_sources=page_sources,
            )
            results[transfer.name] = [ok] * len(keys)
            _t38c_durable_log(
                {
                    "evt": "batch_set_result",
                    **trace_context,
                    "requested_pages": len(keys),
                    "succeeded_pages": len(keys) if ok else 0,
                    "result": bool(ok),
                }
            )
            if transfer.name == PoolName.MAMBA:
                _t38c_log(
                    {
                        "evt": "pc_mamba_write",
                        "node_id": getattr(transfer, "_t38c_node_id", ""),
                        "final_kv_hash": getattr(
                            transfer, "_t38c_final_kv_hash", ""
                        ),
                        "mamba_transfer_exists": True,
                        "mamba_key": keys[-1] if keys else "",
                        "batch_set_v2": bool(ok),
                    }
                )
            if ok:
                self._log_extent_write(
                    transfer.name,
                    getattr(extra_info, "node_id", None),
                    storage_keys,
                    values
                    if values is not None
                    else [source.length for source in page_sources],
                )
        return results
```


### `ExtentFileBackend._reclaim_victims` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:2204-2230` (27 lines)

```python
    def _reclaim_victims(self, passed, drop_events):
        """Enumerate the live refs held by circular-reclaim victim slots.

        A victim is a slot the pure planner put in ``passed``: its generation
        is about to be bumped and its bytes reused.  Only refs that currently
        resolve (present in the index, in this exact slot, at the slot's
        current generation) are returned; dead/stale entries are never copied.
        """
        drop_slots = {slot for slot, _ in drop_events}
        order = []
        seen = set()
        for slot in passed:
            if slot in seen or slot not in drop_slots:
                continue
            seen.add(slot)
            order.append(slot)
        victims = []
        for slot in sorted(order):
            generation = self._allocator._generations[slot]
            for key in sorted(self._allocator._slot_keys[slot]):
                ref = self._allocator._index.get(key)
                if ref is None or ref.extent_id != slot:
                    continue
                if ref.generation != generation:
                    continue
                victims.append((key, ref))
        return victims
```


### `ExtentFileBackend._relocate_reclaim_victims_locked` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:2232-2329` (98 lines)

```python
    def _relocate_reclaim_victims_locked(self, passed, drop_events, planned_refs):
        """Move every live ref out of the reclaim victims before they drop.

        Preserves the existing durability order exactly: exact bytes are
        pread from the victim and pwritten to non-victim space, then the
        replacements are published with SET -> BATCH_COMMIT -> fsync and
        installed.  Only after that may the caller append the DROP_SLOT
        frames and bump the victim generation.  Returns False (fail closed)
        when no destination capacity can be secured; the victim is then left
        untouched and the whole write is refused.
        """
        victims = self._reclaim_victims(passed, drop_events)
        if not victims:
            return True
        # Destination space must never be a victim (about to be dropped), a
        # slot carrying this plan's own refs (its pwrite/`_cursors` update
        # follows), or a staged reservation (its bytes are already written
        # but its refs are not installed yet).
        excluded = {slot for slot, _ in drop_events}
        excluded.update(ref.extent_id for ref in planned_refs if ref is not None)
        excluded.update(self._staged_slots())
        start_slot = max(
            (ref.extent_id for ref in planned_refs if ref is not None),
            default=self._allocator._next_slot,
        )
        key_lengths = [(key, ref.length) for key, ref in victims]
        destination_refs = self._allocator.plan_relocation(
            [slot for slot in {ref.extent_id for _key, ref in victims}],
            key_lengths,
            excluded_slots=sorted(excluded),
            start_slot=start_slot,
        )
        if destination_refs is None:
            # Extent is a finite cache, not a permanent store. When safe
            # relocation cannot fit, drop this LRU victim atomically with the
            # incoming write. DROP_SLOT invalidates its generation before any
            # bytes are reused; concurrent readers verify their snapshot and
            # turn a raced read into a miss. The scheduler consumes the dropped
            # keys and clears every dependent Radix durability claim.
            logger.info(
                "ExtentFileBackend: evicting %d LRU live refs from slots %s "
                "to satisfy circular allocation (no relocation tail space)",
                len(victims),
                sorted({ref.extent_id for _key, ref in victims}),
            )
            return True
        # Exact bytes, read from the victim and written to the replacement.
        for (key, ref), destination in zip(victims, destination_refs):
            buffer = bytearray(ref.length)
            if (
                self._pread_full(
                    buffer, ref.extent_id * self._extent_size + ref.offset
                )
                != ref.length
            ):
                logger.error(
                    "ExtentFileBackend: reclaim relocation read failed for %s", key
                )
                return False
            if not self._pwritev(
                destination.extent_id * self._extent_size + destination.offset,
                [memoryview(buffer)],
            ):
                logger.error(
                    "ExtentFileBackend: reclaim relocation write failed for %s", key
                )
                return False
        relocated = [
            (
                key,
                destination,
                self._components.get(key, component_from_pool_name(PoolName.KV)),
            )
            for (key, _ref), destination in zip(victims, destination_refs)
        ]
        try:
            self._append_relocation_commit(relocated)
        except Exception as exc:
            logger.error(
                "ExtentFileBackend: reclaim relocation WAL commit failed: %s", exc
            )
            return False
        if not self._allocator.commit_install(
            [key for key, _ref in victims], destination_refs
        ):
            logger.error(
                "ExtentFileBackend: reclaim relocation install failed; "
                "refusing the write"
            )
            return False
        logger.info(
            "ExtentFileBackend: reclaim relocated %d live refs out of victim "
            "slots %s (%d bytes)",
            len(victims),
            sorted({ref.extent_id for _key, ref in victims}),
            sum(ref.length for _key, ref in victims),
        )
        return True
```


### `ExtentFileBackend._write_pages_locked` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:2352-2462` (111 lines)

```python
    def _write_pages_locked(
        self,
        keys: List[str],
        values: List[Any],
        trace_context=None,
        group_id=None,
        component=None,
        page_sources=None,
    ) -> bool:
        """Pack pages into extents and pwrite, all-or-nothing.

        Watermark GC runs first (under the lock); the whole plan->pwrite->
        commit sequence holds the index lock, so readers cannot snapshot a
        half-applied write and no state is mutated if a pwrite fails (ACK =
        pwrite success + index registration).
        """
        if page_sources is None:
            if len(keys) != len(values) or any(v is None for v in values):
                return False
        elif len(page_sources) != len(keys):
            return False
        if group_id is not None:
            try:
                group_id = self._validate_group_id(group_id)
            except ValueError:
                return False
            if group_id[0] != self._namespace_epoch or group_id not in self._staged_groups:
                return False
        with self._lock:
            if page_sources is not None:
                # Arm B with a raw meta source: skip the Python gather entirely.
                page_lens = [source.length for source in page_sources]
                views = None
            else:
                views = [_page_byte_view(v) for v in values]
                page_lens = [len(v) for v in views]
            pending_drops = self._select_gc_victims()
            refs, passed, drop_events = self._plan_split_with_staged(
                list(zip(keys, page_lens)), pending_drops
            )
            if any(slot in self._staged_slots() for slot, _ in drop_events):
                return False
            if any(r is None for r in refs):
                logger.warning(
                    "ExtentFileBackend: batch of %s pages refused (page "
                    "larger than extent_size %s B)",
                    len(keys),
                    self._extent_size,
                )
                return False
            # Reclaim-time relocation: a circular-reclaim victim's live refs
            # must have a durable replacement before its generation is bumped.
            if not self._relocate_reclaim_victims_locked(passed, drop_events, refs):
                return False
            evicted_keys = self._keys_for_drop_events(drop_events)
            try:
                self._append_drops(drop_events)
                self._allocator.apply_drops(drop_events, trace_context=trace_context)
                self._evicted_storage_keys.extend(evicted_keys)
            except Exception as exc:
                logger.error("ExtentFileBackend: WAL invalidation failed: %s", exc)
                return False
            groups: dict = {}
            for i, ref in enumerate(refs):
                groups.setdefault(ref.extent_id, []).append(i)
            pool = (trace_context or {}).get("pool", PoolName.KV)
            persisted_component = (
                component
                if component is not None
                else component_from_pool_name(pool)
            )
            if self._native_write_path:
                # Arm B: data pwritev + WAL frames + fdatasync on the Rust worker.
                if not self._native_write_locked(
                    keys,
                    page_sources,
                    views,
                    refs,
                    groups,
                    persisted_component,
                    group_id,
                ):
                    return False
            else:
                for extent_id, idxs in groups.items():
                    first = refs[idxs[0]].offset
                    bufs = [views[i] for i in idxs]
                    if not self._pwritev(extent_id * self._extent_size + first, bufs):
                        return False
                try:
                    self._append_batch_commit(
                        keys, refs, persisted_component, group_id=group_id
                    )
                except Exception as exc:
                    logger.error("ExtentFileBackend: WAL commit failed: %s", exc)
                    return False
            if group_id is not None:
                return self._stage_group_members(
                    group_id,
                    keys,
                    refs,
                    persisted_component,
                    drop_events,
                )
            if not self._allocator.commit_install(keys, refs):
                return False
            self._components.update(
                zip(keys, [persisted_component] * len(keys))
            )
            _t38c_extent_commits(keys, refs, groups, trace_context)
            return True
```


### `ExtentFileBackend._native_write_locked` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:2569-2686` (118 lines)

```python
    def _native_write_locked(
        self, keys, page_sources, views, refs, groups, component, group_id
    ) -> bool:
        """Arm B: run the whole data + WAL durable sequence on the Rust worker.

        The worker owns page pwritev, frame encoding, WAL append and fdatasync;
        it never calls back into Python.  ``commit_install`` still runs in
        Python only after this returns (invariant 3).
        """
        if page_sources is None:
            page_sources = [
                _NativePageSource(len(view), buffers=[view]) for view in views
            ]
        raw = page_sources[0].blocks is not None
        plans = []
        for extent_id, idxs in groups.items():
            ordered = sorted(idxs, key=lambda index: refs[index].offset)
            first = refs[ordered[0]].offset
            if raw:
                spec = []
                for index in ordered:
                    spec.extend(page_sources[index].blocks)
            else:
                spec = []
                for index in ordered:
                    spec.extend(page_sources[index].buffers)
            plans.append((int(extent_id * self._extent_size + first), spec))
        if group_id is None:
            group_epoch, group_seq = b"\x00" * 16, 0
        else:
            group_epoch, group_seq = self._validate_group_id(group_id)
        batch_id = self._next_batch_id
        self._next_batch_id += 1
        entries = [
            (
                key.encode("utf-8"),
                int(ref.extent_id),
                int(ref.offset),
                int(ref.length),
                int(ref.generation),
                int(component),
            )
            for key, ref in zip(keys, refs)
        ]
        writer = self._ensure_native_writer()
        common = dict(
            data_fd=self._fd,
            wal_fd=self._wal_fd,
            wal_offset=int(self._wal_offset),
            wal_seq=int(self._wal_next_seq),
            group_epoch=group_epoch,
            group_seq=group_seq,
            batch_id=batch_id,
            member_index=0,
            member_count=1,
            entries=entries,
            wal_max_record_bytes=DEFAULT_WAL_MAX_RECORD_BYTES,
        )
        try:
            if raw:
                job_id = writer.submit_write_raw(plans=plans, **common)
            else:
                job_id = writer.submit_write_buffers(plans=plans, **common)
        except Exception as exc:
            logger.error("ExtentFileBackend: native submit failed: %s", exc)
            return False
        completion = writer.wait(job_id)
        if completion is None:
            # H2: a missing completion is a protocol violation, not success.
            logger.error(
                "ExtentFileBackend: native write job %s produced no completion; "
                "failing the batch closed",
                job_id,
            )
            return False
        (
            _job_id,
            ok,
            error,
            errno,
            bytes_written,
            wal_offset,
            wal_seq,
            data_syscalls,
        ) = completion
        # Advance the shared WAL cursor even on failure: a frame the worker
        # already appended must not be overwritten (same invariant as
        # _append_wal_frame's per-frame accounting).
        if wal_offset >= self._wal_offset:
            self._wal_offset = wal_offset
            self._wal_next_seq = wal_seq
            self._stats["wal_active_bytes"] = max(
                0, wal_offset - SEGMENT_HEADER_SIZE
            )
        if data_syscalls:
            self._stats["pwrites"] += data_syscalls
            self._stats["bytes_written"] += bytes_written
        # Invariant 3: completion arrived, so the page lease may (and must) be
        # released -- on failure too, otherwise a refused batch would keep a
        # stale lease on its pages forever.
        writer.release(job_id)
        if not ok:
            # H2: explicit failure (errno/message) is propagated as a whole-batch
            # refusal. The caller returns False to the engine, no WAL frame
            # beyond what the worker durably appended is assumed, and
            # commit_install is never reached.
            self._stats["native_write_failures"] += 1
            self._stats["native_write_last_error"] = (
                f"errno={errno} {error}" if errno else error
            )
            logger.error(
                "ExtentFileBackend: native write failed (errno=%s): %s; "
                "batch refused (no commit_install)",
                errno,
                error,
            )
            return False
        return True
```


### `ExtentFileBackend._select_gc_victims` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:2690-2715` (26 lines)

```python
    def _select_gc_victims(self):
        """Select LRU victim slots without mutating allocator state."""
        if self._max_size_bytes <= 0 and self._min_free_bytes <= 0:
            return []
        victims = []
        selected = set()
        used = self._allocator.used_bytes
        recency = list(self._allocator._recency)
        while recency:
            pressure = (
                self._max_size_bytes > 0
                and used > int(self._max_size_bytes * self._eviction_ratio)
            )
            if not pressure and self._min_free_bytes > 0:
                st = os.statvfs(self._storage_dir)
                pressure = st.f_bavail * st.f_frsize < self._min_free_bytes
            if not pressure:
                break
            key = recency.pop(0)
            ref = self._allocator._index.get(key)
            if ref is None or ref.extent_id in selected:
                continue
            selected.add(ref.extent_id)
            victims.append(ref.extent_id)
            used -= self._allocator._slot_bytes[ref.extent_id]
        return victims
```


### `ExtentFileBackend._gc_evict` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:2717-2740` (24 lines)

```python
    def _gc_evict(self, trace_context=None) -> None:
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
            evicted = self._allocator.evict_slot_lru(trace_context=trace_context)
            if evicted == 0:
                return
```


### `ExtentFileBackend.close` — `python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py:2855-2891` (37 lines)

```python
    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            try:
                with self._lifecycle_lock:
                    if self._lifecycle_state == "OPEN":
                        self._lifecycle_state = "CLOSING"
                self._checkpoint_stop.set()
                self._checkpoint_event.set()
                checkpoint_thread = self._checkpoint_thread
                if checkpoint_thread is not None:
                    checkpoint_thread.join()
                    self._checkpoint_thread = None
                # H3 teardown barrier: drain + join the native worker before the
                # fds it writes through close, and before any host-pool
                # destroy()/cudaHostUnregister can run after close() returns.
                if self._native_writer is not None:
                    if not self._native_shutdown():
                        raise RuntimeError(
                            "ExtentFileBackend.close: native worker still holds "
                            "page leases; refusing to tear down pinned memory"
                        )
                    self._native_writer = None
                if self._constructor_complete and os.path.isdir(self._storage_dir):
                    with self._write_gate:
                        self._abort_all_groups_locked()
                    self.checkpoint()
                if self._wal_fd is not None:
                    os.close(self._wal_fd)
                    self._wal_fd = None
                if self._fd is not None:
                    os.close(self._fd)
                    self._fd = None
            finally:
                self._closed = True
                self._release_backend_meta_lock()
```


## 4. Complete hot-path source: `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py`

Source version: `06f89994845f0e41c779950924064c16ebfbd956`.


### `ExtentAllocator.__init__` — `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py:119-140` (22 lines)

```python
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
        # All-or-nothing guard for the split install path (NEW-4).  The
        # backend still serializes logical calls under its own index lock;
        # this lock only makes apply_drops/commit_install internally atomic.
        self._lock = threading.RLock()
```


## 4.1. Full park/wake and Host allocability helpers


### `Scheduler._host_alloc_wait_eligible` — `python/sglang/srt/managers/scheduler.py:3727-3766` (40 lines)

```python
    def _host_alloc_wait_eligible(self, req) -> bool:
        cursor = getattr(req, "hicache_host_alloc_wait_cursor", None)
        if cursor is None:
            return False
        current = self._host_alloc_snapshot_for_req(req)
        if current is None or current.cache_instance_id != cursor.snapshot.cache_instance_id:
            return False
        # Per-domain eligibility.  A blocked domain stops blocking as soon as
        # EITHER signal says it is no longer a constraint:
        #   (a) its generation advanced since the park (the original
        #       invalidation signal), OR
        #   (b) it is already capacity-satisfiable right now.
        # (b) is required for liveness: a domain can be admitted into
        # ``blocked_domains`` even though its requirement was already met
        # (e.g. mamba ``free 75 >= required 1``).  Its host EVICTABLE set then
        # never changes, so its generation never advances -- demanding one
        # starves the waiter even after the material domain (kv) becomes
        # satisfiable.  Generation is an invalidation signal only; the cache
        # allocator remains authoritative, so admitting a retry when
        # ``free + evictable`` already covers the requirement is safe.
        for pool in cursor.blocked_domains:
            if current.generation_by_pool.get(
                pool, 0
            ) > cursor.snapshot.generation_by_pool.get(pool, 0):
                continue
            # KV is the primary domain: its requirement is the request's
            # durable token span.  Aux domains use their per-pool units.
            if str(pool) == "kv":
                required = int(cursor.requested_primary_tokens)
            else:
                required = int(cursor.required_aux_units.get(str(pool), 0))
            # A blocked domain with no positive requirement is not a real
            # constraint: treat it as satisfied rather than starve.
            if required <= 0:
                continue
            free = int(current.free_units_by_pool.get(str(pool), 0))
            evictable = int(current.evictable_units_by_pool.get(str(pool), 0))
            if free + evictable < required:
                return False
        return True
```

### `Scheduler._capture_host_alloc_wait` — `python/sglang/srt/managers/scheduler.py:3791-3944` (154 lines)

```python
    def _capture_host_alloc_wait(
        self, req, failure: Optional[HostAllocFailure] = None
    ) -> None:
        if failure is None:
            pop_failure = getattr(self.tree_cache, "pop_host_alloc_failure", None)
            failure = pop_failure(req.rid) if pop_failure is not None else None
        if failure is None:
            snapshot = self._host_alloc_snapshot_for_req(req)
            if snapshot is None:
                return
            failure = HostAllocFailure(
                requested_primary_tokens=0,
                required_aux_units={},
                failed_domains=frozenset({"kv"}),
                positive_hit_tokens=0,
                sidecar_hit_pages={},
                allocability_snapshot=snapshot,
            )
        if not hasattr(self, "_host_alloc_wake_arbiter"):
            self._host_alloc_wake_arbiter = HostAllocWakeArbiter()
        arbiter = self._host_alloc_wake_arbiter
        wait_records = getattr(self, "_host_alloc_wait_records", None)
        if wait_records is None:
            wait_records = self._host_alloc_wait_records = {}
        if getattr(req, "hicache_host_alloc_attempt_id", None) is not None:
            req.hicache_host_alloc_last_attempt_id = req.hicache_host_alloc_attempt_id
            attempt_snapshot = self._host_alloc_global_snapshot()
            sequence = arbiter.record_attempt_result(
                req.rid,
                attempt_snapshot or failure.allocability_snapshot,
            )
            req.hicache_host_alloc_attempt_id = None
        else:
            sequence = arbiter.enqueue(req.rid)
        # Each (re-)park is a distinct producer-owned wait keyed to its own
        # FIFO sequence.  Reusing the previous park's wait_id would make the
        # request's own earlier release indistinguishable from its current
        # wait (the predecessor_wait_id would equal wait_id), so the identity
        # is refreshed on every park.
        req.hicache_host_alloc_wait_id = f"{req.rid}:wait:{sequence}"
        lifecycle_key = self._host_alloc_lifecycle_key(req)
        wait_record = wait_records.setdefault(
            req.rid,
            {
                "wait_id": req.hicache_host_alloc_wait_id,
                "terminal_event_id": None,
                "terminal_state": None,
            },
        )
        # A (re-)park opens a fresh producer-owned wait: refresh the terminal
        # and predecessor slots so a release from an earlier wait can never be
        # joined to this one.
        wait_record["wait_id"] = req.hicache_host_alloc_wait_id
        wait_record["rid"] = req.rid
        wait_record["fifo_sequence"] = sequence
        wait_record["blocked_domains"] = sorted(
            str(pool) for pool in (failure.failed_domains or frozenset({"kv"}))
        )
        wait_record["cache_instance_id"] = (
            failure.allocability_snapshot.cache_instance_id
        )
        wait_record["lifecycle_key"] = lifecycle_key
        wait_record["terminal_event_id"] = None
        wait_record["terminal_state"] = None
        wait_record["terminal_reason"] = None
        wait_record["predecessor_wait_id"] = None
        wait_record["predecessor_terminal_event_id"] = None
        wait_record["predecessor_terminal_state"] = None
        wait_record["predecessor_lineage_reason"] = None
        wait_record["attempt_id"] = getattr(
            req, "hicache_host_alloc_last_attempt_id", None
        )
        wait_record["wake_event_id"] = None
        req.hicache_host_alloc_wait_cursor = HostAllocWaitCursor(
            snapshot=failure.allocability_snapshot,
            blocked_domains=failure.failed_domains or frozenset({"kv"}),
            requested_primary_tokens=failure.requested_primary_tokens,
            required_aux_units=failure.required_aux_units,
            fifo_sequence=sequence,
        )
        worker, rank = self._host_alloc_telemetry_identity()
        wait_started_mono_ns = int(
            getattr(req, "hicache_restore_state_ts", time.perf_counter()) * 1e9
        )
        timeout_s = getattr(
            getattr(self, "server_args", None),
            "hicache_restore_wait_timeout_s",
            0,
        )
        deadline_mono_ns = (
            wait_started_mono_ns + int(timeout_s * 1e9) if timeout_s > 0 else None
        )
        req.hicache_host_alloc_wait_event_id = _log_host_alloc_telemetry(
            "restore_host_alloc_wait",
            worker=worker,
            rank=rank,
            rid=req.rid,
            attempt_id=getattr(req, "hicache_host_alloc_last_attempt_id", None),
            cache_instance_id=failure.allocability_snapshot.cache_instance_id,
            trace_context=self._host_alloc_trace_context(req),
            state="WAIT_CAPACITY",
            reason="HOST_ALLOC",
            positive_hit_tokens=int(failure.positive_hit_tokens),
            sidecar_hit_pages=dict(failure.sidecar_hit_pages),
            requested_primary_tokens=int(failure.requested_primary_tokens),
            required_aux_units=dict(failure.required_aux_units),
            blocked_domains=sorted(map(str, failure.failed_domains)),
            captured_generations=dict(failure.allocability_snapshot.generation_by_pool),
            current_generations=dict(failure.allocability_snapshot.generation_by_pool),
            free_units=dict(failure.allocability_snapshot.free_units_by_pool),
            evictable_units=dict(failure.allocability_snapshot.evictable_units_by_pool),
            prefetch_reservation_held=False,
            fifo_sequence=sequence,
            wait_started_mono_ns=wait_started_mono_ns,
            deadline_mono_ns=deadline_mono_ns,
            retry_grant=False,
            retry_skip=False,
            retry_outcome="parked",
            lifecycle_key=lifecycle_key,
            wait_id=wait_record["wait_id"],
            predecessor_wait_id=None,
            predecessor_terminal_event_id=None,
            predecessor_terminal_state=None,
            predecessor_lineage_reason=None,
            attempt_number=0,
            attempt_origin="HOST_ALLOC_WAIT",
            parent_wait_id=None,
            terminal_event_id=None,
            terminal_state=None,
            terminal_reason=None,
            wake_event_id=None,
        )
        self._record_host_alloc_lineage(
            req,
            attempt_number=0,
            origin="HOST_ALLOC_WAIT",
            replace_missing=True,
            wake_event_id=None,
            terminal_event_id=None,
            terminal_state=None,
            terminal_reason=None,
            predecessor_wait_id=None,
            predecessor_terminal_event_id=None,
            predecessor_terminal_state=None,
            predecessor_lineage_reason=None,
            fifo_sequence=sequence,
            cache_instance_id=failure.allocability_snapshot.cache_instance_id,
            blocked_pool_generations=dict(
                failure.allocability_snapshot.generation_by_pool
            ),
            current_generations=dict(failure.allocability_snapshot.generation_by_pool),
            deadline_mono_ns=deadline_mono_ns,
            wait_started_mono_ns=wait_started_mono_ns,
        )
```

### `Scheduler._remove_host_alloc_waiter` — `python/sglang/srt/managers/scheduler.py:3946-3953` (8 lines)

```python
    def _remove_host_alloc_waiter(
        self, rid: str, *, terminal_state=None, reason=None, req=None
    ) -> None:
        if terminal_state is not None:
            self._record_host_alloc_terminal(rid, terminal_state, reason, req)
        arbiter = getattr(self, "_host_alloc_wake_arbiter", None)
        if arbiter is not None:
            arbiter.remove(rid)
```

### `Scheduler._select_host_alloc_waiter` — `python/sglang/srt/managers/scheduler.py:3955-3989` (35 lines)

```python
    def _select_host_alloc_waiter(self) -> Optional[str]:
        if not hasattr(self, "_host_alloc_wake_arbiter"):
            self._host_alloc_wake_arbiter = HostAllocWakeArbiter()
        arbiter = self._host_alloc_wake_arbiter
        requests = {req.rid: req for req in self.waiting_queue}
        for rid in arbiter.ordered_rids():
            req = requests.get(rid)
            if req is None or req.hicache_restore_state is not RestoreState.WAIT_CAPACITY:
                self._remove_host_alloc_waiter(
                    rid,
                    terminal_state="ABANDONED",
                    reason="stale_fifo_entry",
                    req=req,
                )
        if not requests:
            return None
        controller = getattr(self.tree_cache, "cache_controller", None)
        if controller is None or controller.prefetch_rate_limited():
            return None
        timeout_s = self.server_args.hicache_restore_wait_timeout_s
        now = time.perf_counter()
        return arbiter.choose(
            lambda rid: (
                requests[rid].hicache_restore_wait_reason is RestoreWaitReason.HOST_ALLOC
                and self._host_alloc_wait_eligible(requests[rid])
                and (
                    timeout_s <= 0
                    or now
                    - getattr(requests[rid], "hicache_restore_state_ts", now)
                    <= timeout_s
                )
            ),
            lambda rid: self._host_alloc_global_generation_vector()
            or self._host_alloc_generation_vector_for_req(requests[rid]),
        )
```

### `Scheduler._host_alloc_skip_decision` — `python/sglang/srt/managers/scheduler.py:3991-3997` (7 lines)

```python
    def _host_alloc_skip_decision(self, req) -> str:
        controller = getattr(self.tree_cache, "cache_controller", None)
        if controller is None or controller.prefetch_rate_limited():
            return "hold_budget"
        if not self._host_alloc_wait_eligible(req):
            return "hold_no_generation"
        return "hold_global_grant_used"
```

### `Scheduler._emit_host_alloc_wake_grant` — `python/sglang/srt/managers/scheduler.py:3999-4103` (105 lines)

```python
    def _emit_host_alloc_wake_grant(self, req) -> Optional[str]:
        """Emit the authoritative grant record for one woken waiter.

        The record carries the producer-owned predecessor lineage resolved
        from the FIFO arbiter terminal history, and its own ``event_id`` as
        ``wake_event_id`` so later retry/finalize/READY events join to exactly
        this grant.  A grant is never coalesced away.
        """
        worker, rank = self._host_alloc_telemetry_identity()
        cursor = getattr(req, "hicache_host_alloc_wait_cursor", None)
        current = self._host_alloc_snapshot_for_req(req)
        current_generations = (
            dict(current.generation_by_pool) if current is not None else {}
        )
        captured_generations = (
            dict(cursor.snapshot.generation_by_pool) if cursor else {}
        )
        vector = current.generation_vector() if current is not None else None
        (
            predecessor_wait_id,
            predecessor_terminal_event_id,
            predecessor_terminal_state,
            predecessor_reason,
        ) = self._host_alloc_predecessor_lineage(req)
        grant_event_id = next_event_id("host-alloc")
        event_id = _log_host_alloc_telemetry(
            "restore_host_alloc_wake_decision",
            worker=worker,
            rank=rank,
            rid=req.rid,
            attempt_id=getattr(req, "hicache_host_alloc_attempt_id", None),
            cache_instance_id=(
                current.cache_instance_id if current is not None else None
            ),
            trace_context=self._host_alloc_trace_context(req),
            decision="grant",
            captured_generations=captured_generations,
            current_generations=current_generations,
            blocked_domains=sorted(map(str, cursor.blocked_domains))
            if cursor
            else [],
            required_aux_units=(dict(cursor.required_aux_units) if cursor else {}),
            requested_primary_tokens=(
                int(cursor.requested_primary_tokens) if cursor else 0
            ),
            fifo_sequence=cursor.fifo_sequence if cursor else None,
            generation_vector_id=self._host_alloc_generation_vector_id(vector),
            global_grant_used=True,
            budget_available=True,
            free_units=(
                dict(current.free_units_by_pool) if current is not None else {}
            ),
            evictable_units=(
                dict(current.evictable_units_by_pool)
                if current is not None
                else {}
            ),
            retry_grant=True,
            retry_skip=False,
            retry_outcome="grant",
            event_id=grant_event_id,
            wake_event_id=grant_event_id,
            lifecycle_key=self._host_alloc_lifecycle_key(req),
            wait_id=getattr(req, "hicache_host_alloc_wait_id", None),
            predecessor_wait_id=predecessor_wait_id,
            predecessor_terminal_event_id=predecessor_terminal_event_id,
            predecessor_terminal_state=predecessor_terminal_state,
            predecessor_lineage_reason=predecessor_reason,
            attempt_number=getattr(req, "hicache_host_alloc_attempt_number", 0),
            attempt_origin="HOST_ALLOC_WAKE",
            parent_wait_id=getattr(req, "hicache_host_alloc_wait_id", None),
        )
        if event_id is None:
            # The grant is the authority for wake_event_id; never advertise a
            # wake id that has no producer record behind it.
            return None
        req.hicache_host_alloc_wake_event_id = event_id
        records = getattr(self, "_host_alloc_wait_records", None)
        wait_record = records.get(str(req.rid)) if records else None
        if wait_record is not None:
            wait_record["wake_event_id"] = event_id
            wait_record["predecessor_wait_id"] = predecessor_wait_id
            wait_record["predecessor_terminal_event_id"] = (
                predecessor_terminal_event_id
            )
            wait_record["predecessor_terminal_state"] = predecessor_terminal_state
            wait_record["predecessor_lineage_reason"] = predecessor_reason
        self._record_host_alloc_lineage(
            req,
            attempt_number=getattr(req, "hicache_host_alloc_attempt_number", 0),
            origin="HOST_ALLOC_WAKE",
            replace_missing=True,
            wake_event_id=event_id,
            predecessor_wait_id=predecessor_wait_id,
            predecessor_terminal_event_id=predecessor_terminal_event_id,
            predecessor_terminal_state=predecessor_terminal_state,
            predecessor_lineage_reason=predecessor_reason,
            fifo_sequence=cursor.fifo_sequence if cursor else None,
            cache_instance_id=(
                current.cache_instance_id if current is not None else None
            ),
            blocked_pool_generations=captured_generations,
            current_generations=current_generations,
        )
        return event_id
```

### `Scheduler._restore_backup_wake_ready` — `python/sglang/srt/managers/scheduler.py:5748-5762` (15 lines)

```python
    def _restore_backup_wake_ready(self, req) -> bool:
        """The T15 backup-completion wake condition (P2-IO R2): the
        parked request's chain durable frontier has crossed the request's
        end (backup_wait_ready, re-read every pass -- the ACK drain
        advances it, so the wake is ACK-driven) and a DEMAND_RESTORE
        ticket is free (bounded concurrency for a backup-complete wake
        batch; the re-issue bypasses only the speculative PREFETCH_BUDGET,
        every other gate still applies)."""
        anchor = req.last_host_node
        if anchor is None:
            return False
        return (
            self.tree_cache.backup_wait_ready(req.rid)
            and demand_restore_available(self.tree_cache.demand_restore_inflight())
        )
```

### `UnifiedRadixCache._bump_host_allocability` — `python/sglang/srt/mem_cache/unified_radix_cache.py:3907-4007` (101 lines)

```python
    def _bump_host_allocability(
        self,
        pool: str,
        cause: str,
        returned_units: int = 0,
        *,
        evictable_before: Optional[int] = None,
        evictable_after: Optional[int] = None,
        causal_rid: Optional[str] = None,
        trace_context=None,
    ) -> None:
        """Advance one pool generation after a completed causal mutation.

        The generation and telemetry sequence advance for every mutation.
        Mutation records are observational samples keyed by pool, cause,
        request, and trace context: the first 16 per key are emitted, then
        every 128th mutation, with a 64-record per-key and 256-record
        per-cache-instance hard cap.  This preserves request/cause joins and
        sequence gaps while bounding log volume; it never changes wake or
        allocation behavior.
        """
        import json as _json

        returned_units = int(returned_units or 0)
        if returned_units <= 0 and cause != "lock_release_evictable":
            return
        pool = getattr(pool, "value", pool)
        generations = getattr(self, "_host_allocability_generations", None)
        if generations is None:
            generations = {}
            self._host_allocability_generations = generations
        before = generations.get(pool, 0)
        generations[pool] = before + 1
        if evictable_after is None:
            evictable_after = self._host_evictable_signature(pool)[0]
        if evictable_before is None:
            evictable_before = evictable_after
        self._host_allocability_telemetry_seq += 1

        trace_key = _json.dumps(trace_context, sort_keys=True, default=str)
        telemetry_key = (str(pool), str(cause), causal_rid, trace_key)
        mutations = getattr(self, "_host_allocability_telemetry_mutations", None)
        emitted = getattr(self, "_host_allocability_telemetry_emitted", None)
        last_emitted = getattr(
            self, "_host_allocability_telemetry_last_emitted", None
        )
        if mutations is None or emitted is None or last_emitted is None:
            mutations = {}
            emitted = {}
            last_emitted = {}
            self._host_allocability_telemetry_mutations = mutations
            self._host_allocability_telemetry_emitted = emitted
            self._host_allocability_telemetry_last_emitted = last_emitted
        if telemetry_key not in mutations and len(mutations) >= _HOST_ALLOC_MUTATION_TELEMETRY_MAX_KEYS:
            mutations.clear()
            emitted.clear()
            last_emitted.clear()
        mutation_count = mutations.get(telemetry_key, 0) + 1
        mutations[telemetry_key] = mutation_count
        key_emitted = emitted.get(telemetry_key, 0)
        total_emitted = getattr(
            self, "_host_allocability_telemetry_total_emitted", 0
        )
        should_emit = key_emitted < _HOST_ALLOC_MUTATION_TELEMETRY_HEAD or (
            mutation_count % _HOST_ALLOC_MUTATION_TELEMETRY_STRIDE == 0
            and key_emitted < _HOST_ALLOC_MUTATION_TELEMETRY_MAX_PER_KEY
        )
        if (
            not should_emit
            or key_emitted >= _HOST_ALLOC_MUTATION_TELEMETRY_MAX_PER_KEY
            or total_emitted >= _HOST_ALLOC_MUTATION_TELEMETRY_MAX_TOTAL
        ):
            return
        emitted[telemetry_key] = key_emitted + 1
        self._host_allocability_telemetry_total_emitted = total_emitted + 1
        previous_emitted_mutation = last_emitted.get(telemetry_key, 0)
        last_emitted[telemetry_key] = mutation_count
        _log_host_alloc_telemetry(
            "host_allocability_change",
            cache_instance_id=getattr(self, "_host_allocability_instance_id", 0),
            pool=pool,
            generation_before=before,
            generation_after=before + 1,
            cause=cause,
            returned_units=int(returned_units),
            evictable_before=int(evictable_before),
            evictable_after=int(evictable_after),
            causal_rid=causal_rid,
            trace_context=trace_context,
            telemetry_seq=self._host_allocability_telemetry_seq,
            telemetry_mutation_count=mutation_count,
            telemetry_sample_index=key_emitted + 1,
            telemetry_coalesced_mutations=max(
                0, mutation_count - previous_emitted_mutation - 1
            ),
            lifecycle_key=None,
            wait_id=None,
            blocked_pool_generations=dict(
                getattr(self, "_host_allocability_generations", {})
            ),
        )
```

### `UnifiedRadixCache.host_allocability_snapshot` — `python/sglang/srt/mem_cache/unified_radix_cache.py:4024-4068` (45 lines)

```python
    def host_allocability_snapshot(
        self, required_pools: Optional[Sequence[PoolName | str]] = None
    ) -> HostAllocabilitySnapshot:
        """Return a cache-owned per-pool allocability snapshot."""
        if required_pools is None:
            pools = [PoolName.KV.value]
            group = self.host_pool_group
            if group is not None:
                pools.extend(
                    getattr(entry.name, "value", entry.name)
                    for entry in group.entries
                )
        else:
            pools = [getattr(pool, "value", pool) for pool in required_pools]
            if PoolName.KV.value not in pools:
                pools.insert(0, PoolName.KV.value)
        pools = list(dict.fromkeys(str(pool) for pool in pools))

        generation_state = getattr(self, "_host_allocability_generations", {})
        generations = {pool: generation_state.get(pool, 0) for pool in pools}
        free_units = {}
        evictable_units = {}
        for pool in pools:
            evictable_units[pool] = self._host_evictable_signature(pool)[0]
            controller = self.cache_controller
            host_group = getattr(controller, "mem_pool_host", None)
            try:
                free_units[pool] = int(
                    host_group.available_size(pool=PoolName(pool))
                )
            except (AttributeError, KeyError, TypeError, ValueError):
                try:
                    free_units[pool] = (
                        int(host_group.available_size())
                        if pool == PoolName.KV.value
                        else 0
                    )
                except (AttributeError, TypeError, ValueError):
                    free_units[pool] = 0
        return HostAllocabilitySnapshot(
            cache_instance_id=getattr(self, "_host_allocability_instance_id", 0),
            generation_by_pool=generations,
            free_units_by_pool=free_units,
            evictable_units_by_pool=evictable_units,
        )
```

### `UnifiedRadixCache.evict_host` — `python/sglang/srt/mem_cache/unified_radix_cache.py:4155-4173` (19 lines)

```python
    def evict_host(
        self, num_tokens: int, component_type: ComponentType = BASE_COMPONENT_TYPE
    ) -> int:
        """Evict host resources for a specific component to free host pool space."""
        # Capture before the buffer-mode early return: ``num_tokens`` is the
        # real slot demand the failing ``prepare_prefetch`` passed to
        # ``HostPoolGroup.alloc`` regardless of whether the tree can actually
        # evict anything.
        self._note_host_alloc_reclaim_enter(component_type, num_tokens)
        try:
            if self.host_memory_mode == "buffer_only":
                # The tree never holds host values in buffer mode, and staging
                # is operation-owned (freed at each ack): nothing is evictable.
                return 0
            result = self.tree_core.drive_host_eviction(component_type, num_tokens)
            self._free_values(result.device_frees, result.host_frees)
            return result.tracker.get(component_type, 0)
        finally:
            self._note_host_alloc_reclaim_exit(component_type)
```

## 4.2. Complete Extent allocator planning, commit and recycle functions


### `ExtentAllocator.plan_split` — `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py:202-225` (24 lines)

```python
    def plan_split(
        self,
        key_lengths: Sequence[Tuple[str, int]],
        pending_drops: Optional[Sequence[int]] = None,
    ) -> Tuple[
        List[Optional[ExtentRef]], List[int], List[Tuple[int, int]]
    ]:
        """Pure plan returning ``(refs, passed, drop_events)`` (NEW-1/NEW-4).

        ``pending_drops`` is the set of GC-victim slots selected purely for
        this plan; it may be None or empty.  The unified generation form
        bumps any slot in ``passed``, ``pending_drops``, or both exactly
        once::

            pending_gen[s] = _generations[s] + max(
                passed.count(s), 1 if s in pending_drops else 0
            )
            ref.gen = pending_gen[slot]

        ``drop_events`` lists ``(slot, pending_gen[slot])`` for
        ``passed`` U ``pending_drops`` exactly once per slot.  No state is
        mutated; ``apply_drops`` later consumes ``drop_events``.
        """
        return self._plan_pure(key_lengths, pending_drops)
```

### `ExtentAllocator._plan_pure` — `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py:237-299` (63 lines)

```python
    def _plan_pure(
        self,
        key_lengths: Sequence[Tuple[str, int]],
        pending_drops: Optional[Sequence[int]] = None,
    ) -> Tuple[
        List[Optional[ExtentRef]], List[int], List[Tuple[int, int]]
    ]:
        """Shared pure planner (see :meth:`plan_split` for the contract).

        Placement is computed exactly as if ``_drop_slot`` had been applied
        once per ``pending_drops`` slot (cursor reset to 0, slot empty): a
        pending-drop slot is never treated as its pre-drop live cursor, and
        because it is empty it never contributes a ``passed`` entry -- it is
        already a drop_event, so overlap stays a single event / single bump.
        """
        pending_drops_slots = set(pending_drops) if pending_drops else set()
        refs: List[Optional[ExtentRef]] = []
        passed: List[int] = []
        packed: set = set()
        slot = self._next_slot
        cursor = 0 if slot in pending_drops_slots else self._cursors[slot]
        for _key, length in key_lengths:
            if length > self.extent_size:
                refs.append(None)
                continue
            while cursor + length > self.extent_size:
                slot = (slot + 1) % self.num_slots
                if slot in packed:
                    # Batch larger than the whole file: placement would
                    # overwrite this plan's own pages; refuse the batch.
                    return [None] * len(key_lengths), [], []
                if slot in pending_drops_slots:
                    # Victim dropped in this plan: empty with cursor 0, so
                    # place from the start of the slot and do NOT append it
                    # to ``passed`` (it is already a drop_event).
                    cursor = 0
                else:
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
                    self._pending_generation(slot, passed, pending_drops_slots),
                )
            )
            cursor += length
        drop_slots = list(dict.fromkeys(passed))
        for dropped in sorted(pending_drops_slots):
            if dropped not in drop_slots:
                drop_slots.append(dropped)
        drop_events = [
            (
                dropped,
                self._pending_generation(dropped, passed, pending_drops_slots),
            )
            for dropped in drop_slots
        ]
        return refs, passed, drop_events
```

### `ExtentAllocator.commit` — `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py:301-326` (26 lines)

```python
    def commit(
        self,
        keys: Sequence[str],
        refs: Sequence[ExtentRef],
        passed: List[int],
        trace_context: Optional[dict] = None,
    ) -> None:
        """Apply a plan after its pwrite succeeded (the backend's ACK point)."""
        for slot in passed:
            self._drop_slot(
                slot, reason="commit_reuse", trace_context=trace_context
            )
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
```

### `ExtentAllocator.apply_drops` — `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py:328-385` (58 lines)

```python
    def apply_drops(
        self,
        drop_events: Sequence[Tuple[int, int]],
        trace_context: Optional[dict] = None,
    ) -> None:
        """Apply ``(slot, new_generation)`` drops (NEW-4).

        This is the only new-path method that removes keys, resets
        ``_cursors``/``_slot_bytes``, and bumps generations.  It is
        idempotent per ``(slot, new_generation)``: a slot already at
        ``new_generation`` is a no-op, and a request that would decrease a
        generation fails closed (NM-INV-06).
        """
        with self._lock:
            for slot, new_generation in drop_events:
                old_generation = self._generations[slot]
                if old_generation == new_generation:
                    continue
                if old_generation > new_generation:
                    raise ValueError(
                        "ExtentAllocator: generation decrease for slot "
                        f"{slot}: {old_generation} -> {new_generation}"
                    )
                freed = self._slot_bytes[slot]
                removed_keys = sorted(self._slot_keys[slot])
                for key in removed_keys:
                    self._index.pop(key, None)
                    self._recency.pop(key, None)
                self._slot_keys[slot].clear()
                self._slot_bytes[slot] = 0
                self._cursors[slot] = 0
                self._generations[slot] = new_generation
                for key in removed_keys:
                    _t38c_durable_log(
                        {
                            "evt": "storage_invalidate",
                            "trace_context": trace_context,
                            "operation": "allocator_apply_drops",
                            "pool": "storage",
                            "storage_key": key,
                            "extent_id": slot,
                            "extent_generation": new_generation,
                            "old_generation": old_generation,
                            "new_generation": new_generation,
                            "index_removed": True,
                            "reason": "apply_drops",
                            "result": True,
                        }
                    )
                if freed > 0:
                    logger.info(
                        "[P3] ts_ms=%d evt=extent_recycle slot=%d "
                        "generation=%d freed=%d",
                        int(time.time() * 1000),
                        slot,
                        new_generation,
                        freed,
                    )
```

### `ExtentAllocator.commit_install` — `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py:387-430` (44 lines)

```python
    def commit_install(
        self,
        keys: Sequence[str],
        refs: Sequence[Optional[ExtentRef]],
    ) -> bool:
        """Install-only commit: never drops and never re-reads ``passed``.

        All-or-nothing under the allocator lock: every non-None ref is
        validated first (slot range, geometry, and ``ref.generation`` equal
        to the slot's current generation -- the value applied by
        :meth:`apply_drops`).  On any validation failure nothing is
        installed and ``False`` is returned.
        """
        with self._lock:
            if len(keys) != len(refs):
                return False
            for ref in refs:
                if ref is None:
                    continue
                if not 0 <= ref.extent_id < self.num_slots:
                    return False
                if (
                    ref.offset < 0
                    or ref.length < 0
                    or ref.offset + ref.length > self.extent_size
                ):
                    return False
                if ref.generation != self._generations[ref.extent_id]:
                    return False
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
            return True
```

### `ExtentAllocator.plan_relocation` — `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py:434-493` (60 lines)

```python
    def plan_relocation(
        self,
        victim_slots: Sequence[int],
        key_lengths: Sequence[Tuple[str, int]],
        excluded_slots: Sequence[int] = (),
        start_slot: Optional[int] = None,
    ) -> Optional[List[ExtentRef]]:
        """Pure placement of relocated refs outside the victim generation.

        Circular reclaim bumps a victim slot's generation and reuses its
        bytes, destroying every live index entry that still points into that
        generation.  Before any of that happens the backend enumerates the
        victim's live refs and asks for replacement space here.

        Relocated refs are appended to the live tail (``_cursors``) of slots
        that are neither victims nor ``excluded_slots`` (the in-flight plan's
        own refs and the staged reservations), scanning forward circularly
        from ``start_slot``.  The method is pure: it never passes, drops,
        resets or recurses into a slot, and it never bumps a generation -- the
        returned refs carry each destination slot's *current* generation.

        Returns a list aligned with ``key_lengths``, or ``None`` when the
        total free tail space is smaller than the requested bytes (fail
        closed: the caller must not touch the victim).  The caller performs
        the byte IO and the durable publish (SET -> BATCH_COMMIT) before
        applying the drops.
        """
        avoid = set(victim_slots) | set(excluded_slots)
        if not key_lengths:
            return []
        for _key, length in key_lengths:
            if length < 0 or length > self.extent_size:
                return None
        if start_slot is None:
            start_slot = self._next_slot
        order: List[int] = []
        for step in range(self.num_slots):
            slot = (start_slot + step) % self.num_slots
            if slot not in avoid:
                order.append(slot)
        refs: List[ExtentRef] = []
        floors = {slot: self._cursors[slot] for slot in order}
        index = 0
        for slot in order:
            room = self.extent_size - floors[slot]
            while index < len(key_lengths) and (room > 0 or key_lengths[index][1] == 0):
                length = key_lengths[index][1]
                if length > room:
                    break
                refs.append(
                    ExtentRef(slot, floors[slot], length, self._generations[slot])
                )
                floors[slot] += length
                room -= length
                index += 1
            if index >= len(key_lengths):
                break
        if index < len(key_lengths):
            return None
        return refs
```

### `ExtentAllocator.evict_slot_lru` — `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py:497-509` (13 lines)

```python
    def evict_slot_lru(self, trace_context: Optional[dict] = None) -> int:
        """Drop the slot holding the least-recently-used key; returns the
        number of live bytes freed (0 when there is nothing to evict)."""
        if not self._recency:
            return 0
        oldest_key = next(iter(self._recency))
        oldest = self._index.get(oldest_key)
        if oldest is None:
            self._recency.pop(oldest_key, None)
            return 0
        return self._drop_slot(
            oldest.extent_id, reason="lru_gc", trace_context=trace_context
        )
```

### `ExtentAllocator._drop_slot` — `python/sglang/srt/mem_cache/storage/extent/extent_allocator.py:541-586` (46 lines)

```python
    def _drop_slot(
        self,
        slot: int,
        reason: str = "unknown",
        trace_context: Optional[dict] = None,
    ) -> int:
        old_generation = self._generations[slot]
        freed = self._slot_bytes[slot]
        removed_keys = sorted(self._slot_keys[slot])
        for key in removed_keys:
            self._index.pop(key, None)
            self._recency.pop(key, None)
        self._slot_keys[slot].clear()
        self._slot_bytes[slot] = 0
        self._cursors[slot] = 0
        self._generations[slot] += 1
        for key in removed_keys:
            _t38c_durable_log(
                {
                    "evt": "storage_invalidate",
                    "trace_context": trace_context,
                    "operation": "allocator_drop_slot",
                    "pool": "storage",
                    "storage_key": key,
                    "extent_id": slot,
                    "extent_generation": self._generations[slot],
                    "old_generation": old_generation,
                    "new_generation": self._generations[slot],
                    "index_removed": True,
                    "reason": reason,
                    "result": True,
                }
            )
        if freed > 0:
            # [P3] extent_recycle: a slot's generation bumped (the index
            # entries captured before the reuse now fail the read-side
            # generation re-verification -- a storage miss). Emitted under
            # the allocator lock held by the backend's write path.
            logger.info(
                "[P3] ts_ms=%d evt=extent_recycle slot=%d generation=%d freed=%d",
                int(time.time() * 1000),
                slot,
                self._generations[slot],
                freed,
            )
        return freed
```

## 5. Architecture review questions

1. Does the scheduler’s unconditional per-pass `check_hicache_events` + storage ACK drain + restore reconciliation create material host-thread cost under this workload, or are measured idle intervals explained by ordinary lack of admissible requests? Separate inclusive NVTX from exclusive attribution.
2. Under `write_through`, what exact prerequisites allow host reclaim/Full duplicate reclaim? Can `deferred_acked` nodes or an un-drained ACK queue hold host capacity while a restore admission is waiting? Examine `55ff0b2f0d`, `c58cf9d5ce`, and `13d1b3263d` against exact current bodies above.
3. Does L3 prefetch/reconciliation ever park a request whose current L1 prefix already supplies the usable match? Current L1+L2 all-800 telemetry reports L2=0 and unknown prefix authority; this workload does not prove L1 shielding or a blocker. Use the full-tier WAIT lines and per-RID causal events only as correlations.
4. Extent persistence is physically preallocated / bounded by `file_size`; the prior full-tier run used a 32GiB sparse-configured extent file and produced artifacts on root-backed `/data`. Current disk layout is a hard blocker for another large run. `/dev/shm` is expressly prohibited for large Extent and is tmpfs, so no full-tier rerun should be launched before a separate durable volume is available.
5. No scheduler/cache production code was modified in this report task. This review package is source and evidence only; no experiments were run for this request. (Superseded: the T007 convergence phase that followed did modify scheduler/cache production code, and its complete diff is §6.)

## 6. Phase-final production diff (T007 convergence, frozen at acceptance)

This section is the reviewed production change for the T007 convergence phase, appended after acceptance passed. It supersedes §5 item 5 ("No scheduler/cache production code was modified in this report task"), which described the earlier report-only scope.

- Review baseline: `06f8999484` (the source the rest of this document lists).
- Phase-final HEAD: `c24c421dafd14bcbe31d07ecea5cebc1c6f667ee` (`3090-24g-hicache`, pushed; `origin` equal at the time of writing).
- Command: `git diff 06f8999484..HEAD -- python/` (838 lines; 11 files, +329/-109 before this appendix).
- The acceptance runs used exactly this production source: `20261125T-t007-l3-wb-swasync2-c8` ran at `14856c531a` with `source-status.txt` showing no modification under `python/` (only four unrelated control scripts), and `git diff 14856c531a..HEAD -- python/` is empty. Its seven recorded module digests in `source-identity.json` re-hash equal to the working tree at HEAD (checked at freeze time). The preceding acceptances (`20261125T-t007-l3-wb-markerall2-c8` 550.58 TPS, `20261125T-t007-l3-wb-final-c8` 550.03 TPS) differ only by the last two hunks in `triton_backend.py`, which the later 550.33 TPS run includes.

What each file contributes, and the measurement behind it:

| File | Change | Evidence |
|---|---|---|
| `kernels/jit/csrc/kvcacheio/staged_write_back.cuh` | Coalesce consecutive destination pages into one `cudaMemcpyAsync` per run in the staged write-back host copy; scattered pages keep the per-page loop | 4096-page backup 18.6ms -> 0.23ms CPU; 512-page 2.44ms -> 0.12ms; byte-exact vs staged rows for 128/512/4096 pages, contiguous and scattered |
| `layers/attention/triton_backend.py` | SWA window buffer update reads the token total once and reuses a cached 0-dim window-size tensor | `update_sliding_window_buffer` 2.54s -> 2.05s of 40.5s sampled scheduler CPU |
| `managers/scheduler.py` | Per-pass host-allocability snapshot reuse, reconcile split into a scoped pass with invalidation after resource-changing prefetch retries, L3-only (FRONTIER/BACKUP_PENDING) wait fast-forward, hold-record emission only when a record can change, reconcile NVTX range, marker checks via the memo | reconcile cost measured at 0.55% of a 120s window (hypothesis refuted, kept as neutral cleanup); 205 L3-only fast-forwards per full-tier run with zero sanity failures |
| `mem_cache/trace_context.py` | `marker_present()`: 1s memoized `os.path.exists` for operator trace markers | `os.path.exists` 6.2% of scheduler CPU -> one stat per second; trace still enable-able mid-run |
| `mem_cache/unified_radix_cache.py` | Evictable-signature memo keyed by pool generation + reset hook; marker checks via the memo | same reconcile measurement; `os.path.exists` leaf removed from the release/revoke path |
| `mem_cache/hybrid_cache/hybrid_cache_controller.py` | Marker checks via the memo (this file held its own copies, which is why the stat survived the first fix) | `os.path.exists` 1.22s -> 0.00s |
| `mem_cache/pool_host/mha.py` | Resolve the Gemma owner logical->physical transfer buffers once per pool instead of rebuilding a CUDA tensor, copying it, and running a synchronizing `torch.equal` per backup | `_resolve_device_transfer_buffers` 0.99s -> 0.00s |
| `mem_cache/storage/extent/extent_file_backend.py` | Linear LRU victim walk with one `statvfs` per selection, per-slot re-check during reclamation | full-pressure scan no longer quadratic; no over-eviction |
| `mem_cache/storage/extent/extent_allocator.py` | Marker checks via the memo | none of these are on a per-page path any more |
| `mem_cache/unified_cache/components/mamba_component.py` | Marker checks via the memo | as above |
| `managers/cache_controller.py` | Marker checks via the memo | as above |

Acceptance evidence for this diff (frozen `write_back` + `wait_complete`, Owner-only W4A16 FP8 E5M2, fixed Full/SWA pool, chunk4096, full L1/L2/L3, original C8 40x20): 800/800 with zero Radix sanity failures and the exact 800-payload multiset, **550.58 / 550.03 / 550.33 TPS at 77.84 / 77.19 / 76.79% duty** (plus one 526.22 variance sample), against 511.58 TPS before this diff. Real L3 restore re-validated on this build (`20261125T-t007-wb-l3-restore3`).

### Diff

```diff
diff --git a/python/sglang/kernels/jit/csrc/kvcacheio/staged_write_back.cuh b/python/sglang/kernels/jit/csrc/kvcacheio/staged_write_back.cuh
index 93322643a4..a1777c1831 100644
--- a/python/sglang/kernels/jit/csrc/kvcacheio/staged_write_back.cuh
+++ b/python/sglang/kernels/jit/csrc/kvcacheio/staged_write_back.cuh
@@ -81,12 +81,38 @@ inline void copy_page_first_pages_fallback(
     const size_t src_page_bytes = static_cast<size_t>(page_size * src_stride0 * elem_size);
     const size_t dst_page_bytes = static_cast<size_t>(page_size * dst_stride0 * elem_size);
     RuntimeCheck(src_page_bytes == dst_page_bytes, "Source and destination page spans must match");
-    for (const auto page_offset : irange(num_pages)) {
-      const char* src_ptr = static_cast<const char*>(src_ptrs[tensor_id].data_ptr()) +
-                            static_cast<size_t>(page_offset * page_size * src_stride0 * elem_size);
-      char* dst_ptr = static_cast<char*>(dst_ptrs[tensor_id].data_ptr()) +
-                      static_cast<size_t>(dst_indices_ptr[page_offset * page_size] * dst_stride0 * elem_size);
-      RuntimeDeviceCheck(cudaMemcpyAsync(dst_ptr, src_ptr, src_page_bytes, cudaMemcpyDeviceToHost, stream));
+    // Consecutive destination pages map to one contiguous host span, so a run
+    // of them is a single copy instead of one copy per page. Backups allocate
+    // their host slots as one block, which makes whole chunks land in a single
+    // run; a fragmented range still falls back to one copy per page for the
+    // pages that did not coalesce.
+    constexpr int64_t kMinCoalescedPages = 2;
+    int64_t run_begin = 0;
+    while (run_begin < num_pages) {
+      int64_t run_end = run_begin + 1;
+      while (run_end < num_pages &&
+             dst_indices_ptr[run_end * page_size] ==
+                 dst_indices_ptr[(run_end - 1) * page_size] + page_size) {
+        ++run_end;
+      }
+      const int64_t run_pages = run_end - run_begin;
+      if (run_pages >= kMinCoalescedPages) {
+        const char* src_ptr = static_cast<const char*>(src_ptrs[tensor_id].data_ptr()) +
+                              static_cast<size_t>(run_begin * page_size * src_stride0 * elem_size);
+        char* dst_ptr = static_cast<char*>(dst_ptrs[tensor_id].data_ptr()) +
+                        static_cast<size_t>(dst_indices_ptr[run_begin * page_size] * dst_stride0 * elem_size);
+        RuntimeDeviceCheck(cudaMemcpyAsync(
+            dst_ptr, src_ptr, static_cast<size_t>(run_pages) * src_page_bytes, cudaMemcpyDeviceToHost, stream));
+      } else {
+        for (const auto page_offset : irange(run_begin, run_end)) {
+          const char* src_ptr = static_cast<const char*>(src_ptrs[tensor_id].data_ptr()) +
+                                static_cast<size_t>(page_offset * page_size * src_stride0 * elem_size);
+          char* dst_ptr = static_cast<char*>(dst_ptrs[tensor_id].data_ptr()) +
+                          static_cast<size_t>(dst_indices_ptr[page_offset * page_size] * dst_stride0 * elem_size);
+          RuntimeDeviceCheck(cudaMemcpyAsync(dst_ptr, src_ptr, src_page_bytes, cudaMemcpyDeviceToHost, stream));
+        }
+      }
+      run_begin = run_end;
     }
   }
 }
@@ -104,6 +130,7 @@ inline bool try_copy_page_first_pages_batch(
 #else
   host::RuntimeCheck(src_ptrs.size() == dst_ptrs.size(), "Source and destination tensors must have the same count");
   constexpr size_t kLargeCopyThresholdBytes = 128 * 1024;
+  constexpr size_t kBatchMinCopies = 256;
   thread_local std::vector<CudaMemcpyBatchPtr> batch_srcs;
   thread_local std::vector<CudaMemcpyBatchPtr> batch_dsts;
   thread_local std::vector<size_t> batch_sizes;
diff --git a/python/sglang/srt/layers/attention/triton_backend.py b/python/sglang/srt/layers/attention/triton_backend.py
index e78719ea3d..179a862ec2 100644
--- a/python/sglang/srt/layers/attention/triton_backend.py
+++ b/python/sglang/srt/layers/attention/triton_backend.py
@@ -2132,6 +2132,19 @@ class TritonMultiStepDraftBackend:
             attn_backend.init_forward_metadata_in_graph(forward_batch)
 
 
+_WINDOW_SIZE_TENSORS: dict[tuple[str, int], torch.Tensor] = {}
+
+
+def _window_size_tensor(size: int, device) -> torch.Tensor:
+    """0-dim window size on the device: one allocation per (device, size)."""
+    key = (str(device), int(size))
+    tensor = _WINDOW_SIZE_TENSORS.get(key)
+    if tensor is None:
+        tensor = torch.tensor(int(size), dtype=torch.int64, device=device)
+        _WINDOW_SIZE_TENSORS[key] = tensor
+    return tensor
+
+
 def update_sliding_window_buffer(
     window_kv_indptr,
     req_to_token,
@@ -2160,13 +2173,17 @@ def update_sliding_window_buffer(
     """
     window_kv_lens = torch.minimum(
         seq_lens,
-        torch.tensor(sliding_window_size),
+        _window_size_tensor(sliding_window_size, seq_lens.device),
     )
     window_kv_indptr[1 : bs + 1] = torch.cumsum(window_kv_lens, dim=0)
     window_kv_indptr = window_kv_indptr[: bs + 1]
+    # Reading the token total off the prefix sums is a device->host sync. Read it
+    # once and reuse it for both the buffer size and the translate slice.
+    total_tokens = None
     if window_kv_indices is None:
+        total_tokens = int(window_kv_indptr[-1])
         window_kv_indices = torch.empty(
-            window_kv_indptr[-1], dtype=torch.int64, device=device
+            total_tokens, dtype=torch.int64, device=device
         )
     window_kv_start_idx = seq_lens - window_kv_lens
     create_flashinfer_kv_indices_triton[(bs,)](
@@ -2181,10 +2198,11 @@ def update_sliding_window_buffer(
     if not skip_full_to_swa_translation and hasattr(
         token_to_kv_pool, "translate_loc_from_full_to_swa"
     ):
-        kv_last_index = window_kv_indptr[-1]
-        window_kv_indices[:kv_last_index] = (
+        if total_tokens is None:
+            total_tokens = int(window_kv_indptr[-1])
+        window_kv_indices[:total_tokens] = (
             token_to_kv_pool.translate_loc_from_full_to_swa(
-                window_kv_indices[:kv_last_index]
+                window_kv_indices[:total_tokens]
             )
         )
     return window_kv_indptr, window_kv_indices, window_kv_lens, window_kv_start_idx
diff --git a/python/sglang/srt/managers/cache_controller.py b/python/sglang/srt/managers/cache_controller.py
index ecc38ef525..8f09fbde2d 100644
--- a/python/sglang/srt/managers/cache_controller.py
+++ b/python/sglang/srt/managers/cache_controller.py
@@ -41,6 +41,7 @@ from sglang.srt.layers.dp_attention import (
     is_dp_attention_enabled,
 )
 from sglang.srt.mem_cache.l2_transfer import L2Transfer, L2TransferEngine
+from sglang.srt.mem_cache.trace_context import marker_present
 from sglang.srt.mem_cache.memory_pool import MLATokenToKVPool
 from sglang.srt.runtime_context import get_parallel
 from sglang.srt.utils import get_device_module
@@ -72,7 +73,7 @@ def _t38c_log(rec):
         import json as _json
         import time as _time
         import os as _os
-        if not _os.path.exists("/tmp/t38c-on"):
+        if not marker_present("/tmp/t38c-on"):
             return
         rec["ts"] = round(_time.time(), 3)
         with open("/tmp/t38c-probe.log", "a") as _f:
diff --git a/python/sglang/srt/managers/scheduler.py b/python/sglang/srt/managers/scheduler.py
index 7928e499b1..3fb43695a0 100644
--- a/python/sglang/srt/managers/scheduler.py
+++ b/python/sglang/srt/managers/scheduler.py
@@ -309,6 +309,7 @@ from sglang.srt.managers.utils import (
     validate_input_length,
 )
 from sglang.srt.mem_cache import kv_cache_builder
+from sglang.srt.mem_cache.trace_context import marker_present
 from sglang.srt.mem_cache.telemetry_context import (
     configure_producer_context,
     host_alloc_lineage,
@@ -403,7 +404,7 @@ logger = logging.getLogger(__name__)
 # Gate on /tmp/t38c-on, the same file gate as the t38c probe: touch the file
 # to enable, remove it to disable (no restart needed).
 def _p2a_trace(fmt, *args):
-    if os.path.exists("/tmp/t38c-on"):
+    if marker_present("/tmp/t38c-on"):
         logger.info(fmt, *args)
 
 
@@ -551,7 +552,7 @@ def _t38c_log(rec):
         import json as _json
         import time as _time
         import os as _os
-        if not _os.path.exists("/tmp/t38c-on"):
+        if not marker_present("/tmp/t38c-on"):
             return
         rec["ts"] = round(_time.time(), 3)
         with open("/tmp/t38c-probe.log", "a") as _f:
@@ -3538,7 +3539,47 @@ class Scheduler(
         snapshot_fn = getattr(self.tree_cache, "host_allocability_snapshot", None)
         if snapshot_fn is None:
             return cursor.snapshot if cursor is not None else None
-        return snapshot_fn(sorted(pools))
+        key = tuple(sorted(pools))
+        pass_snapshots = getattr(self, "_host_alloc_pass_snapshots", None)
+        if pass_snapshots is not None:
+            cached = pass_snapshots.get(key)
+            if cached is not None:
+                return cached
+        snapshot = snapshot_fn(list(key))
+        if pass_snapshots is not None:
+            pass_snapshots[key] = snapshot
+        return snapshot
+
+    def _begin_host_alloc_pass(self) -> None:
+        """Open one reconciliation pass's snapshot-reuse scope.
+
+        The scheduler is the only mutator inside one pass, and every mutation
+        it performs advances the affected host-allocability generation, so a
+        snapshot taken here stays authoritative until the pass ends. The cache
+        side additionally drops its memoized evictable signatures at this
+        boundary, so an unreported mutation cannot leak across passes.
+        """
+        self._host_alloc_pass_snapshots = {}
+        self._host_alloc_pass_global_vector = None
+        self._host_alloc_pass_global_vector_ready = False
+        reset_fn = getattr(
+            self.tree_cache, "reset_host_allocability_signature_memo", None
+        )
+        if reset_fn is not None:
+            reset_fn()
+
+    def _end_host_alloc_pass(self, previous) -> None:
+        self._host_alloc_pass_snapshots = previous
+        self._host_alloc_pass_global_vector_ready = False
+        self._host_alloc_pass_global_vector = None
+
+    def _invalidate_host_alloc_pass_snapshots(self) -> None:
+        """Forget this pass's snapshots after a resource-changing action."""
+        pass_snapshots = getattr(self, "_host_alloc_pass_snapshots", None)
+        if pass_snapshots:
+            pass_snapshots.clear()
+        self._host_alloc_pass_global_vector_ready = False
+        self._host_alloc_pass_global_vector = None
 
     def _host_alloc_telemetry_identity(self):
         parallel_state = getattr(self, "ps", None)
@@ -3779,10 +3820,16 @@ class Scheduler(
         )
 
     def _host_alloc_global_generation_vector(self):
+        if getattr(self, "_host_alloc_pass_global_vector_ready", False):
+            return self._host_alloc_pass_global_vector
         snapshot_fn = getattr(self.tree_cache, "host_allocability_snapshot", None)
         if snapshot_fn is None:
             return None
-        return snapshot_fn().generation_vector()
+        vector = snapshot_fn().generation_vector()
+        if getattr(self, "_host_alloc_pass_snapshots", None) is not None:
+            self._host_alloc_pass_global_vector = vector
+            self._host_alloc_pass_global_vector_ready = True
+        return vector
 
     def _host_alloc_global_snapshot(self):
         snapshot_fn = getattr(self.tree_cache, "host_allocability_snapshot", None)
@@ -3996,6 +4043,58 @@ class Scheduler(
             return "hold_no_generation"
         return "hold_global_grant_used"
 
+    def _emit_host_alloc_hold(self, req, decision_name) -> None:
+        """Emit one non-granted HOST_ALLOC waiter record.
+
+        Repeat records are coalesced downstream by ``_log_host_alloc_telemetry``
+        (identical decision/wait/generation signature), so this path only pays
+        for the state it reports when a record can actually change.
+        """
+        worker, rank = self._host_alloc_telemetry_identity()
+        cursor = getattr(req, "hicache_host_alloc_wait_cursor", None)
+        current = self._host_alloc_snapshot_for_req(req)
+        _log_host_alloc_telemetry(
+            "restore_host_alloc_wake_decision",
+            worker=worker,
+            rank=rank,
+            rid=req.rid,
+            attempt_id=getattr(req, "hicache_host_alloc_attempt_id", None),
+            cache_instance_id=(
+                current.cache_instance_id if current is not None else None
+            ),
+            trace_context=self._host_alloc_trace_context(req),
+            decision=decision_name,
+            captured_generations=(
+                dict(cursor.snapshot.generation_by_pool) if cursor else {}
+            ),
+            current_generations=(
+                dict(current.generation_by_pool) if current is not None else {}
+            ),
+            blocked_domains=sorted(map(str, cursor.blocked_domains)) if cursor else [],
+            required_aux_units=(dict(cursor.required_aux_units) if cursor else {}),
+            requested_primary_tokens=(
+                int(cursor.requested_primary_tokens) if cursor else 0
+            ),
+            fifo_sequence=cursor.fifo_sequence if cursor else None,
+            generation_vector_id=self._host_alloc_generation_vector_id(
+                current.generation_vector() if current is not None else None
+            ),
+            global_grant_used=decision_name == "hold_global_grant_used",
+            budget_available=decision_name != "hold_budget",
+            free_units=(dict(current.free_units_by_pool) if current is not None else {}),
+            evictable_units=(
+                dict(current.evictable_units_by_pool) if current is not None else {}
+            ),
+            retry_grant=False,
+            retry_skip=decision_name != "grant",
+            retry_outcome=decision_name,
+            lifecycle_key=self._host_alloc_lifecycle_key(req),
+            wait_id=getattr(req, "hicache_host_alloc_wait_id", None),
+            wake_event_id=None,
+            attempt_number=0,
+            attempt_origin="HOST_ALLOC_WAKE_HOLD",
+        )
+
     def _emit_host_alloc_wake_grant(self, req) -> Optional[str]:
         """Emit the authoritative grant record for one woken waiter.
 
@@ -4102,6 +4201,7 @@ class Scheduler(
         )
         return event_id
 
+    @scheduler_nvtx_method("scheduler.reconcile_restore_states")
     def _reconcile_restore_states(self):
         """Per-pass restore-state reconciliation (P2-1 M1b/M2; evolved from
         _retry_missed_storage_prefetches). Feeds terminal prefetch outcomes
@@ -4117,6 +4217,15 @@ class Scheduler(
                 )
             return
 
+        previous_scope = getattr(self, "_host_alloc_pass_snapshots", None)
+        self._begin_host_alloc_pass()
+        try:
+            self._reconcile_restore_states_in_pass()
+        finally:
+            self._end_host_alloc_pass(previous_scope)
+
+    def _reconcile_restore_states_in_pass(self):
+        """Body of ``_reconcile_restore_states`` inside one snapshot scope."""
         # 1) Terminal outcomes recorded by the drain this pass (same thread).
         for req in self.waiting_queue:
             self._feed_restore_terminal(req)
@@ -4145,6 +4254,9 @@ class Scheduler(
                     req.storage_prefetch_retry_attempts,
                 )
                 self._prefetch_kvcache(req, origin=HiCachePrefetchOrigin.DEMAND_RETRY)
+                # The retry may have claimed or freed host slots, so a later
+                # admission decision in this pass must re-read allocability.
+                self._invalidate_host_alloc_pass_snapshots()
 
         # 3) M2: frontier-ACK wakes (T12). The ack drain moved the waiter
         # into the ready set earlier in this same event pass.
@@ -4178,6 +4290,7 @@ class Scheduler(
                     origin=HiCachePrefetchOrigin.DEMAND_RETRY,
                     demand_restore=self.enable_ready_horizon or was_backup_pending,
                 )
+                self._invalidate_host_alloc_pass_snapshots()
                 if req.hicache_restore_state is RestoreState.NONE:
                     # The wake re-issue was declined too-short: terminal
                     # (T4 on the re-issue leg), released to recompute now
@@ -4205,68 +4318,9 @@ class Scheduler(
                 # leaves only via the paced retry or the T13 timeout.
                 continue
             if req.hicache_restore_wait_reason is RestoreWaitReason.HOST_ALLOC:
-                worker, rank = self._host_alloc_telemetry_identity()
-                cursor = getattr(req, "hicache_host_alloc_wait_cursor", None)
-                current = self._host_alloc_snapshot_for_req(req)
-                current_generations = (
-                    dict(current.generation_by_pool) if current is not None else {}
-                )
-                captured_generations = (
-                    dict(cursor.snapshot.generation_by_pool) if cursor else {}
-                )
-                vector = (
-                    current.generation_vector() if current is not None else None
-                )
                 if req.rid != host_alloc_grant:
-                    decision_name = self._host_alloc_skip_decision(req)
-                    _log_host_alloc_telemetry(
-                        "restore_host_alloc_wake_decision",
-                        worker=worker,
-                        rank=rank,
-                        rid=req.rid,
-                        attempt_id=getattr(
-                            req, "hicache_host_alloc_attempt_id", None
-                        ),
-                        cache_instance_id=(
-                            current.cache_instance_id if current is not None else None
-                        ),
-                        trace_context=self._host_alloc_trace_context(req),
-                        decision=decision_name,
-                        captured_generations=captured_generations,
-                        current_generations=current_generations,
-                        blocked_domains=sorted(
-                            map(str, cursor.blocked_domains)
-                        )
-                        if cursor
-                        else [],
-                        required_aux_units=(
-                            dict(cursor.required_aux_units) if cursor else {}
-                        ),
-                        requested_primary_tokens=(
-                            int(cursor.requested_primary_tokens) if cursor else 0
-                        ),
-                        fifo_sequence=cursor.fifo_sequence if cursor else None,
-                        generation_vector_id=self._host_alloc_generation_vector_id(
-                            vector
-                        ),
-                        global_grant_used=decision_name == "hold_global_grant_used",
-                        budget_available=decision_name != "hold_budget",
-                        free_units=(
-                            dict(current.free_units_by_pool) if current is not None else {}
-                        ),
-                        evictable_units=(
-                            dict(current.evictable_units_by_pool)
-                            if current is not None
-                            else {}
-                        ),
-                        retry_grant=False,
-                        retry_skip=decision_name != "grant",
-                        retry_outcome=decision_name,
-                        lifecycle_key=self._host_alloc_lifecycle_key(req),
-                        wait_id=getattr(req, "hicache_host_alloc_wait_id", None),
-                        wake_event_id=None,
-                        attempt_number=0,
-                        attempt_origin="HOST_ALLOC_WAKE_HOLD",
+                    self._emit_host_alloc_hold(
+                        req, self._host_alloc_skip_decision(req)
                     )
                     continue
                 self._emit_host_alloc_wake_grant(req)
@@ -4315,6 +4369,7 @@ class Scheduler(
                     origin=HiCachePrefetchOrigin.DEMAND_RETRY,
                     demand_restore=self.enable_ready_horizon or was_backup_pending,
                 )
+                self._invalidate_host_alloc_pass_snapshots()
                 if req.hicache_restore_state is RestoreState.NONE:
                     # Same terminal rule as the T12 wake leg: a capacity
                     # wake whose re-issued prefetch is declined too-short
@@ -6681,6 +6736,31 @@ class Scheduler(
 
         return NextBatchPlan(batch_to_run=ret, running_batch=running_batch)
 
+    def _release_l3_only_restore_wait(self, req) -> bool:
+        """Release a stale L3-only wait so current prefix admission can run.
+
+        FRONTIER and BACKUP_PENDING describe the durability frontier, not the
+        validity of the request's current L1/L2 match. Clear only that wait;
+        PrefillAdder remains authoritative for real device/aux capacity and
+        owns any rollback/cleanup for an admission that still cannot fit.
+        """
+        if req.hicache_restore_wait_reason not in (
+            RestoreWaitReason.FRONTIER,
+            RestoreWaitReason.BACKUP_PENDING,
+        ):
+            return False
+        self.tree_cache.discard_frontier_waiter(req.rid)
+        discard_backup_wait = getattr(
+            self.tree_cache, "discard_backup_wait", None
+        )
+        if discard_backup_wait is not None:
+            discard_backup_wait(req.rid)
+        decision = self._apply_restore_event(req, RestoreEvent.TIMEOUT)
+        if decision is RestoreDecision.ADMIT_RECOMPUTE:
+            self._log_restore_recompute(req, "l3_wait_fast_forward")
+            return True
+        return False
+
     def _get_new_batch_prefill_raw(
         self,
         prefill_delayer_single_pass: Optional[PrefillDelayerSinglePassExecutor],
@@ -6866,10 +6946,16 @@ class Scheduler(
                 # revoke) before the WAIT skip below.
                 self._feed_restore_terminal(req)
                 if req.hicache_restore_state is RestoreState.WAIT_CAPACITY:
-                    # Restore intent denied for capacity: keep waiting for a
-                    # wake (T11/T12) instead of admitting into a full
-                    # recompute; bounded by the WAIT timeout (T13).
-                    continue
+                    # FRONTIER/BACKUP_PENDING are L3-only waits. They can
+                    # describe persistence that is stale relative to the
+                    # current L1/L2 prefix. Drop that restore intent and let
+                    # PrefillAdder make the authoritative device-capacity
+                    # decision below; L3 remains asynchronously persistent
+                    # and eligible for later requests. Other capacity waits
+                    # (DEVICE_QUOTA/HOST_ALLOC/PREFETCH_BUDGET) retain their
+                    # existing wake/timeout path.
+                    if not self._release_l3_only_restore_wait(req):
+                        continue
                 # Pop the number of tokens loaded from storage (L3 hits)
                 loaded_tokens = self.tree_cache.pop_prefetch_loaded_tokens(req.rid)
                 if loaded_tokens > 0:
diff --git a/python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py b/python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py
index 12fc0c6db2..fc923a0af6 100644
--- a/python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py
+++ b/python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py
@@ -42,6 +42,7 @@ from sglang.srt.mem_cache.trace_context import (
     INERT_RELEASE_TOKEN,
     ordered_key_set_digest,
     remember_slot_context,
+    marker_present,
 )
 from sglang.srt.mem_cache.telemetry_context import next_event_id, producer_context
 from sglang.srt.mem_cache.p2a_timing_probe import begin_storage_query_probe
@@ -63,7 +64,7 @@ def _t38c_log(rec):
         import json as _json
         import time as _time
         import os as _os
-        if not _os.path.exists("/tmp/t38c-on"):
+        if not marker_present("/tmp/t38c-on"):
             return
         rec["ts"] = round(_time.time(), 3)
         with open("/tmp/t38c-probe.log", "a") as _f:
@@ -75,7 +76,7 @@ def _t38c_log(rec):
 def _t38c_durable_log(rec):
     """Marker-gated p0_durable.v2 trace; identities/counters only."""
     try:
-        if not os.path.exists("/tmp/t38c-durable-trace"):
+        if not marker_present("/tmp/t38c-durable-trace"):
             return
         thread_id = threading.get_ident()
         with _T38C_DURABLE_SEQ_LOCK:
@@ -141,7 +142,7 @@ def _t38c_durable_log(rec):
 
 
 def _t38c_slot_digest(pool, values) -> str | None:
-    if not os.path.exists("/tmp/t38c-durable-trace"):
+    if not marker_present("/tmp/t38c-durable-trace"):
         return None
     import hashlib
 
diff --git a/python/sglang/srt/mem_cache/pool_host/mha.py b/python/sglang/srt/mem_cache/pool_host/mha.py
index 5304c86802..30014c87ec 100644
--- a/python/sglang/srt/mem_cache/pool_host/mha.py
+++ b/python/sglang/srt/mem_cache/pool_host/mha.py
@@ -412,6 +412,21 @@ class MHATokenToKVPoolHost(HostKVCache):
                 self.packed_device_k_buffers,
                 self.packed_device_v_buffers,
             )
+        # The owner logical->physical order and the per-layer buffer list are
+        # fixed once the pool is built, but resolving them allocates two CUDA
+        # tensors, copies one, and compares them on device (a synchronizing
+        # bounce) -- per backup. Resolve once per pool instead.
+        cached = getattr(device_pool, "_hicache_transfer_buffers", None)
+        if cached is not None:
+            return cached
+        resolved = self._resolve_device_transfer_buffers_uncached(device_pool)
+        try:
+            device_pool._hicache_transfer_buffers = resolved
+        except AttributeError:
+            pass
+        return resolved
+
+    def _resolve_device_transfer_buffers_uncached(self, device_pool):
         if hasattr(device_pool, "logical_owner_layer_ids"):
             logical_to_physical = device_pool._hicache_logical_to_physical
             logical_ids = device_pool.logical_owner_layer_ids
diff --git a/python/sglang/srt/mem_cache/storage/extent/extent_allocator.py b/python/sglang/srt/mem_cache/storage/extent/extent_allocator.py
index a1ab4c6349..d29133dc38 100644
--- a/python/sglang/srt/mem_cache/storage/extent/extent_allocator.py
+++ b/python/sglang/srt/mem_cache/storage/extent/extent_allocator.py
@@ -40,7 +40,7 @@ from typing import Callable, List, Optional, Sequence, Tuple
 
 import msgspec
 
-from sglang.srt.mem_cache.trace_context import attach_trace_context
+from sglang.srt.mem_cache.trace_context import attach_trace_context, marker_present
 
 logger = logging.getLogger(__name__)
 
@@ -49,7 +49,7 @@ _T38C_DURABLE_SEQ_LOCK = threading.Lock()
 
 
 def _t38c_durable_log(rec):
-    if not os.path.exists("/tmp/t38c-durable-trace"):
+    if not marker_present("/tmp/t38c-durable-trace"):
         return
     try:
         thread_id = threading.get_ident()
diff --git a/python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py b/python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py
index 83292a90b8..1cd60298ff 100644
--- a/python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py
+++ b/python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py
@@ -105,7 +105,7 @@ from sglang.srt.mem_cache.storage.extent.extent_metadata import (
     write_manifest_atomic,
 )
 from sglang.srt.mem_cache.storage.file.lru_file_evictor import _parse_size_to_bytes
-from sglang.srt.mem_cache.trace_context import attach_trace_context
+from sglang.srt.mem_cache.trace_context import attach_trace_context, marker_present
 from sglang.srt.utils.common import human_readable_int
 
 logger = logging.getLogger(__name__)
@@ -292,7 +292,7 @@ def _t38c_log(rec):
     try:
         import json as _json
 
-        if not os.path.exists("/tmp/t38c-on"):
+        if not marker_present("/tmp/t38c-on"):
             return
         rec["ts"] = round(time.time(), 3)
         with open("/tmp/t38c-probe.log", "a") as _f:
@@ -304,7 +304,7 @@ def _t38c_log(rec):
 def _t38c_durable_log(rec):
     """Marker-gated p0_durable.v2 trace; identities/counters only."""
     try:
-        if not os.path.exists("/tmp/t38c-durable-trace"):
+        if not marker_present("/tmp/t38c-durable-trace"):
             return
         thread_id = threading.get_ident()
         with _T38C_DURABLE_SEQ_LOCK:
@@ -1768,7 +1768,7 @@ class ExtentFileBackend(HiCacheStorage):
             query_context = getattr(extra_info, "extra_info", None) or {}
 
             def log_mamba_query(logical_key: str, present_result: bool) -> None:
-                if not os.path.exists("/tmp/t38c-durable-trace"):
+                if not marker_present("/tmp/t38c-durable-trace"):
                     return
                 storage_key = self._component_key(PoolName.MAMBA, logical_key)
                 ref = self._allocator.lookup(storage_key)
@@ -2694,18 +2694,24 @@ class ExtentFileBackend(HiCacheStorage):
         victims = []
         selected = set()
         used = self._allocator.used_bytes
-        recency = list(self._allocator._recency)
-        while recency:
+        # Filesystem free space is invariant during this read-only victim
+        # selection (the write has not started yet). Sample it once rather
+        # than issuing statvfs for every LRU key. Walk OrderedDict directly:
+        # copying every key and pop(0) made a full-pressure scan quadratic.
+        free_bytes = None
+        if self._min_free_bytes > 0:
+            st = os.statvfs(self._storage_dir)
+            free_bytes = st.f_bavail * st.f_frsize
+        free_space_pressure = (
+            free_bytes is not None and free_bytes < self._min_free_bytes
+        )
+        for key in self._allocator._recency:
             pressure = (
                 self._max_size_bytes > 0
                 and used > int(self._max_size_bytes * self._eviction_ratio)
-            )
-            if not pressure and self._min_free_bytes > 0:
-                st = os.statvfs(self._storage_dir)
-                pressure = st.f_bavail * st.f_frsize < self._min_free_bytes
+            ) or free_space_pressure
             if not pressure:
                 break
-            key = recency.pop(0)
             ref = self._allocator._index.get(key)
             if ref is None or ref.extent_id in selected:
                 continue
@@ -2723,6 +2729,11 @@ class ExtentFileBackend(HiCacheStorage):
         """
         if self._max_size_bytes <= 0 and self._min_free_bytes <= 0:
             return
+        # Free space is re-read after each reclaimed slot: this loop runs once
+        # per evicted extent (bytes needed / extent_size, a handful), not once
+        # per LRU key, so the statvfs cost stays bounded while the sweep still
+        # stops as soon as free space recovers instead of over-evicting to a
+        # stale pressure reading.
         while True:
             pressure = (
                 self._max_size_bytes > 0
@@ -2731,8 +2742,7 @@ class ExtentFileBackend(HiCacheStorage):
             )
             if not pressure and self._min_free_bytes > 0:
                 st = os.statvfs(self._storage_dir)
-                if st.f_bavail * st.f_frsize < self._min_free_bytes:
-                    pressure = True
+                pressure = st.f_bavail * st.f_frsize < self._min_free_bytes
             if not pressure:
                 return
             evicted = self._allocator.evict_slot_lru(trace_context=trace_context)
diff --git a/python/sglang/srt/mem_cache/trace_context.py b/python/sglang/srt/mem_cache/trace_context.py
index 30d68d9f11..eeb5612cf6 100644
--- a/python/sglang/srt/mem_cache/trace_context.py
+++ b/python/sglang/srt/mem_cache/trace_context.py
@@ -5,11 +5,31 @@ from __future__ import annotations
 import os
 import threading
 import hashlib
+import time
 from typing import Any, Optional
 
 TRACE_MARKER = "/tmp/t38c-durable-trace"
 TRACE_SCHEMA = "p0_durable.v3"
 
+# The marker files are operator-created files, but they are consulted from the
+# per-pass release/revoke path (dozens of call sites, one per released page
+# group or drain). A stat per call showed up as a measurable scheduler cost, so
+# presence is memoized for a short window: enabling a trace still takes effect
+# within a second, and a disabled trace still costs one stat per interval.
+_MARKER_TTL_S = 1.0
+_MARKER_CACHE: dict[str, tuple[float, bool]] = {}
+
+
+def marker_present(path: str) -> bool:
+    """Memoized ``os.path.exists`` for an operator trace marker."""
+    now = time.monotonic()
+    cached = _MARKER_CACHE.get(path)
+    if cached is not None and now - cached[0] < _MARKER_TTL_S:
+        return cached[1]
+    present = os.path.exists(path)
+    _MARKER_CACHE[path] = (now, present)
+    return present
+
 _SLOT_CONTEXTS: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
 _SLOT_CONTEXTS_LOCK = threading.Lock()
 _SLOT_SEQUENCE = 0
@@ -26,7 +46,7 @@ def is_inert_release_token(token: Optional[tuple[Any, ...]]) -> bool:
 
 
 def durable_trace_enabled() -> bool:
-    return os.path.exists(TRACE_MARKER)
+    return marker_present(TRACE_MARKER)
 
 
 def ordered_key_set_digest(keys) -> tuple[str, int]:
diff --git a/python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py b/python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py
index 80849e878a..3549814370 100644
--- a/python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py
+++ b/python/sglang/srt/mem_cache/unified_cache/components/mamba_component.py
@@ -29,6 +29,7 @@ from sglang.srt.mem_cache.trace_context import (
     attach_trace_context,
     durable_trace_enabled,
     slot_context,
+    marker_present,
 )
 from sglang.srt.mem_cache.telemetry_context import producer_context
 from sglang.srt.mem_cache.unified_cache.cache_action import (
@@ -71,7 +72,7 @@ _T38C_DURABLE_SEQ_LOCK = threading.Lock()
 
 
 def _t38c_durable_enabled() -> bool:
-    return os.path.exists("/tmp/t38c-durable-trace")
+    return marker_present("/tmp/t38c-durable-trace")
 
 
 def _t38c_slot_digest(pool, values) -> str | None:
diff --git a/python/sglang/srt/mem_cache/unified_radix_cache.py b/python/sglang/srt/mem_cache/unified_radix_cache.py
index 050731b804..ea038b811d 100644
--- a/python/sglang/srt/mem_cache/unified_radix_cache.py
+++ b/python/sglang/srt/mem_cache/unified_radix_cache.py
@@ -58,6 +58,7 @@ from sglang.srt.mem_cache.radix_cache import RadixKey
 from sglang.srt.mem_cache.swa_memory_pool import SWAKVPool
 from sglang.srt.mem_cache.trace_context import (
     attach_trace_context,
+    marker_present,
     complete_trace_context,
     complete_slot_context,
     durable_trace_enabled,
@@ -351,8 +352,8 @@ def _t38c_log(rec):
     try:
         import json as _json
         import time as _time
-        import os as _os
-        if not _os.path.exists("/tmp/t38c-on"):
+
+        if not marker_present("/tmp/t38c-on"):
             return
         rec["ts"] = round(_time.time(), 3)
         with open("/tmp/t38c-probe.log", "a") as _f:
@@ -362,9 +363,8 @@ def _t38c_log(rec):
 
 
 def _t38c_durable_enabled() -> bool:
-    import os as _os
-
-    return _os.path.exists("/tmp/t38c-durable-trace")
+    # Memoized: this gate is consulted from the per-pass release/revoke path.
+    return marker_present("/tmp/t38c-durable-trace")
 
 
 def _t38c_slot_digest(pool, values) -> str | None:
@@ -403,7 +403,7 @@ def _t38c_durable_log(rec):
         import json as _json
         import os as _os
 
-        if not _os.path.exists("/tmp/t38c-durable-trace"):
+        if not marker_present("/tmp/t38c-durable-trace"):
             return
         thread_id = threading.get_ident()
         with _T38C_DURABLE_SEQ_LOCK:
@@ -1805,6 +1805,12 @@ class UnifiedRadixCache(BasePrefixCache):
         # compare equal to the new cache state.
         self._host_allocability_instance_id = 0
         self._host_allocability_generations: dict[str, int] = {}
+        # Per-pool evictable signature memo keyed by the pool generation that
+        # produced it. A bump invalidates the entry, so a signature is scanned
+        # once per (pool, generation) instead of once per waiting request.
+        self._host_allocability_signature_memo: dict[
+            str, tuple[int, tuple[int, frozenset[int]]]
+        ] = {}
         self._host_allocability_telemetry_seq = 0
         self._host_allocability_telemetry_mutations = {}
         self._host_allocability_telemetry_emitted = {}
@@ -2699,6 +2705,7 @@ class UnifiedRadixCache(BasePrefixCache):
         """Full reset: destroy entire tree and all state."""
         self._host_allocability_instance_id += 1
         self._host_allocability_generations = {PoolName.KV.value: 0}
+        getattr(self, "_host_allocability_signature_memo", {}).clear()
         self._host_allocability_telemetry_seq = 0
         self._host_allocability_telemetry_mutations = {}
         self._host_allocability_telemetry_emitted = {}
@@ -3895,6 +3902,40 @@ class UnifiedRadixCache(BasePrefixCache):
             eligible,
         )
 
+    def _host_evictable_signature_cached(
+        self, pool: str
+    ) -> tuple[int, frozenset[int]]:
+        """Return the evictable signature, reusing the scan for one generation.
+
+        The signature is a pure function of tree/host-LRU state, and every
+        mutation that changes it advances that pool's allocability generation
+        (``_bump_host_allocability`` / ``_bump_changed_host_allocability``).
+        Keying the memo by that generation therefore returns what a fresh scan
+        would produce, while a burst of waiters in one scheduler pass no
+        longer repeats the walk over ``evictable_host_leaves`` or the whole
+        host LRU per request. A generation bump invalidates the entry;
+        ``reset_host_allocability_signature_memo`` additionally drops the memo
+        at a scheduler pass boundary so a mutation that did not report itself
+        cannot outlive the pass that observed it.
+        """
+        pool = str(getattr(pool, "value", pool))
+        memo = getattr(self, "_host_allocability_signature_memo", None)
+        if memo is None:
+            memo = self._host_allocability_signature_memo = {}
+        generation = getattr(self, "_host_allocability_generations", {}).get(pool, 0)
+        cached = memo.get(pool)
+        if cached is not None and cached[0] == generation:
+            return cached[1]
+        signature = self._host_evictable_signature(pool)
+        memo[pool] = (generation, signature)
+        return signature
+
+    def reset_host_allocability_signature_memo(self) -> None:
+        """Drop memoized evictable signatures at a state-change boundary."""
+        memo = getattr(self, "_host_allocability_signature_memo", None)
+        if memo:
+            memo.clear()
+
     def _host_allocability_signatures(self) -> dict[str, tuple[int, frozenset[int]]]:
         pools = [PoolName.KV.value]
         pools.extend(
@@ -3938,7 +3979,7 @@ class UnifiedRadixCache(BasePrefixCache):
         before = generations.get(pool, 0)
         generations[pool] = before + 1
         if evictable_after is None:
-            evictable_after = self._host_evictable_signature(pool)[0]
+            evictable_after = self._host_evictable_signature_cached(pool)[0]
         if evictable_before is None:
             evictable_before = evictable_after
         self._host_allocability_telemetry_seq += 1
@@ -4044,7 +4085,7 @@ class UnifiedRadixCache(BasePrefixCache):
         free_units = {}
         evictable_units = {}
         for pool in pools:
-            evictable_units[pool] = self._host_evictable_signature(pool)[0]
+            evictable_units[pool] = self._host_evictable_signature_cached(pool)[0]
             controller = self.cache_controller
             host_group = getattr(controller, "mem_pool_host", None)
             try:
```
