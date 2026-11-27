#!/usr/bin/env bash
# Reuses the R17 CUDA_PROFILER marker recipe: NCU --profile-from-start off,
# /start_profile .. /stop_profile delimit each phase inside the real scheduler.
set -euo pipefail
OUT=/data/sglang-hicache/gemma4/runs/20261127T-t010-hwprof
NCU=/usr/local/cuda-12.9/bin/ncu
METRICS="gpu__time_duration.sum,sm__cycles_elapsed.avg.per_second,sm__cycles_active.avg.pct_of_peak_sustained_elapsed,sm__throughput.avg.pct_of_peak_sustained_elapsed,sm__warps_active.avg.pct_of_peak_sustained_active,sm__pipe_tensor_cycles_active.avg.pct_of_peak_sustained_active,sm__pipe_fma_cycles_active.avg.pct_of_peak_sustained_active,sm__pipe_alu_cycles_active.avg.pct_of_peak_sustained_active,sm__inst_executed_pipe_lsu.avg.pct_of_peak_sustained_active,sm__inst_executed_pipe_xu.avg.pct_of_peak_sustained_active,smsp__issue_active.avg.pct_of_peak_sustained_active,smsp__inst_executed.avg.per_cycle_active,smsp__average_warps_issue_stalled_long_scoreboard_per_issue_active.ratio,smsp__average_warps_issue_stalled_barrier_per_issue_active.ratio,smsp__average_warps_issue_stalled_math_pipe_throttle_per_issue_active.ratio,smsp__average_warps_issue_stalled_lg_throttle_per_issue_active.ratio,smsp__average_warps_issue_stalled_mio_throttle_per_issue_active.ratio,smsp__average_warps_issue_stalled_wait_per_issue_active.ratio,smsp__average_warps_issue_stalled_not_selected_per_issue_active.ratio,l1tex__throughput.avg.pct_of_peak_sustained_elapsed,l1tex__t_sector_hit_rate.pct,lts__throughput.avg.pct_of_peak_sustained_elapsed,lts__t_sector_hit_rate.pct,dram__bytes_read.sum,dram__bytes_write.sum,gpu__dram_throughput.avg.pct_of_peak_sustained_elapsed,launch__registers_per_thread,launch__shared_mem_per_block_static,launch__occupancy_limit_registers,launch__occupancy_limit_shared_mem,launch__occupancy_limit_warps,launch__occupancy_limit_blocks"
sudo -n rm -f /tmp/nsight-compute-lock || true
exec sudo -n $NCU --profile-from-start off --target-processes all --replay-mode kernel \
  --kernel-name regex:"(_fwd_kernel|_fwd_grouped_kernel_stage1|Marlin|RMSNormKernel|fused_rope_kernel|act_and_mul_kernel|_gemma_qkv_rmsnorm_kernel)" \
  --metrics "$METRICS" --clock-control none \
  --export "$OUT/ncu-detail" --force-overwrite \
  /home/ubuntu/venvs/sglang-3090/bin/python "$OUT/hw_capture.py" \
  --phases ext1024,ext1280,ext4096,long,dec8,dec16,dec32 --port 31406 --out "$OUT"
