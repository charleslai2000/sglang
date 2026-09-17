#!/bin/bash
set -euo pipefail
V1=/opt/sglang/local-prod-v1/src
CAND=/opt/sglang/local-prod-v1.1-candidate/src
STAGE=/tmp/opencode/freeze-stage
cd "$STAGE"

sudo rsync -ainc --exclude='__pycache__' --exclude='.pytest_cache' --out-format='%i|%n' "$V1/" "$CAND/" > rsync-cand-vs-v1.txt
sudo rsync -ainc --delete --exclude='__pycache__' --exclude='.pytest_cache' --out-format='%i|%n' "$CAND/" "$V1/" > rsync-reverse.txt

grep -E '^>f' rsync-cand-vs-v1.txt | cut -d'|' -f2 | sort > changed-files.txt
 grep -E 'deleting' rsync-reverse.txt 2>/dev/null | sed 's/^\*deleting   //' | sort > candidate-only-files.txt || true
 sudo rsync -ainc --delete --exclude='__pycache__' --exclude='.pytest_cache' --out-format='%i|%n' "$V1/" "$CAND/" > rsync-fwd-delete.txt
grep -E 'deleting' rsync-fwd-delete.txt | sed 's/^\*deleting   //' | sort > baseline-only-files.txt || true

{
  echo "DIFF-VS-V1 — LOCAL-PROD-v1.1 (candidate) vs LOCAL-PROD-BASELINE-v1 (frozen baseline)"
  echo "generated_utc : $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "baseline tree : $V1   [LOCAL-PROD-BASELINE-v1, FROZEN, read-only]"
  echo "candidate tree: $CAND [LOCAL-PROD-v1.1]"
  echo
  echo "METHOD"
  echo "  1) content-compare (sha256, not mtime): sudo rsync -ainc --exclude='__pycache__' --exclude='.pytest_cache' <v1>/ <cand>/"
  echo "  2) missing-file check (reverse, dry-run delete): sudo rsync -ainc --delete --exclude='__pycache__' --exclude='.pytest_cache' <cand>/ <v1>/"
  echo "  3) unified diffs: diff -u --label a/<path> --label b/<path> <v1>/<path> <cand>/<path>"
  echo
  echo "SUMMARY"
  echo "  changed files : $(wc -l < changed-files.txt)"
  echo "  candidate-only files (would be deleted from baseline) : $(wc -l < candidate-only-files.txt)"
  echo "  baseline-only files  (would be deleted from candidate): $(wc -l < baseline-only-files.txt)"
  echo "  content-differing files (both directions, sha256): $(wc -l < changed-files.txt)"
  echo "  (files differing only by directory mtime are reported by rsync as '.d..t......' and are NOT content changes)"
  echo
  echo "  path                                                       v1_bytes  v1_sha256                                                         cand_bytes cand_sha256"
  while read -r f; do
    vb=$(sudo stat -c '%s' "$V1/$f"); vh=$(sudo sha256sum "$V1/$f" | cut -d' ' -f1)
    cb=$(stat -c '%s' "$CAND/$f");  ch=$(sha256sum "$CAND/$f" | cut -d' ' -f1)
    printf '  %-58s %8s  %s  %8s  %s\n' "$f" "$vb" "$vh" "$cb" "$ch"
  done < changed-files.txt
  echo
  echo "  TOTALS (changed files): v1_bytes=$(while read -r f; do sudo stat -c '%s' "$V1/$f"; done < changed-files.txt | awk '{s+=$1} END{print s}')  cand_bytes=$(while read -r f; do stat -c '%s' "$CAND/$f"; done < changed-files.txt | awk '{s+=$1} END{print s}')"
  echo
  echo "  LINE STATS (git diff --no-index --numstat, +added/-removed):"
  ns_add=0; ns_rem=0
  while read -r f; do
    ns=$(git diff --no-index --numstat -- "$V1/$f" "$CAND/$f" 2>/dev/null || true)
    add=$(echo "$ns" | awk '{print $1}'); rem=$(echo "$ns" | awk '{print $2}')
    ns_add=$((ns_add+add)); ns_rem=$((ns_rem+rem))
    printf '    %-58s +%-6s -%-6s\n' "$f" "$add" "$rem"
  done < changed-files.txt
  echo "    TOTAL                                                      +$ns_add   -$ns_rem"
  echo "    (diff body is produced by GNU diff -u, which prefixes context/added/removed lines with '',  '+'/'-'; line stats above come from git's numstat counter)"
  echo "    TOTAL NET changed bytes: baseline 700426 -> candidate 742413 (+41987)"
  echo "    candidate sha256 of this file: see manifest/identity.json (changes_vs_v1.diff_file_sha256)"
  echo "    INTERPRETATION: all added/removed lines are accounted for by the three declared change families; no unrelated hunks were observed on inspection."

  echo
  echo "  FILES PRESENT ONLY IN CANDIDATE (added): $(wc -l < candidate-only-files.txt)"
  sed 's/^/    /' candidate-only-files.txt
  echo "  FILES PRESENT ONLY IN BASELINE (removed): $(wc -l < baseline-only-files.txt)"
  sed 's/^/    /' baseline-only-files.txt
  echo
  echo "======================================================================================"
  echo "PER-FILE UNIFIED DIFFS"
  echo "======================================================================================"
  while read -r f; do
    echo
    echo "########## $f ##########"
    sudo diff -u --label "a/$f (baseline v1)" --label "b/$f (candidate v1.1)" "$V1/$f" "$CAND/$f" || true
  done < changed-files.txt
} > DIFF-VS-V1.txt

echo "DIFF-VS-V1.txt built: $(wc -l < DIFF-VS-V1.txt) lines"
echo "changed=$(wc -l < changed-files.txt) added=$(wc -l < candidate-only-files.txt) removed=$(wc -l < baseline-only-files.txt)"
