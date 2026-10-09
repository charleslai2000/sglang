# Telemetry availability contract — 2026-09-14

Status: **TELEMETRY_CONTRACT_READY**

This is an auditable availability contract for the performance cache. It records
only the completed telemetry-availability scout result; it is not a performance
run and does not authorize starting a GPU or server. Existing specifications,
runs, raw evidence, source, model, and runtime are unchanged.

## Collection sources

| Source path | Availability | Contract use |
|---|---|---|
| `/metrics` | Available for authoritative exported metrics | Primary metric collection source. Record metric name, labels, value, unit, and scrape timestamp exactly as exposed. |
| `/v1/loads?include=all` | Available for authoritative load inventory/details | Load and model-load evidence source; preserve the response fields exactly, including absent/null fields. |
| `/health` | Available | Health/status checkpoint source. HTTP status and response body are recorded as observed. |
| `/v1/models` | Available | Model inventory/identity source. Record returned identifiers and fields without deriving runtime state. |
| `/v1/server` | Available | Server identity/capability/status source. Record returned fields without inference. |

## Authoritative telemetry

The following are contractually collectible when present in the named source.
Metric names and units are recorded verbatim from `/metrics`; where the scout
did not establish a canonical name or unit, the value is `UNAVAILABLE` rather
than reconstructed from another field.

| Logical field/group | Source | Metric name / JSON field | Unit / semantics | Counter/gauge and caveats |
|---|---|---|---|---|
| Exported runtime metrics | `/metrics` | Exact exposition names and labels | As declared by exposition; otherwise unknown | Preserve counter vs gauge type as exposed. Counters may reset on process restart; gauges are point-in-time. Scrape interval and reset boundary must be recorded. |
| Load records | `/v1/loads?include=all` | Exact response fields | As declared by response | Snapshot fields; no cumulative/gauge classification unless explicitly declared by the endpoint. |
| Health | `/health` | Exact status/body | HTTP status plus body semantics | Point-in-time checkpoint; sampling interval and transition timing are not implied. |
| Model inventory | `/v1/models` | Exact response fields | As declared by response | Snapshot; not a substitute for load timing or cache accounting. |
| Server identity/status | `/v1/server` | Exact response fields | As declared by response | Snapshot; not a substitute for host or device telemetry. |

## Explicitly unavailable partitions

The following fields are **UNAVAILABLE** for this contract unless a separately
authorized scout establishes an authoritative source. They must not be inferred
from latency, request counts, load records, logs, host tools, or model behavior.

### Cache tier partition and restore

- Exact L1/L2/L3 partition accounting.
- Exact L1/L2/L3 restore-stage accounting.
- Per-tier hit/miss/occupancy/capacity/eviction fields when not explicitly
  exported by an authoritative source.

### Mamba state lifecycle

- Mamba restore counts/timing.
- Mamba rebuild counts/timing.
- Mamba eviction counts/timing.

### RH scheduling and avoidable work

- RH lead.
- RH slack.
- Ready-before-admission.
- Avoidable recompute.
- Cache idle.

### External device and host telemetry

- External GPU telemetry.
- External CPU telemetry.
- PCIe H2D/D2H telemetry.
- NVMe read/write telemetry.

## No-inference and time-series policy

1. A field is authoritative only when returned by its named endpoint or
   explicitly exported by `/metrics`.
2. Missing, null, unrecognized, or endpoint-inapplicable fields are recorded as
   `UNAVAILABLE`; they are never filled from a similarly named field.
3. Cumulative values are differenced only when the exposition declares a
   counter and the collection interval plus reset/restart boundary are known.
4. Gauges are not accumulated. A snapshot is not a rate, duration, or total.
5. No metric name, unit, semantic, tier attribution, restore stage, or causal
   relationship is inferred from endpoint shape, latency, throughput, logs, or
   downstream outputs.
6. A later authorized source does not retroactively change this contract; it
   creates a new dated contract or an explicitly versioned amendment.

## Validation boundary

Validation is limited to syntax/format and digest consistency for the four
authorized artifacts in this directory. No server, GPU, source, model, runtime,
or raw run was started or modified.
