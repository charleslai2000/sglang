# phase2-hicache-design-tester-gate3-soak-e1 — Gate-3 baseline soak
status: done
epoch: 1
task: gate3-baseline-soak (run+measure+report)

## 1. status
done (Run A baseline soak complete and fully analyzed; Run B RH-ON not run —
see open_issues for rationale)

## 2. artifacts
Local report: /home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/phase2-hicache-design-tester-gate3-soak-e1.md
Local evidence dir: /home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/.memory/phase2-hicache-design/work/gate3-soak-evidence/
Remote (3090 175.155.64.171):
  - /root/evidence-gate3-soak/          (Run A evidence: gpu-util.csv, runs.csv, join.log, mid-run-metrics.txt, metrics-final.txt, t38c-probe.log, engine-events.txt, collect-report.json)
  - /root/engine-gate3-soak.log         (Run A engine log)
  - /root/gate3_soak.sh                 (soak driver, config-only)
  - /root/direct-launch-gate1-rhon.sh   (RH-ON wrapper, config-only, NOT used)
  - /data/l3/p2io-gate3-soak/           (fresh namespace, 96G extent file)
  - /root/evidence-gate3-soak/run-20260904-185337/ (verdict.json, runs.csv, join.log)

## 3. evidence (Run A — baseline soak, RH OFF, 106-pool, 64G/96G)
- Duration: 18:53:37 → 20:54:27 = 7249.3 s ≈ 120.8 min (elapsed_s from verdict.json)
- Requests: 2499 total (32 phase-A writes + 2467 phase-B reads); rc=0; http=200 all 2499; finished=True all 2499
- GPU utilization (nvidia-smi, 5s samples, n=1446; core=1436 excluding boot/shutdown):
    core mean=97.1% median=100% p90=100%; samples<50% = 13 (0.91%); samples<90% = 88 (6.13%)
    idle dips only at boot (18:53) and shutdown (20:53-54); NO GPU-idle-while-queued during soak
- L3 restore latency (prefetch_issued -> prefetch_io_finished, fixed last-issued pairing, n=958):
    p50=1.388s p90=2.687s p95=3.312s p99=4.179s max=4.917s mean=1.567s min=0.152s
    (scheduler io_finished->restore_ready p50=0.217s)
    Latency stable over run: hour0 p50=1.52 / hour1 p50=1.26 (no GC-driven slowdown)
- Correctness signatures:
    OOM/CUDA-OOM: 0
    forced_drop_to_miss: 13 (all reason=no_durable_backup, small 2K nodes)
    backup failure (hicache_dropped_tokens_total host_pressure): KV=453,698 tokens + mamba=96 tokens (non-zero!)
    restore_loadback_fail: 10
    extent_recycle (GC): 6454 events, ~323.5 GB total freed (avg 50.1 MB/slot), ratio 0.165 of extent_write(39068)
    traceback lines: 62 (all benign torchcodec/libavutil FFmpeg load warnings at boot; no engine crash)
    no_token: 5806 (normal admission backpressure, can_run=1 mostly)
    prefill_deny_summary: only rem_total_tokens denials (memory cap), no starvation/OOM
    HTTP/finished errors: 0
- Class-A (revoked:miss with storage_hit>0):
    revoked:miss total = 1870 rids; matched to runs.csv 1870/1870
    class-A (storage>0) = 250 (13.4% of revoked:miss)
    class split: A_storage>0=250, B_device/host=1106, C_cold=514
    class-A storage_hit min=17 max=34743 mean=10053
    class-A over time: hour0=143, hour1=107 (stable/not growing)
- Restore ratio (join rows):
    L0 restore rows n=925 ratio=0.6184 (vs gate2 0.95) — DEGRADED, tied to GC+host saturation
    ALL restore rows n=1540 ratio=0.6281
    restore rows hit<100 (full miss): 320 (20.8%)
    L0 restore hit>=20000 (near-exact): 374 (40.4%); hit<10k: 313 (33.8%)
- Engine counter effective ratio (mid-run): 1.69-1.86 (authoritative counter, includes decode accounting)
- Throughput: agent_turns_per_s=0.345 (aggregate), active_width=7, p95_round_interval=43.2s
- Engine/storage gauges: host cache saturated (97821/98305 tokens = 99.5%); storage cached=6.94M tokens; backuped=25.49M; prefetched=9.45M

## 4. summary
Run A (baseline 106-pool/64G/96G soak, RH OFF) completed 2h at rc=0 with
excellent GPU utilization (mean 97.1%, median 100%, 0.91% samples<50%) and
ZERO HTTP/request errors, OOM, or crash — a clean soak on the request layer.
However, three Gate-3 stability/correctness issues surfaced that were NOT
visible in the short gate-2 runs: (1) the extent backend GC IS active at
64G (eviction watermark = 64G x 0.9 = 57.6G), firing 6454 LRU slot
evictions / ~323GB over the 2h — the "no-GC (recycle=0)" claim from gate2
only held because those runs were too short to cross the watermark;
(2) host_pressure backup drops are non-zero (453,698 KV tokens + 96 mamba
tokens destroyed without host backup) — the host L2 cache saturates at
99.5%; (3) L0 exact-restore ratio degraded to 0.6184 (vs 0.95 in gate2),
with 20.8% of restores full-missing and only 40.4% near-exact — attributed
to GC evicting committed L3 keys + host saturation forcing recompute, NOT
restore-latency (latency stayed flat at p50 1.39s). Ready Horizon (RH) was
NOT enabled in this baseline (defaults off), so the ~0.8s latency-hiding
comparison was not directly measured; instead I quantified the real L3
restore latency (p50 1.39s, p90 2.69s — higher than the 0.8s claim) and the
scheduler-side consume gap (0.22s), which bounds what RH could hide.

## 5. followups
- (orchestrator/coder) Decide whether the 64G extent watermark (0.9 ratio) is
  acceptable for production soak, or whether max_size / eviction_ratio must be
  raised for a true no-GC long soak. This is a config-level question, not a
  code change.
- (orchestrator) Consider whether to run Run B (RH ON) for the direct
  latency-hiding comparison. Given baseline latency is p50 1.39s (not 0.8s)
  and GPU idle-waiting is already negligible (0.91%), RH's marginal benefit
  on GPU util is expected to be small; recommend weighing before burning
  another 2h.
- (tester next) If RH-ON run is authorized: launch via
  direct-launch-gate1-rhon.sh + gate3_soak.sh --launch ... and compare GPU
  idle, restore latency, and queue behavior vs Run A.

## 6. open_issues
- GC confound: the "stable 64G/no-GC" baseline config actually triggers GC at
  57.6G watermark; gate-2 recycle=0 result is not representative of a
  multi-hour soak. This is the single most important new finding.
- host_pressure drops (453K KV tokens) — backup failure under host saturation.
- L0 restore ratio degradation (0.62 vs 0.95) — must be explained before
  declaring Gate-3 PASS; likely GC+host-saturation, needs root-cause
  attribution (config-level vs defect).
- Run B (RH ON) not executed — direct RH-vs-baseline latency-hiding comparison
  not measured; only latency magnitude + scheduler gap quantified.
- ssh flakiness: none encountered this epoch; all remote ops succeeded.
- The extent file is 96G logical (sparse); /data usage may have grown; not
  cleaned (no rm policy).
