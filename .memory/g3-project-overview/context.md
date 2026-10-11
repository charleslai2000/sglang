# G3 baseline context

- Read: repository `AGENTS.md` and `HANDOFF-G3-2026-09-07.md`.
- Confirmed local branch: `sglang-3090-24g-qwen3.8-27b-gsq-rco-iq3_s`; HEAD `dac6db1ebabdb80209b757fd063cf53e05c091e7`.
- Confirmed five intentional P1 files remain modified; `git diff --check` passes.
- Handoff says the IQ3_S v1 baseline was healthy on `175.155.64.171:22109`, port `8035`, PID `298123`, with `/data/qwen3-g3-baseline/` present; prior C1 smoke created no formal JSONL.
- Frozen profile and safety boundaries are authoritative in `AGENTS.md`.
