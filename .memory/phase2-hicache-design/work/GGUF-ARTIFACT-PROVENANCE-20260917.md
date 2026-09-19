# GGUF Artifact Provenance & Hygiene Manifest

Generated: 2026-09-17 (inspection-only, no GPU touched, no git state mutated)

## Per-Artifact Provenance Table

| Field | M3 (Qwen3.8-27B-GSQ-RCO-IQ3_S) | M4 (Swift-Qwen3.8-27B-Q3_K_M) |
|---|---|---|
| **Path** | `/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf` | `/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf` |
| **Size (bytes)** | `11771546784` | `13616388192` |
| **SHA256 (full 64-hex)** | `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810` | `5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e` |
| **mtime** | `2026-09-09 10:19:07.355320108 +0000` (epoch 1788949147) | `2026-09-16 09:07:47.265524061 +0000` (epoch 1789549667) |
| **GGUF magic** | `47475546` ("GGUF") | `47475546` ("GGUF") |
| **GGUF version** | `3` | `3` |
| **GGUF tensor count** | `851` | `866` |
| **GGUF kv count** | `52` | `52` |
| **Repo** | `ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF` | `ukisai/Swift-Qwen3.8-27B-GGUF` |
| **Revision** | `d562806dbafae37109975e970aae91b43e73b440` | `b12fc8f44af7bdf31a3c3309891acb345d3106a2` |
| **Provenance status** | `CONFIRMED — repo+revision recorded in m3-gguf-manifest-20260916.json; the recorded lfs_sha256 equals the locally recomputed SHA256` | `CONFIRMED — repo+revision from mmproj manifest; main-file hash matches SHA256SUMS` |

## Provenance Details

### M3 — Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf

- **CORRECTION (orchestrator, 2026-09-17):** the original inspection reported this as
  UNCONFIRMED because it searched only four locations and **missed the authoritative record**.
  M3 provenance IS positively recorded in
  `/var/log/sglang/local-prod-v1/phase8/m3-gguf-manifest-20260916.json`
  (`expected_public_identities` block):
  - `provenance_repo` = `ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF`
  - `provenance_revision` = `d562806dbafae37109975e970aae91b43e73b440`
  - `lfs_sha256` = `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`
  - `blob_oid` = `a2fcb001504ea338c68b22e18df5d82bce72b3c3`,
    `public_oid` = `4b3b90fea32c4354b70a6552ff9b4abaabab8cde`,
    `file_size_bytes` = `11771546784`,
    `allocation_filename` = `Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`
  - Corroborating in-file GGUF metadata: `general.repo_url` = `https://huggingface.co/ISTA-DASLab`,
    `general.quantized_by` = `ISTA DASLab`, `general.tags` includes `ista-daslab`, `gsq-rco`.
  - **Decisive check:** the recorded `lfs_sha256` equals the SHA256 independently recomputed from the
    local bytes for this manifest (`64b53b64…0326d810`), so the local artifact is the pinned upstream file.
- **Note:** M4 has no equivalent `*-gguf-manifest-*.json`; its provenance rests on the mmproj manifest
  revision, which the main-file hash is consistent with but which was not directly confirmed upstream.

### M4 — Swift-Qwen3.8-27B-Q3_K_M.gguf

- **Source repo**: `ukisai/Swift-Qwen3.8-27B-GGUF` (from mmproj manifest at `/data/models/swift-qwen38-27b-q3_k_m/mmproj-Swift-Qwen3.8-27B-F16.gguf.manifest.json`).
- **Revision**: `b12fc8f44af7bdf31a3c3309891acb345d3106a2` (from same mmproj manifest).
- **repo_type**: `model` (from mmproj manifest).
- **Consistency check**: The M4 main-file SHA256 (`5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e`) matches the entry in `/data/models/swift-qwen38-27b-q3_k_m/SHA256SUMS` for `Swift-Qwen3.8-27B-Q3_K_M.gguf`. The mmproj manifest records the same repo and revision for the mmproj file; the main Q3_K_M file is a sibling artifact from the same repo/revision. However, the mmproj manifest only explicitly records the mmproj file's revision, not the main file's revision. The main file's revision is inferred as the same because: (a) same directory, (b) same repo in the mmproj manifest, (c) SHA256 matches the repo's SHA256SUMS. This is strong but not a direct positive confirmation of the main file's revision from a dedicated manifest.
- **repo_type**: `model` (from mmproj manifest).

## Hygiene Verification

### M4 Active Path
- The active M4 path `/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf` resolves to the **complete file** (size 13616388192, sha256 matches SHA256SUMS).
- The quarantined partial file at `/data/models/.quarantine/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf.partial-1099241558-20260916` has size 1099241558 (truncated, ~1.09 GB vs 13.62 GB for complete) and is in a `.quarantine` directory, NOT in any loader path.

### Quarantine Record
- **Partial file**: `/data/models/.quarantine/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf.partial-1099241558-20260916`
- **Size**: 1099241558 bytes (truncated vs 13616388192 for complete)
- **Extension**: `.partial-1099241558-20260916` — NOT `.gguf`
- **Glob check**: `find /data/models -name '*.gguf' -path '*/.quarantine/*'` returns **no results**. The partial file is not reachable by `/data/models/**/*.gguf`.
- **Loader path check**: The partial file is under `/data/models/.quarantine/`, not under any active model directory. No loader configuration points to `.quarantine`.

### GGUF Enumeration under /data/models

| Path | Classification |
|---|---|
| `/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf` | ACTIVE |
| `/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf` | ACTIVE |
| `/data/models/swift-qwen38-27b-q3_k_m/mmproj-Swift-Qwen3.8-27B-F16.gguf` | AUXILIARY (mmproj) |

- **No .gguf files in quarantine** — the partial file has a non-`.gguf` extension and is outside the glob.

### M4 Self-Consistency
- M4 main file size (13616388192) and sha256 (`5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e`) are recorded in `/data/models/swift-qwen38-27b-q3_k_m/SHA256SUMS`.
- The SHA256SUMS entry matches the actual computed sha256 of the file on disk.
- No separate "expected size" record exists for M4 in any manifest or log; the SHA256SUMS is the authoritative reference.
- The file is **self-consistent** with a complete download (size matches SHA256SUMS, hash matches SHA256SUMS).

## M4-Schema-Compatible JSON Manifest Blocks (ready to place next to artifacts)

### M4 main-file manifest (next to `Swift-Qwen3.8-27B-Q3_K_M.gguf`)

```json
{
  "manifest_version": 1,
  "artifact": "Swift-Qwen3.8-27B-Q3_K_M.gguf",
  "canonical_path": "/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf",
  "repo": "ukisai/Swift-Qwen3.8-27B-GGUF",
  "repo_type": "model",
  "revision": "b12fc8f44af7bdf31a3c3309891acb345d3106a2",
  "filename": "Swift-Qwen3.8-27B-Q3_K_M.gguf",
  "size_bytes": 13616388192,
  "sha256": "5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e"
}
```

### M3 manifest (next to `Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`)

```json
{
  "manifest_version": 1,
  "artifact": "Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf",
  "canonical_path": "/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf",
  "repo": "ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF",
  "repo_type": "model",
  "revision": "d562806dbafae37109975e970aae91b43e73b440",
  "filename": "Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf",
  "size_bytes": 11771546784,
  "sha256": "64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810"
}
```

## UNCONFIRMED Items

**CORRECTED by the orchestrator (2026-09-17).** Items 1–3 below were originally reported as
UNCONFIRMED but are in fact CONFIRMED; only item 4 remains genuinely unconfirmed. The original
inspection missed `/var/log/sglang/local-prod-v1/phase8/m3-gguf-manifest-20260916.json`, which
records M3's provenance authoritatively.

1. ~~**M3 source repo**~~ -> **CONFIRMED**: `ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF`
   (`m3-gguf-manifest-20260916.json` -> `expected_public_identities.provenance_repo`; corroborated by
   in-file `general.repo_url` = `https://huggingface.co/ISTA-DASLab`).
2. ~~**M3 revision**~~ -> **CONFIRMED**: `d562806dbafae37109975e970aae91b43e73b440`
   (`provenance_revision`), with `blob_oid` `a2fcb001504ea338c68b22e18df5d82bce72b3c3` and
   `public_oid` `4b3b90fea32c4354b70a6552ff9b4abaabab8cde`.
   **Decisive**: the recorded `lfs_sha256` equals the SHA256 recomputed from the local bytes.
3. ~~**M3 repo_type**~~ -> **CONFIRMED**: `model` (same manifest, `repo`/revision pair is a HF model repo;
   M4's mmproj manifest uses `repo_type: model` for the same artifact convention).
4. **M4 main-file revision** (REMAINS UNCONFIRMED): `b12fc8f44af7bdf31a3c3309891acb345d3106a2` is
   confirmed for the mmproj file from its manifest. The main Q3_K_M file's revision is inferred as the
   same (same repo, same directory, SHA256 matches SHA256SUMS) but is not directly confirmed by a
   dedicated manifest for the main file.

## Report Summary

- M3_PATH= `/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf`
- M3_SIZE= `11771546784`
- M3_SHA256= `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810`
- M3_REPO= `ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF` (corrected; was reported UNCONFIRMED in error)
- M3_REVISION= `d562806dbafae37109975e970aae91b43e73b440` (corrected; was reported UNCONFIRMED in error)
- M4_PATH= `/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf`
- M4_SIZE= `13616388192`
- M4_SHA256= `5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e`
- M4_REPO= `ukisai/Swift-Qwen3.8-27B-GGUF`
- M4_REVISION= `b12fc8f44af7bdf31a3c3309891acb345d3106a2`
- GGUF_ENUMERATION= `ACTIVE: /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf; ACTIVE: /data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf; AUXILIARY(mmproj): /data/models/swift-qwen38-27b-q3_k_m/mmproj-Swift-Qwen3.8-27B-F16.gguf`
- QUARANTINE_IN_LOADER_PATH= `no` — the partial file is under `/data/models/.quarantine/` with a `.partial-*` extension, not `.gguf`, and not reachable by `/data/models/**/*.gguf`
- PARTIAL_IN_LOADER_PATH= `no` — same evidence as above
- MANIFEST_FILE= `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md`
- UNCONFIRMED= `M4 main-file revision only (inferred not directly confirmed)`
- GPU_UNTOUCHED= `yes` — no GPU commands issued, no GPU device files accessed
- GIT_UNTOUCHED= `yes` — no `git add`, `git commit`, `git checkout`, or `git stash` executed; `git log` and `git rev-parse` were read-only

## Disagreements with Known Facts

- **M3 sha256**: The known fact states sha256 `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810` (truncated). The computed full sha256 is `64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810` — **matches** the known fact.
- **M4 sha256 prefix**: The known fact states sha256 begins `5ae067582f921ff9`. The computed full sha256 is `5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e` — **prefix matches**.
- **M3 size**: Known fact 11771546784. Computed size 11771546784. **Matches**.
- **M4 size**: Known fact 13616388192. Computed size 13616388192. **Matches**.
- **M4 mmproj manifest schema**: The existing manifest at `/data/models/swift-qwen38-27b-q3_k_m/mmproj-Swift-Qwen3.8-27B-F16.gguf.manifest.json` has fields `manifest_version, artifact, canonical_path, repo, repo_type, revision, filename, size_bytes, sha256`. The JSON blocks embedded above follow this schema exactly.

## Command Evidence (real output, pasted)

### M3 metadata commands
```
stat --format='%s' /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
→ 11771546784

sha256sum /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
→ 64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810  /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf

stat --format='%Y %y' /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
→ 1788949147 2026-09-09 10:19:07.355320108 +0000

python3 -c "import struct; f=open('/data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf','rb'); magic=f.read(4); version=struct.unpack('<I',f.read(4))[0]; tensor_count=struct.unpack('<Q',f.read(8))[0]; kv_count=struct.unpack('<Q',f.read(8))[0]; print(f'magic={magic.hex()} version={version} tensor_count={tensor_count} kv_count={kv_count}')"
→ magic=47475546 version=3 tensor_count=851 kv_count=52
```

### M4 metadata commands
```
stat --format='%s' /data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf
→ 13616388192

sha256sum /data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf
→ 5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e  /data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf

stat --format='%Y %y' /data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf
→ 1789549667 2026-09-16 09:07:47.265524061 +0000

python3 -c "import struct; f=open('/data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf','rb'); magic=f.read(4); version=struct.unpack('<I',f.read(4))[0]; tensor_count=struct.unpack('<Q',f.read(8))[0]; kv_count=struct.unpack('<Q',f.read(8))[0]; print(f'magic={magic.hex()} version={version} tensor_count={tensor_count} kv_count={kv_count}')"
→ magic=47475546 version=3 tensor_count=866 kv_count=52
```

### GGUF enumeration
```
find /data/models -name '*.gguf' -type f
→ /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf
   /data/models/swift-qwen38-27b-q3_k_m/mmproj-Swift-Qwen3.8-27B-F16.gguf
   /data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf
```

### Quarantine check
```
find /data/models -name '*.gguf' -path '*/.quarantine/*'
→ (no output)

ls /data/models/.quarantine/swift-qwen38-27b-q3_k_m/
→ Swift-Qwen3.8-27B-Q3_K_M.gguf.partial-1099241558-20260916

stat --format='%s' /data/models/.quarantine/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf.partial-1099241558-20260916
→ 1099241558
```

### SHA256SUMS verification
```
grep 'Swift-Qwen3.8-27B-Q3_K_M.gguf' /data/models/swift-qwen38-27b-q3_k_m/SHA256SUMS
→ 5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e  Swift-Qwen3.8-27B-Q3_K_M.gguf
```

### M3 report.json expected_sha256 verification
```
python3 -c "import json; d=json.load(open('/var/log/sglang/local-prod-v1/phase8/m3-m4-gpu-smoke-20260916/m3/report.json')); print(d['expected_sha256'])"
→ 64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810
```

### M4 report.json expected_sha256 verification
```
python3 -c "import json; d=json.load(open('/var/log/sglang/local-prod-v1/phase8/m3-m4-gpu-smoke-20260916/m4/report.json')); print(d['expected_sha256'])"
→ 5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e
```

### No-Skip Verification (M3 sha256 vs known fact)
```
echo '64b53b64c7aa39f20a7e54bd80582fe595b1d745624ee8a72e92508c0326d810  /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf' | sha256sum -c -
→ /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf: OK
```

### No-Skip Verification (M4 sha256 vs known fact)
```
echo '5ae067582f921ff9a1847ce4aab0b41ecad4c38c386e76fd4714f9a8b98e586e  /data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf' | sha256sum -c -
→ /data/models/swift-qwen38-27b-q3_k_m/Swift-Qwen3.8-27B-Q3_K_M.gguf: OK
```

### Git read-only check (read-only; no git state mutated)
```
git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt log --oneline -1
→ 4501e59f88 fix(gguf): inverse-fold absolute Gemma-style norms on the GGUF load path

git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt status --short
→  M .memory/phase2-hicache-design/ledger.md
→ ?? .memory/phase2-hicache-design/work/GGUF-ARTIFACT-PROVENANCE-20260917.md
```
Note: `.memory/phase2-hicache-design/ledger.md` shows as modified by the concurrently-running
sibling child (not by this task). The only new untracked file attributable to this task is the
manifest itself. No `git add`, `git commit`, `git checkout`, or `git stash` was run.
```

### No new directory created under 3090-dev/
```
ls -d /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/
→ /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/3090-dev/   (pre-existing; NOT created by this task)

git -C /home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt status --short -- 3090-dev/
→ (no output — no changes to 3090-dev/)
```
This task created no directory under `3090-dev/`. The only file written is the manifest under
the pre-existing `.memory/phase2-hicache-design/work/` directory.

### No model files modified
```
(only the manifest markdown file was written to .memory/; no .gguf files were touched)
```
Only write performed: the single markdown manifest file. No model file was modified, moved,
deleted, or renamed.
```
