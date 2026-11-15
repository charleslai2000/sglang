"""Test-only launcher to save pre-sampling logits in an isolated diagnostic run."""

import os, sys, torch
from sglang.srt.layers.logits_processor import LogitsProcessor
from sglang.srt.server_args import prepare_server_args
from sglang.srt.plugins import load_plugins
from sglang.srt.utils import kill_process_tree

path = os.environ.get("G1_LOGITS_CAPTURE")
if not path:
    raise RuntimeError("G1_LOGITS_CAPTURE must name a private output prefix")
original = LogitsProcessor.forward
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
load_plugins()
server_args = prepare_server_args(sys.argv[1:])
try:
    from sglang.launch_server import run_server

    run_server(server_args)
finally:
    kill_process_tree(os.getpid(), include_parent=False)
