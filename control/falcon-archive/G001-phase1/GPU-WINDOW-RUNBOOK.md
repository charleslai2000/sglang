# Falcon-H1 Phase 1 GPU-window runbook

## Preconditions

1. Owner explicitly releases the RTX 3090 for this bounded window.
2. `nvidia-smi` shows no existing serving workload.
3. Do **not** kill PID 2064356 or any unknown process from this runbook.
4. Confirm the artifact path and SHA evidence in `falcon-h1-phase1-artifact-accounting.json`.

## Fixed order

```text
nvidia-smi sanity
-> start scripts/falcon_h1_phase1_server.sh
-> capture server stdout/stderr and resolved PID/argv
-> wait for /health 200
-> capture startup accounting (quant/kernel, weights, KV, Mamba, effective request cap, graphs)
-> one deterministic correctness request
-> scripts/falcon_h1_phase1_probe.py --levels 1,2,4,8,16
-> only if no boundary: --levels 24,32
-> targeted graceful shutdown of the Falcon-H1 PID/group only
-> nvidia-smi confirms GPU released
```

The server uses `127.0.0.1:30170`, not the M4 `:30000`. The probe does not start,
stop, or kill processes. Any startup failure, unsupported kernel, incorrect
output, unexplained OOM, or Mamba initialization anomaly is a STOP condition.
