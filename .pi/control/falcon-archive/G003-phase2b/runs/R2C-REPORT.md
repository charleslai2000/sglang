# R2C report

## Verdict

```text
R2 host gate: PASS
Oracle qualification: PASS
Formal B5/B6: NOT RUN
```

## R2A old harness root cause

The old harness did not include assistant responses, did not use a chat template,
and serialized each request as independent plain text. Offline token audit still
showed substantial same-session LCP:

```text
turn 0→1: 59 / 75 = 0.787
turn 1→2: 77 / 93 = 0.828
turn 2→3: 95 / 111 = 0.856
turn 3→4: 113 / 129 = 0.876
```

Different-session LCP was 8 tokens. The old harness is formally deprecated and
was not used for acceptance.

## R2B device gate

Previously established and not repeated as a mechanism validation:

```text
turn2 device_hit: 1792
```

The aligned runtime hit matched the offline token audit.

## R2C host micro gate

Configuration remained the B4 PASS configuration:

```text
ratio=2
write_through
extra_buffer
prefill graph disabled
decode graph full
FULL + MAMBA
no L3/storage
```

Target setup used an approximately 1900-token prefix, aligned to 1024 cached
tokens for this prompt. Target node was node 18. The target was not requested
during pressure.

Adaptive pressure used 10 batches × 8 distinct prefixes, each bounded to
approximately 1600 input tokens. The gate stopped at the first target transition
with both device components detached and no host detach:

```text
pressure host_used: 123196 tokens
runtime FULL host capacity: 290773 tokens
stop: target_device_absent_host_retained
```

Target pre-restore state:

```text
node exists: yes
FULL:  device absent / host present, 1020 slots
MAMBA: device absent / host present, 1 slot
```

Target revisit result:

```text
cached_tokens: 1024
cached_tokens_details:
  device: 0
  host: 1024

host_hit delta: +1024
```

Restore telemetry/counters:

```text
FULL H→D:  load_back_tokens_total pool=kv, +1020
MAMBA H→D: load_back_tokens_total pool=mamba, +2
```

The MAMBA count of 2 is the expected node-restore plus request/device-slot CoW
accounting established in R5. Read-only snapshots after ACK showed:

```text
FULL:  device present / host present
MAMBA: device present / host present
```

No HTTP/CUDA/runtime error occurred; output was valid for the micro request.

## Oracle qualification

Exact contract:

```text
The session code is <4 digits>.
Question: Return the session code.
Reply exactly in this form: CODE=<4 digits>
```

Parser:

```text
case-insensitive regex: CODE\s*=\s*(\d{4})
```

HiCache-OFF cold/eager qualification:

```text
sessions: 200
passed: 200
wrong code: 0
missing code: 0
```

Raw outputs and parsed values are saved in:

```text
runs/r2-oracle-off/oracle.json
```

## Artifacts

```text
runs/r2c-host/result.json
runs/r2c-host/t38c-probe.log
runs/r2c-host/server.log
runs/r2c-host/stdout
runs/r2-oracle-off/oracle.json
runs/r2-oracle-off/oracle.stdout
runs/r2-oracle-off/server.log
control/G003-phase2b-hicache/r2_micro.py
control/G003-phase2b-hicache/r2_oracle.py
control/G003-phase2b-hicache/R2A-AUDIT.md
```
