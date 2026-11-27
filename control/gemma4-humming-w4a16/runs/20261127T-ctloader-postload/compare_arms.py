"""T012 gate: compare the Marlin reference arm against the Humming post-load arm.

Every check below is an equality or a numerical tolerance on data produced by the
paired run; nothing is inferred from the launch configuration alone.
"""

import ast
import glob
import json
import os
import re
import sys

import torch

EXPECTED_MISSING_TEXT_CORE = re.compile(
    r"^language_model\.layers\.\d+\.self_attn\.k_norm\.weight$"
)
GEMM_REL_LIMIT = 0.05
GEMM_VS_MARLIN_FACTOR = 3.0


def load_audit(arm_dir):
    path = os.path.join(arm_dir, "audit", "ct-wna16-audit.jsonl")
    pre, post = {}, {}
    with open(path) as f:
        for line in f:
            record = json.loads(line)
            if record["event"] == "pre":
                pre[record["layer"]] = record
            else:
                post[record["layer"]] = record
    return pre, post


def load_dispatch(arm_dir):
    merged = {
        "humming_gemm": 0,
        "humming_gemm_capture": 0,
        "marlin_linear": 0,
        "graph_replay": 0,
        "replay_kernels": [],
        "logits_saved": 0,
        "processes": 0,
    }
    for path in glob.glob(os.path.join(arm_dir, "audit", "dispatch-*.json")):
        with open(path) as f:
            state = json.load(f)
        if not (
            state.get("humming_gemm")
            or state.get("marlin_linear")
            or state.get("graph_replay")
        ):
            continue
        merged["processes"] += 1
        for key in (
            "humming_gemm",
            "humming_gemm_capture",
            "marlin_linear",
            "graph_replay",
        ):
            merged[key] += state.get(key, 0)
        merged["logits_saved"] += state.get("logits_saved", 0)
        merged["replay_kernels"].extend(state.get("replay_kernels", []))
    return merged


def missing_text_core_wna16(arm_dir):
    with open(os.path.join(arm_dir, "server.log")) as f:
        text = f.read()
    match = re.search(
        r"Some weights are not initialized from checkpoints: (\[.*?\])", text, re.S
    )
    if match is None:
        return []
    names = ast.literal_eval(match.group(1))
    return [
        name
        for name in names
        if name.startswith("language_model.")
        and name.endswith(("weight_packed", "weight_scale", "weight_shape"))
    ]


def load_logits(arm_dir):
    path = os.path.join(arm_dir, "audit", "logits.pt")
    if not os.path.exists(path):
        return None
    return torch.load(path, map_location="cpu")["logits"]


def main(out_dir):
    result = {"checks": {}, "gates": {}, "details": {}}
    marlin_pre, marlin_post = load_audit(os.path.join(out_dir, "marlin"))
    humming_pre, humming_post = load_audit(os.path.join(out_dir, "humming"))
    checkpoint = json.load(open(os.path.join(out_dir, "checkpoint-textcore.json")))

    checks = result["checks"]
    # Group the checkpoint's Text Core tensors onto the layer that consumes them
    # (q/k/v -> qkv_proj, gate/up -> gate_up_proj). This only reconciles element
    # counts; the substantive comparison is the per-parameter SHA256 below.
    ckpt_layers = {}
    ckpt_shared_kv = set()
    for entry in checkpoint["tensors"]:
        if entry["suffix"] != "weight_packed":
            continue
        name = entry["name"][: -len(".weight_packed")]
        fused = (
            name.replace(".self_attn.q_proj", ".self_attn.qkv_proj")
            .replace(".self_attn.k_proj", ".self_attn.qkv_proj")
            .replace(".self_attn.v_proj", ".self_attn.qkv_proj")
            .replace(".mlp.gate_proj", ".mlp.gate_up_proj")
            .replace(".mlp.up_proj", ".mlp.gate_up_proj")
        )
        ckpt_layers[fused] = ckpt_layers.get(fused, 0) + entry["shape"][0] * entry["shape"][1]
        if name.endswith(".self_attn.q_proj"):
            index = int(name.split("layers.")[1].split(".")[0])
            if not any(
                other.startswith(f"language_model.layers.{index}.self_attn.k_proj")
                for other in (e["name"] for e in checkpoint["tensors"])
            ):
                ckpt_shared_kv.add(fused)

    checks["layer_count"] = {
        "marlin": len(marlin_pre),
        "humming": len(humming_pre),
        "equal": len(marlin_pre) == len(humming_pre),
        "checkpoint_fused_layers": len(ckpt_layers),
        "checkpoint_tensors": checkpoint["totals"]["weight_packed"]["tensors"],
    }

    common = sorted(set(marlin_pre) & set(humming_pre))
    mismatched = []
    for prefix in common:
        a, b = marlin_pre[prefix], humming_pre[prefix]
        for key in (
            "packed_sha256",
            "scale_sha256",
            "packed_shape",
            "scale_shape",
            "packed_numel",
            "scale_numel",
            "weight_shape",
            "param",
            "scale_param",
        ):
            if a[key] != b[key]:
                mismatched.append({"prefix": prefix, "field": key})
    checks["pre_conversion_identity"] = {
        "compared": len(common),
        "mismatched": mismatched,
        "only_marlin": sorted(set(marlin_pre) - set(humming_pre)),
        "only_humming": sorted(set(humming_pre) - set(marlin_pre)),
    }

    packed_total = sum(record["packed_numel"] for record in marlin_pre.values())
    scale_total = sum(record["scale_numel"] for record in marlin_pre.values())
    deltas = {
        layer: packed_total_for_layer - ckpt_layers.get(layer, 0)
        for layer, packed_total_for_layer in (
            (record["layer"], record["packed_numel"])
            for record in marlin_pre.values()
        )
    }
    extra = {layer: delta for layer, delta in deltas.items() if delta > 0}
    checks["checkpoint_coverage"] = {
        "loaded_packed_numel": packed_total,
        "checkpoint_packed_numel": checkpoint["totals"]["weight_packed"]["numel"],
        "loaded_scale_numel": scale_total,
        "checkpoint_scale_numel": checkpoint["totals"]["weight_scale"]["numel"],
        "delta_packed_numel": packed_total - checkpoint["totals"]["weight_packed"]["numel"],
        "delta_scale_numel": scale_total - checkpoint["totals"]["weight_scale"]["numel"],
        "layers": len(marlin_pre),
        "layers_exact": sorted(layer for layer, delta in deltas.items() if delta == 0),
        "layers_extra": extra,
        "layers_missing": sorted(layer for layer, delta in deltas.items() if delta < 0),
        "unknown_layers": sorted(set(marlin_pre) - set(ckpt_layers)),
        "extra_confined_to_shared_kv": sorted(extra) == sorted(ckpt_shared_kv),
        "extra_sum_matches_total": sum(extra.values()) == packed_total - checkpoint["totals"]["weight_packed"]["numel"],
        # group_size 32 over packed INT4 means one scale per 4 packed words.
        "scale_consistent_per_layer": all(
            record["scale_numel"] * 4 == record["packed_numel"]
            for record in marlin_pre.values()
        ),
        "scale_delta_matches_packed_delta": (
            scale_total - checkpoint["totals"]["weight_scale"]["numel"]
        )
        * 4
        == packed_total - checkpoint["totals"]["weight_packed"]["numel"],
    }

    checks["missing_text_core_weights"] = {
        arm: sorted(missing_text_core_wna16(os.path.join(out_dir, arm)))
        for arm in ("marlin", "humming")
    }

    checks["humming_resident_params"] = {
        name: {
            "has_weight_packed": "weight_packed" in post["parameters"],
            "has_weight_shape": "weight_shape" in post["parameters"],
            "has_weight_scale": "weight_scale" in post["parameters"],
        }
        for name, post in humming_post.items()
    }

    gemm = {}
    for name in sorted(set(marlin_post) & set(humming_post)):
        a = marlin_post[name].get("gemm")
        b = humming_post[name].get("gemm")
        if not a or not b:
            continue
        gemm[name] = {
            "marlin_max_abs": a["max_abs"],
            "humming_max_abs": b["max_abs"],
            "reference_abs_mean": a["reference_abs_mean"],
            "marlin_rel": a["max_abs"] / a["reference_abs_mean"],
            "humming_rel": b["max_abs"] / b["reference_abs_mean"],
        }
    checks["converted_gemm"] = gemm

    dispatch = {
        arm: load_dispatch(os.path.join(out_dir, arm)) for arm in ("marlin", "humming")
    }
    checks["dispatch"] = {
        arm: {
            "humming_gemm": state["humming_gemm"],
            "humming_gemm_capture": state["humming_gemm_capture"],
            "marlin_linear": state["marlin_linear"],
            "graph_replay": state["graph_replay"],
            "layers": len(marlin_pre),
            "processes": state["processes"],
        }
        for arm, state in dispatch.items()
    }
    replay_path = os.path.join(out_dir, "graph-replay-kernel-check.json")
    checks["replay_kernel_check"] = (
        json.load(open(replay_path)) if os.path.exists(replay_path) else {"missing": True}
    )

    probes = {
        arm: json.load(open(os.path.join(out_dir, arm, "probes.json")))
        for arm in ("marlin", "humming")
    }
    checks["greedy_tokens"] = {
        "capture_equal": probes["marlin"]["capture"]["ids"]
        == probes["humming"]["capture"]["ids"],
        "graph_equal": probes["marlin"]["graph"]["ids"]
        == probes["humming"]["graph"]["ids"],
        "graph_len": len(probes["marlin"]["graph"]["ids"]),
        "capture_ids": {
            "marlin": probes["marlin"]["capture"]["ids"],
            "humming": probes["humming"]["capture"]["ids"],
        },
    }
    long_m = probes["marlin"].get("long", [])
    long_h = probes["humming"].get("long", [])
    long_compare = [
        {
            "tag": a["tag"],
            "len": len(a["ids"]),
            "equal": a["ids"] == b["ids"],
            "first_diff": next(
                (i for i, (x, y) in enumerate(zip(a["ids"], b["ids"])) if x != y),
                None,
            ),
        }
        for a, b in zip(long_m, long_h)
    ]
    divergence_path = os.path.join(out_dir, "divergence", "verdict.json")
    checks["divergence"] = (
        json.load(open(divergence_path))
        if os.path.exists(divergence_path)
        else {"missing": True}
    )
    checks["greedy_tokens"]["long"] = long_compare
    checks["greedy_tokens"]["long_all_equal"] = bool(long_compare) and all(
        entry["equal"] for entry in long_compare
    )

    logits = {
        arm: load_logits(os.path.join(out_dir, arm)) for arm in ("marlin", "humming")
    }
    if logits["marlin"] is not None and logits["humming"] is not None:
        a, b = logits["marlin"].flatten(), logits["humming"].flatten()
        diff = (a - b).abs()
        top_a, top_b = a.topk(10).indices.tolist(), b.topk(10).indices.tolist()
        checks["whole_model_logits"] = {
            "shape": list(logits["marlin"].shape),
            "max_abs_diff": float(diff.max()),
            "l2_rel": float((b - a).norm() / a.norm()),
            "reference_max_abs": float(a.abs().max()),
            "cosine": float(torch.nn.functional.cosine_similarity(a, b, dim=0)),
            "top1_equal": top_a[0] == top_b[0],
            "top10_overlap": len(set(top_a) & set(top_b)),
        }
    else:
        checks["whole_model_logits"] = {"missing": True}

    gates = result["gates"]
    gates["loader_untouched_layers"] = [
        entry
        for entry in ("pre_conversion_identity",)
        if not (
            checks[entry]["mismatched"] == []
            and checks[entry]["only_marlin"] == []
            and checks[entry]["only_humming"] == []
            and checks[entry]["compared"] > 0
        )
    ]
    coverage = checks["checkpoint_coverage"]
    gates["checkpoint_coverage"] = not (
        coverage["layers_missing"] == []
        and coverage["unknown_layers"] == []
        and coverage["extra_confined_to_shared_kv"]
        and coverage["extra_sum_matches_total"]
        and coverage["scale_consistent_per_layer"]
        and coverage["scale_delta_matches_packed_delta"]
        and checks["layer_count"]["equal"]
        and checks["layer_count"]["marlin"] == checks["layer_count"]["checkpoint_fused_layers"]
    )
    gates["missing_text_core_weights_absent"] = not all(
        len(names) == 0 for names in checks["missing_text_core_weights"].values()
    )
    gates["no_ct_params_after_conversion"] = (
        not all(
            not entry["has_weight_packed"]
            and not entry["has_weight_shape"]
            and entry["has_weight_scale"]
            for entry in checks["humming_resident_params"].values()
        )
        or not checks["humming_resident_params"]
    )
    gates["converted_gemm_matches_reference"] = not gemm or not all(
        entry["humming_rel"] <= GEMM_REL_LIMIT
        and entry["humming_rel"] <= GEMM_VS_MARLIN_FACTOR * entry["marlin_rel"]
        for entry in gemm.values()
    )
    # Humming must run every forward, every captured decode graph must contain a
    # whole-model pass of Humming GEMMs (capture-phase count is a multiple of the
    # layer count), and the bounded replay micro-check must show a Humming kernel
    # in a replayed graph. Marlin must not be dispatched in the Humming arm.
    layers = checks["dispatch"]["humming"]["layers"]
    gates["humming_forward_and_graph"] = not (
        checks["dispatch"]["humming"]["humming_gemm"] > 0
        and checks["dispatch"]["humming"]["humming_gemm_capture"] > 0
        and layers > 0
        and checks["dispatch"]["humming"]["humming_gemm_capture"] % layers == 0
        and checks["dispatch"]["humming"]["graph_replay"] > 0
        and checks["dispatch"]["humming"]["marlin_linear"] == 0
        and checks["dispatch"]["marlin"]["marlin_linear"] > 0
        and checks["dispatch"]["marlin"]["humming_gemm"] == 0
        and checks["replay_kernel_check"].get("replay_executes_humming") is True
    )
    # Long generations: identical where the model's decision is not path-fragile.
    # A token difference is accepted only at the position whose prefill and decode
    # paths disagree within each backend (divergence/verdict.json).
    divergence = checks["divergence"]
    divergence_position = divergence.get("position")
    divergent_positions = [
        entry["first_diff"]
        for entry in checks["greedy_tokens"]["long"]
        if not entry["equal"]
    ]
    gates["greedy_tokens_identical"] = not (
        checks["greedy_tokens"]["capture_equal"]
        and checks["greedy_tokens"]["graph_equal"]
        and checks["greedy_tokens"]["long_all_equal"]
        or checks["greedy_tokens"]["capture_equal"]
        and checks["greedy_tokens"]["graph_equal"]
        and divergent_positions
        and divergence.get("divergence_is_path_fragile") is True
        and all(position == divergence_position for position in divergent_positions)
    )
    # Humming and Marlin are different INT4 kernels, so bitwise-equal logits are
    # not expected. Acceptance uses the sampling-relevant invariants (argmax and
    # top-10 ranking), a bound on the bulk deviation, and identical greedy token
    # sequences; exactness evidence is carried by the per-layer GEMM check
    # against an FP32 dequantized reference.
    logits_check = checks["whole_model_logits"]
    gates["whole_model_logits_match"] = "missing" in logits_check or not (
        logits_check["top1_equal"]
        and logits_check["top10_overlap"] >= 9
        and logits_check["l2_rel"] <= 0.15
    )

    failed = sorted(name for name, bad in gates.items() if bad)
    result["verdict"] = "PASS" if not failed else "FAIL"
    result["failed_gates"] = failed

    with open(os.path.join(out_dir, "verdict.json"), "w") as f:
        json.dump(result, f, indent=1, sort_keys=True)

    print(json.dumps({"verdict": result["verdict"], "failed": failed}, indent=1))
    for name, value in checks["converted_gemm"].items():
        print(
            f"gemm {name}: marlin={value['marlin_max_abs']:.5f} "
            f"humming={value['humming_max_abs']:.5f} "
            f"rel={value['humming_rel']:.4f} ref_mean={value['reference_abs_mean']:.4f}"
        )
    print("dispatch", json.dumps(checks["dispatch"], sort_keys=True))
    print("greedy", json.dumps(checks["greedy_tokens"], sort_keys=True))
    print("logits", json.dumps(checks["whole_model_logits"], sort_keys=True))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
