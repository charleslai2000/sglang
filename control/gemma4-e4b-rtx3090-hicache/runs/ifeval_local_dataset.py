"""Load the official Google/IFEval train split from a pinned local JSONL snapshot."""

from pathlib import Path

from datasets import load_dataset

DATA_PATH = Path("/data/sglang-hicache/gemma4/ifeval/google_ifeval_train.jsonl")


def load(**kwargs):
    return load_dataset("json", data_files={"train": str(DATA_PATH)})
