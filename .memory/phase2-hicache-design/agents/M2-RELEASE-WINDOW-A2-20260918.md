---
task_id: M2-RELEASE-WINDOW-A2-20260918
agent: devops-executor
status: BLOCKED
date: 2026-09-18
---

# M2 发布窗口 A2 — BLOCKED（方法仍不可达 exit 0：BLOCKER-4 未修复）

## Task

在单窗口内，用**已裁定的修正 freeze 命令**把 M2 新冻结树（detector 加固 + telemetry + HiCache trio）
上线 `:30000`；只冻 M2，M1 字节不变；失败即回滚。执行角色：只执行已定义方法，不改方法、不诊断设计、
不扩大范围。本文件为结果 artifact。

## Scope

- In scope：步骤 1–9（pre-window 记录 / stop-m2.sh / move-aside / freeze / 树内 CPU 核验 / 起服 /
  验收 / 恢复 `:30000` / 回滚）。
- 禁（本任务原文）：动 M1 树/字节；`pkill`/`killall`；改权重；就地改冻结树 `src/`；GGUF 入库；
  `:30000` 以外端口；改仓库内 allowlist/freeze.sh/launcher-repin.sh。
- 大输出目录：`.memory/phase2-hicache-design/work/M2-RELEASE-WINDOW-A2-20260918/`。

## Result

**未进入发布窗口，未停 `:30000`，未 move-aside，未 freeze，未触碰任何 `/opt` 树与仓库工具文件。
终态 BLOCKED。**

本 invocation 在**任何破坏性动作之前**对任务给定的**逐字 freeze 命令**做 CPU-only 端到端预演
（dest 置于 `/tmp`，非生产路径），实测 **`FREEZE_RC=5`**：方法在 `repin launcher` 阶段必然失败，
**不可能到达 exit 0**，更无法进行到停服/移树/起服。故按角色约束「方法无效即 BLOCKED 并停止」，
保留现状并回报，不进入窗口。

这是上一轮 `M2-RELEASE-WINDOW-A2-20260918` 已记录的 **BLOCKER-4**（方法/工具缺陷：repin 内置
dry-run 步骤 6a/6b 的 `env -i` 未提供 `SGLANG_L3_MODE`，与新 M2 模板第 36 行 fail-closed 冲突）。
本派单**未包含**该缺陷的修正项，工作树中的工具**未改变**，且该缺陷需改动 `launcher-repin.sh`
（`--no-dry-run` 缺失于 `freeze.sh:241` 调用）或 `freeze.sh`——均为本执行角色**无授权改动**的文件。
本窗口对 BLOCKER-3 的授权（`--allowed-source-change tools/validate_telemetry.py`）已按任务逐字包含，
但**不足以**绕过 BLOCKER-4：失败发生在其**之前**的 repin 阶段。

## Evidence

采集时间 2026-09-18T21:18–21:20Z。

### E1. 本 invocation 逐字冻结命令 → `FREEZE_RC=5`（决定性，第一手）
命令（dest/work 均在 `/tmp`，**非生产路径**；其余逐字照抄任务步骤 4）：
```
bash 3090-dev/tools/freeze/bin/freeze.sh --build-candidate \
  --src /tmp/opencode/m2-stage2-20260918 \
  --dest /tmp/opencode/m2-a2-freeze-e2e-<stamp>/dest \
  --identity LOCAL-PROD-v1.2.1-M2 \
  --tree-name local-prod-v1.2.1-candidate-M2 \
  --baseline-tree /opt/sglang/local-prod-v1.1-candidate \
  --allowed-source-changes-file 3090-dev/tools/freeze/pins/local-prod-v1.2-candidate-allowlist.txt \
  --allowed-source-change tools/validate_telemetry.py \
  --work-dir /tmp/opencode/m2-a2-freeze-e2e-<stamp>/work
FREEZE_RC=5
```
完整 stdout：`work/M2-RELEASE-WINDOW-A2-20260918/freeze-e2e.stdout.txt`；repin 日志：
`work/M2-RELEASE-WINDOW-A2-20260918/freeze-e2e.repin.log`。关键段：
```
### install identity tools            ok
### repoint tools/validate_telemetry.py
repoint OK: .../dest/tools/validate_telemetry.py -> .../dest/src (bindings 10/10 verified)
### provisional manifest               ok: 14790 entries
### env symlink                        ok: env -> /home/ubuntu/venvs/sglang-3090
### repin launcher
launcher repin FAILED; log:
   rendered -> .../work/repin/launch.sh.rendered
   bash -n: OK
LAUNCHER-AUDIT PASS: .../work/repin/launch.sh.rendered
dry-run negative test FAILED: shared run id should exit 4, got 1
.../launch.sh.rendered: line 36: SGLANG_L3_MODE: FATAL: SGLANG_L3_MODE must be set explicitly to 'disabled' for M2 (no default)
```
注：`source-scope.json` 在本次运行中**从未生成**（失败早于 source-scope 门，`freeze.sh:190` 的
repin 位于其后的 `305+` 范围门之前）；这与 STAGE2 已记录的 gate-corrected RC=0 不冲突——本方法
根本到不了那一步。

### E2. 隔离复现 repin（第一手）
```
bash 3090-dev/tools/freeze/bin/launcher-repin.sh --write \
  --tree /tmp/opencode/m2-a2-repin-repro-<stamp>/tree \
  --identity LOCAL-PROD-v1.2.1-M2 --scratch .../scratch
REPIN_RC=24
```
证据：`work/M2-RELEASE-WINDOW-A2-20260918/repin-repro.stdout.txt`。与 E1 同因：
步骤 6a（`launcher-repin.sh:153`）用 `env -i` 且变量表**不含 `SGLANG_L3_MODE`**，M2 模板第 36 行
未设该变量即 `rc 1`（而非步骤 6a 要求的 `rc 4`）⇒ repin `exit 24` ⇒ freeze `exit 5`。

### E3. 工具当前状态（工作树，未改）
```
grep -n SGLANG_L3_MODE 3090-dev/tools/freeze/bin/launcher-repin.sh   -> NO_MATCH
grep -c no-dry-run       3090-dev/tools/freeze/bin/freeze.sh          -> 0
freeze.sh:241  "$REPIN" --write --tree "$DEST" --identity "$IDENTITY" \
                  --scratch ... （未传 --no-dry-run）
templates/launch.sh.m2.tmpl:36  : "${SGLANG_L3_MODE:?FATAL: ... no default}"
git diff --stat launcher-repin.sh -> 4 insertions（仅 identity 选模板），env -i 块未含 L3_MODE
```
即：BLOCKER-4 的修复**未落地**。

### E4. Pre-window 状态（未动）：`:30000` 全程 UP、身份未变
```
loopback /health=200  LAN(192.168.20.250) /health=200  loopback /v1/models=200
served id=/data/models/omnicoder-9b-gptq-int4
m2.pid=1851500  supervisor_pid=1851473
run_id=m2-20260918T190239Z-1851237（未变）
tree=/opt/sglang/local-prod-v1.2.1-candidate-M2  cold_start_s=111.8  started_at=2026-09-18T19:04:31Z
state/ready/m2.ready 存在；gpu-owner.json role=m2 state=held pid=1851500 port=30000
ss -ltnp :30000 LISTEN pid=1851500
nvidia-smi compute apps: 1851500(300MiB) + 1851964 sglang::scheduler(19170MiB，M2 子进程)
无其它 GPU 持有者；无 /opt/sglang/.pre-windowA2-* 目录
```
证据：`work/M2-RELEASE-WINDOW-A2-20260918/prewindow-state.txt`。

### E5. 基线 sha 与 M1 字节（窗口前，用于回滚/不变式）
```
old M2 launcher/launch.sh       9a557d5f06dad5481b8e850c7b9b02ae29db276dc232b6baa1ac7e92d93b21c4
old M2 manifest/TREE-SHA256.txt e6e8de1cb117e89e7a7477582d41f6408a032c9f0e7e45c7408f0d98677c495a
old M2 manifest/identity.json   f46e49b8f562040809dff4d081eabaaba52337f4acdc3e2539abf69cdb5fb1bc
M1 detector                     92eeaeaf02ac1c1e966a8b9bbd4393141353ca9177265044fe12e250c0e38089（未变）
stage2 detector                 848e0690cb80719e70c7ceedb7c1eb253c879d39a1b7be1cb85645f861a9d151（符合目标）
```
`/opt/sglang/local-prod-v1.2.1-candidate-M2` 与 `/opt/sglang/local-prod-v1.1-candidate` 目录
mtime/所有权未变；仓库 tracked 变更集与本 invocation 开始时相同（未新增）；pre-validation 仅写
`/tmp/opencode/**` 与 `work/**`。

### E6. `:30000` 恢复上线（binding §109）
本任务**从未停止** `:30000`，因此**无新 run_id**。窗口结束时生产仍为原进程、原 run：
- 恢复/保持上线时刻：本次采集 **2026-09-18T21:19:53Z**（loopback `/health`=200 实测）。
- run_id：`m2-20260918T190239Z-1851237`（pid 1851500）。
- health 证据：loopback 200 / LAN 200 / `/v1/models` 200，见 E4。

## Defects or blockers

### BLOCKER-4（方法/工具缺陷，本 invocation 决定性复现）
- 现象：任务给定的逐字 `freeze.sh --build-candidate` 在 repin 阶段 `exit 5`，**不可能 exit 0**。
- 根因：`launcher-repin.sh` 的 dry-run 负例步骤 6a（`:153`）与其正例 6b（`:168`）用 `env -i`，变量表
  不含 `SGLANG_L3_MODE`；`launch.sh.m2.tmpl:36` 对该变量无默认、fail-closed ⇒ 负例得 `rc 1` 而非
  步骤要求的 `rc 4` ⇒ `exit 24`；`freeze.sh:241` 未传 `--no-dry-run` ⇒ repin 失败即 `freeze.sh exit 5`。
- 证据：E1、E2、E3。
- 授权边界：修复须改 `launcher-repin.sh`（步骤 6a/6b 的 `env -i` 加 `SGLANG_L3_MODE=disabled`）、或
  `freeze.sh:241` 加 `--no-dry-run`、或改模板第 36 行——三者均属本任务**明令禁止/无授权**的仓库工具文件。
  本派单的授权仅覆盖 BLOCKER-3（`--allowed-source-change tools/validate_telemetry.py`），不覆盖 BLOCKER-4。
- 最小所需条件：方法所有者对 BLOCKER-4 做出修正裁决并落地**一处**工具改动（推荐：`launcher-repin.sh`
  步骤 6a/6b 的 `env -i` 显式加 `SGLANG_L3_MODE=disabled`，不改变生产 launcher 的 fail-closed 语义），
  然后以**新 invocation** 重发本窗口；届时本 artifact 的 E1/E2/E5 证据可直接复用。

### 未决登记（移交 orchestrator，不阻塞修复）
- ledger §117 正文在本盘 ledger 中**未找到**（仅在 CONTROL STATE L24-25 与 §116 引用）；验收「7a–7f」
  无逐字出处。本 artifact 按任务派单逐字执行，未据 §117 正文推断额外授权。

## Remaining claims or exclusions

- 本 invocation **未**执行：stop/start、move-aside、freeze 到生产路径、绑定端口、发信号、改 `/opt`/
  `/data`/仓库 allowlist/freeze.sh/launcher-repin.sh/templates、改权重。
- `:30000` 全程 UP；M1 与现冻结 M2 字节均未改动；无 move-aside/failed 目录产生。
- **未验证**：修正 BLOCKER-4 后 freeze 的其余门禁（fidelity / manifest 确定性 / immutability / repin
  GATE 1-3 / preflight）与步骤 5–7 的所有验收——因未到达该阶段，不得由本 artifact 推断为通过。
  注意 STAGE2 已单独验证 source-scope 门在**追加 `--allowed-source-change tools/validate_telemetry.py`**
  后 RC=0；那只证明范围门，不代表 repin 之后的链路。
- BLOCKER-4 属**方法/工具缺陷**，非环境故障，非本执行角色可自行修正。

## Next

1. **orchestrator**：就 BLOCKER-4 做方法所有者裁决并落地**一处**已授权工具改动（首选：`launcher-repin.sh`
   步骤 6a/6b 的 `env -i` 增加 `SGLANG_L3_MODE=disabled`）。改动属 repo 工具写域，需另派授权 invocation。
2. **修正后新 invocation**：重跑本窗口（同一逐字命令 + BLOCKER-3 的 `--allowed-source-change`），
   预期 `freeze exit 0`；随后按步骤 5–8 核验/起服/验收/恢复并回报。
3. 在获授权前**不**采取任何窗口动作；`:30000` 保持现状。

## Terminal state

BLOCKED

## Artifact

`.memory/phase2-hicache-design/agents/M2-RELEASE-WINDOW-A2-20260918.md`
