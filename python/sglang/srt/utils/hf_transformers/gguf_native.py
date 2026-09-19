# Copyright 2023-2026 SGLang Team
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
"""Reading config and tokenizer from a GGUF whose architecture transformers lacks.

``load_gguf_checkpoint`` refuses any architecture outside its own
``GGUF_SUPPORTED_ARCHITECTURES``, and it does so before touching a single field,
so both the config and the tokenizer are unreachable for such a checkpoint --
even though the tokenizer half of that reader is entirely architecture-agnostic
(it dispatches on ``tokenizer.ggml.model``, not on the model architecture).

This module carries SGLang's own path for those checkpoints:

* ``GGUF_NATIVE_CONFIG_BUILDERS`` maps a GGUF ``general.architecture`` to a
  builder returning a fully populated config.
* ``build_gguf_tokenizer`` reuses transformers' own converters, which work fine
  once they are reached directly instead of through the gated loader.

Reaching for these is a last resort: a config.json next to the .gguf still wins,
because the checkpoint author's own config outranks anything reconstructed.
"""

from typing import Any, Callable, Dict, Optional

from transformers import PretrainedConfig

from sglang.srt.configs.muse_glimmer import MuseGlimmerConfig
from sglang.srt.configs.qwen3_5 import Qwen3_5TextConfig

GGUF_NATIVE_CONFIG_BUILDERS: Dict[str, Callable[[str], PretrainedConfig]] = {
    "muse-glimmer": MuseGlimmerConfig.from_gguf,
    # llama.cpp spells the Qwen3.5 archive architecture "qwen35"; the HF side of
    # the same checkpoint is the text backbone (``qwen3_5_text``).
    "qwen35": Qwen3_5TextConfig.from_gguf,
}


def read_gguf_architecture(gguf_path: str) -> Optional[str]:
    """The ``general.architecture`` string, or None if it cannot be read."""
    try:
        from gguf import GGUFReader

        reader = GGUFReader(gguf_path)
        field = reader.fields.get("general.architecture")
        if field is None:
            return None
        value = field.contents()
        return value if isinstance(value, str) else None
    except Exception:
        return None


def has_native_gguf_support(gguf_path: str) -> bool:
    return read_gguf_architecture(gguf_path) in GGUF_NATIVE_CONFIG_BUILDERS


def build_gguf_config(gguf_path: str) -> PretrainedConfig:
    arch = read_gguf_architecture(gguf_path)
    return GGUF_NATIVE_CONFIG_BUILDERS[arch](gguf_path)


_GPT4O_SPLIT_REGEX = (
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*"
    r"[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?|"
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+"
    r"[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?|"
    r"\p{N}{1,3}| ?[^\s\p{L}\p{N}]+[\r\n/]*|\s*[\r\n]+|\s+(?!\S)|\s+"
)

_PRE_TOKENIZER_REGEX = {
    # LLAMA_VOCAB_PRE_TYPE_LLAMA3
    "llama-bpe": (
        r"(?:'[sS]|'[tT]|'[rR][eE]|'[vV][eE]|'[mM]|'[lL][lL]|'[dD])|"
        r"[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}{1,3}| ?[^\s\p{L}\p{N}]+[\r\n]*|"
        r"\s*[\r\n]+|\s+(?!\S)|\s+"
    ),
    "gpt-4o": _GPT4O_SPLIT_REGEX,
    "llama4": _GPT4O_SPLIT_REGEX,
    # LLAMA_VOCAB_PRE_TYPE_QWEN35 from llama.cpp src/llama-vocab.cpp. The HF
    # tokenizer.json expresses the same split case-insensitively; llama.cpp
    # expands it because its regex engine has no inline ``(?i:...)``.
    "qwen35": (
        r"(?:'[sS]|'[tT]|'[rR][eE]|'[vV][eE]|'[mM]|'[lL][lL]|'[dD])|"
        r"[^\r\n\p{L}\p{N}]?[\p{L}\p{M}]+|\p{N}| ?[^\s\p{L}\p{M}\p{N}]+[\r\n]*|"
        r"\s*[\r\n]+|\s+(?!\S)|\s+"
    ),
}

# llama.cpp token types (``llama_vocab_type`` in ggml): 1 = NORMAL, 3 = CONTROL,
# 4 = USER_DEFINED. CONTROL tokens are the chat/turn delimiters (``<|im_start|>``,
# ``<|endoftext|>``, ...); USER_DEFINED tokens are the ones the runtime parses
# back out of the text (``<think>``, ``</think>``, ``<tool_call>``, ...).
_GGML_TOKEN_TYPE_CONTROL = 3
_GGML_TOKEN_TYPE_USER_DEFINED = 4
_GGML_SPECIAL_TOKEN_TYPES = (_GGML_TOKEN_TYPE_CONTROL, _GGML_TOKEN_TYPE_USER_DEFINED)


def build_gguf_generation_config(gguf_path: str):
    """GenerationConfig from GGUF metadata, or None if there is nothing to say.

    llama.cpp records the end-of-generation ids explicitly, and for a
    Harmony-style model the distinction matters: ``eos_token_id`` ends the
    sequence and ``eot_token_id`` ends a turn, so both must stop generation while
    an end-of-*message* id must not -- stopping on that truncates the model
    mid-reasoning, before it answers.
    """
    from gguf import GGUFReader
    from transformers import GenerationConfig

    reader = GGUFReader(gguf_path)
    meta = {key: field.contents() for key, field in reader.fields.items()}

    stop_ids = []
    for key in ("tokenizer.ggml.eos_token_id", "tokenizer.ggml.eot_token_id"):
        if key in meta:
            value = int(meta[key])
            if value not in stop_ids:
                stop_ids.append(value)
    if not stop_ids:
        return None

    fields: Dict[str, Any] = {
        "eos_token_id": stop_ids if len(stop_ids) > 1 else stop_ids[0]
    }
    if "tokenizer.ggml.bos_token_id" in meta:
        fields["bos_token_id"] = int(meta["tokenizer.ggml.bos_token_id"])
    if "tokenizer.ggml.padding_token_id" in meta:
        fields["pad_token_id"] = int(meta["tokenizer.ggml.padding_token_id"])
    return GenerationConfig(**fields)


def build_gguf_tokenizer(gguf_path: str, **kwargs: Any):
    """Build a fast tokenizer from GGUF metadata alone.

    transformers' own GGUF tokenizer path is unreachable for an architecture its
    checkpoint loader rejects, and its converters key on ``tokenizer.ggml.model``
    (here "gpt2") which loses both the special-token block and the pre-tokenizer
    regex. So the tokenizers spec is assembled directly instead: a byte-level BPE
    over the NORMAL tokens, the CONTROL tokens registered as added specials, and
    the split regex named by ``tokenizer.ggml.pre``.
    """
    import json

    from gguf import GGUFReader
    from tokenizers import Tokenizer
    from transformers import PreTrainedTokenizerFast

    reader = GGUFReader(gguf_path)
    meta = {key: field.contents() for key, field in reader.fields.items()}

    tokens = list(meta["tokenizer.ggml.tokens"])
    token_types = [int(t) for t in meta["tokenizer.ggml.token_type"]]
    merges = [tuple(m.split(" ", 1)) for m in meta["tokenizer.ggml.merges"]]

    pre_name = meta.get("tokenizer.ggml.pre")
    if pre_name not in _PRE_TOKENIZER_REGEX:
        raise ValueError(
            f"No pre-tokenizer regex known for tokenizer.ggml.pre={pre_name!r}; "
            f"known: {sorted(_PRE_TOKENIZER_REGEX)}"
        )

    control_ids = [
        i for i, t in enumerate(token_types) if t == _GGML_TOKEN_TYPE_CONTROL
    ]
    special_ids = [
        i for i, t in enumerate(token_types) if t in _GGML_SPECIAL_TOKEN_TYPES
    ]
    # The BPE model keeps EVERY GGUF id, including the CONTROL/USER_DEFINED rows,
    # so the vocabulary owns each token's canonical id. ``tokenizers`` assigns
    # added-token ids sequentially from ``len(model.vocab)`` and ignores the
    # declared ``id`` (verified against tokenizers 0.22.2), so the ids can only be
    # honoured by already serving that exact id from the base vocab. Removing the
    # CONTROL rows here is what previously shifted them onto the ``[PAD*]`` rows.
    vocab = {tok: i for i, tok in enumerate(tokens)}

    def token_of(key):
        idx = meta.get(f"tokenizer.ggml.{key}")
        return None if idx is None else tokens[int(idx)]

    bos = token_of("bos_token_id")

    spec = {
        "version": "1.0",
        "truncation": None,
        "padding": None,
        "added_tokens": [
            {
                "id": i,
                "content": tokens[i],
                "single_word": False,
                "lstrip": False,
                "rstrip": False,
                "normalized": False,
                # CONTROL tokens are true specials: they are stripped from
                # decoded output. USER_DEFINED markers must stay in the text --
                # the reasoning/tool parsers split on the literal
                # ``<think>``/``</think>``/``<tool_call>`` strings.
                "special": token_types[i] == _GGML_TOKEN_TYPE_CONTROL,
            }
            for i in special_ids
        ],
        "normalizer": None,
        "pre_tokenizer": {
            "type": "Sequence",
            "pretokenizers": [
                {
                    "type": "Split",
                    "pattern": {"Regex": _PRE_TOKENIZER_REGEX[pre_name]},
                    "behavior": "Isolated",
                    "invert": False,
                },
                {
                    "type": "ByteLevel",
                    "add_prefix_space": False,
                    "trim_offsets": True,
                    "use_regex": False,
                },
            ],
        },
        "post_processor": None,
        "decoder": {
            "type": "ByteLevel",
            "add_prefix_space": True,
            "trim_offsets": True,
            "use_regex": True,
        },
        "model": {
            "type": "BPE",
            "dropout": None,
            "unk_token": None,
            "continuing_subword_prefix": None,
            "end_of_word_suffix": None,
            "fuse_unk": False,
            "byte_fallback": False,
            "ignore_merges": True,
            "vocab": vocab,
            "merges": [list(m) for m in merges],
        },
    }

    if meta.get("tokenizer.ggml.add_bos_token") and bos is not None:
        bos_id = int(meta["tokenizer.ggml.bos_token_id"])
        spec["post_processor"] = {
            "type": "TemplateProcessing",
            "single": [
                {"SpecialToken": {"id": bos, "type_id": 0}},
                {"Sequence": {"id": "A", "type_id": 0}},
            ],
            "pair": [
                {"SpecialToken": {"id": bos, "type_id": 0}},
                {"Sequence": {"id": "A", "type_id": 0}},
                {"Sequence": {"id": "B", "type_id": 0}},
            ],
            "special_tokens": {
                bos: {"id": bos, "ids": [bos_id], "tokens": [bos]},
            },
        }

    backend = Tokenizer.from_str(json.dumps(spec))

    named = {
        bos,
        token_of("eos_token_id"),
        token_of("padding_token_id"),
        token_of("unknown_token_id"),
    }
    additional = [tokens[i] for i in control_ids if tokens[i] not in named]

    return PreTrainedTokenizerFast(
        tokenizer_object=backend,
        bos_token=bos,
        eos_token=token_of("eos_token_id"),
        unk_token=token_of("unknown_token_id"),
        pad_token=token_of("padding_token_id"),
        additional_special_tokens=additional,
        chat_template=meta.get("tokenizer.chat_template"),
        **kwargs,
    )
