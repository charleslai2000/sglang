# T012 Humming W4A16 plan

Status: DONE. Weight/correctness gate PASS (`runs/T012-CTLOADER-HUMMING-QUALIFICATION.md`); original C-8 L1-only **+12.71%** mean TPS and the production three-tier stack **+8.90%** (`runs/T012-C8-AB-AND-TIERS.md`). The scoped opt-in is retained behind `SGLANG_CTWNA16_HUMMING` (default off).

## Established inputs
Frozen source `c4f6b50da7940ff28fefae2eb3fb0b71eb1014cc`; checkpoint is group-32 symmetric INT4 with BF16 scales/compute. Humming 0.1.12 runs on RTX 3090 SM86; prior actual-weight isolated results are archived in `runs/T012-SHAPE-COMPATIBILITY-AND-BENCHMARK.md` and will not be repeated.

## Decisive evidence
A paired server run with explicit `--quantization humming` (FA2 disabled; same checkpoint, BF16 compute, FP8-E5M2 KV, Triton attention, Decode graph bs32) completed and served all probes. Humming selected `HummingLinearMethod` and its decode graph captured/replayed. Greedy outputs matched Marlin, but this is not correctness evidence: `Gemma4ForConditionalGeneration.load_weights` reported 271 uninitialized Text Core `*.weight` parameters (Marlin had zero of those; its 18 missing entries were the shared K-norm parameters). The Humming compressed-tensors adapter creates a schema whose packed checkpoint key is `weight_packed`, while Gemma4's stacked loader mappings look for `.weight` and therefore skip the packed tensors; Humming then converts its empty initialized placeholders to packed form. Original and graph argmax IDs can match despite this failure.

Run artifacts: `runs/20261127T-full-model-probes/retry5-wrapper.log`, Humming `server.log` and `probes.json`. Wrapper exit=0; GPU returned to 1 MiB/0%, port 31412 released, and exclusive lock free. The Humming diagnostic marker was not created in this run due to a literal backslash-n in the writer, but config dispatch is confirmed by the missing-weight names and the live Humming graph path.

## Implementation (landed)
Environment-controlled opt-in branch in `CompressedTensorsWNA16.process_weights_after_loading`, before any Marlin repack/workspace mutation, plus a dispatch branch in `apply_weights`. It mirrors Humming's own post-load conversion: CT's already-loaded `weight_packed`/`weight_scale` are passed to Humming's compressed-tensors schema conversion and transform, the CT parameters are dropped before the Humming ones are installed (no duplicate residence), and `locks`/compute config are set. `create_weights`, the fused/sharded loader, `Gemma4.load_weights`, Marlin and every kernel are unchanged; Marlin remains the default.

## Audit (qualification only)
`runs/20261127T-ctloader-postload/auditlib/sitecustomize.py` (run-scoped `PYTHONPATH`, never imported by production) maps parameters to their `named_parameters()` names, then records per-parameter SHA256 of the loaded `weight_packed`/`weight_scale` before conversion in both arms, plus dispatch counters, the probe logits and replay evidence. No hashing or audit code exists in `python/`.

## Outcome
C-8 L1-only (`runs/20261127T-c8-l1only-ab/`, arms `off`/`on1`/`on2`, frozen argv, no audit instrumentation): 653.89 → 736.49/737.51 official TPS, +12.63%/+12.79%, decode device −15.8%, extend −7.2%, 800/800 with an identical payload multiset, KV capacity −0.19% and not binding. Three-tier production stack: 570.65 → 621.42 TPS (+8.90%), identical payloads and L1 cached tokens, same-order L2/extent activity, capacity not reduced.

Retained as an opt-in flag with Marlin as the default; enabling it in production is a launch-time `SGLANG_CTWNA16_HUMMING=1`. FA2 remains excluded. Preserved unrelated T011 work throughout.
