import json, os, re, datetime, hashlib

W = "/home/ubuntu/workspaces/3rdparty/sglang-3090-24g-opt/.memory/phase2-hicache-design/work/swe-corpus-freeze-20260916"
INV = json.load(open("/tmp/opencode/vm901-inventory.json"))
RAW = [l.rstrip("\n") for l in open("/tmp/opencode/docker-images-raw.txt") if l.strip()]
BC  = [l.rstrip("\n") for l in open("/tmp/opencode/basecommits.tsv") if l.strip()]

# ---- images ----
imgs = {}
for l in RAW:
    p = l.split("|")
    if not p[0].startswith("ghcr.io/epoch-research"): continue
    repo, tag, digest, iid, size = p[0], p[1], p[2], p[3], p[4].strip()
    inst = repo.split("swe-bench.eval.x86_64.")[1]
    imgs[inst] = {"image_ref": repo+":"+tag, "digest": digest, "image_id": iid, "size": size}
bc = {}
for l in BC:
    lab, base, dig, iid, img = l.split("\t")
    r, env, inst = lab.split("|")
    bc[inst] = {"repo": r, "env_image": env, "base_commit": base, "ref_digest": dig, "image_id": iid, "image": img}

cases = []
for inst in sorted(imgs):
    d = imgs[inst]; b = bc[inst]
    sha = d["digest"] if d["digest"].startswith("sha256:") else d["ref_digest"].split("@")[-1]
    cases.append({
        "task_id": inst, "repo": b["repo"], "base_commit": b["base_commit"],
        "image_ref": d["image_ref"],
        "pinned_ref": d["image_ref"].split(":")[0] + "@" + sha,
        "image_digest": sha, "image_id": d["image_id"], "size": d["size"],
        "image_labels": {"swe_bench_repo": b["repo"], "swe_bench_instance_id": inst, "swe_bench_env_image": b["env_image"]},
        "prompt": None, "tool_schema": None, "timeout_s_agent": None,
        "reasoning_policy": None,
        "verifier_identity": "swebench 5.0.2 :: swebench eval verified (dataset SWE-bench/SWE-bench_Verified, split test)",
        "result_schema_ref": "swebench report.json v2 (see manifest.result_schema)"
    })

# ---- dev exclusion derivation ----
inst_src = {}
def add(inst, cat, path):
    inst_src.setdefault(inst, {"instance_id": inst, "sources": [], "categories": []})
    if path not in inst_src[inst]["sources"]: inst_src[inst]["sources"].append(path)
    if cat not in inst_src[inst]["categories"]: inst_src[inst]["categories"].append(cat)

for p, d in INV["prediction_files"].items():
    if "unique" not in d: continue
    cat = None
    if "predictions-48" in p: cat = "vm901_harness_model_predictions(gpu-cpu combined)"
    elif "predictions-cpu" in p: cat = "vm901_harness_model_predictions(cpu-ornith-35b)"
    elif "predictions-gpu" in p: cat = "vm901_harness_model_predictions(gpu-qwen3-27b)"
    elif "j1c1" in p: cat = "harness_calibration_j1c1(qwen3-27b-iq3s-c1)"
    elif "j1v1" in p: cat = "harness_calibration_j1v1(qwen3-27b-iq3s)"
    elif "c2-baseline" in p: cat = "harness_calibration_c2b_c2q(qwen3-27b-c2)"
    else: cat = "other_prediction_artifact"
    for i in d["unique"]: add(i, cat, p.replace("/home/ubuntu", "~/"))

for k, ids in INV["report_runs"].items():
    run, model = k.split("|")
    if run == "r1": cat = "vm901_harness_r1_eval(%s)" % model
    elif run.startswith("c2"): cat = "harness_calibration_c2b_c2q(qwen3-27b-c2)"
    elif run.startswith("j1"): cat = "harness_calibration_%s(qwen3-27b-iq3s)" % run
    else: cat = "harness_eval(%s)" % run
    for i in ids: add(i, cat, "~/logs/run_evaluation/%s/%s/%s/report.json" % (run, model, i))

dev = [inst_src[i] for i in sorted(inst_src)]
dev_ids = set(inst_src)
img_ids = set(imgs)

# ---- schema ----
report_schema = {
  "run_level_json": {
    "keys": ["total_instances","submitted_instances","completed_instances","resolved_instances","unresolved_instances",
             "infra_failure_instances","ambiguous_failure_instances","empty_patch_instances","error_instances",
             "completed_ids","incomplete_ids","empty_patch_ids","submitted_ids","resolved_ids","unresolved_ids",
             "infra_failure_ids","ambiguous_failure_ids","failure_reasons","error_ids","schema_version",
             "unstopped_instances","unstopped_containers","unremoved_images"],
    "observed_schema_version": 2,
    "observability": "swebench 5.0.2 --report-dir (<run-id>.<instance>.json)"
  },
  "per_instance_report_json": {
    "keys": ["patch_is_None","patch_exists","patch_successfully_applied","resolved","infra_failure","tests_status"],
    "terminal_states_observed": ["resolved","unresolved","empty_patch","infra_failure","error"]
  },
  "note": "Copied verbatim from VM901 artifacts: c2-baseline-verifier/runs/*.json (run level) and logs/run_evaluation/**/report.json (per-instance)."
}

conflict = {
  "type": "FROZEN_BASIS_IDENTICAL_TO_DEV_EXCLUSION_SET",
  "severity": "blocking",
  "prepulled_official_image_count": len(img_ids),
  "derived_dev_exclusion_count": len(dev_ids),
  "intersection_count": len(img_ids & dev_ids),
  "dev_only": sorted(dev_ids - img_ids),
  "images_not_in_dev": sorted(img_ids - dev_ids),
  "scored_set_cardinality_if_mandatory_exclusion_applied": len(img_ids - dev_ids),
  "detail": ("Every one of the 24 pre-pulled ghcr.io/epoch-research official eval images corresponds to an "
             "instance that appears in VM901's own prior harness artifacts (prediction files and/or "
             "run_evaluation report.json). Applying the owner's mandatory dev/calibration exclusion to the "
             "preferred 24-image basis therefore yields an EMPTY scored set. The two stated rules "
             "('prefer exactly those 24' and 'exclude every dev instance') are mutually inconsistent on the "
             "current VM901 state.")
}

scoring = {
  "round_1": {"metric": "pass@1", "models": ["M1","M2","M3","M4"], "seeds_per_case": 1,
              "advance_rule": "top-2 models by pass@1 advance"},
  "round_2": {"metric": "pass@3 + variance", "models": "top-2 from round 1",
              "seeds": "2 additional seeds", "cases": "only that model's round-1 failed cases"},
  "aggregation": "per (model, task, seed, attempt); verified success requires swebench eval 'resolved' (verifier), not process exit",
  "effort": {"primary": ["low","medium"], "diagnostic_only": "xhigh"},
  "network": "off", "privilege": "unprivileged",
  "seed_definition": "UNRESOLVED - seed derivation not present in VM901 artifacts",
  "per_attempt_record_fields": ["task_id","model_identity","effort","seed","attempt","image_digest","verifier_identity",
                                "terminal_state","resolved_bool","failure_reason","agent_harness_contract_sha256","gpu_hours"]
}

harness = {
  "status": "MISSING_EVIDENCE",
  "reason": ("No agent harness, prompt template, tool schema, agent timeout, or reasoning-policy config exists on "
             "VM901 or in /home/ubuntu/workspaces. VM901 only consumes already-produced prediction JSONL "
             "({'instance_id','model_name_or_path','model_patch'}) and runs `swebench eval verified`. The model-side "
             "contract lived on the producing host (not in scope/authority here)."),
  "searched_locations": [
    "swe901:~/ (all *.py/*.sh; only swebench eval wrappers run_c2b.sh/run_c2q.sh/parse_results.py exist)",
    "swe901:/usr/local/lib/python3.10/dist-packages/swebench (verifier package only)",
    "local:/home/ubuntu/workspaces/** (no SWE harness)",
    "local:.memory/** (no SWE corpus/prompt contract; COMMON-SWE-VM-PROTOCOL-v1 explicitly leaves prompt/task IDs undefined)"
  ],
  "required_before_execution": ["exact prompt (system+user template)","tool schema","agent timeout","reasoning policy",
                                "max tokens / context budget","model endpoint + revision hashes","seed derivation"]
}

non_touch = {
  "models_started": 0, "gpu_used": False,
  "production_runtime_touched": False,
  "vm901_containers_running_during_freeze": 0,
  "vm901_model_processes": 0,
  "note": ("Only read-only inspection was performed: `docker images`, `docker image inspect`, and read-only "
           "`docker run --rm --network none --entrypoint git <img> -C /testbed rev-parse HEAD` to read the "
           "base_commit baked into each image. No model was launched, no GPU was used, no production service "
           "was touched, and no swebench evaluation was executed.")
}

resolution = {
  "recommended": "R1",
  "R1_additive_repin": {
    "summary": ("Keep the official-image family and verifier identity, but freeze the scored corpus by a "
                "deterministic disjointness rule over SWE-bench_Verified test split. Recommended concrete rule: "
                "let S = lexicographically sorted instance_ids of SWE-bench_Verified (test); let D = derived "
                "dev-exclusion set (25 ids, see dev_exclusion_set); for each repo, take the first instances of "
                "S\\D matching the current per-repo quota (8 django, 3 pytest-dev, 3 pydata__xarray, 2 sympy, "
                "2 astropy, 1 each sphinx-doc/pylint-dev/psf/scikit-learn/mwaskom/matplotlib = 24); pull the "
                "official ghcr.io/epoch-research images and pin by digest."),
    "preserves": ["24 cases", "official eval images", "swebench 5.0.2 verifier", "deterministic, no hand-picking",
                  "anti-contamination disjointness", "repo/category coverage"],
    "cost": "requires pulling up to 24 new images on swe901 (network dependency; docker.io showed timeouts in r1, ghcr availability to confirm)",
    "needs": "owner approval + registry reachability check before bring-up"
  },
  "R2_no_pull_fallback": {
    "summary": ("If no new images can be pulled, the corpus cannot be frozen NOW: the only pre-pulled basis is fully "
                "dev-contaminated. Either (a) owner explicitly narrows the exclusion rule (e.g. excludes only "
                "instances used for prompt tuning, retaining runtime-only bring-up instances) with a recorded "
                "rationale, or (b) defer scored-corpus freeze until a disjoint image set is available."),
    "risk": "reintroduces selection/calibration bias the owner's ruling exists to prevent"
  },
  "rejected": {"R3_use_24_minus_dev": "yields 0 cases (all 24 contaminated)"}
}

manifest = {
  "manifest_id": "swe-corpus-freeze-20260916",
  "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "protocol_id": "common-swe-vm-protocol-v1",
  "status": "BLOCKED_OWNER_DECISION",
  "status_reason": ("Mandatory dev-exclusion set is identical to the 24-image frozen basis (24/24 overlap) => scored "
                    "set empty; also the model-side agent harness contract (prompt/tool schema/timeout/reasoning "
                    "policy) is absent from all in-scope artifacts."),
  "scope": "corpus + verifier freeze ONLY; no model bring-up, no GPU, no production runtime",
  "verifier_authority": {
    "host": "swe-harness-901 (ssh alias swe901)", "os": "Linux swe-harness-901 5.15.0-191-generic x86_64",
    "docker": "29.1.3", "swebench": "5.0.2", "gpu_present": False
  },
  "verifier_identity": {
    "command": "swebench eval verified -p <predictions.jsonl> --run-id <id> -j 1 --report-dir <dir> -i <instance_id>",
    "dataset": "SWE-bench/SWE-bench_Verified", "split": "test (default)",
    "per_instance_timeout_s_default": 1800, "workers_default": 4, "workers_observed": 1,
    "image_family": "ghcr.io/epoch-research/swe-bench.eval.x86_64.<repo>__<instance>:latest (pinned by digest)",
    "fail_closed": "no verifier => no successful result (per COMMON-SWE-VM-PROTOCOL-v1)"
  },
  "result_schema": report_schema,
  "scoring_protocol": scoring,
  "prepulled_official_images": cases,
  "dev_exclusion_set": {
    "derived_count": len(dev_ids),
    "rule": ("Union of every instance_id appearing in VM901 prior harness artifacts: prediction JSONL files under "
             "~/ (predictions-48/cpu/gpu, j1c1, j1v1) and every run_evaluation/**/report.json "
             "(r1, c2b, c2q, j1c1, j1v1)."),
    "instances": dev
  },
  "conflict": conflict,
  "agent_harness_contract": harness,
  "proposed_resolution": resolution,
  "non_touch_attestation": non_touch,
  "evidence_artifacts": [
    "evidence/docker-images-raw.txt",
    "evidence/basecommits.tsv",
    "evidence/vm901-harness-inventory.json",
    "evidence/overlap-analysis.txt",
    "evidence/README-evidence.md"
  ]
}

with open(W+"/corpus-manifest.json","w") as f:
    json.dump(manifest, f, indent=2, sort_keys=False)

# overlap analysis text
lines = []
lines.append("SWE corpus freeze - overlap analysis (swe-corpus-freeze-20260916)")
lines.append("="*70)
lines.append("pre-pulled official ghcr.io/epoch-research images: %d" % len(img_ids))
lines.append("derived dev-exclusion instances:                    %d" % len(dev_ids))
lines.append("intersection:                                       %d" % len(img_ids & dev_ids))
lines.append("dev-only (no pre-pulled image):                     %s" % sorted(dev_ids - img_ids))
lines.append("images-only (not seen in dev artifacts):            %s" % sorted(img_ids - dev_ids))
lines.append("=> scored set if mandatory exclusion applied:       %d cases" % len(img_ids - dev_ids))
lines.append("")
lines.append("Per-instance derivation (instance -> artifact sources):")
for d in dev:
    lines.append("  %s" % d["instance_id"])
    for s in d["sources"]:
        lines.append("      - %s" % s)
open(W+"/evidence/overlap-analysis.txt","w").write("\n".join(lines)+"\n")
print("wrote manifest with %d cases and %d dev instances" % (len(cases), len(dev_ids)))
print("conflict intersection:", len(img_ids & dev_ids))
