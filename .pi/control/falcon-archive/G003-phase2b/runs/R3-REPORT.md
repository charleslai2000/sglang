# B4-R3 report

## Verdict

```text
ROOT CAUSE ISOLATED / BLOCKED
```

B5/B6 were not run. R3B was not entered because R3A Gate A failed.

## R3A ratio=2

Configuration retained `hicache-ratio=2`, `write_through`, FULL + MAMBA,
`extra_buffer`, prefill CUDA graph disabled, decode CUDA graph full, no swap.
Runtime host allocations were:

```text
FULL/KV host: 290773 tokens, 13.10 GB
MAMBA host: 11.72 GB
MAMBA device: 83 states
```

One approximately 2K-token target request (`P + suffix A`) completed normally.
The process then remained idle for eight observations at two-second intervals.

```text
backup enqueue/issued/completed: no positive runtime evidence
pending/retry queue: no positive runtime evidence
FULL host_used: 0
MAMBA host_used: no positive host residency observed
FULL backup counter: 0 / no positive evidence
MAMBA backup counter: 0 / no positive evidence
```

The target was not accepted as backed up; R3B was stopped.

## Ratio=1 minimal A/B

The same target and waiting procedure were run on a clean ratio=1 service.
Runtime FULL/KV host capacity was 140689 tokens. The result was identical:

```text
FULL host_used: 0
MAMBA host_used: no positive host residency observed
backup counter: 0 / no positive evidence
```

Thus this minimal A/B does **not** show a ratio-dependent failure:

```text
ratio=1: no single-request backup observed
ratio=2: no single-request backup observed
```

This is not evidence that the previously observed ratio=1 pressure backups
were impossible; it establishes that ordinary insertion of one target does not
itself trigger the D→H path in this runtime. Earlier pressure-triggered backup
observations remain distinct.

## R3B

```text
not run
pressure tokens: 0
 target touched during pressure: N/A
device eviction: N/A
FULL host retained: N/A
MAMBA host retained: N/A
node retained: N/A
restore: N/A
```

No source patch or diagnostic instrumentation was added.

## Root cause status

The isolated condition is the trigger boundary: `write_through` does not
backup a newly inserted target merely because its request completed. The
observed implementation submits backup through HiCache's write-through/eviction
path; ordinary target insertion left host usage at zero. The ratio value was
not the differentiating variable in this minimal test. A pressure-triggered
A/B is required to separate pressure admission from the prior successful
ratio=1 pressure backup, but no such run was authorized in this step.

## Artifacts

```text
runs/r3a-ratio2/server.log
runs/r3a-ratio2/probe.stdout
runs/r3a-ratio2/response.json
runs/r3a-ratio2/metrics-0.txt ... metrics-7.txt
runs/r3a-ratio1/server.log
runs/r3a-ratio1/probe.stdout
runs/r3a-ratio1/response.json
runs/r3a-ratio1/metrics-0.txt ... metrics-7.txt
```
