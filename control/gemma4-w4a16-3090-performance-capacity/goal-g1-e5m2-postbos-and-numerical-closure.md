# G1 E5M2 post-BOS quality and N512-514 numerical closure

## Goal
At base commit `8eea0bc89e51ffc6f6da62988cc6217532ceb9bc`, evaluate W4A16 with E5M2 KV under the corrected explicit-Gemma-BOS protocol, paired to the already accepted per-item BF16-KV run. Separately rebuild reproducible N=512/513/514 probes and decide numerical correctness using logits, selected-token logprobs, greedy IDs and continuous decoding; repair confirmed defects and recheck.

## Scope and constraints
Only current working tree/branch. Do not rerun BF16 full GSM8K or any performance matrix. No T004 Q4_0/MMQ reactivation; keep it paused. Do not infer numerical correctness from GSM8K aggregate. Preserve frozen BF16 evidence; exact prompt IDs must match the E5M2 arm. Label reconstructed guards as new probes if historical captures are absent; do not claim historical replay. Use exclusive `/tmp/f1-r16b-gpu-exclusive.lock` for every GPU operation, clean services/ports/lock after each; user authorizes GPU use. Commit/push small coherent changes as earned. E5M2 remains experimental/NOT ACCEPTED until numerical acceptance. N512/513/514 guards remain independent.

## Completion
Post-BOS E5M2 full GSM8K 1,319 score, paired 4-cell table/CI and generation divergence audit; reproducible BF16/E5M2 guard comparisons with full first-step logits, selected-token logprobs, greedy IDs and bounded continuous decode; concrete defect fixed and affected tests repeated, or residual issue documented as NOT ACCEPTED; report exact commits/remote sync and clean GPU state.