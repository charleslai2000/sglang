# V122-TOOLCHAIN-COMPLETE-20260918

Status: DONE (terminal; supersedes the prior WORKING stub)

## Task
Verify the v1.2.2 freeze-toolchain edits already on disk (prior invocation left a WORKING stub
but did land edits), repair only real defects, run compile/syntax/tests, and commit the
toolchain change with EXPLICIT PATHS (never `git add -A`). Owner ruling "Option A" requires the
v1.2.2 candidate to bind `192.168.20.250` (not 0.0.0.0 / 127.0.0.1), serve model name
`qwen35-9b-local`, AUTH OFF.

TASK_ID: V122-TOOLCHAIN-VERIFY-FINALIZE-20260918

## Scope
Owned files (edit only if defective):
- `3090-dev/tools/freeze/templates/launch.sh.tmpl`
- `3090-dev/tools/freeze/pysrc/audit_launcher.py`
- `3090-dev/tools/freeze/pysrc/test_audit_launcher.py`
- `3090-dev/tools/freeze/bin/freeze.sh`

Read-only verification of `/opt/sglang/*/launcher/launch.sh` (no writes to /opt), the running
service state was not touched. No GPU, no server, no freeze/repin runs, no `3090-dev/gates/**`.

Out of scope (not touched, not committed): `.memory/**` (except this owned artifact),
`3090-dev/gates/**`, `python/**`, `test/**`, GGUF/tokenizer files.

## Result
DONE.

1. The landed `audit_launcher.py` and `launch.sh.tmpl` edits were VERIFIED CORRECT and
   fail-closed; no change was needed to either. `bin/freeze.sh` allowlist edit was VERIFIED
   CORRECT; no change needed.
2. The landed `test_audit_launcher.py` had REAL DEFECTS and was repaired (details below). The
   suite now executes 57 checks, all pass, rc=0.
3. Committed the four toolchain paths explicitly:
   `ea7b0e9b445e23852cd900ee0abe9e2a1eab17ee` — freeze-toolchain only, zero product/runtime
   source.

### Defects found and fixed in `test_audit_launcher.py` (the only file edited this invocation)
- **D1 (crash / dead branch):** the `else` branch for a missing installed v1.2.2 launcher called
  undefined `test_write(...)`/`read(...)` helpers → `NameError` traceback, rc=1. The committed
  file has no such calls; it renders the repo template exactly like `bin/launcher-repin.sh`
  does and audits that real file.
- **D2 (false FAIL against stale on-disk launcher):** the suite hard-coded
  `/opt/sglang/local-prod-v1.2-candidate/launcher/launch.sh` (host `127.0.0.1`, no
  `--served-model-name`) as its "production passes" positive case. Under the new firewall that
  launcher correctly FAILS — the landed test therefore failed its own positive case. The
  committed suite's positive case is the *intended* v1.2.2 rendered-template profile; the
  installed v1.2.2 launcher is audited additively when present.
- **D3 (no-op host/model mutations):** the landed unknown-host / unknown-model negative cases
  mutated that stale v1.2 candidate (replacing `--host 192.168.20.250` /
  `--served-model-name qwen35-9b-local`, neither present) — the `mutation_applied` check
  failed and the "audit failed" result came from the wrong cause. Committed suite mutates the
  rendered v1.2.2 profile and additionally asserts the failure REASON string.
- **D4 (coverage removed):** the landed edit dropped the prior unknown-serving-flag and
  unapproved-value-drift negative cases. Restored (both still FAIL, no blanket rule).
- **D5 (positive profile):** installed v1.2.2 tree does not exist on disk
  (`/opt/sglang/local-prod-v1.2.2-candidate` absent — expected, this commit is the toolchain
  prerequisite); the template is the correct positive source and `bin/launcher-repin.sh` will
  render it.

`audit_launcher.py` was inspected and deliberately NOT modified: the audit already implements
the required semantics (A/B/C below); changing it would be an unauthorized redesign.

## Evidence

### Per-file BEFORE/AFTER sha256 (BEFORE = prior invocation's on-disk edit; HEAD base vs worktree)

| file | HEAD (base, pre-edit) | worktree/committed (AFTER) |
|---|---|---|
| `3090-dev/tools/freeze/templates/launch.sh.tmpl` | `9bc213fe9be546b422eda61a675022a069b633b2b8dadf4d3c9859302bd0fd73` | `eb2d444b55deeb43123e17a0df4dcf5c95014f5a52e2ea68050e433c3996b56d` |
| `3090-dev/tools/freeze/pysrc/audit_launcher.py` | `fb97891fd7446bec9578c8b7b83d9e8ce66972ab18e9f5b2060dd12d099227a6` | `3144c87b22d3f0377e498d0731e4baa2bb35805ee0eb91c639341a5856ae4e32` |
| `3090-dev/tools/freeze/pysrc/test_audit_launcher.py` | `e6ee96348b70d28385064a3e924992adb184bc00dbaa7d529bc9ed2215a38979` | `1ea2b1640b2330bf93ddff6361434b5b564827167b8a6e2b98b77b625ad99f41` |
| `3090-dev/tools/freeze/bin/freeze.sh` | `09ac7d18202d2d81a734841e0d458833858d9bf8b34ea14ee44501a17ab6e543` | `7f7e8d56e8abc21a360c32f0acce91e2f2a758e25e640fc034ca159937371d59` |

Interim "prior-edited" hashes (before this invocation's repair of the test only):
- template `eb2d444b...` (unchanged by me)
- audit_launcher `3144c87b...` (unchanged by me)
- freeze.sh `7f7e8d56...` (unchanged by me)
- test file prior landed hash `f83a1b18124b9a189e491b71ddad4f0544e573a6ddd115950ce1bad27fb92137` → repaired to `1ea2b164...`

### Verified line numbers/content of each edit
- `bin/freeze.sh` line 127: `      /opt/sglang/local-prod-v1.1.2-candidate|/opt/sglang/local-prod-v1.2-candidate|/opt/sglang/local-prod-v1.2.1-candidate|/opt/sglang/local-prod-v1.2.2-candidate)`
- `templates/launch.sh.tmpl` line 146: `  --host 192.168.20.250 --port "$PORT" \`
- `templates/launch.sh.tmpl` line 147: `  --served-model-name qwen35-9b-local`
- `templates/launch.sh.tmpl` lines 150-154: `--max-total-tokens 524288`, `--context-length 131072`, `--max-running-requests 8`, `--max-mamba-cache-size 48`, `--kv-cache-dtype fp8_e4m3`
- `pysrc/audit_launcher.py` lines 73-75: `PRODUCTION_BIND_HOST_APPROVED = {"127.0.0.1": "192.168.20.250"}` (exact match-allowed→replacement map)
- `pysrc/audit_launcher.py` lines 81-83: `PRODUCTION_SERVED_MODEL_NAME_APPROVED = frozenset({"qwen35-9b-local"})`
- `pysrc/audit_launcher.py` lines 218-240 (check 4a): `--host` must appear exactly once; every value must be in the approved set
- `pysrc/audit_launcher.py` lines 244-261 (check 4b): every `--served-model-name` value must be approved; missing → failure; count > 1 → failure
- `pysrc/audit_launcher.py` line 67: `FORBIDDEN_SERVING_TOKENS = frozenset({"--api-key"})` (unchanged)
- `pysrc/audit_launcher.py` lines 176-181: `_allowed_new` = declared profile tokens ∪ replacement values ∪ `{"--served-model-name"}` ∪ approved model names — no blanket rule

### Exact diff hunks (committed)
```
diff --git a/3090-dev/tools/freeze/bin/freeze.sh b/3090-dev/tools/freeze/bin/freeze.sh
@@ -124,7 +124,7 @@ case "$DEST" in
-      /opt/sglang/local-prod-v1.1.2-candidate|/opt/sglang/local-prod-v1.2-candidate|/opt/sglang/local-prod-v1.2.1-candidate)
+      /opt/sglang/local-prod-v1.1.2-candidate|/opt/sglang/local-prod-v1.2-candidate|/opt/sglang/local-prod-v1.2.1-candidate|/opt/sglang/local-prod-v1.2.2-candidate)

diff --git a/3090-dev/tools/freeze/templates/launch.sh.tmpl b/3090-dev/tools/freeze/templates/launch.sh.tmpl
@@ -143,7 +143,8 @@ fi
-  --host 127.0.0.1 --port "$PORT"
+  --host 192.168.20.250 --port "$PORT" \
+  --served-model-name qwen35-9b-local
```
`audit_launcher.py` diff: +100/−? (`git show HEAD --stat` shows 100 changed lines) — adds the
two allowlist constants (lines 69-83), reworks check 4 allowance sets (lines 173-213), adds
check 4a bind host (lines 215-240) and check 4b served-model-name (lines 242-261); comment
renumber 4b→5b. Full hunks reproduced in `git show ea7b0e9b44 -- .../audit_launcher.py`.

`test_audit_launcher.py` diff: rewritten with the case matrix below; +/− per stat.

### (A) Audit pass/fail matrix — raw function-call output
Command: `python3 /tmp/opencode/verify_matrix_compact.py` (imports the REAL
`pysrc/audit_launcher.py` in-process; renders the repo template exactly like
`bin/launcher-repin.sh`; audits real scratch files; no /opt writes). RC=0.
```
CASE                                                           audit_ok expected verdict
A1 v1.2.2 rendered profile (host .250 + served-model-name + 128K/C8) True     True     PASS :: -
A2 unknown host 3.1.2.4                                        False    False    PASS :: ... unapproved_new=['3.1.2.4'] ... missing_replacements=['192.168.20.250']
A2 unknown host 0.0.0.0                                        False    False    PASS :: ... unapproved_new=['0.0.0.0'] ... missing_replacements=['192.168.20.250']
A2 unknown host 127.0.0.1                                      False    False    PASS :: bind host must be one of the approved v1.2 hosts ['192.168.20.250'], found '127.0.0.1'
A2 missing --host                                              False    False    PASS :: no --host flag found in launcher
A3 unknown served-model-name 'other-model'                     False    False    PASS :: unapproved_new=['other-model']
A3 unknown served-model-name 'qwen35-9b-w4a16'                 False    False    PASS :: unapproved_new=['qwen35-9b-w4a16']
A4 no --served-model-name                                      False    False    PASS :: --served-model-name missing (exactly one approved value is required)
A5 --api-key injected                                          False    False    PASS :: forbidden serving token(s) present (AUTH must be OFF): ['--api-key']
A6 unknown serving flag injected                               False    False    PASS :: unapproved_new=['--totally-unknown-serving-flag', '7']
A6 unapproved value drift (max-running-requests 8->11)         False    False    PASS :: unapproved_new=['11']
A7 v1.1 reference rejected by new firewall                     False    False    PASS :: bind host must be one of the approved v1.2 hosts ['192.168.20.250'], found '127.0.0.1'
PRODUCTION_BIND_HOST_APPROVED          = {'127.0.0.1': '192.168.20.250'}
PRODUCTION_SERVED_MODEL_NAME_APPROVED  = ['qwen35-9b-local']
FORBIDDEN_SERVING_TOKENS               = ['--api-key']
OVERALL: ALL CASES AS EXPECTED
```
Interpretation, per the mandated questions:
- **v1.2.2 profile PASSES** — A1 True (host `.250`, model `qwen35-9b-local`, 128K/C8 flags).
- **Unknown bind host FAILS, fail closed** — A2 (3.1.2.4 / 0.0.0.0 / 127.0.0.1 / missing all
  rejected; 127.0.0.1 is the v1.1 value and now rejected).
- **Unknown `--served-model-name` FAILS** — A3 (including the model-path value, which is NOT
  accepted).
- **NO `--served-model-name`: intended design stated BEFORE asserting** —
  `audit_launcher.py` check 4b (lines 242-261) REQUIRES exactly one approved value:
  `if not served_names: failures.append("--served-model-name missing (exactly one approved
  value is required)")`. Intended behavior = hard FAIL, no implicit default. Test asserts FAIL
  (A4) with that exact reason.
- **`--api-key` STILL rejected** — A5 + `FORBIDDEN_SERVING_TOKENS == {'--api-key'}` assertion.
- **No blanket rule** — A2/A3/A6/A7: allowlists are exact sets; unknown flags and value drift
  still fail; the v1.1 reference does not pass.

CLI-level confirmation (real `main()`, exit codes):
```
$ python3 3090-dev/tools/freeze/pysrc/audit_launcher.py --launcher /tmp/opencode/v122-toolchain-audit-tests/v122_rendered.sh --tree /opt/sglang/local-prod-v1.2.2-candidate --identity LOCAL-PROD-v1.2.2 --expect-stream 0{64} --ref-launcher /opt/sglang/local-prod-v1.1-candidate/launcher/launch.sh
LAUNCHER-AUDIT PASS: /tmp/opencode/v122-toolchain-audit-tests/v122_rendered.sh
CLI PASS rc=0
$ python3 .../audit_launcher.py --launcher .../unknown_bind_host_10_0_0_1.sh ...
LAUNCHER-AUDIT FAIL: .../unknown_bind_host_10_0_0_1.sh
  - bind host must be one of the approved v1.2 hosts ['192.168.20.250'], found '10.0.0.1'
CLI FAIL rc=1
```

### (C) Compile / syntax / test raw output
```
$ python3 -m py_compile 3090-dev/tools/freeze/pysrc/audit_launcher.py 3090-dev/tools/freeze/pysrc/test_audit_launcher.py
py_compile rc=0

$ bash -n 3090-dev/tools/freeze/bin/freeze.sh
bash -n rc=0

$ python3 3090-dev/tools/freeze/pysrc/test_audit_launcher.py
... (57 lines [PASS], incl. mutation_applied and *_reason_is_specific checks) ...
[INFO] installed v1.2.2 launcher not present (/opt/sglang/local-prod-v1.2.2-candidate/launcher/launch.sh); positive case used the rendered template profile
...
[PASS] v11_reference_rejected_by_new_firewall

==== test_audit_launcher: 57 passed, 0 failed ====
test_rc=0
```
Full raw capture: `/tmp/opencode/v122_test_raw_output.txt` (57 `[PASS]`, 0 `[FAIL]`).
`bash -n` on the rendered v1.2.2 launcher: rc=0.

Also observed BEFORE repair (prior landed test, evidence for D1-D3):
```
$ python3 3090-dev/tools/freeze/pysrc/test_audit_launcher.py; echo RC=$?
[FAIL] current_production_launcher_passes :: failures=["bind host must be one of the approved v1.2 hosts ['192.168.20.250'], found '127.0.0.1'", '--served-model-name missing (exactly one approved value is required)']
...
Traceback (most recent call last): ... NameError: name 'test_write' is not defined
RC=1
```

### (D) Profile otherwise intact
`git show HEAD` for the template contains ONLY the two-line hunk above. Byte-identity of all
other serving args confirmed by diff (nothing else changed). Verbatim serving argv block:
```
ARGS=(
  -m sglang.launch_server
  --model-path /data/models/qwen35-9b-w4a16
  --host 192.168.20.250 --port "$PORT" \
  --served-model-name qwen35-9b-local
  --tp-size 1
  --mem-fraction-static 0.92
  --max-total-tokens 524288
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
  --hicache-storage-backend extent
  --hicache-storage-prefetch-policy wait_complete
  --hicache-size "$L2_GB"
  --enable-ready-horizon
  --reasoning-parser qwen3
  --tool-call-parser qwen3_coder
  --enable-metrics
  --export-metrics-to-file
  --export-metrics-to-file-dir "$LOG_DIR"
  --disable-prefill-cuda-graph
)
```
- `--max-total-tokens 524288`: byte-identical (line 150, untouched by the hunk).
- `--kv-cache-dtype fp8_e4m3`: byte-identical (line 154).
- native L3 write-path env `export SGLANG_L3_NATIVE_WRITE_PATH=1` (line 83): intact.
- `--hicache-*` (lines 160-164): intact.
- `--enable-ready-horizon` (line 165): intact.
- port: `PORT="${SGLANG_PORT:-30000}"` (line 26) and `--port "$PORT"` (line 146): intact.
- no `--api-key` token anywhere in the template (grep count 0).

### (E) Commit evidence
```
$ git diff --cached --name-only   (before commit, exactly)
3090-dev/tools/freeze/bin/freeze.sh
3090-dev/tools/freeze/pysrc/audit_launcher.py
3090-dev/tools/freeze/pysrc/test_audit_launcher.py
3090-dev/tools/freeze/templates/launch.sh.tmpl
```
`git commit` produced `ea7b0e9b445e23852cd900ee0abe9e2a1eab17ee`:
```
$ git show --stat --format="%H%n%s" HEAD
ea7b0e9b445e23852cd900ee0abe9e2a1eab17ee
feat(freeze): add v1.2.2 candidate profile (LAN bind, served-model-name) with fail-closed audit
 3090-dev/tools/freeze/bin/freeze.sh                |   2 +-
 3090-dev/tools/freeze/pysrc/audit_launcher.py      | 100 +++++++--
 3090-dev/tools/freeze/pysrc/test_audit_launcher.py | 250 +++++++++++++++------
 3090-dev/tools/freeze/templates/launch.sh.tmpl     |   3 +-
 4 files changed, 275 insertions(+), 80 deletions(-)
```
`git status --porcelain` after commit, every line attributed:
```
 M .memory/phase2-hicache-design/ledger.md              # another workstream's ledger; not mine, untouched/not staged
 D 3090-dev/gates/production/gate_common.py             # pre-existing staged deletion from another workstream; UNSTAGED by me (restore --staged), file itself untouched
 M python/sglang/srt/function_call/qwen3_coder_detector.py  # product source owned by another workstream; untouched
 M python/sglang/srt/utils/hf_transformers/gguf_native.py   # product source owned by another workstream; untouched
?? .memory/phase2-hicache-design/HANDOFF-20260917-PRODUCTION-PRIORITY.md  # another workstream's memory; untouched
?? .memory/phase2-hicache-design/agent/                # another workstream's memory; untouched
?? .memory/phase2-hicache-design/agents/               # includes this artifact; untouched by commit
?? .memory/phase2-hicache-design/work/EPOCH-RESUME-20260917-R2.md           # another workstream's memory; untouched
?? .memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md  # another workstream's memory; untouched
?? .memory/phase2-hicache-design/work/PROD-TAKEOVER-AUTHORITY-AND-GATE-A-20260917.md  # another workstream's memory; untouched
?? .memory/protocol-subagent-smoke-20260917/           # another workstream's memory; untouched
?? 3090-dev/gates/gguf-sampled-smoke/                  # gates workstream; explicitly out of scope
?? test/registered/unit/utils/test_gguf_native_tokenizer_ids.py  # product test owned by another workstream; untouched
```
No `.memory/**`, no `3090-dev/gates/**`, no GGUF/tokenizer file was staged or committed.
No push, amend, rebase, reset, branch or tag was performed.

## Defects / blockers
Defects found: D1 (NameError crash), D2 (positive case contradicted firewall), D3 (no-op
mutations), D4 (dropped negative coverage). All repaired in `test_audit_launcher.py` only.
`audit_launcher.py`, `launch.sh.tmpl`, `bin/freeze.sh` required no correction.

Blockers: none. Note (not a blocker): `/opt/sglang/local-prod-v1.2.2-candidate` does not exist
yet; it is created by the subsequent `bin/freeze.sh --build-candidate` run, which the owner
authorized separately and which this invocation must not run. The installed-launcher positive
checks skip gracefully with an `[INFO]` line until then.

Unrelated failure reported, not diagnosed/fixed: the pre-existing staged deletion of
`3090-dev/gates/production/gate_common.py` (another workstream's in-flight change). I unstaged
it so the commit contains exactly four paths; the file remains deleted in the worktree.

## Remaining claims / exclusions
- This is implementation evidence, not independent tester/reviewer acceptance. The test suite
  was authored here; an independent tester run is still the acceptance gate.
- No end-to-end freeze/repin was run (forbidden); the rendered-launcher audit and suite were
  exercised in-process and via the real CLI on scratch files only.
- The v1.2.2 candidate tree must still be built, launched and smoke-tested under the separate
  production-repush workstream; the live v1.2 service (host 127.0.0.1) is unaffected by this
  change and is expected to remain on its own committed tree until repush.
- The AUTH-OFF ruling and Option A host/model values are taken as given per task authority; not
  re-litigated here.

## Terminal state: DONE
