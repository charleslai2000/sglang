"""Child-process hook for opt-in G1 boundary pre-sampling logits capture."""

import os

prefix = os.environ.get("G1_LOGITS_CAPTURE")
if prefix:
    import torch
    from sglang.srt.layers.logits_processor import LogitsProcessor

    _original = LogitsProcessor.forward
    _counter = 0

    def _capture(self, *args, **kwargs):
        global _counter
        out = _original(self, *args, **kwargs)
        logits = out.next_token_logits
        if logits is not None and not torch.cuda.is_current_stream_capturing():
            _counter += 1
            fb = args[3] if len(args) > 3 else kwargs.get("logits_metadata")
            lens = getattr(fb, "extend_seq_lens_cpu", None)
            tag = "unknown" if not lens else "-".join(map(str, lens))
            torch.save(
                {
                    "logits": logits.detach().float().cpu(),
                    "extend_seq_lens": lens,
                    "tag": tag,
                },
                f"{prefix}.captured-{os.getpid()}-{_counter:06d}-{tag}.pt",
            )
        return out

    LogitsProcessor.forward = _capture
