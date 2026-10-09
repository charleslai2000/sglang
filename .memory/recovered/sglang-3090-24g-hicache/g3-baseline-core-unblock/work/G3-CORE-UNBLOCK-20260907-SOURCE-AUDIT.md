# G3-CORE-UNBLOCK-20260907-SOURCE-AUDIT

ENTRY: ACCEPT

invocation_status: done
task_id: G3-CORE-UNBLOCK-20260907-SOURCE-AUDIT
epoch: E3
role: scout

## Scope and baseline

Read-only local audit only. No SSH, benchmark/API request, source edit, or remote
operation was performed. Repository root is
`/home/dev-codex/workspaces/3rdparty/sglang-qwen3-27b-iq3s`. The applicable root
`AGENTS.md` confirms the experimental host is `175.155.64.171:22109`, production
hosts/VM901 are out of scope, and the frozen v1 profile must not change.

Observed git state:

- `HEAD`: `dac6db1ebabdb80209b757fd063cf53e05c091e7`.
- Worktree is dirty with pre-existing changes in `python/sglang/benchmark/serving.py`,
  OpenAI protocol/serving files, sampling files/tests, plus untracked handoff and
  `.memory` material. No changes were made by this audit.
- Current local `python/sglang/benchmark/serving.py` SHA-256 is
  `01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb`.
  Preserved settle report says this file was byte-identical to the deployed source
  during its read-only check: `.memory/g3-baseline-20260907/work/
  G3-RUNNER-OOM-FIX-SETTLE-20260907.md` lines 1-8.
- Current `git diff --check` is clean. `git diff --stat` shows the serving change is
  a 15-line `check_chat_template` guard; unrelated dirty files are preserved.

## Dataset semantics and exact-length path

`python/sglang/benchmark/datasets/__init__.py:18-27` maps both `random` and
`random-ids` to `RandomDataset`, while `random-ids` selects the non-ShareGPT branch
through `RandomDataset.from_args` at `python/sglang/benchmark/datasets/random.py:30-40`:

- `return_text = not args.tokenize_prompt`.
- `random_sample = (args.dataset_name == "random")`, therefore `random-ids` is
  `False` and cannot enter the ShareGPT branch.

`random.py:67-76` computes input and output lengths with `compute_random_lens`.
At `random_range_ratio=1.0`, the randint lower bound equals `full_len` and upper
bound is exclusive `full_len+1` (implementation in
`python/sglang/benchmark/datasets/common.py`), so every request is exactly ISL/OSL.
The `random_sample=True` branch at `random.py:84-93` would validate a local JSON
and otherwise call `download_and_cache_hf_file` for ShareGPT; that branch is not
selected by `random-ids`. The integer branch at `random.py:145+` constructs Python
`int` token IDs and only decodes them when `return_text` is true. With
`--tokenize-prompt`, it remains a list of integer IDs.

The native request path is proven by `python/sglang/benchmark/serving.py:657-681`:

- `--backend sglang` selects `async_request_sglang_generate` and its `/generate`
  API path (`serving.py:657-673` and `_BACKEND_API_PATHS` near line 940).
- If the prompt is a list (the `random-ids` + tokenize path), payload key is
  `input_ids`, not `text` (`serving.py:672-675`). Thus the server receives the
  exact generated list length, independent of decode/re-tokenization.
- Sampling payload keeps `max_new_tokens`, `ignore_eos`, and stream defaults
  (`serving.py:665-675`). Omitting negative disable flags leaves streaming and
  ignore-EOS enabled.
- HTTP 200 is treated as success and non-200/error is captured in the output
  (`serving.py:705-778`). Completion count and runner-side input length are
  retained in result details; metrics use each `DatasetRow.prompt_len`.

`--tokenize-prompt` is explicitly documented as integer-ID input at
`serving.py:2619-2623`, and `run_benchmark` rejects it unless backend is exactly
`sglang` at `serving.py:2008-2011`. This matches the E3 native-backend requirement.

## GGUF/client guard and prior failure evidence

The current local serving diff at `serving.py:1900-1918` handles a single-file
GGUF before `AutoTokenizer.from_pretrained`: it checks for tokenizer sidecars in
the parent directory, returns `False` without loading if absent, and otherwise
passes the parent directory rather than the GGUF file. This is the relevant guard
against benchmark-side GGUF parsing.

The normal tokenizer path is separately visible at `serving.py:2103-2121`:
`/model_info` supplies `tokenizer_path` or `model_path`, then `get_tokenizer` is
called. `python/sglang/benchmark/utils.py:44-61` routes `.gguf` paths through
SGLang's GGUF-aware tokenizer helper; it does not call the serving guard's plain
`AutoTokenizer` path. The E3 smoke should still capture the client command, PID,
RSS, and open/network activity as evidence rather than infer safety solely from
source.

Preserved evidence documents the former failure and its settlement:

- `G3-PRODUCTION-A-EXEC-20260907.md` reports prior C1 attempts were killed at
  rc=137 before any POST /generate, with about 42.6 GB anonymous RSS.
- `G3-RUNNER-OOM-DIAG-20260907.md` attributes that to the old
  `check_chat_template(args.model)` path reading the raw GGUF as JSON/config.
- `G3-RUNNER-OOM-FIX-SETTLE-20260907.md` records the current serving hash,
  byte identity to deployed source, a real GGUF check under an 8 GiB cap with
  1.428 GiB peak RSS, and no benchmark request during that check.

These are preserved reports, not a substitute for the E3 smoke gate.

## Warmup and flush ordering

`serving.py:1353-1464` implements warmup before measurement. It constructs the
first request, runs `warmup_requests`, requires at least one successful warmup,
then calls `flush_server_cache` when `--flush-cache` is set. For SGLang,
`flush_server_cache` posts `/flush_cache?timeout=<value>` (`serving.py:977-995`).
The parser exposes `--flush-cache`, `--flush-cache-timeout`, and
`--warmup-requests` at `serving.py:2602-2617`. Therefore every formal repeat must
use `--warmup-requests 3 --flush-cache`; the runner itself performs warmup then
flush once per invocation. A wrapper must invoke each repeat independently and
not rely on retained cache between repeats.

## Smoke command candidate

The following is a command candidate for the authorized remote executor. It is
not executed by this scout. It uses the deployed interpreter/source binding and
native SGLang endpoint, one exact 2048/512 request, no `--tokenizer`, no ShareGPT,
and no client-side model loading intent beyond tokenizer sidecar resolution:

```text
cd /data/sglang-qwen35 && \
PYTHONUNBUFFERED=1 /data/sglang-qwen35-env/bin/python -m sglang.benchmark.serving \
  --backend sglang --base-url http://127.0.0.1:8035 \
  --model /data/models/Qwen3.8-27B-GSQ-RCO-GGUF/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --dataset-name random-ids --random-input-len 2048 --random-output-len 512 \
  --random-range-ratio 1.0 --request-rate inf --seed 42 \
  --max-concurrency 1 --num-prompts 1 --tokenize-prompt \
  --output-details --output-file <SMOKE_DIR>/result.jsonl \
  --flush-cache --flush-cache-timeout 60 --warmup-requests 0
```

`--warmup-requests 0` makes the smoke's single request the measured request. If
the executor chooses to establish kernel warmup first, it must record a separate
pre-smoke invocation and then run this one-request gate with the same dataset
binding. Formal runs should use the frozen C1/C4/C5 and performance-only
C1/C4/C8/C16 matrices plus prefill 2K/8K/32K × OSL32, each with 3 repeats and
flush before every measured repeat.

## Gate evidence recommendations and limits

The source proves intended behavior but cannot prove runtime gates. The executor
should preserve:

1. Client no-GGUF-load: command/PID, `/proc/<pid>/cmdline`, RSS samples, and
   client stderr/stdout. The current guard plus `--model <GGUF>` must be checked
   against the deployed file hash.
2. Small/stable client RSS: sample `/proc/<pid>/status` or `ps` at startup,
   dataset creation, and after completion; retain peak and timestamps.
3. No network/dataset download: capture runner logs plus a scoped network trace
   or `/proc/<pid>/fd`/socket evidence during the short smoke. Source evidence
   alone establishes that `random-ids` avoids the ShareGPT branch, but not that
   unrelated tokenizer resolution did not attempt network access.
4. Exact input length: retain raw `runner.stdout` (`#Input tokens`), the
   `result.jsonl` input lengths, and server-side request evidence. The native
   payload is `input_ids` at `serving.py:672-675`; server logs/access traces or
   an authorized request-capture mechanism are needed to establish what the
   server actually received. `/v1/loads?include=all` is aggregate and cannot by
   itself prove per-request input length.
5. Successful completion: require one JSON result with `completed=1`, no errors,
   HTTP 200, and nonzero output; preserve status/error fields even on failure.

Known telemetry limitation from the preserved runbook: `/metrics` is unavailable
on the host, so `/v1/loads?include=all`, runner output, GPU dmon/query samples,
and server logs are the available evidence sources. HiCache fields remain N/A per
the task policy.

## Open issues

- The source audit cannot establish actual deployed `serving.py` identity or
  runtime behavior without the authorized remote smoke; the settle report is the
  latest preserved identity evidence.
- Exact server input length requires server-side access/log evidence; runner-side
  `prompt_len` and payload construction are necessary but not sufficient.
- Client no-network requires runtime observation in addition to the static branch
  proof.
- No product files, benchmark artifacts, ledger, plan, or context files were
  modified by this invocation.

followups: remote devops-executor may run the smoke gate under its fresh Task ID;
formal matrices remain downstream of all five smoke gates passing.
