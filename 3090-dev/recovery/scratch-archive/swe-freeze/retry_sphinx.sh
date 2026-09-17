#!/usr/bin/env bash
REF="ghcr.io/epoch-research/swe-bench.eval.x86_64.sphinx-doc__sphinx-9320:latest"
for i in $(seq 1 40); do
  echo "[$(date +%H:%M:%S)] attempt $i"
  if timeout 150 docker pull "$REF" 2>&1 | tail -2; then
    if docker image inspect "$REF" >/dev/null 2>&1; then
      echo "[$(date +%H:%M:%S)] SUCCESS attempt $i"
      exit 0
    fi
  fi
  echo "[$(date +%H:%M:%S)] attempt $i ended without image"
done
echo "GAVE_UP"
exit 1
