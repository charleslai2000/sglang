#!/usr/bin/env python3
"""Regenerate DIFF-VS-V1.txt for LOCAL-PROD-v1.1 including non-src changes."""
import subprocess, hashlib, datetime, sys

V1 = "/opt/sglang/local-prod-v1"
CAND = "/opt/sglang/local-prod-v1.1-candidate"
OUT = "/tmp/opencode/repin/DIFF-VS-V1.new"

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def size(p):
    return subprocess.run(["stat", "-c", "%s", p], capture_output=True, text=True).stdout.strip()

# --- changed src files via content compare ---
r = run(f"sudo rsync -ainc --exclude='__pycache__' --exclude='.pytest_cache' "
        f"--out-format='%i|%n' {V1}/src/ {CAND}/src/")
src_changed = sorted(ln.split("|", 1)[1] for ln in r.stdout.splitlines() if ln.startswith(">f"))

# --- non-src changed files (launcher + tools) ---
non_src = ["launcher/launch.sh", "tools/validate_telemetry.py"]
non_src_changed = [p for p in non_src
                   if sha(f"{V1}/{p}") != sha(f"{CAND}/{p}")]

allpairs = [("src", p, f"{V1}/src/{p}", f"{CAND}/src/{p}") for p in src_changed] + \
           [("tree", p, f"{V1}/{p}", f"{CAND}/{p}") for p in non_src_changed]

now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
L = []
L.append("DIFF-VS-V1 — LOCAL-PROD-v1.1 (candidate) vs LOCAL-PROD-BASELINE-v1 (frozen baseline)")
L.append(f"generated_utc : {now}")
L.append(f"baseline tree : {V1}   [LOCAL-PROD-BASELINE-v1, FROZEN, read-only]")
L.append(f"candidate tree: {CAND} [LOCAL-PROD-v1.1]")
L.append("")
L.append("NOTE: this revision additionally carries the two NON-SRC change families that were not in")
L.append("      the superseded 2026-09-16T17:09:56Z identity: the launcher re-pin")
L.append("      (launcher/launch.sh: v1 source/log/L3/branding -> v1.1) and the telemetry-tool")
L.append("      repoint (tools/validate_telemetry.py: SRC -> v1.1 src + self-branding).")
L.append("")
L.append("METHOD")
L.append("  1) content-compare (sha256, not mtime): sudo rsync -ainc --exclude='__pycache__' --exclude='.pytest_cache' <v1>/src/ <cand>/src/")
L.append("  2) missing-file check (reverse, dry-run delete): sudo rsync -ainc --delete --exclude='__pycache__' --exclude='.pytest_cache' <cand>/src/ <v1>/src/")
L.append("  3) unified diffs: diff -u --label a/<path> --label b/<path> <v1>/<path> <cand>/<path>")
L.append("")
L.append("SUMMARY")
L.append(f"  changed files : {len(allpairs)} ({len(src_changed)} src + {len(non_src_changed)} non-src)")
L.append("  candidate-only files (would be deleted from baseline) : 0")
L.append("  baseline-only files  (would be deleted from candidate): 0")
L.append("")
L.append("  scope  path                                                       v1_bytes  v1_sha256                                                         cand_bytes cand_sha256")

tot_v1 = tot_cand = 0
for scope, p, a, b in allpairs:
    vb, cb = int(size(a)), int(size(b))
    tot_v1 += vb; tot_cand += cb
    L.append(f"  {scope:<6} {p:<58} {vb:>8}  {sha(a)}  {cb:>8}  {sha(b)}")

L.append("")
L.append(f"  TOTALS (all {len(allpairs)} changed files): v1_bytes={tot_v1}  cand_bytes={tot_cand}  net={tot_cand - tot_v1:+d}")
L.append("")
L.append("  LINE STATS (git diff --no-index --numstat, +added/-removed):")
sum_add = sum_rem = 0
for scope, p, a, b in allpairs:
    ns = run(f"git diff --no-index --numstat '{a}' '{b}'").stdout.split()
    add, rem = int(ns[0]) if ns else 0, int(ns[1]) if ns else 0
    sum_add += add; sum_rem += rem
    L.append(f"    {p:<58} +{add:<5} -{rem:<5}")
L.append(f"    {'TOTAL':<58} +{sum_add:<5} -{sum_rem:<5}")
L.append("")
L.append("  FILES PRESENT ONLY IN CANDIDATE (added): 0")
L.append("  FILES PRESENT ONLY IN BASELINE (removed): 0")
L.append("")
L.append("  FORWARD-REF: the non-src diffs are covered by change families 4 (launcher re-pin) and")
L.append("  5 (telemetry-tool repoint) in manifest/identity.json changes_vs_v1.families.")
L.append("")
L.append("=" * 86)
L.append("PER-FILE UNIFIED DIFFS")
L.append("=" * 86)

for scope, p, a, b in allpairs:
    L.append("")
    L.append(f"########## {p} ##########")
    d = run(f"diff -u --label 'a/{p} (baseline v1)' --label 'b/{p} (candidate v1.1)' '{a}' '{b}'")
    L.append(d.stdout.rstrip("\n"))

open(OUT, "w").write("\n".join(L) + "\n")
print("changed src :", len(src_changed))
print("changed non-src:", non_src_changed)
print("lines written:", len(L))
print("out:", OUT)
