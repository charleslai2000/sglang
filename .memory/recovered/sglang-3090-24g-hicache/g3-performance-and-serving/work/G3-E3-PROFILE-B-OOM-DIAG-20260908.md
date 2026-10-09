# G3-E3-PROFILE-B-OOM-DIAG-20260908

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: G3-E3-PROFILE-B-OOM-DIAG-20260908
epoch: E3
role: devops

## Scope and outcome

Read-only diagnosis on `root@175.155.64.171:22109`. No service launch,
traffic, flag change, GPU reset, signal, remote write, audit, tracing, or
instrumentation was performed. The only local write is this report.

**Classification: (a), scoped to the frozen Profile-B contract as executed by
this SGLang build/model on the single RTX 3090: startup is over capacity.**
The exact command loaded the intended model and B flags, allocated its static
pools, and then failed during required prefill CUDA-graph capture. This does
not prove that every alternate allocator/backend or larger GPU would fail, but
those would be changed diagnostic conditions. Classification (b) is not
supported by the evidence: no accidental B flag, model/weight, source, or
runner mismatch was found.

No B effective capacity or benchmark result is claimable. B never passed
health/admission and no benchmark request was sent.

## Exact launch and failure evidence

Preserved run root:
`/data/qwen3-g3-baseline/e3-profile-b/g3-e3-profile-b-20260907T170803Z/`

Local raw copy:
`.memory/g3-baseline-20260907/work/raw/g3-e3-profile-b-20260907T170803Z/`

The exact B command is preserved at
`launch/profile-b.command` (SHA-256
`cb02a208e967ff1786c6841b6aa0ca0abc46e2e4d9bbd3535590351b029c8840`). It
contains the frozen quality flags and the capacity flags:

```text
--chunked-prefill-size 2048 --max-prefill-tokens 16384
--max-running-requests 16 --max-mamba-cache-size 64
--max-total-tokens 33024 --mem-fraction-static 0.95
--cuda-graph-max-bs-decode 16
```

The launch began at `2026-09-07T17:15:43Z`; the log uses host local time
(UTC+8). The complete startup log is
`launch/profile-b.log`, SHA-256
`e653fb4cd4b9b53a0cb319336b7b749510d3ca08bd9a36350e424e448de2b608`.
Its exact sequence is:

```text
01:17:21  Load weight end ... avail mem=11.37 GB, mem usage=11.86 GB
01:17:29  max_total_tokens=33024 is larger than the profiled value 28928. Use the profiled value instead.
01:17:29  Mamba Cache ... max_mamba_cache_size: 64, conv_state 0.18GB, ssm_state 9.14GB
01:17:29  KV Cache ... #tokens: 28928, K 0.44 GB, V 0.44 GB
01:17:29  Memory pool end. avail mem=1.09 GB
01:17:29  prefill CUDA graph capture begins ... avail mem=0.66 GB
01:18:43  CUDA OOM while capturing num_tokens=2048 (first of 42 shapes)
01:18:43  process 480396: 23.53 GiB in use; 10.88 MiB free; request 170.00 MiB
01:18:44  scheduler exception and process-tree cleanup
```

The CUDA allocator records the same failed request as 178,257,920 bytes with
11,403,264 bytes free. The exception stack ends in the GGUF
`ggml_dequantize` call for a Qwen MoE `down_proj` during the graph warmup.
This identifies the failed allocation site, not the total memory consumed by
dequantization; no larger component attribution is fabricated.

The B health and loads statuses are both `000`; see
`launch/health.status` and `launch/loads.status`. The outcome marker is
`launch/current-outcome.txt` (SHA-256
`2c7e340dc1c60a997e385ee996d4f385df0ec9b423661761decfe2f09bb1102a`).

## Baseline versus B allocation facts

The preserved v1 startup log is remote
`/data/sglang-qwen35/exp_server_j1_v1.log`; its SHA-256 at the read-only
recheck was
`ab6f367900899f4026298d0ad78bda4e58c6ac5a2a057e7c4bbaaed24fc549a5`.
The original startup allocation lines are at log lines 17--36. The preserved
v1 restore log copy is
`restore/v1.log`, SHA-256
`6b8581858b60ff59cd35eaea85816ec33a725e391cb4136c93c5da3ba9c112bb`.

| Quantity | Frozen v1 observed | B observed/attempted | Difference/meaning |
|---|---:|---:|---|
| Model weights | 11.86 GB | 11.86 GB | unchanged |
| Mamba conv + SSM | 0.07 + 3.38 = 3.45 GB | 0.18 + 9.14 = 9.32 GB | +5.87 GB from max cache 23 to 64 |
| KV K + V | 2.02 + 2.02 = 4.04 GB | 0.44 + 0.44 = 0.88 GB | -3.16 GB; B pool was profiled at 28,928 tokens |
| Memory pool end available | 3.86 GB | 1.09 GB | near 2.77 GB less headroom |
| Prefill graph start available | 3.43 GB | 0.66 GB | same 42-shape list, B could not capture first shape |
| Decode graph | 0.10 GB, completed | not reached | no B decode graph evidence |
| Final startup available | 1.48 GB, completed | none | B failed before admission |

The arithmetic direction is consistent with the observed pool changes (larger
Mamba state allocation partially offset by a much smaller KV pool), but the
logs do not expose a complete per-component allocator ledger. In particular,
the 624.89 MiB reserved-but-unallocated figure and the 170 MiB dequantization
request show allocator headroom/fragmentation behavior; they do not establish
that fragmentation alone caused the failure. The B process reached 23.53 GiB
in use on a 23.56 GiB CUDA capacity before that request, which is sufficient
to fail the exact startup contract regardless of whether the last margin is
described as pool sizing, graph workspace, temporary dequantization, or
allocator fragmentation.

## Identity and environment checks

The B log and command show the same model path and frozen settings:
`reasoning-parser auto`, `tool-call-parser qwen3_coder`, `kv-cache-dtype
fp8_e4m3`, `mamba-radix-cache-strategy extra_buffer_lazy`, and
`preserve_thinking=false`. Read-only host checks report:

```text
model MD5:       a37cff66ad81b0e6311d4b6671ac2b09
model size:      11771546784 bytes
serving.py SHA:  01bb7b7c5130ed3ba7dea895e62543a075add5fd592861d839c6448cbddc9bfb
server_args.py:  aba8af3f6ee28ea3216bef7e6488683bb60ac03cec6cd511e01041c304e5fcb9
Python:          3.12.0
SGLang:          0.5.10.dev0
GPU:             RTX 3090, 24576 MiB total
```

These match the preserved transition/restore evidence. The v1 command is
`restore/v1.command`, SHA-256
`69f80370e67d3e8e4c364ee847c1ef914641567a07dfc1ba2edb882909d70007`.

## Terminal-claim gate

Observed facts:

- Exact Profile-B launch was used once; B allocated weights, Mamba, KV, and
  began the configured prefill graph capture.
- `max_total_tokens=33024` was not physically realized: SGLang explicitly
  profiled and substituted 28,928 tokens.
- The first 2,048-token prefill graph warmup attempted a 170 MiB allocation
  with only 10.88 MiB free and failed at the GGUF dequantization call.
- B had no health/admission, no effective `/v1/loads` capacity, and no
  benchmark traffic.
- The v1 service is currently healthy and idle (fresh read-only check at
  `2026-09-07T17:53:39Z`): PID `462700` owns 127.0.0.1:8035, `/health`
  returned HTTP 200, `/v1/loads?include=all` returned HTTP 200 with
  `num_running_reqs=0`, `num_waiting_reqs=0`, `max_running_requests=5`, and
  `max_total_num_tokens=132436`. Current GPU query showed one attributable
  SGLang compute owner (`483639`, 22,776 MiB); 8036 was absent.

Assumptions/inferences, kept separate:

- The exact contract is operationally over capacity on this 24 GiB card for
  this runtime because its own startup allocator could not complete. This is
  not a mathematical proof against all changed allocators/backends.
- The larger Mamba pool is the dominant known capacity delta, while the
  reduced KV pool offsets part of it. The logs do not justify assigning the
  remaining failure margin to one component.
- The dequantization temporary is a required graph-capture allocation at the
  observed stack site, but its full lifetime/peak contribution is unknown.

Bypass/alternate-mechanism check: the command, model identity, source hashes,
and frozen parser/KV/Mamba/template settings were all verified; B's internal
token clamp and OOM occurred before any client activity. No launch typo or
second GPU owner explains the failure. The only apparent remedies (smaller
Mamba/KV/token pool, lower memory fraction, reduced/disabled prefill graph,
alternate graph backend, allocator environment, or larger hardware) change
the frozen B contract or platform and therefore are not remedies under this
Task ID.

## Recommendation and open issues

There is no known remedy on the current single RTX 3090 that preserves the
frozen B contract exactly. Do not claim B performance or combine this failed
startup with any denominator. Keep PID `462700`/8035 running and untouched.

If the user wants a lower-capacity or allocator/backend diagnostic, issue a
fresh Task ID with one explicitly named changed condition and a new runbook;
do not rerun B or alter the v1 service under this task. A useful next task
would compare one changed capacity variable at a time (for example the Mamba
cache cap or graph capture policy), with the same identity and rollback gates,
but that is a recommendation only and was not executed.

Open issues: exact per-component split of graph workspace, temporary GGUF
dequantization, and allocator fragmentation is unresolved; B effective
capacity remains unavailable by design. This does not weaken the conclusion
that the exact B startup contract failed on the target card.

Followups: fresh Task ID and explicit user decision required for any changed
profile; preserve v1 and all B raw artifacts.

Final status: **done**
