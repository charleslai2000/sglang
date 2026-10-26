#!/usr/bin/env python3
"""Register local GSM8K completion adapter before invoking the lm-eval CLI."""

import gsm8k_completion_adapter  # noqa: F401
import score_gsm8k_text  # registers gsm8k-strict-last filter
from lm_eval.__main__ import cli_evaluate

if __name__ == "__main__":
    cli_evaluate()
