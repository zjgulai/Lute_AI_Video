"""Strategy source loader — loads scenario-specific prompt templates and config.

Each scenario directory under strategy_source/ contains:
  - strategy_prompt.md      # Scenario-specific system prompt additions
  - audit_weights.json      # Per-criterion weight overrides for auditor
  - quality_thresholds.json # Auto-approve / reject thresholds per checkpoint

Usage:
    from strategy_source import load_scenario
    scenario = load_scenario("influencer_remix")
    system_prompt_addendum = scenario["system_prompt_addendum"]
"""
from __future__ import annotations

import json
import os
from typing import Any

_SCENARIO_DIR = os.path.dirname(os.path.abspath(__file__))
_STRATEGY_SOURCE_DIR = _SCENARIO_DIR


def load_scenario(scenario: str) -> dict[str, Any]:
    """Load scenario configuration from strategy_source/<scenario>/.

    Returns a dict with keys:
      - system_prompt_addendum (str): text appended to the base system prompt
      - audit_weights (dict): criterion name -> weight (0-1)
      - quality_thresholds (dict): {"auto_approve": float, "auto_reject": float}
      - platform_config (dict): per-platform script length and format hints

    Falls back to "general" if the requested scenario doesn't exist.
    """
    scenario_dir = os.path.join(_STRATEGY_SOURCE_DIR, scenario)
    if not os.path.isdir(scenario_dir):
        scenario_dir = os.path.join(_STRATEGY_SOURCE_DIR, "general")
        if not os.path.isdir(scenario_dir):
            return _default_config()

    result: dict[str, Any] = {}

    # Prompts
    prompt_path = os.path.join(scenario_dir, "strategy_prompt.md")
    if os.path.isfile(prompt_path):
        with open(prompt_path) as f:
            result["system_prompt_addendum"] = f.read()
    else:
        result["system_prompt_addendum"] = ""

    # Audit weights
    weights_path = os.path.join(scenario_dir, "audit_weights.json")
    if os.path.isfile(weights_path):
        with open(weights_path) as f:
            result["audit_weights"] = json.load(f)
    else:
        result["audit_weights"] = {}

    # Quality thresholds
    thresholds_path = os.path.join(scenario_dir, "quality_thresholds.json")
    if os.path.isfile(thresholds_path):
        with open(thresholds_path) as f:
            result["quality_thresholds"] = json.load(f)
    else:
        result["quality_thresholds"] = {"auto_approve": 0.90, "auto_reject": 0.60}

    # Platform config
    platform_path = os.path.join(scenario_dir, "platform_config.json")
    if os.path.isfile(platform_path):
        with open(platform_path) as f:
            result["platform_config"] = json.load(f)
    else:
        result["platform_config"] = {}

    return result


def _default_config() -> dict[str, Any]:
    """Return safe defaults when no scenario config is found."""
    return {
        "system_prompt_addendum": "",
        "audit_weights": {},
        "quality_thresholds": {"auto_approve": 0.90, "auto_reject": 0.60},
        "platform_config": {},
    }
