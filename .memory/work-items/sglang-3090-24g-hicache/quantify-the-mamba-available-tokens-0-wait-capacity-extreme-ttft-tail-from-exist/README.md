# quantify the `mamba_available_tokens == 0 -> WAIT_CAPACITY -> extreme TTFT` tail from existing

- **工作标题：** MAMBA-CAPACITY-TELEMETRY-20260918
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/agents/MAMBA-CAPACITY-TELEMETRY-20260918.md`：**
production telemetry and decide whether it is a Mamba-pool capacity problem; produce the data that
justifies (or kills) the narrow `max_mamba_cache_size` 48/56/64 sweep. READ-ONLY: no restart/stop,
no signal, no GPU workload, no config edit, no git mutation. Only this artifact was written inside
the workspace; the raw `/metrics` scrape captures live in the pre-approved temp dir
`/tmp/opencode/mam_metrics{,2,3}.txt`.
Window captured: the run `prod-20260917T211800Z-1653969` from boot 21:18:00Z to its natural stop
23:05:31Z (supervisor rc=0), requests 21:20:03Z -> 23:06:28Z. Evidence digests at read time
(2026-09-17T23:39Z): `server.console.log` sha256 a5f63862c7c5fa413318b8c13b5590ef4c11dc157413eeca30edde75cb90f5dd;

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** DONE

**`phase2-hicache-design/agents/MAMBA-CAPACITY-TELEMETRY-20260918.md`：**
**Diagnosis (one line): the WAIT_CAPACITY tail is explained by the Mamba state pool — but by the
pool's host-side staging capacity and by the wake predicate's slot-vs-token mismatch, not by a
shortage of simultaneous device slots.**
Every one of the 42 WAIT_CAPACITY parks has `blocked_domains == ["mamba"]`, Mamba host staging
`free == 0` and `evictable == 0`, while the host KV pool was 48.5–80.6 % free. The prefetch retry
allocates exactly **one** Mamba host slot (`MambaComponent.prepare_prefetch`,
`srt/mem_cache/unified_cache/components/mamba_component.py:836-849`) and that single-slot alloc
failed because the whole Mamba host pool was allocated and none of it evictable. The Mamba host pool
holds only **142 usable slots** (one radix checkpoint per slot), so it can host-buffer at most ~142
distinct linear-attention checkpoints; any request whose matched prefix needs a checkpoint that is
not host-resident parks. Worse, the wake predicate charges the **whole matched-prefix token count**
against that slot pool (`required_aux_units["mamba"] = len(prefetch_key)`, 484 – 65,347 units
measured, versus a 142-slot pool), so a grant is arithmetically impossible even if one slot were free.
All 261 wake checks resolved to `hold_no_generation`; all 42 requests left only via the 60 s T13


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/agents/MAMBA-CAPACITY-TELEMETRY-20260918.md` → `.memory/phase2-hicache-design/agents/MAMBA-CAPACITY-TELEMETRY-20260918.md`; SHA256 `957a66d22c9b34c9300672796c2dd0c11a93e5bf0b5762790f53c48b2bc176a9`; source state `tracked`
