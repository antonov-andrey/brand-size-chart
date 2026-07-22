"""TDD contracts for the concrete Task 5 workflow input and runtime migration."""

import importlib
import json
from pathlib import Path

import pytest
from workflow_container_runtime.step import (
    WorkflowStepCodexConcurrentConfigBase,
    WorkflowStepCodexConfigBase,
)
from workflow_container_runtime.workflow import WorkflowConfigBase, WorkflowInputBase

from brand_size_chart.app import runtime_config


def _input_payload_get() -> dict[str, object]:
    """Build one complete public workflow input payload.

    Returns:
        Complete explicit request and config payload.
    """

    return {
        "request": {
            "brand_list": ["Mavi"],
            "priority_country_code": "TR",
            "product_type_request_list": ["dress"],
            "source_type_allow_list": ["official_brand_size_guide"],
        },
        "config": {
            "instruction": "Use Turkish sources first.",
            "mcp_playwright_profile_writeback_policy": {
                "mcp_playwright_profile_name_prefix": "",
                "workflow_run_status_list": ["done"],
            },
            "step_map": {
                "canonical_select": {
                    "correction_attempt_limit": 3,
                    "instruction": "Keep one chart per group.",
                    "mcp_playwright_network_proxy_name": "owner/canonical",
                    "mcp_playwright_profile": None,
                    "mcp_playwright_profile_source": None,
                    "model": "gpt-5.6-terra",
                    "reasoning_effort": "high",
                },
                "coverage_decide": {
                    "correction_attempt_limit": 3,
                    "instruction": "Classify every requested product type.",
                    "mcp_playwright_network_proxy_name": "owner/coverage",
                    "mcp_playwright_profile": None,
                    "mcp_playwright_profile_source": None,
                    "model": "gpt-5.6-terra",
                    "reasoning_effort": "high",
                },
                "source_discover": {
                    "concurrency": 2,
                    "correction_attempt_limit": 3,
                    "instruction": "Collect verified size charts.",
                    "mcp_playwright_network_proxy_name": "owner/source",
                    "mcp_playwright_profile": "source-discover",
                    "mcp_playwright_profile_source": None,
                    "model": "gpt-5.6-terra",
                    "reasoning_effort": "high",
                },
            },
        },
    }


def test_public_input_owns_complete_request_and_closed_typed_step_map() -> None:
    """Expose one complete typed public input without prompt-derived settings."""

    model = importlib.import_module("brand_size_chart.model")

    assert hasattr(model, "WorkflowBrandSizeChartInput")
    assert hasattr(model, "WorkflowBrandSizeChartRequest")
    assert hasattr(model, "WorkflowBrandSizeChartConfig")
    assert hasattr(model, "WorkflowStepCanonicalSelectConfig")
    assert hasattr(model, "WorkflowStepCoverageDecideConfig")
    assert hasattr(model, "WorkflowStepSourceDiscoverConfig")

    workflow_input = model.WorkflowBrandSizeChartInput.model_validate_json(json.dumps(_input_payload_get()))

    assert isinstance(workflow_input, WorkflowInputBase)
    assert set(type(workflow_input.request).model_fields) == {
        "brand_list",
        "priority_country_code",
        "product_type_request_list",
        "source_type_allow_list",
    }
    assert isinstance(workflow_input.config, WorkflowConfigBase)
    assert set(type(workflow_input.config.step_map).model_fields) == {
        "canonical_select",
        "coverage_decide",
        "source_discover",
    }
    assert isinstance(workflow_input.config.step_map.source_discover, WorkflowStepCodexConcurrentConfigBase)
    assert isinstance(workflow_input.config.step_map.coverage_decide, WorkflowStepCodexConfigBase)
    assert isinstance(workflow_input.config.step_map.canonical_select, WorkflowStepCodexConfigBase)
    with pytest.raises(ValueError):
        model.WorkflowBrandSizeChartInput.model_validate_json(
            json.dumps(
                {
                    **_input_payload_get(),
                    "config": {
                        **_input_payload_get()["config"],
                        "step_map": {**_input_payload_get()["config"]["step_map"], "unknown": {}},
                    },
                }
            )
        )


def test_configurable_step_inputs_keep_only_stable_domain_data_and_workflow_input_path() -> None:
    """Persist workflow input identity rather than copied config or instructions."""

    model = importlib.import_module("brand_size_chart.model")

    assert hasattr(model, "SourceDiscoveryInput")
    assert hasattr(model, "BrandSourceTypeResultStepInput")
    assert "workflow_input_path" in model.SourceDiscoveryInput.model_fields
    assert "workflow_input_path" in model.BrandSourceTypeResultStepInput.model_fields
    for step_input_model in (model.SourceDiscoveryInput, model.BrandSourceTypeResultStepInput):
        assert "workflow_input" not in step_input_model.model_fields
        assert "step_instruction_list" not in step_input_model.model_fields
        assert "config" not in step_input_model.model_fields


def test_runtime_uses_platform_input_path_without_a_cli_translation() -> None:
    """Keep the complete input location owned by the standard platform environment."""

    assert not hasattr(runtime_config, "args_parse")
