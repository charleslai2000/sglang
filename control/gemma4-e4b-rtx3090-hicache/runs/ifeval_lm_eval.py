#!/usr/bin/env python3
"""Load the registered Gemma prompt adapter and invoke lm_eval's stock CLI."""

import sys

import ifeval_chat_adapter  # noqa: F401 - registers local Gemma chat adapter
from lm_eval.__main__ import cli_evaluate

if __name__ == "__main__":
    cli_evaluate()
