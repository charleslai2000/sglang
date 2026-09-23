# Formal B5 report

## Original run classification (superseded by B5-DH audit)

The original run was conservatively classified as:

```text
B5 FAIL — correctness/stability passed, but required device_hit evidence was zero
```

That conservative gate classification is superseded by `B5-DH-AUDIT-REPORT.md`.
The current adjudication is:

```text
B5 correctness/stability: PASS
B5 host-tier churn: PASS
B5 device-hit observation: UNRESOLVED
B5 overall: HOLD
B6: BLOCKED
```

## Workload / serialization

```text
200 logical sessions
5 turns/session
1000 total turns
active concurrency: 16
seed: fixed
```

Each request used the actual tokenizer chat template with append-only messages:

```text
system/base context
user query
assistant response from the previous request
next user query
```

Revisit waves covered immediate, warm, and dormant orderings. Actual prompt token
lengths were:

```text
minimum: 1800
maximum: 1948
```

This stayed below the 2048 chunked-prefill boundary.

## Correctness

Oracle:

```text
parser: CODE\\s*=\\s*(\\d{4})
```

Results:

```text
completed: 1000/1000
parsed: 1000/1000
correct: 1000/1000
wrong-code: 0
missing-code: 0
HTTP errors: 0
```

No wrong-session code or missing code occurred.

## Cache telemetry

Final runtime counters after drain:

```text
prefill input: 1,785,067 tokens
prefill device_hit: 0 tokens
prefill host_hit: 88,930 tokens
prefill storage_hit: 0 tokens

FULL/KV D→H backup: 1,165,389 tokens
MAMBA D→H backup: 1,504 states
FULL/KV H→D load_back: 55,072 tokens
MAMBA H→D load_back: 118 states
device evictions: 1,171,474 tokens
KV dropped under host pressure: 0
MAMBA dropped under host pressure: 0
```

Host occupancy:

```text
peak/final observed host_used: 233749 / 290773 tokens
```

The run demonstrated substantial host-hit and FULL/MAMBA restore activity, but
no positive device-hit counter was captured in the final runtime telemetry.
Because the requested B5 acceptance explicitly requires both:

```text
device_hit > 0
host_hit > 0
```

this is a gate failure, not a B5 PASS.

## Stability / cleanup

```text
CUDA/runtime errors: 0 observed
scheduler crash: 0
HTTP deadlock: 0
OOM: 0
active requests after drain: 0
swap: 0 B
```

Host pool bookkeeping remained bounded and no dropped KV/MAMBA tokens were
reported.

## First failure evidence

No correctness failure occurred. The first failed acceptance condition was:

```text
required device_hit > 0
observed device_hit: 0
```

This is not evidence of device-hit mechanism failure because R2B independently
passed the device-hit micro gate with 1792 tokens. It indicates that this formal
revisit ordering did not produce a separately counted device-hit event in the
accepted final accounting.

## B6

Not run. B6 remains blocked pending a B5 PASS with positive device-hit and
host-hit evidence in the same formal churn.

## Artifacts

```text
runs/formal-b5-r3/result.json
runs/formal-b5-r3/turn-0.json ... turn-4.json
runs/formal-b5-r3/stdout
runs/formal-b5-r3/server.log
runs/formal-b5-r3/t38c-probe.log
control/G003-phase2b-hicache/formal_b5.py
```
