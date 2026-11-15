"""Test-only launcher to save each pre-sampling next-token logits tensor."""

import os, runpy, sys, torch
from sglang.srt.layers.logits_processor import LogitsProcessor

original = LogitsProcessor.forward
path = os.environ["G1_LOGITS_CAPTURE"]
count = 0


def hooked(self, *args, **kwargs):
    global count
    out = original(self, *args, **kwargs)
    x = out.next_token_logits
    if x is not None:
        count += 1
        md = args[3] if len(args) > 3 else kwargs.get("logits_metadata")
        n = getattr(md, "extend_seq_lens_cpu", None)
        tag = "unknown" if not n else "-".join(map(str, n))
        torch.save(
            {"logits": x.detach().float().cpu(), "extend_seq_lens": n, "tag": tag},
            f"{path}.captured-{count:06d}-{tag}.pt",
        )
    return out


LogitsProcessor.forward = hooked
sys.argv = ["sglang.launch_server", *sys.argv[1:]]
runpy.run_module("sglang.launch_server", run_name="__main__")
