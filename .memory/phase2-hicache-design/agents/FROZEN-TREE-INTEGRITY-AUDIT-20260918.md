# FROZEN-TREE-INTEGRITY-AUDIT-20260918

## Identity verdict (one line)
**IDENTITY-DIVERGED** — the live tree's `TREE_HASH` is now `5ed662d0…` while the acceptance campaign is pinned to `TREE_HASH=3bd285d5…`; `SOURCE_COMMIT=b2bbd6ea28` and all `src/` bytes are unchanged, and the *only* content change is `launcher/launch.sh` line 146 `--host 127.0.0.1` → `--host 0.0.0.0`, with the manifest/identity files re-pinned around it.

- **Terminal state: DONE**
- Role: devops-executor — READ-ONLY. No process was started/stopped/signalled; no file in the tree was edited, repaired, restored, or deleted. The only write was this artifact plus a read-only `sha256sum -c` output file under `/tmp/opencode/`.

---

## Task
Establish exactly what changed in the frozen production tree `/opt/sglang/local-prod-v1.2.1-candidate` after the 2026-09-17 ~21:16:38–44Z in-place rewrite (4 files backed up as `*.bak-bindhost-20260917T211632Z`), attribute the change, and decide whether the frozen identity is still valid for the acceptance campaign pinned `SOURCE_COMMIT=b2bbd6ea28 / TREE_HASH=3bd285d5…`.

## Scope
- Target: `/opt/sglang/local-prod-v1.2.1-candidate` and its metadata only.
- Read-only forensic commands (`ls`, `stat`, `cat`, `diff`, `sha256sum`, `grep`, `find`, `pgrep`, `/proc` inspection, `ss`).
- Explicitly excluded: any repair/restore/delete, any signal to any process, any git mutation, any GPU workload, starting/stopping anything.

---

## Result

### A. What is there now

`ls -la /opt/sglang/local-prod-v1.2.1-candidate/`
```
total 24
drwxrwxr-x  6 ubuntu ubuntu 4096 Sep 17 18:35 .
drwxr-xr-x  9 root   root   4096 Sep 17 18:32 ..
lrwxrwxrwx  1 ubuntu ubuntu   30 Sep 17 18:35 env -> /home/ubuntu/venvs/sglang-3090
dr-xr-xr-x  2 ubuntu ubuntu 4096 Sep 17 18:35 launcher
drwxrwxr-x  2 ubuntu ubuntu 4096 Sep 17 21:16 manifest
dr-xr-xr-x 24 ubuntu ubuntu 4096 Sep 17 18:35 src
dr-xr-xr-x  2 ubuntu ubuntu 4096 Sep 17 18:35 tools
```

`ls -la /opt/sglang/local-prod-v1.2.1-candidate/manifest/`
```
total 4036
drwxrwxr-x 2 ubuntu ubuntu    4096 Sep 17 21:16 .
drwxrwxr-x 6 ubuntu ubuntu    4096 Sep 17 18:35 ..
-rw-rw-r-- 1 ubuntu ubuntu 2042130 Sep 17 21:16 TREE-SHA256.txt
-rw-rw-r-- 1 ubuntu ubuntu 2042130 Sep 17 18:36 TREE-SHA256.txt.bak-bindhost-20260917T211632Z
-rw-rw-r-- 1 ubuntu ubuntu    1601 Sep 17 21:16 identity-pins.json
-rw-rw-r-- 1 ubuntu ubuntu    1601 Sep 17 18:36 identity-pins.json.bak-bindhost-20260917T211632Z
-rw-rw-r-- 1 ubuntu ubuntu    5869 Sep 17 21:16 identity.json
-rw-rw-r-- 1 ubuntu ubuntu    5869 Sep 17 18:36 identity.json.bak-bindhost-20260917T211632Z
-r-xr-xr-x 1 ubuntu ubuntu    8336 Sep 17 18:35 launch.sh.bak-bindhost-20260917T211632Z
```

`ls -la /opt/sglang/local-prod-v1.2.1-candidate/launcher/`
```
total 20
dr-xr-xr-x 2 ubuntu ubuntu 4096 Sep 17 18:35 .
drwxrwxr-x 6 ubuntu ubuntu 4096 Sep 17 18:35 ..
-r-xr-xr-x 1 ubuntu ubuntu 8334 Sep 17 21:16 launch.sh
```

Every `*.bak*` under the tree (read-only `find`, mtimes):
```
2026-09-17 18:35:56.5344654430 /opt/sglang/local-prod-v1.2.1-candidate/manifest/launch.sh.bak-bindhost-20260917T211632Z
2026-09-17 18:36:24.6911108310 /opt/sglang/local-prod-v1.2.1-candidate/manifest/TREE-SHA256.txt.bak-bindhost-20260917T211632Z
2026-09-17 18:36:32.5935635510 /opt/sglang/local-prod-v1.2.1-candidate/manifest/identity.json.bak-bindhost-20260917T211632Z
2026-09-17 18:36:32.5945636080 /opt/sglang/local-prod-v1.2.1-candidate/manifest/identity-pins.json.bak-bindhost-20260917T211632Z
```
Note: the `.bak` filenames carry the rewrite wall-clock tag `20260917T211632Z`, but `cp -p` reproduced the **original** file mtimes (18:35/18:36, freeze time), so the `.bak` mtimes do not show the 21:16 edit time. The `launch.sh` backup was placed **inside `manifest/`**, not `launcher/` (manifest is the writable evidence dir; `launcher/` is `dr-xr-xr-x`).

Current mtimes (stat):
```
2026-09-17 21:16:44.019257731 +0000 launcher/launch.sh
2026-09-17 21:16:44.117260654 +0000 manifest/identity.json
2026-09-17 21:16:44.117260654 +0000 manifest/identity-pins.json
2026-09-17 21:16:44.075259401 +0000 manifest/TREE-SHA256.txt
```
The `manifest/` directory itself: `2026-09-17 21:16:38.090080871` (first backup creation).

### B. Current identity vs recorded identity

`cat manifest/identity.json` (full):
```json
{
  "LAUNCHER_HASH": "4ae6847066ca0104159cef66f0ae67cd09b940e4d6c8bb1725fe4cdb32ff2ff5",
  "LOADED_SO_HASH": {
    "bytes": 578264,
    "cache_root": "/home/ubuntu/.cache/sglang/rust_extensions",
    "note": "sha256 of the native extension the loader selects for this source; when null the resolved path is recorded and the hash must be verified at launch",
    "path": "/home/ubuntu/.cache/sglang/rust_extensions/artifacts/l3-native-wal/51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376/_l3wal.cpython-312-x86_64-linux-gnu.so",
    "resolved_fingerprint": "51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376",
    "sha256": "f1f0c0d3634f3e11891d6632790fc9301167d2e9168b2e441506684846220750",
    "source_digest": "de26465d438f284d5c03654997d719964c0c7c51c37d9d07bcf83a3c509a16aa",
    "target_fingerprint": "ddabafdf7410df267036948a",
    "unavailable_reason": null,
    "verified_at_freeze": true,
    "verified_at_launch": false
  },
  "RUST_SOURCE_DIGEST": "51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376",
  "SOURCE_COMMIT": "b2bbd6ea28",
  "TREE_HASH": "5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950",
  "freeze_tool": "v1.1.2-freeze-20260917",
  "frozen_at_utc": "2026-09-17T18:36:32Z",
  "generated_by": "bin/freeze.sh",
  "gpu_touched": false,
  "identity_fields": {
    "LAUNCHER_HASH": "sha256 of launcher/launch.sh",
    "LOADED_SO_HASH": "sha256 of the loader-selected native .so",
    "RUST_SOURCE_DIGEST": "loader fingerprint over src/rust (cache key the .so binds to)",
    "SOURCE_COMMIT": "git -C <src> rev-parse HEAD",
    "TREE_HASH": "sha256 of manifest/TREE-SHA256.txt (self-digest)"
  },
  "identity_version": 1,
  "launcher": {
    "note": "rendered by bin/launcher-repin.sh; hard gate + per-run namespace enforcement",
    "path": "/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh",
    "sha256": "4ae6847066ca0104159cef66f0ae67cd09b940e4d6c8bb1725fe4cdb32ff2ff5"
  },
  "layout": {
    "env": { "note": "shared venv, not per-tree frozen", "path": "/opt/sglang/local-prod-v1.2.1-candidate/env", "type": "symlink" },
    "launcher": { "path": "/opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh" },
    "manifest": { "note": "evidence dir, intentionally writable", "path": "/opt/sglang/local-prod-v1.2.1-candidate/manifest" },
    "src": { "mode_after_freeze": "write bits cleared on every entry", "path": "/opt/sglang/local-prod-v1.2.1-candidate/src" },
    "tools": { "path": "/opt/sglang/local-prod-v1.2.1-candidate/tools" }
  },
  "name": "LOCAL-PROD-v1.2.1",
  "namespace_policy": {
    "enforcement": "tools/l3_namespace.py (installed verbatim from the freeze tool) + launcher gate",
    "rule": "one task/run -> one unique L3 store namespace",
    "shared_stores": "never used or cleared by a run (clearing destroys the previous run's WAL/durability evidence)",
    "store": "<SGLANG_L3_ROOT>/<SGLANG_RUN_ID>, default /data/l3/<run-id>"
  },
  "no_server_started": true,
  "open_items": [
    "manifest/ and __pycache__/.pytest_cache are excluded from the tree digest by design",
    "the env symlink is shared with v1/v1.1 and is not per-tree frozen",
    "per-run LOG_DIR is derived from SGLANG_RUN_ID so a run cannot overwrite a previous run's metrics evidence"
  ],
  "runtime": {
    "editable_binding_caveat": "the venv editable install resolves sglang to the live WIP workspace; every launch MUST export PYTHONPATH=<tree>/src/python and pass the fail-closed source-identity gate in launcher/launch.sh",
    "env_symlink": "/opt/sglang/local-prod-v1.2.1-candidate/env"
  },
  "self_test": {
    "added": ["./tools/l3_namespace.py", "./tools/preflight_identity.py"],
    "fidelity_ok": true,
    "mode": "build",
    "modified_allowed": ["./launcher/launch.sh", "./tools/validate_telemetry.py"]
  },
  "source_tree": "/tmp/opencode/v1.2.1-stage",
  "status": "FROZEN",
  "template_identity": "LOCAL-PROD-v1.1",
  "tools_sha256": {
    "l3_namespace.py": "40e65e04b1daabbd9248aa273dc5ceaa55343e50050d46daa0e5df4dce880b44",
    "preflight_identity.py": "29a5a11bc8f1bef402a6a4b10ac62240798eca1a1a2e288c30b650208ac858de",
    "validate_telemetry.py": "6324681519d9d2f71d6a3e75a1bc5bf834033c038ed6cfd0ee69c6c6f2bc89f8"
  },
  "tree": {
    "exclusions": { "__pycache__/ and .pytest_cache/": "interpreter/test-runner byproducts", "manifest/": "self-reference; its digest is recorded here instead" },
    "file_count": 14788,
    "path": "/opt/sglang/local-prod-v1.2.1-candidate",
    "src_file_count": 14784,
    "src_path": "/opt/sglang/local-prod-v1.2.1-candidate/src",
    "src_total_bytes": 2014047336,
    "srctree_stream_digest_command_v1_convention": "cd /opt/sglang/local-prod-v1.2.1-candidate/src && find . -type f -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum",
    "srctree_stream_digest_sha256_v1_convention": "c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc",
    "total_bytes": 2014085068,
    "tree_manifest_bytes": 2042130,
    "tree_manifest_digest_sha256": "5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950",
    "tree_manifest_file": "manifest/TREE-SHA256.txt",
    "tree_manifest_generation_command": "cd /opt/sglang/local-prod-v1.2.1-candidate && find . -type f -not -path './manifest/*' -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -print0 | LC_ALL=C sort -z | xargs -0 sha256sum",
    "tree_manifest_lines": 14788,
    "tree_manifest_sha256_command": "sha256sum /opt/sglang/local-prod-v1.2.1-candidate/manifest/TREE-SHA256.txt",
    "tree_manifest_sha256_self": "5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950",
    "tree_name": "local-prod-v1.2.1-candidate"
  }
}
```

`cat manifest/identity-pins.json` (full):
```json
{
  "LAUNCHER_HASH": "4ae6847066ca0104159cef66f0ae67cd09b940e4d6c8bb1725fe4cdb32ff2ff5",
  "LOADED_SO_HASH": "f1f0c0d3634f3e11891d6632790fc9301167d2e9168b2e441506684846220750",
  "LOADED_SO_PATH": "/home/ubuntu/.cache/sglang/rust_extensions/artifacts/l3-native-wal/51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376/_l3wal.cpython-312-x86_64-linux-gnu.so",
  "RUST_SOURCE_DIGEST": "51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376",
  "SOURCE_COMMIT": "b2bbd6ea28",
  "TREE_HASH": "5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950",
  "created_at_utc": "2026-09-17T18:36:32Z",
  "freeze_tool": "v1.1.2-freeze-20260917",
  "identity": "LOCAL-PROD-v1.2.1",
  "launcher_sha256": "4ae6847066ca0104159cef66f0ae67cd09b940e4d6c8bb1725fe4cdb32ff2ff5",
  "source_tree": "/tmp/opencode/v1.2.1-stage",
  "src_file_count": 14784,
  "src_stream_digest_v1_convention": "c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc",
  "src_total_bytes": 2014047336,
  "tools_sha256": {
    "l3_namespace.py": "40e65e04b1daabbd9248aa273dc5ceaa55343e50050d46daa0e5df4dce880b44",
    "preflight_identity.py": "29a5a11bc8f1bef402a6a4b10ac62240798eca1a1a2e288c30b650208ac858de",
    "validate_telemetry.py": "6324681519d9d2f71d6a3e75a1bc5bf834033c038ed6cfd0ee69c6c6f2bc89f8"
  },
  "tree": "/opt/sglang/local-prod-v1.2.1-candidate",
  "tree_file_count": 14788,
  "tree_manifest_bytes": 2042130,
  "tree_manifest_sha256": "5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950",
  "tree_name": "local-prod-v1.2.1-candidate",
  "tree_total_bytes": 2014085068
}
```

Field summary (current values):
| Field | Current (post-21:16:44) |
|---|---|
| name / identity | LOCAL-PROD-v1.2.1 |
| status | FROZEN |
| frozen_at_utc | 2026-09-17T18:36:32Z (NOT updated by the rewrite) |
| SOURCE_COMMIT | b2bbd6ea28 |
| RUST_SOURCE_DIGEST | 51ca2e73eb48bd054bcab6ea100bd2faf84411579a0296b31b53ab58804b0376 |
| LOADED_SO_HASH | f1f0c0d3634f3e11891d6632790fc9301167d2e9168b2e441506684846220750 |
| LAUNCHER_HASH | 4ae6847066ca0104159cef66f0ae67cd09b940e4d6c8bb1725fe4cdb32ff2ff5 |
| TREE_HASH | 5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950 |

**Fields that look rewritten** (vs the `.bak` copies): `LAUNCHER_HASH` (×1 in identity.json, ×2 in identity-pins.json incl. `launcher_sha256`), `TREE_HASH` (identity.json ×3: top-level + `tree.tree_manifest_digest_sha256` + `tree.tree_manifest_sha256_self`; identity-pins ×2), and in identity.json `launcher.sha256`. **Unchanged:** SOURCE_COMMIT, RUST_SOURCE_DIGEST, LOADED_SO_HASH, tools_sha256, src digests/sizes, name, status, `frozen_at_utc` (still 18:36:32Z).

`sha256sum launcher/launch.sh` vs declared `LAUNCHER_HASH`:
```
4ae6847066ca0104159cef66f0ae67cd09b940e4d6c8bb1725fe4cdb32ff2ff5  /opt/sglang/local-prod-v1.2.1-candidate/launcher/launch.sh
```
→ **MATCHES** the declared `LAUNCHER_HASH` / `launcher.sha256` / `launcher_sha256`. Self-consistent.

`grep -n -- "--host" launcher/launch.sh` (CURRENT bind host line, verbatim):
```
146:  --host 0.0.0.0 --port "$PORT"
```
Same grep on the backup:
```
146:  --host 127.0.0.1 --port "$PORT"
```

`manifest/TREE-SHA256.txt` head:
```
4ae6847066ca0104159cef66f0ae67cd09b940e4d6c8bb1725fe4cdb32ff2ff5  ./launcher/launch.sh
77685bca58a00fbdb78fc13e80ababcd147b1f9f65fa7559efa443893e618426  ./src/.claude/rules/comment-style.md
... (14788 lines total)
```
tail:
```
3006f63dca3396b746877ce59dde2ef51a82514e97721b9233233132b59821b3  ./src/tools/expert_pack/prepare_kimi_pack.py
96f8d99ea0793f994debc75f616c21b4e4b84b0d7ae2336bbb3b50ec77b542e9  ./src/tools/expert_pack/validate.py
40e65e04b1daabbd9248aa273dc5ceaa55343e50050d46daa0e5df4dce880b44  ./tools/l3_namespace.py
29a5a11bc8f1bef402a6a4b10ac62240798eca1a1a2e288c30b650208ac858de  ./tools/preflight_identity.py
6324681519d9d2f71d6a3e75a1bc5bf834033c038ed6cfd0ee69c6c6f2bc89f8  ./tools/validate_telemetry.py
```

TREE-SHA256 self-digest (current) vs declared TREE_HASH:
```
5ed662d0b603ef9ab29294a690c036718714e0ed5b699b62b8b7be488defd950  /opt/sglang/local-prod-v1.2.1-candidate/manifest/TREE-SHA256.txt
```
→ **MATCHES** current `TREE_HASH`. The backup manifest self-digest was `3bd285d51e3f…` = the campaign pin.

Full read-only verification against the manifest **was performed** (`sha256sum -c` writes nothing):
```
exit=0
14788
--- FAILED ---
(none)
```
→ **14788/14788 lines OK, 0 failed.** Every path currently in the tree hashes exactly to its manifest entry. The manifest's only delta vs the backup is the single `./launcher/launch.sh` line (backup `38487942…` → current `4ae68470…`).

### C. Attribution of the change

`diff` backup → current (exact deltas, no other lines changed):

`launch.sh`:
```
146c146
<   --host 127.0.0.1 --port "$PORT"
---
>   --host 0.0.0.0 --port "$PORT"
```

`identity.json` (5 hunks):
```
2c2   "LAUNCHER_HASH": 38487942… -> 4ae68470…
18c18 "TREE_HASH":     3bd285d5… -> 5ed662d0…
34c34 launcher.sha256: 38487942… -> 4ae68470…
108c108 tree_manifest_digest_sha256: 3bd285d5… -> 5ed662d0…
113c113 tree_manifest_sha256_self:   3bd285d5… -> 5ed662d0…
```

`identity-pins.json` (4 hunks):
```
2c2   "LAUNCHER_HASH":  38487942… -> 4ae68470…
7c7   "TREE_HASH":      3bd285d5… -> 5ed662d0…
11c11 "launcher_sha256": 38487942… -> 4ae68470…
24c24 "tree_manifest_sha256": 3bd285d5… -> 5ed662d0…
```

`TREE-SHA256.txt`: exactly one line changed (line 1) — `./launcher/launch.sh` hash `38487942…` → `4ae68470…`. All 14787 other lines identical.

**Plain statement of what changed:** the sole *content* edit is `launcher/launch.sh` line 146 changing the bind host from loopback `127.0.0.1` to wildcard `0.0.0.0`. The manifest and both identity files were then re-pinned consistently around that one line. Hash-chain is internally consistent: `sha256(launch.sh)=4ae68470…` = manifest line 1 = `LAUNCHER_HASH`; `sha256(TREE-SHA256.txt)=5ed662d0…` = `TREE_HASH`; full `sha256sum -c` = 14788/14788 OK. This **is the intended "bind host" fix shape** (`127.0.0.1` → `0.0.0.0`): the `.bak` suffix literally names it `bindhost`, and only the `--host` token changed — the launcher's argv template, ports, model, L3/hicache flags, and the `src/` tree are byte-identical. The edit was not a template re-render (a `launcher-repin.sh` render would also touch the template-derived comments/fingerprint lines; the diff is a single-token change).

**Related processes currently running:** none attributable to the rewrite.
```
pgrep -af 'freeze|launcher-repin|audit_launcher|bindhost'
1656348 /bin/bash -c echo "=== pgrep ==="; pgrep -af 'freeze|...'   <-- self-match of the audit's own shell only
```
No `freeze`/`launcher-repin`/`audit_launcher`/`bindhost` process exists. No process other than the audit's own shell had a cwd on the tree:
```
ls -l /proc/*/cwd | grep -i local-prod-v1.2.1   -> (none)
/proc cwd scan for *local-prod-v1.2.1*          -> only PID 1657154 = this audit's own `sha256sum -c` shell
```
So the mutating workstream appears to have **completed** (rewrite finished 21:16:44, backups created 21:16:38); no live writer remains.

### D. Impact assessment (report only)

**Live production process.** The pid named in the brief, `1602808`, **no longer exists** (`/proc/1602808` absent). The current :30000 listener is a *newer* process:
```
LISTEN 0 2048 0.0.0.0:30000 0.0.0.0:*  users:(("python",pid=1654119,fd=68))
```
```
1654119  1654092  ubuntu  STARTED Thu Sep 17 21:18:00 2026  python -u -m sglang.launch_server --model-path /data/models/qwen35-9b-w4a16 --host 0.0.0.0 --port 30000 --tp-size 1 ... --enable-hierarchical-cache ... --export-metrics-to-file-dir /tmp/opencode/prod-service-20260917/logs/prod-20260917T211800Z-1653969
```
- Env: `PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate/src/python`, `SGLANG_L3_ROOT=/data/l3`, `SGLANG_RUN_ID=prod-20260917T211800Z-1653969`, `SGLANG_L3_NATIVE_WRITE_PATH=1`. Parent is `supervise.sh … /opt/sglang/local-prod-v1.2.1-candidate 30000 …`.
- This process started **21:18:00Z, ~76 s after the 21:16:44Z rewrite**, and its argv already carries `--host 0.0.0.0`. A prior run (`prod-20260917T190831Z-1602589`) logged until 21:17:44 and was replaced. So the tree edit coincides with a production restart, and the *currently* serving process reflects the post-edit `0.0.0.0` bind.
- **Can the file edit affect the already-running process?** No. The process `exec`'d and loaded its Python/argv at start; an in-place edit to `launch.sh`/manifest cannot alter a running process's loaded code or arguments. The edit changes **what a future start binds** (wildcard `0.0.0.0` instead of loopback), and the restart at 21:18 already exercised that: :30000 is now exposed on all interfaces rather than `127.0.0.1` only.

**Campaign usability — IDENTITY-DIVERGED.** The campaign pin is `SOURCE_COMMIT=b2bbd6ea28 / TREE_HASH=3bd285d5…`. The current tree's `TREE_HASH=5ed662d0…`; the value `3bd285d5…` is now found only in the `.bak` copies. Evidence: `sha256(TREE-SHA256.txt)` before = `3bd285d5…` (backup) vs after = `5ed662d0…` (current), and `TREE_HASH` differs identically in both identity files. Therefore the frozen identity no longer matches the pinned `TREE_HASH`. Mitigating facts (scope of divergence): `SOURCE_COMMIT` is still `b2bbd6ea28`; `src_stream_digest=c7427132…`, `RUST_SOURCE_DIGEST`, `LOADED_SO_HASH`, tools hashes, and all 14784 `src/` files are byte-identical (full `sha256sum -c` 14788/14788 OK); the divergence is confined to the launcher's one bind-host token plus the manifest/identity self-digests. So this is a **metadata/launcher re-pin around a one-line security-relevant host change**, not a source-content drift. It still means an acceptance campaign that verifies its identity pin by `TREE_HASH` will **fail the pin** as currently recorded, and a campaign that re-pins to `5ed662d0…` must consciously accept `0.0.0.0` exposure. Verdict: **IDENTITY-DIVERGED** (source commit intact; tree-manifest/launcher hash and bind host diverged).

**Post-freeze mtime blast radius** (`find -newermt '2026-09-17T18:36:32Z'`), 7 entries:
```
2026-09-17 18:36:32.5935635510 f .../manifest/identity.json.bak-bindhost-20260917T211632Z
2026-09-17 18:36:32.5945636080 f .../manifest/identity-pins.json.bak-bindhost-20260917T211632Z
2026-09-17 21:16:38.0900808710 d .../manifest
2026-09-17 21:16:44.0192577310 f .../launcher/launch.sh
2026-09-17 21:16:44.0752594010 f .../manifest/TREE-SHA256.txt
2026-09-17 21:16:44.1172606540 f .../manifest/identity-pins.json
2026-09-17 21:16:44.1172606540 f .../manifest/identity.json
```
(The two `*identity*.bak` entries appear only because their preserved freeze-time mtime lands 0.59 s after the `18:36:32Z` boundary; `launch.sh.bak` at 18:35:56 and `TREE-SHA256.txt.bak` at 18:36:24 fall before the boundary and are not listed. Only the 5 objects after 21:16 — 4 files + `manifest/` dir — are true post-freeze writes; all are the one bind-host change plus its re-pin + backups.)

**Notable defects/anomalies (reported, not acted on):**
1. `frozen_at_utc` remains `2026-09-17T18:36:32Z` and `status` remains `FROZEN` although the tree was mutated at 21:16:44Z. The identity self-description is now misleading: it advertises FROZEN-at-18:36 while its own hash was re-pinned at 21:16.
2. The `launch.sh` backup was written into `manifest/` (writable evidence dir) rather than beside the original in `launcher/`; the freeze tool’s `cp -p` preserved 18:35 mtime, so the backup’s mtime does not reflect the 21:16 mutation.
3. `.bak` files are retained in the tree, in the writable `manifest/` dir; `manifest/` is excluded from the tree digest by design, so they neither pollute nor protect the digest.
4. The bind change to `0.0.0.0` widens network exposure of a production inference endpoint (previously loopback-only).
5. The change was made by an unidentified concurrent workstream, not the freeze/repin tooling under `/tmp/opencode/v1.1.2-freeze-20260917/bin/launcher-repin.sh` (which renders from a template and would not produce a single-token diff, nor the `bindhost` backup suffix).

**E. No repair/restore/delete was performed.** `.bak` files and all current files are untouched by this audit.

---

## Evidence (commands run, all read-only)
- `ls -la` on tree root, `manifest/`, `launcher/`.
- `find … -name '*.bak*' -printf …` (mtime enumeration).
- `stat -c '%y %n'` / full `stat` on the four target files and dirs.
- `cat manifest/identity.json`, `cat manifest/identity-pins.json`.
- `sha256sum launcher/launch.sh`; `sha256sum manifest/TREE-SHA256.txt`; `sha256sum` on the two `.bak` counterparts.
- `grep -n -- '--host'` on current and backup launch.sh.
- `head`/`tail`/`wc -l` on `TREE-SHA256.txt` and its `.bak`.
- `diff` backup→current for launch.sh, identity.json, identity-pins.json; `diff` of TREE-SHA256 backup→current.
- `cd /opt/sglang/local-prod-v1.2.1-candidate && sha256sum -c manifest/TREE-SHA256.txt` → exit 0, 14788 OK, 0 failed (output preserved at `/tmp/opencode/verify-tree.out`).
- `pgrep -af 'freeze|launcher-repin|audit_launcher|bindhost'`; `/proc/*/cwd` scans via `ls -l` and `readlink`.
- `ps -o … -p 1602808` (absent) and `-p 1654119`; `/proc/1654119/{cwd,exe,cmdline,environ}`; `ss -ltnp` for :30000.
- `find … -newermt '2026-09-17T18:36:32Z' -printf …`.
- `grep`/`find` over `/tmp/opencode` for `repin`/`bindhost` scripts and near-21:16 mtimes; `grep` of `launcher-repin.sh`.

## Defects / blockers
- No blocker to completing this read-only audit. See "Notable defects/anomalies" above (stale `frozen_at_utc`/`status`, misplaced backup, widened `0.0.0.0` exposure, unidentified writer).
- Open risk requiring a decision by the orchestrator (outside this read-only role): the acceptance campaign pin `TREE_HASH=3bd285d5…` no longer matches the live tree; re-pinning and/or review of the concurrent workstream is needed. A live production process is now serving on `0.0.0.0:30000`.

## Remaining claims / exclusions
- **Established:** exact diffs; hash-chain consistency; full 14788/14788 read-only verification; current bind host `0.0.0.0`; pid 1602808 gone and pid 1654119 serving `0.0.0.0:30000` since 21:18:00Z; no active freeze/repin process; campaign `TREE_HASH` no longer present in the live identity.
- **Not established / excluded:** *who* ran the 21:16:44Z mutation (no attributable live process; no matching `bindhost` script found — likely an ad-hoc edit by another workstream); whether that workstream has further intent; whether the campaign will re-pin; git history/commit of the edit (no git mutation performed, and tree is not a repo per environment); whether network policy allows `0.0.0.0` exposure of :30000.
- No source content under `src/` changed; no GPU workload run; no process signalled; no file repaired/restored/deleted.

## Terminal state: DONE
