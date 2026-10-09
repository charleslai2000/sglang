# G3-E3-SMOKE-VERIFY-20260907

ENTRY: ACCEPT

status: done
task_id: G3-E3-SMOKE-VERIFY-20260907
orchestration_epoch: E3
role: tester
invocation_status: done

## Scope and method

Read-only independent verification of the native smoke report and its preserved
raw subtree. No benchmark request, remote state change, product edit, audit or
tracing mechanism, or additional workload was used. The authoritative inputs
were:

- `.memory/g3-baseline-20260907/work/G3-E3-SMOKE-NATIVE-20260907.md`
- `.memory/g3-baseline-20260907/work/raw/g3-e3-smoke-native-20260907T143437Z/`
- `.memory/g3-baseline-20260907/work/G3-CORE-UNBLOCK-20260907-SOURCE-AUDIT.md`
- `.memory/g3-baseline-20260907/work/G3-E3-SMOKE-RUNBOOK-20260907.md`

## Five-gate disposition

1. **No client GGUF load/parse: PASS (observational).**
   `command.txt` uses native `--backend sglang`, an explicit tokenizer sidecar
   (`--tokenizer /data/models/Qwen3.8-27B-GSQ-RCO-GGUF`), and no audit/preload/
   interposer flags. `client_status_samples.txt` is nonempty and peaks at
   `1,498,280 kB`, below the 4 GiB bound. The source-audit branch evidence and
   the deployed serving-source identity support tokenizer-sidecar operation.
   There is no kernel-level open trace in this uninstrumented run; this is an
   observational PASS, not proof from syscall tracing.

2. **Small/stable RSS: PASS.**
   The 38 one-second samples in `client_status_samples.txt` rise to the peak
   above, then remain at `1,450,272 kB` from 14:34:59Z through 14:35:21Z;
   final samples fall to `1,357,156 kB` (the recorded last value). The
   post-dataset completion values
   are within 256 MiB of the stable plateau and show no unbounded growth.

3. **No network/dataset download: PASS (observational).**
   `environment.txt` sets `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`,
   loopback `NO_PROXY/no_proxy`, and unsets HTTP/HTTPS/ALL proxy variables.
   `preflight_connections.txt` and `postflight_connections.txt` are identical:
   the existing SSH/agent links and SGLang loopback scheduler pair only; no
   benchmark client external connection appears. The command selects
   `random-ids`, not ShareGPT, and contains no ShareGPT flags. Within the
   timestamp-delimited smoke interval in `server_log_post_tail.txt`, there is
   one flush, one generate, and the expected local status/metadata GETs. No
   download marker is present. The shared-log tails include surrounding
   pre/post health activity, so exact byte-range isolation is not claimed.

4. **Exact server input: PASS.**
   `result.jsonl` contains exactly one JSON object and independently parses as:
   `completed=1`, `input_lens=[2048]`, `output_lens=[512]`, `error=null`,
   `total_input_tokens=2048`, and `total_output_tokens=512`. The delimited
   server evidence has exactly one smoke `Prefill batch` line with
   `#new-seq: 1, #new-token: 2048, #cached-token: 0`, at
   `server_log_post_tail.txt` line 282. The one flush is at line 280 and the
   one successful `/generate` is at line 281.

5. **One successful request/service invariant: PASS.**
   `client.exit` is `0`; the delimited log has exactly one `POST /generate ...
   200 OK` and no error/timeout/zero-progress marker. Pre/post service command
   line text is byte-identical, both recorded command-line hashes are
   `7832781e755152980cc32aafb518117a97cdfa0b08facd0f3611bd2c2b58e9bf`, and
   both process snapshots retain PID `298123`, model path, frozen parser/tool
   parser/KV/Mamba/template arguments, and port 8035. Pre/post health status is
   200; pre/post loads are idle with zero running/waiting/used/total tokens and
   the same memory/capacity fields. Pre/post model identity paths are the same.

## Exact command checks

`command.txt` contains all required workload controls: native SGLang, loopback
8035, `random-ids`, ISL 2048, OSL 512, ratio 1.0, seed 42, C1 (`--max-concurrency
1`), one prompt, `--tokenize-prompt`, `--output-details`, explicit tokenizer,
`--flush-cache --flush-cache-timeout 60`, and `--warmup-requests 0`. ShareGPT
dataset/length flags and `--disable-stream`/`--disable-ignore-eos` are absent.
The runner stdout also records `disable_stream=False` and
`disable_ignore_eos=False`.

## Artifact integrity

**PARTIAL / INCOMPLETE, not a content mismatch.** The raw subtree contains 50
files but no `SHA256SUMS` manifest. `source_serving.py.sha256` is itself a
failed lookup for `/data/sglang-qwen35/sglang/benchmark/serving.py`; the
correctly addressed `source_serving_paths.sha256` records
`01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb`, which
matches local `python/sglang/benchmark/serving.py`. Pre/post command-line hash
records agree with each other, and pre/post command-line text is identical.
This is an evidence-packaging limitation to preserve in downstream records,
not a failed runtime gate.

## Blocking findings and go/no-go

No blocking runtime finding: all five requested gates PASS on the preserved
native smoke. Formal Production A is **GO from the five-gate smoke admission**,
with the artifact-integrity limitation above carried forward explicitly. Do
not describe this report as a complete SHA256SUMS verification; regenerate a
manifest in the formal-run artifact pack if a complete manifest is required.

## Evidence paths

- Command/result: `.../raw/g3-e3-smoke-native-20260907T143437Z/command.txt`,
  `result.jsonl`, `client.exit`, `client.stdout`, `client.stderr`
- RSS/process: `client_status_samples.txt`, `client_ps_samples.txt`,
  `client_observed_times.txt`, `client_ps_initial.txt`
- Offline/connections: `environment.txt`, `preflight_connections.txt`,
  `postflight_connections.txt`, `preflight_listener.txt`,
  `postflight_listener.txt`
- Server correlation: `server_log_post_tail.txt` (lines 280–282 for flush,
  generate, exact prefill), `server_log_pre_tail.txt`
- Service invariant: `preflight_service_ps.txt`, `postflight_service_ps.txt`,
  `preflight_service_cmdline.txt`, `postflight_service_cmdline.txt`, their
  `.sha256` files, `pre/postflight_health.status`, `pre/postflight_loads.json`,
  and `pre/postflight_models.json`
- Source identity: `source_serving_paths.sha256`,
  `source_serving.py.sha256`, `sglang_identity.txt`

## Followups

Carry the missing/failed-path checksum evidence as an open artifact-packaging
issue and keep the benign `resource_tracker` traceback in downstream records;
it did not alter exit status or completion. No further smoke work is needed for
this Task ID. Extra work requires a fresh Task ID.

open_issues:
- Native raw subtree lacks `SHA256SUMS`; one redundant source-hash file records
  a wrong deployed path. Runtime gate results remain PASS, but integrity status
  is partial.
- Shared server-log tails are observationally delimited rather than a copied
  byte-range delta.
- RSS is client process RSS, not GPU memory.

artifacts:
- `.memory/g3-baseline-20260907/work/G3-E3-SMOKE-VERIFY-20260907.md`
