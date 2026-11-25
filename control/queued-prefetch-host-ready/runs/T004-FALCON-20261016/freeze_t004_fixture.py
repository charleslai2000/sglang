#!/usr/bin/env python3
"""Freeze the deterministic Falcon T004 L0 fixture as explicit token IDs."""
import hashlib
import json
from pathlib import Path
from transformers import AutoTokenizer

HERE = Path(__file__).resolve().parent
MODEL = Path("/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4")
FIXTURE = HERE / "t004-l0-fixture.json"
TOK = AutoTokenizer.from_pretrained(str(MODEL), trust_remote_code=True)


def digest(ids):
    return hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()


fixture = json.loads(FIXTURE.read_text())
fixture["tokenizer_sha256"] = hashlib.sha256((MODEL / "tokenizer.json").read_bytes()).hexdigest()
fixture["targets"] = {}
ids_file = HERE / "t004-l0-fixture-token-ids.json"
all_ids = {}
for label in "ABCD":
    text = f"T004 AB {label} unique: " + ("maple river quartz cedar violet " * 500)
    ids = TOK.encode(text, add_special_tokens=False)[:1920]
    if len(ids) != 1920:
        raise RuntimeError(f"{label}: expected exactly 1920 prefix tokens, got {len(ids)}")
    all_ids[label] = ids
    fixture["targets"][label] = {
        "prefix_tokens": len(ids),
        "prefix_sha256": digest(ids),
        "prompt_recipe": f"T004 AB {label} unique: maple river quartz cedar violet repeated 500; first 1920 tokenizer IDs",
    }
ids_file.write_text(json.dumps({"schema": "t004_fixture_token_ids.v1", "model_revision": fixture["model_revision"], "tokenizer_sha256": fixture["tokenizer_sha256"], "targets": all_ids}, separators=(",", ":")) + "\n")
fixture["token_ids_file"] = ids_file.name
fixture["token_ids_file_sha256"] = hashlib.sha256(ids_file.read_bytes()).hexdigest()
fixture["note"] = "Deterministic new fixture for matched T004 arms. Not historical T003 input. IDs are authoritative; prompt recipes are explanatory only."
FIXTURE.write_text(json.dumps(fixture, indent=2) + "\n")
print(json.dumps({"fixture": str(FIXTURE), "ids": str(ids_file), "tokenizer_sha256": fixture["tokenizer_sha256"], "token_ids_file_sha256": fixture["token_ids_file_sha256"], "targets": fixture["targets"]}, indent=2))
