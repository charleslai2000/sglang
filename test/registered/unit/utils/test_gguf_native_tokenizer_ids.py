"""Unit tests for the GGUF native tokenizer's special-token id binding.

``build_gguf_tokenizer`` must bind every special GGUF token to the id the GGUF
vocabulary itself declares.  ``tokenizers`` allocates added-token ids
sequentially from ``len(model.vocab)`` and ignores the declared ``id``, so the
base BPE vocab has to serve each canonical id; the builder therefore keeps the
CONTROL/USER_DEFINED rows in the base vocab instead of removing them and
re-declaring them as added tokens.

The tiny GGUF written here reproduces the real layout at a small scale: NORMAL
tokens, a CONTROL block, a USER_DEFINED block, then a ``[PAD*]`` tail whose ids
start exactly at the count of non-CONTROL tokens -- the same hole structure that
used to shift the CONTROL ids onto the PAD rows.  No server, no model weights.
"""

import os
import tempfile
import unittest

from sglang.test.ci.ci_register import register_cpu_ci
from sglang.test.test_utils import CustomTestCase

register_cpu_ci(est_time=5, suite="base-a-test-cpu")

from gguf import GGUFReader, GGUFWriter

from sglang.srt.utils.hf_transformers.gguf_native import build_gguf_tokenizer

# NORMAL(1) x7, CONTROL(3) x3, USER_DEFINED(4) x2, then the PAD tail.
TOKENS = [
    "a",
    "b",
    "ab",
    "c",
    "d",
    "e",
    "f",
    "<|endoftext|>",
    "<|im_start|>",
    "<|im_end|>",
    "<think>",
    "</think>",
    "[PAD12]",
    "[PAD13]",
    "[PAD14]",
]
TOKEN_TYPES = [1, 1, 1, 1, 1, 1, 1, 3, 3, 3, 4, 4, 5, 5, 5]
CANONICAL = {tok: i for i, tok in enumerate(TOKENS)}
BOS_ID = 7
EOS_ID = 9
# ids of the CONTROL(3) and USER_DEFINED(4) rows
SPECIAL_IDS = [i for i, t in enumerate(TOKEN_TYPES) if t in (3, 4)]


def _write_tiny_gguf(path: str) -> None:
    writer = GGUFWriter(path, "qwen35")
    writer.add_token_list(TOKENS)
    writer.add_token_types(TOKEN_TYPES)
    writer.add_token_merges(["a b"])
    writer.add_tokenizer_model("gpt2")
    writer.add_tokenizer_pre("qwen35")
    writer.add_bos_token_id(BOS_ID)
    writer.add_eos_token_id(EOS_ID)
    writer.add_pad_token_id(BOS_ID)
    writer.add_add_bos_token(False)
    writer.add_chat_template("CHAT")
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()


class TestGgufNativeTokenizerIds(CustomTestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls._dir.name, "tiny.gguf")
        _write_tiny_gguf(cls.path)
        cls.tokenizer = build_gguf_tokenizer(cls.path)

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def test_special_tokens_encode_to_canonical_ids(self):
        # The defect bound these to the PAD tail (or split them into text).
        for token in (
            "<|endoftext|>",
            "<|im_start|>",
            "<|im_end|>",
            "<think>",
            "</think>",
        ):
            ids = self.tokenizer.encode(token, add_special_tokens=False)
            self.assertEqual(ids, [CANONICAL[token]], token)

    def test_no_added_token_collides_with_base_vocab(self):
        backend = self.tokenizer.backend_tokenizer
        added = backend.get_added_tokens_decoder()
        collisions = [
            (aid, str(added[aid]), backend.model.id_to_token(aid))
            for aid in added
            if backend.model.id_to_token(aid) is not None
            and backend.model.id_to_token(aid) != str(added[aid])
        ]
        self.assertEqual(collisions, [])
        self.assertEqual(len(added), 5)

    def test_base_vocab_serves_every_canonical_id(self):
        # The whole id space must be owned by the base vocab, otherwise
        # tokenizers' sequential allocation would shift the added ids.
        backend = self.tokenizer.backend_tokenizer
        self.assertEqual(
            backend.get_vocab_size(with_added_tokens=False), len(TOKENS)
        )
        for token, cid in CANONICAL.items():
            self.assertEqual(backend.model.id_to_token(cid), token)

    def test_bos_eos_match_gguf_metadata(self):
        self.assertEqual(self.tokenizer.bos_token_id, BOS_ID)
        self.assertEqual(self.tokenizer.eos_token_id, EOS_ID)

    def test_control_specials_are_stripped_from_decoded_text(self):
        # CONTROL tokens are real specials: skip_special_tokens drops them.
        self.assertEqual(
            self.tokenizer.decode([CANONICAL["<|im_end|>"]], skip_special_tokens=True),
            "",
        )

    def test_user_defined_markers_survive_detokenization(self):
        # The reasoning/tool parsers split on the literal marker strings, so
        # USER_DEFINED tokens must NOT be treated as strippable specials.
        for token in ("<think>", "</think>"):
            self.assertEqual(
                self.tokenizer.decode(
                    [CANONICAL[token]], skip_special_tokens=True
                ),
                token,
            )

    def test_ids_derive_from_gguf_token_type_not_a_name_list(self):
        reader = GGUFReader(self.path)
        meta = {key: field.contents() for key, field in reader.fields.items()}
        token_types = [int(t) for t in meta["tokenizer.ggml.token_type"]]
        special = [i for i, t in enumerate(token_types) if t in (3, 4)]
        self.assertEqual(sorted(special), sorted(SPECIAL_IDS))
        added = self.tokenizer.backend_tokenizer.get_added_tokens_decoder()
        self.assertEqual(sorted(added), sorted(special))

    def test_control_is_special_and_user_defined_is_not(self):
        added = self.tokenizer.backend_tokenizer.get_added_tokens_decoder()
        for i, token_type in enumerate(TOKEN_TYPES):
            if token_type == 3:
                self.assertTrue(added[i].special, TOKENS[i])
            elif token_type == 4:
                self.assertFalse(added[i].special, TOKENS[i])

    def test_add_bos_false_does_not_prefix_ordinary_text(self):
        # The tiny file declares add_bos_token=False, so no bos id is injected.
        self.assertEqual(
            self.tokenizer.encode("ab", add_special_tokens=True), [CANONICAL["ab"]]
        )


class TestGgufNativeTokenizerHfPathInert(CustomTestCase):
    """A non-GGUF tokenizer directory is loaded without the GGUF builder."""

    def test_hf_directory_untouched(self):
        import json

        spec = {
            "version": "1.0",
            "truncation": None,
            "padding": None,
            "added_tokens": [
                {
                    "id": 3,
                    "content": "<|im_start|>",
                    "single_word": False,
                    "lstrip": False,
                    "rstrip": False,
                    "normalized": False,
                    "special": True,
                },
                {
                    "id": 4,
                    "content": "<|im_end|>",
                    "single_word": False,
                    "lstrip": False,
                    "rstrip": False,
                    "normalized": False,
                    "special": True,
                },
            ],
            "normalizer": None,
            "pre_tokenizer": {
                "type": "ByteLevel",
                "add_prefix_space": False,
                "trim_offsets": True,
                "use_regex": True,
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
                "vocab": {"a": 0, "b": 1, "c": 2},
                "merges": [],
            },
        }
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "tokenizer.json"), "w") as f:
                json.dump(spec, f)
            with open(os.path.join(d, "tokenizer_config.json"), "w") as f:
                json.dump(
                    {
                        "tokenizer_class": "PreTrainedTokenizerFast",
                        "bos_token": "<|im_start|>",
                        "eos_token": "<|im_end|>",
                    },
                    f,
                )
            from sglang.srt.utils.hf_transformers.tokenizer import get_tokenizer

            tokenizer = get_tokenizer(d, tokenizer_mode="auto")
            # The ids come from the on-disk tokenizer.json, untouched.
            self.assertEqual(
                tokenizer.encode("<|im_start|>", add_special_tokens=False), [3]
            )
            self.assertEqual(
                tokenizer.encode("<|im_end|>", add_special_tokens=False), [4]
            )
            self.assertEqual(
                tokenizer.encode("abc", add_special_tokens=False), [0, 1, 2]
            )


if __name__ == "__main__":
    unittest.main()
