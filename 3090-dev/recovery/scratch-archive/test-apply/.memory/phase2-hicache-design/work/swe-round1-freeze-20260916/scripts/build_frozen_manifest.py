#!/usr/bin/env python3
"""Assemble the frozen Round-1 manifest from the collected, identity-checked inputs.

Reads (all under this freeze root unless noted):
  data/blind_round1_sample.py310.json   sampling output executed on VM901 (py3.10)
  data/blind24-pull-results.json        per-image digests/ids/sizes (from VM901)
  data/blind24-verify.json              digest + baked-in base_commit verification
  config/official-swebench-config.yaml
  config/round1-swebench-local.yaml
  data/swe-verified-test-instances-78f471bf.json
  data/dev_exclusions_25.json
Writes round1-frozen-manifest.json.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CFG = ROOT / "config"
EVID = ROOT / "evidence"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(p):
    return json.loads(Path(p).read_text())


FAIRNESS_CONTRACT = {
    "statement": (
        "All four Round-1 models run under one identical mini-SWE-agent configuration. "
        "Only the following model-specific differences are allowed: "
        "(a) endpoint / base URL, (b) model name, "
        "(c) a required chat-template / protocol adapter. "
        "NOT allowed: model-specific prompts, model-specific tools, model-specific repo hints, "
        "model-specific turn limits."
    ),
    "allowed_model_specific_differences": [
        "endpoint/base_url",
        "model_name",
        "required_chat_template_or_protocol_adapter",
    ],
    "forbidden_model_specific_differences": [
        "prompts (system/instance/observation/format-error templates)",
        "tools (tool schema)",
        "repo hints",
        "turn limits (step_limit / cost_limit)",
    ],
    "reasoning_policy": {
        "main_round": "medium",
        "mtp": "OFF for all SWE runs (enforced at endpoint provisioning; server-side flag)",
        "low": "may be used later for an efficiency curve (not the primary comparison)",
        "xhigh": "diagnostic-only; must never enter the primary comparison",
    },
}

ROUND1_PROTOCOL = {
    "status": "RECORDED, NOT RUN (no model endpoints exist yet; GPU is occupied by another task)",
    "models": 4,
    "tasks": 24,
    "metric": "pass@1",
    "seed": "same seed for a given task across all four models (frozen default seed=0, passed as model.seed)",
    "harness": "identical mini-SWE-agent 2.4.6 config (frozen file) for all four models",
    "verifier": "VM901 official swebench 5.0.2 (swebench eval) over the pinned dataset",
    "per_attempt_record_fields": [
        "resolved", "tool_calls", "reasoning_tokens", "generated_tokens",
        "wall_time", "gpu_time", "retries",
    ],
    "screening_caveat": (
        "The 24 cases are a SCREENING set only; a 24-case pass rate is NOT a final model ranking."
    ),
}

ROUND2_DESIGN = {
    "status": "DESIGNED, NOT RUN",
    "models": "top-2 from Round 1 only",
    "additional_tasks": "24-48 ADDITIONAL new/unseen blind tasks",
    "extra_seeds": "2 extra seeds on each model's Round-1 FAILED cases",
    "purpose": "generalization (new tasks) AND stochastic variance (extra seeds on failures)",
    "explicit_non_sufficiency": (
        "Re-running only the same 24 Round-1 tasks with different seeds is INSUFFICIENT."
    ),
}


def main():
    sample = load(DATA / "blind_round1_sample.py310.json")
    pulls = {x["instance_id"]: x for x in load(DATA / "blind24-pull-results.json")}
    verify = {x["instance_id"]: x for x in load(DATA / "blind24-verify.json")}
    instances = load(DATA / "swe-verified-test-instances-78f471bf.json")
    exclusions = load(DATA / "dev_exclusions_25.json")
    cal_details = {x["instance_id"]: x for x in load(EVID / "calibration-details.json")}
    blind_details = {x["instance_id"]: x for x in load(EVID / "blind-details.json")}

    cases = []
    for sel in sample["selected"]:
        i = sel["instance_id"]
        p = pulls.get(i, {})
        v = verify.get(i, {})
        cases.append({
            "instance_id": i,
            "repo": sel["repo"],
            "base_commit": sel["base_commit"],
            "dataset_image_ref": p.get("dataset_ref"),
            "ghcr_ref": p.get("ghcr_ref"),
            "image_digest": p.get("image_digest"),
            "image_id": p.get("image_id"),
            "size_bytes": p.get("size_bytes"),
            "image_head": v.get("image_head"),
            "base_commit_match": v.get("base_commit_match"),
            "local_tag": blind_details.get(i, {}).get("local_tag"),
            "label": "BLIND ROUND-1 / SCORED",
        })

    manifest = {
        "manifest_id": "swe-round1-freeze-20260916",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": (
            "SWE Round-1 environment/corpus/harness freeze + readiness validation ONLY. "
            "No model was run; no GPU used; no production runtime touched."
        ),
        "corpus": {
            "dataset": {
                "repo_id": "SWE-bench/SWE-bench_Verified",
                "revision": "78f471bf655a3137b2e8a75af1501690ec009ec3",
                "split": "test",
                "rows": len(instances),
                "parquet_sha256": "030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25",
                "selection_rationale": (
                    "Owner named princeton-nlp/SWE-bench_Verified. The pinned official verifier "
                    "(swebench 5.0.2 cli/_datasets.py) resolves the 'verified' alias to "
                    "SWE-bench/SWE-bench_Verified, so that canonical id is used for corpus/verifier "
                    "agreement. The princeton-nlp alias (revision c104f840cc67f8b6eec6f759ebc8b2693d585d4a) "
                    "was downloaded and compared: identical 500 instance ids and identical base_commits."
                ),
                "princeton_nlp_alias": {
                    "repo_id": "princeton-nlp/SWE-bench_Verified",
                    "revision": "c104f840cc67f8b6eec6f759ebc8b2693d585d4a",
                    "parquet_sha256": "a45b1fe4e2f0c8390b2b2938ac83e92ed5979000856808f3679c07812e9e6dcd",
                    "instance_set_identical": True,
                },
            },
            "contaminated_calibration_set": {
                "count": len(exclusions),
                "label": "CALIBRATION / NON-SCORED",
                "ids": exclusions,
                "image_digest_map": [
                    {"instance_id": k, "image_digest": cal_details[k].get("image_digest"),
                     "source_ref": cal_details[k].get("source_ref"),
                     "local_tag": cal_details[k].get("local_tag")}
                    for k in sorted(cal_details)
                ],
                "labeling_note": (
                    "Docker image labels are immutable at build time, so the CALIBRATION mapping is "
                    "recorded here (image digest -> CALIBRATION) and additionally surfaced on VM901 as a "
                    "local tag `swe-calibration/<repo>__<inst>:non-scored` where the image exists. "
                    "The 25th id (psf__requests-1921) has no pre-pulled image."
                ),
            },
            "blind_round1_set": {
                "count": len(cases),
                "label": "BLIND ROUND-1 / SCORED",
                "sampling": {
                    "seed": sample["seed"],
                    "algorithm": sample["algorithm"],
                    "repo_quotas": sample["repo_quotas"],
                    "remaining_repo_counts": sample["remaining_repo_counts"],
                    "allocation_diagnostics": sample["allocation_diagnostics"],
                    "script": "scripts/sample_blind_round1.py",
                    "script_sha256": sha256(ROOT / "scripts" / "sample_blind_round1.py"),
                    "reproduced_on": [
                        "VM901 python 3.10.12",
                        "local python 3.12.3 (identical selected ids + quotas)",
                    ],
                },
                "cases": cases,
            },
            "screening_caveat": (
                "The 24 cases are a SCREENING set only; a 24-case pass rate is NOT a final model ranking."
            ),
        },
        "harness": {
            "agent": {
                "name": "mini-swe-agent",
                "publisher": "SWE-agent team (Princeton/Stanford)",
                "version": "2.4.6",
                "source": "PyPI (mini-swe-agent==2.4.6)",
                "wheel_sha256": "a35463c553ac825c7773b03cfa69cd44958e3af20155dcc5711fdf9e4c67cd54",
                "install": {
                    "isolation": "virtualenv at /home/ubuntu/venvs/mini-swe-agent",
                    "commands": [
                        "virtualenv -p python3 ~/venvs/mini-swe-agent",
                        "~/venvs/mini-swe-agent/bin/pip install --upgrade pip setuptools wheel",
                        "~/venvs/mini-swe-agent/bin/pip install mini-swe-agent==2.4.6",
                    ],
                    "resolved_version": "2.4.6",
                    "python": "3.10.12",
                    "litellm": "1.101.0",
                },
                "console_scripts": ["mini", "mini-e", "mini-extra", "mini-swe-agent"],
            },
            "official_base_config": {
                "path": "minisweagent/config/benchmarks/swebench.yaml",
                "copy": "config/official-swebench-config.yaml",
                "sha256": sha256(CFG / "official-swebench-config.yaml"),
            },
            "frozen_round1_config": {
                "path": "config/round1-swebench-local.yaml",
                "sha256": sha256(CFG / "round1-swebench-local.yaml"),
                "generator": "scripts/make_round1_config.py",
                "parameterization": {
                    "model.model_name": "openai/LOCAL_MODEL (per-model override)",
                    "model.model_kwargs.api_base": "http://127.0.0.1:30000/v1 (per-model override)",
                    "model.model_kwargs.api_key": "EMPTY (local OpenAI-compatible endpoint)",
                    "model.model_kwargs.reasoning_effort": "medium (owner-fixed)",
                    "model.model_kwargs.drop_params": True,
                    "model.model_kwargs.parallel_tool_calls": True,
                    "model.cost_tracking": "ignore_errors (local endpoints not in LiteLLM price registry)",
                    "agent.cost_limit": 0.0,
                    "agent.step_limit": 250,
                },
                "unchanged_from_official": (
                    "system_template, instance_template, observation_template, "
                    "format_error_template, environment block (cwd /testbed, timeout 60, docker)"
                ),
                "override_mechanism": (
                    "per-model values (and any allowed protocol adapter) are applied with `-c key=value` "
                    "specs on the mini-extra swebench command line; see scripts/run_round1_attempt.sh"
                ),
            },
            "fairness_contract": FAIRNESS_CONTRACT,
            "local_data_adaptation": {
                "reason": "VM901 cannot reach huggingface.co (TLS reset by peer) and registry-1.docker.io "
                          "(connection reset), so the pinned dataset is staged locally and images are "
                          "pre-pulled from GHCR and tagged with the dataset's `swebench/...` names.",
                "local_dataset_dir": "/home/ubuntu/swe-round1/data/swe-verified-78f471bf "
                                     "(standard HF layout: data/test-00000-of-00001.parquet)",
                "verified": "datasets.load_dataset(<local dir>, split='test') -> 500 rows",
            },
        },
        "verifier": {
            "host": "swe-harness-901 (ssh alias swe901)",
            "swebench_version": "5.0.2",
            "command_template": "swebench eval verified -p <predictions.jsonl> --run-id <id> -j 1 --report-dir <dir>",
            "dataset_for_verifier": "pinned local dataset dir (SWE-bench/SWE-bench_Verified @ 78f471bf)",
            "per_instance_timeout_s": 1800,
            "image_source_on_vm901": "local tags swebench/sweb.eval.x86_64.<repo>_1776_<inst>:latest "
                                     "pulled from ghcr.io/epoch-research and digest-pinned",
            "fail_closed": "no verifier => no successful result",
        },
        "round1_protocol": ROUND1_PROTOCOL,
        "round2_design": ROUND2_DESIGN,
        "reproduction_commands": {
            "fetch_pinned_parquet": (
                "curl -sSL -o test-verified-78f471bf.parquet "
                "'https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/resolve/"
                "78f471bf655a3137b2e8a75af1501690ec009ec3/data/test-00000-of-00001.parquet'"
            ),
            "parse_parquet_to_instances_json": (
                "python -c \"import pyarrow.parquet as pq,json;"
                "t=pq.read_table('test-verified-78f471bf.parquet');"
                "json.dump([{'instance_id':i,'repo':r,'base_commit':c} for i,r,c in "
                "zip(t.column('instance_id').to_pylist(),t.column('repo').to_pylist(),"
                "t.column('base_commit').to_pylist())],open('swe-verified-test-instances-78f471bf.json','w'))\""
            ),
            "sample_blind24": (
                "python3 scripts/sample_blind_round1.py "
                "--instances data/swe-verified-test-instances-78f471bf.json "
                "--exclusions data/dev_exclusions_25.json "
                "--out data/blind_round1_sample.py310.json   # seed 20260916"
            ),
            "pull_and_pin_images": (
                "python3 scripts/pull_blind24.py ; python3 scripts/finalize_blind24.py "
                "(pull GHCR refs, tag dataset names, record digests + baked base_commit)"
            ),
            "generate_frozen_config": "python3 scripts/make_round1_config.py",
            "install_harness": (
                "virtualenv -p python3 ~/venvs/mini-swe-agent && "
                "~/venvs/mini-swe-agent/bin/pip install mini-swe-agent==2.4.6"
            ),
            "config_load_check": "MSWEA_SILENT_STARTUP=1 ~/venvs/mini-swe-agent/bin/python scripts/load_config_proof.py",
            "fail_closed_check": (
                "mini -c config/round1-swebench-local.yaml -c environment.environment_class=local "
                "-c model.model_kwargs.api_base=http://127.0.0.1:9/v1 -t 'print hello' "
                "(exit 1, OpenAIException - Connection error)"
            ),
        },
        "environment_findings": {
            "docker_root_dir_reported": "/data/docker",
            "actual_image_store_at_pull_time": (
                "/var/lib/containerd (io.containerd.snapshotter.v1.overlayfs) on / (root FS); confirmed "
                "by /proc/<containerd pid>/fd. /data/docker held only Docker metadata "
                "(buildkit/network/volumes) during the pulls."
            ),
            "note": (
                "Docker 29.1.3 uses the containerd image store, so `data-root: /data/docker` does NOT "
                "hold image bytes. At pull time the 24 calibration + 24 blind images lived in "
                "/var/lib/containerd on /dev/sda1; /dev/sda1 used grew from 35G to 47G (15G free left). "
                "Root-FS capacity is therefore the real constraint for Round-2 image growth, not the "
                "185G free on /data."
            ),
            "concurrent_external_action_observed": {
                "process": "rsync -aHAX --numeric-ids /var/lib/containerd/ /data/containerd/",
                "launcher": "sudo nohup setsid bash -c ... > /tmp/containerd-migrate.log (root-owned)",
                "started_utc": "2026-09-16T11:53:47Z",
                "observed_running_at_utc": "2026-09-16T11:57Z",
                "attribution": (
                    "NOT started by this freeze task; appears to be an orchestrator/host action "
                    "relocating the containerd store to /data. This task did not touch it."
                ),
                "effect": (
                    "A mirror of the containerd store appears at /data/containerd; /data usage grew from "
                    "~1G to ~16G during the freeze. The effective store location may change once that "
                    "external migration completes."
                ),
            },
            "capacity_at_freeze": {
                "root_fs_free_gb": 15,
                "root_fs_total_gb": 62,
                "data_free_gb": 175,
            },
            "registry_reachability_from_vm901": {
                "ghcr.io": "reachable (slow/flaky at times)",
                "registry-1.docker.io": "NOT reachable (connection reset by peer)",
                "pypi.org": "reachable",
                "huggingface.co": "NOT reachable (TLS connection reset by peer)",
            },
            "endpoints": "the four SGLang model endpoints do not exist yet; nothing was started",
        },
        "non_touch_attestation": {
            "models_started": 0,
            "gpu_used": False,
            "production_runtime_touched": False,
            "model_servers_started": 0,
            "containers_run_for_scoring": 0,
            "containers_run_for_readonly_basecommit_check": "24 (docker run --rm --network none --entrypoint git)",
            "actions_during_freeze": [
                "read-only docker inspection",
                "docker pull (GHCR) of the 24 blind eval images",
                "docker tag to the dataset image names (local alias)",
                "docker tag of CALIBRATION / BLIND classification aliases",
                "pip/virtualenv install of mini-SWE-agent 2.4.6 on VM901",
                "config-load + fail-closed test against 127.0.0.1:9 (no endpoint)",
            ],
            "not_done_by_this_task": [
                "no model server started, no GPU used, no model inference performed",
                "no production runtime touched",
                "the concurrent root `containerd-migrate` rsync to /data was NOT started by this task",
            ],
        },
        "evidence": {
            "docker_images_after": "evidence/docker-images-swe-after.txt, evidence/docker-images-raw-after.txt",
            "docker_system_df": "evidence/docker-system-df.txt",
            "dataset_api": (
                "evidence/dataset/hf-api-canonical.json, evidence/dataset/hf-api-princeton.json, "
                "evidence/dataset/hf-tree-canonical.json, evidence/dataset/hf-tree-princeton.json"
            ),
            "config_load_proof": "evidence/config-load-proof.txt",
            "fail_closed_proof": "evidence/failclosed-no-endpoint.out",
            "harness_install": "evidence/harness-install-evidence.md, evidence/mini-swe-agent-2.4.6-install.log",
            "pip_lock": "evidence/mini-swe-agent-2.4.6-pip-freeze.txt",
            "image_verification": "data/blind24-verify.json, data/blind24-pull-results.json",
            "classification_tags": "evidence/calibration-details.json, evidence/blind-details.json",
            "calibration_retention": "evidence/calibration-retention-check.txt",
            "reachability": "evidence/vm901-reachability.txt",
            "final_state": "evidence/vm901-final-state.txt",
        },
        "frozen_inputs_sha256": {
            "data/swe-verified-test-instances-78f471bf.json": sha256(DATA / "swe-verified-test-instances-78f471bf.json"),
            "data/dev_exclusions_25.json": sha256(DATA / "dev_exclusions_25.json"),
            "data/blind_round1_sample.py310.json": sha256(DATA / "blind_round1_sample.py310.json"),
            "config/official-swebench-config.yaml": sha256(CFG / "official-swebench-config.yaml"),
            "config/round1-swebench-local.yaml": sha256(CFG / "round1-swebench-local.yaml"),
        },
    }
    out = ROOT / "round1-frozen-manifest.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print("wrote", out)
    print("cases:", len(cases),
          "digests:", sum(1 for c in cases if c["image_digest"]),
          "commit_match:", sum(1 for c in cases if c["base_commit_match"]))


if __name__ == "__main__":
    main()
