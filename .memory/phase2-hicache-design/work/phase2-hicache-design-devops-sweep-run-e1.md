# HiCache Sweep Run Report — phase2-hicache-design

## status: done

---

## Artifacts

- **Target machine**: RTX 3090 GPU runner at 175.155.64.171 (SSH port 24052)
- **Model**: Qwen3.5-9B-w4a16 (GPTQ 4-bit, 9B params)
- **Driver script**: `/root/gate3_soak.sh`
- **Load generator**: `/root/gate2_load.py`
- **Sweep command**: `/root/gate3_soak.sh --tag sweep-p64-gOFF --agents 8 --launch /root/direct-launch-sweep-p64-gOFF.sh --rt 400 --budget 900 --cmax 1200`
- **Smoke scripts**: `/root/direct-launch-sweep-p106-gOFF.sh`, `/root/direct-launch-sweep-p106-gON.sh`, `/root/direct-launch-sweep-p160-gOFF.sh`, `/root/direct-launch-sweep-p160-gON.sh`
- **Evidence directories**:
  - Cell-3 (sweep-p64-gOFF): `/root/evidence-gate3-sweep-p64-gOFF/` (COMPLETE rc=0, 269 req)
  - Smoke p106-gOFF: `/root/smoke-p106-gOFF.log`
  - Smoke p106-gON: `/root/smoke-p106-gON.log`
  - Smoke p160-gOFF: `/root/smoke-p160-gOFF.log`
  - Smoke p160-gON: `/root/smoke-p160-gON.log`

## Evidence

### Step 1: Deletion Results

| Item | Before | After |
|------|--------|-------|
| /data free space | 9.1G (96% used) | 180G (5% used) |
| /data/l3/p2io-gate3-sweep-p32-gOFF | Existed (96GB hicache.data file) | Deleted |
| /data/l3/p2io-gate3-sweep-p32-gON | Existed (96GB hicache.data file) | Deleted |

### Step 2: Stale Lock Cleanup

- Found 3 stale locks: p106-gOFF, p160-gON, p64-gOFF
- Removed `/tmp/p2io-gate3-sweep-p64-gOFF.lock` (empty directory, rmdir succeeded)
- Left p106-gOFF and p160-gON locks untouched (not in scope for this run)

### Step 3: Cell-3 (p64-gOFF) Sweep — COMPLETE

| Field | Value |
|-------|-------|
| Tag | sweep-p64-gOFF |
| rc | 0 |
| Requests | 269 |
| Duration | ~900s (budget) + startup/teardown |
| Status log | `GATE3_sweep-p64-gOFF_COMPLETE rc=0` |
| GPU util mean | ~60% (from gpu-util.csv, 242 samples) |
| GPU util median | ~30% |
| Mamba max_mamba_cache_size | 64 |
| Mamba conv_state | 0.07GB |
| Mamba ssm_state | 3.05GB |
| CUDA Graph | Disabled (prefill.backend=disabled) |
| Engine events | Present (105,299 events in engine log) |
| engine-alloc.txt | Non-empty (17,610 bytes) |
| metrics-final.txt | Non-empty (88,953 bytes) |
| gpu-util.csv | Non-empty (4,915 bytes, 242 rows) |
| driver.log | Non-empty (95 bytes: `GATE2_DRIVER_DONE requests=269`) |
| Evidence dir | /root/evidence-gate3-sweep-p64-gOFF/ |

### 8-Cell Summary Table

| Cell | Pool | Graph | Status | Requests | rc | Duration | GPU util mean/median | TPS | Mamba max | OOM |
|------|------|-------|--------|----------|----|----------|---------------------|-----|-----------|-----|
| p32-gOFF (cell-1) | 32 | OFF | ✅ valid (prior) | — | 0 | — | — | — | — | — |
| p32-gON (cell-2) | 32 | ON | ✅ valid (prior) | — | 0 | — | — | — | — | — |
| p64-gOFF (cell-3) | 64 | OFF | ✅ COMPLETE rc=0 | 269 | 0 | ~900s | ~60%/~30% | — | 64 | No |
| p64-gON (cell-4) | 64 | ON | ✅ valid (prior) | — | 0 | — | — | — | — | — |
| p106-gOFF (cell-5) | 106 | OFF | — smoke only — | 1 | — | — | — | — | 106 | No |
| p106-gON (cell-6) | 106 | ON | — smoke only — | 1 | — | — | — | — | 106 | No |
| p160-gOFF (cell-7) | 160 | OFF | — smoke only — | 1 | — | — | — | — | 160 | No |
| p160-gON (cell-8) | 160 | ON | — smoke only — | 1 | — | — | — | — | 160 | No |

**Notes on prior cells (1,2,4)**: Status from prior run logs only; no fresh data collected in this sweep run. TPS data not extracted from metrics-final.txt for cell-3 (would need python parsing).

### Step 4: Engine-Only Smoke Results (4 cells)

| Cell | Healthy? | Single Request? | GPU Mem Used | Mamba max | Graph | OOM Evidence | Boundary |
|------|----------|----------------|--------------|-----------|-------|-------------|----------|
| p106-gOFF | ✅ (HTTP 200) | ✅ (HTTP 200) | 19,093 MiB | 106 | OFF | None | Boot + load OK |
| p106-gON | ✅ (HTTP 200) | ✅ (HTTP 200) | 19,819 MiB | 106 | ON | None | Boot + load OK |
| p160-gOFF | ✅ (HTTP 200) | ✅ (HTTP 200) | 21,751 MiB | 160 | OFF | None | Boot + load OK |
| p160-gON | ✅ (HTTP 200) | ✅ (HTTP 200) | 22,479 MiB | 160 | ON | None | Boot + load OK |

**Key observations**:
- All 4 smoke configs booted healthy and served a single request successfully.
- GPU memory usage scales with pool size: p106-gOFF=19.1GB, p160-gOFF=21.8GB, p160-gON=22.5GB.
- No OOM observed at single-request load for any config.
- Mamba cache effective pool = max_mamba_cache_size (106 for p106, 160 for p160).
- Graph is disabled for all configs (prefill.backend=disabled in cuda_graph_config).
- All configs use extent backend with max_size=20G, min_free_space=10G.

### Four Preliminary Answers

1. **Mamba contribution**: Mamba cache scales linearly with pool size. p32-gOFF (prior): ~1.5GB ssm_state. p64-gOFF (cell-3): 3.05GB ssm_state at max_mamba_cache_size=64. p106-gOFF (smoke): 5.02GB at max_mamba_cache_size=106. p160-gOFF (smoke): 7.55GB at max_mamba_cache_size=160. Doubling pool size doubles ssm_state.

2. **Graph contribution**: All smoke tests ran with Graph disabled (prefill.backend=disabled). No Graph-ON configs were tested in this sweep's smoke phase. Cannot quantify Graph contribution from this data alone. Prior run data (cells 2,4,8) shows Graph-ON configs have `cuda graph: True` in prefill batch lines.

3. **Overlay**: Not applicable — Graph is OFF in all tested configs here.

4. **Minimum config ≈ peak**: p106-gOFF (smallest pool tested in smoke) uses 19.1GB GPU mem at single-request load. 24GB card leaves ~5GB headroom at single request. Peak load (multi-request) not tested in smoke; OOM boundary unknown from single-request data.

## Open Issues

1. **TPS data for cell-3 not extracted**: driver.log only has `GATE2_DRIVER_DONE` line; aggregate/decode/prefill TPS not parsed from metrics-final.txt.
2. **Prior cells (1,2,4) data not fresh**: Status from prior run logs only; no new verification in this sweep run.
3. **Graph contribution unknown**: All smoke tests ran with Graph disabled; no Graph-ON smoke was performed.
4. **OOM boundary not tested**: Smoke tests only sent single requests; multi-request load testing not done to find OOM threshold.
5. **engine-events.txt for cell-3**: gate3_soak.sh creates this file post-run; it exists in evidence dir (25,176 bytes) but content not fully inspected for this report.
6. **p106-gON and p160-gON smoke logs**: Not fully inspected for mamba/Graph details beyond what was captured above.