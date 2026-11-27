# Adapted from https://github.com/vllm-project/vllm/tree/main/vllm/model_executor/layers/quantization/compressed_tensors
# SPDX-License-Identifier: Apache-2.0

# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
import json
import logging
from typing import Callable, Optional

import torch
from compressed_tensors.quantization import ActivationOrdering

from sglang.srt.environ import envs

# yapf conflicts with isort for this block
# yapf: disable
from sglang.srt.layers.parameter import (
    BasevLLMParameter,
    ChannelQuantScaleParameter,
    GroupQuantScaleParameter,
    PackedColumnParameter,
    PackedvLLMParameter,
    RowvLLMParameter,
    permute_param_layout_,
)
from sglang.srt.layers.quantization.compressed_tensors.schemes import (
    CompressedTensorsLinearScheme,
)
from sglang.srt.layers.quantization.marlin_utils import (
    MarlinLinearLayerConfig,
    apply_gptq_marlin_linear,
    check_marlin_supports_shape,
    marlin_is_k_full,
    marlin_make_empty_g_idx,
    marlin_make_workspace,
    marlin_permute_scales,
    marlin_repeat_scales_on_all_ranks,
    marlin_sort_g_idx,
    marlin_zero_points,
)
from sglang.srt.layers.quantization.utils import (
    get_scalar_types,
    replace_parameter,
    unpack_cols,
)
from sglang.srt.utils import is_cuda

_is_cuda = is_cuda()

if _is_cuda:
    from sglang.kernels.ops.quantization.gptq_marlin_repack import gptq_marlin_repack


ScalarType, scalar_types = get_scalar_types()

logger = logging.getLogger(__name__)

__all__ = ["CompressedTensorsWNA16"]
WNA16_SUPPORTED_TYPES_MAP = {
    4: scalar_types.uint4b8,
    8: scalar_types.uint8b128
}
WNA16_ZP_SUPPORTED_TYPES_MAP = {4: scalar_types.uint4, 8: scalar_types.uint8}
WNA16_SUPPORTED_BITS = list(WNA16_SUPPORTED_TYPES_MAP.keys())


class CompressedTensorsWNA16(CompressedTensorsLinearScheme):
    _kernel_backends_being_used: set[str] = set()

    def __init__(self,
                 strategy: str,
                 num_bits: int,
                 group_size: Optional[int] = None,
                 symmetric: Optional[bool] = True,
                 actorder: Optional[ActivationOrdering] = None):

        self.pack_factor = 32 // num_bits
        self.strategy = strategy
        self.symmetric = symmetric
        self.group_size = -1 if group_size is None else group_size
        self.has_g_idx = actorder == ActivationOrdering.GROUP

        if self.group_size == -1 and self.strategy != "channel":
            raise ValueError("Marlin kernels require group quantization or "
                             "channelwise quantization, but found no group "
                             "size and strategy is not channelwise.")

        if num_bits not in WNA16_SUPPORTED_TYPES_MAP:
            raise ValueError(
                f"Unsupported num_bits = {num_bits}. "
                f"Supported num_bits = {WNA16_SUPPORTED_TYPES_MAP.keys()}")

        self.quant_type = (WNA16_ZP_SUPPORTED_TYPES_MAP[num_bits]
                           if not self.symmetric else
                           WNA16_SUPPORTED_TYPES_MAP[num_bits])

    @classmethod
    def get_min_capability(cls) -> int:
        # ampere and up
        return 80

    def create_weights(self, layer: torch.nn.Module, output_size: int,
                       input_size: int, output_partition_sizes: list[int],
                       input_size_per_partition: int,
                       params_dtype: torch.dtype, weight_loader: Callable,
                       **kwargs):

        output_size_per_partition = sum(output_partition_sizes)

        self.kernel_config = MarlinLinearLayerConfig(
            full_weight_shape=(input_size, output_size),
            partition_weight_shape=(
                input_size_per_partition,
                output_size_per_partition,
            ),
            weight_type=self.quant_type,
            act_type=params_dtype,
            group_size=self.group_size,
            zero_points=not self.symmetric,
            has_g_idx=self.has_g_idx
        )

        # If group_size is -1, we are in channelwise case.
        group_size = self.group_size if self.group_size != -1 else input_size
        row_parallel = (input_size != input_size_per_partition)
        partition_scales = not marlin_repeat_scales_on_all_ranks(
            self.has_g_idx, self.group_size, row_parallel)

        scales_and_zp_size = input_size // group_size

        if partition_scales:
            assert input_size_per_partition % group_size == 0
            scales_and_zp_size = input_size_per_partition // group_size

        weight = PackedvLLMParameter(input_dim=1,
                                     output_dim=0,
                                     weight_loader=weight_loader,
                                     packed_factor=self.pack_factor,
                                     packed_dim=1,
                                     data=torch.empty(
                                         output_size_per_partition,
                                         input_size_per_partition //
                                         self.pack_factor,
                                         dtype=torch.int32,
                                     ))

        weight_scale_args = {
            "weight_loader":
            weight_loader,
            "data":
            torch.empty(
                output_size_per_partition,
                scales_and_zp_size,
                dtype=params_dtype,
            )
        }

        zeros_args = {
            "weight_loader":
            weight_loader,
            "data":
            torch.zeros(
                output_size_per_partition // self.pack_factor,
                scales_and_zp_size,
                dtype=torch.int32,
            )
        }

        if not partition_scales:
            weight_scale = ChannelQuantScaleParameter(output_dim=0,
                                                      **weight_scale_args)

            if not self.symmetric:
                qzeros = PackedColumnParameter(output_dim=0,
                                               packed_dim=0,
                                               packed_factor=self.pack_factor,
                                               **zeros_args)
        else:
            weight_scale = GroupQuantScaleParameter(output_dim=0,
                                                    input_dim=1,
                                                    **weight_scale_args)
            if not self.symmetric:
                qzeros = PackedvLLMParameter(input_dim=1,
                                             output_dim=0,
                                             packed_dim=0,
                                             packed_factor=self.pack_factor,
                                             **zeros_args)

        # A 2D array defining the original shape of the weights
        # before packing
        weight_shape = BasevLLMParameter(data=torch.empty(2,
                                                          dtype=torch.int64),
                                         weight_loader=weight_loader)

        layer.register_parameter("weight_packed", weight)
        layer.register_parameter("weight_scale", weight_scale)
        layer.register_parameter("weight_shape", weight_shape)

        if not self.symmetric:
            layer.register_parameter("weight_zero_point", qzeros)

        # group index (for activation reordering)
        if self.has_g_idx:
            weight_g_idx = RowvLLMParameter(data=torch.empty(
                input_size_per_partition,
                dtype=torch.int32,
            ),
                                            input_dim=0,
                                            weight_loader=weight_loader)
            layer.register_parameter("weight_g_idx", weight_g_idx)

    # Checkpoints are serialized in compressed-tensors format, which is
    # different from the format the kernel may want. Handle repacking here.
    def process_weights_after_loading(self, layer: torch.nn.Module) -> None:
        if envs.SGLANG_CTWNA16_HUMMING.get():
            self._process_weights_after_loading_humming(layer)
            return

        # Default names since marlin requires empty parameters for these,
        # TODO: remove this requirement from marlin (allow optional tensors)
        self.w_q_name = "weight_packed"
        self.w_s_name = "weight_scale"
        self.w_zp_name = "weight_zero_point"
        self.w_gidx_name = "weight_g_idx"

        device = getattr(layer, self.w_q_name).device
        c = self.kernel_config

        check_marlin_supports_shape(
            c.partition_weight_shape[1],  # out_features
            c.partition_weight_shape[0],  # in_features
            c.full_weight_shape[0],  # in_features
            c.group_size,
        )

        row_parallel = c.partition_weight_shape[0] != c.full_weight_shape[0]
        self.is_k_full = marlin_is_k_full(c.has_g_idx, row_parallel)

        # Allocate marlin workspace.
        self.workspace = marlin_make_workspace(device)

        def _transform_param(
            layer: torch.nn.Module, name: Optional[str], fn: Callable
        ) -> None:
            if name is not None and getattr(layer, name, None) is not None:

                old_param = getattr(layer, name)
                new_param = fn(old_param)
                # replace the parameter with torch.nn.Parameter for TorchDynamo
                # compatibility
                replace_parameter(
                    layer, name, torch.nn.Parameter(new_param.data, requires_grad=False)
                )

        def transform_w_q(x):
            assert isinstance(x, BasevLLMParameter)
            permute_param_layout_(x, input_dim=0, output_dim=1, packed_dim=0)
            x.data = gptq_marlin_repack(
                x.data.contiguous(),
                perm=layer.g_idx_sort_indices,
                size_k=c.partition_weight_shape[0],
                size_n=c.partition_weight_shape[1],
                num_bits=c.weight_type.size_bits,
            )
            return x

        def transform_w_s(x):
            assert isinstance(x, BasevLLMParameter)
            permute_param_layout_(x, input_dim=0, output_dim=1)
            x.data = marlin_permute_scales(
                x.data.contiguous(),
                size_k=c.partition_weight_shape[0],
                size_n=c.partition_weight_shape[1],
                group_size=c.group_size,
            )
            return x

        if c.has_g_idx:
            g_idx, g_idx_sort_indices = marlin_sort_g_idx(
                getattr(layer, self.w_gidx_name)
            )
            _transform_param(layer, self.w_gidx_name, lambda _: g_idx)
            layer.g_idx_sort_indices = g_idx_sort_indices
        else:
            setattr(layer, self.w_gidx_name, marlin_make_empty_g_idx(device))
            layer.g_idx_sort_indices = marlin_make_empty_g_idx(device)

        if c.zero_points:
            grouped_k = (
                c.partition_weight_shape[0] // c.group_size if c.group_size != -1 else 1
            )
            _transform_param(
                layer,
                self.w_zp_name,
                lambda x: marlin_zero_points(
                    unpack_cols(
                        x.t(),
                        c.weight_type.size_bits,
                        grouped_k,
                        c.partition_weight_shape[1],
                    ),
                    size_k=grouped_k,
                    size_n=c.partition_weight_shape[1],
                    num_bits=c.weight_type.size_bits,
                ),
            )
        else:
            setattr(layer, self.w_zp_name, marlin_make_empty_g_idx(device))
        _transform_param(layer, self.w_q_name, transform_w_q)
        _transform_param(layer, self.w_s_name, transform_w_s)

    def _process_weights_after_loading_humming(self, layer: torch.nn.Module) -> None:
        """Convert CT's already-loaded WNA16 tensors to Humming before Marlin repack.

        The compressed-tensors loader has already put the checkpoint's packed
        INT4 words and BF16 group scales on this layer under the exact names a
        native Humming layer uses (``weight_packed`` / ``weight_scale`` /
        ``weight_shape``). This mirrors HummingLinearMethod's own post-load
        conversion instead of building a second loader or re-deriving the fused
        shard layout, so the kernel gets the very tensors Marlin would repack.
        """
        from humming.schema.compressed_tensors import CompressedTensorsWeightSchema
        from sglang.srt.layers.quantization import humming as humming_method

        humming_method._lazy_import_humming()
        HummingMethod = humming_method.HummingMethod

        prefix = getattr(layer, "prefix", "") or (
            f"<{type(layer).__name__} n={int(layer.weight_packed.shape[0])} "
            f"k={int(layer.weight_packed.shape[1]) * self.pack_factor}>"
        )
        required = ("weight_packed", "weight_scale")
        missing = [name for name in required if getattr(layer, name, None) is None]
        if missing:
            raise RuntimeError(
                f"Humming post-load requires the CT checkpoint tensors {missing} "
                f"on {prefix}; refusing to convert a partially loaded layer"
            )
        if self.has_g_idx or not self.symmetric:
            raise RuntimeError(
                f"Humming post-load opt-in requires symmetric INT4 without "
                f"activation-order indices, got {prefix}"
            )

        weight = layer.weight_packed
        scale = layer.weight_scale
        # The CT scheme never sets ``param_dtype`` on the layer (Humming's own
        # create_weights does). The checkpoint's scale dtype is the BF16 compute
        # dtype this layer was quantized for, so use it as the authority.
        param_dtype = scale.dtype
        layer.param_dtype = param_dtype
        # Derive the local partition shape from the tensors the unchanged loader
        # already filled; ``input_size_per_partition`` is only passed to
        # create_weights and not retained by every linear class.
        output_size = int(weight.shape[0])
        input_size = int(weight.shape[1]) * self.pack_factor
        output_partition_sizes = [int(v) for v in getattr(layer, "output_partition_sizes", [output_size])]
        # `weight_shape` is an optional bookkeeping parameter: several towers (and
        # some Text Core layers) never receive it from the checkpoint, so it is not
        # used as evidence here. The tensors themselves are validated by shape and,
        # in the paired run, by per-parameter SHA256.
        expected_weight_shape = (output_size, input_size // self.pack_factor)
        expected_scale_shape = (
            output_size,
            input_size // self.group_size if self.group_size != -1 else 1,
        )
        if tuple(weight.shape) != expected_weight_shape:
            raise RuntimeError(
                f"Humming post-load packed-weight shape mismatch on {prefix}: "
                f"actual={tuple(weight.shape)}, expected={expected_weight_shape}"
            )
        if tuple(scale.shape) != expected_scale_shape:
            raise RuntimeError(
                f"Humming post-load scale shape mismatch on {prefix}: "
                f"actual={tuple(scale.shape)}, expected={expected_scale_shape}"
            )

        schema = CompressedTensorsWeightSchema(
            quant_method="compressed-tensors",
            format="pack-quantized",
            type="int",
            num_bits=32 // self.pack_factor,
            strategy="group" if self.group_size != -1 else "channel",
            symmetric=True,
            group_size=self.group_size if self.group_size != -1 else None,
        )
        humming_schema, tensors = schema.convert_humming(
            tensors=dict(layer.state_dict()),
            shape_n_stacks=output_partition_sizes,
            shape_k_stacks=[input_size],
            param_dtype=param_dtype,
        )
        if tensors["weight"].dtype != torch.int32:
            raise RuntimeError("Humming conversion did not preserve packed INT4 storage")

        # Drop the CT storage parameters before installing the Humming ones so the
        # packed matrix is never resident twice. Humming's schema conversion only
        # re-views the same INT32 words, it does not requantize.
        for name in list(layer._parameters):
            if layer._parameters[name] is not None:
                delattr(layer, name)
        for name, tensor in tensors.items():
            setattr(layer, name, torch.nn.Parameter(tensor, requires_grad=False))
        del tensors

        layer.output_partition_sizes_sum = output_size
        HummingMethod.prepare_layer_meta(
            layer=layer,
            shape_n=output_size,
            shape_k=input_size,
            weight_schema=humming_schema,
            input_schema=None,
            pad_n_to_multiple=256,
            pad_k_to_multiple=128,
            has_bias=getattr(layer, "bias", None) is not None,
            torch_dtype=param_dtype,
        )
        HummingMethod.transform_humming_layer(layer)

        layer.humming_compute_config = json.dumps(
            {
                "use_f16_accum": envs.SGLANG_HUMMING_USE_F16_ACCUM.get(),
                "gemm_type": "dense",
            }
        )
        if getattr(layer, "locks", None) is None:
            layer.register_buffer(
                "locks", torch.zeros(1024, dtype=torch.int32, device=weight.device)
            )
        layer.is_humming_converted = True

    def apply_weights(self, layer: torch.nn.Module, x: torch.Tensor,
                      bias: Optional[torch.Tensor]) -> torch.Tensor:
        if getattr(layer, "is_humming_converted", False):
            from sglang.srt.layers.quantization.humming import HummingMethod

            output = HummingMethod.forward_layer(
                layer=layer,
                inputs=x.reshape(-1, x.size(-1)),
                compute_config=layer.humming_compute_config,
            )
            return output.view(*x.shape[:-1], output.size(-1))

        c = self.kernel_config

        def _get_weight_params(
            layer: torch.nn.Module,
        ) -> tuple[
            torch.Tensor,  # w_q
            torch.Tensor,  # w_s
            Optional[torch.Tensor],  # w_zp,
            Optional[torch.Tensor],  # w_gidx
        ]:
            return (
                getattr(layer, self.w_q_name),
                getattr(layer, self.w_s_name),
                getattr(layer, self.w_zp_name or "", None),
                getattr(layer, self.w_gidx_name or "", None),
            )

        w_q, w_s, w_zp, w_gidx = _get_weight_params(layer)

        # `process_weights_after_loading` will ensure w_zp and w_gidx are not
        #  None for marlin
        return apply_gptq_marlin_linear(
            input=x,
            weight=w_q,
            weight_scale=w_s,
            weight_zp=w_zp,  # type: ignore
            g_idx=w_gidx,  # type: ignore
            g_idx_sort_indices=layer.g_idx_sort_indices,
            workspace=self.workspace,
            wtype=c.weight_type,
            input_size_per_partition=c.partition_weight_shape[0],
            output_size_per_partition=c.partition_weight_shape[1],
            is_k_full=self.is_k_full,
            bias=bias,
        )
