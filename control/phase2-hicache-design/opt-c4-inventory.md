# Phase C4 `/opt` deployment source reconciliation

Reference deployment: `/opt/sglang/opencodex-provider-2d4e33a832`
Canonical reference before this record: `ad63118354829f995b733ed0f5048caf8cda912e`

## Enumeration correction

The original C3 count said 238 missing and 43 differing. A fresh extension-filtered, byte-hash inventory found **239 missing** and **43 differing**. The additional missing path is `.memory/phase2-hicache-design/authority.yaml`; it is historical memory material, not runtime source. The audited population is therefore **282 paths**, not 281.

The inventory excludes generated Python caches, virtual environments, `node_modules`, and Rust `target` trees. Each path is classified below; no source-like suffix was treated as sufficient evidence of runtime authority.

## Final acceptance

```text
OPT_REQUIRED_RUNTIME_REMAINING=0
OPT_REQUIRED_OPERATIONAL_TOOL_REMAINING=0
UNIQUE_SOURCE_IN_OPT=ZERO
SOURCE_AUTHORITY_RECONCILED=YES
```

`UNIQUE_SOURCE_IN_OPT=ZERO` means zero required, non-superseded runtime or operational source remains unique to this deployment copy. The `/opt` tree itself is intentionally retained by the C4 boundary.

## Counts

| Classification | Missing | Differing | Total |
|---|---:|---:|---:|
| REQUIRED_RUNTIME | 0 | 0 | 0 |
| REQUIRED_OPERATIONAL_TOOL | 0 | 0 | 0 |
| TEST/HARNESS_ONLY | 70 | 3 | 73 |
| DEPLOYMENT_GENERATED | 134 | 0 | 134 |
| OBSOLETE/SUPERSEDED | 35 | 40 | 75 |
| **Total** | **239** | **43** | **282** |

## Decisions and semantic evidence

### Required runtime: none to absorb

The 26 `/opt` runtime differences are not missing fixes. The canonical tree contains the newer/authoritative Qwen3.5 GGUF and GDN implementation, including the tiled-V-head route and loader checks. The relevant history is present in commits `d0e9450123` and `d637d258bb`; the canonical snapshot also contains the later model/GGUF fixes (`3fa3b78197`, `4501e59f88`). The `/opt` files remove or predate those paths, so copying them would regress canonical behavior.

The other runtime differences are likewise canonical-forward changes or deployment snapshot regressions: GGUF token handling, OpenAI reasoning fields, function-call streaming framing, HiCache backup attribution/reclaim accounting, cache-root handling, metrics, and server defaults. No `/opt`-only runtime behavior was found that is both required and absent from canonical.

### Required operational tool: none to absorb

The five `3090-dev/tools/prod-service/bin/*` differences and `3090-dev/deploy/bin/supervise.sh` are older service variants. The `/opt` versions hard-code `LOCAL-PROD-v1.1.2`, use a fixed three-second environment race, and remove current role/identity handling. Canonical versions read the selected tree identity from its manifest, poll until the launcher environment is established, and retain the current service contract.

The four `3090-dev/tools/freeze/bin/*` differences and `pysrc/audit_launcher.py` are an older freeze layout/profile: they point at `lib` instead of the canonical `pysrc` modules and omit the reviewed source-change/profile firewall. Canonical is the authority; the `/opt` implementation is superseded.

The four production-gate differences are old gate variants. Canonical has the current fail-closed checks and geometry; no `/opt` gate change was identified as a missing operational fix.

Production-use evidence was checked in the deployment configuration and script references. No running SGLang process or active systemd/supervisor unit was found in this environment, so “actual production version” is established by the checked-in service scaffold contract: both `/opt` service scripts and canonical service scripts target selectable frozen trees, while canonical is the only reviewed source authority. The `/opt` copy is not promoted or modified by this phase.

## Full classification inventory

The authoritative complete path lists are stored in `/tmp/opt-missing.txt` and `/tmp/opt-diff.txt` for this session. The deterministic rules used for every path were:

* `TEST/HARNESS_ONLY`: `3090-dev/harness/**`, plus the three differing registered unit tests.
* `DEPLOYMENT_GENERATED`: `.memory/**` and `3090-dev/recovery/scratch-archive/**`; these are historical evidence, generated/recovery snapshots, probes, reducers, and archived launch attempts.
* `OBSOLETE/SUPERSEDED`: `3090-dev/recovery/residual/**`, all differing runtime files under `python/**`, and old freeze/service/gate tooling.
* No path qualified as `REQUIRED_RUNTIME` or `REQUIRED_OPERATIONAL_TOOL`.

### Missing paths: TEST/HARNESS_ONLY (70)

All missing paths under `3090-dev/harness/`:

```text
3090-dev/harness/f1-probes/*
3090-dev/harness/failclosed/*
3090-dev/harness/gguf-probes/*
3090-dev/harness/microbench/*
3090-dev/harness/misc/*
3090-dev/harness/native-poc/*
3090-dev/harness/optionA/*
3090-dev/harness/wal-isolation/*
```

The wildcard groups expand to the exact 70 paths in `/tmp/opt-missing.txt`; these are probes, microbenchmarks, smoke drivers, and WAL experiments, not importable runtime modules or required production tests.

### Missing paths: DEPLOYMENT_GENERATED (134)

* `.memory/phase2-hicache-design/**`: 45 historical authority/work files.
* `3090-dev/recovery/scratch-archive/**`: 89 archived probes, patch attempts, lineage snapshots, freeze attempts, and copied test-apply material.
* The `.memory/phase2-hicache-design/authority.yaml` path is included in the 45-file memory count; the combined generated count is 45 + 89 = 134.

### Missing paths: OBSOLETE/SUPERSEDED (35)

All paths under:

```text
3090-dev/recovery/residual/**
```

These are named residual copies of prior L3/Qwen3.5/cache implementations and frozen self-test trees. Canonical contains the selected successors; none is an active import or launcher dependency.

### Differing paths: TEST/HARNESS_ONLY (3)

```text
test/registered/unit/function_call/test_function_call_parser.py
test/registered/unit/managers/test_hicache_host_allocability.py
test/registered/unit/managers/test_hybrid_group_wiring.py
```

The `/opt` versions are older tests and remove current coverage; no test-only behavior is required in canonical.

### Differing paths: OBSOLETE/SUPERSEDED (40)

Runtime (26):

```text
python/sglang/kernels/aot/csrc/quantization/gguf/ggml-common.h
python/sglang/kernels/ops/attention/fla/chunk.py
python/sglang/kernels/ops/attention/fla/chunk_delta_h.py
python/sglang/kernels/ops/attention/fla/chunk_fwd.py
python/sglang/kernels/ops/attention/fla/chunk_o.py
python/sglang/kernels/ops/attention/fla/fused_recurrent.py
python/sglang/kernels/ops/attention/fla/fused_sigmoid_gating_recurrent.py
python/sglang/kernels/ops/attention/fla/wy_fast.py
python/sglang/srt/entrypoints/openai/protocol.py
python/sglang/srt/entrypoints/openai/serving_chat.py
python/sglang/srt/entrypoints/openai/usage_processor.py
python/sglang/srt/function_call/qwen3_coder_detector.py
python/sglang/srt/layers/attention/linear/gdn_backend.py
python/sglang/srt/layers/attention/linear/kernels/gdn_triton.py
python/sglang/srt/layers/radix_linear_attention.py
python/sglang/srt/managers/scheduler_components/metrics_reporter.py
python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py
python/sglang/srt/mem_cache/storage/extent/extent_file_backend.py
python/sglang/srt/mem_cache/unified_radix_cache.py
python/sglang/srt/model_loader/loader.py
python/sglang/srt/models/qwen3_5.py
python/sglang/srt/models/qwen3_5_text.py
python/sglang/srt/observability/metrics_collector.py
python/sglang/srt/sampling/custom_logit_processor.py
python/sglang/srt/server_args.py
python/sglang/srt/utils/hf_transformers/gguf_native.py
```

Operational/gate tooling (14):

```text
3090-dev/deploy/bin/supervise.sh
3090-dev/gates/production/f2_restart_recovery.py
3090-dev/gates/production/gate_a_content_integrity.py
3090-dev/gates/production/gate_a_f1_cold_l1.py
3090-dev/gates/production/test_gate_helpers.py
3090-dev/tools/freeze/bin/freeze.sh
3090-dev/tools/freeze/bin/l3-namespace.sh
3090-dev/tools/freeze/bin/launcher-repin.sh
3090-dev/tools/freeze/bin/preflight.sh
3090-dev/tools/freeze/pysrc/audit_launcher.py
3090-dev/tools/prod-service/bin/start.sh
3090-dev/tools/prod-service/bin/stop.sh
3090-dev/tools/prod-service/bin/supervise.sh
3090-dev/tools/prod-service/bin/switch.sh
```

The runtime list contains 26 files; the operational list contains 14, for 40 superseded differing paths. No file was copied from `/opt` into canonical.

## Absorption

```text
ABSORBED_FROM_OPT=0
```

This is intentional: every candidate `/opt` delta was either historical/generated, test/harness-only, or superseded by canonical content. Direct directory copying was not used.

## Boundary compliance

`/opt/sglang/opencodex-provider-2d4e33a832` was not deleted or modified. No branch/worktree was deleted, no push was performed, `main` was not modified, and no model/runtime acceptance was started.
