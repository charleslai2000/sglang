"""Offline GSM8K JSONL source for lm-eval; pin data via external hashes."""

import json
import os
from pathlib import Path

from datasets import Dataset, DatasetDict


def load(**kwargs):
    root = Path(os.environ["GSM8K_DATA_DIR"])
    result = {}
    for split in ("train", "test"):
        path = root / f"{split}.jsonl"
        with path.open() as f:
            result[split] = [json.loads(line) for line in f if line.strip()]
    return DatasetDict({k: Dataset.from_list(v) for k, v in result.items()})
