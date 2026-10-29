# G1 Residual/RMSNorm A/B diagnostic — review snapshot

**Status: NOT VALIDATED. G1 remains FAILED / NOT ACCEPTED.** The env-gated diagnostic is off by default. No production math conclusion is claimed.

## Runner and target capture

The external runner used for the last attempt is `/data/sglang-hicache/gemma4/runs/20261029T-residual-rounding-bf16-ab/run-ab.sh`; config is pinned model SHA `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`, IDs `[6974,886,2822,13315,1003,506,7217,236761]`, positions `1..8`, A port 31251, B port 31252, lock `/tmp/f1-r16b-gpu-exclusive.lock`. The run used `--context-length 1024 --max-running-requests 1 --mem-fraction-static .82 --disable-radix-cache --kv-cache-dtype bf16 --attention-backend triton --cuda-graph-max-bs-decode 1 --skip-server-warmup`.

A target Forward is RID `799796d3b5254837ae2f434fd96a4495`, UUID `9aeef60b3124418aa231eed89f6079d8`. Manifest: `/data/sglang-hicache/gemma4/runs/20261029T-residual-rounding-bf16-ab/A/layers.9aeef60b3124418aa231eed89f6079d8.manifest`. Its FID-prefixed file set is `layers.9aeef60b3124418aa231eed89f6079d8.{finalnorm,layer_output.0..41,logits,manifest,prenorm}` under `/data/sglang-hicache/gemma4/runs/20261029T-residual-rounding-bf16-ab/A/`. The current validator accepted this target with `artifact_count=45` when passed the matching model-fingerprint env.

B has no FID-prefixed captures; only `/data/sglang-hicache/gemma4/runs/20261029T-residual-rounding-bf16-ab/B/{server.log,request.json,response.json}` remain. Thus no A/B result exists.

## First failure and other confirmed errors

A preserved runner invocation emitted its first shell assertion:

```text
A missing layer 0
```

The visible saved runner at `/data/sglang-hicache/gemma4/runs/20261029T-residual-rounding-bf16-ab/run-ab.sh` currently parses FID using `fid=${fwd##*.}` from a path ending in `.manifest`; that expression yields `manifest`, not the UUID. Its subsequent check would look for `layers.manifest.layer_output.0`, whereas the actual A target is `layers.9aeef60b3124418aa231eed89f6079d8.layer_output.0`. The saved runner's artifact check is therefore demonstrably wrong, and it is consistent with the observed message, but the run directory is shared across runner revisions and the invocation-time script bytes were not snapshotted; do not claim the exact historical message is proven to come from this exact script version. The preserved target A artifacts themselves are complete and validator-PASS; B has no captures.

A subsequent runner revision emitted `A complete-forward capture missing` while searching for the manifest. The shared run tree has artifacts from multiple invocations, so that message cannot be tied to a unique preserved runner version from the current files. Do not infer a second root cause from it.

A separate earlier hook failure is proven by `A/server.log` in this same run tree: `RuntimeError: component capture has no per-forward UUID` on a health-check Forward. Another earlier attempt logged `FileExistsError` for `component.<RID>.<FID>.layer0.decoder_layer_output.json`, caused by the watched-layer output capture plus all-layer output capture both invoking the same synchronous `save_gemma4_capture()` destination. The duplicate invocation has since been removed. `save_gemma4_capture()` itself is synchronous, refuses existing destinations and publishes via hard link; no async writer is used.

## Validator/PLE check

The original `verify-forward-capture.py` exact artifact set rejected any FID-prefixed `.ple.<layer>` sidecar. The submitted validator now handles this via explicit `--allow-ple`, validating sidecar identity, boundary, shape, and finite values; default exact-set behavior remains. The captured A target has no `.ple.*` artifact in its `layers` base directory (component PLE sidecars are elsewhere), so this was a potential code conflict, not the cause of the target A failure.

## Status

A/B **NOT VALIDATED**; no B Forward, no matched logits comparison and no GSM8K causal check. No threshold/oracle change. Review artifacts exclude weights and tensor payloads.
