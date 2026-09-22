Status: DONE
Work area: experiments
Objective: Reproduce exact serving Marlin B=8/B=16 kernel shapes in an isolated benchmark using the existing production binding, with correctness and NCU resource-signature gates.
Inputs: T004 NCU reports; Falcon config; GPTQ-Marlin binding/source; existing quantization helpers.
Completion: Exact variants/shapes reproduced at B=8/B=16; correctness passes; isolated NCU metrics reproduce key production signature; no optimization.
Result: PASS. Reconstructed `(M,N,K)=(8/16,12288,3072)`, BF16, uint4b8, group_size=128, act_order=true, is_k_full=true, with qweight [192,24576], scales [24,12288], g_idx/sort [3072]. Existing `gptq_marlin_gemm` produced exact T004 symbols and 82x256 geometry. Correctness relative mean absolute error was 1.90e-6 B8 and 2.07e-6 B16. Valid isolated NCU signatures matched T004: registers 96/148, shared memory ~101.38 KiB, occupancy ~16.6%, DRAM 73.60%/62.86%, L2 36.86%/37.44%, eligible warps 0.38/0.29. Report: `T006-REPORT.md`.
Remaining: Owner review; T007 may first investigate shared-memory/tile-staging footprint offline. No optimization authorized by T006.
