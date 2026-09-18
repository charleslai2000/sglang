# M2 concurrency degradation RCA — controlled single-GPU experiment

Status: DONE
Terminal state: DONE

## VERDICT
**WARM-REMOVES-QUEUE + CACHE-STATE-ROOT-CAUSE** (both, combined).

- **WARM-REMOVES-QUEUE**: with the prefix cache warmed, M2's concurrency queue collapses
  to zero. At c=5 warm: TTFT p50 **0.314 s**, queue 0.0, decode/req **78.9 tok/s**; the
  cold baseline at c=5 was TTFT **3.461 s**, queue max **3.322**, decode/req **24.6**.
  M2 is not categorically bad at concurrency — its degradation is entirely a *cold-cache*
  effect.
- **CACHE-STATE-ROOT-CAUSE**: M2's prefix retention is bound by the **mamba slot budget**
  (`max_mamba_cache_size=48`, 4 slots/request), not by KV token capacity. Retention holds
  for N≤14 distinct prefixes and collapses at N=16 (1/16 retained) exactly when mamba free
  reaches ~2. This reproduces F39's M2 appearance; F39 compared M2 *cold* against M1
  *warm* and was therefore confounded by cache state.
- **The owner's HiCache hypothesis is CONFIRMED for the mechanism, not just correlation**:
  attaching HiCache (`hicache_attached=True`, host tier) lifts M2 retention from the
  N=16 cliff (1/16) to **24/24 retained with mamba free/evictable flat (~2/42)** — the host
  backup decouples prefix retention from the device mamba-slot budget.

## Owner's ruling (binding, supersedes prior framing)
- F39 M1/M2 comparison is INVALID / CONFOUNDED BY CACHE STATE. (Re-confirmed independently here.)
- FIRST question: why did M2 not retain the prefix/cache state M1 did? -> ANSWERED (mamba slot cliff).
- 262144->524288 is NO LONGER decisive. (Correct: no behavioural effect; see X-a.)
- Required controlled matrix: (1) M2 cold baseline [done], (2) M2 warm-prefix [PRIMARY, done],
  (3) 524288 only if warm still queues [NOT NEEDED — warm removed queue], (4) isolate
  hicache_attached / Mamba slot eviction [done].
- Mamba/HiCache survival idea was a HYPOTHESIS only -> now supported by a controlled isolation.

## New measurement-integrity finding (must be recorded)
The first warm-concurrency attempt on :30000 failed at `flush_cache` ("Flush cache failed"),
and a live-prod probe found **22-25 external worker-agent requests were hitting :30000 during
the window** (peer `192.168.1.203`, `# Tools` prompts, `max_new_tokens=32000`). All subsequent
controlled arms were therefore run on the scaffold's **designated diagnostic port 30164** with
**0 external rows**, and the clean run reproduced the contaminated run exactly (B/C/D results
identical), so the contamination did not change conclusions — but :30000 is NOT a measurement-
safe port while production traffic is live.

## Evidence

### X-a. 262144 -> 524288 REFUTED (owner step 3, not needed; recorded for completeness)
TTFT delta +0.6/-0.3/+0.4/+0.2% at c=1/2/4/5; decode ~0%. KV free grew 190k->449k with no
behaviour change. Conclusion: KV token capacity is not the binding resource.

### X-b. M2 cold baseline (distinct prefixes, c=1/2/4/5), 262144 no-HiCache
TTFT p50 1.081/1.849/2.977/3.461; decode/req 83.93/64.31/30.84/24.61; queue p50/max
0.001/0.228, 0.936/1.412 (**max 0.001/0.465/2.359/3.322**); running 1/2/4/5; graph_fallbacks=0;
mamba free_min 2; KV free_min ~190k.

### X-c. PRIMARY warm-concurrency test (owner step 2) — clean, :30164
Warm set N=8 verified 8/8 (cached 4480 each) BEFORE measuring; then c=1/2/4/5 re-sending the
warm set (16 requests/level, no-HiCache arm):
| c | ttft_p50 | queued_max | running_max | decode/req p50 | client cached hits | mamba_free_min |
|---|----------|-----------|-------------|----------------|--------------------|----------------|
| 1 | 0.131 | 0.0 | 1 | 83.60 | 16/16 | 21 |
| 2 | 0.224 | 0.0 | 2 | 81.25 | 16/16 | 18 |
| 4 | 0.233 | 0.0 | 4 | 78.72 | 16/16 | 12 |
| 5 | 0.314 | 0.0 | 5 | 78.92 | 16/16 | 9 |
graph_fallbacks=0 at every level. => **WARM-REMOVES-QUEUE**. (HiCache arm at same N=8 gave
TTFT 0.126/0.217/0.245/0.314 and decode 83.59/81.48/78.52/78.95 — statistically identical.)

### X-d. M2 warm-state micro-probe (clean, :30164, --enable-cache-report only)
Flush confirmed (KV free 262080/262144, mamba 47 free/1 evictable):
- B (shared prefix x2): B1 cold cached=0 -> B2 cached=3776. HIT.
- C (single distinct x2): C1 cold cached=0 -> C2 cached=4608. HIT.
- D (16 distinct once, then immediate re-send): D1 all cold, mamba free 47->2, evictable 1->43,
  KV free 249k -> 186k; D2 **1/16 hit**. Single distinct persists; 16 do not co-exist.
This exactly reproduces the earlier contaminated run -> measurement robust.

### X-e. Retention capacity curve N=1..14 (clean, no-HiCache) — mamba cliff
N=1/2/4/6/8/10/12/14 -> hits **N/N**; N=16 -> **1/16**. mamba free after R1:
42/39/33/27/21/18/9/3 -> then **2** at N=16. KV free still 190k at collapse.
=> Binding resource = mamba slots, not KV tokens. Sharp cliff between N=14 and N=16.

### X-f. ROOT CAUSE ISOLATION: M2 + HiCache (owner step 4), :30164
`--enable-hierarchical-cache --hicache-write-policy write_back --hicache-size 32`, console
confirms `hicache_attached=True`. Retention curve:
| N | no-HiCache hits | +HiCache hits | +HiCache mamba free/evict |
|---|-----------------|---------------|---------------------------|
| 8 | 8/8 | 8/8 | 21/23 |
| 12 | 12/12 | 12/12 | 9/35 |
| 16 | **1/16** | **16/16** | 2/42 |
| 20 | - | **20/20** | 5/43 |
| 24 | - | **24/24** | 2/42 |
=> With HiCache attached, the mamba cliff disappears: all prefixes retained to 24/24, and
mamba free/evictable stays flat (~2/42) at every N. The host tier absorbs evicted mamba
states, decoupling retention from the device slot budget. **This is the mechanism behind
M1's retention advantage** (M1 runs `--enable-hierarchical-cache`).

### X-g. Live production M2 (no HiCache) — M2 CAN retain in production
42 real worker-agent requests at 18:11-18:16Z: 40/42 cached_tokens>0
(`pt=20178 cached=10944`, `pt=31117 cached=30912`, `pt=47490 cached=40370`), retractions=0.
F39's M2 failure was a cold/warm-state artifact, not categorical inability.

## Causal chain (reconstructed)
1. M2's radix cache retains KV tokens cheaply, but every cached prefix also pins per-request
   Mamba SSM/conv state; with `max_mamba_cache_size=48` and 4 mamba layers/request, ~14
   distinct prefixes exhaust the slot pool.
2. On the 15th-16th distinct prefix the cache evicts earlier prefixes' mamba state; their KV
   entries survive but are unusable without matching SSM state, so re-sends are recomputed
   cold (cached=0) and queue again.
3. In F39, M1 (`--enable-hierarchical-cache`) had HiCache backing up evicted states, so it
   re-hydrated prefixes and showed retention; M2 (cold, no HiCache) did not. Comparing them
   compared different cache states.
4. When the prefix is actually warm (this experiment), M2 short-circuits prefill for every
   request, so no request waits behind another's prefill -> the concurrency queue disappears
   even though decode throughput still scales sub-linearly past bs~4 (GPU compute limit, not
   a scheduling defect).

## Defects / blockers
- None. All required arms completed; production restored.

## Competing hypotheses resolved
- H1 "M2 cannot retain prefixes" — REFUTED (X-g live 40/42; X-d single-prefix hits).
- H2 "KV token capacity is binding" — REFUTED (X-a: 524288 no effect; X-e KV 190k free at cliff).
- H3 "Mamba slot budget binds retention; HiCache lifts it" — **SUPPORTED** (X-e + X-f isolation).
- H4 "concurrency degradation is inherent to M2" — REFUTED; it is cold-cache-only
  (X-b vs X-c).

## Remaining claims / exclusions
- OUT OF SCOPE per owner: `reasoning_tokens ≈ budget+3`.
  (Observed incidentally on the restored prod: short prompts spend the whole budget on
  reasoning and return empty `content`; not investigated.)
- The exact per-prefix mamba slot accounting (4/request at bs<=1, 8 at req=2) was taken from
  prior F39 instrumentation, not re-derived here.
- No weights, training, commits, or product-source edits were made. No `cp -al`, no `chmod -R`.

## Restored-state record (production M2 on :30000)
- Started via `bash /tmp/opencode/prod-service-20260917/bin/start.sh m2` at 18:37:45Z.
- role=m2, pid=**1840571**, supervisor_pid=1840544, port=30000,
  run_id=m2-20260918T183744Z-1840331, tree=/opt/sglang/local-prod-v1.2.1-candidate-M2,
  namespace="" (L3 disabled), lock_generation=**1**, cold_start_s=106.8.
- gpu-owner.json: state=**held**, role=m2, pid=1840571, note="serving".
- Frozen argv verified byte-for-byte: `--max-total-tokens 262144 --max-running-requests 8
  --max-mamba-cache-size 48 --kv-cache-dtype fp8_e4m3 --mamba-radix-cache-strategy extra_buffer
  --disable-prefill-cuda-graph`; **`--enable-hierarchical-cache` absent (hicache_attached=False)**.
- Tree init: `hybrid_ssm=True hicache_attached=False`; max_total_num_tokens=262144.
- Health: **200** (3 consecutive probes). Chat smoke: real content generated
  (`"What is 2+2?"` -> `finish=stop`, content ends `4`, reasoning_tokens=130).
- No RCA server processes remain on :30000 or :30164; all diagnostic windows stopped.

## Artifacts
- `/tmp/opencode/M2-RCA-20260918/warm-state-M2-iso.json` / `capacity-M2-iso.json` (no-HiCache)
- `/tmp/opencode/M2-RCA-20260918/capacity-M2-hicache-iso.json` (HiCache root-cause arm)
- `/tmp/opencode/M2-RCA-20260918/warm-concurrency-M2-iso.json`, `warm-concurrency-M2-hicache-iso.json`
- `/tmp/opencode/M2-RCA-20260918/capacity-compare.txt` (side-by-side cliff vs HiCache)
- Logs under `/tmp/opencode/M2-RCA-20260918/logs/warm-iso-30164-*`, `hicache-iso-30164-*`
- Isolated server console logs record `hicache_attached` transitions.

Terminal state: DONE
