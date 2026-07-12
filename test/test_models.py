"""Model contracts for persisted downstream workflow inputs."""

from pathlib import Path

import pytest

from brand_size_chart.model import BrandSourceTypeResultStepInput, SourceDiscoveryInput


def test_configurable_step_inputs_require_only_workflow_input_identity() -> None:
    """Reject old copied workflow configuration and prompt instruction fields."""

    for model in (BrandSourceTypeResultStepInput, SourceDiscoveryInput):
        assert "workflow_input_path" in model.model_fields
        assert "workflow_input" not in model.model_fields
        assert "step_instruction_list" not in model.model_fields


def test_downstream_input_rejects_unknown_config_copy() -> None:
    """Keep downstream input closed around results and the workflow input path."""

    with pytest.raises(ValueError):
        BrandSourceTypeResultStepInput.model_validate(
            {
                "source_type_result_list": [],
                "workflow_input_path": Path("workflow/brand/input.json"),
                "workflow_config": {},
            }
        )
