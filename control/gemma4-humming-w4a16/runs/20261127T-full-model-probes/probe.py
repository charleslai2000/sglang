import json, requests, sys, torch

port, out = sys.argv[1:]


def post(ids, n, tag):
    data = {
        "input_ids": ids,
        "sampling_params": {
            "temperature": 0.0,
            "top_k": 1,
            "max_new_tokens": n,
            "ignore_eos": True,
        },
    }
    r = requests.post(f"http://127.0.0.1:{port}/generate", json=data, timeout=600)
    r.raise_for_status()
    d = r.json()
    return {
        "tag": tag,
        "input_len": len(ids),
        "ids": d.get("output_ids") or [],
        "meta": d.get("meta_info", {}),
    }


probe = list(range(1000, 2024))
response = post(probe, 1, "logits-capture")
for size in (2048, 4096):
    post(list(range(5000, 5000 + size)), 1, f"prefill-{size}")
graph = post(probe, 32, "decode-graph")
json.dump({"capture": response, "graph": graph}, open(out, "w"), indent=1)
print("CAPTURE_AND_GRAPH_OK", len(graph["ids"]))
