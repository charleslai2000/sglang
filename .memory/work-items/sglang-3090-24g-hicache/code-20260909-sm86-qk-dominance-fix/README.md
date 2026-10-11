# CODE-20260909-SM86-QK-DOMINANCE-FIX

- **工作标题：** CODE-20260909-SM86-QK-DOMINANCE-FIX
- **来源仓：** `sglang-3090-24g-hicache`
- **合并阶段/报告：** 1
- **收集时 branch/HEAD：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`

## 工作目标
**`phase2-hicache-design/work/CODE-20260909-SM86-QK-DOMINANCE-FIX.md`：**
ENTRY: ACCEPT

## 实际改了什么
报告没有明确列出实际修改文件/改动；不将“提及代码路径”冒充已改。来源卡保留报告 scope/result 供人工追读。

## 生成结果与验收
- **原报告状态：** done

**`phase2-hicache-design/work/CODE-20260909-SM86-QK-DOMINANCE-FIX.md`：**
Rewrote the fused QK kernel's runtime Q/K pointer selection so both branch
pointers are formed unconditionally and selected with `tl.where` over integer
addresses, followed by a single typed-pointer cast. This removes the dynamic
`if is_k` assignments whose later uses failed Triton 3.2 TTGIR dominance
verification. The `HAS_GATE`, `HAS_PASS`, and `ENABLE_PDL` constexpr behavior
and numerical operations are unchanged.


## 执行分支与commit
- **报告中提及的commit/HEAD候选：** `7224d14629`, `a94c11c100`
  - 候选值可能是代码目标、baseline 或对照commit；若原文未声明角色，卡片不擅自指定为执行target。
- **归集来源快照：** `3090-24g-hicache` @ `5be7b9b927fab4e45bf5a5cc412737ae06cacf1d`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/CODE-20260909-SM86-QK-DOMINANCE-FIX.md` → `.memory/phase2-hicache-design/work/CODE-20260909-SM86-QK-DOMINANCE-FIX.md`; SHA256 `dad11e9c458639b3b5a79e941346f79d78e365b97559ee0fdea2e57b068e1888`; source state `tracked`
