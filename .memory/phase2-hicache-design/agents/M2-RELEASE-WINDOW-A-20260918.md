# M2-RELEASE-WINDOW-A-20260918

Task / Scope / Result / Evidence / Defects or blockers / Remaining claims or exclusions / Terminal state: DONE|BLOCKED

Terminal state: BLOCKED

## Task
在单个发布窗口内，按 `QWEN3CODER-INVALID-INDEX-PROD-20260918.md` 的 runbook 将 M2 新冻结树
（detector 加固 + telemetry + HiCache trio）上线 `:30000`。只冻 M2，M1 字节必须保持不变；任何步骤失败
即回滚。本任务为**执行**角色：只执行已定义方法，不诊断、不设计、不选择替代方案、不扩大范围；方法无效
或越权须报 BLOCKED 并停止。产出终态 artifact 即本文件。

## Scope
- In scope：按 runbook 步骤 4–12 执行停服 / 移树 / freeze / 起服 / 校验；记录命令、输出、变更资源与验证证据。
- Out of scope（本任务明确禁止）：修改 M1 树与 M1 冻结树、`pkill`/`killall`、改权重、就地改冻结树 `src/`、
  GGUF 入库、绑定 `:30000` 以外的端口、编辑 `freeze.sh`/allowlist/`launcher-repin.sh`/`validate_telemetry.py`、
  诊断或设计新方法。停服预告已由 owner 授权。
- Artifact：本文件。大体积证据（manifest 与 scope JSON）：
  `.memory/phase2-hicache-design/work/M2-RELEASE-WINDOW-A-20260918/`。

## Result
**未进入发布窗口，未停止 `:30000`，未做任何破坏性动作。** 在执行前对 runbook 步骤 2 与步骤 7 的
输入做确定性门禁复现时，发现两处方法缺陷，导致按 runbook 字面命令**无法达成 freeze exit 0**：

- **BLOCKER-1（命令缺陷）**：runbook 步骤 7 给出的 `freeze.sh` 命令**缺少 `--allowed-source-changes-file`**。
  `freeze.sh` 的 `ALLOWED_SOURCE_CHANGES_FILE` 默认为空，且**无任何自动加载**（仅由该 CLI 参数注入，
  `freeze.sh:60,86,311-317`；全仓库无其它注入点）。缺此参数时，源码范围门使用内置 2 条 literal
  allowlist，而 stage 相对 baseline v1.1 有 140 条新增路径、且 7 个 `src/` 文件内容非预期变化
  （因为这些路径本应由 164 条 allowlist 覆盖）。结果：`compare` RC=1 → `freeze.sh` 在源码范围门
  `exit 8`，**不可能 exit 0**。
- **BLOCKER-2（基底缺陷）**：runbook 步骤 2 要求"以现冻结 M2 树为基底"构造 stage，但该基底本身
  `tools/` 与 `launcher/` 与 baseline 不同：含 `tools/l3_namespace.py`、`tools/preflight_identity.py`，
  且 `launcher/launch.sh`、`tools/validate_telemetry.py` 已被重绑定/重指向。若以其为 `--src`，即使补上
  allowlist，源码范围门仍报 `unapproved_added=['tools/l3_namespace.py','tools/preflight_identity.py']` 与
  `changed unexpectedly=[./launcher/launch.sh, ./tools/validate_telemetry.py]`（allowlist 条目全部为
  `src/` 前缀，不含 `tools/`；`tools/` 由 `freeze.sh:195-196` 在门禁**之后**安装，故源清单里不应预置）。
  RC=1 → 同样 `exit 8`。

对照实验：仅当 `--src` = D4 定义的 `/tmp/opencode/v1.2.1-stage`（其 `src` 与现冻结 M2 逐字节相同，
`tools/`仅 `validate_telemetry.py`、`launcher/launch.sh` 与 baseline 同 sha）**且**带上 164 条 allowlist 时，
源码范围门才 `RC=0`、`unapproved_added=[]`、`unapproved_changed=[]`。即：runbook 步骤 2 的基底描述与
步骤 7 的命令**互相冲突**，两者均无法按字面达成 `exit 0`。

因角色约束（不得自行修正方法/编辑 allowlist/选择替代命令），在 freeze 门禁这一**破坏性动作之前**停止，
并保留 `:30000` 现状。

## Evidence
采集时间 2026-09-18T20:52Z；采集时未执行任何冻结/停服。

### E1. `:30000` 仍 UP、身份未变（证明未进入窗口）
```
curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:30000/health     -> 200
curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://192.168.20.250:30000/health -> 200
curl -s http://127.0.0.1:30000/v1/models -> served id: /data/models/omnicoder-9b-gptq-int4
state/pids/m2.pid      -> 1851500
state/runs/m2.run      -> run_id=m2-20260918T190239Z-1851237 supervisor_pid=1851473
                          tree=/opt/sglang/local-prod-v1.2.1-candidate-M2 cold_start_s=111.8
state/gpu-owner.json   -> role=m2, state=held, pid=1851500, port=30000, run_id 同上, l3_namespace=""
```
无新 run_id，无新 pid，无 move-aside 目录（`/opt/sglang/` 下不存在 `pre-detector*`/`failed-detector*`）。

### E2. M1 字节未变（约束满足）
```
/opt/sglang/local-prod-v1.1-candidate                                       (root:root 755, 存在)
.../src/python/sglang/srt/function_call/qwen3_coder_detector.py sha256
  = 92eeaeaf02ac1c1e966a8b9bbd4393141353ca9177265044fe12e250c0e38089   (pre-fix，与冻结 M1 一致)
```
M1 树全程只读、无写入。

### E3. 缺陷门禁复现（确定性，本任务新跑）
命令（`MT=3090-dev/tools/freeze/pysrc/manifest_tool.py`，`BASE=/opt/sglang/local-prod-v1.1-candidate`）：

- **RUN A（runbook 字面：无 allowlist，D4 stage 基底）**
  `python3 $MT compare --source $BASE/manifest/TREE-SHA256.txt --dest <stage manifest> --allow-modified "" --json`
  → `RC=1`；`added=140`；`changed_allowed=0`；`errors=['7 file(s) changed content unexpectedly: ./src/.gitignore, ./src/python/sglang/srt/mem_cache/storage/extent/extent_allocator.py, …']`。
  证据：`work/.../_repro_A2.json`、`_stage_scope_none.json`。
- **RUN B（补 allowlist + D4 stage 基底）**
  `--allow-modified "$(164 条 allowlist 以逗号连接)"`
  → `RC=0`；`unapproved_added=[]`；`unapproved_changed=[]`。
  证据：`work/.../_repro_B.json`、`_stage_scope_allow.json`。
- **RUN C（补 allowlist + runbook 步骤 2 基底=现冻结 M2 树内容）**
  → `RC=1`；`unapproved_added=['tools/l3_namespace.py','tools/preflight_identity.py']`；
  `unapproved_changed=['./launcher/launch.sh','./tools/validate_telemetry.py']`。
  证据：`work/.../_repro_C.json`、`_synthetic_scope.json`、`_scope_m2_allow.json`。

### E4. 机制证据
```
freeze.sh:60   ALLOWED_SOURCE_CHANGES_FILE=""                 # 默认空
freeze.sh:86   --allowed-source-changes-file) ...             # 唯一注入点
freeze.sh:311-317  仅当非空才加载 allowlist                    # 无自动加载
grep -rn "allowed-source-changes-file" --include=*.sh .       # 仅 freeze.sh:86，无 wrapper
manifest_tool.py compare: 不在 allow 且内容不同 => reason=UNEXPECTED => errors => RC!=0
freeze.sh:326-364 门禁：unapproved_added or unapproved_changed or gguf => exit 8
```
`3090-dev/tools/freeze/pins/local-prod-v1.2-candidate-allowlist.txt`：167 行 / 164 条，**全部 `src/` 前缀**，
无 `tools/`、无 `launcher/` 条目；sha256=`915f89243495fcbfa86a100e39225e0e18ba4f98cbeebf21a29a1678015fe497`。

### E5. 基底差异证据
```
现冻结 M2 tools/   : l3_namespace.py, preflight_identity.py, validate_telemetry.py
baseline  tools/   : validate_telemetry.py
D4 stage  tools/   : validate_telemetry.py
D4 stage  launcher/launch.sh sha256 = a69d231e…  == baseline 同值
D4 stage  /tmp/opencode/v1.2.1-stage/src 与现冻结 M2 src 逐字节相同（14784 文件，无 diff）
```

## Defects or blockers

### BLOCKER-1 — runbook 步骤 7 缺 `--allowed-source-changes-file`
- 现象：字面命令（无 allowlist）在源码范围门 `exit 8`，无法 exit 0。
- 证据：E3 RUN A、E4。
- 最小所需条件：提供**已授权、已提交**的修正命令，显式包含
  `--allowed-source-changes-file 3090-dev/tools/freeze/pins/local-prod-v1.2-candidate-allowlist.txt`。

### BLOCKER-2 — runbook 步骤 2 的"基底=现冻结 M2 树"与命令冲突
- 现象：以现冻结 M2 树为 `--src` 时，即使补 allowlist，仍报 2 条未批准 added + 2 条非预期 changed。
- 证据：E3 RUN C、E5。
- 最小所需条件：由方法所有者澄清唯一的 stage 基底（经复现为 D4 定义的
  `/tmp/opencode/v1.2.1-stage`，即 `src` = 冻结 M2 字节、`tools/`/`launcher/` 保持 baseline），
  或授权把 `tools/l3_namespace.py`、`tools/preflight_identity.py` 及
  `launcher/launch.sh`、`tools/validate_telemetry.py` 纳入 allowlist（属 tooling/pins 变更，超出本执行角色权限）。

两 Blocker 共同点：均属**方法/输入缺陷**，非环境故障；修正需方法所有者（非本执行角色）做出。

## Remaining claims or exclusions
- 本任务**未**执行 freeze、未停服、未起服、未移树、未绑定端口、未发信号、未改任何源码/冻结树/allowlist。
- `:30000` 全程保持 UP；M1 字节与 M2 冻结树字节均未改动。
- 未验证：修正命令后 freeze 的其余门禁（fidelity / manifest 确定性 / immutability / repin GATE 1-3 /
  preflight）是否能通过——因未到达该阶段。这些仍是未知，不得由本 artifact 推断为通过。
- GPU 上 `sglang::scheduler`(pid 1851964, 19170MiB) 已确认是 M2 pid 的子进程，非其它持有者；
  不构成阻塞。
- 磁盘 `/` 余 19G（97% used），与 D4 记录一致；不构成本次阻塞。

## Next
1. **执行侧**：等待 orchestrator 转交方法所有者的修正裁决（BLOCKER-1 的完整命令 + BLOCKER-2 的唯一基底）。
   在获授权前不采取任何窗口动作。
2. **修正后**（由 orchestrator 重新派发新执行 invocation）：以修正命令重跑
   `freeze.sh --build-candidate`，预期 `exit 0`；随后按 runbook 步骤 8–12 校验/起服/回报。
3. 本 artifact 已置为终态 `BLOCKED`，不释放任何依赖；不执行停服。
