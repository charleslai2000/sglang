#!/usr/bin/env python3
"""Hash the frozen local Falcon checkpoint without loading model weights."""
import hashlib
import json
import pathlib

root = pathlib.Path('/data/models/Falcon-H1-7B-Instruct-GPTQ-Int4')
index_path = root / 'model.safetensors.index.json'
index = json.loads(index_path.read_text())
files = sorted(set(index['weight_map'].values()))
record = {
    'model_revision': '52036ae497a2c0c253e17f98cc8652f2f7082ae3',
    'config_sha256': hashlib.sha256((root / 'config.json').read_bytes()).hexdigest(),
    'tokenizer_sha256': hashlib.sha256((root / 'tokenizer.json').read_bytes()).hexdigest(),
    'index_sha256': hashlib.sha256(index_path.read_bytes()).hexdigest(),
    'weights': [],
}
for name in files:
    path = root / name
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    record['weights'].append({'file': name, 'size_bytes': path.stat().st_size, 'sha256': h.hexdigest()})
print(json.dumps(record, indent=2))
