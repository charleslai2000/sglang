# M2-CONCURRENCY-DEGRADATION-RCA-20260918

- **工作标题：** M2-CONCURRENCY-DEGRADATION-RCA-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/M2-CONCURRENCY-DEGRADATION-RCA-20260918.md`：**
**WARM-REMOVES-QUEUE + CACHE-STATE-ROOT-CAUSE** (both, combined).
- **WARM-REMOVES-QUEUE**: with the prefix cache warmed, M2's concurrency queue collapses
to zero. At c=5 warm: TTFT p50 **0.314 s**, queue 0.0, decode/req **78.9 tok/s**; the
cold baseline at c=5 was TTFT **3.461 s**, queue max **3.322**, decode/req **24.6**.
M2 is not categorically bad at concurrency — its degradation is entirely a *cold-cache*
effect.
- **CACHE-STATE-ROOT-CAUSE**: M2's prefix retention is bound by the **mamba slot budget**
(`max_mamba_cache_size=48`, 4 slots/request), not by KV token capacity. Retention holds

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/M2-CONCURRENCY-DEGRADATION-RCA-20260918.md`：**
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

### 报告列出的产物/证据
- `phase2-hicache-design/agents/M2-CONCURRENCY-DEGRADATION-RCA-20260918.md`：- `/tmp/opencode/M2-RCA-20260918/warm-state-M2-iso.json` / `capacity-M2-iso.json` (no-HiCache)
- `/tmp/opencode/M2-RCA-20260918/capacity-M2-hicache-iso.json` (HiCache root-cause arm)
- `/tmp/opencode/M2-RCA-20260918/warm-concurrency-M2-iso.json`, `warm-concurrency-M2-hicache-iso.json`
- `/tmp/opencode/M2-RCA-20260918/capacity-compare.txt` (side-by-side cliff vs HiCache)
- Logs under `/tmp/opencode/M2-RCA-20260918/logs/warm-iso-30164-*`, `hicache-iso-30164-*`
- Isolated server console logs record `hicache_attached` transitions.
Terminal state: DONE

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/M2-CONCURRENCY-DEGRADATION-RCA-20260918.md` → `.memory/phase2-hicache-design/agents/M2-CONCURRENCY-DEGRADATION-RCA-20260918.md`; SHA256 `8927f3e6cdcdbea91dc3817781636ea9d3ad09bd7954259e18841b56242d8dd6`; source state `tracked`
