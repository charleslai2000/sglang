#!/usr/bin/env python3
"""Validate delayed Nsight collection with a real CUDA fork child."""

import os
import signal
import time

pid = os.fork()
if pid == 0:
    import torch

    x = torch.randn((2048, 2048), device="cuda")
    y = torch.randn_like(x)
    for _ in range(100):
        z = x @ y
        torch.cuda.synchronize()
        time.sleep(0.02)
    print(float(z[0, 0]), flush=True)
    os._exit(0)

time.sleep(3)
os.kill(os.getppid(), signal.SIGUSR1)
os.waitpid(pid, 0)
