Invocation status: done

Evidence: [specialist report](/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s/.memory/g3-baseline-20260907/work/G3-PROTOCOL-FREEZE-20260907.md), SHA-256 `6138fc37ee1fcce2a15cb421b17a00e336f7172ff1ee731a89274201ff3a1b5e`. This was the only file written; no benchmarks, API calls, remote mutations, restarts, or product/MMQ edits occurred.

Open issues include:

- Ratio `0` generates lengths from 1 through the maximum, conflicting with fixed ISL/OSL.
- Three built-in warmups run concurrently outside the C limit.
- Prefill prompt counts are unspecified.
- Client/backend/dataset bindings, performance-server capacity arguments, and telemetry methods remain unresolved.

Follow-up: resolve those choices under a fresh Task ID before dispatching any benchmark.