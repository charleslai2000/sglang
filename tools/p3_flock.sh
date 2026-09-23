#!/usr/bin/env bash
# Common P3 launcher contract: the sole 3090 GPU lock is this exact path.
# Usage: p3_flock.sh COMMAND [ARG ...]
set -u

LOCK=/mnt/data/gpu/3090.lock
if [ "$#" -eq 0 ]; then
  printf 'usage: %s COMMAND [ARG ...]\n' "$0" >&2
  exit 2
fi

exec flock --exclusive --nonblock "$LOCK" "$@"
