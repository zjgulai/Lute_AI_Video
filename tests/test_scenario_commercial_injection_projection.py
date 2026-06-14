from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from src.pipeline.scenario_injection_plan import (
    CURRENT_STEP_INJECTION_KEY,
    SCENARIO_INJECTION_CONFIG_KEY,
    SCENARIO_INJECTION_EVIDENCE_LEVEL_KEY,
    SCENARIO_INJECTION_MODE_KEY,
    STEP_INJECTION_DATA_KEY,
)
from src.pipeline.state_manager import PipelineStateManager


def _plan_payload() -> dict[str, Any]:
    return {
        "scenario": "s1",
        "brand_id": "momcozy",
        "platform": "tiktok",
        "read_only": True,
        "evidence_level": "L2-fixture-or-dry-run",
        "steps": [
            {
                "scenario": "s1",
                "step": "strategy",
                "hard_token_ids": ["bat_hard_fixture"],
                "soft_token_ids": [],
                "source_token_ids": ["bat_hard_fixture"],
                "bundle_refs": ["BrandConstraintBundle"],
                "toolbox_refs": ["ImageToolbox"],
                "contract_refs": ["QualityContract"],
                "gate_checks": ["rights_pass"],
                "notes": [],
            }
        ],
    }


async def _save_state(label: str) -> None:
    await PipelineStateManager().save(
        label,
        {
            "label": label,
            "scenario": "s1",
            "current_step": "strategy",
            "config": {
                SCENARIO_INJECTION_CONFIG_KEY: _plan_payload(),
                SCENARIO_INJECTION_MODE_KEY: "read_only_blueprint",
                SCENARIO_INJECTION_EVIDENCE_LEVEL_KEY: "L2-fixture-or-dry-run",
            },
            "steps": {
                "strategy": {
                    "status": "pending",
                    "output": None,
                    STEP_INJECTION_DATA_KEY: {
                        "scenario": "s1",
                        "step": "strategy",
                        "prompt_payload": "must-not-leak",
                        "brand_asset_body": {"secret": "must-not-leak"},
                    },
                },
                "scripts": {"status": "pending", "output": None},
            },
            CURRENT_STEP_INJECTION_KEY: {
                "scenario": "s1",
                "step": "strategy",
                "prompt_payload": "must-not-leak",
            },
            "errors": [],
            "media_synthesis_errors": [],
        },
    )


@pytest.mark.asyncio
async def test_scenario_state_endpoints_project_read_only_commercial_injection(
    isolated_state_dir,
    auth_headers,
) -> None:
    from src.api import app

    label = "s1-commercial-injection-projection"
    await _save_state(label)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        state_response = await client.get(f"/scenario/s1/state/{label}", headers=auth_headers)
        steps_response = await client.get(f"/scenario/s1/state/{label}/steps", headers=auth_headers)
        status_response = await client.get(f"/scenario/s1/status/{label}", headers=auth_headers)

    assert state_response.status_code == 200, state_response.text
    assert steps_response.status_code == 200, steps_response.text
    assert status_response.status_code == 200, status_response.text

    state_payload = state_response.json()
    steps_payload = steps_response.json()
    status_payload = status_response.json()

    assert state_payload[CURRENT_STEP_INJECTION_KEY]["source_token_ids"] == ["bat_hard_fixture"]
    assert state_payload["steps"]["strategy"][STEP_INJECTION_DATA_KEY]["gate_checks"] == ["rights_pass"]
    assert steps_payload[CURRENT_STEP_INJECTION_KEY]["bundle_refs"] == ["BrandConstraintBundle"]
    strategy_row = next(item for item in steps_payload["steps"] if item["step_name"] == "strategy")
    assert strategy_row[STEP_INJECTION_DATA_KEY]["contract_refs"] == ["QualityContract"]
    assert status_payload[CURRENT_STEP_INJECTION_KEY]["toolbox_refs"] == ["ImageToolbox"]

    serialized = str({
        "state": state_payload[CURRENT_STEP_INJECTION_KEY],
        "step": state_payload["steps"]["strategy"][STEP_INJECTION_DATA_KEY],
        "row": strategy_row[STEP_INJECTION_DATA_KEY],
        "status": status_payload[CURRENT_STEP_INJECTION_KEY],
    })
    assert "must-not-leak" not in serialized
    assert "prompt_payload" not in serialized
    assert "brand_asset_body" not in serialized
