# G3-PRODUCTION-A-THROUGHPUT-RECON-20260908

ENTRY: ACCEPT

status: done
invocation_status: done
task_id: G3-PRODUCTION-A-THROUGHPUT-RECON-20260908
epoch: E5
role: tester

## Scope and method

This was a read-only reconciliation of the preserved local Production A and
Profile C artifacts. No SSH command, workload, service, product source, or
benchmark client was changed or rerun.

Sources:

- `.memory/g3-baseline-20260907/work/raw/g3-e3-prod-a-20260907T145045488234751Z/`
- `.memory/g3-baseline-20260907/work/raw/g3-profile-c1-decode-retry2-20260908/`
- `.memory/g3-baseline-20260907/work/raw/g3-profile-c6-equals-20260908/`
- `.memory/g3-baseline-20260907/work/raw/g3-profile-c8-python-20260908/`

The independent checks used the equivalent read-only operations:

```text
sed -n '11,31p' <repeat>/benchmark.stdout
sed -n '11,31p' <repeat>/runner.stdout-or-log
jq -r '[.duration,.total_input_tokens,.total_output_tokens,.output_throughput,.total_throughput] | @tsv' <repeat>.jsonl
```

For each raw JSONL record, the arithmetic was checked as:

```text
output throughput = total_output_tokens / duration
total throughput  = (total_input_tokens + total_output_tokens) / duration
```

The calculated values match the runner's `output_throughput` and
`total_throughput` fields. The runner's throughput uses `total_output_tokens`
(the requested/generated count), not `total_output_tokens_retokenized`; the
retokenized count is retained separately in the raw records.

## Exact runner labels

The preserved stdout uses these distinct labels in every checked point:

```text
Request throughput (req/s):
Input token throughput (tok/s):
Output token throughput (tok/s):
Peak output token throughput (tok/s):
Total token throughput (tok/s):
Concurrency:
```

Representative exact blocks are preserved at:

- Production A C4 repeat 2: `.../C4/repeat-2/benchmark.stdout`
- Production A C5 repeat 2: `.../C5/repeat-2/benchmark.stdout`
- Profile C C1 repeat 2: `.../runner/repeat-2.log`
- Profile C C6 repeat 2: `.../repeat2/runner.stdout`
- Profile C C8 repeat 2: `.../repeat2.log`

## Reconciled medians

Values below are medians of the three raw JSONL repeats. `out` is the runner's
`Output token throughput`; `total` is the runner's `Total token throughput`.

| point | workload / nominal C | input tokens / repeat | requested output / repeat | output tok/s | total tok/s | duration s |
|---|---|---:|---:|---:|---:|---:|
| Production A C1 | 2048 -> 512, C1 | 40,960 | 10,240 | 24.545720 | 122.728599 | 417.180677 |
| Production A C4 | 2048 -> 512, C4 | 81,920 | 20,480 | 33.881157 | 169.405783 | 604.465788 |
| Production A C5 | 2048 -> 512, C5 | 102,400 | 25,600 | 34.186597 | 170.932986 | 748.831473 |
| Profile C C1 / pool20 | 1024 -> 256, C4 | 32,768 | 8,192 | 33.907601 | 169.538004 | 241.597748 |
| Profile C C6 / pool32 | 1024 -> 256, C6 | 49,152 | 12,288 | 34.959714 | 174.798571 | 351.490289 |
| Profile C C8 / pool40 | 1024 -> 256, C8 | 65,536 | 16,384 | 36.557910 | 182.789552 | 448.165658 |

The Profile C C1 values quoted as approximately `33.91 output` and `169.54
total` are therefore correct for that point. Production A's `169.405783` and
`170.932986` are unambiguously its C4 and C5 **total** throughput values. Its
corresponding output values are `33.881157` and `34.186597`.

## Repeat-level raw outcome check

| point | repeat 1 output / total | repeat 2 output / total | repeat 3 output / total |
|---|---:|---:|---:|
| Production A C1 | 24.582051 / 122.910255 | 24.543098 / 122.715488 | 24.545720 / 122.728599 |
| Production A C4 | 33.779563 / 168.897813 | 33.881157 / 169.405783 | 33.882418 / 169.412090 |
| Production A C5 | 34.186597 / 170.932986 | 34.191070 / 170.955348 | 34.173328 / 170.866641 |
| Profile C C1 | 33.962464 / 169.812319 | 33.900047 / 169.500236 | 33.907601 / 169.538004 |
| Profile C C6 | 35.040670 / 175.203349 | 34.932532 / 174.662661 | 34.959714 / 174.798571 |
| Profile C C8 | 36.613911 / 183.069557 | 36.557910 / 182.789552 | 36.536767 / 182.683835 |

## Corrected interpretation

The prior comparison of approximately `170` versus `35` is invalid if it was
intended as a production-versus-Profile-C **output/decode** comparison. It
compared Production A C4/C5 `Total token throughput` (~169--171) with Profile C
`Output token throughput` (~34--37).

The apples-to-apples comparison is:

- Production A C4/C5 output: `33.88` / `34.19` tok/s.
- Profile C C1/C6/C8 output: `33.91` / `34.96` / `36.56` tok/s.

The aggregate totals are also internally consistent with the fixed 4:1
input:output ratio: total is approximately five times output. They are not the
same workload, however: Production A is 2048/512, while Profile C is 1024/256;
the points also differ in nominal concurrency. Thus total throughput should be
retained as an aggregate prefill+decode metric, while the formal performance
scorecard should use output TPS, TPOT, TTFT, and observed concurrency for
generation-speed claims.

This reconciliation does not alter the Profile C saturation observation:
output rises only from `33.907601` at Profile C C1/pool20 to `36.557910` at
C8/pool40, while latency increases substantially. It does correct the metric
label and removes the false `170 vs 35` impression.

## Artifact hashes

The following hashes were independently computed from the preserved artifacts:

```text
85096669d45cb78a69b18977aa35c9e337ea43fa3d239f3e09dae198e7ea5485  raw/g3-e3-prod-a-20260907T145045488234751Z/C4/repeat-2/benchmark.stdout
67e58f655ff53b4e88950f51eb45ec3d008699d4ab047c6e0b4b176dbf0a3ac6  raw/g3-e3-prod-a-20260907T145045488234751Z/C5/repeat-2/benchmark.stdout
420bbeae5082765301336694c5e32e23c03f72fbb395386922f00f7e3e729b22  raw/g3-profile-c1-decode-retry2-20260908/runner/repeat-2.log
386897fcf92ef71c7c9c59b5a312c61482ea7cbebc14cd44f5b5275d7d5b36d0  raw/g3-profile-c6-equals-20260908/repeat2/runner.stdout
f284673bc01420a027d08faec1e2fa237db35a30a0e74a4f10b1b392bc1cfc8f  raw/g3-profile-c8-python-20260908/repeat2.log
dc27ce7b102674b9d86d25da33ae80b886f7fc85ee5acf1ff43730a0b8b08899  raw/g3-profile-c1-decode-retry2-20260908/runner/repeat-2.jsonl
af772f099016305bd23014ce9e2d4e81b64e6af80ee7d136b360608b294ff686  raw/g3-profile-c6-equals-20260908/repeat2/runner.jsonl
6644ab4d75f22b0d6b02d21383879f6678459b93e56f296d88d6d8df15c451ff  raw/g3-profile-c8-python-20260908/raw/repeat2.jsonl
```

The complete Production A subtree remains covered by its preserved
`SHA256SUMS` (484 listed files, independently verified in
`G3-E3-PRODUCTION-A-VERIFY-20260908.md`).

## Limitations and final status

- No unavailable fields were inferred or fabricated.
- `total_output_tokens_retokenized` is lower than requested output in these
  records, but it is not the field used by the runner's throughput summary;
  both values remain available in raw JSONL.
- This task did not rerun or mutate any service and did not independently
  validate the separate kernel-causal hypothesis.

artifacts:
- `.memory/g3-baseline-20260907/work/G3-PRODUCTION-A-THROUGHPUT-RECON-20260908.md`
- the four raw subtrees listed under Scope and method

evidence: exact stdout labels, raw JSONL formula checks, repeat-level values,
and hashes above.

summary: PASS; Production A 169.405783/170.932986 are Total token throughput,
not Output token throughput. The prior `170 vs 35` comparison was a metric
miscomparison.

followups: use Output TPS / TPOT / TTFT / observed concurrency for generation
speed scorecards; retain Total TPS as a separate aggregate metric.

open_issues: none for this reconciliation.

invocation_status: done
