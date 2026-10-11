# phase2-hicache-design-tester-gate2-saturation

- **工作标题：** phase2-hicache-design-tester-gate2-saturation
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/phase2-hicache-design-tester-gate2-saturation.md`：**
done

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
**`phase2-hicache-design/work/phase2-hicache-design-tester-gate2-saturation.md`：**
**Gate 2 verdict: FAIL.** Under Mamba checkpoint pool pressure, the aggregate
effective cache ratio is far below 95%, and the failure is a true cliff, not a
load-shape artifact:
- Even at K=4 (pool ~30% used, zero eviction) the phase-B aggregate ratio is
  0.8335 and exact L0 restores hit only 0.9201. The <95% at K=4 is partly
  load-shape (grow-chains and BB mid-branch have inherent new content), but
  exact same-chain L0 restores already miss ~8% due to partial radix matches
  (device hit=9 with host carrying the bulk, i.e. checkpoint not in device
  pool).
- At K=8 (pool ~30% used, dropped(mamba)=1) exact L0 restore ratio drops to
  0.8743 and **4/40 restores (10%) are full recomputes** of previously-written
  chains (`revoked:miss`, L3 storage_hit_count=0, ttft 28-45s).
- At K=16 (pool ~30% used, dropped=0) it collapses: L0 restore ratio 0.7921,
  **36/80 restores (45%) are full recomputes**, phase-B full-miss 46%.

### 报告列出的产物/证据
- `phase2-hicache-design/work/phase2-hicache-design-tester-gate2-saturation.md`：Gate 2 of the three hard gates (3090): **Mamba checkpoint pool 压力下
aggregate effective_cache_ratio ≥95%**, measured across unsaturated →
near-saturated → saturated, with a cliff scan (old-session / mid-branch
systematic 0-hit). No code/checkpoint-strategy changes — only measurement of
real capacity boundaries.
Deliverables (all in /root on 3090 unless noted):
- Load driver (two-phase: write-saturate then read-verify):
  `/root/gate2_load.py` (local copy `3090-dev/gate2_load.py`)
- Run driver: `/root/gate2-run2.sh` (local `3090-dev/gate2-run2.sh`)
- Analyzer: `/root/gate2_analyze.py` (local `3090-dev/gate2_analyze.py`)
- Evidence: `/root/evidence-gate2-k4/`, `/root/evidence-gate2-k8/`,…（节选；见来源报告）

## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/phase2-hicache-design-tester-gate2-saturation.md` → `.memory/phase2-hicache-design/work/phase2-hicache-design-tester-gate2-saturation.md`; SHA256 `1db22fba139bff620ef87c99aa2ba8bd6da759901c3b6496d483ac471b661233`; source state `tracked`
