"""Opt-in capture of the exact position tensor presented to Gemma4 RoPE."""

import json
import os
from pathlib import Path
import torch


def install():
    if os.getenv("GEMMA4_ROPE_POSITION_CAPTURE") != "1":
        return
    from sglang.srt.layers.rotary_embedding.rope_variant import Gemma4RotaryEmbedding

    original = Gemma4RotaryEmbedding.forward_cuda

    def wrapped(self, positions, query, key, *args, **kwargs):
        result = original(self, positions, query, key, *args, **kwargs)
        out_dir = os.getenv("GEMMA4_ROPE_POSITION_OUT")
        if out_dir:
            record = {
                "rotary_dim": self.rotary_dim,
                "head_size": self.head_size,
                "positions_shape": list(positions.shape),
                "positions_dtype": str(positions.dtype),
                "positions": positions.detach().cpu().tolist(),
                "query_shape": list(query.shape),
                "key_shape": list(key.shape),
                "query_device": str(query.device),
                "query_dtype": str(query.dtype),
                "positions_sha256": __import__("hashlib").sha256(positions.detach().cpu().contiguous().numpy().tobytes()).hexdigest(),
            }
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            target = Path(out_dir) / f"rope-dim{self.rotary_dim}-pid{os.getpid()}.jsonl"
            with target.open("a") as f:
                f.write(json.dumps(record) + "\n")
        return result

    Gemma4RotaryEmbedding.forward_cuda = wrapped


install()
