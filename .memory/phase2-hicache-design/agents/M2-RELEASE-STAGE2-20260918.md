# M2-RELEASE-STAGE2-20260918

status: BLOCKED

## Task
离线产出**已通过源码范围门（RC=0）的冻结交付 stage**，供随后极窄窗口一次 freeze 成功。不得停/起
`:30000`，不得碰 `/opt/**` 冻结树。只执行已定义方法（M2-HICACHE-RELEASE-DESIGN-R2-20260918 D4 +
M2-RELEASE-WINDOW-A-20260918 的两个 blocker 裁决），不设计、不扩大范围。

## Scope
- 写域：仅 `/tmp/opencode/m2-stage2-20260918/` 及本 artifact（与大输出目录
  `.memory/phase2-hicache-design/work/M2-RELEASE-STAGE2-20260918/`）。
- 禁：停/起服务、绑 `:30000`、改 `/opt/**`、`/data/**`、`python/**`、`3090-dev/**`、GPU、commit/push、
  编辑仓库内 allowlist/freeze.sh/validate_telemetry。

## Result

**stage 已按 D4 完整构建，但源码范围门无法在已授权方法下达成 RC=0。终态 BLOCKED。**

1. **stage 构建完成**（`/tmp/opencode/m2-stage2-20260918/`，top-level 恰为 `src/ launcher/ tools/`）：
   - 以 D4 基底 `/tmp/opencode/v1.2.1-stage` 复制（`cp -a`）。
   - 覆盖 D4 的 14 条路径（12 modified + 2 added）。detector sha =
     `848e0690cb80719e70c7ceedb7c1eb253c879d39a1b7be1cb85645f861a9d151`（DETECTOR_SHA_OK）。
   - 14 条中 12 条相对原 stage 有 DIFF，2 条原 stage 不存在（ABSENT→added）。
   - stage 源清单确定性：重生成得到 14788 行，与 `stage2-source.txt` 逐字节相同。
2. **D4 步骤 4 重绑完成**：stage2 `tools/validate_telemetry.py` 的 `SOURCE_HASHES`
   `unified_radix_cache.py` `5b5dc29f…`→`4a512882…`；该文件相对原 stage 仅此 1 处（2 行）变化；
   编辑后 sha = `c62b3d5b35eb47bcf6cc651387ae2ccd5142d099bdf69ea598bbe39cc2a6362c`。
   `repoint_telemetry.py` dry-run（`--tree` = stage2）PASS：`bindings_checked=10`、
   `mismatched=[]`、`missing=[]`、audit ok。
3. **门禁字面复现 RC=1**（决定性）：以 `freeze.sh:311-319` 的精确语义（2 条内置 + 164 条 allowlist，
   逗号连接）对 stage2 源清单跑 `manifest_tool.py compare`：
   - RC=1；`added=142`；`changed_allowed=20`；
     `errors=['1 file(s) changed content unexpectedly: ./tools/validate_telemetry.py']`；
     `unapproved_added=[]`、`unapproved_changed=[]`。
   - 依 `freeze.sh:325`，RC≠0 ⇒ **exit 8**。
   - 证据：`work/M2-RELEASE-STAGE2-20260918/gate-literal.json`、`source-scope.json`。
4. **最小修正已验证可达 RC=0**：仅需把 `tools/validate_telemetry.py` 追加进 source-scope allow
   （CLI `--allowed-source-change tools/validate_telemetry.py`，或 allowlist 增该条），则：
   RC=0；`added=142`；`changed_allowed=21`；`errors=[]`；`unapproved_added=[]`；`unapproved_changed=[]`。
   证据：`gate-corrected.json`、`scope-allow-joined-withtools.txt`。
5. **未执行 freeze、未停/起服、未碰 `/opt` 与仓库内 allowlist/freeze.sh**；`:30000` 全程 UP。

## Evidence

采集时间 2026-09-18T21:00–21:03Z；`curl 127.0.0.1:30000/health -> 200`。

- **E1 stage 布局与 base sha**
  ```
  ls -A /tmp/opencode/m2-stage2-20260918          -> launcher  src  tools
  /tmp/opencode/v1.2.1-stage/tools/validate_telemetry.py
    sha256 = d1e8b95e73ca80c28d23c33811160e3b639345cc4815eb4d16d08910683eae4c  (== baseline)
  /tmp/opencode/m2-stage2-20260918/tools/validate_telemetry.py
    sha256 = c62b3d5b35eb47bcf6cc651387ae2ccd5142d099bdf69ea598bbe39cc2a6362c
  stage2/src/python/.../qwen3_coder_detector.py
    sha256 = 848e0690cb80719e70c7ceedb7c1eb253c879d39a1b7be1cb85645f861a9d151
  ```
- **E2 重绑 diff**（仅 unified_radix_cache 一行，2 行变化）
  `work/.../validate_telemetry.diff`：
  `- "5b5dc29fa21eefdf44ac660881cab02e9bc6ab1408cd33ca645a4bb326f6bf6f"` →
  `+ "4a5128828dc2cf67a214c794984be6f2d5177178d64cda070e35e467ec03fe1b"`。
- **E3 重绑后 repoint dry-run PASS**
  ```
  python3 3090-dev/tools/freeze/pysrc/repoint_telemetry.py \
    --file /tmp/opencode/m2-stage2-20260918/tools/validate_telemetry.py \
    --tree /tmp/opencode/m2-stage2-20260918 --identity LOCAL-PROD-v1.2.1-M2 --json
  -> ok true, exit_code 0, bindings_checked 10, bindings_mismatched [], missing []
  ```
  证据：`work/.../repoint-dryrun-stage2.json`。
- **E4 字面门禁 RC=1（allowlist-only）** 见 Result 3；`gate-literal.json`。
- **E5 修正门禁 RC=0（+tools allow）** 见 Result 4；`gate-corrected.json`。
  21 条 changed_allowed = 20 条 `src/…` + `./tools/validate_telemetry.py`；142 条 added 含 D4 的
  `./src/python/sglang/srt/parser/qwen35_reasoning_policy.py` 与
  `./src/test/registered/unit/parser/test_qwen35_reasoning_policy.py`。
- **E6 机制**（本任务实测）
  ```
  baseline TREE-SHA256.txt 含 ./tools/validate_telemetry.py（grep -c = 1）
  freeze.sh:305 gen_coreutils "$SRC" 把 ./tools/validate_telemetry.py 纳入 SRC_MAN
  freeze.sh:321-322 compare --source <baseline>/manifest/TREE-SHA256.txt --dest $SRC_MAN
  freeze.sh:311-319 SCOPE_ALLOW = 2 builtins + allowlist 文件条目（无其它注入点）
  allowlist 167 行/164 条，全部 `src/` 前缀（含 `src/3090-dev/tools/...` 树内路径），
    无顶层 `tools/` 或 `launcher/` 条目；sha 915f8924…497（未改）
  freeze.sh:202-216 repoint 对 $DEST/tools/validate_telemetry.py 验证 6+4 绑定，
    绑 5b5dc29f 而 stage src 为 4a512882 ⇒ 若不预重绑则 exit 5
  ```
- **E7 环境不变量**
  `curl 127.0.0.1:30000/health -> 200`（全程）。
  `git status --porcelain -uno` 仅既有 tracked 变更（含 `M 3090-dev/tools/freeze/pins/local-prod-v1.2-candidate-allowlist.txt`、
  `M 3090-dev/tools/freeze/bin/freeze.sh` 等他方既有改动），本任务未新增 tracked 变更；
  allowlist 文件 sha 与任务开始时一致（未 edit）。
- 证据文件清单：
  `work/M2-RELEASE-STAGE2-20260918/{overlay-table.txt, validate_telemetry.diff, stage2-source.txt,
  stage2-source-regen.txt, gate-literal.json, source-scope.json, gate-corrected.json,
  scope-allow-list.txt, scope-allow-joined.txt, scope-allow-list-withtools.txt,
  scope-allow-joined-withtools.txt, repoint-dryrun-stage2.json, repoint-dryrun-origstage.json}`。

## Defects or blockers

### BLOCKER-3 — D4 步骤 4 的强制重绑与 source-scope allowlist 冲突（新发现）
- **现象**：D4 步骤 4 强制把 stage 的 `tools/validate_telemetry.py` 重绑（否则 `repoint_telemetry.py`
  在 freeze 内 fail-closed → `exit 5`）。此编辑使该文件相对 baseline 内容变化，而 source-scope
  allowlist 全部为 `src/` 前缀、**无顶层 `tools/` 条目** ⇒ 按已授权的 allowlist-only 方法，
  源码范围门恒为 RC=1 → `freeze.sh exit 8`。二者互斥，与 BLOCKER-1/2 同属**方法/输入缺陷**。
- **决定性对照**：仅追加 `tools/validate_telemetry.py` 到 allow 后 RC=0（Result 4）。
- **为何不在本角色内自决**：允许一条额外生产路径与 baseline 不同，属**授权/策略决定**；
  `M2-HICACHE-RELEASE-DESIGN-R2` 明确将 allowlist/tooling/validate_telemetry 的改动列为
  "separate authorized changes, not part of this READ-ONLY design"（该件 L349-351）；
  派单亦禁编辑仓库 allowlist。上一窗口已就"扩大 allow 范围"裁定超出执行角色权限。
- **最小所需条件（二选一，由方法所有者裁决并写入修正命令）**：
  1. 修正后的 freeze 命令在 §116 的基础上**追加**
     `--allowed-source-change tools/validate_telemetry.py`（`freeze.sh:85` 可重复参数）；
     或
  2. 授权把 `tools/validate_telemetry.py` 写入
     `3090-dev/tools/freeze/pins/local-prod-v1.2-candidate-allowlist.txt`（属 tooling/pins 变更，
     超出本执行角色权限；需另派授权 invocation）。
  本任务已验证：两种形式均使 `source-scope.json` 变为 RC=0 / `unapproved_*=[]` / changed_allowed=21。

> 备注（不构成新阻塞）：stage2 的 gate-corrected 结果与上一窗口 `_repro_B`（RC=0, added=140,
> changed=19）不同，属预期——`_repro_B` 用的是**未重绑**的 `/tmp/opencode/v1.2.1-stage`；本 stage2
> 按 D4 步骤 3+4 多出 rebind 与 2 条 D4 added，故 added=142、changed_allowed=21。

## Remaining claims or exclusions
- 本任务**未**执行 freeze、未停服、未移树、未绑定端口、未发信号、未改任何 `/opt` 冻结树、
  未改仓库内 allowlist/freeze.sh/launcher-repin.sh/validate_telemetry。
- `:30000` 全程 UP；M1 与现冻结 M2 字节未改动。
- stage2 的 `tools/validate_telemetry.py` 是**stage 内副本**的编辑，非仓库文件编辑。
- 未验证：修正命令后 freeze 的其余门禁（fidelity / manifest 确定性 / immutability / repin /
  preflight）是否通过——未到达该阶段，不得由本 artifact 推断为通过。
- "`tools/validate_telemetry.py` 应为允许变更路径"是**待方法所有者裁决的授权问题**，本 artifact
  仅记录实测事实与最小条件，不做授权推断。

## Next
1. **orchestrator**：就 BLOCKER-3 做方法所有者裁决（二选一），产出含该 allow 的完整修正 freeze 命令，
   或在授权 invocation 中落 allowlist 条目。
2. **修正后新窄窗口 invocation**（非本任务）：`freeze.sh --build-candidate --src /tmp/opencode/m2-stage2-20260918
   --dest /opt/sglang/local-prod-v1.2.1-candidate-M2 --identity LOCAL-PROD-v1.2.1-M2
   --tree-name local-prod-v1.2.1-candidate-M2 --baseline-tree /opt/sglang/local-prod-v1.1-candidate
   --allowed-source-changes-file 3090-dev/tools/freeze/pins/local-prod-v1.2-candidate-allowlist.txt
   --allow-production-dest`（**并按裁决追加** `--allowed-source-change tools/validate_telemetry.py`
   或已授权 allowlist 条目）。
3. stage2 与全部证据已就位，可直接复用，无需重建。

## Terminal state
BLOCKED

## Artifact
`.memory/phase2-hicache-design/agents/M2-RELEASE-STAGE2-20260918.md`
