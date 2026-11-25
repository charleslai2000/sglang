#!/usr/bin/env python3
"""Replay the existing deterministic generated-shared-prefix dataset through SGLang's benchmark client."""
import asyncio,sys
from pathlib import Path
ROOT=Path('/tmp/sglang-f1-r16b-clean');RUN=Path('/home/ubuntu/workspaces/3rdparty/sglang-hicache/control/falcon-h1-3090-hicache-perf/runs/R16B-20261011T1230Z')
sys.path.insert(0,str(ROOT/'python'))
from sglang.benchmark.serving import get_tokenizer,get_dataset,resolve_base_url,async_request_sglang_generate,build_request_func_input,benchmark,ASYNC_REQUEST_FUNCS
import argparse,random,numpy as np,json,os
from sglang.benchmark.serving import benchmark as run_bench
from sglang.benchmark.datasets import get_dataset as dataset
from sglang.benchmark.serving import main as _unused
# use public CLI implementation through subprocess with supported GSP dataset; kept as helper for frozen manifest.
if __name__=='__main__':
 raise SystemExit('use run_gsp.sh; this module documents the intended data path')
