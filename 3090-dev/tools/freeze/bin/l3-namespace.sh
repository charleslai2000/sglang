#!/usr/bin/env bash
# l3-namespace — allocate or validate a per-run L3 store namespace.
#
# Frozen policy: one task/run -> one unique L3 store namespace
#   SGLANG_HICACHE_EXTENT_BACKEND_STORAGE_DIR=<root>/<SGLANG_RUN_ID>   (root=/data/l3)
# A shared store is NEVER used or cleared by a run: clearing would unlink the
# previous task's WAL segment and destroy concurrent durability evidence.
# This helper refuses:
#   * reserved/shared names          - anything starting with `local-prod-`
#                                      (and shared/default/common/prod/...), e.g.
#                                      /data/l3/local-prod-v1.1 for a new run;
#   * a path that is not exactly <root>/<run-id> (not unique to the run);
#   * a path outside <root>, or any symlinked component;
#   * a pre-existing store with no claim (may belong to another run);
#   * a store claimed by a different run, or by this run without its resume token.
# It has no clear/delete operation, by design.
#
# Exit codes: 0 ok, 2 usage, 3 bad run id, 4 reserved/shared, 5 outside root,
#             6 pre-existing/unallocated store, 7 symlink, 8 claim mismatch,
#             9 not unique to the run.
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL_DIR="$(cd "$SELF_DIR/.." && pwd)"
exec python3 "$TOOL_DIR/pysrc/l3_namespace.py" "$@"
