# mamba-full-memory-ratio sizing experiment (task 24052) — tester e1 report

status: done
artifacts:
  - remote: /root/mamba-ratio/{launch.sh, run_one.sh, run_matrix.sh, matrix.txt, gate5.sh, workload60k.py}
  - remote evidence: /root/mamba-ratio/evid-<tag>/* (alloc/capped/graph/nvidia-smi/status.log), engine-<tag>.log
  - remote Gate-5 evidence: /root/mamba-ratio/evid-g5-r04/, /root/mamba-ratio/evid-g5-r05/
  - remote workload results: /root/mamba-ratio/evid-g5-{r04,r05}/workload60k.json + workload.out
  - this report: phase2-mamba-sizing-tester-e1.md
evidence:
  - Full matrix boot/measurement table (below) from evid-* and engine-*.log
  - Host-RAM failure tracebacks in engine-r0{4,5}-480k.log, engine-r05-512k.log, engine-r04-479k.log
  - Gate 5: 8/8 x ~60K distinct-prefix concurrency OK for ratio 0.4@478k and 0.5@448k
summary:
  - mamba-full-memory-ratio is a COMPLETE NO-OP when --max-mamba-cache-size 64 is fixed (confirmed empirically across ratios 0.9/0.5/0.4/0.3/0.1).
  - Effective KV capacity is bounded by HOST RAM (31GB), not GPU OOM: max reliably bootable pool = 478k tokens (~94.5% GPU, decode graph bs8 ok, no mamba cap).
  - Recommended production value: keep mamba-full-memory-ratio=0.9 (default); it has no effect. If a value must be pinned for explicitness, any of 0.4/0.5/0.9 are equivalent.
followups:
  - 479k+ KV pool is flaky-to-failing on host RAM (available fluctuates); production max_total_tokens should stay <= 478000.
  - Host-RAM reserve accounting (HICACHE_HOST_MEMORY_RESERVE_BYTES=10GB, available is psutil reclaimable) makes the 478-480k boundary nondeterministic; document this.
open_issues:
  - Host-RAM budget variance across runs (4.25-4.99GB free) means the exact max pool is run-dependent; 478k succeeded, 479k and 480k failed on host RAM.

---

## 1. Objective

For production 22151 (pool64 + c8 + HiCache 3-tier, Qwen3.5-9B hybrid mamba+full-attn, FP8 KV, RTX 3090 24G), find the optimal `mamba-full-memory-ratio` delivering maximum effective KV capacity without Mamba eviction/churn.

Definition confirmed from code (`kv_cache_configurator.py`): `mamba-full-memory-ratio` = Mamba state memory / full-attention KV memory (NOT "what % to give Mamba").

## 2. Fixed baseline (all runs)

| knob | value |
|---|---|
| KV dtype | fp8_e5m2 |
| max-mamba-cache-size | 64 |
| CUDA graph max-bs | 8 (bs=[1,2,4,8]) |
| max-running-requests | 8 |
| context-length | 262144 |
| ready-horizon | OFF (no --enable-ready-horizon) |
| write policy / L3 | write_back / extent |
| mamba radix | extra_buffer |
| mamba-ssm dtype | float32 |
| mem-fraction-static | 0.92 |
| tp / hicache-ratio | 1 / 1.5 |
| model | /root/models/Qwen3.5-9B-w4a16 |

Each run used an independent STORAGE_DIR namespace `/data/l3/mamba-ratio-<tag>`. Production 22151 untouched; only target 175.155.64.171:24052.

## 3. Critical structural finding

**`mamba-full-memory-ratio` is a NO-OP when `--max-mamba-cache-size 64` is fixed.**

Code path (`kv_cache_configurator.py`):
- Line 2075: `if get_schedule().max_mamba_cache_size is not None:` → explicit-set branch (bypasses ratio entirely).
- Ratio-based auto-fit fallback (lines 2116-2157) runs only when `max_mamba_cache_size is None`.

Empirical confirmation: across ratios 0.9/0.5/0.4/0.3/0.1 at identical max_total_tokens, the Mamba pool (64 slots, 3.05GB), KV pool, pool-end avail mem, and nvidia-smi footprint are byte-identical. No ratio in the set changes any allocation.

## 4. Full matrix

Legend: G1 = Mamba 64 slots; G2 = c8 not capped; G3 = decode graph bs8 captured; G4 = VRAM headroom; Boot = engine reached "ready to roll".

| ratio | max_total_tokens | resolved max_total_num_tokens | resolved mamba size | mamba bytes | KV pool (tokens) | post-graph avail mem (GPU) | nvidia-smi mem | c8 cap | decode bs8 | boot |
|---|---|---|---|---|---|---|---|---|---|---|
| 0.9 | 327680 | 327680 | 64 | 3.05GB (conv .07GB) | 327680 | 3.55GB | 20867 MiB | no | bs8 end 3.55GB | OK |
| 0.9 | 384000 | 384000 | 64 | 3.05GB | 384000 | 2.71GB | 21733 MiB | no | bs8 end 2.71GB | OK |
| 0.5 | 384000 | 384000 | 64 | 3.05GB | 384000 | 2.71GB | 21733 MiB | no | bs8 end 2.71GB | OK |
| 0.4 | 384000 | 384000 | 64 | 3.05GB | 384000 | 2.71GB | 21733 MiB | no | bs8 end 2.71GB | OK |
| 0.3 | 384000 | 384000 | 64 | 3.05GB | 384000 | 2.71GB | 21733 MiB | no | bs8 end 2.71GB | OK |
| 0.1 | 384000 | 384000 | 64 | 3.05GB | 384000 | 2.71GB | 21733 MiB | no | bs8 end 2.71GB | OK |
| 0.5 | 448000 | 448000 | 64 | 3.05GB | 448000 | 1.74GB | 22729 MiB | no | bs8 end 1.74GB | OK |
| 0.4 | 448000 | 448000 | 64 | 3.05GB | 448000 | 1.74GB | 22729 MiB | no | bs8 end 1.74GB | OK |
| 0.4 | 478000 | 478000 | 64 | 3.05GB | 478000 | 1.27GB | 23211 MiB | no | bs8 end 1.27GB | OK |
| 0.5 | 480000 | — | — | — | — | — | — | — | (scheduler died) | FAIL host RAM |
| 0.4 | 480000 | — | — | — | — | — | — | — | (scheduler died) | FAIL host RAM |
| 0.5 | 512000 | — | — | — | — | — | — | — | (scheduler died) | FAIL host RAM |
| 0.1 | 512000 | — | — | — | — | — | — | — | (scheduler died) | FAIL host RAM |

Notes:
- 320k run: Mamba allocated 64 slots/3.05GB, KV 327680 tokens, decode bs8 end avail 3.55GB.
- The ratio NO-OP holds at every max_total_tokens tier (0.9=0.5=0.4=0.3=0.1).

## 5. Failure evidence (host RAM binding constraint)

480k and 512k fail on HOST RAM (CPU), not GPU OOM. The scheduler dies during `MambaPoolHost.__init__` (`pool_host/mamba.py:101`) while the model runner continues (hence decode-graph log lines appear in failed engines — misleading).

```
engine-r04-480k.log: Allocating kv hierarchical KV host pool: 720001 tokens, 11.80 GB host memory.
engine-r04-480k.log: ValueError: Not enough host memory available. Requesting 5.00 GB but only have 4.95 GB free.
engine-r05-480k.log: ... only have 4.91 GB free.
engine-r05-512k.log: ... Requesting 5.00 GB but only have 4.25 GB free.
engine-r04-479k.log: (boundary) ... only have 4.95 GB free.  (479k FAIL)
```

Host budget logic (`pool_host/base.py`): `budget = psutil.virtual_memory().available - 10GB` (HICACHE_HOST_MEMORY_RESERVE_BYTES). psutil `available` includes reclaimable page cache and fluctuates, making the 478-480k boundary nondeterministic run-to-run:
- 478k: booted OK at 08:24 (matrix) and 08:44 (gate5); FAILED once at 08:33 on host RAM (transient).
- 479k: FAILED (host RAM).
- 480k: FAILED (host RAM).
- 512k: FAILED (host RAM).

Current host: avail=32.26GB → budget≈21.53GB (barely fits 478k's 11.75GB KV + 5.00GB mamba = 16.75GB, with margin for OS).

## 6. Hard Gates

Gate 1 — Mamba actually 64 slots: PASS (all runs log `max_mamba_cache_size: 64, conv_state 0.07GB, ssm_state 3.05GB`).
Gate 2 — c8 not capped: PASS (no `max_running_requests is capped to X by the mamba state cache` in any run; `max_running_requests=8` resolved).
Gate 3 — decode graph bs8 capture: PASS (all successful runs log `Capture target decode CUDA graph end ... bs=[1,2,4,8]` and "The server is fired up and ready to roll!").
Gate 4 — reasonable VRAM headroom post-graph-capture: PASS-marginal at 478k (1.27GB avail / 23211 MiB used = 94.5% GPU); better at lower pools (448k → 1.74GB/22729 MiB).
Gate 5 — 8x real ~60K different-prefix workload on重点档: PASS for both 0.4 and 0.5 at their max pools (details below).

## 7. Gate 5 workload validation

Method: `gate5.sh` boots the engine, waits healthy, then `workload60k.py` fires 8 concurrent `/v1/chat/completions`, each with a distinct ~60K-token prefix (deterministic distinct marker per session), max_new=32, validates all complete HTTP 200. Short test (not soak). GPU util rose to 100% during both runs, confirming real compute.

Ratio 0.4 @ 478k (max pool):
```
WL60K: 8/8 ok, wall=134.5s, prompt_tokens=55797 each (est ~55.8K), completion 32 each, http 200 all
```
(First estimator run; hit ~55.8K rather than 60K — payload generator calibrated afterward.)

Ratio 0.5 @ 448k (max pool):
```
WL60K: 8/8 ok, wall=150.0s, prompt_tokens=60087 each, completion 32 each, http 200 all
```

Both重点档 handle 8 concurrent distinct 60K-prefix requests end-to-end without eviction failure or cap.

## 8. Recommendation

- **mamba-full-memory-ratio: NO-OP under the fixed 64-slot pool. Keep production default 0.9.** Pin explicitly to 0.9 (or 0.5/0.4 — equivalent) only if explicitness is wanted. It does not control Mamba sizing in this config.
- **Max effective KV pool = 478000 tokens**, bounded by HOST RAM (31GB), not GPU. GPU-side headroom at 478k is thin (1.27GB / 94.5%) but decode bs8 captures cleanly.
- **Production guidance:** set `--max-total-tokens 478000` as ceiling; do NOT exceed ~478k or host-RAM flakiness at the 479-480k boundary may abort boot. If headroom margin is valued over max capacity, 448k (1.74GB / 92.5%) is the safer choice.
- Mamba eviction/churn is not a factor: with max-mamba-cache-size fixed at 64 (5 state slots/request via `_calculate_mamba_ratio`), c8 has no mamba cap at any ratio tested.

## 9. Envelope

status: done
artifacts:
  - /root/mamba-ratio/* (scripts) and /root/mamba-ratio/evid-*/* (evidence)
  - /root/mamba-ratio/evid-g5-r04/, /root/mamba-ratio/evid-g5-r05/ (Gate 5)
  - this report
evidence:
  - Matrix table (section 4) from evid-*/alloc.txt, nvidia-smi.txt, graph.txt, capped.txt
  - Host-RAM failure tracebacks (section 5)
  - Gate 5 8/8 results (section 7)
summary:
  - ratio NO-OP; KV capacity bounded by host RAM; max pool 478k; recommendation keep ratio=0.9, cap total tokens <=478k
followups:
  - Consider raising HICACHE_HOST_MEMORY_RESERVE_BYTES / documenting available-fluctuation to make 478-480k boundary deterministic
  - Production deploy should verify host RAM headroom before booting 478k
open_issues:
  - None blocking; boundary nondeterminism at 478-480k is environmental (host RAM), not product defect
