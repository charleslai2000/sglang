# G1 E5M2 vs BF16 numerical comparison and CUDA Graph Decode pair (2026-11-15)

## Saved eager full-logit comparison

Computed directly from the six existing SGLang full-vocabulary first-step captures/results for the exact same new N=512/513/514 fixtures; no request rerun for eager data. Vocab rows are 262,144. For each row the E5M2 and BF16 prompt token IDs and fixture SHA-256 match.

| N | BF16/E5M2 top-1 | top-2 BF16/E5M2 | margin BF16→E5M2 | max |Δlogit| | logits RMSE | relative L2 | selected-token logprob BF16→E5M2 | Δlogprob |
|---:|---|---|---:|---:|---:|---:|---|---:|
| 512 | 236810 / 236810 | 236778 / 236778 | 8.9373 → 9.0319 | 0.6367 | 0.14527 | 0.04679 | −0.00049262 → −0.00049588 | −0.00000326 |
| 513 | 808 / 808 | 578 / 578 | 1.5890 → 1.5001 | 1.0580 | 0.20660 | 0.05491 | −0.19368265 → −0.20923139 | −0.01554874 |
| 514 | 236743 / 236743 | 2986 / 2986 | 7.8854 → 7.6672 | 0.6992 | 0.16870 | 0.04619 | −0.00074843 → −0.00091641 | −0.00016798 |

“Selected-token” here means the shared BF16/E5M2 greedy top-1, also the first returned generated token. Top-1 is unchanged in all three samples. The smallest BF16 margin is N513 (1.589 logit units); E5M2 narrows it by 0.089 to 1.500 but does not flip the winner. At N512 E5M2 slightly widens the margin; at N514 it narrows the margin by 0.218. This is a three-input observation, not an estimate of general flip probability.

Runner: `runs/analyze_g1_eager_capture_pair.py`; output `eager-pair-delta.json` beside the inputs in `/data/sglang-hicache/gemma4/runs/20261115T-g1-e5m2-boundary-new/`.

## Real CUDA Graph Decode same-input pair

Runner `runs/run_g1_graph_pair.sh` started two isolated services (same W4A16 checkpoint, SGLang source/runtime artifacts, attention backend, one active request, radix cache disabled), BF16-KV on port 31181 and E5M2-KV on 31182. Both explicitly enabled full Decode graph backend at bs=1 and disabled Prefill graph. Server logs confirm successful bs=1 Decode graph capture and subsequent decode batches with `cuda graph: True`. Each of N=512/513/514 was submitted twice per dtype (deterministic repeatability check); all 32-token outputs repeated identically within each arm.

| N | BF16/E5M2 32-token IDs identical? | mean |Δ selected-token logprob| | max |
|---:|---|---:|---:|
| 512 | yes | 0.02892 | 0.28720 |
| 513 | yes | 0.01574 | 0.17633 |
| 514 | yes | 0.02124 | 0.34309 |

The pair includes initial prefill (not graph) and subsequent Decode where log lines explicitly confirm graph replay. Exact output-token IDs matched across KV dtypes for all 32 steps; no first divergence. These graph requests did not capture full logits, so no graph-vs-eager full-distribution delta is claimed. Eager-vs-graph comparison is only at greedy token IDs and API-returned selected-token logprobs, with matching inputs. Logprob differences are expected to be path/numerics-sensitive and are not a validated acceptance metric yet.

Evidence: `/data/sglang-hicache/gemma4/runs/20261115T-g1-e5m2-graph-pair/` (server logs, model info, raw request outputs, graph status and GPU/port cleanup). GPU returned to 0% / 1 MiB; ports clear; exclusive lock released.

## Interpretation

Across these three inputs, observed full-logit quantization error did not alter first-token choice; the narrowest margin remained 1.50 after E5M2 perturbation. No greedy divergence appeared in 32-token eager or real-graph continuations. E5M2 does perturb logit distributions and selected logprobs, with the largest eager shared-token logprob delta 0.01555 at N513; Decode-graph 32-step paired mean absolute logprob deltas are 0.01574–0.02892 and maxima 0.176–0.343. Only three prefixes and a bounded horizon were tested, so these are empirical samples for the upcoming tolerance decision, not a complete guard or proof of numerical equivalence. E5M2 remains NOT ACCEPTED pending a separately specified tolerance and broader correctness acceptance.
