"""Tests for Task 4 persisted downstream model contracts."""

from pydantic import ValidationError

from brand_size_chart.model import (
    BrandSourceTypeResultStepInput,
    BrandWorkflowInput,
    CanonicalSelection,
    SourceDiscoveryAcceptedTable,
    SourceDiscoveryResult,
    SourceDiscoveryTable,
    SourceTypeResult,
)


def _source_type_result_get() -> SourceTypeResult:
    """Build one complete source result.

    Returns:
        Successful source result with a declared SQLite handle.
    """

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


def test_downstream_steps_share_exact_complete_source_result_input() -> None:
    """Persist source results, never copied table or candidate carriers."""

    step_input = BrandSourceTypeResultStepInput(
        source_type_result_list=[_source_type_result_get()],
        workflow_input=BrandWorkflowInput.model_validate(
            {
                "brand_input": {
                    "parsed_brand_key": "brand",
                    "parsed_brand_name": "Brand",
                    "raw_brand_name": "Brand",
                    "source_line_number": 1,
                },
                "prompt_scope": {},
            }
        ),
    )

    assert set(BrandSourceTypeResultStepInput.model_fields) == {
        "source_type_result_list",
        "step_instruction_list",
        "workflow_input",
    }
    with_validation_error = {
        **step_input.model_dump(),
        "copied_table_list": [],
    }
    try:
        BrandSourceTypeResultStepInput.model_validate(with_validation_error)
    except ValidationError:
        pass
    else:
        raise AssertionError("copied table fields must be rejected")


def test_accepted_table_is_transient_row_with_only_query_fields() -> None:
    """Keep accepted database rows outside persisted downstream inputs."""

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

    assert set(SourceDiscoveryAcceptedTable.model_fields) == {
        "chart_path",
        "source_priority",
        "source_table",
        "source_type",
    }
    assert (
        CanonicalSelection(selected_chart_path=accepted_table.chart_path).selected_chart_path
        == accepted_table.chart_path
    )


def test_downstream_input_rejects_duplicate_source_type_and_database_handoffs() -> None:
    """Reject duplicate source-result identities before downstream lookup construction."""

    workflow_input = BrandWorkflowInput.model_validate(
        {
            "brand_input": {
                "parsed_brand_key": "brand",
                "parsed_brand_name": "Brand",
                "raw_brand_name": "Brand",
                "source_line_number": 1,
            },
            "prompt_scope": {},
        }
    )
    source_type_result = _source_type_result_get()
    duplicate_source_type_result = source_type_result.model_copy(
        update={"source_discovery_result": source_type_result.source_discovery_result.model_copy()}
    )
    duplicate_database_result = source_type_result.model_copy(update={"source_type": "official_seller_size_guide"})

    for result_list in (
        [source_type_result, duplicate_source_type_result],
        [source_type_result, duplicate_database_result],
    ):
        with_validation_error = {
            "source_type_result_list": [result.model_dump() for result in result_list],
            "workflow_input": workflow_input.model_dump(),
        }
        try:
            BrandSourceTypeResultStepInput.model_validate(with_validation_error)
        except ValidationError:
            continue
        raise AssertionError("duplicate downstream source-result identities must be rejected")
