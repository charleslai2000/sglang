# G3-RUNNER-OOM-DIAG-20260907 — Runner 42.6GB OOM Root Cause

ENTRY: ACCEPT

status: done

## Summary — root cause statement

The deterministic ~42.6GB anonymous-RSS kernel OOM of `python -m sglang.benchmark.serving`
is caused by a **single call**, `serving.py:1902 check_chat_template(args.model)`, which
runs `transformers.AutoConfig.from_pretrained(<11.77GB .gguf path>, trust_remote_code=True)`.
In transformers 5.12.1 that call treats the raw GGUF file as the JSON config file and executes
`configuration_utils.py:888 _dict_from_json_file` → `reader.read()`, which **pre-reads the
entire 11.77GB GGUF into the TextIOWrapper/BufferedReader internal buffers and incrementally
decodes it as UTF-8 before raising UnicodeDecodeError** (the error only surfaces after the
whole-file buffering pass completes). That whole-file buffered read + partially built str in a
process that has already imported torch+transformers+sglang (patches, CUDA init, ~1.1GB baseline)
grows anonymous RSS to ~42.6GB — killing the host's 48GB/0-swap memory and OOM-killing the runner.

The allocating call frame (captured by faulthandler stack dump in a capped faithful run and in a
direct `AutoConfig.from_pretrained` replica):
```
transformers/configuration_utils.py:888 _dict_from_json_file  -> reader.read()
transformers/configuration_utils.py:776 _get_config_dict
transformers/configuration_utils.py:687 get_config_dict
transformers/models/auto/configuration_auto.py:376 from_pretrained
sglang/benchmark/serving.py:1902 check_chat_template
sglang/benchmark/serving.py:2058 run_benchmark
```

`get_tokenizer()` (the sglang GGUF-aware path, which resolves to the sidecar directory and uses
`gguf_file`) is **NOT** the OOM — measured 1.3GB peak standalone. The random-ids dataset loop is
trivial (20x2048 ints). Page-cache double counting is ruled out (dmesg `file-rss:0`). The OOM is
Signed-Off: a real in-process anonymous allocation.

## Causal chain

```
symptom              runner dies rc=137 at anon-rss ~42.6GB (total-vm ~68GB) before any POST /generate
-> triggering        run_benchmark calls check_chat_template(args.model)  [serving.py:2058]
->                   check_chat_template calls AutoTokenizer.from_pretrained(<GGUF path>)  [serving.py:1902]
->                   (AutoConfig) PreTrainedConfig.get_config_dict(<GGUF path>)
->                   _get_config_dict: os.path.isfile(subfolder, path) is True, so
                      resolved_config_file = the 11.77GB GGUF itself; gguf_file is None
->                   _dict_from_json_file(<11.77GB GGUF>) opens it as utf-8 text and calls reader.read()
->                   TextIOWrapper whole-file buffered read grows RSS to 22.4GB even before the
                      UnicodeDecodeError@958 that is deferred until the buffering pass completes
->                   in the sglang process (torch+patches loaded, ~1.1GB base) the same read
                      reaches anon-rss 42646340kB = 42.6GB
-> observed failure  kernel OOM-kills the runner (dmesg: total-vm 68260992kB anon-rss 42646340kB file-rss 0kB)
```

## Evidence (measurements)

| phase | command | peak RSS | result |
|---|---|---|---|
| P0 `import sglang.benchmark.serving` | capped 10GB | 1.10 GB | rc=0, OK |
| P1 `get_tokenizer(<GGUF>)` as runner | capped 10GB | 1.33 GB | rc=0, OK |
| P2 `AutoTokenizer.from_pretrained(<GGUF>, trust_remote_code=True)` replicate | capped 10GB | 0.81 GB | rc=1 (fast MemoryError at the SAME `_dict_from_json_file` read — the 10GB ulimit -v capped the buffered read, which uncapped grows to 22-42GB; same site, cap changed failure mode not location) |
| faithful full runner (run_faithful.py) | watch kill @6GB | reached 6GB | faulthandler stack = `_dict_from_json_file:888 reader.read()` via check_chat_template |
| direct `AutoConfig.from_pretrained(<GGUF>)` (clean, no sglang) | watch kill @6GB | reached 6.3GB | readlog: `read <GGUF> size=11771546784`; stack = same frame |
| same AutoConfig replica (clean) | kernel-OOM | **42.6GB anon** | dmesg PID 380174 |
| clean `f.read()` on full 11.77GB GGUF text-mode | none | **22.4GB RSS / 33.7GB VmPeak** | UnicodeDecodeError@958 after 24.6s |
| clean `f.read()` on 1GB slice | none | 2.06 GB | ratio ~2x file size |
| clean `f.read()` on 512MB slice | none | 1.04 GB | ratio ~2x |

Key numbers:
- GGUF file size: 11,771,546,784 bytes (11.77GB)
- text-mode `read()` of the full file: peak RSS 22.4GB, VmPeak 33.7GB, error deferred 24.6s
- observed runner OOM: anon-rss 42,646,340kB, total-vm 68,260,992kB, pgtables 86,252kB
- pgtables 86MB ≈ 11M pages ≈ consistent with a bulk anonymous allocation, not a mapping artifact

## Alternatives rejected (with reason)

1. get_tokenizer / tokenizer call — DISPROVEN: standalone 1.33GB, service uses the same and runs at 3.5GB total.
2. random-ids dataset build — DISPROVEN: loop is 20 x 2048 ints; also the runner dies BEFORE the dataset log line.
3. torch/tensor import-time allocation — DISPROVEN: `import sglang.benchmark.serving` (which imports torch) peaks 1.1GB.
4. Page/zone or file-cache double-counting — DISPROVEN: dmesg file-rss=0; the allocation is anon.
5. `check_chat_template` NOT involved — DISPROVEN: get_tokenizer is GGUF-aware (sidecar), but check_chat_template is NOT; the stack and readlog prove it reads the GGUF as config.

## Why prior attempts did not resolve it

The prior executor's abort protocol correctly halted on >8GB RSS, but the runner source reading
("check_chat_template just loads a tokenizer config") and the memory-light `get_tokenizer` dry-check
were insufficient: the failing call is `AutoTokenizer` (not `get_tokenizer`) on the GGUF path, and
it fails only in the FULL `-m sglang.benchmark.serving` process because of import-state + CUDA +
the transformers GGUF single-file special case. The `--tokenizer` flag never fixes it (check_chat_template
always uses `args.model`); hence all three invocation variants (no tokenizer / with tokenizer /
random-ids) OOM identically.

## Minimal fix directions (NOT implemented — require decision)

All three share the invariant: **the raw GGUF must never be passed to plain `AutoTokenizer.from_pretrained`**
as the model path by the runner.

1. **Use the sidecar dir instead of the GGUF file for check_chat_template (byte-identical-safe)**
   In `serving.py check_chat_template`, when the model path is a `.gguf`, pass the parent directory
   (`/data/models/.../GGUF/`) which contains config.json/tokenizer.json/chat_template.jinja. This loads
   only the real config. Zero invocation change. This is the smallest code change, but it IS a runner
   source modification — requires authorization (no source edits authorized in this dispatch).

2. **Change invocation: host a sidecar tokenizer dir / use --tokenizer (compat_note needed)**
   e.g. create `/data/models/Qwen3.8-27B-GSQ-RCO-GGUF-sidecar` (copy config.json + tokenizer files) and
   run `--model <GGUF> --tokenizer <sidecar-dir>`. But check_chat_template still uses `--model`, so this
   does NOT avoid the blowup unless --model is ALSO the sidecar dir. So a compliant variant is:
   `--model /data/models/.../GGUF/ --tokenizer <same dir>` — but the frozen protocol wants the GGUF model
   path. This is a flag change → needs explicit decision + compat_note.

3. **Host mem/swap remedy**: add swap or lower concurrency so 22-42GB transient fits. Does not change
   invocation. Risk: 48GB host, resident service uses 3.5GB + 22.8GB VRAM; a 22-42GB transient read is
   extremely likely to destabilize the service even with more free RAM — not recommended.

4. **Runner-equivalent minimal client**: bypass the OOM path by not invoking `-m sglang.benchmark.serving`;
   write a small client replicating the HTTP interaction (loads + generate) with the sidecar-light tokenizer.
   Byte-identical to the protocol only if the tokenizer/length semantics and request bytes match. Requires
   decision; also changes deployment (a separate helper), so it needs a compat_note too.

Recommended: Option 1 (or 2 with the sidecar dir as --model) — smallest change, keeps frozen command
semantics; needs an explicit authorization since it edits the runner.

## Service/health verification

- PID 298123 remained alive throughout, /health=200, RSS 220MB idle, GPU 0% util, VRAM 22802MiB unchanged.
- Frozen cmdline hash `tr '\0' ' ' < /proc/298123/cmdline | sha256sum` = 7832781e755152... (exact match to snapshot).
- Zero stray subprocesses after cleanup.

## Artifacts (remote)

- /data/qwen3-g3-baseline/g3-runner-oom-diag-20260907/probe-readlog.txt  (the smoking gun)
- /data/qwen3-g3-baseline/g3-runner-oom-diag-20260907/probe.stderr.txt   (fault stack)
- /data/qwen3-g3-baseline/g3-runner-oom-diag-20260907/probe-rss.log     (RSS trajectory)
- /data/qwen3-g3-baseline/g3-runner-oom-diag-20260907/f1-runner.stderr.txt (faithful runner stack)
- /data/qwen3-g3-baseline/g3-runner-oom-diag-20260907/verify-autoconfig.stderr.txt
- /data/qwen3-g3-baseline/g3-runner-oom-diag-20260907/p0-peak.txt, p1-peak.txt
- diag scripts in /tmp/g3-diag/*.py, watch_rss.py

## Followups
- Decision needed on which remediation (1/2/3/4) to authorize; each tagged byte-identical vs invocation vs host change above.
- After decision, a fresh RUN_ID under /data/qwen3-g3-baseline/prod-a/ for Production-A rerun.

## Open issues
- The 42.6 versus 22.4GB exact delta is environmental (imported torch/CUDA/patches in the same process). Root allocating site is proven regardless.
- The prior "23GB at 1GB file" reading was an artifact of a contaminated harness (copy-in-interpreter); the clean sweep (256/512/768/1024MB → ~2x) is authoritative.
