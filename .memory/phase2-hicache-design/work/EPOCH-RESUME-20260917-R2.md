# EPOCH RESUME — 2026-09-17 16:43Z (orchestrator R2)

接管入口。权威排序仍以 `HANDOFF-20260917-PRODUCTION-PRIORITY.md` §1（生产优先）为准。
本文件只记录**本 session 的一手复验结果**与**当前活跃工作台账**。

## 0. 对上一 session 收尾报告的更正（依一手证据，非采信）

上一 session 报告「无进程残留 / GPU 完全空闲 / 无 sglang server」。**实测不符**：

| 项 | 上一 session 报告 | 本 session 实测 16:43Z |
|---|---|---|
| GPU 占用 | 1 MiB used / 24124 free | **18291 MiB used** |
| sglang server | 无 | **有孤儿 server pid 1488800** |
| 端口 30165 | 未提 | **LISTEN（gate 保留端口）** |
| canonical lock | 陈旧记录、无持有者 | 陈旧记录（pid 1488437 已死）、**flock 实际 FREE** — 此项报告正确 |

**事实链（一手）**：
- 16:31:50 启动过一次 post-fix final Gate A campaign；16:32:36 取得 canonical lock
  `generation=2 owner=gate-a- pid=1488437`。
- 该 driver（1488437）随后死亡（`/proc/1488437` 不存在），**lock 已释放**（`flock -n` 成功）。
- 但它启动的 server **未被回收**：pid 1488800（`.../env/bin/python -u -m sglang.launch_server`,
  `--port 30165`），pgid/sid 1488800，parent 已 reaped（现为 pid 1）；
  子进程 1488879 / 1488880(`sglang::scheduler`, ~18 GB) / 1488881 / 1489457。
- 归属已确证：`/proc/1488800/environ` 含 `SGLANG_GATE_LOCK=/tmp/opencode/gpu-3090.lock`
  => 它就是我们 harness 自己的子进程，非第三方 workload。
- 该 run **未产出任何 verdict**：`gateA/gate-a-result.json` mtime 仍是 07:54:07（07:41 run 的 INVALID），
  16:31 run 只走到 `launched server s1`，无 gate 结果。
- 该 run 的 server 配置**已带 host-pool 修复**：`Allocating kv hierarchical KV host pool: 79615 tokens,
  1.30 GB`（对比 07:41 run 的 19904 tokens / 0.33 GB 且带 "smaller than the device pool" 警告）。
  => 修复本身生效，campaign 是在启动后被中断的。

## 1. 当前活跃工作台账（本 session）

| id | owner | scope | 依赖 | 终态条件 |
|----|-------|-------|------|----------|
| W1 | devops-executor `ses_f4fbe5a35ffetSQkqY9oUtOR1z` | 清理孤儿 server（identity-checked，term→kill pgid 1488800）+ 从**已提交 repo harness 字节**跑一次性 final Gate A/F1/F2 + canary；每 gate 强制 storage>0 与 host-pool sizing 证据 | — | GATE_A/F1/F2 各自 PASS/INVALID/FAIL + 唯一 blocker；GPU/端口/lock 释放；不启 PROD/DEV |
| W2 | coder `ses_f4fbe59eaffeqUtu1DiCgpQb9A` | 修 `bin/supervise.sh` 的 `sleep 3` 时序竞态（有界轮询，仍 fail-closed） | — | bash -n + OLD-fails/NEW-passes + timeout-failclosed + happy-path 不变的 stub 证据 + diff |
| W3 | coder `ses_f4fbe0da7ffey2X89YCXInima6` | 修 GGUF tokenizer special-token id 绑定（CONTROL+USER_DEFINED 绑到 GGUF 词表自身 id） | — | 缺陷复现 + 正确 encode id 集合 + 0 碰撞 + bos/eos 符合 metadata + HF 路径 inert + 单测通过 |

W2/W3 为 CPU-only，不占 GPU，与 W1 互不重叠。W3 是 owner 已授权的 GGUF 正确性下一步。

## 1b. 工作结果（2026-09-17 16:57Z 复核，以 artifact 为准）

| id | 状态 | 一手核对结果 |
|----|------|--------------|
| W1 | **部分完成 / 报告为空**（子 agent provider 中途失败，未返回正式结果） | 见下。**孤儿已清理**（1488800 消失、lock FREE、端口全空、GPU 空闲）；**Gate A 首次产出真实 verdict**；A-F1/F2/canary **未跑** |
| W2 | **done（已独立复核）** | scaffold `supervise.sh` 已修：`bash -n` rc=0、sha `d3a1742e…f2e6`、diff 与报告一致、两条 identity 断言逐字保留；CPU rig 证明 OLD-fails / NEW-passes / timeout-failclosed / happy-path 不变；未动 canonical lock |
| W3 | 进行中（GGUF tokenizer id 绑定） | — |
| W4 | 已派（新 INVALID 归因裁定） | debugger-deep `ses_f4fb1ac7affeuTe1u8xPG1rTEy` |
| W5 | 已派（把 W2 补丁应用到 repo 副本） | coder 续用 `ses_f4fbe59eaffeqUtu1DiCgpQb9A` |

## 1c. 决定性进展：Gate A 第一次真正走上 L3 storage tier

证据：`/var/log/sglang/local-prod-v1.1/phase9-gates-final-20260916/final-campaign-20260917-r2/gateA/`
（`gate-a-result.json`、`gateA.log`、`server.console.s1.log`；L3 命名空间
`/data/l3/phase9-gates-final-20260916/gateA-gateA-20260917T165123Z-1500213`）

| 项 | 07:41 旧 run | 16:51 r2 run |
|---|---|---|
| host pool kv tokens | 19904（mis-sized，有 smaller-than-device 警告） | **79615 ≥ required 69096**（无警告） |
| `extent_write` | **0（storage 从未被使用）** | **93 事件 / 2,665,513,536 B** |
| L3 命名空间 data 文件 | 0 | **3,489,660,928 B** |
| DEVICE arm | OK | OK（A/B ids 各 32，互异） |
| verdict | INVALID（storage=0，实为读 device） | INVALID，**新原因** |

**新 INVALID 原因**：`kv subtree dropped without backup due to host memory pressure (7 事件)`
（console 16:54:15–18，`root node 83..77`），发生**在 unrelated-filler 阶段**；
紧邻其前是 `ExtentFileBackend: reclaim relocation of 953 live refs refused:
no destination capacity outside victims [1]`。

**算术事实**：host pool 79615 − prompt 65000 = 14015…14615 headroom，而每个 filler 请求
16000 token ⇒ filler **放不进**剩余 host headroom（超出约 1385 token）。

两条竞争假设待裁定（**不得先改再判**）：
- **H-A harness/oracle 问题**：被 drop 的是 unrelated filler（本来就不要求 durable），
  而 graded 65000 prefix 已在 16:53:53–55 写入 L3（2.665 GB）；gate 的检查过宽——
  README 原意是"**graded prefix** 不得 drop"，但 `parse_storage_events` 把任何匹配行都收进
  `dropped_no_backup`（`gate_common.py:716`，调用点在 `gate_a_content_integrity.py:532-539`）。
  若 H-A 成立，最小修复在 **harness**（把检查限定到 graded prefix，和/或按 README 明示把
  `--hc-size` 提到 9|10 使 prompt+filler 同时可容纳）。
- **H-B 产品缺陷**：graded prefix 自身被 drop，或 host-pressure 处理丢失了本应保留/重定位的 durable 数据。

裁定由 W4 用 harness 自带只读 oracle（`wal_forensics.py --mode membership`）判定
graded prefix 是否仍在 extent index。

## 1d. 待收敛项

- W1 未跑 A-F1 / F2 / canary；**在 W4 裁定前不得重跑 Gate A**（否则只会复现同一 INVALID）。
- W1 报告为空属**同一类 provider 失败**（前 session 该 devops-executor 亦反复
  `stream error: socket closed`）。后续同类工作应换机制/更小分片，而非原样重派。
- r2 的 INVALID artifact **保留**（是真实证据，非失败记录）。
- `/data` 仅剩 119 G（76% 用量），extent 有只增不减历史，后续 run 需留意水位。

## 1e. 生产 blocker B 已修复（supervise.sh 启动竞态），待终审

**结论**：`supervise.sh` 的 `sleep 3` 时序竞态已在**所有 in-repo 副本**修好，且三份字节相同。

| 路径 | 修复前 sha256 | 修复后 sha256 |
|---|---|---|
| `3090-dev/deploy/bin/supervise.sh` | `f40825a1…` | **`d3a1742e…`** |
| `3090-dev/tools/prod-service/bin/supervise.sh` | `f40825a1…` | **`d3a1742e…`** |
| `/tmp/opencode/prod-service-20260917/bin/supervise.sh`（`start.sh prod` 实际调用的 scaffold） | — | **`d3a1742e…`** |

- 修复内容：`sleep 3` + 单次读 `/proc/<pid>/environ` → **有界轮询**（`ENV_POLL_INTERVAL_S=1`、
  `ENV_POLL_TIMEOUT_S=120`），直到 PYTHONPATH 非空且位于 `$TREE/src/python` 之内、
  `CUDA_VISIBLE_DEVICES == $GPU_UUID` 才 break；超时仍 **fail-closed**；
  轮询期间进程死亡（zombie-aware `launcher_is_live`）立即报 `launcher exited immediately`。
- 两条 identity 断言**逐字保留**；无新 env knob；ready/state_write/cold-start/`wait` 语义未变。
- 证据：scaffold 首次修复 + repo 两份收尾，均经 orchestrator 独立复核
  （`bash -n` rc=0、`cmp` 三份互等、diff 与报告一致、HEAD 未变、未 stage）。
  各副本另有 CPU stub rig 证据（OLD-fails / NEW-passes / timeout-failclosed /
  happy-path 无额外延迟 / death-during-poll 立即失败）。
- **W7 已派**独立终审：`ses_f4fad88acffe61DbFpJWOnIgzv`（reviewer），审最终字节是否可安全
  用于生产启动路径，重点拷问 `set -euo pipefail` 交互与 lock 生命周期。
- **未提交 git**：两份 repo 副本仅 unstaged（HEAD 仍 `7d08fb26f8`）。

**另记（out of scope，只标记不修改）**：冻结树
`/opt/sglang/opencodex-provider-2d4e33a832/3090-dev/{deploy,tools/prod-service}/bin/supervise.sh`
仍是缺陷版 `f40825a1…`。该树只读、未激活本 scaffold；若将来启用需单独授权。

## 2. 已知须遵守的约束（本 session 复核）

- harness **已提交**字节 = `3090-dev/gates/production/`（HEAD `7d08fb26f8`），其中
  `gate_a_f1_cold_l1.py` 已含 R3 修复（删除死字段 `"mode":"unique_unrelated_prefixes"`）；
  而 `/var/log/sglang/.../phase9-gates-final-20260916/gate_a_f1_cold_l1.py` 是 **pre-R3 旧副本**，
  仍带该死字段。故 campaign 必须从 repo 副本执行。
- 其余 7 个 harness 文件 repo 副本与 deployed 副本逐字节相同。
- 不得 `pkill -f`；不得 signal 未识别进程；不得改 `/opt/sglang/**`；
  `/var/log/sglang/.../gateA/*`（07:41 INVALID 证据）不得覆盖。
- DEV provider 保持 DOWN（30001），生产 30000 保持 DOWN，直到 campaign 给出 GREEN。

_本文件由 orchestrator 于 2026-09-17 16:45Z 落盘，依据一手复验，非采信子 agent 报告。_
