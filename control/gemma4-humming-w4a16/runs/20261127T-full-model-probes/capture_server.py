"""Private diagnostic launcher capturing one eager pre-sampling logits vector."""

import os, sys, torch
from sglang.srt.layers.logits_processor import LogitsProcessor
from sglang.srt.plugins import load_plugins
from sglang.srt.server_args import prepare_server_args
from sglang.srt.utils import kill_process_tree

capture = os.environ["T012_LOGITS_PATH"]
original = LogitsProcessor.forward
saved = False


def hooked(self, *args, **kwargs):
    global saved
    out = original(self, *args, **kwargs)
    logits = out.next_token_logits
    if (
        logits is not None
        and not saved
        and not torch.cuda.is_current_stream_capturing()
    ):
        torch.save(logits.detach().float().cpu(), capture)
        saved = True
    return out


def main():
    LogitsProcessor.forward = hooked
    # This marker crosses spawn into the scheduler and proves HummingLinearMethod
    # actually processes checkpoint layers (the generic load log reports source
    # quantization metadata, not necessarily the chosen backend implementation).
    from sglang.srt.layers.quantization.humming import HummingConfig, HummingLinearMethod
    get_quant_method = HummingConfig.get_quant_method

    def report_quant_method(self, layer, prefix):
        method = get_quant_method(self, layer, prefix)
        with open(os.environ["T012_HUMMING_MARKER"], "a") as f:
            f.write(f"method\\t{prefix}\\t{type(method).__name__ if method is not None else 'None'}\\n")
        return method

    HummingConfig.get_quant_method = report_quant_method
    process_weights = HummingLinearMethod.process_weights_after_loading

    def report_humming_layer(self, layer):
        with open(os.environ["T012_HUMMING_MARKER"], "a") as f:
            f.write(f"{getattr(layer, 'prefix', '<layer>')}\t{layer.input_size_per_partition}\t{layer.output_partition_sizes_sum}\t{getattr(self.weight_schema, 'quant_method', type(self.weight_schema).__name__)}\n")
        return process_weights(self, layer)

    HummingLinearMethod.process_weights_after_loading = report_humming_layer
    load_plugins()
    server_args = prepare_server_args(sys.argv[1:])
    try:
        from sglang.launch_server import run_server

        run_server(server_args)
    finally:
        kill_process_tree(os.getpid(), include_parent=False)


if __name__ == "__main__":
    main()
