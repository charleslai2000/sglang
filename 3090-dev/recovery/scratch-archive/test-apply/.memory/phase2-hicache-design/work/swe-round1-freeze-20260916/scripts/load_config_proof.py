#!/usr/bin/env python3
"""Readiness proof: load the frozen Round-1 config with the pinned mini-SWE-agent
and resolve the model transport. Uses no endpoint and starts no GPU server."""

import json

from minisweagent.config import get_config_from_spec, get_config_path
from minisweagent.models import get_model

CFG = "/home/ubuntu/swe-round1/config/round1-swebench-local.yaml"

cfg = get_config_from_spec(CFG)
print("resolved config path :", get_config_path(CFG))
m = cfg["model"]
print("model_name           :", m["model_name"])
print("api_base             :", m["model_kwargs"]["api_base"])
print("api_key              :", m["model_kwargs"]["api_key"])
print("reasoning_effort     :", m["model_kwargs"]["reasoning_effort"])
print("drop_params          :", m["model_kwargs"]["drop_params"])
print("parallel_tool_calls  :", m["model_kwargs"]["parallel_tool_calls"])
print("cost_tracking        :", m["cost_tracking"])
print("agent.step_limit     :", cfg["agent"]["step_limit"])
print("agent.cost_limit     :", cfg["agent"]["cost_limit"])
print("environment_class    :", cfg["environment"]["environment_class"])
print("environment.cwd      :", cfg["environment"]["cwd"])

model = get_model(config=m)
print("model class          :", type(model).__name__)
print("model.config.model_name:", model.config.model_name)
print("model.config.model_kwargs:", json.dumps(model.config.model_kwargs, sort_keys=True))
print("CONFIG_LOADS_OK")
