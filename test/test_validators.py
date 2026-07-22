"""Validation behavior for complete workflow input and request values."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
from workflow_container_contract import WorkflowContractError, WorkflowInputSchema

from brand_size_chart.model import WorkflowBrandSizeChartInput, WorkflowBrandSizeChartRequest


def test_priority_country_code_has_identical_schema_and_model_contract() -> None:
    """Keep public country and source-type identity constraints equal at both input boundaries."""

    schema = WorkflowInputSchema.from_path(Path("input.schema.json"))
    valid_payload = _input_payload_get()

    assert schema.input_validate(valid_payload) == valid_payload
    assert (
        WorkflowBrandSizeChartInput.model_validate_json(json.dumps(valid_payload)).request.priority_country_code == "TR"
    )
    for invalid_value in ("tr", " TR", "TR "):
        invalid_payload = deepcopy(valid_payload)
        invalid_payload["request"]["priority_country_code"] = invalid_value
        with pytest.raises(WorkflowContractError):
            schema.input_validate(invalid_payload)
        with pytest.raises(ValueError):
            WorkflowBrandSizeChartInput.model_validate_json(json.dumps(invalid_payload))
    duplicate_source_type_payload = deepcopy(valid_payload)
    duplicate_source_type_payload["request"]["source_type_allow_list"] = [
        "official_brand_size_guide",
        "official_brand_size_guide",
    ]
    with pytest.raises(WorkflowContractError):
        schema.input_validate(duplicate_source_type_payload)
    with pytest.raises(ValueError):
        WorkflowBrandSizeChartInput.model_validate_json(json.dumps(duplicate_source_type_payload))


def test_request_rejects_duplicate_source_types() -> None:
    """Keep source type allow-list identity unique at the complete request boundary."""

    with pytest.raises(ValueError, match="unique"):
        WorkflowBrandSizeChartRequest(
            brand_list=["Brand"],
            priority_country_code="TR",
            product_type_request_list=[],
            source_type_allow_list=["official_brand_size_guide", "official_brand_size_guide"],
        )


def _input_payload_get() -> dict[str, object]:
    """Build one complete public workflow input document."""

    return {
        "request": {
            "brand_list": ["Brand"],
            "priority_country_code": "TR",
            "product_type_request_list": [],
            "source_type_allow_list": [],
        },
        "config": {
            "instruction": "",
            "mcp_playwright_profile_writeback_policy": {
                "mcp_playwright_profile_name_prefix": "",
                "workflow_run_status_list": ["done"],
            },
            "step_map": {
                step_key: (
                    {
                        "concurrency": 1,
                        "correction_attempt_limit": 1,
                        "instruction": "",
                        "mcp_playwright_network_proxy_name": None,
                        "mcp_playwright_profile": "source-discover",
                        "mcp_playwright_profile_source": None,
                        "model": "gpt-5.6-terra",
                        "reasoning_effort": "high",
                    }
                    if step_key == "source_discover"
                    else {
                        "correction_attempt_limit": 1,
                        "instruction": "",
                        "mcp_playwright_network_proxy_name": None,
                        "mcp_playwright_profile": None,
                        "mcp_playwright_profile_source": None,
                        "model": "gpt-5.6-terra",
                        "reasoning_effort": "high",
                    }
                )
                for step_key in ("source_discover", "coverage_decide", "canonical_select")
            },
        },
    }
