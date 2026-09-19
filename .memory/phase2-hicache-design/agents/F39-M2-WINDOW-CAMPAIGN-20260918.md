# F39 — M2 GPU-Window Consolidated Campaign

Status: DONE

Terminal state: DONE

## Task
Single-window consolidated campaign on the single RTX 3090: (0) install the `m2` scaffold role,
(1) launch M2 via the scaffold, (2) verify the just-landed reasoning/cache telemetry changes take
effect, (3) run a narrow reasoning-effort calibration, (4) run a controlled efficiency sweep (M2,
optionally M1), (5) restore production to M2. One owner, one GPU window. Never leave the host
without a healthy serving instance.

## Scope
- Prod scaffold scripts `/tmp/opencode/prod-service-20260917` (Step 0 only).
- Frozen trees `/opt/sglang/**` read-only, with the one authorized exception that the M2 launcher
  was exercised. The test tree was a scratch hardlink clone under `/tmp/opencode/F39-CAMPAIGN-20260918`.
- Worktree `/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt` was used as the source of the
  landed telemetry files; nothing in it was modified or committed.
- Scratch driver plus request harnesses under `/tmp/opencode/F39-CAMPAIGN-20260918/` only.
- Single GPU: exactly one server process held the device at any time. No model weights touched.

## Result (per step)

### Step 0 — install/repair the `m2` scaffold role — DONE
PREMISE CORRECTION (FACT): the premise "the integration was staged but NEVER applied" is only half
true on disk.
- `bin/start.sh` ALREADY contained the `m2)` case before this campaign (backup
  `bin/start.sh.bak-20260918125106`, mtime 12:51). It was missing only the `ROLE=m2`
  L3-namespace-skip wrapper from the staged patch's second hunk.
- `conf/service.env` had NO `M2_*` keys at all. Consequently `start.sh m2` died at
  `M2_PORT: unbound variable` (reproduced).
- The `.rej` files under `/tmp/opencode/M2-ARCH-STAGE-20260918/patchcheck/` are consistent with a
  previously rejected attempt; the staged intent itself lives in `patch/b`, which matches
  design-artifact deliverables 3/4.

WHAT I DID (scaffold scripts only — not product source):
1. Backed up both target files:
   `bin/start.sh.pre-f39-20260918T161154Z` and `conf/service.env.pre-f39-20260918T161154Z`.
2. Added the `ROLE=m2` namespace-skip wrapper (`if [ "$ROLE" = "m2" ]; then NAMESPACE=""; ... else
   <original allocation> fi`) to `bin/start.sh`.
3. Replaced `conf/service.env` with `patch/b/conf/service.env` verbatim (adds `M2_PORT=30000`,
   `M2_TREE_DEFAULT`, `M2_IDENTITY_DEFAULT`, `M2_MODEL_PATH`, `M2_L3_MODE=disabled`, and their
   export list).

Acceptance evidence: `bash -n bin/start.sh` rc 0; `bash -n bin/stop-m2.sh` rc 0; `prod`/`test`
case lines byte-identical to the pre-change backup; both files now equal the staged `patch/b`
except the two usage strings in `start.sh` (see Defects D5); `start.sh m2` dry-run resolves to
tree `/opt/sglang/local-prod-v1.2.1-candidate-M2` and port `30000`.

### Step 1 — launch M2 via the scaffold — DONE
`bash /tmp/opencode/prod-service-20260917/bin/start.sh m2` returned rc 0 and reached `=== m2 UP ===`
in 94.9 s. `/health` 200, `/v1/models` id `/data/models/omnicoder-9b-gptq-int4`. The effective argv
is token-for-token identical to the known pre-campaign production argv once the per-run metrics
directory is normalized; the only intended difference is the interpreter/tree prefix
(`...candidate-M2/env/bin/python` vs `...candidate/env/bin/python`, same symlink target) and the
log directory. `/proc/<server>/environ` shows `PYTHONPATH=...candidate-M2/src/python`,
`CUDA_VISIBLE_DEVICES=GPU-2e3ed202-...`, `SGLANG_L3_MODE=disabled`. Lock generation advanced
24 → 25.

### Step 2 — telemetry changes actually take effect — DONE
Test tree = frozen `candidate-M2/src/python` hardlink clone PLUS exactly 7 enumerated files copied
from the worktree: `server_args.py`, `entrypoints/openai/protocol.py`,
`entrypoints/openai/serving_chat.py`, `entrypoints/openai/usage_processor.py`, `environ.py`,
`sampling/custom_logit_processor.py`, and NEW `parser/qwen35_reasoning_policy.py`.
`diff -rq` vs the frozen tree reports exactly those 7 paths and nothing else. Launched via
`PYTHONPATH=<test-tree>` with `--enable-custom-logit-processor` (needed for Step 3).

REAL REQUEST RESULTS:
- Cache reporting ON by default: a first (cold) request with a ~1991-token prompt returned
  `prompt_tokens_details: null`; an immediately repeated identical request returned
  `"prompt_tokens_details": {"cached_tokens": 1984}`. Duration dropped 0.542 s → 0.133 s.
- `usage.completion_tokens_details.reasoning_tokens` present and a subset: arithmetic prompt with
  thinking enabled returned `completion_tokens=303`, `completion_tokens_details.reasoning_tokens=298`,
  `finish_reason=stop`, `reasoning_content_len=763`, `content="\n\n391"`. 298 ≤ 303.
- A truthful reasoning trace is required and was confirmed (`reasoning_content` non-empty,
  `reasoning_tokens > 0`).

### Step 3 — narrow reasoning-effort calibration — DONE (observations only)
Small fixed prompt set: `arith` (17×23), `arith2` (13×29), `code_constrained` (constrained-output
Python reverse). Tiers: `none` (omitted control), `low`, `high`; 3 reps each; `max_tokens=8192`,
temperature 0.

Deterministic per (prompt,tier) in every rep (reasoning_tokens):

| prompt | none (omitted) | low | high |
|---|---|---|---|
| arith | 298 (stop) | 275 (stop) | 527 (stop) |
| arith2 | 265 (stop) | 298 (stop) | 413 (stop) |
| code_constrained | 790 (stop) | 425 (stop) | 2223 / 8192 / 8192 (stop,length,length) |

OBSERVATIONS (not final ladder decisions):
- `low` vs `high` DO differ, and the direction is not uniform: on `arith` `low < none < high`, but
  on `arith2` `none < low < high`. So `low` is not uniformly "less thinking than the default".
- Budget enforcement IS active but was masked at `high` because the policy budget (8192) equalled
  the `max_tokens` ceiling. Re-probed with `max_tokens=16384`: `high` (budget 8192) produced
  `reasoning_tokens=8195` and `finish_reason=stop` with non-empty content, whereas `medium`
  (budget 2048, unconstrained) produced 790. `minimal` (budget 256) produced 259 vs the control's
  298. This is positive evidence the `Qwen35ThinkingBudgetLogitProcessor` budget is being applied;
  observed counts run 3 tokens past the nominal budget (see Defects D4).
- True `"none"` is distinct from an omitted effort: `reasoning_effort="none"` produced
  `reasoning_tokens=null` and `completion_tokens=4` (no thinking), while omitting the field produced
  298. The omitted-effort default tier is unchanged, as designed.
- I am NOT selecting final `max_thinking_tokens` values. The current ladder is a runtime policy
  overridable by `SGLANG_QWEN35_EFFORT_POLICY`; it is provisional.

### Step 4 — controlled efficiency sweep — DONE
Bounded, reproducible sweep on the live server: c = 1/2/4/8, 16 streamed requests per level,
`max_tokens=64` with `ignore_eos=true`, temperature 0, thinking off. Two cases:
- `distinct-noreuse`: unique ~4489–4492-token prompt per request (no shared radix prefix).
- `shared-prefix-reuse`: identical ~3772-token prompt (one warm-up request, then measured).

M2 (test tree), p50 values:

| case | c | TTFT p50 | TTFT p90 | dur p50 | dur p90 | decode TPS p50 | cached nonzero |
|---|---|---|---|---|---|---|---|
| distinct | 1 | 1.099 | 1.131 | 1.864 | 1.898 | 83.62 | 0/16 |
| distinct | 2 | 1.640 | 2.208 | 2.928 | 2.997 | 76.17 | 1/16 |
| distinct | 4 | 2.983 | 4.248 | 5.064 | 5.226 | 30.85 | 0/16 |
| distinct | 8 | 4.408 | 7.499 | 8.847 | 9.466 | 15.07 | 1/16 |
| shared | 1 | 0.130 | 0.133 | 0.895 | 0.899 | 83.54 | 16/16 (3712) |
| shared | 2 | 0.230 | 0.239 | 1.011 | 1.022 | 81.80 | 16/16 (3712) |
| shared | 4 | 0.236 | 0.248 | 1.041 | 1.050 | 79.76 | 16/16 (3712) |
| shared | 8 | 0.350 | 0.360 | 1.185 | 1.192 | 76.79 | 16/16 (3712) |

CACHE BENEFIT: at c=1 the reused prefix cut TTFT from 1.099 s to 0.130 s (8.5×) and duration from
1.864 s to 0.895 s (2.1×), and `cached_tokens` was 3712 on all 16 measured requests. This confirms
the reported cache value reflects a real prefill saving. The 1–2 nonzero hits in the `distinct`
case are partial prefix matches on the shared boilerplate, not full reuse.

max-running-requests: 8 (from argv). Exact argv is stored in
`/tmp/opencode/F39-CAMPAIGN-20260918/testtree-argv.txt`.

OPTIONAL M1 COMPARISON: RUN. `bash .../start.sh prod` brought up `LOCAL-PROD-v1.2.1`
(`/data/models/qwen35-9b-w4a16`, L3/HiCache ON, `--max-total-tokens 524288`, lock gen 27), and the
same sweep was executed (c=1/2/4/8, 16 requests/level). Note this compares two DIFFERENT models on
two DIFFERENT configs; it is not an apples-to-apples ablation.

| case | c | M2 TTFT p50 | M1 TTFT p50 | M2 decode p50 | M1 decode p50 | M2 dur p50 | M1 dur p50 |
|---|---|---|---|---|---|---|---|
| distinct | 1 | 1.099 | 1.086 | 83.62 | 90.82 | 1.864 | 1.791 |
| distinct | 2 | 1.640 | 0.220 | 76.17 | 87.40 | 2.928 | 0.954 |
| distinct | 4 | 2.983 | 0.228 | 30.85 | 84.63 | 5.064 | 0.985 |
| distinct | 8 | 4.408 | 0.372 | 15.07 | 76.15 | 8.847 | 1.216 |
| shared | 1 | 0.130 | 0.136 | 83.54 | 90.58 | 0.895 | 0.842 |
| shared | 2 | 0.230 | 0.221 | 81.80 | 87.90 | 1.011 | 0.949 |
| shared | 4 | 0.236 | 0.234 | 79.76 | 85.69 | 1.041 | 0.981 |
| shared | 8 | 0.350 | 0.328 | 76.79 | 82.35 | 1.185 | 1.106 |

OBSERVATION: at c=1 the two are close. Under concurrency M2 degrades sharply on the
distinct/non-cached path (TTFT 1.1→4.4 s; decode 84→15 tok/s) while M1 stays nearly flat
(TTFT 1.1→0.37 s; decode 91→76 tok/s). On the cached path M2 holds up well. This is recorded as an
observation only; no root-cause claim (see Defects D3).

### Step 5 — restore production — DONE
`bash /tmp/opencode/prod-service-20260917/bin/start.sh m2` (scaffold, now proven) returned rc 0 and
reached `=== m2 UP ===` in 95.8 s. `/health` 200 on loopback AND on LAN (192.168.20.250:30000),
`/v1/models` = `/data/models/omnicoder-9b-gptq-int4`, and a chat smoke returned
`content="\n\n391"`, `finish_reason=stop`. Exactly one server on the GPU. See Restored-state record.

## Evidence

### E0. Step 0 — exact pre/post facts
```
$ git-free diff current vs staged patch/b
$ diff -u bin/start.sh /tmp/opencode/M2-ARCH-STAGE-20260918/patch/b/bin/start.sh
@@ -25,7 +25,7 @@
-ROLE="${1:?usage: start.sh <prod|test|m2> [tree]}"
+ROLE="${1:?usage: start.sh <prod|test> [tree]}"
...
-  *) die "unknown role '$ROLE' (want prod|test|m2)" 2 ;;
+  *) die "unknown role '$ROLE' (want prod|test)" 2 ;;
(only the two usage strings differ; pre-existing before this campaign)

$ diff -u conf/service.env .../patch/b/conf/service.env    -> ENV_IDENTICAL_PATCH_B

$ bash -n bin/start.sh; echo $?          -> 0
$ bash -n bin/stop-m2.sh; echo $?        -> 0
$ grep -nE '^  (prod|test)\)' bin/start.sh
32:  prod) PORT="$PROD_PORT"; TREE="${TREE_OVERRIDE:-$PROD_TREE_DEFAULT}"; IDENTITY="${PROD_IDENTITY_DEFAULT}" ;;
33:  test) PORT="$TEST_PORT"; TREE="${TREE_OVERRIDE:-$TEST_TREE_DEFAULT}"; IDENTITY="LOCAL-PROD-v1.1.2" ;;
(diff vs pre-f39 backup -> PROD_TEST_BYTE_IDENTICAL)

$ grep -E '^M2_' conf/service.env
M2_PORT=30000
M2_TREE_DEFAULT=/opt/sglang/local-prod-v1.2.1-candidate-M2
M2_IDENTITY_DEFAULT=LOCAL-PROD-v1.2.1-M2
M2_MODEL_PATH=/data/models/omnicoder-9b-gptq-int4
M2_L3_MODE=disabled

$ START_DRY_RUN=1 bash bin/start.sh m2
[16:14:29] === start role=m2 port=30000 tree=/opt/sglang/local-prod-v1.2.1-candidate-M2 ===
[16:14:46] preflight PASS: /opt/sglang/local-prod-v1.2.1-candidate-M2
[16:14:46] FATAL: GPU has a material compute holder; stop it first (this script never signals it):
1808321 19174 sglang::scheduler 1
(the role resolved correctly and failed closed at the GPU gate while the incumbent was live)

$ bash bin/start.sh bogus; echo $?
[16:14:46] FATAL: unknown role 'bogus' (want prod|test|m2) 2
2
```

### E1. Step 1 — scaffold launch and argv parity
```
$ bash /tmp/opencode/prod-service-20260917/bin/start.sh m2
[16:21:38] L3 DISABLED for m2 (SGLANG_L3_MODE=disabled): no namespace allocated; /data/l3 untouched
[16:21:38] supervisor pid=1821535 (holds the canonical GPU lock for the server lifetime)
[16:23:14] === m2 UP ===
role=m2
pid=1821562
supervisor_pid=1821535
port=30000
tree=/opt/sglang/local-prod-v1.2.1-candidate-M2
run_id=m2-20260918T162138Z-1821348
namespace=
lock_generation=25
cold_start_s=94.9
START_RC=0

$ curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:30000/health      -> 200
$ curl -s http://127.0.0.1:30000/v1/models
{"object":"list","data":[{"id":"/data/models/omnicoder-9b-gptq-int4",...}]}

$ diff -u incumbent-argv.txt scaffold-argv.txt
ARGV_IDENTICAL_TOKEN_FOR_TOKEN          (log dir normalized to <LOG_DIR>)

$ tr '\0' '\n' < /proc/1821562/environ | grep -E 'PYTHONPATH|CUDA_VISIBLE|SGLANG_L3'
SGLANG_PORT=30000
CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
SGLANG_L3_MODE=disabled
PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate-M2/src/python
SGLANG_RUN_ID=m2-20260918T162138Z-1821348
SGLANG_MODEL_PATH=/data/models/omnicoder-9b-gptq-int4
```

### E2. Step 2 — test-tree delta and real telemetry
```
$ diff -rq --exclude=__pycache__ --exclude=*.pyc <frozen>/src/python <test-tree>/python
Files .../entrypoints/openai/protocol.py and .../protocol.py differ
Files .../entrypoints/openai/serving_chat.py and .../serving_chat.py differ
Files .../entrypoints/openai/usage_processor.py and .../usage_processor.py differ
Files .../environ.py and .../environ.py differ
Only in <test-tree>/python/sglang/srt/parser: qwen35_reasoning_policy.py
Files .../sampling/custom_logit_processor.py and .../custom_logit_processor.py differ
Files .../server_args.py and .../server_args.py differ
(7 entries; every one intended)

$ grep -n 'enable_cache_report' <test-tree>/.../server_args.py
1380:    enable_cache_report: A[
      ] = True

$ F39 test-tree launch
PYTHONPATH=/tmp/opencode/F39-CAMPAIGN-20260918/test-tree/python
CUDA_VISIBLE_DEVICES=GPU-2e3ed202-3655-d919-0a64-259209bc6587
--enable-custom-logit-processor
F39_TESTTREE_UP pid=1822512 run_id=f39-testtree-20260918T162420Z-1822488 cold_start_s=77

$ prefix-reuse cache check (real requests)
{"run": "cold-1",  "prompt_tokens": 1991, "prompt_tokens_details": null}
{"run": "reuse-2", "prompt_tokens": 1991, "prompt_tokens_details": {"cached_tokens": 1984}}
(cold 0.542 s -> reuse 0.133 s)

$ reasoning usage (thinking enabled)
"usage": {"prompt_tokens": 25, "total_tokens": 328, "completion_tokens": 303,
          "completion_tokens_details": {"reasoning_tokens": 298}, "reasoning_tokens": 0}
"content": "\n\n391", "reasoning_content_len": 763, "finish_reason": "stop"
(298 is a subset of 303)

$ server-side confirmation
sglang:cached_tokens_total{cache_source="device",...} 394098.0
sglang:cache_hit_rate{...} 0.984...
```

### E3. Step 3 — calibration and budget enforcement
```
tier-level determinism (3/3 reps identical per cell):
arith            none rt=298  low rt=275  high rt=527
arith2           none rt=265  low rt=298  high rt=413
code_constrained none rt=790  low rt=425  high rt=2223,8192,8192

budget enforcement probes (fresh requests):
{"case":"arith","tier":"minimal","max_tokens":2048,"reasoning_tokens":259,"finish_reason":"stop"}
{"case":"code_high_max16k","tier":"high","max_tokens":16384,"reasoning_tokens":8195,
 "completion_tokens":8214,"finish_reason":"stop",
 "content_head":"</think>\n\ndef rev(s: str) -> str:\n    return s[::-1]"}
{"case":"code_medium_max16k","tier":"medium","max_tokens":16384,"reasoning_tokens":790,
 "finish_reason":"stop"}
(high budget 8192 stops at 8195 while max_tokens=16384 -> budget is enforced)

true "none" vs omitted:
{"case":"omitted_effort","reasoning_tokens":298,"completion_tokens":303,"content":"\n\n391"}
{"case":"effort_none_string","reasoning_tokens":null,"completion_tokens":4,"content":"391"}
```

### E4. Step 4 — sweep artifacts
```
testtree-argv.txt / m1-argv.txt   (exact server argv)
efficiency-m2.json / efficiency-m2.out
efficiency-m1.json / efficiency-m1.out
```
Raw per-level rows are in those JSON files (TTFT p50/p90/p95, dur p50/p90/p95, decode TPS
p50/p90, aggregate TPS, cached token counts, n_ok/n_err) plus the M1/M2 merge table above.
No request failed (`n_err=0` on all 16 levels). Server console contains only the pre-existing
libtorchcodec/FFmpeg startup tracebacks and one 503 during the very first health poll; there are
no request-level errors, and the only 4xx/5xx in the whole log is that startup 503.

### E5. Incident — permission side effect (see Defects D1 for full disclosure)
```
$ mode histogram comparison
M2 files: 6145 444 / 37 555    (after remediation)
M1 files: 6145 444 / 37 555
M2 dirs:  743 555
untouched siblings local-prod-v1.2/v1.1.2: identical 444/555 pattern
$ frozen src stream digest M2 = c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc
$ frozen src stream digest M1 = c7427132b7977797a4cf3ff3ec46e665842229482bb1e45f7b874e15bb3dafbc
$ M2 manifest sha = e6e8de1c...  launcher sha = 9a557d5f...
$ M1 manifest sha = 5ed662d0...  launcher sha = 4ae68470...
```

### E6. Step 5 — restored state
```
$ bash /tmp/opencode/prod-service-20260917/bin/start.sh m2
[16:47:20] L3 DISABLED for m2 ...
[16:47:20] supervisor pid=1824666 ...
[16:48:56] === m2 UP ===  cold_start_s=95.8  lock_generation=28  RESTORE_RC=0

$ curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:30000/health        -> 200
$ curl -s -o /dev/null -w "%{http_code}\n" http://192.168.20.250:30000/health   -> 200
$ curl -s http://127.0.0.1:30000/v1/models
{"object":"list","data":[{"id":"/data/models/omnicoder-9b-gptq-int4",...}]}
$ chat smoke: completion_tokens=303, finish_reason=stop, content="\n\n391"
$ /proc/1824693/environ PYTHONPATH=/opt/sglang/local-prod-v1.2.1-candidate-M2/src/python
$ restored server argv has 0 occurrences of --enable-custom-logit-processor (frozen production parity)
$ ps: 1824666 supervise.sh m2 ... ; 1824693 launch_server ; 1825100 sglang::scheduler ; 1825101 detokenizer
$ nvidia-smi: 1825100 18752 MiB sglang::scheduler
```

## Defects / blockers

- **D1 (SELF-INFLICTED, REMEDIATED; must be disclosed).** Building the Step 2 test tree I used
  `cp -al` (hardlinks) from the frozen M2 `src/python`, then ran `chmod -R u+w` on the clone. Because
  the files were hardlinked, this changed the mode of the SHARED frozen M2/M1 inodes from 444 to
  644. I detected it by comparing the mode histogram against untouched frozen siblings, then
  remediated with `chmod -R a-w /opt/sglang/local-prod-v1.2.1-candidate-M2/src/python`, which
  restored the shared inodes. Post-remediation histograms for M2 and M1 exactly match untouched
  siblings (files 6145×444 + 37×555, dirs 743×555); content digests (M2/M1 src stream
  `c7427132…`, M2 manifest `e6e8de1c…`, M1 manifest `5ed662d0…`) are unchanged and match their
  pins. No file content was ever modified. The window was never at risk of serving wrong bytes.
  This is a process error I introduced; the remediation is verified, not assumed.
- **D2 (metric caveat).** My `aggregate_tps` is `total_out / max(per-request duration)` inside a
  level. At c=1 that divides a small total by 16 back-to-back requests and is not a true
  per-second server throughput. Only the TTFT/duration/decode/cached columns should be read as
  measured facts; `aggregate_tps` is relative only.
- **D3 (M2 concurrency collapse, observed not root-caused).** On the non-cached path M2's TTFT and
  decode TPS degrade far more than M1's as concurrency rises. Plausible causes (INFERENCE, unproven)
  are M2's larger KV footprint with the same `--max-total-tokens 262144` and mamba-cache contention,
  since M1 ran `--max-total-tokens 524288` with L3. This campaign did not isolate the cause.
- **D4 (budget off-by-a-few).** Enforced budgets land 3 tokens above the nominal value
  (256→259, 8192→8195). Likely the newline/token-sequence matcher counting; INFERENCE, not proven.
  Not a blocker for the budget mechanism, which is demonstrably active.
- **D5 (pre-existing deviation from staged patch).** `bin/start.sh` usage/unknown-role strings
  include `m2`; the staged `patch/b` keeps them as `prod|test`. This deviation predates this
  campaign (12:51 edit) and is the more accurate text; I left it. Behavior is unaffected.
- **D6 (wire contains both old and new reasoning fields).** Responses still emit the legacy
  top-level `"reasoning_tokens": 0` alongside `completion_tokens_details.reasoning_tokens`. The new
  field is authoritative per the landed design; the legacy zero could confuse naive clients. Noted.
- **D7 (startup noise).** The server console has 5 libtorchcodec/FFmpeg `OSError` tracebacks at
  import time. They are pre-existing, non-fatal (multimodal processor skipped), and unrelated to
  the landed changes.

## Remaining claims / exclusions

ESTABLISHED:
- `start.sh m2` now resolves to the M2 tree/port, passes `bash -n`, and `prod`/`test` lines are
  byte-identical to before.
- A real scaffold-managed M2 launch reaches `/health` 200 with argv/env parity to the incumbent.
- On the test tree, `usage.prompt_tokens_details.cached_tokens` is populated by default for a
  reused prefix, and `completion_tokens_details.reasoning_tokens` is present and a subset of
  `completion_tokens`.
- `low`/`high` tiers produce different reasoning token counts and the thinking budget is actually
  enforced when `max_tokens` exceeds the budget.
- The measured M2 efficiency table and the M1 comparison table above.

NOT ESTABLISHED / EXCLUDED:
- I did NOT choose final `max_thinking_tokens` values or alter the live default tier.
- The M2-vs-M1 sweep is NOT a controlled model comparison: different models, different
  max-total-tokens, M1 with L3/HiCache. It is a same-workload observation only.
- `low` is not uniformly below the omitted-effort default (see arith2), so no monotonic
  low<none claim is made.
- Exact budget semantics (why +3) are not established.
- The test tree was scratch and is NOT a production candidate; the telemetry overlay was never
  installed into `/opt` and production was restored from the FROZEN M2 tree. The restored server
  therefore does NOT expose the new telemetry by design (it has `prompt_tokens_details: null`),
  matching pre-campaign production.
- No commits, no ledger edits, no weight changes, no `pkill`, no other GPU process signalled.
- The scratch test tree (~99 MB) and campaign logs remain under
  `/tmp/opencode/F39-CAMPAIGN-20260918/` as evidence.

## Restored-state record

| Item | Value |
|---|---|
| Serving instance | M2 OmniCoder-9B GPTQ INT4 on :30000 |
| Launch command | `bash /tmp/opencode/prod-service-20260917/bin/start.sh m2` |
| Tree | `/opt/sglang/local-prod-v1.2.1-candidate-M2` (frozen) |
| PYTHONPATH | `/opt/sglang/local-prod-v1.2.1-candidate-M2/src/python` |
| supervisor pid | 1824666 (`supervise.sh m2 ...`) |
| server pid | 1824693 |
| scheduler / detokenizer / tracker | 1825100 / 1825101 / 1825099 |
| run_id | `m2-20260918T164720Z-1824480` |
| lock generation | 28 (`supervise-m2-m2-20260918T164720Z-1824480`) |
| L3 namespace | none (M2 is no-L3; `/data/l3` untouched by M2) |
| cold start | 95.8 s |
| `/health` loopback / LAN | 200 / 200 |
| `/v1/models` | `/data/models/omnicoder-9b-gptq-int4` |
| chat smoke | `content="\n\n391"`, `finish_reason=stop` |
| scaffold file hashes | `start.sh` `7fe92ce17044546f73b7e98e020b2c0034ff8c7a15b02cc2c3e98403c23c6611`; `service.env` `d7ec2f0fa5e4c678cf641f2b8b3bf4505c56cf3ce5fc34b86698c5b6ba9a3c7d` |
| backups | `bin/start.sh.bak-20260918125106`, `bin/start.sh.pre-f39-20260918T161154Z`, `conf/service.env.bak-20260918125106`, `conf/service.env.pre-f39-20260918T161154Z` |

## Terminal state: DONE
