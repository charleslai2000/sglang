"""Record the checkpoint's Text Core WNA16 tensors for the T012 coverage gate.

Enumerates every ``language_model.*`` ``weight_packed`` / ``weight_scale`` /
``weight_shape`` tensor straight from the safetensors file, hashes the payload
bytes, and sums element counts. The paired run's per-layer audit totals must match
these sums exactly, which rules out a fused shard being dropped or loaded twice.
"""

import hashlib
import json
import sys

import torch
from safetensors import safe_open

TEXT_CORE_MARKERS = ("language_model.",)
SUFFIXES = ("weight_packed", "weight_scale", "weight_shape")


def sha256_tensor(tensor):
    host = tensor.contiguous().view(torch.uint8)
    return hashlib.sha256(host.numpy().tobytes()).hexdigest()


def main(model_dir, out_path):
    handle = safe_open(f"{model_dir}/model.safetensors", framework="pt", device="cpu")
    keys = sorted(
        key
        for key in handle.keys()
        if TEXT_CORE_MARKERS[0] in key and key.endswith(SUFFIXES)
    )

    entries = []
    totals = {suffix: {"numel": 0, "tensors": 0} for suffix in SUFFIXES}
    for key in keys:
        tensor = handle.get_tensor(key)
        suffix = key.rsplit(".", 1)[1]
        totals[suffix]["numel"] += int(tensor.numel())
        totals[suffix]["tensors"] += 1
        entries.append(
            {
                "name": key.replace("model.language_model.", "language_model."),
                "suffix": suffix,
                "shape": [int(v) for v in tensor.shape],
                "dtype": str(tensor.dtype),
                "sha256": sha256_tensor(tensor),
            }
        )
        del tensor

    with open(out_path, "w") as f:
        json.dump({"totals": totals, "tensors": entries}, f, indent=1, sort_keys=True)
    print("checkpoint_textcore_w4a16", json.dumps(totals, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
