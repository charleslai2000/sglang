# T002 — W4A16 BF16/E5M2 GSM8K full pair

Status: DONE
Work area: experiments
Objective: Complete matched official 1,319-item GSM8K comparison and retain item-level evidence for W4A16 BF16 KV vs E5M2 KV.
Inputs: Branch `3090-24g-hicache`, source `4c1673b5c7cfffcd1dc0bd3ef6104dc12af90472`; official five-shot GSM8K protocol.
Completion: Full run both arms, paired item scores/CI, protocol/history audit, valid JSONL sample+request-audit linkage, raw evidence hashes, cleanup.
Result: BF16 896/1,319 (67.930%); E5M2 890/1,319 (67.475%). Independently rescored cells both-correct/both-wrong/BF16-only/E5M2-only = 829/362/67/61; delta −0.455 pp, paired bootstrap 95% CI [−2.199,+1.213] pp (20,000, seed 20261114). Each arm's rebuilt JSONL has 1,319 entries and joins to raw request audit on prompt/output IDs, returned text, stop and finish. Historical Oct-30 81.12% corrected-stop raw JSONL is absent; no historical item-level re-score was possible. Its report says same `Question:`+EOS stops and first-`####` extraction, but source/service differ. Historical Oct-26 stop-attribution report confirms adding `Question:` changed generations (all flipped decoded outputs diverged before boundary); only 1/304 BF16 and 0/327 E5M2 flips had first answer after boundary, so score shift is not simple suffix trimming. Do not attribute Oct-30/current score gap to a single cause. Full evidence: `runs/GSM8K-E5M2-PAIRED-20261114.md` and `/data/sglang-hicache/gemma4/runs/20261114T-gsm8k-w4a16-bf16-e5m2-paired/`.
Remaining: No task items. E5M2 remains experimental opt-in and BF16 remains default; no general numerical equivalence or N512/513/514 guard closure claim.
