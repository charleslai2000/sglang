#!/usr/bin/env python3
"""Run the existing measured T004 fixture against the profiler-managed server."""
from pathlib import Path
import sys

run_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(run_dir))
import driver

driver.run_ab_measured()
