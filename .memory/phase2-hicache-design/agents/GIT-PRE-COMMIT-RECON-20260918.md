# GIT-PRE-COMMIT-RECON-20260918

- **Task**: GIT-PRE-COMMIT-RECON-20260918
- **Scope**: `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt`（以 `git -C <repo> ...` 运行）只读仓库状态与变更清单采集，为随后的 commit+push 提供事实。未执行任何写/`git add`/`commit`/`push`/`reset`/`checkout`/`stash`。未触碰 `/opt/sglang/**`、`/tmp/opencode/**`。
- **Result**: 采集成功。当前分支 `3090-24g-opt`，HEAD `ea7b0e9b445e23852cd900ee0abe9e2a1eab17ee`，上游 `origin/3090-24g-opt`。工作树 20 个已跟踪路径有改动（19 M + 1 D）、19 个未跟踪条目；**暂存区为空**（无 staged 内容）。`diff --stat` 合计 20 files changed, 9460 insertions(+), 1972 deletions(-)。关键路径 `qwen3_coder_detector.py` 为 tracked 且工作树 sha256 与期望值完全一致（`848e0690...a9d151`），且 `git status` 显示其被修改（未暂存）。全仓未发现任何 `*.gguf` 权重/二进制文件。
- **Terminal state**: DONE

## Evidence

### 0. 指令文件核查
- 仓库根不存在 `AGENTS.md`：`ls: cannot access '/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/AGENTS.md': No such file or directory`
- 仅存在 `docs/AGENTS.md`（find 结果唯一）。适用指令为全局 `~/.config/opencode/AGENTS.md` 与本 dispatch 自身。

### 1. 当前分支
```
$ git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt rev-parse --abbrev-ref HEAD
3090-24g-opt
```

### 2. HEAD 与近 5 条提交
```
$ git -C <repo> rev-parse HEAD
ea7b0e9b445e23852cd900ee0abe9e2a1eab17ee

$ git -C <repo> log --oneline -5
ea7b0e9b44 feat(freeze): add v1.2.2 candidate profile (LAN bind, served-model-name) with fail-closed audit
3f2a417e95 test(gates): close Gate-A/F1 drop-predicate and evidence conditions (harness-only, no runtime change)
910e5a01c0 docs(memory): session-close handoff for the M1 production session
a6beb3004c docs(memory): reconcile production commit identity (b2bbd6ea28 / 8c8cdcea03)
9c4685e1bb chore(freeze): record the v1.2.1 candidate pins and approved delta
```

### 3. `git status --porcelain`（完整，原样）
```
 M .memory/phase2-hicache-design/ledger.md
 D 3090-dev/gates/production/gate_common.py
 M 3090-dev/tools/freeze/bin/freeze.sh
 M 3090-dev/tools/freeze/bin/launcher-repin.sh
 M 3090-dev/tools/freeze/pins/local-prod-v1.2-candidate-allowlist.txt
 M 3090-dev/tools/freeze/pysrc/audit_launcher.py
 M 3090-dev/tools/freeze/pysrc/test_audit_launcher.py
 M python/sglang/srt/entrypoints/openai/protocol.py
 M python/sglang/srt/entrypoints/openai/serving_chat.py
 M python/sglang/srt/entrypoints/openai/usage_processor.py
 M python/sglang/srt/environ.py
 M python/sglang/srt/function_call/qwen3_coder_detector.py
 M python/sglang/srt/mem_cache/hybrid_cache/hybrid_cache_controller.py
 M python/sglang/srt/mem_cache/unified_radix_cache.py
 M python/sglang/srt/sampling/custom_logit_processor.py
 M python/sglang/srt/server_args.py
 M python/sglang/srt/utils/hf_transformers/gguf_native.py
 M test/registered/unit/function_call/test_function_call_parser.py
 M test/registered/unit/managers/test_hicache_host_allocability.py
 M test/registered/unit/managers/test_hybrid_group_wiring.py
?? .memory/phase2-hicache-design/HANDOFF-20260917-PRODUCTION-PRIORITY.md
?? .memory/phase2-hicache-design/HANDOFF-20260918-FINAL.md
?? .memory/phase2-hicache-design/HANDOFF-20260918-SESSION-2.md
?? .memory/phase2-hicache-design/agent/
?? .memory/phase2-hicache-design/agents/
?? .memory/phase2-hicache-design/work/EPOCH-RESUME-20260917-R2.md
?? .memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md
?? .memory/phase2-hicache-design/work/M2-RELEASE-STAGE2-20260918/
?? .memory/phase2-hicache-design/work/M2-RELEASE-WINDOW-A-20260918/
?? .memory/phase2-hicache-design/work/M2-RELEASE-WINDOW-A2-20260918/
?? .memory/phase2-hicache-design/work/PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md
?? .memory/protocol-subagent-smoke-20260917/
?? 3090-dev/gates/gguf-sampled-smoke/
?? 3090-dev/tools/freeze/pins/local-prod-v1.2.1-candidate-M2-pins.json
?? 3090-dev/tools/freeze/selftest/
?? 3090-dev/tools/freeze/templates/launch.sh.m2.tmpl
?? python/sglang/srt/parser/qwen35_reasoning_policy.py
?? test/registered/unit/parser/test_qwen35_reasoning_policy.py
?? test/registered/unit/utils/test_gguf_native_tokenizer_ids.py
```

### 4. diff stat（未暂存 / 已暂存）
```
$ git -C <repo> diff --stat
 .memory/phase2-hicache-design/ledger.md            | 7742 ++++++++++++++++++++
 3090-dev/gates/production/gate_common.py           | 1679 -----
 3090-dev/tools/freeze/bin/freeze.sh                |    8 +-
 3090-dev/tools/freeze/bin/launcher-repin.sh        |   27 +-
 .../pins/local-prod-v1.2-candidate-allowlist.txt   |   14 +
 3090-dev/tools/freeze/pysrc/audit_launcher.py      |  310 +-
 3090-dev/tools/freeze/pysrc/test_audit_launcher.py |  149 +
 python/sglang/srt/entrypoints/openai/protocol.py   |   39 +-
 .../sglang/srt/entrypoints/openai/serving_chat.py  |  182 +
 .../srt/entrypoints/openai/usage_processor.py      |   34 +-
 python/sglang/srt/environ.py                       |    6 +
 .../srt/function_call/qwen3_coder_detector.py      |  416 +-
 .../hybrid_cache/hybrid_cache_controller.py        |   71 +-
 python/sglang/srt/mem_cache/unified_radix_cache.py |  177 +-
 .../sglang/srt/sampling/custom_logit_processor.py  |   14 +
 python/sglang/srt/server_args.py                   |    2 +-
 .../srt/utils/hf_transformers/gguf_native.py       |   26 +-
 .../function_call/test_function_call_parser.py     |  187 +
 .../managers/test_hicache_host_allocability.py     |  186 +-
 .../unit/managers/test_hybrid_group_wiring.py      |  163 +
 20 files changed, 9460 insertions(+), 1972 deletions(-)

$ git -C <repo> diff --cached --stat
（空输出）
```

### 5. 变更条目计数
```
$ git -C <repo> status --porcelain --ignored=no | wc -l
39
```
（39 = 20 已跟踪变更 + 19 未跟踪条目）

### 6. 远程与上游
```
$ git -C <repo> remote -v
origin	git@github.com:charleslai2000/sglang.git (fetch)
origin	git@github.com:charleslai2000/sglang.git (push)
upstream	git@github.com:sgl-project/sglang.git (fetch)
upstream	git@github.com:sgl-project/sglang.git (push)

$ git -C <repo> rev-parse --abbrev-ref --symbolic-full-name '@{u}'
origin/3090-24g-opt
```
（无报错）

### 7. 关键路径逐项报告
判定说明：`status-line` 取 ` M` 为工作树已改未暂存；空 = 与 HEAD 一致无改动。

| 路径 | tracked at HEAD | worktree sha256 | size | status-line | diff vs HEAD |
|---|---|---|---|---|---|
| `python/sglang/srt/function_call/qwen3_coder_detector.py` | yes | `848e0690cb80719e70c7ceedb7c1eb253c879d39a1b7be1cb85645f861a9d151` | 20333 | ` M` | 1 file changed, 212 insertions(+), 204 deletions(-) |
| `python/sglang/srt/utils/hf_transformers/gguf_native.py` | yes | `0f3c8fb9f2e6c3eb2bdcf0a3640f26880a88179bb0b4a3f41674fbfaf8202ade` | 11296 | ` M` | 1 file changed, 22 insertions(+), 4 deletions(-) |
| `3090-dev/tools/freeze/bin/freeze.sh` | yes | `294984b7d658051dcc2f0bc2d362fdf2cb86e3a5aa110fed2a0fd7cb99c39aa7` | 28362 | ` M` | 1 file changed, 4 insertions(+), 4 deletions(-) |
| `3090-dev/tools/freeze/bin/launcher-repin.sh` | yes | `8ee5de1fd8b123fe0cffe59dd5882f7e5dffdd1314843c2e60cb9d9309551338` | 9043 | ` M` | 1 file changed, 23 insertions(+), 4 deletions(-) |
| `3090-dev/tools/freeze/templates/launch.sh.m2.tmpl` | **no** | `9ac8b5acf143ad10030871c519e3c09c154a7cef96ba2d4169237928db34f693` | 12236 | `??` | 无（新增/未跟踪） |
| `3090-dev/tools/freeze/templates/launch.sh.tmpl` | yes | `eb2d444b55deeb43123e17a0df4dcf5c95014f5a52e2ea68050e433c3996b56d` | 8097 | （空） | 无改动 |
| `3090-dev/tools/freeze/pysrc/audit_launcher.py` | yes | `990db83049d952a2dce2b88737f32f8b0cc35414982235be5b5187f965d54f5c` | 25887 | ` M` | 1 file changed, 277 insertions(+), 33 deletions(-) |
| `3090-dev/tools/freeze/pysrc/test_audit_launcher.py` | yes | `be876d7aea8303581abfad9aeb71feb218830d67d123ed67acd5f69b22d2098c` | 18451 | ` M` | 1 file changed, 149 insertions(+) |
| `3090-dev/tools/freeze/pins/local-prod-v1.2-candidate-allowlist.txt` | yes | `915f89243495fcbfa86a100e39225e0e18ba4f98cbeebf21a29a1678015fe497` | 9128 | ` M` | 1 file changed, 14 insertions(+) |

**`qwen3_coder_detector.py` 专项**：
- 期望 sha256 `848e0690cb80719e70c7ceedb7c1eb253c879d39a1b7be1cb85645f861a9d151`，实测**完全一致**。
- `git status` 显示其为 ` M`（工作树已改、未暂存）。
- 该路径在 HEAD 中存在（tracked）；HEAD 版本内容 sha256 = `92eeaeaf02ac1c1e966a8b9bbd4393141353ca9177265044fe12e250c0e38089`，与工作树不同。
- `launch.sh.m2.tmpl` 确认为**新增（untracked `??`），不在 HEAD**。

### 8. 危险项排查（`*.gguf` 权重/二进制）
- `git status --porcelain` 中包含 "gguf" 的全部行：
```
 M python/sglang/srt/utils/hf_transformers/gguf_native.py
?? .memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md
?? 3090-dev/gates/gguf-sampled-smoke/
?? test/registered/unit/utils/test_gguf_native_tokenizer_ids.py
```
- 全仓（含 `.git`）`find -iname '*.gguf'` 结果：(空) —— **不存在任何 `.gguf` 文件**。
- `3090-dev/gates/gguf-sampled-smoke/`（untracked 目录）内文件与大小：
```
6675	.../3090-dev/gates/gguf-sampled-smoke/README.md
84167	.../3090-dev/gates/gguf-sampled-smoke/__pycache__/server_harness_sampled.cpython-312.pyc
9102	.../3090-dev/gates/gguf-sampled-smoke/cpu_smoke.out.json
7092	.../3090-dev/gates/gguf-sampled-smoke/llamacpp-discriminator.md
4024	.../3090-dev/gates/gguf-sampled-smoke/run_sampled_smoke.sh
73674	.../3090-dev/gates/gguf-sampled-smoke/server_harness_sampled.py
```
- 上述含 "gguf" 的路径均为源码 / 文档 / 测试 / 小体积 JSON 与一个 `.pyc`（最大 84 KB），无 `.gguf` 权重或大二进制。
- 索引中匹配 gguf 的已跟踪文件均为源码（`gguf_native.py`、`.../aot/.../gguf/*.cu`、tests 等），非权重文件。

### 9. 已暂存内容
- `git diff --cached --name-status` 与 `git diff --cached --stat` 均为**空** ⇒ 无 staged 内容。

### 10. diff 总文件数与总插入/删除
```
$ git -C <repo> diff --numstat | awk '{f++; i+=$1; d+=$2} END {print "files="f, "insertions="i, "deletions="d}'
files=20 insertions=9460 deletions=1972
```
`diff --stat` 尾行一致：`20 files changed, 9460 insertions(+), 1972 deletions(-)`。
主要量来自 `.memory/phase2-hicache-design/ledger.md` (+7742) 与删除的 `3090-dev/gates/production/gate_common.py` (-1679)。

### 附：未跟踪条目的体积（供 commit 范围评估）
- `.memory/phase2-hicache-design/agents/`（约 100+ 个 .md，单文件最大 51399 B）与 `.memory/phase2-hicache-design/agent/`（1 个 .md）。
- `M2-RELEASE-STAGE2-20260918/`、`M2-RELEASE-WINDOW-A-20260918/`、`M2-RELEASE-WINDOW-A2-20260918/` 内含数个约 2 MB 的 `.txt`（如 `stage2-source.txt` 2042200 B、`_baseline_full.txt` 2024721 B）及小 JSON。
- `.memory/protocol-subagent-smoke-20260917/` 为 .md 报告集。
- `3090-dev/tools/freeze/selftest/` 为小体积日志/JSON。
- 单文件：`test_qwen35_reasoning_policy.py` 24241 B；`HANDOFF-20260917-PRODUCTION-PRIORITY.md` 22642 B；`GGUF-ARTIFACT-PROVENANCE-20260917.md` 16304 B；`qwen35_reasoning_policy.py` 8699 B；`local-prod-v1.2.1-candidate-M2-pins.json` 1608 B 等。

## Defects or blockers
- 无阻塞。所有命令均只读执行成功（`@{u}` 解析无报错）。
- 事实性缺口：本报告未读取 `docs/AGENTS.md` 内容（仅确认其存在）。

## Remaining claims or exclusions
- 不评估变更内容正确性、不判断 commit 安全性、不给 commit 范围建议（按 dispatch 要求）。
- 未递归遍历 `.git` 内部对象计数、未计算 worktree 全量文件清单（仅按 status 与关键路径）。
- 未触碰 `/opt/sglang/**`、`/tmp/opencode/**`；未运行任何写操作。
- 根据本 dispatch 授权仅采集仓库事实；对 staged/untracked 的处置权归属 orchestrator 的后续 dispatch。
