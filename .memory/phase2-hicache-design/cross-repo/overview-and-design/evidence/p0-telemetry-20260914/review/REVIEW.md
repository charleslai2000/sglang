# P0 telemetry Expert-Gate 后独立终审

- Task: `LOCAL-P0-TELEMETRY-FINAL-REVIEW-20260914`
- Role: `reviewer-deep`
- Date: 2026-09-14
- Status: **done**
- Decision: **CHANGES_REQUIRED**
- Telemetry-enabled cache/agent/performance reruns: **NOT AUTHORIZED**
- Repository: `/home/dev-codex/workspaces/3rdparty/sglang-3090-24g-opt`
- HEAD: `993ef8e5c3a6448aff2e752cf66cc45deadab59a`
- Reviewed final-fix scoped diff SHA-256: `1d4e241afb629f1c903df6fa7b101660d214df53da55a163dea344e94f5b2a02`
- GPU/server/performance run: not started

## 终审结论

Expert Gate 已明确解决先前的公式冲突，controller 也已将 issue timestamp 移到 queue publication 之前；独立重跑的 13 个 focused tests、compileall 和 `git diff --check` 均为 exit 0，且 fix packet 所列 14 个 identity 均重新校验一致。

但当前 final bytes 仍不满足 Gate 的 production-seam 与数据权威性要求。存在三项 confirmed defects，其中两项会产生自相矛盾或错误授权的 durable telemetry；同时所谓 13 个 production-seam tests 实际上主要是 pure-helper/static-source tests，未执行 Gate 强制要求的真实 queue fake、selected-anchor→operation→finalizer handoff、metrics DI 或 JSONL writer seam。因此本次不能授权 telemetry-enabled baseline reruns。

## Confirmed defects

### FR1 — HIGH — proof 降级为 unknown 后，durable total 仍保持正值并被当作 complete

**Requirement.** Expert Gate §3.2 要求 scheduler 仅在 request lineage、attempt、generation、prompt/hash lineage 和 component proof 全部匹配时接受正值 `Md`；否则 matched durable 与 total durable 必须为 null，且不应产生 avoidable credit。

**Evidence.** Finalizer 在 `unified_radix_cache.py:5954-5960` 仅检查 proof 对象 truthy、accepted 和 hybrid-complete，就直接计算 `stats_matched_prefix_tokens + completed_tokens`。Builder 随后在 `hicache_telemetry.py:207-222` 可以因 request/attempt/generation 不匹配把 matched classification 降为 `unknown/null`，但在 `:225-300` 仍原样保留 finalizer 的 positive `durable_reusable_prefix_tokens`，据此计算 avoidable recompute，并可给出 `outcome="complete"`。

独立 CPU falsification 使用 mismatched `request_lineage` proof，实际得到：

```text
matched_prefix_authority = unknown
matched_prefix_l3_tokens = null
durable_reusable_prefix_tokens = 10
avoidable_recompute_tokens = 5
outcome = complete
invalid_reason = null
```

**Impact.** JSONL 与 Prometheus 可以在同一 record 中一边承认 matched proof unknown，一边发布由该 proof 派生的 authoritative durable/avoidable 正值，直接违反 null/unknown 与 positive-proof invariants。若 bytes 在重跑中触发任何 stale/mixed proof，这会污染 baseline attribution。

**Disposition.** 在 finalizer/scheduler acceptance seam 验证完整 proof tuple，而非仅检查 dict truthiness；只有 validated `Md` 才能参与 `D`。任何 lineage/attempt/generation/component mismatch 必须按 Gate precedence 置 invalid，并清空所有 dependent durable/timing facts；unknown/incomplete 必须令 `D` 和 avoidable 为 null。增加能复现上述矛盾的 production-handoff test。

### FR2 — HIGH — matched-prefix component proof 与 suffix component completeness 未按 Gate 实现

**Requirement.** Positive matched-prefix credit 必须证明 active layout 的完整 required component set；DSA suffix 必须取 KV 与每个 required sidecar 的 common prefix，SWA/Mamba 必须 all-or-nothing。

**Evidence.** `_matched_prefix_l3_proof` 在 `unified_radix_cache.py:5996-6015` 只允许 `len(self.tree_components) == 1` 的 pure-KV positive proof。所有 hybrid matched prefixes 一律退化为 no proof；这虽比误报安全，却没有实现 Gate 要求的 joined-restore/component-complete positive path。更严重的是 `_host_alloc_hybrid_sidecar_counts` 在 `:5897-5900` 明确跳过 `indices_from_pool == PoolName.KV` 的 transfers，而 `_host_alloc_hybrid_restore_complete` 在 `:6017-6025` 仅检查该被过滤后的集合。`D` 又仅依赖这个布尔值。因此这段新 final-total 逻辑本身没有证明 DSA/KV-derived required sidecar 的 common boundary。

Gate 指定的 T2 vectors（device-only、host-only、unacked、persisted, broad-restored-without-lineage、DSA shortfall、SWA/Mamba shortfall、stale attempt/generation、component unavailable）均没有通过真实 finalizer handoff 执行。当前 13-test 文件只对一个人工 proof dict 调用 pure classifier。

**Impact.** Hybrid 情况要么永久丢失本应可权威分类的 matched durable coverage，要么 suffix completeness 依赖未在 telemetry final-total seam 内建立的隐式假设。后者可能使 `D` 在 required KV-derived sidecar 未被 telemetry completeness 检查时取得正值。

**Disposition.** 将 active layout 的 required component set 与 per-component/common boundary 作为 operation-local fact；对 DSA 使用实际 common prefix，对 SWA/Mamba 使用明确 all-or-nothing accepted fact。若当前代码无法提供匹配的 durability proof，保持 unknown/null。必须通过实际 selected-anchor→operation→finalizer→scheduler seam 覆盖 Gate T2 vectors。

### FR3 — MEDIUM — JSONL embedding 路径不附加 telemetry object

**Requirement.** Gate T3 要求 token、string 和 applicable embedding multi-tokenizer paths preserve the object；现有 exporter 为唯一 writer。

**Evidence.** `multi_tokenizer_mixin.py:280-292` 已传播 `BatchEmbeddingOutput.hicache_telemetry`，但 `tokenizer_manager.py:2251-2287` 将 `meta_info["hicache_telemetry"]` 的附加逻辑放在 `if not isinstance(recv_obj, BatchEmbeddingOutput)` 分支内。Embedding 在 `:2426-2430` 使用同一个 `meta_info` 生成输出，却没有对应 attach path。因此 embedding telemetry 在 exporter 前被丢弃。

**Impact.** Applicable embedding request 的 opt-in JSONL record 不符合固定 schema/object-preservation 要求，造成按请求类型的 silent denominator loss。

**Disposition.** 在不改变 writer ownership 的前提下，为 embedding 复用同一 bounded public object attach helper；增加 direct 与 multi-tokenizer embedding-to-export record test。

## Test evidence disposition

### Confirmed pass evidence

- Independent: `PYTHONDONTWRITEBYTECODE=1 python3 test/registered/unit/observability/test_hicache_request_telemetry.py` → **13 tests, exit 0**.
- Independent compileall over the eight packet-listed source/test files → **exit 0**.
- Independent `git diff --check` → **exit 0**.
- Packet logs independently read: focused unit, compileall, diff-check all record exit 0.
- `ruff` module is absent; formatting is **unavailable**, not passed.
- `orjson` module is absent; full production-module import is **unavailable**, not passed.

### Why the 13 tests are insufficient

- T1 is a text-order assertion using `Path.read_text()`; it never invokes real `HybridCacheController.prefetch`, never uses a queue fake whose `put` synchronously inspects the operation, never simulates immediate dequeue/query, and never tests disabled telemetry.
- T2 does not invoke `_matched_prefix_l3_proof`, `_host_alloc_hybrid_completion`, `_check_hybrid_prefetch_result`, scheduler terminal join, or any real anchor/component object.
- T3 does not instantiate `SchedulerMetricsCollector` with fake Counter/Histogram, does not verify exact registration labels/observation idempotence, does not write/read one JSONL line, does not test health exclusion, and does not execute token/string/embedding propagation.
- The tests therefore pass, but they do not constitute the 13 production-seam tests claimed by the report and cannot falsify FR1–FR3.

## Contract items confirmed

- Controller assigns `prefetch_issue_mono_ns` immediately before `prefetch_queue.put`; no later production assignment was found. Disabled path leaves it null.
- Accounting uses the exclusive partition `prompt=L1+L2+L3+newly_prefilled`; negative/oversummed input is invalid rather than clamped.
- Avoidable recompute is a separate subset and separate Prometheus counter.
- Prometheus metric names, four source enums, four stage enums, three outcomes, and bucket tuple match the Gate; no request/session/attempt/cache-key identity label was added.
- JSONL public object contains outcome/reason fields and strips internal keys; existing `FileRequestMetricsExporter` remains the only writer and still skips health checks.
- Derivation and collector observation exceptions are isolated from serving.
- No telemetry-derived value controls scheduling, RH, retry, cache, storage, loader, or model behavior. No telemetry writer/thread/queue/lock or persistence format was introduced.
- Exporter-off request payload remains absent; telemetry clocks are disabled only when both existing metrics and file export are off.

## Identity and erratum validation

- Current HEAD matches the packet: `993ef8e5c3a6448aff2e752cf66cc45deadab59a`.
- Packet scoped diff SHA-256 `1d4e241a…b2a02` exactly matches a fresh diff of its six tracked source files. Full worktree diff SHA-256 is `42206295…29f2` because documented pre-existing/unrelated tracked dirt remains.
- Every entry in `hashes.sha256` verifies, including the two untracked telemetry files and Expert Gate/spec/erratum artifacts.
- Erratum hashes verify as Markdown `135854e3…17c6` and JSON `4a0f219a…128e`; Gate hashes verify as Markdown `48b4faad…3c00` and JSON `1e8277e9…374`.
- The erratum correctly replaces only v2 cache accounting with exclusive conservation and separate optimization opportunity while preserving original v2 bytes.
- Plausible risk: the erratum JSON names the Gate artifact but does not embed its SHA-256, and no runner/hash-binding implementation was found. Before an accepted rerun, the orchestrator/runner must bind the exact reviewed Gate/erratum hashes rather than only filenames. This is not the primary blocker because FR1–FR3 already require code/test correction.

## Boundary and dirty-state disposition

The final-fix packet's `changed-files.txt` is a whole-worktree tracked list, not a precise telemetry ownership list; it includes documented pre-existing `qwen3_5_text.py` and `test_extent_g1_metadata_unit.py` changes. The scoped correction diff contains only six tracked files, while `hicache_telemetry.py` and its focused test are untracked and separately hashed. No reviewed bytes were modified by this review. Only these three requested review artifacts were replaced.

## Required follow-up

1. Repair FR1 so classification, durable total, avoidable recompute, outcome and invalid precedence derive from one validated proof/join result.
2. Repair/establish hybrid component-complete matched and suffix authority, with safe unknown/null fallback.
3. Preserve the public telemetry object through applicable embedding export.
4. Replace static/helper-only claims with dependency-local production-seam tests required by Gate T1–T3; include actual queue fake, finalizer/scheduler handoff, metrics DI, JSONL line/health exclusion, and token/string/embedding propagation.
5. Capture fresh dependent-byte identities, bind the future runner to the exact Gate/erratum hash, then request one fresh independent terminal review.

Until these are verified, telemetry-enabled cache/agent/performance reruns remain **not authorized**.
