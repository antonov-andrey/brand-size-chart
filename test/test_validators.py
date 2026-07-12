"""Validation behavior for complete workflow input and request values."""

from copy import deepcopy
from pathlib import Path

import pytest
from workflow_container_contract import WorkflowContractError, WorkflowInputSchema

from brand_size_chart.model import WorkflowBrandSizeChartInput, WorkflowBrandSizeChartRequest


def test_priority_country_code_has_identical_schema_and_model_contract() -> None:
    """Accept uppercase ISO alpha-2 input unchanged and reject normalization candidates at both boundaries."""

    schema = WorkflowInputSchema.from_path(Path("input.schema.json"))
    valid_payload = _input_payload_get()

    assert schema.input_validate(valid_payload) == valid_payload
    assert WorkflowBrandSizeChartInput.model_validate(valid_payload).request.priority_country_code == "TR"
    for invalid_value in ("tr", " TR", "TR "):
        invalid_payload = deepcopy(valid_payload)
        invalid_payload["request"]["priority_country_code"] = invalid_value
        with pytest.raises(WorkflowContractError):
            schema.input_validate(invalid_payload)
        with pytest.raises(ValueError):
            WorkflowBrandSizeChartInput.model_validate(invalid_payload)


def test_request_rejects_duplicate_source_types() -> None:
    """Keep source type allow-list identity unique at the complete request boundary."""

    with pytest.raises(ValueError, match="unique"):
        WorkflowBrandSizeChartRequest(
            brand_list_text="Brand",
            priority_country_code="TR",
            product_type_request_list=[],
            source_type_allow_list=["official_brand_size_guide", "official_brand_size_guide"],
        )


def _input_payload_get() -> dict[str, object]:
    """Build one complete public workflow input document."""

    return {
        "request": {
            "brand_list_text": "Brand\\n",
            "priority_country_code": "TR",
            "product_type_request_list": [],
            "source_type_allow_list": [],
        },
        "config": {
            "instruction": "",
            "step_map": {
                step_key: (
                    {
                        "concurrency": 1,
                        "correction_attempt_limit": 1,
                        "instruction": "",
                        "model": "gpt-5.6-terra",
                        "reasoning_effort": "high",
                    }
                    if step_key == "source_discover"
                    else {
                        "correction_attempt_limit": 1,
                        "instruction": "",
                        "model": "gpt-5.6-terra",
                        "reasoning_effort": "high",
                    }
                )
                for step_key in ("source_discover", "coverage_decide", "canonical_select")
            },
        },
    }
