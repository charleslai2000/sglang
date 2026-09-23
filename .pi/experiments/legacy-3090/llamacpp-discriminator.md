# llama.cpp neutrality control (`llama.cpp` discriminator)

Status: **BUILT AND READY (CPU-only).** Not run against the gate yet, by design:
the discriminator is conditional on an SGLang sampled-arm failure.

## Purpose

Decide whether an SGLang repetition loop under the frozen sampled contract is a
**model/quantization** behavior or a **narrowly scoped SGLang GGUF residual**:

| observation | conclusion |
|---|---|
| llama.cpp *also* loops | model/quantization behavior — **not** an SGLang correctness blocker |
| llama.cpp coherent, SGLang loops | narrowly scoped SGLang GGUF residual investigation |
| llama.cpp fails to load | infrastructure problem, no verdict either way |

It is a neutral control: it must not share SGLang's GGUF loader, kernels, or
sampling implementation. A **CPU-only** build is therefore preferred — it is
fully independent of the GPU, needs no VRAM, and cannot contend with the
128K-C8 M1 profile work.

## Build record

| field | value |
|---|---|
| repo | `https://github.com/ggml-org/llama.cpp` |
| commit | `b49650adb31f2e49a0d76113aeb1792134fd8413` (2026-09-17T11:53:54Z) |
| commit subject | `model : skip gate_up_exps if TENSOR_SKIP is set (#29014)` |
| clone dir | `/mnt/data/nerun-dev/llamacpp-discriminator-20260917/llama.cpp` |
| build dir | `/mnt/data/nerun-dev/llamacpp-discriminator-20260917/llama.cpp/build-cpu` |
| binary | `/mnt/data/nerun-dev/llamacpp-discriminator-20260917/llama.cpp/build-cpu/bin/llama-cli` |
| bin sha256 | `845cb1db74eeb583616dda0bffd0dc1b3d332c40c342d950245a60d0754abfac` |
| version | `version: 0.4.1-dev (build 11026, commit b49650adb)` / GNU 13.3.0 / Linux x86_64 |
| devices | `Available devices: (none)` — no CUDA libs linked (`ldd` has no `cuda`/`nvidia`) |

Configure + build command (cmake from the venv because it is not on `PATH`):

```bash
CM=/home/ubuntu/venv/lib/python3.12/site-packages/cmake/data/bin/cmake
cd /mnt/data/nerun-dev/llamacpp-discriminator-20260917/llama.cpp
"$CM" -B build-cpu -G Ninja -DCMAKE_BUILD_TYPE=Release \
   -DGGML_CUDA=OFF -DGGML_METAL=OFF -DGGML_VULKAN=OFF -DGGML_SYCL=OFF \
   -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=ON \
   -DLLAMA_BUILD_SERVER=ON -DGGML_NATIVE=ON
"$CM" --build build-cpu --config Release -j 24     # rc=0
```

Network note: `git clone` over the proxy is flaky (`gnutls_handshake() failed`),
but it succeeded on a bounded retry loop. `api.github.com` and
`git ls-remote` were reachable; `codeload.github.com` was not. The clone worked,
which is all the build needed — no tarball fallback was required.

### Why this commit is adequate

The `qwen35` architecture is present in this commit:

```
src/llama-arch.h:46      LLM_ARCH_QWEN35
src/llama-arch.cpp:41    { LLM_ARCH_QWEN35, "qwen35" }
src/llama-model.cpp:326  return new llama_model_qwen35(params);
```

and llama.cpp reads the same `general.sampling.*` metadata the gate uses
(`common/common.cpp:1267` maps `general.sampling.penalty_repeat` and friends
into `common_params_sampling`). So the discriminator can be given an
**equivalent** contract rather than an approximation.

## Exact discriminator invocation (ready to run later)

**Preferred form: `llama-server` + the identical JSON body.** This was verified
working: llama.cpp's OpenAI-compatible endpoint accepts the *same* request body
the gate sends, so the comparison isolates the engine rather than the harness.
`llama-cli` is the fallback if a server is undesirable.

### Preferred: llama-server (verified working)

```bash
R=/mnt/data/nerun-dev/llamacpp-discriminator-20260917
BIN=$R/llama.cpp/build-cpu/bin/llama-server
PORT=30166                      # experiment port; NEVER 30000

# 1. start the CPU-only control server (one model at a time)
"$BIN" -m /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
   --host 127.0.0.1 --port "$PORT" -t 16 -c 8192 --jinja \
   > "$R/llamaserver_m3.log" 2>&1 &
# wait for {"status":"ok"} on /health

# 2. send the SAME gate contract, /v1/chat/completions, non-streaming
curl -sS -m 3600 -X POST "http://127.0.0.1:$PORT/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d '{"model":"default","messages":[{"role":"user","content":"<gate prompt>"}],
       "temperature":1.0,"top_p":0.95,"top_k":20,"min_p":0.0,
       "repetition_penalty":1.0,"seed":20260916,"max_tokens":640,
       "chat_template_kwargs":{"enable_thinking":false}}' \
  > "$R/m3_llamacpp_sampled.json"

# 3. score with the gate's OWN metric (identical word-level 4-gram)
$R/score_llamacpp_server_reply.py "$R/m3_llamacpp_sampled.json"

# 4. repeat with the M4 control GGUF, then stop the server
```

For M4 the body is identical; only the GGUF differs. The `-c 8192` context is
the M4 gate value; use `-c 16384` for M3 to match its gate launch spec.

### Fallback: llama-cli (single process, no server)

```bash
BIN=/mnt/data/nerun-dev/llamacpp-discriminator-20260917/llama.cpp/build-cpu/bin/llama-cli
cd /mnt/data/nerun-dev/llamacpp-discriminator-20260917
"$BIN" \
  -m /data/models/Qwen3.8-27B-GSQ-RCO-IQ3_S.gguf \
  --jinja -st -t 16 -n 640 -s 20260916 \
  -p 'Write a Python function that parses a CSV file and returns a dict of column sums, where each value is the sum of the numeric values in that column. Include a docstring and handle missing values by skipping them.' \
  --chat-template-kwargs '{"enable_thinking":false}' \
  --temp 1.0 --top-p 0.95 --top-k 20 --min-p 0.0 --repeat-penalty 1.0 \
  > m3_llamacpp.out 2>&1
```

Equivalent-sampling mapping (SGLang request field -> llama.cpp flag):

| contract field | SGLang body | llama.cpp flag |
|---|---|---|
| `temperature` | `1.0` | `--temp 1.0` |
| `top_p` | `0.95` | `--top-p 0.95` |
| `top_k` | `20` | `--top-k 20` |
| `min_p` | `0.0` | `--min-p 0.0` |
| `seed` | `20260916` | `-s 20260916` |
| `max_tokens` | `640` | `-n 640` |
| `penalty_repeat` (M4) | `repetition_penalty: 1.0` | `--repeat-penalty 1.0` |
| `enable_thinking=false` | `chat_template_kwargs` | `--chat-template-kwargs '{"enable_thinking":false}'` |

`--jinja` renders the GGUF's own embedded chat template; `-st` is single-turn so
the process exits instead of waiting on stdin.

### Reading the output

Score the generated text with the **same** word-level 4-gram metric used by the
gate (`_ngram_analysis(words, 4)` -> `repeat_token_frac`), so the numbers are
directly comparable: `<= 0.27` coherent, `>= 0.51` degenerate.

Note that llama.cpp's `llama-cli` prints chat-template scaffolding; extract only
the assistant message body before scoring, exactly as the gate extracts
`choices[0].message.content`.

## CPU timing expectation

Observed on this host (M4, Q3_K_M, 16 threads): prompt eval ~3.5 t/s, generation
~1.8 t/s. A 640-token single-turn run therefore takes on the order of several
minutes; budget ~15–30 min per model and run it when no other CPU-heavy job is
active.

## Verified so far (no GPU used)

* `llama-cli --version` -> `version: 0.4.1-dev (build 11026, commit b49650adb)`.
* `llama-cli --list-devices` -> `(none)`; `ldd` shows no CUDA/NVIDIA libraries.
* M4 loads from the real GGUF and generates on CPU (`m4_cpu_loadtest.log`).
