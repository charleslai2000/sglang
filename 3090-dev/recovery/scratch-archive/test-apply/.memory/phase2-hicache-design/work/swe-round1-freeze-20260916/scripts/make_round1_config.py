#!/usr/bin/env python3
"""Generate the frozen Round-1 config from the pinned official SWE-bench config.

Base = minisweagent 2.4.6 ``config/benchmarks/swebench.yaml`` (byte-identical copy
kept as ``config/official-swebench-config.yaml``).

The transformation is a strictly-checked textual replacement so every byte of the
official agent/environment templates is preserved. Only the model transport block
and the local-cost handling are changed:

  * model.model_name        -> placeholder, overridden per model (allowed diff (b))
  * model.model_kwargs.api_base/api_key -> local OpenAI-compatible endpoint
                               (allowed diff (a), per-model overridable)
  * model.model_kwargs.reasoning_effort -> "medium" (owner-fixed reasoning policy)
  * model.cost_tracking     -> ignore_errors (local endpoints are not in LiteLLM's
                               price registry; global, identical for all models)
  * agent.cost_limit        -> 0 (global, identical for all models; replaces the
                               meaningless USD limit for local endpoints)

Every replacement must match exactly once or the script fails (fail closed).
"""

import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = ROOT / "config" / "official-swebench-config.yaml"
DST = ROOT / "config" / "round1-swebench-local.yaml"

REPL = [
    (
        "  model_name: \"anthropic/claude-sonnet-4-5-20250929\"\n"
        "  model_kwargs:\n"
        "    drop_params: true\n"
        "    parallel_tool_calls: true\n",
        "  model_name: \"openai/LOCAL_MODEL\"  # per-model override (allowed diff b)\n"
        "  cost_tracking: ignore_errors  # local endpoint: not in LiteLLM price registry\n"
        "  model_kwargs:\n"
        "    drop_params: true\n"
        "    parallel_tool_calls: true\n"
        "    api_base: \"http://127.0.0.1:30000/v1\"  # per-model override (allowed diff a)\n"
        "    api_key: \"EMPTY\"  # local OpenAI-compatible endpoint\n"
        "    reasoning_effort: \"medium\"  # owner-fixed reasoning policy (Round 1)\n",
    ),
    (
        "  cost_limit: 3.\n",
        "  cost_limit: 0.\n",
    ),
]


def main():
    text = SRC.read_text(encoding="utf-8")
    for old, new in REPL:
        n = text.count(old)
        if n != 1:
            sys.exit(f"FAIL-CLOSED: expected exactly 1 occurrence, found {n} for:\n{old!r}")
        text = text.replace(old, new)
    DST.write_text(text, encoding="utf-8")
    print("wrote", DST)
    print("official sha256", hashlib.sha256(SRC.read_bytes()).hexdigest())
    print("round1   sha256", hashlib.sha256(DST.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
