#!/usr/bin/env bash
# Option B relaunch (coordinator ruling): env-layer path override to sglang-patch, frozen script untouched.
export CUDA_HOME=/root/miniconda3/envs/sglang-patch/lib/python3.10/site-packages/nvidia/cu13
export CPLUS_INCLUDE_PATH=/root/miniconda3/envs/sglang-patch/include
export LIBRARY_PATH=/root/miniconda3/envs/sglang-patch/lib
export LD_LIBRARY_PATH=/root/miniconda3/envs/sglang-patch/lib:${CUDA_HOME}/lib
export PATH=/root/miniconda3/envs/sglang-patch/bin:$PATH
export L3_BACKEND=extent STORAGE_DIR=/data/l3/hicache-prod MAX_SIZE=160G MIN_FREE=10G SGLANG_PORT=8024
echo "=== pre-launch resolved env ===" > /root/prod-deploy/relaunch-e1.env
echo "CUDA_HOME=$CUDA_HOME" >> /root/prod-deploy/relaunch-e1.env
echo "CPLUS_INCLUDE_PATH=$CPLUS_INCLUDE_PATH" >> /root/prod-deploy/relaunch-e1.env
echo "LIBRARY_PATH=$LIBRARY_PATH" >> /root/prod-deploy/relaunch-e1.env
echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH" >> /root/prod-deploy/relaunch-e1.env
echo "PATH=$PATH" >> /root/prod-deploy/relaunch-e1.env
bash /root/direct-launch-gate1.sh
