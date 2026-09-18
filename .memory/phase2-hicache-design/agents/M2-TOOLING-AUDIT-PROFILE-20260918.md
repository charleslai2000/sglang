# M2-TOOLING-AUDIT-PROFILE-20260918

Status: DONE
Terminal state: DONE

## Task
Implement design D3 of `M2-HICACHE-RELEASE-DESIGN-R2-20260918.md`: introduce model-aware
`LAUNCHER_PROFILES` keyed by identity plus a `--profile` selector in
`3090-dev/tools/freeze/pysrc/audit_launcher.py`; add negative/positive profile tests in
`3090-dev/tools/freeze/pysrc/test_audit_launcher.py`; demonstrate real behavior against the
installed M1/M2 launchers (read-only). CPU-only; no GPU; no signalling; no port binds;
`freeze.sh`/`launcher-repin.sh` not run.

## Scope
- Write scope (ONLY these two files, both edited):
  - `3090-dev/tools/freeze/pysrc/audit_launcher.py`
  - `3090-dev/tools/freeze/pysrc/test_audit_launcher.py`
- Not edited / untouched: `templates/launch.sh.tmpl`, `bin/launcher-repin.sh`, `bin/freeze.sh`,
  the pins allowlist, `/opt/**`, `/data/**`, `/tmp/opencode/**` except scratch fixtures,
  `python/sglang/srt/**`.
- Read-only inputs: design D1/D2/D3, installed M1/M2 launchers, v1.1 reference launcher, template.
- Verification: `python3 -m py_compile` on both files; full `test_audit_launcher.py` run;
  `audit_launcher.py` runs against installed launchers; `git status`/`git diff --stat`.

## Result

### Profile table implemented in `LAUNCHER_PROFILES`

| identity | approved hosts | served-model-name rule | replacements | approved-new | allowed-dropped |
|---|---|---|---|---|---|
| `LOCAL-PROD-v1.2.1` (M1) | `0.0.0.0`, `192.168.20.250` | optional; if present must be `qwen35-9b-local` | `65536`→{`524288`}; `127.0.0.1`→{`0.0.0.0`,`192.168.20.250`} | `--context-length 131072`, `--max-running-requests 8`, `--max-mamba-cache-size 48`, `524288`, `0.0.0.0`, `192.168.20.250`, `--served-model-name`, `qwen35-9b-local` | none (extent L3 args must remain present) |
| `LOCAL-PROD-v1.2.1-M2` | `0.0.0.0`, `192.168.20.250` | optional; if present must be `qwen35-9b-local` | `65536`→{`262144`}; `127.0.0.1`→{`0.0.0.0`,`192.168.20.250`}; `/data/models/qwen35-9b-w4a16`→{`"$MODEL_PATH"`} | `--context-length 131072`, `--max-running-requests 8`, `--max-mamba-cache-size 48`, `262144`, `0.0.0.0`, `192.168.20.250`, `"$MODEL_PATH"`, HiCache trio (`--enable-hierarchical-cache`, `--hicache-write-policy write_back`, `--hicache-size 32`), optional `--hicache-host-memory-mode cache`, `--served-model-name`, `qwen35-9b-local` | `--hicache-storage-backend`, `extent`, `--hicache-storage-prefetch-policy`, `wait_complete`, `"$L2_GB"`, `--enable-ready-horizon` |
| `<<default>>` (legacy, no profile / unknown identity) | `192.168.20.250` | REQUIRED exactly one `qwen35-9b-local` | `65536`→{`524288`}; `127.0.0.1`→{`192.168.20.250`} | legacy Option-A set | none |

Both M1 and M2 profiles additionally have `forbidden_tokens = {"--api-key"}`; M2 adds
`--hicache-storage-backend`, `--hicache-storage-prefetch-policy`,
`--hicache-storage-backend-extra-config`, `--enable-ready-horizon`, `--hicache-ratio`,
`--hicache-io-backend`, `--hicache-mem-layout`. `--api-key` refusal is unchanged.

Fail-closed behavior (all verified):
- unknown profile name → hard failure (`UnknownProfileError`, exit 1);
- extra token not in `approved_new_tokens` → `unapproved_new` failure;
- reference token dropped without being in `allowed_dropped_tokens` (or replaced) →
  `unapproved_dropped` failure;
- required token missing → `missing_required_tokens` failure (enforced even without
  `--ref-launcher`);
- value mismatch → `missing_replacements` + required-token failure (e.g. `--hicache-size 64`);
- forbidden token injected → `profile_forbidden_tokens_present` / AUTH refusal.
The `--profile` selection is: explicit `--profile` (must exist), else auto-select by
`--identity`, else the legacy default. Comparison is exact set membership against the selected
profile — not a blanket allowlist. Existing checks 1/2/3/5/6 and `--api-key` refusal are
unchanged; the `audit()` signature gained an optional `profile=None` parameter, so all existing
callers keep the legacy default behavior.

### Exact test results
- Interpreter: `/usr/bin/python3` (Python 3.12.3), matching the file shebang `#!/usr/bin/env python3`.
- `python3 -m py_compile 3090-dev/tools/freeze/pysrc/audit_launcher.py` → EXIT=0
- `python3 -m py_compile 3090-dev/tools/freeze/pysrc/test_audit_launcher.py` → EXIT=0
- `python3 3090-dev/tools/freeze/pysrc/test_audit_launcher.py` → EXIT=0,
  **`==== test_audit_launcher: 81 passed, 0 failed ====`**.
  The three required new cases all PASS:
  - (a) `[PASS] m2_old_launcher_FAILS`, `[PASS] m2_old_reason_missing_required`,
    `[PASS] m2_old_reason_unapproved_dropped`, `[PASS] m2_old_has_no_hicache_serving_flag`;
  - (b) `[PASS] m2_injected_storage_backend_FAILS`,
    `[PASS] m2_injected_storage_backend_reason_is_specific`;
  - (c) `[PASS] m2_new_launcher_PASSES`, `[PASS] m2_auto_profile_passes`,
    `[PASS] m2_auto_profile_selected`.
  Additional new M2 checks PASS: `m2_bad_hicache_size_FAILS`, `unknown_profile_FAILS`,
  `unknown_profile_reason_is_specific`, `m2_profile_hosts_include_0000`,
  `m2_profile_served_model_optional`, `m2_audit_reports_no_served_model_name`.
  New M1 checks PASS: `installed_m1_launcher_passes_profile`,
  `installed_m1_bind_host_is_0000`, `installed_m1_has_no_served_model_name`,
  `m1_profile_hosts_include_0000`, `m1_profile_served_model_optional`.
  All 57 pre-existing checks still PASS (no regression), including
  `v122_rendered_profile_passes` and `unknown_bind_host_0_0_0_0_FAILS` (the legacy default
  still rejects `0.0.0.0`).

### Installed-launcher audit results (`--ref-launcher /opt/sglang/local-prod-v1.1-candidate/launcher/launch.sh`)
All three `/opt` launchers were readable (mode `-r-xr-xr-x`); no permission errors.

1. M1 installed + explicit profile `LOCAL-PROD-v1.2.1`:
   `--launcher /opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh --tree
   /opt/sglang/local-prod-v1.2.1-candidate --identity LOCAL-PROD-v1.2.1
   --profile LOCAL-PROD-v1.2.1 --ref-launcher <ref> --json` → **EXIT=0**:
   ```json
   {"exit_code": 0, "ok": true, "failures": [],
    "details": {"profile": "LOCAL-PROD-v1.2.1", "bind_host": "0.0.0.0",
      "bind_host_approved": true, "served_model_names": [],
      "served_model_name_required": false, "missing_required_tokens": [],
      "profile_forbidden_tokens_present": [],
      "serving_delta_allowance": {"unapproved_new": [], "unapproved_dropped": [],
        "missing_replacements": [], "missing_required_tokens": []}}}
   ```
   The M1 launcher passes while preserving bind `0.0.0.0`, no `--served-model-name`, and the
   extent L3 args (`--hicache-storage-backend extent`, `--hicache-storage-prefetch-policy
   wait_complete`, `--hicache-size "$L2_GB"`, `--enable-ready-horizon`).

2. M2 installed (PRE-CHANGE, HiCache DISABLED) + explicit profile `LOCAL-PROD-v1.2.1-M2`:
   `--launcher /opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh --tree
   /opt/sglang/local-prod-v1.2.1-candidate-M2 --identity LOCAL-PROD-v1.2.1-M2
   --profile LOCAL-PROD-v1.2.1-M2 --ref-launcher <ref> --json` → **EXIT=1** (expected,
   fail-closed, because D1 HiCache-trio injection is a separate task):
   ```json
   {"exit_code": 1, "ok": false,
    "failures": [
      "required serving token(s) missing for profile (LOCAL-PROD-v1.2.1-M2): ['--enable-hierarchical-cache', '--hicache-size', '--hicache-write-policy', '32', 'write_back']",
      "serving flags differ from reference beyond the exact profile (LOCAL-PROD-v1.2.1-M2) delta: only-in-new=['\"$MODEL_PATH\"', '0.0.0.0', '262144', '--context-length', '131072', '--max-running-requests', '8', '--max-mamba-cache-size', '48'] only-in-reference=['/data/models/qwen35-9b-w4a16', '127.0.0.1', '65536', '--enable-hierarchical-cache', '--hicache-write-policy', 'write_back', '--hicache-storage-backend', 'extent', '--hicache-storage-prefetch-policy', 'wait_complete', '--hicache-size', '\"$L2_GB\"', '--enable-ready-horizon'] unapproved_new=[] unapproved_dropped=['--enable-hierarchical-cache', '--hicache-write-policy', 'write_back', '--hicache-size'] missing_replacements=[] missing_required_tokens=['--enable-hierarchical-cache', '--hicache-size', '--hicache-write-policy', '32', 'write_back']"],
    "details": {"profile": "LOCAL-PROD-v1.2.1-M2", "bind_host": "0.0.0.0",
      "bind_host_approved": true, "served_model_names": [],
      "served_model_name_required": false}}
   ```
   This is the required negative case (a): the old M2 launcher fails the new M2 profile.

3. NEW M2 launcher (D1 HiCache trio injected into the installed copy, rendered to
   `/tmp/opencode/m2-tooling-audit-profile-20260918/m2_new_rendered.sh`) + profile
   `LOCAL-PROD-v1.2.1-M2` → **EXIT=0**:
   ```json
   {"exit_code": 0, "ok": true, "failures": [],
    "details": {"profile": "LOCAL-PROD-v1.2.1-M2", "bind_host": "0.0.0.0",
      "bind_host_approved": true, "served_model_names": [],
      "served_model_name_required": false, "missing_required_tokens": [],
      "profile_forbidden_tokens_present": [],
      "serving_delta_allowance": {"unapproved_new": [], "unapproved_dropped": [],
        "missing_replacements": [], "missing_required_tokens": []}}}
   ```
   Auto-select (no `--profile`, identity drives it) also EXIT=0 with
   `details.profile == "LOCAL-PROD-v1.2.1-M2"`.

Additional real-behavior probes (CPU-only, read-only, scratch under `/tmp/opencode`):
- NEW M2 without the optional `--hicache-host-memory-mode cache` → EXIT=0 (optional token).
- NEW M2 keeping `65536` (no `262144`) → EXIT=1, `missing_replacements=['65536']`.
- NEW M2 with hardcoded model path (no `"$MODEL_PATH"`) → EXIT=1,
  `missing_replacements=['/data/models/qwen35-9b-w4a16']`.
- NEW M2 with injected `--hicache-storage-backend extent` → EXIT=1,
  `profile_forbidden_tokens_present=['--hicache-storage-backend']`.
- NEW M2 with `--hicache-size 64` → EXIT=1.
- NEW M2 with injected `--api-key` → EXIT=1, `forbidden_serving_tokens_present=['--api-key']`.
- `--profile NOPE` → EXIT=1, `unknown launcher profile 'NOPE'; known profiles:
  ['LOCAL-PROD-v1.2.1', 'LOCAL-PROD-v1.2.1-M2']`.
- M1 variant with approved host `192.168.20.250` + `--served-model-name qwen35-9b-local`
  → EXIT=0; same variant with `bad-model` → EXIT=1
  (`--served-model-name must be one of ['qwen35-9b-local'], found 'bad-model'`).

### Repository state
- `git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt status --porcelain` includes
  exactly the two write-scope files as ` M`:
  ` M 3090-dev/tools/freeze/pysrc/audit_launcher.py` and
  ` M 3090-dev/tools/freeze/pysrc/test_audit_launcher.py`.
- `git diff --stat -- 3090-dev/tools/freeze/pysrc/`:
  ```
   3090-dev/tools/freeze/pysrc/audit_launcher.py      | 310 ++++++++++++++++++---
   3090-dev/tools/freeze/pysrc/test_audit_launcher.py | 149 ++++++++++
   2 files changed, 426 insertions(+), 33 deletions(-)
  ```
  Only the two authorized files appear in that path. `git status` also shows
  `M 3090-dev/tools/freeze/bin/freeze.sh` and
  `M 3090-dev/tools/freeze/pins/local-prod-v1.2-candidate-allowlist.txt` — these are NOT mine
  (see Remaining claims/exclusions); they were already modified before this invocation
  (mtimes 20:02, session edits 20:12) and the D4/D5/D7 task owns them. `templates/` and
  `bin/launcher-repin.sh` are unchanged by this session.
- Full report JSON artifacts saved read-only under
  `/tmp/opencode/m2-tooling-audit-profile-20260918/` (`m1_final.json`, `m2_old_final.json`,
  `m2_new_final.json`, plus probe fixtures/JSON).

## Evidence
- Real command output pasted above for `py_compile`, the full 81/0 test run, and four
  `audit_launcher.py` invocations (M1 installed PASS, M2 installed pre-change FAIL, NEW M2 PASS,
  auto-select PASS), plus fail-closed probes.
- Exact literals implemented in `audit_launcher.py`: `M1_PROFILE` L167, `M2_PROFILE` L200,
  `LAUNCHER_PROFILES` L253, `select_profile` L259, `--profile` CLI L553, `LauncherProfile`
  dataclass L124, `UnknownProfileError` L119.
- Installed M1 launcher (`/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh`):
  bind L146 `--host 0.0.0.0`; no `--served-model-name`; extent L3 args L161-164.
- Installed M2 launcher (`/opt/sglang/local-prod-v1.2.1-candidate-M2/launcher/launch.sh`):
  ARGS L144-166 (no HiCache trio), mandatory `SGLANG_L3_MODE=disabled` L35-39.
- Reference launcher tokens read from `/opt/sglang/local-prod-v1.1-candidate/launcher/launch.sh`
  L44-67.
- New tests live in `test_audit_launcher.py` §9 (model-aware profiles) and §10 (installed M1).

## Defects or blockers
None blocking. Notes:
- The installed M2 launcher still FAILS its profile because the D1 launcher edit (injecting the
  HiCache trio into `launch.sh`) is a separate task. That failure is the intended fail-closed
  result until D1 lands; the "NEW M2 PASSES" demonstration uses a fixture rendered from the
  installed copy with the D1 trio injected.
- Two files outside my write scope (`bin/freeze.sh`, pins allowlist) are modified in the worktree
  by the separate D4/D7 task. I did not touch them (confirmed via mtimes and by read-only
  diff inspection); do not attribute them to this task.

## Remaining claims or exclusions
- Excluded/not performed: editing `launch.sh`, the template, `launcher-repin.sh`, `freeze.sh`,
  the pins allowlist, or `validate_telemetry.py`; running `freeze.sh`/`launcher-repin.sh`;
  GPU use; process signalling; port binding; inference; writes outside the two authorized files
  and `/tmp/opencode` scratch.
- Not established here: that the re-frozen M2 tree actually passes end-to-end (requires D1/D4/D5
  and a freeze window); that `launcher-repin.sh` auto-selects the correct profile (inference:
  it calls the audit with `--identity` and no `--profile`, which the tested auto-select path
  handles; the repin script itself was not run per constraints).
- Inference (marked): adding `192.168.20.250` to each profile's `approved_new_tokens` is required
  so the separately-enforced approved alternate bind host is accepted by the token-delta
  comparison; it does not widen the approved host set (4a still enforces exactly
  `{0.0.0.0, 192.168.20.250}`).
- The `git status` lines for `freeze.sh` / pins allowlist are pre-existing work owned by another
  task; I make no claim about their correctness.

## Terminal state
DONE
