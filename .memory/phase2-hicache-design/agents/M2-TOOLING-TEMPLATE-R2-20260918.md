# M2-TOOLING-TEMPLATE-R2-20260918

Task: M2-TOOLING-TEMPLATE-R2-20260918
Status: DONE
Terminal state: DONE

## Scope

只做 2 个文件操作（已自证）：

1. 新建 `3090-dev/tools/freeze/templates/launch.sh.m2.tmpl`（以 M1 模板 `launch.sh.tmpl` 190 行为蓝本）。
2. 改 `3090-dev/tools/freeze/bin/launcher-repin.sh`（只加「按 identity 选模板」一处，6 行）。

未改任何其它文件；未碰 `/opt/**`、`/data/**`、`python/**`、`confs`；未停/起服务、未绑端口、未用 GPU、未 commit/push。

## Result

### 交付物 1：`templates/launch.sh.m2.tmpl`

以 M1 模板整体复制为蓝本，按 1a–1h 做固定替换：

- 1a：`--model-path /data/models/qwen35-9b-w4a16` → `--model-path "$MODEL_PATH"`；`set -euo pipefail` 之后新增
  `MODEL_PATH="${MODEL_PATH:-/data/models/omnicoder-9b-gptq-int4}"`（与冻结 M2 launcher L62 取值一致）。
- 1b：`--host 192.168.20.250 --port "$PORT"` → `--host 0.0.0.0 --port "$PORT"`；删除 `--served-model-name qwen35-9b-local` 行。
- 1c：`--max-total-tokens 524288` → `--max-total-tokens 262144`。
- 1d：删除 extent/L3 四行（`--hicache-storage-backend extent`、`--hicache-storage-prefetch-policy wait_complete`、`--hicache-size "$L2_GB"`、`--enable-ready-horizon`）。
- 1e：`--mamba-ssm-dtype float32` 之后插入恰好四行：`--enable-hierarchical-cache`、`--hicache-write-policy write_back`、`--hicache-size 32`、`--hicache-host-memory-mode cache`。
- 1f：保留 `--reasoning-parser qwen3` / `--tool-call-parser qwen3_coder` / `--enable-metrics` / `--export-metrics-to-file*` / `--disable-prefill-cuda-graph`。
- 1g：保留 GATE 1/3、GATE 2/3、`SGLANG_L3_MODE=disabled` 检查、extent 环境变量 strip；把原先「一刀禁 HiCache」的 forbidden-argv 循环换成**正向钉死**：断言 `--enable-hierarchical-cache` 恰好 1 次、`--hicache-write-policy` 后紧跟 `write_back`、`--hicache-size` 后紧跟 `32`、`--hicache-host-memory-mode` 后紧跟 `cache`；仍禁止 `--hicache-storage-backend` / `--hicache-storage-prefetch-policy` / `--enable-ready-horizon` / `--hicache-ratio` / `--hicache-io-backend` / `--hicache-mem-layout`，并对四个正向 flag 各做「恰好 1 次」重复检查。strip 列表与 post-strip 泄漏检查均加入 `SGLANG_L3_BACKEND`。
- 1h：保留 `case "$PROFILE"` 的 `L2_GB`（M2 不再消费该值，仅保留变量与日志行）；未引入新 `@@token@@`，仅用 `@@TREE@@`/`@@IDENTITY@@`/`@@TREE_NAME@@`/`@@SRC_STREAM_SHA256@@`。

实现说明（消除输入歧义，非改需求）：步骤 1 指定以 M1 模板为蓝本，但 1g 引用的门禁代码（`SGLANG_L3_MODE=disabled`、extent strip、forbidden-argv 循环）只存在于冻结的 M2 launcher（`/opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh`），M1 模板不含。故按 1g 语义把冻结 M2 的门禁移植到 M1 模板形状上，并做 1d/1e 的 argv 替换。`SGLANG_L3_MODE` 由 launcher 内强制要求，dry-run 环境须显式给 `disabled`（与冻结 M2 launcher 行为一致）。

### 交付物 2：`bin/launcher-repin.sh`

在参数解析完成后、`[ -f "$TEMPLATE" ]` 存在性检查之前，恰好新增：

```bash
# M2 has its own launcher shape (HiCache host tier, no L3 backend).
case "$IDENTITY" in
  *-M2) TEMPLATE="$TOOL_DIR/templates/launch.sh.m2.tmpl" ;;
esac
```

其余逻辑一行未改（见下方 diff，仅 +4 行净增）。

## Evidence

### AC1 — 语法（rc 0）

```bash
bash -n templates/launch.sh.m2.tmpl   # rc=0
bash -n bin/launcher-repin.sh         # rc=0
```
输出：`m2_tmpl_bash_n_rc=0`、`repin_bash_n_rc=0`。
token 扫描只出现允许的四种 `@@` token。

### AC2 — 渲染 + 审计 exit 0 / PASS

scratch：`/tmp/opencode/m2-tooling-template-r2-20260918/`；fake tree `fake/local-prod-v1.2.1-candidate-M2`（含 `src/`，stream 值以实际计算值替换）。

命令：

```bash
python3 3090-dev/tools/freeze/pysrc/audit_launcher.py \
  --launcher /tmp/opencode/m2-tooling-template-r2-20260918/rendered.sh \
  --tree /tmp/opencode/m2-tooling-template-r2-20260918/fake/local-prod-v1.2.1-candidate-M2 \
  --identity LOCAL-PROD-v1.2.1-M2 --profile LOCAL-PROD-v1.2.1-M2 \
  --ref-launcher /opt/sglang/local-prod-v1.1-candidate/launcher/launch.sh
```
输出：`LAUNCHER-AUDIT PASS: /tmp/opencode/m2-tooling-template-r2-20260918/rendered.sh`，`AUDIT_RC=0`。

`rendered.sh` 的 ARGS 段原文：

```
ARGS=(
  -m sglang.launch_server
  --model-path "$MODEL_PATH"
  --host 0.0.0.0 --port "$PORT" \
  --tp-size 1
  --mem-fraction-static 0.92
  --max-total-tokens 262144
  --context-length 131072
  --max-running-requests 8
  --max-mamba-cache-size 48
  --kv-cache-dtype fp8_e4m3
  --attention-backend flashinfer
  --linear-attn-prefill-backend triton
  --linear-attn-decode-backend triton
  --mamba-radix-cache-strategy extra_buffer
  --mamba-ssm-dtype float32
  --enable-hierarchical-cache
  --hicache-write-policy write_back
  --hicache-size 32
  --hicache-host-memory-mode cache
  --reasoning-parser qwen3
  --tool-call-parser qwen3_coder
  --enable-metrics
  --export-metrics-to-file
  --export-metrics-to-file-dir "$LOG_DIR"
  --disable-prefill-cuda-graph
)
```
（`$MODEL_PATH` 在渲染出的 launcher 顶部由 `MODEL_PATH="${MODEL_PATH:-/data/models/omnicoder-9b-gptq-int4}"` 定义。）

### AC3 — 反向自证：`--hicache-size 64` 必须 FAIL

把 `rendered.sh` 中 `--hicache-size 32` 改为 `--hicache-size 64`（`rendered_bad.sh`），同一审计：

```
LAUNCHER-AUDIT FAIL: /tmp/opencode/m2-tooling-template-r2-20260918/rendered_bad.sh
  - required serving token(s) missing for profile (LOCAL-PROD-v1.2.1-M2): ['32']
  - serving flags differ from reference beyond the exact profile (LOCAL-PROD-v1.2.1-M2) delta: ... unapproved_new=['64'] ... missing_required_tokens=['32']
```
`MUTATED_AUDIT_RC=1`。

### AC4 — 回归测试

```bash
python3 3090-dev/tools/freeze/pysrc/test_audit_launcher.py
```
输出结尾：`==== test_audit_launcher: 81 passed, 0 failed ====`，`TEST_RC=0`（无新增失败）。

### AC5 — git status 只多出这两个文件

任务前基线 `/tmp/opencode/M2-TOOLING-TEMPLATE-baseline-status.txt` 与任务后 diff：

```
3a4
>  M 3090-dev/tools/freeze/bin/launcher-repin.sh
29a31
> ?? 3090-dev/tools/freeze/templates/launch.sh.m2.tmpl
```

工作树其余 ` M/??` 条目均为调用前已存在（由别的任务拥有），本次未触碰。任务范围内：

```
 M 3090-dev/tools/freeze/bin/launcher-repin.sh
?? 3090-dev/tools/freeze/templates/launch.sh.m2.tmpl
```

`launcher-repin.sh` diff（仅此一处）：

```diff
@@ -64,6 +64,10 @@ done
 [ -n "$MODE" ] || die "one of --write, --verify-only or --verify-installed is required"
 case "$TREE" in /*) ;; *) die "--tree must be absolute" ;; esac
 [ -d "$TREE/src" ] || die "no such tree src: $TREE/src"
+# M2 has its own launcher shape (HiCache host tier, no L3 backend).
+case "$IDENTITY" in
+  *-M2) TEMPLATE="$TOOL_DIR/templates/launch.sh.m2.tmpl" ;;
+esac
 [ -f "$TEMPLATE" ] || die "template missing: $TEMPLATE"
```

### AC6 — M1 模板字节未变

```bash
git diff --stat -- 3090-dev/tools/freeze/templates/launch.sh.tmpl   # 空输出
sha256sum 3090-dev/tools/freeze/templates/launch.sh.tmpl
# eb2d444b55deeb43123e17a0df4dcf5c95014f5a52e2ea68050e433c3996b56d
```
`git diff --stat -- 3090-dev/tools/freeze/templates/` 亦为空（新增文件为 untracked，不计入 diff）。

### 额外证据（身份选模板 + 门禁端到端）

- M2 identity 选中 m2 模板并 repin PASS（scratch fake tree，`--write --no-dry-run`）：
  `LAUNCHER-REPIN PASS: ... launcher_sha256=f860f995...`；渲染结果含 `MODEL_PATH=...omnicoder-9b-gptq-int4`、`--max-total-tokens 262144`、`--hicache-size 32`、`--hicache-host-memory-mode cache`、`--host 0.0.0.0`，无 extent/`--enable-ready-horizon`/`--served-model-name`。
- M1 identity（不含 `-M2`）仍选默认模板：渲染结果 `--host 192.168.20.250`、`--served-model-name qwen35-9b-local`、`--max-total-tokens 524288`、`--hicache-size "$L2_GB"`，repin PASS。
- 端到端 dry-run（仅 scratch stub gates，`preflight_identity.py` exit 0、`l3_namespace.py` exit 6，`SGLANG_L3_MODE=disabled`）：
  `DRYRUN_RC=0`，`L3 GATE: storage backend DISABLED (... HiCache host tier pinned)`，打印的 argv 与 AC2 的 ARGS 一致。

## Defects or blockers

无阻塞。已交付两项机械改动，全部验收命令通过。

## Remaining claims or exclusions

- 未执行/未覆盖：真实 `/opt` 树的 freeze/repin；GPU；服务停起；端口绑定；推理；commit/push；未改 `/opt/**`、`/data/**`、`python/**`、`conf/service.env`。
- 未建立的主张（exclusion）：本任务不证明重冻后的 M2 真实树端到端通过；也不证明 `freeze.sh` 全链路（需 D4/D5 窗口与真实 gate 工具）。
- 实现推断（已在 Result 说明）：步骤 1.g 的门禁语义取自冻结 M2 launcher 并移植到 M1 模板形状；`--hicache-host-memory-mode cache` 仍为审计 profile 中的可选 token（本模板选择显式钉死）。
- 门禁 `/opt` 契约保持：M2 模板仍要求 `SGLANG_L3_MODE=disabled` 且 `l3_namespace.py --validate` 以 exit 6 拒绝；dry-run/启动前须显式设置该变量，与冻结 M2 launcher 一致。

## Next

- 由 orchestrator 在 GPU 窗口按 `M2-HICACHE-RELEASE-DESIGN-R2-20260918.md` D4/D5/D7 步骤做真实 freeze/repin（本任务仅提供 CPU-only 工具前置）。
- 窗口内验证 `launcher-repin.sh --identity *-M2` 选中 m2 模板并在真实树 dry-run 通过。

## Terminal state

DONE
