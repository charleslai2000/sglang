#!/usr/bin/env python3
import gsm8k_completion_adapter  # noqa: F401
import score_gsm8k_text  # noqa: F401
from lm_eval.__main__ import cli_evaluate

if __name__ == "__main__":
    cli_evaluate()
