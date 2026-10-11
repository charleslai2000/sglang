# phase2-hicache-design-tester-gate1-l3restore

- **工作标题：** phase2-hicache-design-tester-gate1-l3restore
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-tester-gate1-l3restore.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** 07:58:56 begin; Gate 1 PASS — real L3 (NVMe) restore stably triggers on the 3090

**`phase2-hicache-design/work/phase2-hicache-design-tester-gate1-l3restore.md`：**
**Verdict: Gate 1 PASS — real L3 (NVMe) restore stably triggers on the 3090
under deterministic Host eviction.**
Under a repeatable 9-chain churn with a deliberately small host pool
(HICACHE_SIZE=3) plus explicit page-cache eviction (fadvise DONTNEED) before each
cold read, 4 genuine L3 restores occurred (2 full chains r-b2/r-c2 at 20855
tokens, 1 partial w-i1 at 16375, 1 short rb-a1 at 3450). Each restore shows the
complete chain: `L3 exists` (pc_storage_query storage_hit>0 incl. mamba sidecar)
-> `L3 read` (pc_get_v2 kv_batch preads + sidecar mamba hit) -> `Host materialize`
(pc_l3_host / prefetch_io_finished) -> `request consume`
(restore_success + cached_tokens=20864 in the served usage). The scheduler
read_bytes deltas (735 MB x2, 198 MB) prove these were real NVMe extent reads,
not page-cache bounces; correctness matches the cold baseline with zero
structural failures (no backup_failed / forced_drop / OOM / zero-progress), and
restore latency p50=0.835 s / p90=0.896 s. Mamba checkpoints restored together

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-tester-gate1-l3restore.md`：Gate 1 of the three hard gates (3090): prove **real L3 (NVMe) restore stably
triggers** under deterministic Host eviction. Config = the deployed upstream
baseline (extent backend, HICACHE_SIZE=3, ratio 1.5, wait_complete, all-or-nothing
restore, no ready-horizon, no fallback flag — arg-for-arg identical to g1's
server_args minus the reverted `hicache_partial_restore_fallback`).
Deliverables:
- Launch script (copy, prod template untouched): `/root/direct-launch-gate1.sh`
- Churn driver (9-chain deterministic Host eviction + page-cache eviction +
  scheduler /proc/<pid>/io read_bytes deltas + t38c probe):
  `/root/gate1-churn.sh` (status `/root/gate1-churn-status.log`,…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-tester-gate1-l3restore.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-tester-gate1-l3restore.md`; SHA256 `75d4dd1b1287ca27f6b33c4f279c71c616c069e5e9895a11d2ed0ba25f9aa2c8`; source state `tracked`
