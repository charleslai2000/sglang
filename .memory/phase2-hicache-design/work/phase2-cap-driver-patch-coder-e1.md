# phase2-cap-driver-patch-coder-e1 — gate3_capacity.py 55k 档补丁（③ 阻塞项）

- agent: coder
- epoch: e1
- date: 2026-09-07
- task: phase2-cap-driver-patch-coder-e1

## status: done

## artifacts
- `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/3090-dev/gate3_capacity.py` (modified, 5 edits)

## diff summary
1. `TIER_TARGETS` (L92-96): added `"55k": 55000`, between `"50k": 50000` and `"80k": 80000`. 50k/80k preserved. Docstring line updated to "50K / 55K / 80K".
2. `--tier` argparse (L325): `default="64k"` -> `default="55k"` (now inside `choices=sorted(TIER_TARGETS)`; fixes `invalid choice: '64k'` crash on default path). `help="50k|55k|80k history target"`.
3. Module docstring example commands (L68, L72): `--tier 64k` -> `--tier 55k` in both example invocations (were stale/driving users into the choices crash).
4. `--evidence-dir /root/evidence-capacity-64k-c6` (L69) deliberately LEFT as-is: it is an output directory name, not a tier choice; changing it would alter the output location (out of scope).

Zero changes to: process flow, output schema, argparse interface/parameters (names/types/choices set), engine launch, run_agents/_mkrow structure.

## evidence
- `python3 -m py_compile gate3_capacity.py` -> `PY_COMPILE_OK`
- `python3 gate3_capacity.py --dry-run --agents 4` (no --tier, default path) -> `DRY_RUN_OK ... NO_TIER_EXIT=0` (previously would crash `invalid choice: '64k'`)
- `python3 gate3_capacity.py --dry-run --agents 4 --tier 55k` -> `DRY_RUN_OK ... TIER55k_EXIT=0`
- Both dry-runs print tiers sorted `[('50k',50000), ('55k',55000), ('80k',80000)]`; confirms 55k resolves to 55000 and sits in correct order.
- Note: current env has no `transformers` module -> dry-run reports `tokenizer-unavailable` (pre-existing, graceful, exit 0). Real run on 24052 has the model/tokenizer.

## summary
Both blocking bugs fixed as a minimal atomic patch: (1) TIER_TARGETS now has a 55K tier (55000 tokens, aligning 50k->50000 / 80k->80000 semantics), enabling H0=55K as the primary ③ judgment tier; (2) --tier default no longer picks an out-of-choices value so a bare run no longer crashes. Docstring example commands updated to a valid tier to prevent leading users into the crash. No product code, no push.

## followups
- 24052 real-card sync + real run are owned by tester (I did not touch 24052). File lives at `/home/charles/Workspaces/3rdparty/sglang-3090-24g-hicache/3090-dev/gate3_capacity.py`; sync/copy to the 24052 run path before the real run (as my coder e1 report notes: driver lives locally in 3090-dev/, real card uses sync or copy).

## open_issues
- None blocking. Optional: `transformers` tokenizer unavailable in this local env so the dry-run hit the `tokenizer-unavailable` branch; the real-card run on 24052 (tester-owned) is the authoritative prefill-size check.

## orchestrator note（2026-09-07）
- 补丁本身验收通过。报告最初被该 coder 落到错误项目根 `/home/charles/Workspaces/homenet/.memory/phase2-cap-driver-patch-coder-e1/`；本文件为规范化报头后的 canonical 副本（内容一致），stray 副本保留在 homenet .memory 待后续清理（格式完整可用，非阻塞）。
