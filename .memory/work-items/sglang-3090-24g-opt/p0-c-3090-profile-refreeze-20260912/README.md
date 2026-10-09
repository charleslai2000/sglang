# P0-C-3090-PROFILE-REFREEZE-20260912

- **工作标题：** P0-C-3090-PROFILE-REFREEZE-20260912
- **来源仓：** `sglang-3090-24g-opt`
- **合并阶段/报告：** 2
- **收集时 branch/HEAD：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`

## 工作目标
**`phase2-hicache-design/work/R124-profile/P0-C-3090-PROFILE-REFREEZE-20260912.md`：**
- Task: `P0-C-3090-PROFILE-REFREEZE-20260912` (follows the R117 freeze).
- Reason: user-authorized Option 1 — the HOST_ALLOC wake-liveness fix changed a
producer source file (`scheduler.py`), so the running build is no longer the
one R117 bound. R117 remains **immutable**; this is a NEW freeze.
- Scope: no profile/param change; only the build binding and live process identity
change. Launch argv is byte-identical to R117.

**`phase2-hicache-design/work/R128-profile/P0-C-3090-PROFILE-REFREEZE-20260912.md`：**
- Task: `P0-C-3090-PROFILE-REFREEZE-20260912-P2A` (follows the R124 freeze).
- Reason: the user-authorized P2-A observation-only probe edited three producer
files (`scheduler.py`, `unified_radix_cache.py`, `hybrid_cache_controller.py`)
and added `p2a_timing_probe.py`, so the running build is no longer the one R124
bound. R117 and R124 remain **immutable**; this is a NEW freeze.
- Scope: NO profile/param change (same `launch-r112.sh`, byte-identical 59-token
argv). Only the build binding, live process identity, log path, and one
observability env toggle change.

## 实际改了什么
R124 followup 只做 user-authorized P0-C refreeze：HOST_ALLOC scheduler fix 已改变 producer build，因此记录新 live process identity/build binding；R117 freeze 保留不可变。无 profile/参数修改，launch argv 与 R117 byte-identical。关联的后续 R128 是 P2-A probe 的另一轮 refreeze，三个 producer file 与 timing probe 改动触发新 binding；不要把 R128 改动算入 R124。

## 生成结果与验收
R124 将当时 local RTX 3090 server PID/child、health、59-token argv、scheduler hash 与 host pool/L3 状态重新冻结。关键缺陷：telemetry `source_build` digest 路径把 `<repo>/python` 又拼上 `python/...`，所有目标文件落到 `<missing>`，导致常量且不能区分 builds；报告明确未修复（超出 wake-liveness authorization）。可信 binding 必须用 scheduler 单文件 SHA及真实六文件 digest `abe6504f4b8539a9d93ba6461fb7e559d4c95a0384e2481856879ef85f34974b`。这是历史身份/参数重冻结，不代表当前 live server，也不等于 product provenance bug 已修复。


## 执行分支与commit
- **执行target commit：原文未记载/无法提取，未知。**
- **归集来源快照：** `3090-24g-opt` @ `ad749d6f283b7d6c59a8df928304325eda90e98b`
- 来源branch/HEAD仅标识提供报告的仓库快照，不替代报告记录的运行目标。

## 原始报告（事实依据）
- `phase2-hicache-design/work/R124-profile/P0-C-3090-PROFILE-REFREEZE-20260912.md` → `.memory/rh-p0c-runtime-provenance/R124-profile/P0-C-3090-PROFILE-REFREEZE-20260912.md`; SHA256 `cbdc2202ca2c913795d9103d76cf9e5ff7f61d0ea0f082da587b8ccbbcee267d`; source state `tracked`
- `phase2-hicache-design/work/R128-profile/P0-C-3090-PROFILE-REFREEZE-20260912.md` → `.memory/rh-p0c-runtime-provenance/R128-profile/P0-C-3090-PROFILE-REFREEZE-20260912.md`; SHA256 `5673146b5ce731129d7fa7c177c10a65b805e631cbb653ccddcf72f17bc0d019`; source state `tracked`
