# Evidence index — P0 telemetry final review

## Normative inputs

| Artifact | Identity / use |
|---|---|
| `/mnt/data/cache/performance-baseline-v1/manifests/P0-TELEMETRY-EXPERT-GATE-20260914.md` | SHA-256 `48b4faade00d2261889eb94f2bce44d11a62d12139b6d9200d7289c3c74f8c17`; controlling timestamp, proof, formula, metrics, JSONL and T1–T3 contract. |
| `/mnt/data/cache/performance-baseline-v1/manifests/P0-TELEMETRY-EXPERT-GATE-20260914.json` | SHA-256 `1e8277e9762cafc7336156479973d725d9bce973d245d1f62974ad407795e374`. |
| `/mnt/data/cache/performance-baseline-v1/manifest/PERFORMANCE-BASELINE-SPEC-v2-P0-TELEMETRY-ERRATUM-20260914.md` | SHA-256 `135854e3511f416024cd1653469cae598209c6fbaf2b778b3c5e788148a317c6`; corrected exclusive conservation. |
| `/mnt/data/cache/performance-baseline-v1/manifest/PERFORMANCE-BASELINE-SPEC-v2-P0-TELEMETRY-ERRATUM-20260914.json` | SHA-256 `4a0f219aca6940eda00606a649d50634a87958ba1f0be84600acdb1177a8128e`. |
| Prior `P0-telemetry-final-review-20260914` and `P0-telemetry-terminal-review-20260914` artifacts | Prior defect requirements and correction history; not accepted as proof of current bytes. |

## Final-fix packet

Base: `/mnt/data/nerun-dev/p3/LOCAL-PROD-BASELINE-v1/P0-telemetry-final-fix-20260914/`

| Artifact | Review result |
|---|---|
| `REPORT.md` | Claims FIX_READY and 13 production-seam tests; conclusion independently challenged. |
| `manifest.json` | Records scope, test exits, unavailable ruff/orjson and erratum paths. |
| `diff.patch` | SHA-256 `1d4e241afb629f1c903df6fa7b101660d214df53da55a163dea344e94f5b2a02`; exactly matches fresh diff of the six scoped tracked files. |
| `hashes.sha256` | All 14 entries independently passed `sha256sum -c`. |
| `status.txt` / `changed-files.txt` | Whole-worktree dirty classification; includes pre-existing/unrelated tracked files and omits untracked files from `changed-files.txt`. |
| `tests/logs/focused-unit.*` | Exit 0; `Ran 13 tests`; packet output matches independent rerun. |
| `tests/logs/compileall.*` | Exit 0, empty stdout. |
| `tests/logs/git-diff-check.*` | Exit 0, empty stdout. |
| `commands-exits.txt` | Ruff unavailable exit 127; production import blocked by missing orjson; no GPU/server/performance run. |

## Current identities

- HEAD: `993ef8e5c3a6448aff2e752cf66cc45deadab59a`
- Scoped final-fix tracked diff: `1d4e241afb629f1c903df6fa7b101660d214df53da55a163dea344e94f5b2a02`
- Full current tracked diff: `42206295d1095d02f57dad7a87dccc3ba0613d3cdf3a7ba84a39f79aa5e829f2`

| Source/test | SHA-256 |
|---|---|
| `python/sglang/srt/observability/hicache_telemetry.py` | `5f433f8479f1487c2d3c54d2f211c7e2ac423bbb8708cae6a6bb18d77fba3c00` |
| `python/sglang/srt/observability/metrics_collector.py` | `fd55df0a0aa3b85a5561450fe1556cc265bcc94bbb03a4847ea4e6485b7e491e` |
| `python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py` | `4462403deb5b4975a5be95072cd344bb98a01dba78f10c40eb9aead08b843729` |
| `python/sglang/srt/mem_cache/hiradix_cache.py` | `953c2b272e4da42b36251f5a8870600f8f88096c4b58056480d1b711428991d8` |
| `python/sglang/srt/mem_cache/unified_radix_cache.py` | `86117ad1736ef4e50c03131b4749c265d28cdb93bd7148774ceb0f6a7a0d5d02` |
| `python/sglang/srt/managers/schedule_batch.py` | `55304d8bf8965f59ade70faf0ccb565c1c40a32280ad11da5582c5f707709596` |
| `python/sglang/srt/managers/scheduler.py` | `a85e8078d476b1f5107186b58babf78d3becedf596cfc1df92343bd29165efdc` |
| `test/registered/unit/observability/test_hicache_request_telemetry.py` | `10f8b58a473bada4b86c12474f9c6e11a6ed25e3af3c18815eaa37237723c036` |

Relevant reused unchanged identities from prior final review were also re-read: output streamer `e92da3e4…94af9`, tokenizer manager `b3f92cc2…2a844`, multi-tokenizer mixin `d280636e…75de`, IO struct `7a4d1e94…c94e5`, detokenizer `a1124467…197`.

## Causal traces

| Claim | Evidence |
|---|---|
| Issue mark ordered before publication | `hybrid_cache_controller.py:812-848`; assignment at 846, queue put at 847. Search found no later production assignment. |
| D derived from proof truthiness | `unified_radix_cache.py:5954-5960`. |
| Proof can be downgraded without clearing D | `hicache_telemetry.py:204-228, 247-300`; independent falsification output recorded in `REVIEW.md`. |
| Hybrid matched proof unavailable | `unified_radix_cache.py:5996-6015` requires exactly one tree component. |
| KV-derived sidecars filtered from telemetry completeness | `unified_radix_cache.py:5897-5900, 6017-6025`. |
| Embedding attach gap | Propagation at `multi_tokenizer_mixin.py:280-292`; attach only under non-embedding branch at `tokenizer_manager.py:2251-2287`; embedding output construction at `:2426-2430`. |
| Fixed metric names/cardinality | `metrics_collector.py:853-885, 1327-1363`; enum/buckets at `hicache_telemetry.py:13-57`. |
| Exclusive formula and subset | `hicache_telemetry.py:66-104`; erratum lines 9-41. |
| Existing sole writer and health exclusion | `request_metrics_exporter.py:72-156`; existing lock/thread-offload unchanged. |

## Independent command evidence

1. `git status --short && git rev-parse HEAD && git diff --check && git diff --stat` — exit 0; status/HEAD as recorded; diff check clean.
2. `sha256sum -c .../hashes.sha256` — exit 0; all entries `OK`.
3. `PYTHONDONTWRITEBYTECODE=1 python3 test/registered/unit/observability/test_hicache_request_telemetry.py` — exit 0; 13 tests OK.
4. `PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q [eight packet-listed files]` — exit 0.
5. Python module discovery — `ruff None`, `orjson None`; neither represented as passing.
6. CPU falsification with a mismatched-lineage proof — produced `unknown/null` matched classification together with positive durable/avoidable and `complete`, confirming FR1.

## Review artifacts

- `REVIEW.md` — human-readable decision, confirmed defects, risks, evidence and dispositions.
- `decision.json` — machine-readable `CHANGES_REQUIRED` decision and rerun denial.
- `evidence-index.md` — dependency-scoped identities and evidence trace.
