# Service Metrics Monitor - Rollup Report

**Task**: Passive, read-only monitoring of serving performance on port 30000

**Status**: WORKING

**Target**: SGLang inference server on 127.0.0.1:30000

**Observation Start**: Pending...

---

## Scope

**Hard Constraints**:
- Read-only access only
- NO `/v1/chat/completions` or `/v1/completions` requests
- Do NOT modify server or infrastructure
- May use: `GET /metrics`, `GET /health`, `GET /v1/models`

**Metrics Surfaces to Discover**:
1. Prometheus metrics at `/metrics`
2. CLI flags: `--export-metrics-to-file` (if enabled)
3. Per-request JSON logs under `/tmp/opencode/`
4. GPU metrics via `nvidia-smi`

---

## Evidence

*Population below as metrics are scraped...*

---

## Available-metric-inventory

*Population below...*

---

## Rollup

*Population below...*

---

## Defects / Blockers

*Population below...*

---

## Remaining claims / exclusions

*Population below...*

---

**Terminal state**: WORKING
