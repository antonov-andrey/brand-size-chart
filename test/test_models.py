"""Persisted downstream workflow-input behavior tests."""

import json
from pathlib import Path

import pytest
from workflow_container_contract import WorkflowInputSchema
from workflow_container_runtime.workflow import WorkflowBrowserConfigBase

from brand_size_chart.model import (
    BrandSourceTypeResultStepInput,
    SourceDiscoveryAcceptedTable,
    SourceDiscoveryResult,
    SourceDiscoveryTable,
    SourceTypeResult,
    WorkflowBrandSizeChartConfig,
    WorkflowBrandSizeChartInput,
    WorkflowStepCanonicalSelectConfig,
    WorkflowStepCoverageDecideConfig,
    WorkflowStepSourceDiscoverConfig,
)


def test_input_schema_is_generated_from_pydantic_owner() -> None:
    """Keep the checked-in public schema identical to the concrete input model schema."""

    schema_path = Path("input.schema.json")

    assert json.loads(schema_path.read_text(encoding="utf-8")) == WorkflowBrandSizeChartInput.model_json_schema()
    WorkflowInputSchema.from_path(schema_path)


def test_workflow_config_uses_explicit_browser_profile_contract() -> None:
    """Require the workflow policy and both nullable profile fields on every Codex step."""

    assert issubclass(WorkflowBrandSizeChartConfig, WorkflowBrowserConfigBase)
    for config_model in (
        WorkflowStepCanonicalSelectConfig,
        WorkflowStepCoverageDecideConfig,
        WorkflowStepSourceDiscoverConfig,
    ):
        assert {"mcp_playwright_profile", "mcp_playwright_profile_source"} <= set(config_model.model_fields)
        assert config_model.model_fields["mcp_playwright_profile"].is_required()
        assert config_model.model_fields["mcp_playwright_profile_source"].is_required()


def test_downstream_steps_accept_complete_source_results_and_reject_copied_config() -> None:
    """Persist only complete source result handoffs plus the public workflow input identity."""

    source_type_result = _source_type_result_get()
    persisted_payload = BrandSourceTypeResultStepInput(
        source_type_result_list=[source_type_result],
        workflow_input_path=Path("workflow/run/input.json"),
    ).model_dump(mode="json")

    restored_input = BrandSourceTypeResultStepInput.model_validate_json(json.dumps(persisted_payload))
    assert restored_input.source_type_result_list == [source_type_result]
    assert restored_input.workflow_input_path == Path("workflow/run/input.json")
    persisted_payload["workflow_config"] = {}
    with pytest.raises(ValueError):
        BrandSourceTypeResultStepInput.model_validate_json(json.dumps(persisted_payload))


def test_accepted_table_remains_transient_and_cannot_enter_persisted_downstream_input() -> None:
    """Reject a reader-only accepted table when it is injected into persisted handoff JSON."""

    accepted_table = SourceDiscoveryAcceptedTable(
        chart_path="workflow/run/source/source_discover/chart/women_dress__tr.json",
        source_priority=600,
        source_table=SourceDiscoveryTable(
            evidence_path_list=["workflow/run/source/evidence/table.json"],
            market_scope_key="tr",
            reason="Official chart.",
            size_group_key="women_dress",
            source_title="Women dress chart",
            source_url="https://brand.example/size",
            state="accepted",
        ),
        source_type="official_brand_size_guide",
    )
    payload = {
        "accepted_table_list": [accepted_table.model_dump(mode="json")],
        "source_type_result_list": [_source_type_result_get().model_dump(mode="json")],
        "workflow_input_path": "workflow/run/input.json",
    }

    with pytest.raises(ValueError):
        BrandSourceTypeResultStepInput.model_validate(payload)


def test_downstream_input_rejects_duplicate_source_type_and_database_handoffs() -> None:
    """Reject duplicate source and SQLite identities before downstream read behavior starts."""

    source_type_result = _source_type_result_get()
    duplicate_source_payload = source_type_result.model_dump(mode="json")
    duplicate_database_payload = source_type_result.model_dump(mode="json")
    duplicate_database_payload["source_type"] = "official_seller_size_guide"
    for source_type_result_payload_list in (
        [source_type_result.model_dump(mode="json"), duplicate_source_payload],
        [source_type_result.model_dump(mode="json"), duplicate_database_payload],
    ):
        with pytest.raises(ValueError):
            BrandSourceTypeResultStepInput.model_validate(
                {
                    "source_type_result_list": source_type_result_payload_list,
                    "workflow_input_path": "workflow/run/input.json",
                }
            )


def _source_type_result_get() -> SourceTypeResult:
    """Build one successful complete source result with a declared SQLite handoff."""

    return SourceTypeResult(
        error_list=[],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[],
            outcome="table_available",
            source_discovery_database_path="workflow/run/source/source_discover/state.sqlite3",
        ),
        source_type="official_brand_size_guide",
        status="success",
        warning_list=[],
    )
