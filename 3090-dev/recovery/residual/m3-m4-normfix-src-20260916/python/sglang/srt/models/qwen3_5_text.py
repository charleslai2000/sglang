# Copyright 2025 Qwen Team
# Copyright 2025 SGLang Team
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

import logging
from typing import Iterable, Optional, Set, Tuple, Union

import torch
from torch import nn

from sglang.srt.distributed import get_pp_group
from sglang.srt.eplb.expert_location import ModelConfigForExpertLocation
from sglang.srt.layers.layernorm import GemmaRMSNorm
from sglang.srt.layers.logits_processor import LogitsProcessor
from sglang.srt.layers.quantization.base_config import QuantizationConfig
from sglang.srt.layers.utils import PPMissingLayer
from sglang.srt.layers.vocab_parallel_embedding import ParallelLMHead
from sglang.srt.model_executor.forward_batch_info import ForwardBatch, PPProxyTensors
from sglang.srt.model_loader.weight_utils import default_weight_loader
from sglang.srt.models import qwen3_5
from sglang.srt.models.qwen2_moe import Qwen2MoeSparseMoeBlock
from sglang.srt.runtime_context import get_parallel
from sglang.srt.utils import LazyValue, add_prefix

logger = logging.getLogger(__name__)

_MODEL_PREFIX = "model."

# Runtime names the LM head can receive. Under ``GGUFConfig`` the LM head is a
# quantized ``ParallelLMHead`` exposing ``qweight``/``qweight_type``; the GGUF
# iterator renames ``output.weight`` to ``lm_head.qweight``.
_LM_HEAD_PARAM_NAMES = ("lm_head.weight", "lm_head.qweight", "lm_head.qweight_type")


def _gguf_ssm_a_to_a_log(raw: torch.Tensor) -> torch.Tensor:
    """Undo llama.cpp's GGUF-time ``A_log -> -exp(A_log)`` storage transform."""
    if not raw.is_floating_point() or not torch.isfinite(raw).all():
        raise ValueError("qwen35 GGUF ssm_a must contain finite floating values")
    if not torch.all(raw < 0):
        raise ValueError("qwen35 GGUF ssm_a must contain only -exp(A_log) values")
    return torch.log(-raw)


def _gguf_runtime_param_name(name: str) -> str:
    """Normalize an incoming GGUF name to this port's runtime parameter name.

    ``Qwen3_5ForCausalLM.load_weights`` (``models/qwen3_5.py``) drops the HF
    ``.self_attn`` segment before it resolves the destination parameter, so an
    incoming GGUF name must be compared on that same normalized form.
    """
    return name.replace(".self_attn", "")


def _gemma_norm_param_names(module: nn.Module) -> Set[str]:
    """Runtime parameter names whose destination module is ``GemmaRMSNorm``.

    ``GemmaRMSNorm`` (``sglang/srt/layers/layernorm.py``) is the runtime norm
    whose contract is the *offset* form: it stores ``w_hf`` and applies the
    scale ``1 + w_hf``.  That is the norm family whose GGUF->runtime contract
    needs the inverse fold, so the fold's scope is derived from the destination
    module type rather than from a per-model name list.

    Because the scope is the module contract, every Gemma-style norm is covered
    and plain norms such as ``linear_attn.norm`` (``RMSNormGated``, no ``+1``
    contract) are excluded structurally -- there is no exclusion list.

    LIMITATION: GGUF carries no metadata flag declaring the writer convention
    (neither candidate file exposes ``norms_are_absolute``/``norm_offset``), so
    this keys on ``(source format == GGUF) AND (destination module contract ==
    GemmaRMSNorm)`` and rests on the llama.cpp convention, not on a per-file
    declaration.  A converter that emitted the offset form would not be
    detectable from metadata.
    """
    names: Set[str] = set()
    for mod_name, mod in module.named_modules():
        if isinstance(mod, GemmaRMSNorm):
            for param_name, _ in mod.named_parameters(recurse=False):
                name = f"{mod_name}.{param_name}" if mod_name else param_name
                names.add(_gguf_runtime_param_name(name))
    return names


def _gguf_fold_absolute_norms(
    name: str, loaded_weight: torch.Tensor, offset_param_names: Set[str]
) -> torch.Tensor:
    """Undo llama.cpp's GGUF-time absolute-scale storage for a Gemma-style norm.

    llama.cpp writes this norm family to GGUF as the *absolute* scale
    ``1 + w_hf``, while the runtime ``GemmaRMSNorm`` contract expects the offset
    form ``w_hf`` and derives ``1 + w_hf`` itself.  Loading GGUF directly would
    therefore apply the scale twice, so the loader subtracts the embedded ``1``
    for exactly the parameters whose destination module is ``GemmaRMSNorm``.
    """
    if _gguf_runtime_param_name(name) in offset_param_names:
        return loaded_weight - 1.0
    return loaded_weight


class Qwen3_5ForCausalLM(nn.Module):
    body_cls = qwen3_5.Qwen3_5ForCausalLM

    packed_modules_mapping = qwen3_5.Qwen3_5ForCausalLM.packed_modules_mapping
    supported_lora_modules = qwen3_5.Qwen3_5ForCausalLM.supported_lora_modules

    @classmethod
    def shared_experts_fusion_disable_reason(cls, hf_config, quant_config):
        # The body decides; it is handed this config and quantization verbatim.
        return cls.body_cls.shared_experts_fusion_disable_reason(
            hf_config, quant_config
        )

    def __init__(
        self,
        config,
        quant_config: Optional[QuantizationConfig] = None,
        prefix: str = "",
    ) -> None:
        super().__init__()
        self.config = config
        self.quant_config = quant_config
        self.pp_group = get_pp_group()
        self._is_gguf = (
            quant_config is not None and quant_config.get_name() == "gguf"
        )

        if quant_config is not None and hasattr(quant_config, "packed_modules_mapping"):
            quant_config.packed_modules_mapping = self.packed_modules_mapping

        self.model = self.body_cls(
            config=config,
            quant_config=quant_config,
            prefix=add_prefix("model", prefix),
        )

        if self.pp_group.is_last_rank:
            if self.pp_group.world_size == 1 and config.tie_word_embeddings:
                self.lm_head = self.model.embed_tokens
            else:
                self.lm_head = ParallelLMHead(
                    config.vocab_size,
                    config.hidden_size,
                    quant_config=quant_config,
                    org_num_embeddings=config.vocab_size,
                    prefix=add_prefix("lm_head", prefix),
                    use_attn_tp_group=get_parallel().enable_dp_lm_head,
                )
        else:
            self.lm_head = PPMissingLayer()

        self.logits_processor = LogitsProcessor(config)

        # Text-only checkpoints retain mrope_section, but identical position rows
        # make its rotary embedding equivalent to 1-D RoPE.
        rope_config = getattr(config, "rope_parameters", None) or getattr(
            config, "rope_scaling", None
        )
        self.is_mrope_enabled = bool(rope_config) and "mrope_section" in rope_config

        self.capture_aux_hidden_states = False

    @property
    def start_layer(self) -> int:
        return self.model.start_layer

    @property
    def end_layer(self) -> int:
        return self.model.end_layer

    def get_input_embeddings(self) -> nn.Embedding:
        return self.model.embed_tokens

    def get_embed_and_head(self):
        return self.model.embed_tokens.weight, self.lm_head.weight

    def set_embed_and_head(self, embed, head):
        del self.model.embed_tokens.weight
        del self.lm_head.weight
        self.model.embed_tokens.weight = embed
        self.lm_head.weight = head
        torch.cuda.empty_cache()
        torch.cuda.synchronize()

    def set_dflash_layers_to_capture(self, layers_to_capture: list[int]):
        if not self.pp_group.is_last_rank:
            return
        if layers_to_capture is None:
            raise ValueError(
                "DFLASH requires explicit layer ids for aux hidden capture."
            )
        self.capture_aux_hidden_states = True
        self.model.set_dflash_layers_to_capture(layers_to_capture)

    @torch.no_grad()
    def forward(
        self,
        input_ids: torch.Tensor,
        positions: torch.Tensor,
        forward_batch: ForwardBatch,
        input_embeds: Optional[torch.Tensor] = None,
        pp_proxy_tensors: Optional[PPProxyTensors] = None,
        **kwargs,
    ) -> Union[torch.Tensor, PPProxyTensors]:
        if self.is_mrope_enabled:
            positions = forward_batch.mrope_positions

        hidden_states = self.model(
            input_ids,
            positions,
            forward_batch,
            input_embeds,
            pp_proxy_tensors=pp_proxy_tensors,
        )

        if not self.pp_group.is_last_rank:
            return hidden_states

        aux_hidden_states = None
        if isinstance(hidden_states, tuple):
            hidden_states, aux_hidden_states = hidden_states

        return self.logits_processor(
            input_ids, hidden_states, self.lm_head, forward_batch, aux_hidden_states
        )

    def load_weights(self, weights: Iterable[Tuple[str, torch.Tensor]]) -> Set[str]:
        params_dict = dict(self.named_parameters())
        loaded_params: Set[str] = set()
        # Resolved once from the runtime module tree: the GGUF inverse fold is
        # scoped by the destination module contract, not by a model name list.
        offset_norm_params = (
            _gemma_norm_param_names(self) if self._is_gguf else frozenset()
        )

        body_weights = []
        for name, loaded_weight in weights:
            if name.startswith(_MODEL_PREFIX):
                # llama.cpp folds A_log to -exp(A_log) when writing GGUF; the
                # runtime A_log parameter expects the un-transformed log decay.
                if self._is_gguf and name.endswith(".linear_attn.A_log"):
                    loaded_weight = _gguf_ssm_a_to_a_log(loaded_weight)
                if self._is_gguf:
                    loaded_weight = _gguf_fold_absolute_norms(
                        name, loaded_weight, offset_norm_params
                    )
                body_weights.append((name[len(_MODEL_PREFIX) :], loaded_weight))
            elif name in _LM_HEAD_PARAM_NAMES:
                if self.config.tie_word_embeddings:
                    continue
                if name not in params_dict:
                    continue
                param = params_dict[name]
                weight_loader = getattr(param, "weight_loader", default_weight_loader)
                weight_loader(param, loaded_weight)
                loaded_params.add(name)

        body_loaded = self.model.load_weights(body_weights)
        loaded_params.update(f"{_MODEL_PREFIX}{n}" for n in body_loaded)

        if self.config.tie_word_embeddings and self.pp_group.is_last_rank:
            loaded_params.add("lm_head.weight")

        return loaded_params


class Qwen3_5MoeForCausalLM(Qwen3_5ForCausalLM):
    body_cls = qwen3_5.Qwen3_5MoeForCausalLM

    packed_modules_mapping = qwen3_5.Qwen3_5MoeForCausalLM.packed_modules_mapping
    supported_lora_modules = qwen3_5.Qwen3_5MoeForCausalLM.supported_lora_modules

    def __init__(
        self,
        config,
        quant_config: Optional[QuantizationConfig] = None,
        prefix: str = "",
    ) -> None:
        super().__init__(config=config, quant_config=quant_config, prefix=prefix)

        self._routed_experts_weights_of_layer = LazyValue(
            lambda: {
                layer_id: layer.mlp.get_moe_weights()
                for layer_id, layer in enumerate(self.model.layers)
                if isinstance(layer.mlp, Qwen2MoeSparseMoeBlock)
            }
        )

    @property
    def routed_experts_weights_of_layer(self):
        return self._routed_experts_weights_of_layer.value

    @classmethod
    def get_model_config_for_expert_location(cls, config):
        return ModelConfigForExpertLocation(
            num_layers=config.num_hidden_layers,
            num_logical_experts=config.num_experts,
            num_groups=None,
        )


EntryClass = [Qwen3_5MoeForCausalLM, Qwen3_5ForCausalLM]
