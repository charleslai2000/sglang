# G1 E5M2 and SWA-boundary numerical run — 2026-10-23

## Evidence binding

Fresh actual RTX3090 services under `/tmp/f1-r16b-gpu-exclusive.lock`; pinned checkpoint revision `6cd26aaa2357fb2bad8c51699a7558a4d1a965bb`, safetensors SHA-256 `19d89d2a4b3e401a3eae75ec08ab112810421a036c91d8c8226b686be7fe0c5d`. Run root: `/data/sglang-hicache/gemma4/runs/20261023T203234Z-e5m2-swa-boundary/`. Each E5M2 and BF16 service captured full 42 layer outputs, final norm and logits; each target Forward is a complete EXTEND with exact prompt IDs and positions 1..N, independently bound RID and Forward UUID. Matching frozen exact-ID / positions HF logits oracle is `/data/sglang-hicache/gemma4/runs/20261022T065916Z-e5m2-swa-boundary/oracle-n{510..514}.pt`. This is same-prompt and same-position per N; it does not splice service runs. E5M2 run completed, both servers shut down, GPU returned to 1 MiB and lock released.

## Matched BF16 and E5M2 errors against HF

Errors are full 262,144-logit vectors, no tolerance has been enlarged for this run.

| N | BF16 max / mean / RMSE / rel-L2 | E5M2 max / mean / RMSE / rel-L2 | BF16/HF greedy | E5M2/HF greedy |
|---:|---|---|---|---|
| 510 | 1.6935 / .3524 / .4237 / .10564 | 2.0633 / .3744 / .4624 / .11529 | 131865 / 131865 | 131865 / 131865 |
| 511 | .7918 / .1514 / .1849 / .05169 | 1.1256 / .1985 / .2478 / .06927 | 568 / 568 | 568 / 568 |
| 512 | 3.0655 / .5049 / .6345 / .20965 | 2.8524 / .4818 / .6003 / .19835 | 107 / 236761 | 107 / 236761 |
| 513 | 1.1297 / .3528 / .3844 / .11739 | 2.0068 / .3810 / .4727 / .14437 | 204064 / 204064 | 238247 / 204064 |
| 514 | 2.9221 / 1.3502 / 1.3967 / .25989 | 4.0161 / 1.6938 / 1.7545 / .32647 | 236761 / 527 | 236761 / 527 |

Same-run E5M2 vs BF16 max/mean/RMSE/rel-L2 are respectively N510 `1.2718/.1957/.2464/.06298`, N511 `1.6019/.2160/.2708/.07690`, N512 `1.5407/.2530/.3189/.10202`, N513 `1.5691/.2139/.2711/.08479`, N514 `1.6640/.3636/.4242/.09837`. Greedy changes only at N513 (E5M2 `238247`, BF16 `204064`). This confirms the cache dtype can change a decision near the SWA boundary; it is not a generic cache-path pass.

## Interpretation

Neither E5M2 nor the BF16 reference passes the existing numerical acceptance guards at all lengths. N512 and N514 BF16 already diverge from HF, so lower E5M2 error than BF16 at N512 does not establish correctness. At N513, E5M2 increases error and changes the greedy token vs both BF16 and HF. At N514 both service cache types choose a different greedy token than HF, and E5M2 error is larger. E5M2 is **NOT ACCEPTED**; shared-KV/SWA correctness is not certified by these full-forward measurements. No production math change is justified from dtype deltas alone.

The run proves real paired E5M2/BF16 service execution and complete captures around N=512; it does not explain their source, establish a standalone FP8 tolerance, or replace a same-forward cache-slot/scale attribution. Continue the known final-hidden upstream path and cache semantics independently. Full raw artifacts, request/response IDs, exact captures, per-N service logits hashes, and earlier independent HF oracle files are retained at the paths above.
