"""Tests for cross-project workflow contract metadata."""

import ast
from contextlib import nullcontext
import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
import yaml

from brand_size_chart import workflow
from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import ArtifactWriteTarget
from brand_size_chart.model import BrandInput
from brand_size_chart.model import BrandSizeChart
from brand_size_chart.model import BrandSizeChartMeasurement
from brand_size_chart.model import BrandSizeChartRow
from brand_size_chart.model import CanonicalSelection
from brand_size_chart.model import CanonicalSelectionCandidate
from brand_size_chart.model import CanonicalSelectionInput
from brand_size_chart.model import CanonicalSelectionResult
from brand_size_chart.model import CoverageDecisionProductTypeGap
from brand_size_chart.model import CoverageDecisionInput
from brand_size_chart.model import CoverageDecisionResult
from brand_size_chart.model import CoveredProductType
from brand_size_chart.model import PromptScope
from brand_size_chart.model import PromptStageInstruction
from brand_size_chart.model import SourceDiscovery
from brand_size_chart.model import SourceDiscoveryInput
from brand_size_chart.model import SourceDiscoveryResult
from brand_size_chart.model import SourceSurfaceInventory
from brand_size_chart.model import SourceTypeResult
from brand_size_chart.model import TableExtractionArtifact
from brand_size_chart.model import TableExtractionDelta
from brand_size_chart.model import TableExtractionDeltaBatchResult
from brand_size_chart.model import TableExtractionExecplanItem
from brand_size_chart.model import TableExtractionInput
from brand_size_chart.model import TableExtractionResult
from brand_size_chart.model import WorkflowRunPromptApplyInput
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.source import table_extraction_applicability_status_get
from brand_size_chart.stage.canonical_selection import CanonicalSelectionStep
from brand_size_chart.stage.table_extraction import TableExtractionStep
from brand_size_chart.stage.workflow_run_prompt_apply import WorkflowRunPromptApplyStep
from workflow_container_contract.testing import workflow_contract_file_validate
from workflow_container_runtime.stage import BrowserActionResult
from workflow_container_runtime.stage import (
    StageVerificationResult,
    stage_result_path_get,
)

ACTION_STAGE_KEY_SET = {
    "canonical_select",
    "coverage_decide",
    "source_discover",
    "table_extract",
    "workflow_run_prompt_apply",
}
FORBIDDEN_STAGE_KEY_SET = {
    "canonical_selection",
    "coverage_decision",
    "source_discovery",
    "table_extraction",
}
PROJECT_TEMPLATE_DIR = Path("brand_size_chart/prompt/template")


def _workflow_package_source_text_get() -> str:
    """Return the combined workflow package source text for source-shape contract tests.

    Returns:
        Concatenated workflow package source.
    """
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(Path("brand_size_chart/workflow").glob("*.py"))
    )


def _table_extraction_delta_batch_result_get(
    table_extraction_artifact_list: list[TableExtractionArtifact],
) -> TableExtractionDeltaBatchResult:
    """Return Codex-owned table extraction delta result.

    Args:
        table_extraction_artifact_list: Fake final table extraction artifacts.

    Returns:
        Codex-owned table extraction delta result.
    """

    return TableExtractionDeltaBatchResult(
        table_extraction_delta_list=[
            TableExtractionDelta(
                applicability_description=table_extraction_artifact.applicability_description,
                evidence_path_list=table_extraction_artifact.evidence_path_list,
            )
            for table_extraction_artifact in table_extraction_artifact_list
        ],
    )


def _table_extraction_result_get(
    table_extraction_artifact_list: list[TableExtractionArtifact],
) -> TableExtractionResult:
    """Return public table extraction result.

    Args:
        table_extraction_artifact_list: Final table extraction artifacts.

    Returns:
        Public table extraction result.
    """

    return TableExtractionResult(table_extraction_list=table_extraction_artifact_list)


def _table_extract_stage_dir_prepare(
    tmp_path: Path, table_extraction_artifact_list: list[TableExtractionArtifact], *, source_type: str
) -> Path:
    """Create table-extract stage directory for validator tests.

    Args:
        tmp_path: Test temporary result directory.
        table_extraction_artifact_list: Final table extraction artifacts represented by chart files.
        source_type: Batch source type.

    Returns:
        Prepared table-extract stage directory.
    """

    stage_dir = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / source_type / "table_extract"
    )
    stage_dir.mkdir(parents=True, exist_ok=True)
    _ = table_extraction_artifact_list
    return stage_dir


def _source_discovery_stage_input_get(
    *,
    priority_country_code: str = "TR",
    product_type_request_list: list[str] | None = None,
    source_type: str = "official_brand_size_guide",
) -> SourceDiscoveryInput:
    """Return source-discovery prompt context for validator tests.

    Args:
        priority_country_code: Priority market code.
        product_type_request_list: Requested product types.
        source_type: Source type key.

    Returns:
        Source-discovery prompt context.
    """

    return SourceDiscoveryInput(
        brand_name="Defacto",
        evidence_write_target=ArtifactWriteTarget(
            artifact_path="brand_size_chart_audit/brand/defacto/source_type/" f"{source_type}/source_discover/evidence",
            filesystem_path="/tmp/evidence",
        ),
        priority_country_code=priority_country_code,
        requested_product_type_list=product_type_request_list or [],
        source_type=source_type,
        source_type_instruction="Find source surfaces.",
    )


def _source_surface_table_payload_get(
    *,
    country_code_list: list[str],
    evidence_path_list: list[str],
    reason: str,
    size_group_key: str,
    source_title: str,
    source_url: str,
    state: str,
) -> dict[str, object]:
    """Return one SourceSurfaceTable payload with nested source discovery identity.

    Args:
        country_code_list: Source table market country code list.
        evidence_path_list: Evidence artifact references for the source table.
        reason: Table inventory row reason.
        size_group_key: Stable source table key.
        source_title: Browser-visible table title.
        source_url: Source URL.
        state: Source surface table state.

    Returns:
        SourceSurfaceTable JSON payload.
    """

    return {
        "reason": reason,
        "source_discovery": {
            "country_code_list": country_code_list,
            "evidence_path_list": evidence_path_list,
            "size_group_key": size_group_key,
            "source_title": source_title,
            "source_url": source_url,
        },
        "state": state,
    }


def _source_discovery_result_get(stage_dir: Path) -> SourceDiscoveryResult:
    """Return public source-discovery result from test inventory state.

    Args:
        stage_dir: Source-discovery stage directory.

    Returns:
        Public source-discovery result.
    """

    inventory = SourceSurfaceInventory.model_validate_json((stage_dir / "state.json").read_text(encoding="utf-8"))
    source_discovery_list = [
        source_surface_table.source_discovery
        for source_surface_table in inventory.table_list
        if source_surface_table.state == "accepted"
    ]
    return SourceDiscoveryResult(
        source_discovery_list=source_discovery_list,
        warning_list=[] if source_discovery_list else inventory.no_table_reason_list_get(),
    )


def _table_extraction_stage_input_get(
    *, source_discovery_list: list[SourceDiscovery], stage_dir: Path, tmp_path: Path
) -> TableExtractionInput:
    """Return table-extraction prompt context for validator tests.

    Args:
        source_discovery_list: Source discoveries represented by the execplan.
        stage_dir: Table-extraction stage directory.
        tmp_path: Test temporary result directory.

    Returns:
        Table-extraction prompt context.
    """

    return TableExtractionInput(
        brand_name="Defacto",
        execplan_item_list=[
            TableExtractionExecplanItem(
                chart_filesystem_path=(stage_dir / "chart" / f"{source_discovery.size_group_key}.json").as_posix(),
                evidence_write_target=ArtifactWriteTarget(
                    artifact_path=(stage_dir / "evidence" / source_discovery.size_group_key)
                    .relative_to(tmp_path)
                    .as_posix(),
                    filesystem_path=(stage_dir / "evidence" / source_discovery.size_group_key).as_posix(),
                ),
                source_discovery=source_discovery,
            )
            for source_discovery in source_discovery_list
        ],
    )


def _canonical_selection_stage_input_get(
    table_extraction_list: list[TableExtractionArtifact],
    *,
    source_priority_by_key_map: dict[str, int] | None = None,
) -> CanonicalSelectionInput:
    """Return canonical-selection prompt context for validator tests.

    Args:
        table_extraction_list: Verified table artifacts.
        source_priority_by_key_map: Optional test priority override.

    Returns:
        Canonical-selection prompt context.
    """

    priority_by_key_map = source_priority_by_key_map or SOURCE_TYPE_REGISTRY.source_type_priority_by_key_map
    return CanonicalSelectionInput(
        brand_name="Defacto",
        canonical_selection_candidate_list=[
            CanonicalSelectionCandidate(
                applicability_status=table_extraction_applicability_status_get(
                    table_extraction,
                    priority_country_code="TR",
                ),
                source_priority=priority_by_key_map[table_extraction.source_type],
                table_extraction_artifact=table_extraction,
            )
            for table_extraction in table_extraction_list
        ],
    )


def _table_extraction_artifact_get(
    *,
    chart: BrandSizeChart,
    size_group_key: str,
    source_title: str,
    tmp_path: Path,
    applicability_description: str = "",
    country_code_list: list[str] | None = None,
    evidence_path_list: list[str] | None = None,
    source_type: str = "official_brand_size_guide",
    source_url: str = "https://www.defacto.com.tr/statik/beden-rehberi",
) -> TableExtractionArtifact:
    """Write one chart artifact and return its cross-stage handle.

    Args:
        chart: Chart payload to persist.
        size_group_key: Table size-group key.
        source_title: Browser-visible source title.
        tmp_path: Test temporary result directory.
        applicability_description: Applicability explanation.
        country_code_list: Source market country code list.
        evidence_path_list: Evidence artifact paths relative to tmp_path.
        source_type: Source type key.
        source_url: Source URL.

    Returns:
        Table extraction artifact handle.
    """

    chart_path = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / source_type
        / "table_extract"
        / "chart"
        / f"{size_group_key}.json"
    )
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart_path.write_text(chart.model_dump_json(indent=2), encoding="utf-8")
    return TableExtractionArtifact(
        applicability_description=applicability_description,
        chart_path=chart_path.relative_to(tmp_path).as_posix(),
        country_code_list=country_code_list or ["TR"],
        evidence_path_list=evidence_path_list or [],
        size_group_key=size_group_key,
        source_title=source_title,
        source_type=source_type,
        source_url=source_url,
    )


def _json_stage_value_error_list_get(path: Path, payload: object) -> list[str]:
    """Return generated-schema stage enum or const values that still use noun stage keys.

    Args:
        path: JSON schema file path.
        payload: Parsed JSON payload or nested value.

    Returns:
        Schema stage value error list.
    """

    if isinstance(payload, dict):
        error_list: list[str] = []
        for key, value in payload.items():
            if key in {"const", "enum"}:
                value_list = value if isinstance(value, list) else [value]
                for item in value_list:
                    if item in FORBIDDEN_STAGE_KEY_SET:
                        error_list.append(f"{path}: generated schema stage value {item!r}")
                continue
            error_list.extend(_json_stage_value_error_list_get(path, value))
        return error_list
    if isinstance(payload, list):
        error_list = []
        for item in payload:
            error_list.extend(_json_stage_value_error_list_get(path, item))
        return error_list
    return []


def _python_stage_literal_error_list_get(path: Path) -> list[str]:
    """Return live runtime string constants that still use noun stage keys.

    Args:
        path: Python file path.

    Returns:
        Stage literal error list.
    """

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    error_list = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value in FORBIDDEN_STAGE_KEY_SET:
            error_list.append(f"{path}:{node.lineno}: forbidden stage key {node.value!r}")
        for stage_key in FORBIDDEN_STAGE_KEY_SET:
            if f"/{stage_key}" in node.value or f"{stage_key}/" in node.value:
                error_list.append(f"{path}:{node.lineno}: forbidden stage path segment {stage_key!r}")
    return error_list


def test_stage_names_use_action_verbs() -> None:
    """Keep live stage keys, prompt template names, and generated schema stage values on action verbs."""
    from brand_size_chart.stage import base as stage_base
    from brand_size_chart.validator import prompt_scope

    layout = ArtifactLayout(Path("/tmp/result"))
    brand_input = BrandInput(
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        raw_brand_name="Defacto",
        source_line_number=1,
    )
    scanned_python_path_list = [
        *sorted(Path("brand_size_chart/artifact").glob("*.py")),
        *sorted(Path("brand_size_chart/stage").glob("*.py")),
        *sorted(Path("brand_size_chart/workflow").glob("*.py")),
        Path("brand_size_chart/validator/prompt_scope.py"),
    ]
    fixture_root = Path("test/fixtures")
    if fixture_root.exists():
        scanned_python_path_list.extend(sorted(fixture_root.rglob("*.py")))

    error_list = [
        f"prompt scope still accepts {stage_key!r}"
        for stage_key in FORBIDDEN_STAGE_KEY_SET
        if stage_key in prompt_scope.STAGE_KEY_SET
    ]
    error_list.extend(
        f"prompt template file still uses {stage_key!r}: {path}"
        for path in sorted(Path("brand_size_chart/prompt/template").glob("*.md.j2"))
        for stage_key in FORBIDDEN_STAGE_KEY_SET
        if stage_key in path.name
    )
    for path in scanned_python_path_list:
        error_list.extend(_python_stage_literal_error_list_get(path))

    assert stage_base.STAGE_KEY_SET == ACTION_STAGE_KEY_SET
    assert hasattr(stage_base, "PROMPT_TEMPLATE_NAME_BY_STAGE_KEY_MAP") is False
    assert hasattr(stage_base, "VERIFY_TEMPLATE_NAME_BY_STAGE_KEY_MAP") is False
    assert prompt_scope.STAGE_KEY_SET == ACTION_STAGE_KEY_SET
    assert hasattr(layout, "source_discovery_dir") is False
    assert hasattr(layout, "source_discovery_evidence_dir") is False
    assert hasattr(layout, "coverage_decision_dir") is False
    assert hasattr(layout, "canonical_selection_dir") is False
    assert hasattr(layout, "brand_coverage_decide_dir") is False
    assert (
        layout.source_discover_dir(brand_input, "official_brand_size_guide").as_posix()
        == "/tmp/result/brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/source_discover"
    )
    assert (
        layout.source_discover_evidence_dir(brand_input, "official_brand_size_guide").as_posix()
        == "/tmp/result/.playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/"
        "official_brand_size_guide/source_discover/evidence"
    )
    assert (
        layout.coverage_decide_dir(brand_input, "official_brand_size_guide").as_posix()
        == "/tmp/result/brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/coverage_decide"
    )
    assert (
        layout.canonical_select_dir(brand_input).as_posix()
        == "/tmp/result/brand_size_chart_audit/brand/defacto/canonical_select"
    )
    assert "coverage_decision_write_step" not in workflow.__all__
    assert "source_discovery_write_step" not in workflow.__all__
    assert "coverage_decide_write_step" not in workflow.__all__
    assert "source_discover_write_step" not in workflow.__all__
    assert error_list == []


def test_model_is_package_not_monolithic_module() -> None:
    """Replace the broad model module with focused model package modules."""
    assert Path("brand_size_chart/model.py").exists() is False
    assert Path("brand_size_chart/model/__init__.py").exists()
    assert not Path("brand_size_chart/model/schema_registry.py").exists()
    assert not Path("brand_size_chart/schema").exists()


def test_workflow_is_package_not_monolithic_module() -> None:
    """Replace the broad workflow module with workflow owner package modules."""
    assert Path("brand_size_chart/workflow.py").exists() is False
    assert Path("brand_size_chart/workflow/__init__.py").exists()
    assert Path("brand_size_chart/workflow/root.py").exists()
    assert set(workflow.__all__) == {
        "BRAND_SIZE_CHART_BRAND_WORKFLOW",
        "BRAND_SIZE_CHART_RUN_WORKFLOW",
        "BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW",
        "BrandSizeChartBrandWorkflow",
        "BrandSizeChartRunWorkflow",
        "BrandSizeChartSourceTypeWorkflow",
        "run_failure_result_write",
    }


def test_workflow_has_no_per_table_child_workflow() -> None:
    """Run table extraction as one source-type batch step instead of one child workflow per table."""
    workflow_source_text = _workflow_package_source_text_get()

    assert Path("brand_size_chart/workflow/table.py").exists() is False
    assert "BrandSizeChartTableWorkflow" not in workflow.__all__
    assert "BRAND_SIZE_CHART_TABLE_WORKFLOW" not in workflow.__all__
    assert "brand_size_chart_table" not in workflow.__all__
    assert "table_stage_write_step" not in workflow.__all__
    assert "table_extract_write_step" not in workflow.__all__
    assert "brand_size_chart_table" not in workflow_source_text


def test_dbos_codex_workflow_dependency_owner_is_shared() -> None:
    """Share Codex workflow dependencies through one domain workflow owner."""
    from brand_size_chart.workflow.codex import BrandSizeChartCodexWorkflow

    assert Path("brand_size_chart/workflow/base.py").exists() is False
    assert issubclass(workflow.BrandSizeChartRunWorkflow, BrandSizeChartCodexWorkflow)
    assert issubclass(workflow.BrandSizeChartBrandWorkflow, BrandSizeChartCodexWorkflow)
    assert issubclass(workflow.BrandSizeChartSourceTypeWorkflow, BrandSizeChartCodexWorkflow)
    assert isinstance(workflow.BRAND_SIZE_CHART_RUN_WORKFLOW, BrandSizeChartCodexWorkflow)
    assert isinstance(workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW, BrandSizeChartCodexWorkflow)
    assert isinstance(workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW, BrandSizeChartCodexWorkflow)
    assert "BrandSizeChartCodexWorkflow" not in workflow.__all__


def test_table_extract_stage_has_no_legacy_prompt_alias() -> None:
    """Reject old table-extraction prompt aliases after batch stage migration."""
    from brand_size_chart.stage import base as stage_base

    assert "table_extraction" not in stage_base.STAGE_KEY_SET


def test_dbos_workflow_classes_are_class_owned() -> None:
    """Ensure DBOS workflows are owned by class instance methods."""
    method_expectation_list = [
        (workflow.BRAND_SIZE_CHART_RUN_WORKFLOW.run, "brand_size_chart_run", "BrandSizeChartRunWorkflow"),
        (
            workflow.BRAND_SIZE_CHART_RUN_WORKFLOW.prompt_scope_write_step,
            "prompt_scope_write_step",
            "BrandSizeChartRunWorkflow",
        ),
        (
            workflow.BRAND_SIZE_CHART_RUN_WORKFLOW.result_write_step,
            "run_result_write_step",
            "BrandSizeChartRunWorkflow",
        ),
        (workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.run, "brand_size_chart_brand", "BrandSizeChartBrandWorkflow"),
        (
            workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.selection_write_step,
            "brand_selection_write_step",
            "BrandSizeChartBrandWorkflow",
        ),
        (
            workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.coverage_decide_write_step,
            "coverage_decide_write_step",
            "BrandSizeChartBrandWorkflow",
        ),
        (
            workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.run,
            "brand_size_chart_source_type",
            "BrandSizeChartSourceTypeWorkflow",
        ),
        (
            workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.source_discover_write_step,
            "source_discover_write_step",
            "BrandSizeChartSourceTypeWorkflow",
        ),
        (
            workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.result_write_step,
            "source_type_result_write_step",
            "BrandSizeChartSourceTypeWorkflow",
        ),
        (
            workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.table_extract_write_step,
            "table_extract_write_step",
            "BrandSizeChartSourceTypeWorkflow",
        ),
    ]

    for method, function_name, class_name in method_expectation_list:
        assert method.__self__.__class__.__name__ == class_name
        assert method.__self__.config_name == "default"
        assert getattr(method, "dbos_function_name") == function_name
        assert method.dbos_func_decorator_info.func_type.name == "Instance"
        assert method.dbos_func_decorator_info.class_info.registered_name == class_name


def test_local_codex_runtime_owner_is_absent() -> None:
    """Keep generic Codex runtime out of the domain project."""

    assert not Path("brand_size_chart/codex_stage.py").exists()
    assert not Path("brand_size_chart/codex").exists()


def test_refactor_import_files_are_absent() -> None:
    """Keep refactor-only import files out of the package."""

    assert not Path("brand_size_chart/entrypoint.py").exists()
    assert not Path("brand_size_chart/source_extractor.py").exists()
    assert not Path("brand_size_chart/source_type.py").exists()
    assert not Path("brand_size_chart/validator/artifact.py").exists()
    assert not Path("brand_size_chart/workflow/base.py").exists()


def test_identifier_component_validator_has_one_owner() -> None:
    """Keep identifier-component validation in one model base owner."""

    model_source_text_by_path = {
        path: path.read_text(encoding="utf-8") for path in sorted(Path("brand_size_chart/model").glob("*.py"))
    }
    owner_path_list = [
        path
        for path, source_text in model_source_text_by_path.items()
        if "def identifier_component_validate" in source_text
    ]

    assert owner_path_list == [Path("brand_size_chart/model/base.py")]


def test_source_type_registry_has_no_public_map_aliases() -> None:
    """Expose source type registry through the registry object only."""

    source_package_text = Path("brand_size_chart/source/__init__.py").read_text(encoding="utf-8")
    registry_text = Path("brand_size_chart/source/source_type_registry.py").read_text(encoding="utf-8")

    assert "SOURCE_TYPE_PRIORITY_BY_KEY_MAP" not in source_package_text
    assert "SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP" not in source_package_text
    assert "PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET" not in source_package_text
    assert "SOURCE_TYPE_PRIORITY_BY_KEY_MAP =" not in registry_text
    assert "SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP =" not in registry_text
    assert "PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET =" not in registry_text


def test_source_type_registry_is_immutable_through_public_import() -> None:
    """Prevent public imports from mutating source type registry state."""
    source_type = "official_brand_size_guide"
    original_instruction = SOURCE_TYPE_REGISTRY.source_type_discovery_instruction_get(source_type)
    original_priority = SOURCE_TYPE_REGISTRY.source_type_priority_get(source_type)

    with pytest.raises(TypeError):
        SOURCE_TYPE_REGISTRY.source_type_priority_by_key_map[source_type] = 1
    with pytest.raises(TypeError):
        SOURCE_TYPE_REGISTRY.source_type_discovery_instruction_by_key_map[source_type] = "mutated"
    with pytest.raises(AttributeError):
        SOURCE_TYPE_REGISTRY.product_type_required_source_type_set.add("mutated_source_type")

    assert SOURCE_TYPE_REGISTRY.source_type_priority_get(source_type) == original_priority
    assert SOURCE_TYPE_REGISTRY.source_type_discovery_instruction_get(source_type) == original_instruction
    assert "mutated_source_type" not in SOURCE_TYPE_REGISTRY.product_type_required_source_type_set


def test_artifact_layout_owns_current_paths(tmp_path: Path) -> None:
    """Centralize deterministic artifact paths in ArtifactLayout."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.model import BrandInput

    layout = ArtifactLayout(result_dir=tmp_path)
    brand_input = BrandInput(
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        raw_brand_name="Defacto",
        source_line_number=1,
    )

    assert layout.brand_output_dir(brand_input).relative_to(tmp_path).as_posix() == "brand_size_chart/brand/defacto"
    assert (
        layout.brand_audit_dir(brand_input).relative_to(tmp_path).as_posix() == "brand_size_chart_audit/brand/defacto"
    )
    assert hasattr(layout, "table_extraction_dir") is False
    assert hasattr(layout, "table_extraction_evidence_dir") is False
    assert hasattr(layout, "table_extraction_result_path") is False


def test_table_extract_layout_uses_one_source_type_batch_dir(tmp_path: Path) -> None:
    """Store batch table-extract output under one source-type stage directory."""
    layout = ArtifactLayout(result_dir=tmp_path)
    brand_input = BrandInput(
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        raw_brand_name="Defacto",
        source_line_number=1,
    )

    stage_dir = layout.table_extract_dir(brand_input, "official_brand_size_guide")

    assert (
        stage_dir.relative_to(tmp_path).as_posix()
        == "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract"
    )
    assert (
        layout.table_extract_chart_path(brand_input, "official_brand_size_guide", "women_upper")
        .relative_to(tmp_path)
        .as_posix()
        == "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract/chart/women_upper.json"
    )
    assert (
        stage_result_path_get(layout.table_extract_dir(brand_input, "official_brand_size_guide"))
        .relative_to(tmp_path)
        .as_posix()
        == "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract/result.json"
    )
    assert layout.table_extract_evidence_dir(brand_input, "official_brand_size_guide", "women_upper").relative_to(
        tmp_path
    ).as_posix() == (
        ".playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/"
        "official_brand_size_guide/table_extract/evidence/women_upper"
    )


def test_artifact_reference_validator_rejects_existing_traversal_evidence_path(tmp_path: Path) -> None:
    """Reject existing evidence references that traverse outside the result directory."""
    from brand_size_chart.artifact.reference_validator import ArtifactReferenceValidator

    result_dir = tmp_path / "result"
    result_dir.mkdir()
    (tmp_path / "outside.json").write_text("{}\n", encoding="utf-8")

    try:
        ArtifactReferenceValidator(result_dir).evidence_path_list_validate(
            evidence_path_list=["../outside.json"],
            stage_key="test",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "outside result_dir" in message


def test_artifact_reference_validator_rejects_existing_absolute_artifact_path(tmp_path: Path) -> None:
    """Reject existing absolute artifact references outside the result directory."""
    from brand_size_chart.artifact.reference_validator import ArtifactReferenceValidator

    result_dir = tmp_path / "result"
    result_dir.mkdir()
    outside_path = tmp_path / "outside.json"
    outside_path.write_text("{}\n", encoding="utf-8")

    try:
        ArtifactReferenceValidator(result_dir).path_list_validate(
            path_list=[str(outside_path)],
            stage_key="test",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "outside result_dir" in message


def test_artifact_reference_validator_rejects_whitespace_artifact_path(tmp_path: Path) -> None:
    """Reject artifact references with leading or trailing whitespace."""
    from brand_size_chart.artifact.reference_validator import ArtifactReferenceValidator

    result_dir = tmp_path / "result"
    result_dir.mkdir()

    try:
        ArtifactReferenceValidator(result_dir).path_list_validate(
            path_list=[" artifact.json"],
            stage_key="test",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "leading or trailing whitespace" in message


def test_stage_validators_live_under_validator_package() -> None:
    """Keep mechanical validation outside workflow orchestration."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator
    from brand_size_chart.validator.coverage_decision import CoverageDecisionValidator
    from brand_size_chart.validator.prompt_scope import PromptScopeValidator
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator
    from brand_size_chart.validator.table_extraction import TableExtractionValidator

    assert PromptScopeValidator.__name__ == "PromptScopeValidator"
    assert SourceDiscoveryValidator.__name__ == "SourceDiscoveryValidator"
    assert TableExtractionValidator.__name__ == "TableExtractionValidator"
    assert CoverageDecisionValidator.__name__ == "CoverageDecisionValidator"
    assert CanonicalSelectionValidator.__name__ == "CanonicalSelectionValidator"


def test_table_extraction_stage_builds_source_identity_from_discovery(tmp_path: Path) -> None:
    """Build immutable table identity from verified source discovery, not Codex output."""
    from brand_size_chart.stage.table_extraction import TableExtractionStep

    evidence_path = (
        tmp_path / ".playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/"
        "official_brand_size_guide/table_extract/evidence/women_upper/table.json"
    )
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    source_discovery = SourceDiscovery(
        country_code_list=["TR"],
        evidence_path_list=[evidence_path.relative_to(tmp_path).as_posix()],
        size_group_key="women_upper",
        source_title="Kadın Üst Beden Tablosu",
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )
    table_extraction = _table_extraction_artifact_get(
        chart=BrandSizeChart(
            description="Different title",
            row_list=[
                BrandSizeChartRow(
                    measurement_list=[
                        BrandSizeChartMeasurement(name="Beden", min_value="S", max_value="S", unit="size"),
                    ],
                    size_label="S",
                )
            ],
        ),
        evidence_path_list=[evidence_path.relative_to(tmp_path).as_posix()],
        size_group_key="women_upper",
        source_title="Different title",
        tmp_path=tmp_path,
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )
    stage_dir = _table_extract_stage_dir_prepare(
        tmp_path,
        [table_extraction],
        source_type="official_brand_size_guide",
    )

    def fake_codex_stage_run(
        *,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return fake table extraction delta and successful verification."""

        _ = browser_runtime_mcp_url
        _ = prompt_text
        _ = result_dir
        _ = stage_dir
        _ = stage_name
        if model_class is StageVerificationResult:
            return StageVerificationResult(status="success")
        return _table_extraction_delta_batch_result_get([table_extraction])

    table_extraction_result = TableExtractionStep(
        brand_input=BrandInput(
            parsed_brand_key="defacto",
            parsed_brand_name="Defacto",
            raw_brand_name="Defacto",
            source_line_number=1,
        ),
        browser_runtime_mcp_url="http://127.0.0.1:8931/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_discovery_list=[source_discovery],
        source_type="official_brand_size_guide",
    ).run()
    result_payload = json.loads(stage_result_path_get(stage_dir).read_text(encoding="utf-8"))
    built_table_extraction = table_extraction_result.table_extraction_list[0]

    assert stage_dir.is_dir()
    assert TableExtractionResult.model_validate(result_payload) == table_extraction_result
    assert built_table_extraction.source_title == "Kadın Üst Beden Tablosu"
    assert built_table_extraction.country_code_list == ["TR"]
    assert built_table_extraction.source_type == "official_brand_size_guide"


def test_table_extraction_validator_rejects_missing_deterministic_chart_artifact(tmp_path: Path) -> None:
    """Require batch extraction chart artifacts at the Python-owned deterministic stage path."""
    from brand_size_chart.validator.table_extraction import TableExtractionValidator

    first_evidence_path = (
        tmp_path / ".playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/"
        "official_brand_size_guide/table_extract/evidence/women_upper/table.json"
    )
    second_evidence_path = (
        tmp_path / ".playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/"
        "official_brand_product_page/table_extract/evidence/women_lower/table.json"
    )
    first_evidence_path.parent.mkdir(parents=True)
    second_evidence_path.parent.mkdir(parents=True)
    first_evidence_path.write_text("{}\n", encoding="utf-8")
    second_evidence_path.write_text("{}\n", encoding="utf-8")
    first_discovery = SourceDiscovery(
        country_code_list=["TR"],
        evidence_path_list=[],
        size_group_key="women_upper",
        source_title="Women upper",
        source_url="https://www.defacto.com.tr/size-guide",
    )
    second_discovery = SourceDiscovery(
        country_code_list=["TR"],
        evidence_path_list=[],
        size_group_key="women_lower",
        source_title="Women lower",
        source_url="https://www.defacto.com.tr/product",
    )
    first_extraction = _table_extraction_artifact_get(
        chart=BrandSizeChart(
            description="Women upper",
            row_list=[
                BrandSizeChartRow(
                    measurement_list=[
                        BrandSizeChartMeasurement(name="SIZE", min_value="S", max_value="S", unit="size")
                    ],
                    size_label="S",
                )
            ],
        ),
        evidence_path_list=[first_evidence_path.relative_to(tmp_path).as_posix()],
        size_group_key="women_upper",
        source_title="Women upper",
        tmp_path=tmp_path,
        source_url="https://www.defacto.com.tr/size-guide",
    )
    second_extraction = _table_extraction_artifact_get(
        chart=BrandSizeChart(
            description="Women lower",
            row_list=[
                BrandSizeChartRow(
                    measurement_list=[
                        BrandSizeChartMeasurement(name="SIZE", min_value="M", max_value="M", unit="size")
                    ],
                    size_label="M",
                )
            ],
        ),
        evidence_path_list=[second_evidence_path.relative_to(tmp_path).as_posix()],
        size_group_key="women_lower",
        source_title="Women lower",
        source_type="official_brand_product_page",
        tmp_path=tmp_path,
        source_url="https://www.defacto.com.tr/product",
    )
    second_extraction = TableExtractionArtifact.model_validate(
        {
            **second_extraction.model_dump(mode="python"),
            "source_type": "official_brand_size_guide",
        }
    )
    stage_dir = _table_extract_stage_dir_prepare(
        tmp_path,
        [first_extraction, second_extraction],
        source_type="official_brand_size_guide",
    )
    second_expected_extraction = TableExtractionArtifact.model_validate(
        {
            **second_extraction.model_dump(mode="python"),
            "chart_path": (stage_dir / "chart" / "women_lower.json").relative_to(tmp_path).as_posix(),
        }
    )

    try:
        TableExtractionValidator(
            stage_input=_table_extraction_stage_input_get(
                source_discovery_list=[first_discovery, second_discovery],
                stage_dir=stage_dir,
                tmp_path=tmp_path,
            ),
            result_dir=tmp_path,
        ).validate(_table_extraction_result_get([first_extraction, second_expected_extraction]))
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "missing artifact" in message
    assert "women_lower" in message


def test_semantic_stages_live_under_stage_package() -> None:
    """Keep semantic stage lifecycle outside DBOS workflow orchestration."""
    from brand_size_chart.stage.canonical_selection import CanonicalSelectionStep
    from brand_size_chart.stage.coverage_decision import CoverageDecisionStep
    from brand_size_chart.stage.source_discovery import SourceDiscoveryStep
    from brand_size_chart.stage.table_extraction import TableExtractionStep
    from brand_size_chart.stage.workflow_run_prompt_apply import WorkflowRunPromptApplyStep

    assert WorkflowRunPromptApplyStep.__name__ == "WorkflowRunPromptApplyStep"
    assert SourceDiscoveryStep.__name__ == "SourceDiscoveryStep"
    assert TableExtractionStep.__name__ == "TableExtractionStep"
    assert CoverageDecisionStep.__name__ == "CoverageDecisionStep"
    assert CanonicalSelectionStep.__name__ == "CanonicalSelectionStep"


def test_coverage_decision_validation_retries_inside_semantic_stage(tmp_path: Path) -> None:
    """Feed coverage-decision mechanical errors back into the semantic retry loop."""
    from pydantic import BaseModel

    from brand_size_chart.stage.coverage_decision import CoverageDecisionStep

    call_list: list[dict[str, object]] = []

    def fake_codex_stage_run(
        *,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return one mechanically invalid coverage result, then a corrected result.

        Args:
            browser_runtime_mcp_url: Browser runtime URL.
            model_class: Expected result model.
            prompt_text: Prompt text with feedback.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake coverage or verification result.
        """
        _ = browser_runtime_mcp_url
        _ = result_dir
        _ = stage_dir
        _ = stage_name
        call_list.append({"model_class": model_class, "prompt_text": prompt_text})
        if model_class is StageVerificationResult:
            return StageVerificationResult(
                status="success",
            )
        coverage_call_count = len([call for call in call_list if call["model_class"] is CoverageDecisionResult])
        if coverage_call_count == 1:
            return CoverageDecisionResult(
                covered_product_type_list=[
                    CoveredProductType(
                        chart_path=(
                            "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/"
                            "table_extract/chart/women.json"
                        ),
                        product_type="women shoes",
                        reason="Verified source table exists.",
                    )
                ],
                uncovered_product_type_gap_list=[
                    CoverageDecisionProductTypeGap(
                        product_type="unexpected_product",
                        reason="Unexpected product type.",
                    )
                ],
            )

        assert "coverage_decide returned unexpected product types" in prompt_text
        return CoverageDecisionResult(
            covered_product_type_list=[],
            uncovered_product_type_gap_list=[
                CoverageDecisionProductTypeGap(
                    product_type="women shoes",
                    reason="No matching verified table.",
                )
            ],
        )

    result = CoverageDecisionStep(
        brand_input=BrandInput(
            parsed_brand_key="defacto",
            parsed_brand_name="Defacto",
            raw_brand_name="Defacto",
            source_line_number=1,
        ),
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR", product_type_request_list=["women shoes"]),
        result_dir=tmp_path,
        stage_dir=tmp_path / "coverage_decide",
        table_extraction_list=[
            _table_extraction_artifact_get(
                chart=BrandSizeChart(description="Women shoes", row_list=[]),
                size_group_key="women",
                source_title="Women shoes",
                tmp_path=tmp_path,
                source_url="https://www.defacto.com.tr/size",
            )
        ],
    ).run()

    coverage_call_list = [call for call in call_list if call["model_class"] is CoverageDecisionResult]
    assert len(coverage_call_list) == 2
    assert [gap.product_type for gap in result.uncovered_product_type_gap_list] == ["women shoes"]


def test_coverage_decision_stage_input_contains_table_evidence_references(tmp_path: Path) -> None:
    """Give coverage decision the evidence-backed table context required for product-type coverage."""
    from pydantic import BaseModel

    from brand_size_chart.stage.coverage_decision import CoverageDecisionStep

    call_list: list[dict[str, object]] = []

    def fake_codex_stage_run(
        *,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Assert coverage decision sees source, chart, and evidence references.

        Args:
            browser_runtime_mcp_url: Browser runtime URL.
            model_class: Expected result model.
            prompt_text: Rendered prompt text.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake coverage decision or verification result.
        """
        _ = browser_runtime_mcp_url
        _ = result_dir
        _ = stage_name
        call_list.append({"model_class": model_class, "prompt_text": prompt_text})
        if model_class is StageVerificationResult:
            return StageVerificationResult(status="success")
        stage_input = json.loads((stage_dir / "input.json").read_text(encoding="utf-8"))
        table_artifact = stage_input["verified_table_artifact_list"][0]
        assert "input.json" in prompt_text
        assert table_artifact["source_url"] == "https://www.defacto.com.tr/beden-rehberi"
        assert (
            table_artifact["chart_path"]
            == "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract/chart/women_shoes.json"
        )
        assert table_artifact["evidence_path_list"] == [
            "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract/evidence/women_shoes.md"
        ]
        assert table_artifact["country_code_list"] == ["TR"]
        return CoverageDecisionResult(
            covered_product_type_list=[
                CoveredProductType(
                    chart_path=table_artifact["chart_path"],
                    product_type="women shoes",
                    reason="Verified chart and evidence explicitly cover women shoes.",
                )
            ],
        )

    result = CoverageDecisionStep(
        brand_input=BrandInput(
            parsed_brand_key="defacto",
            parsed_brand_name="Defacto",
            raw_brand_name="Defacto",
            source_line_number=1,
        ),
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR", product_type_request_list=["women shoes"]),
        result_dir=tmp_path,
        stage_dir=tmp_path / "coverage_decide",
        table_extraction_list=[
            _table_extraction_artifact_get(
                applicability_description="Official TR women shoes table.",
                chart=BrandSizeChart(description="Women shoes", row_list=[]),
                evidence_path_list=[
                    (
                        "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/"
                        "table_extract/evidence/women_shoes.md"
                    )
                ],
                size_group_key="women_shoes",
                source_title="Women shoes",
                tmp_path=tmp_path,
                source_url="https://www.defacto.com.tr/beden-rehberi",
            )
        ],
    ).run()

    coverage_call_list = [call for call in call_list if call["model_class"] is CoverageDecisionResult]
    assert len(coverage_call_list) == 1
    assert result.covered_product_type_list[0].product_type == "women shoes"


def test_coverage_decision_stage_has_no_deterministic_draft() -> None:
    """Keep coverage decisions inside the verified Codex stage lifecycle."""
    from brand_size_chart.stage.coverage_decision import CoverageDecisionStep

    assert not hasattr(CoverageDecisionStep, "draft_result_get")


def test_coverage_decision_validator_requires_structured_covered_product_types() -> None:
    """Do not accept positive coverage without a physical table handle."""
    from brand_size_chart.validator.coverage_decision import CoverageDecisionValidator

    coverage_decision_result = CoverageDecisionResult(
        covered_product_type_list=[
            CoveredProductType(
                chart_path="missing.json",
                product_type="women shoes",
                reason="Verified table covers women shoes.",
            )
        ],
    )

    try:
        CoverageDecisionValidator(
            stage_input=CoverageDecisionInput(
                brand_name="Defacto",
                requested_product_type_list=["women shoes"],
                verified_table_artifact_list=[],
            ),
        ).validate(coverage_decision_result)
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "unknown chart_path" in message


def test_workflow_yaml_declares_required_cross_project_contract_keys() -> None:
    """Expose required input, output, and runtime keys in workflow metadata."""
    workflow = yaml.safe_load(Path("workflow.yaml").read_text(encoding="utf-8"))

    assert [source["name"] for source in workflow["data_source_list"]] == ["brand_list", "secret"]
    assert [container["name"] for container in workflow["data_container_list"]] == [
        "brand_size_chart",
        "brand_size_chart_audit",
    ]
    assert workflow["data_source_list"][1]["is_private"] is True
    assert workflow["data_source_list"][1]["mutable_prefix_list"] == ["playwright_profile/**"]
    assert workflow["runtime_capability_list"] == [
        {
            "data_source_name": "secret",
            "name": "browser_vpn_runtime",
        }
    ]


def test_workflow_contract_file_validate() -> None:
    """Validate standard workflow-container contract files."""

    workflow_contract_file_validate(project_root=Path.cwd())


def test_project_secret_is_ignored_by_git() -> None:
    """Keep the local private DataSource out of git."""
    gitignore_text = Path(".gitignore").read_text(encoding="utf-8")

    assert ".secret" in gitignore_text.splitlines()


def test_local_compose_declares_vpn_profile() -> None:
    """Keep only the browser runtime in the OpenVPN network namespace."""
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    openvpn_volume_list = compose["services"]["openvpn"]["volumes"]
    playwright_mcp_volume_list = compose["services"]["playwright-mcp"]["volumes"]
    workflow_volume_list = compose["services"]["workflow"]["volumes"]
    workflow_command_text = compose["services"]["workflow"]["command"][-1]
    workflow_dockerfile_text = Path("docker/workflow/Dockerfile").read_text(encoding="utf-8")

    assert (
        compose["services"]["openvpn"]["build"]["context"] == "${BROWSER_VPN_RUNTIME_CONTEXT:-../browser-vpn-runtime}"
    )
    assert (
        compose["services"]["playwright-mcp"]["build"]["context"]
        == "${BROWSER_VPN_RUNTIME_CONTEXT:-../browser-vpn-runtime}"
    )
    assert compose["services"]["playwright-mcp"]["profiles"] == ["vpn"]
    assert compose["services"]["playwright-mcp"]["entrypoint"] == []
    assert "--allowed-hosts localhost,127.0.0.1,openvpn" in compose["services"]["playwright-mcp"]["command"][-1]
    assert "--output-dir /output/.playwright-mcp/current" in compose["services"]["playwright-mcp"]["command"][-1]
    assert "--output-dir /output\n" not in compose["services"]["playwright-mcp"]["command"][-1]
    assert (
        '--persistent-profile-path "/runtime/browser_vpn_runtime/playwright_profile"'
        in compose["services"]["playwright-mcp"]["command"][-1]
    )
    assert (
        '--mcp-config-path "/runtime/browser_vpn_runtime/playwright_mcp/config.json"'
        in compose["services"]["playwright-mcp"]["command"][-1]
    )
    assert (
        '--persistent-profile-path "/output/brand_size_chart_audit/run/browser_vpn_runtime/playwright_profile"'
        not in compose["services"]["playwright-mcp"]["command"][-1]
    )
    assert (
        '--mcp-config-path "/output/brand_size_chart_audit/run/browser_vpn_runtime/playwright_mcp/config.json"'
        not in compose["services"]["playwright-mcp"]["command"][-1]
    )
    assert compose["services"]["playwright-mcp"]["network_mode"] == "service:openvpn"
    assert compose["services"]["playwright-mcp"]["depends_on"]["openvpn"]["condition"] == "service_healthy"
    assert "network_mode" not in compose["services"]["workflow"]
    assert compose["services"]["workflow"]["dns"] == ["1.1.1.1", "8.8.8.8"]
    assert compose["services"]["workflow"]["depends_on"]["playwright-mcp"]["condition"] == "service_healthy"
    assert "BRAND_LIST" not in compose["services"]["workflow"]["environment"]
    assert compose["services"]["workflow"]["environment"]["BROWSER_RUNTIME_MCP_URL"] == "http://openvpn:8931/mcp"
    assert (
        compose["services"]["workflow"]["environment"]["DBOS_SYSTEM_DATABASE_URL"] == "sqlite:////runtime/dbos.sqlite"
    )
    assert (
        compose["services"]["workflow"]["build"]["additional_contexts"]["workflow_container_runtime"]
        == "${WORKFLOW_CONTAINER_RUNTIME_CONTEXT:-../workflow-container-runtime}"
    )
    assert "./.secret:/input/.secret:ro" in openvpn_volume_list
    assert "./.secret:/input/.secret:ro" in playwright_mcp_volume_list
    assert "${OUTPUT_DIR:-./out}:/output" in playwright_mcp_volume_list
    assert "./.secret:/input/.secret:ro" in workflow_volume_list
    assert {
        "type": "bind",
        "source": "${BRAND_LIST:?Set BRAND_LIST to a brand list file path}",
        "target": "/input/brand_list.txt",
        "read_only": True,
        "bind": {"create_host_path": False},
    } in workflow_volume_list
    assert "${OUTPUT_DIR:-./out}:/output" in workflow_volume_list
    assert ".:/workspace/brand-size-chart" not in playwright_mcp_volume_list
    assert ".:/workspace/brand-size-chart" not in workflow_volume_list
    assert "--input-secret /input/.secret" in workflow_command_text
    assert "--secret /runtime/.secret" in workflow_command_text
    assert "--brand-list /input/brand_list.txt" in workflow_command_text
    assert "--output-dir /output" in workflow_command_text
    assert ".secret/dbos" not in workflow_command_text
    assert "pip install" not in workflow_command_text
    assert "--require-vpn-route" not in compose["services"]["playwright-mcp"]["command"][-1]
    assert "COPY --from=workflow_container_runtime pyproject.toml" in workflow_dockerfile_text
    assert (
        "COPY --from=workflow_container_runtime workflow_container_runtime "
        "/tmp/workflow-container-runtime/workflow_container_runtime"
    ) in workflow_dockerfile_text
    assert "COPY brand_size_chart ./brand_size_chart" in workflow_dockerfile_text
    assert "jq ripgrep" in workflow_dockerfile_text
    assert "git+ssh" not in workflow_dockerfile_text
    assert (
        "pip install --root-user-action=ignore --no-cache-dir /tmp/workflow-container-runtime"
        in workflow_dockerfile_text
    )
    assert "&& python -m pip install --root-user-action=ignore --no-cache-dir ." in workflow_dockerfile_text
    assert "healthcheck" in compose["services"]["openvpn"]
    assert "healthcheck" in compose["services"]["playwright-mcp"]


def test_browser_evidence_layout_uses_playwright_mcp_namespace(tmp_path: Path) -> None:
    """Keep browser evidence away from root workflow artifact directories."""
    layout = ArtifactLayout(tmp_path)
    brand_input = BrandInput(
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        raw_brand_name="Defacto",
        source_line_number=1,
    )

    source_evidence_path = layout.source_discover_evidence_dir(brand_input, "official_brand_size_guide")
    table_evidence_path = layout.table_extract_evidence_dir(
        brand_input,
        "official_brand_size_guide",
        "women_upper",
    )

    assert layout.artifact_path(source_evidence_path) == (
        ".playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/"
        "official_brand_size_guide/source_discover/evidence"
    )
    assert layout.artifact_path(table_evidence_path) == (
        ".playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/"
        "official_brand_size_guide/table_extract/evidence/women_upper"
    )


def test_workflow_imports_dbos_eagerly_without_noop_decorator_fallback() -> None:
    """Keep workflow functions real DBOS workflow and step functions."""
    workflow_source = _workflow_package_source_text_get()

    assert "except ModuleNotFoundError" not in workflow_source
    assert "DBOS = None" not in workflow_source
    assert "def _dbos_step" not in workflow_source
    assert "def _dbos_workflow" not in workflow_source


def test_source_type_registry_has_no_separate_official_brand_asset_stage() -> None:
    """Keep official PDFs, images, and assets inside the official brand size-guide source type."""
    source_type_source = Path("brand_size_chart/source/source_type_registry.py").read_text(encoding="utf-8")

    assert "official_brand_asset" not in source_type_source
    official_brand_instruction = SOURCE_TYPE_REGISTRY.source_type_discovery_instruction_get(
        "official_brand_size_guide"
    ).lower()
    assert "pdf" not in official_brand_instruction
    assert "image" not in official_brand_instruction


def test_source_type_registry_uses_authority_sources_without_seller_qa_stage() -> None:
    """Keep source types based on authority and location, not on evidence format."""
    assert dict(SOURCE_TYPE_REGISTRY.source_type_priority_by_key_map) == {
        "official_brand_size_guide": 600,
        "official_seller_size_guide": 550,
        "official_brand_product_page": 500,
        "official_marketplace_product_page": 300,
        "official_marketplace_store": 200,
    }
    assert "official_seller_qa" not in SOURCE_TYPE_REGISTRY.source_type_discovery_instruction_by_key_map
    assert SOURCE_TYPE_REGISTRY.product_type_required_source_type_set == {
        "official_brand_product_page",
        "official_marketplace_product_page",
        "official_marketplace_store",
    }


def test_source_type_selection_requires_product_types_for_product_page_source_types() -> None:
    """Run product-page source types only when product types are requested."""
    source_type_list_without_product_types = workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.source_type_list_get(
        PromptScope(priority_country_code="TR")
    )
    source_type_list_with_product_types = workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.source_type_list_get(
        PromptScope(priority_country_code="TR", product_type_request_list=["bra"])
    )

    assert source_type_list_without_product_types == ["official_brand_size_guide", "official_seller_size_guide"]
    assert source_type_list_with_product_types == [
        "official_brand_size_guide",
        "official_seller_size_guide",
        "official_brand_product_page",
        "official_marketplace_product_page",
        "official_marketplace_store",
    ]


def test_size_guide_source_types_do_not_receive_product_type_scope() -> None:
    """Keep product-type lists out of source types that search non-product size-guide surfaces."""
    prompt_scope = PromptScope(
        product_type_request_list=["women dresses", "men shoes"],
        shared_instruction="Search official pages only.",
    )

    official_brand_scope = workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.source_type_prompt_scope_get(
        prompt_scope=prompt_scope,
        remaining_product_type_list=["women dresses", "men shoes"],
        source_type="official_brand_size_guide",
    )
    official_seller_scope = workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.source_type_prompt_scope_get(
        prompt_scope=prompt_scope,
        remaining_product_type_list=["women dresses", "men shoes"],
        source_type="official_seller_size_guide",
    )
    product_page_scope = workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.source_type_prompt_scope_get(
        prompt_scope=prompt_scope,
        remaining_product_type_list=["men shoes"],
        source_type="official_brand_product_page",
    )

    assert official_brand_scope.product_type_request_list == []
    assert official_seller_scope.product_type_request_list == []
    assert product_page_scope.product_type_request_list == ["men shoes"]


def test_prompt_scope_owns_priority_country_code() -> None:
    """Carry the priority country through prompt scope without product-type narrowing."""
    from brand_size_chart.validator.prompt_scope import PromptScopeValidator

    prompt_scope = PromptScope(
        priority_country_code="TR",
        product_type_request_list=["women dresses"],
        shared_instruction="Search official pages only.",
    )

    narrowed_prompt_scope = workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.source_type_prompt_scope_get(
        prompt_scope=prompt_scope,
        remaining_product_type_list=[],
        source_type="official_seller_size_guide",
    )

    with pytest.raises(RuntimeError, match="priority_country_code must be supplied"):
        PromptScopeValidator().validate(PromptScope(shared_instruction="Search official pages only."))
    assert PromptScope().priority_country_code == ""
    assert narrowed_prompt_scope.priority_country_code == "TR"
    assert "priority_country_code" in PromptScope.model_fields
    assert "country_code_list" in SourceDiscovery.model_fields


def test_source_discovery_rejects_non_priority_country_when_priority_country_exists(tmp_path: Path) -> None:
    """Return only priority-country candidates when the source type found priority-country tables."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator

    evidence_path = (
        tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "source_type" / "official_brand_size_guide"
    )
    source_discover_dir = evidence_path / "source_discover"
    evidence_path = source_discover_dir / "evidence" / "priority_country.json"
    inventory_path = source_discover_dir / "state.json"
    source_discover_dir.mkdir(parents=True)
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    artifact_layout = ArtifactLayout(tmp_path)
    source_discovery_list = [
        SourceDiscovery(
            country_code_list=["TR"],
            evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
            size_group_key="women_upper",
            source_title="Defacto TR size guide",
            source_url="https://www.defacto.com.tr/statik/beden-rehberi",
        ),
        SourceDiscovery(
            country_code_list=["MA"],
            evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
            size_group_key="women_bras",
            source_title="Defacto Morocco size guide",
            source_url="https://www.defacto.com/en-ma/static/size-charts",
        ),
    ]
    inventory_path.write_text(
        json.dumps(
            {
                "discovery_query_list": [],
                "product_type_sex_worklist": [],
                "url_list": [],
                "table_list": [
                    _source_surface_table_payload_get(
                        country_code_list=source_discovery.country_code_list,
                        evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
                        reason="visible table",
                        size_group_key=source_discovery.size_group_key,
                        source_title=source_discovery.source_title,
                        source_url=source_discovery.source_url,
                        state="accepted",
                    )
                    for source_discovery in source_discovery_list
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    try:
        SourceDiscoveryValidator(
            stage_input=_source_discovery_stage_input_get(priority_country_code="TR"),
            result_dir=tmp_path,
            stage_dir=evidence_path.parents[1],
        ).validate(_source_discovery_result_get(evidence_path.parents[1]))
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "non-priority country" in message
    assert "priority_country_code=TR" in message


def test_source_discovery_rejects_european_country_conflict_as_blocker(tmp_path: Path) -> None:
    """Reject European country conflicts instead of converting them into no-table warnings."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator

    source_discover_dir = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_brand_size_guide"
        / "source_discover"
    )
    evidence_path = source_discover_dir / "evidence" / "european_conflict.json"
    inventory_path = source_discover_dir / "state.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    artifact_layout = ArtifactLayout(tmp_path)
    inventory_path.write_text(
        json.dumps(
            {
                "discovery_query_list": [
                    {
                        "evidence_path_list": [artifact_layout.artifact_path(evidence_path)],
                        "query": "defacto european size guide",
                        "reason": "No priority-country table was visible.",
                        "state": "failed",
                    }
                ],
                "product_type_sex_worklist": [],
                "table_list": [
                    _source_surface_table_payload_get(
                        country_code_list=["EU"],
                        evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
                        reason="European country tables differ for women_upper.",
                        size_group_key="women_upper",
                        source_title="Women upper",
                        source_url="https://brand.example/eu-size-guide",
                        state="market_conflict",
                    )
                ],
                "url_list": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="conflicting European country tables"):
        SourceDiscoveryValidator(
            stage_input=_source_discovery_stage_input_get(priority_country_code="TR"),
            result_dir=tmp_path,
            stage_dir=source_discover_dir,
        ).validate(_source_discovery_result_get(source_discover_dir))


def test_source_discovery_stage_builds_source_result_from_accepted_inventory(tmp_path: Path) -> None:
    """Build cross-stage source candidates from accepted inventory instead of Codex result mirrors."""
    from pydantic import BaseModel

    from brand_size_chart.stage.source_discovery import SourceDiscoveryStep

    def fake_codex_stage_run(
        *,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return browser action result and write accepted inventory state.

        Args:
            browser_runtime_mcp_url: Browser runtime URL.
            model_class: Expected result model.
            prompt_text: Rendered prompt text.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Browser action result or verification result.
        """

        _ = browser_runtime_mcp_url
        _ = prompt_text
        _ = result_dir
        _ = stage_name
        if model_class is StageVerificationResult:
            return StageVerificationResult(status="success")
        assert model_class is BrowserActionResult
        evidence_path = stage_dir / "evidence" / "accepted.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text("{}\n", encoding="utf-8")
        artifact_path = evidence_path.relative_to(tmp_path).as_posix()
        (stage_dir / "state.json").write_text(
            json.dumps(
                {
                    "discovery_query_list": [],
                    "product_type_sex_worklist": [],
                    "url_list": [],
                    "table_list": [
                        _source_surface_table_payload_get(
                            country_code_list=["TR"],
                            evidence_path_list=[artifact_path],
                            reason="visible table",
                            size_group_key="women_upper",
                            source_title="Women upper",
                            source_url="https://brand.example/size-guide",
                            state="accepted",
                        )
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return BrowserActionResult()

    result = SourceDiscoveryStep(
        brand_input=BrandInput(
            parsed_brand_key="defacto",
            parsed_brand_name="Defacto",
            raw_brand_name="Defacto",
            source_line_number=1,
        ),
        browser_runtime_mcp_url="http://127.0.0.1:8931/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_type="official_brand_size_guide",
    ).run()
    result_payload = json.loads(
        stage_result_path_get(
            tmp_path
            / "brand_size_chart_audit"
            / "brand"
            / "defacto"
            / "source_type"
            / "official_brand_size_guide"
            / "source_discover"
        ).read_text(encoding="utf-8")
    )

    assert result == SourceDiscoveryResult(
        source_discovery_list=[
            SourceDiscovery(
                country_code_list=["TR"],
                evidence_path_list=[
                    "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/"
                    "source_discover/evidence/accepted.json"
                ],
                size_group_key="women_upper",
                source_title="Women upper",
                source_url="https://brand.example/size-guide",
            )
        ],
    )
    assert SourceDiscoveryResult.model_validate(result_payload) == result


def test_source_discovery_browser_action_result_rejects_no_table_reason_list() -> None:
    """Keep no-table reasons out of the generic browser action result."""

    with pytest.raises(ValidationError):
        BrowserActionResult(no_table_reason_list=["women shoes were not covered"])


def test_source_discovery_rejects_missing_inventory_evidence_path(tmp_path: Path) -> None:
    """Require source-surface inventory evidence path references to point to real artifacts."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator

    source_discover_dir = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_marketplace_product_page"
        / "source_discover"
    )
    inventory_path = source_discover_dir / "state.json"
    evidence_path = source_discover_dir / "evidence" / "opened_page.yml"
    evidence_path.parent.mkdir(parents=True)
    inventory_path.write_text(
        json.dumps(
            {
                "discovery_query_list": [],
                "product_type_sex_worklist": [],
                "url_list": [
                    {
                        "evidence_path_list": [
                            " brand_size_chart_audit/brand/defacto/source_type/"
                            "official_marketplace_product_page/source_discover/evidence/google_blocked.yml"
                        ],
                        "reason": "blocked page",
                        "state": "rejected",
                        "url": "https://example.test/blocked",
                    }
                ],
                "table_list": [
                    _source_surface_table_payload_get(
                        country_code_list=["GLOBAL"],
                        evidence_path_list=[evidence_path.relative_to(tmp_path).as_posix()],
                        reason="visible table",
                        size_group_key="women_hats",
                        source_title="Marketplace product size chart",
                        source_url="https://example.test/product",
                        state="accepted",
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    evidence_path.write_text("{}\n", encoding="utf-8")
    source_discovery_result = _source_discovery_result_get(inventory_path.parent)

    try:
        SourceDiscoveryValidator(
            stage_input=_source_discovery_stage_input_get(
                priority_country_code="TR",
                source_type="official_marketplace_product_page",
            ),
            result_dir=tmp_path,
            stage_dir=inventory_path.parent,
        ).validate(source_discovery_result)
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "leading or trailing whitespace" in message


def test_source_discovery_validator_uses_explicit_inventory_evidence_fields() -> None:
    """Avoid suffix-based evidence path scanning in source discovery validation."""

    validator_text = Path("brand_size_chart/validator/source_discovery.py").read_text(encoding="utf-8")

    assert "_inventory_evidence_path_list_extend" not in validator_text
    assert "_inventory_evidence_path_list_get(self, *, evidence_path_list" not in validator_text
    assert 'endswith("evidence_path")' not in validator_text
    assert 'endswith("evidence_path_list")' not in validator_text


def test_source_discovery_accepts_url_inventory_errors_without_inventory_duplication(tmp_path: Path) -> None:
    """Accept URL-level browsing failures from explicit inventory fields."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator

    inventory_path = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_brand_size_guide"
        / "source_discover"
        / "state.json"
    )
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(
        json.dumps(
            {
                "discovery_query_list": [],
                "product_type_sex_worklist": [],
                "url_list": [
                    {
                        "evidence_path_list": [inventory_path.relative_to(tmp_path).as_posix()],
                        "reason": "Google displayed reCAPTCHA.",
                        "state": "rejected",
                        "url": "https://www.google.com/search?q=Defacto",
                    }
                ],
                "table_list": [
                    _source_surface_table_payload_get(
                        country_code_list=["TR"],
                        evidence_path_list=[inventory_path.relative_to(tmp_path).as_posix()],
                        reason="visible table",
                        size_group_key="women_upper",
                        source_title="Defacto TR size guide",
                        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
                        state="accepted",
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    source_discovery_result = _source_discovery_result_get(inventory_path.parent)

    SourceDiscoveryValidator(
        stage_input=_source_discovery_stage_input_get(priority_country_code="TR"),
        result_dir=tmp_path,
        stage_dir=inventory_path.parent,
    ).validate(source_discovery_result)


def test_source_discovery_rejects_inventory_without_contract_sections(tmp_path: Path) -> None:
    """Validate source-surface inventory as a strict durable artifact."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator

    inventory_path = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_brand_size_guide"
        / "source_discover"
        / "state.json"
    )
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text('{"opened_urls": []}', encoding="utf-8")
    with pytest.raises(RuntimeError, match="table_list"):
        SourceDiscoveryValidator(
            stage_input=_source_discovery_stage_input_get(priority_country_code="TR"),
            result_dir=tmp_path,
            stage_dir=inventory_path.parent,
        ).validate(SourceDiscoveryResult())


def test_source_discovery_rejects_unlinked_product_type_worklist(tmp_path: Path) -> None:
    """Require active product-type worklist rows to be linked to concrete inventory evidence."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator

    inventory_path = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_marketplace_product_page"
        / "source_discover"
        / "state.json"
    )
    evidence_path = inventory_path.parent / "opened_page.json"
    inventory_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    artifact_layout = ArtifactLayout(tmp_path)
    inventory_path.write_text(
        json.dumps(
            {
                "discovery_query_list": [],
                "product_type_sex_worklist": [
                    {
                        "evidence_path_list": [artifact_layout.artifact_path(evidence_path)],
                        "product_type": "women dresses",
                        "reason": "requested product type",
                        "sex": "women",
                        "state": "active",
                        "worklist_key": "women_dresses",
                    }
                ],
                "url_list": [],
                "table_list": [
                    _source_surface_table_payload_get(
                        country_code_list=["TR"],
                        evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
                        reason="visible table",
                        size_group_key="women_dresses",
                        source_title="Women dresses",
                        source_url="https://market.example/product",
                        state="accepted",
                    )
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="unlinked product_type_sex_worklist"):
        SourceDiscoveryValidator(
            stage_input=_source_discovery_stage_input_get(
                priority_country_code="TR",
                product_type_request_list=["women dresses"],
                source_type="official_marketplace_product_page",
            ),
            result_dir=tmp_path,
            stage_dir=inventory_path.parent,
        ).validate(SourceDiscoveryResult())


def test_source_discovery_rejected_table_does_not_close_active_worklist(tmp_path: Path) -> None:
    """Require active worklist closure through URL entries, not rejected table rows."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator

    inventory_path = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_marketplace_product_page"
        / "source_discover"
        / "state.json"
    )
    evidence_path = inventory_path.parent / "rejected_table.json"
    inventory_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    artifact_layout = ArtifactLayout(tmp_path)
    inventory_path.write_text(
        json.dumps(
            {
                "discovery_query_list": [],
                "product_type_sex_worklist": [
                    {
                        "evidence_path_list": [artifact_layout.artifact_path(evidence_path)],
                        "product_type": "women dresses",
                        "reason": "requested product type",
                        "sex": "women",
                        "state": "active",
                        "worklist_key": "women_dresses",
                    }
                ],
                "table_list": [
                    _source_surface_table_payload_get(
                        country_code_list=["TR"],
                        evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
                        reason="not a size chart for the requested product type",
                        size_group_key="women_dresses",
                        source_title="Rejected women dresses",
                        source_url="https://market.example/product",
                        state="rejected",
                    )
                ],
                "url_list": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="unlinked product_type_sex_worklist"):
        SourceDiscoveryValidator(
            stage_input=_source_discovery_stage_input_get(
                priority_country_code="TR",
                product_type_request_list=["women dresses"],
                source_type="official_marketplace_product_page",
            ),
            result_dir=tmp_path,
            stage_dir=inventory_path.parent,
        ).validate(SourceDiscoveryResult())


def test_source_discovery_equivalent_tables_do_not_close_active_worklist(tmp_path: Path) -> None:
    """Keep equivalent table rows as audit rows, not worklist closure evidence."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator

    inventory_path = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_marketplace_product_page"
        / "source_discover"
        / "state.json"
    )
    evidence_path = inventory_path.parent / "duplicate_table.json"
    inventory_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    artifact_layout = ArtifactLayout(tmp_path)
    inventory_path.write_text(
        json.dumps(
            {
                "discovery_query_list": [],
                "product_type_sex_worklist": [
                    {
                        "evidence_path_list": [artifact_layout.artifact_path(evidence_path)],
                        "product_type": "women dresses",
                        "reason": "requested product type",
                        "sex": "women",
                        "state": "active",
                        "worklist_key": "women_dresses",
                    }
                ],
                "table_list": [
                    _source_surface_table_payload_get(
                        country_code_list=["TR"],
                        evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
                        reason="accepted chart without product worklist closure",
                        size_group_key="women_dresses",
                        source_title="Women dresses",
                        source_url="https://market.example/product",
                        state="accepted",
                    ),
                    _source_surface_table_payload_get(
                        country_code_list=["TR"],
                        evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
                        reason="duplicate of accepted women_dresses",
                        size_group_key="women_dresses",
                        source_title="Women dresses duplicate",
                        source_url="https://market.example/product?duplicate=1",
                        state="equivalent",
                    ),
                ],
                "url_list": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="unlinked product_type_sex_worklist"):
        SourceDiscoveryValidator(
            stage_input=_source_discovery_stage_input_get(
                priority_country_code="TR",
                product_type_request_list=["women dresses"],
                source_type="official_marketplace_product_page",
            ),
            result_dir=tmp_path,
            stage_dir=inventory_path.parent,
        ).validate(_source_discovery_result_get(inventory_path.parent))


def test_source_discovery_rejects_table_worklist_links(tmp_path: Path) -> None:
    """Reject worklist linkage on table rows at the inventory schema boundary."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator

    inventory_path = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_marketplace_product_page"
        / "source_discover"
        / "state.json"
    )
    evidence_path = inventory_path.parent / "inventory.json"
    inventory_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    artifact_layout = ArtifactLayout(tmp_path)
    inventory_path.write_text(
        json.dumps(
            {
                "discovery_query_list": [],
                "product_type_sex_worklist": [
                    {
                        "evidence_path_list": [artifact_layout.artifact_path(evidence_path)],
                        "product_type": "women dresses",
                        "reason": "requested product type",
                        "sex": "women",
                        "state": "active",
                        "worklist_key": "women_dresses",
                    }
                ],
                "table_list": [
                    _source_surface_table_payload_get(
                        country_code_list=["TR"],
                        evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
                        reason="visible table",
                        size_group_key="women_dresses",
                        source_title="Women dresses",
                        source_url="https://market.example/product",
                        state="accepted",
                    )
                    | {"worklist_key_list": ["women_dresses"]},
                ],
                "url_list": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="worklist_key_list"):
        SourceDiscoveryValidator(
            stage_input=_source_discovery_stage_input_get(
                priority_country_code="TR",
                product_type_request_list=["women dresses"],
                source_type="official_marketplace_product_page",
            ),
            result_dir=tmp_path,
            stage_dir=inventory_path.parent,
        ).validate(SourceDiscoveryResult())


def test_source_discovery_rejects_equivalent_without_accepted_row(tmp_path: Path) -> None:
    """Reject equivalent rows that do not point to an accepted table key."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator

    inventory_path = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_brand_size_guide"
        / "source_discover"
        / "state.json"
    )
    evidence_path = inventory_path.parent / "equivalent_table.json"
    inventory_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    artifact_layout = ArtifactLayout(tmp_path)
    inventory_path.write_text(
        json.dumps(
            {
                "discovery_query_list": [],
                "product_type_sex_worklist": [],
                "table_list": [
                    _source_surface_table_payload_get(
                        country_code_list=["TR"],
                        evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
                        reason="equivalent but no accepted canonical table exists",
                        size_group_key="women_upper",
                        source_title="Women upper equivalent",
                        source_url="https://brand.example/equivalent",
                        state="equivalent",
                    )
                ],
                "url_list": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="equivalent table rows must reference"):
        SourceDiscoveryValidator(
            stage_input=_source_discovery_stage_input_get(priority_country_code="TR"),
            result_dir=tmp_path,
            stage_dir=inventory_path.parent,
        ).validate(_source_discovery_result_get(inventory_path.parent))


def test_source_discovery_accepts_rejected_product_type_worklist_without_second_link(tmp_path: Path) -> None:
    """Treat rejected product-type worklist rows as terminal through their own reason and evidence."""
    from brand_size_chart.artifact.layout import ArtifactLayout
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator

    inventory_path = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_marketplace_product_page"
        / "source_discover"
        / "state.json"
    )
    evidence_path = inventory_path.parent / "rejected_product_type.json"
    inventory_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    artifact_layout = ArtifactLayout(tmp_path)
    inventory_path.write_text(
        json.dumps(
            {
                "discovery_query_list": [],
                "product_type_sex_worklist": [
                    {
                        "evidence_path_list": [artifact_layout.artifact_path(evidence_path)],
                        "product_type": "men dresses",
                        "reason": "Product type is not applicable for this sex.",
                        "sex": "men",
                        "state": "rejected",
                        "worklist_key": "men_dresses",
                    }
                ],
                "url_list": [],
                "table_list": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    SourceDiscoveryValidator(
        stage_input=_source_discovery_stage_input_get(
            priority_country_code="TR",
            product_type_request_list=["men dresses"],
            source_type="official_marketplace_product_page",
        ),
        result_dir=tmp_path,
        stage_dir=inventory_path.parent,
    ).validate(_source_discovery_result_get(inventory_path.parent))


def test_source_discovery_rejects_rejected_product_type_worklist_without_evidence(tmp_path: Path) -> None:
    """Require rejected product-type worklist rows to carry their own evidence."""
    from brand_size_chart.validator.source_discovery import SourceDiscoveryValidator

    inventory_path = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_marketplace_product_page"
        / "source_discover"
        / "state.json"
    )
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(
        json.dumps(
            {
                "discovery_query_list": [],
                "product_type_sex_worklist": [
                    {
                        "evidence_path_list": [],
                        "product_type": "men dresses",
                        "reason": "Product type is not applicable for this sex.",
                        "sex": "men",
                        "state": "rejected",
                        "worklist_key": "men_dresses",
                    }
                ],
                "url_list": [],
                "table_list": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="rejected product_type_sex_worklist row has no evidence_path_list"):
        SourceDiscoveryValidator(
            stage_input=_source_discovery_stage_input_get(
                priority_country_code="TR",
                product_type_request_list=["men dresses"],
                source_type="official_marketplace_product_page",
            ),
            result_dir=tmp_path,
            stage_dir=inventory_path.parent,
        ).validate(_source_discovery_result_get(inventory_path.parent))


def test_table_extraction_builds_country_code_from_source_market(tmp_path: Path) -> None:
    """Keep table extraction country scope owned by the verified source market."""
    from brand_size_chart.validator.table_extraction import TableExtractionValidator

    evidence_path = tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "evidence.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}", encoding="utf-8")
    source_discovery = SourceDiscovery(
        country_code_list=["TR"],
        size_group_key="boys_3_8_year_clothing",
        source_title="DeFacto Beden Rehberi",
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )
    table_extraction = _table_extraction_artifact_get(
        country_code_list=["TR"],
        chart=BrandSizeChart(
            description="Boys 3-8 chart.",
            row_list=[
                BrandSizeChartRow(
                    measurement_list=[
                        BrandSizeChartMeasurement(
                            max_value="3-4 YAŞ",
                            min_value="3-4 YAŞ",
                            name="BEDENLER",
                            unit="size",
                        ),
                        BrandSizeChartMeasurement(max_value="104", min_value="98", name="Boy", unit="cm"),
                    ],
                    size_label="3-4 YAŞ",
                )
            ],
        ),
        evidence_path_list=[evidence_path.relative_to(tmp_path).as_posix()],
        size_group_key="boys_3_8_year_clothing",
        source_title="DeFacto Beden Rehberi",
        tmp_path=tmp_path,
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )
    stage_dir = _table_extract_stage_dir_prepare(
        tmp_path,
        [table_extraction],
        source_type="official_brand_size_guide",
    )

    validator = TableExtractionValidator(
        stage_input=_table_extraction_stage_input_get(
            source_discovery_list=[source_discovery],
            stage_dir=stage_dir,
            tmp_path=tmp_path,
        ),
        result_dir=tmp_path,
    )

    validator.validate(_table_extraction_result_get([table_extraction]))


def test_table_extraction_rejects_missing_size_label_measurement(tmp_path: Path) -> None:
    """Preserve the source row size label as a unit=size measurement."""
    from brand_size_chart.validator.table_extraction import TableExtractionValidator

    evidence_path = tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "evidence.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}", encoding="utf-8")
    source_discovery = SourceDiscovery(
        country_code_list=["TR"],
        size_group_key="boys_3_8_year_clothing",
        source_title="DeFacto Beden Rehberi",
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )
    table_extraction = _table_extraction_artifact_get(
        chart=BrandSizeChart(
            description="Boys 3-8 chart.",
            row_list=[
                BrandSizeChartRow(
                    measurement_list=[
                        BrandSizeChartMeasurement(max_value="104", min_value="98", name="Boy", unit="cm"),
                    ],
                    size_label="3-4 YAŞ",
                )
            ],
        ),
        evidence_path_list=[evidence_path.relative_to(tmp_path).as_posix()],
        size_group_key="boys_3_8_year_clothing",
        source_title="DeFacto Beden Rehberi",
        tmp_path=tmp_path,
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )
    stage_dir = _table_extract_stage_dir_prepare(
        tmp_path,
        [table_extraction],
        source_type="official_brand_size_guide",
    )

    try:
        TableExtractionValidator(
            stage_input=_table_extraction_stage_input_get(
                source_discovery_list=[source_discovery],
                stage_dir=stage_dir,
                tmp_path=tmp_path,
            ),
            result_dir=tmp_path,
        ).validate(_table_extraction_result_get([table_extraction]))
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "unit=size" in message
    assert "size_label" in message


def test_canonical_selection_rejects_missing_verified_tables(tmp_path: Path) -> None:
    """Do not let semantic canonical selection drop verified canonical tables."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator

    table_extraction = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Women upper", row_list=[]),
        size_group_key="women_upper",
        source_title="Women upper",
        tmp_path=tmp_path,
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )
    canonical_selection_result = CanonicalSelectionResult(
        canonical_selection_list=[],
    )

    try:
        CanonicalSelectionValidator(stage_input=_canonical_selection_stage_input_get([table_extraction])).validate(
            canonical_selection_result
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "canonical_select missing candidate size_group_key" in message
    assert "women_upper" in message


def test_canonical_selection_stage_writes_empty_result_without_codex(tmp_path: Path) -> None:
    """Skip Codex semantic selection when no verified table candidates exist."""

    def fake_codex_stage_run(**kwargs: object) -> CanonicalSelectionResult:
        """Reject Codex calls for empty canonical selection.

        Args:
            kwargs: Unexpected Codex runner kwargs.

        Returns:
            No value because the function must not be called.
        """

        _ = kwargs
        raise AssertionError("canonical_select Codex runner must not run without verified candidates")

    stage_dir = tmp_path / "canonical_select"
    result = CanonicalSelectionStep(
        brand_name="Defacto",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(),
        result_dir=tmp_path,
        stage_dir=stage_dir,
        table_extraction_list=[],
    ).run()

    result_payload = json.loads(stage_result_path_get(stage_dir).read_text(encoding="utf-8"))
    verification_payload = json.loads((stage_dir / "verification.json").read_text(encoding="utf-8"))
    assert result == CanonicalSelectionResult(canonical_selection_list=[])
    assert result_payload == {"canonical_selection_list": []}
    assert verification_payload == {"feedback_list": [], "status": "success"}


def test_canonical_selection_validator_uses_stage_input_candidate_priority(tmp_path: Path) -> None:
    """Treat prompt-context candidates as the only canonical-selection decision context."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator

    lower_registry_table = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Marketplace shoes", row_list=[]),
        size_group_key="women_shoes",
        source_title="Marketplace shoes",
        source_type="official_marketplace_store",
        source_url="https://market.example/defacto",
        tmp_path=tmp_path,
    )
    higher_registry_table = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Brand shoes", row_list=[]),
        size_group_key="women_shoes",
        source_title="Brand shoes",
        source_type="official_brand_size_guide",
        source_url="https://brand.example/size-guide",
        tmp_path=tmp_path,
    )
    stage_input = CanonicalSelectionInput(
        brand_name="Defacto",
        canonical_selection_candidate_list=[
            CanonicalSelectionCandidate(
                applicability_status="priority_country_official",
                source_priority=900,
                table_extraction_artifact=lower_registry_table,
            ),
            CanonicalSelectionCandidate(
                applicability_status="priority_country_official",
                source_priority=100,
                table_extraction_artifact=higher_registry_table,
            ),
        ],
    )

    CanonicalSelectionValidator(stage_input=stage_input).validate(
        CanonicalSelectionResult(
            canonical_selection_list=[
                CanonicalSelection(
                    selected_chart_path=lower_registry_table.chart_path,
                )
            ]
        )
    )


def test_canonical_selection_rejects_non_extracted_selection(tmp_path: Path) -> None:
    """Do not allow canonical selection to invent a source absent from verified extractions."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator

    table_extraction = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Women clothing", row_list=[]),
        size_group_key="women_clothing",
        source_title="Women clothing",
        tmp_path=tmp_path,
        source_url="https://marketplace.example/defacto",
    )
    canonical_selection_result = CanonicalSelectionResult(
        canonical_selection_list=[
            CanonicalSelection(
                selected_chart_path="brand_size_chart_audit/brand/defacto/source_type/official_brand_product_page/"
                "table_extract/chart/women_clothing.json",
            )
        ],
    )

    try:
        CanonicalSelectionValidator(stage_input=_canonical_selection_stage_input_get([table_extraction])).validate(
            canonical_selection_result
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "canonical_select missing table extraction" in message
    assert "official_brand_product_page" in message


def test_canonical_selection_rejects_lower_priority_duplicate_source(tmp_path: Path) -> None:
    """Prefer the highest-priority verified source for a duplicate size group."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator

    lower_priority_table = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Marketplace women shoes", row_list=[]),
        size_group_key="women_shoes",
        source_title="Marketplace women shoes",
        tmp_path=tmp_path,
        source_type="official_marketplace_store",
        source_url="https://marketplace.example/defacto",
    )
    higher_priority_table = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Brand women shoes", row_list=[]),
        size_group_key="women_shoes",
        source_title="Brand women shoes",
        tmp_path=tmp_path,
        source_url="https://brand.example/shoes",
    )
    canonical_selection_result = CanonicalSelectionResult(
        canonical_selection_list=[
            CanonicalSelection(
                selected_chart_path=lower_priority_table.chart_path,
            )
        ],
    )

    try:
        CanonicalSelectionValidator(
            stage_input=_canonical_selection_stage_input_get([lower_priority_table, higher_priority_table])
        ).validate(canonical_selection_result)
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "canonical_select selected lower priority" in message
    assert "women_shoes" in message


def test_canonical_selection_rejects_non_deterministic_same_priority_selection(tmp_path: Path) -> None:
    """Choose the first sorted representative among equivalent same-priority candidates."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator

    first_table = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Brand women upper", row_list=[]),
        size_group_key="women_upper",
        source_title="Brand women upper",
        tmp_path=tmp_path,
        source_type="official_brand_size_guide",
        source_url="https://brand.example/size-guide",
    )
    second_table = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Seller women upper", row_list=[]),
        size_group_key="women_upper",
        source_title="Seller women upper",
        tmp_path=tmp_path,
        source_type="official_seller_size_guide",
        source_url="https://seller.example/size-guide",
    )
    source_priority_by_key_map = {
        "official_brand_size_guide": 600,
        "official_seller_size_guide": 600,
    }
    canonical_selection_result = CanonicalSelectionResult(
        canonical_selection_list=[
            CanonicalSelection(
                selected_chart_path=second_table.chart_path,
            )
        ],
    )

    with pytest.raises(RuntimeError, match="canonical_select selected non-deterministic representative"):
        CanonicalSelectionValidator(
            stage_input=_canonical_selection_stage_input_get(
                [second_table, first_table],
                source_priority_by_key_map=source_priority_by_key_map,
            )
        ).validate(canonical_selection_result)

    CanonicalSelectionValidator(
        stage_input=_canonical_selection_stage_input_get(
            [second_table, first_table],
            source_priority_by_key_map=source_priority_by_key_map,
        )
    ).validate(
        CanonicalSelectionResult(
            canonical_selection_list=[
                CanonicalSelection(
                    selected_chart_path=first_table.chart_path,
                )
            ],
        )
    )


def test_canonical_selection_validator_accepts_selected_duplicate_source_type(tmp_path: Path) -> None:
    """Validate the selected table, not the last table with the same size_group_key."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator

    lower_priority_table = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Seller boys clothing", row_list=[]),
        size_group_key="boys_3_8_year_clothing",
        source_title="Seller boys clothing",
        tmp_path=tmp_path,
        source_type="official_seller_size_guide",
        source_url="https://seller.example/size-guide",
    )
    higher_priority_table = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Brand boys clothing", row_list=[]),
        size_group_key="boys_3_8_year_clothing",
        source_title="Brand boys clothing",
        tmp_path=tmp_path,
        source_url="https://brand.example/beden-rehberi",
    )
    canonical_selection_result = CanonicalSelectionResult(
        canonical_selection_list=[
            CanonicalSelection(
                selected_chart_path=higher_priority_table.chart_path,
            )
        ],
    )

    CanonicalSelectionValidator(
        stage_input=_canonical_selection_stage_input_get([higher_priority_table, lower_priority_table])
    ).validate(canonical_selection_result)


def test_canonical_selection_validator_accepts_omitted_unresolved_same_priority_conflict(tmp_path: Path) -> None:
    """Allow unresolved same-priority candidates to omit selection without a conflict payload."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator

    first_table = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Women upper first", row_list=[]),
        size_group_key="women_upper",
        source_title="A title",
        tmp_path=tmp_path,
        source_url="https://brand.example/a",
    )
    second_table = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Women upper second", row_list=[]),
        size_group_key="women_upper",
        source_title="Z title",
        tmp_path=tmp_path,
        source_type="official_seller_size_guide",
        source_url="https://brand.example/z",
    )
    source_priority_by_key_map = {
        "official_brand_size_guide": 600,
        "official_seller_size_guide": 600,
    }
    canonical_selection_result = CanonicalSelectionResult(canonical_selection_list=[])

    CanonicalSelectionValidator(
        stage_input=_canonical_selection_stage_input_get(
            [first_table, second_table],
            source_priority_by_key_map=source_priority_by_key_map,
        )
    ).validate(canonical_selection_result)


def test_canonical_selection_validator_rejects_omitted_single_candidate_group(tmp_path: Path) -> None:
    """Require selection when one candidate group has no same-priority ambiguity."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator

    table_extraction = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="Women upper", row_list=[]),
        size_group_key="women_upper",
        source_title="Women upper",
        tmp_path=tmp_path,
        source_url="https://brand.example/size-guide",
    )
    canonical_selection_result = CanonicalSelectionResult(canonical_selection_list=[])

    with pytest.raises(RuntimeError, match="canonical_select missing candidate size_group_key"):
        CanonicalSelectionValidator(stage_input=_canonical_selection_stage_input_get([table_extraction])).validate(
            canonical_selection_result
        )


def test_canonical_selection_stage_has_no_deterministic_draft() -> None:
    """Keep canonical selection inside the verified Codex stage lifecycle."""
    from brand_size_chart.stage.canonical_selection import CanonicalSelectionStep

    assert not hasattr(CanonicalSelectionStep, "draft_result_get")


def test_canonical_selection_result_forbids_conflict_payloads() -> None:
    """Keep unresolved conflict candidates derived from prompt context, not Codex output."""

    with pytest.raises(ValidationError):
        CanonicalSelectionResult(
            canonical_selection_list=[
                CanonicalSelection(
                    selected_chart_path="brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/"
                    "table_extract/chart/women_upper.json",
                )
            ],
            conflict_list=[
                {
                    "chart_path": "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/"
                    "table_extract/chart/women_upper.json"
                }
            ],
        )


def test_canonical_selection_prompt_receives_verified_table_context(tmp_path: Path) -> None:
    """Give canonical selection the verified table data required by its prompt contract."""
    from pydantic import BaseModel

    from brand_size_chart.stage.canonical_selection import CanonicalSelectionStep

    call_list: list[dict[str, object]] = []
    table_extraction = _table_extraction_artifact_get(
        applicability_description="Official TR women upper table.",
        chart=BrandSizeChart(description="Women upper", row_list=[]),
        evidence_path_list=[
            (
                "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/"
                "table_extract/evidence/women_upper.md"
            )
        ],
        size_group_key="women_upper",
        source_title="Women upper",
        tmp_path=tmp_path,
        source_url="https://brand.example/beden-rehberi",
    )
    blocked_table_extraction = _table_extraction_artifact_get(
        chart=BrandSizeChart(description="US-only women lower", row_list=[]),
        country_code_list=["US"],
        size_group_key="women_lower",
        source_title="US-only women lower",
        tmp_path=tmp_path,
        source_url="https://brand.example/us-size-guide",
    )

    def fake_codex_stage_run(
        *,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Assert canonical selection receives the table context it must verify.

        Args:
            browser_runtime_mcp_url: Browser runtime URL.
            model_class: Expected result model.
            prompt_text: Rendered prompt text.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake canonical-selection or verification result.
        """
        _ = browser_runtime_mcp_url
        _ = result_dir
        call_list.append({"model_class": model_class, "prompt_text": prompt_text, "stage_name": stage_name})
        if model_class is StageVerificationResult:
            return StageVerificationResult(status="success")
        stage_input = json.loads((stage_dir / "input.json").read_text(encoding="utf-8"))
        assert len(stage_input["canonical_selection_candidate_list"]) == 1
        candidate_context = stage_input["canonical_selection_candidate_list"][0]
        table_context = candidate_context["table_extraction_artifact"]
        assert "input.json" in prompt_text
        assert table_context["size_group_key"] == "women_upper"
        assert table_context["source_type"] == "official_brand_size_guide"
        assert candidate_context["source_priority"] == 600
        assert candidate_context["applicability_status"] == "priority_country_official"
        assert (
            table_context["chart_path"]
            == "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract/chart/women_upper.json"
        )
        assert table_context["applicability_description"] == "Official TR women upper table."
        assert "product_type_hint_list" not in table_context
        assert table_context["evidence_path_list"] == [
            "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract/evidence/women_upper.md"
        ]
        return CanonicalSelectionResult(
            canonical_selection_list=[
                CanonicalSelection(
                    selected_chart_path=table_context["chart_path"],
                )
            ],
        )

    result = CanonicalSelectionStep(
        brand_name="Defacto",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        stage_dir=tmp_path / "canonical_select",
        table_extraction_list=[table_extraction, blocked_table_extraction],
    ).run()

    assert result.canonical_selection_list[0].selected_chart_path == table_extraction.chart_path
    assert [call["stage_name"] for call in call_list] == ["canonical_select", "canonical_select_verify"]


def test_brand_selection_writes_selected_duplicate_table(monkeypatch: object, tmp_path: Path) -> None:
    """Write the canonical table selected by chart path when size_group_key duplicates exist."""
    from pydantic import BaseModel

    from brand_size_chart.workflow import brand as brand_workflow

    brand_input = BrandInput(
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        raw_brand_name="Defacto",
        source_line_number=1,
    )
    selected_table = _table_extraction_artifact_get(
        chart=BrandSizeChart(
            description="Selected brand table",
            row_list=[
                BrandSizeChartRow(
                    measurement_list=[
                        BrandSizeChartMeasurement(name="Beden", min_value="S", max_value="S", unit="size"),
                    ],
                    size_label="S",
                )
            ],
        ),
        size_group_key="boys_3_8_year_clothing",
        source_title="Brand boys clothing",
        tmp_path=tmp_path,
        source_url="https://brand.example/beden-rehberi",
    )
    duplicate_table = _table_extraction_artifact_get(
        chart=BrandSizeChart(
            description="Lower priority duplicate table",
            row_list=[
                BrandSizeChartRow(
                    measurement_list=[
                        BrandSizeChartMeasurement(name="Beden", min_value="M", max_value="M", unit="size"),
                    ],
                    size_label="M",
                )
            ],
        ),
        size_group_key="boys_3_8_year_clothing",
        source_title="Seller boys clothing",
        tmp_path=tmp_path,
        source_type="official_seller_size_guide",
        source_url="https://seller.example/size-guide",
    )

    class FakeCoverageDecisionStep:
        """Fail if final brand-level coverage stage is invoked."""

        def __init__(self, **kwargs: object) -> None:
            """Reject obsolete final coverage stage construction.

            Args:
                kwargs: Ignored workflow inputs.
            """

            _ = kwargs
            raise AssertionError("selection_write_step must use provided cumulative coverage result")

    class FakeCanonicalSelectionStep:
        """Return a canonical selection for the higher-priority duplicate table."""

        def __init__(self, **kwargs: object) -> None:
            """Accept workflow construction kwargs.

            Args:
                kwargs: Ignored workflow inputs.
            """

            _ = kwargs

        def run(self) -> CanonicalSelectionResult:
            """Return selected canonical chart path.

            Returns:
                Canonical selection result.
            """

            return CanonicalSelectionResult(
                canonical_selection_list=[
                    CanonicalSelection(
                        selected_chart_path=selected_table.chart_path,
                    )
                ],
            )

    monkeypatch.setattr(brand_workflow, "CoverageDecisionStep", FakeCoverageDecisionStep)
    monkeypatch.setattr(brand_workflow, "CanonicalSelectionStep", FakeCanonicalSelectionStep)

    result = brand_workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.selection_write_step.__wrapped__(
        brand_workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW,
        brand_input.model_dump(mode="json"),
        PromptScope().model_dump(mode="json"),
        str(tmp_path),
        [
            SourceTypeResult(
                source_type="official_brand_size_guide",
                table_extraction_list=[selected_table, duplicate_table],
            ).model_dump(mode="json")
        ],
        CoverageDecisionResult(
            covered_product_type_list=[],
            uncovered_product_type_gap_list=[],
        ).model_dump(mode="json"),
    )

    chart_path = tmp_path / "brand_size_chart/brand/defacto/size_chart/boys_3_8_year_clothing.json"
    chart_payload = json.loads(chart_path.read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert chart_payload["description"] == "Selected brand table"
    assert chart_payload["row_list"][0]["size_label"] == "S"


def test_table_extraction_keeps_chart_path_on_verified_table(tmp_path: Path) -> None:
    """Keep the generated chart artifact identity after loading chart content."""
    from brand_size_chart.validator.table_extraction import TableExtractionValidator

    source_type = "official_brand_size_guide"
    chart_path = (
        tmp_path / "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/"
        "table_extract/chart/women_upper.json"
    )
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart = BrandSizeChart(
        description="Women upper",
        row_list=[
            BrandSizeChartRow(
                measurement_list=[
                    BrandSizeChartMeasurement(name="Beden", min_value="S", max_value="S", unit="size"),
                ],
                size_label="S",
            )
        ],
    )
    chart_path.write_text(chart.model_dump_json(indent=2), encoding="utf-8")

    table_extraction = TableExtractionArtifact(
        chart_path=chart_path.relative_to(tmp_path).as_posix(),
        country_code_list=["TR"],
        size_group_key="women_upper",
        source_title="Women upper",
        source_type=source_type,
        source_url="https://brand.example/beden-rehberi",
    )

    assert table_extraction.chart_path == chart_path.relative_to(tmp_path).as_posix()


def test_table_extract_verification_receives_runtime_stage_artifact_paths(tmp_path: Path) -> None:
    """Give table_extract verifier runtime-owned result and prompt-context paths."""
    from pydantic import BaseModel

    from brand_size_chart.stage.table_extraction import TableExtractionStep

    source_discovery = SourceDiscovery(
        country_code_list=["TR"],
        size_group_key="women_upper",
        source_title="Women upper",
        source_url="https://brand.example/beden-rehberi",
    )
    expected_input_path = (
        "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/" "table_extract/input.json"
    )
    expected_result_path = (
        "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/table_extract/result.json"
    )

    def fake_codex_stage_run(
        *,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return a valid extraction and assert verifier prompt artifact paths.

        Args:
            browser_runtime_mcp_url: Browser runtime URL.
            model_class: Expected result model.
            prompt_text: Rendered prompt text.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake table-extraction or verification result.
        """
        _ = browser_runtime_mcp_url
        if model_class is StageVerificationResult:
            assert expected_input_path in prompt_text
            assert expected_result_path in prompt_text
            stage_input = json.loads((stage_dir / "input.json").read_text(encoding="utf-8"))
            assert "stage_state_artifact_path" not in stage_input
            assert "stage_state_filesystem_path" not in stage_input
            return StageVerificationResult(status="success")

        chart_path = stage_dir / "chart" / "women_upper.json"
        evidence_path = stage_dir / "evidence" / "women_upper" / "source.json"
        chart_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text('{"source":"browser"}\n', encoding="utf-8")
        chart_path.write_text(
            BrandSizeChart(
                description="Women upper",
                row_list=[
                    BrandSizeChartRow(
                        measurement_list=[
                            BrandSizeChartMeasurement(name="Beden", min_value="S", max_value="S", unit="size"),
                        ],
                        size_label="S",
                    )
                ],
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )
        (stage_dir / "state.json").write_text(
            json.dumps(
                [
                    {
                        "size_group_key": "women_upper",
                        "state": "extracted",
                    }
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
        return TableExtractionDeltaBatchResult(
            table_extraction_delta_list=[
                TableExtractionDelta(
                    evidence_path_list=[evidence_path.relative_to(result_dir).as_posix()],
                )
            ],
        )

    result = TableExtractionStep(
        brand_input=BrandInput(
            parsed_brand_key="defacto",
            parsed_brand_name="Defacto",
            raw_brand_name="Defacto",
            source_line_number=1,
        ),
        browser_runtime_mcp_url="http://127.0.0.1:8931/mcp",
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_discovery_list=[source_discovery],
        source_type="official_brand_size_guide",
    ).run()

    assert result.table_extraction_list[0].size_group_key == "women_upper"


def test_project_has_no_local_semantic_stage_wrapper() -> None:
    """Keep generic verified stage runtime in workflow-container-runtime."""

    assert not Path("brand_size_chart/stage/semantic.py").exists()


def test_workflow_run_prompt_apply_step_writes_input_without_draft_result(tmp_path: Path) -> None:
    """Give Codex steps typed persisted input instead of draft payloads."""
    captured_prompt_list: list[str] = []

    def fake_codex_stage_run(
        *,
        browser_runtime_mcp_url: str,
        model_class: type[PromptScope] | type[StageVerificationResult],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> PromptScope | StageVerificationResult:
        """Capture prompt text and return schema-valid fake stage outputs.

        Args:
            browser_runtime_mcp_url: Browser MCP URL.
            model_class: Expected output model.
            prompt_text: Rendered prompt text.
            result_dir: Result root.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake stage result.
        """
        _ = browser_runtime_mcp_url
        _ = result_dir
        _ = stage_dir
        captured_prompt_list.append(prompt_text)
        if model_class is StageVerificationResult:
            return StageVerificationResult(status="success")
        return PromptScope(priority_country_code="TR")

    result = WorkflowRunPromptApplyStep(
        codex_stage_run_callable=fake_codex_stage_run,
        result_dir=tmp_path,
        workflow_run_prompt="Brand: Defacto",
    ).run()

    stage_input_payload = json.loads(
        (tmp_path / "brand_size_chart_audit" / "run" / "workflow_run_prompt_apply" / "input.json").read_text(
            encoding="utf-8"
        )
    )
    assert result.priority_country_code == "TR"
    assert stage_input_payload["workflow_run_prompt"] == "Brand: Defacto"
    assert "input.json" in captured_prompt_list[0]
    assert "Draft stage result JSON:" not in captured_prompt_list[0]


def test_brand_workflow_runs_size_guides_before_product_scoped_stop(monkeypatch: object, tmp_path: Path) -> None:
    """Run every non-product size-guide source type before product-type coverage stops product stages."""
    enqueued_source_type_list: list[str] = []

    class FakeHandle:
        """Fake DBOS workflow handle."""

        def __init__(self, result_payload: dict[str, object]) -> None:
            """Store fake workflow result.

            Args:
                result_payload: Fake result returned by `get_result`.
            """
            self.result_payload = result_payload

        def get_result(self) -> dict[str, object]:
            """Return fake workflow result.

            Returns:
                Fake result payload.
            """
            return self.result_payload

    def fake_coverage_decide_write_step(
        brand_input_payload: dict[str, object],
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        source_type: str,
        table_extraction_payload_list: list[dict[str, object]],
    ) -> dict[str, object]:
        """Return full product-type coverage after every size-guide stage.

        Args:
            brand_input_payload: Serialized brand input.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Result root.
            source_type: Completed source type.
            table_extraction_payload_list: Extracted table payloads.

        Returns:
            Serialized coverage decision.
        """
        _ = brand_input_payload
        _ = result_dir
        _ = source_type
        _ = table_extraction_payload_list
        PromptScope.model_validate(prompt_scope_payload)
        return {
            "covered_product_type_list": [
                {
                    "chart_path": "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/"
                    "table_extract/chart/women_clothing.json",
                    "product_type": "women dresses",
                    "reason": "covered",
                }
            ],
            "uncovered_product_type_gap_list": [],
        }

    def fake_enqueue_workflow(
        queue_name: str,
        workflow_func: object,
        workflow_run_id: str,
        brand_input_payload: dict[str, object],
        browser_runtime_mcp_url: str,
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        source_type: str,
    ) -> FakeHandle:
        """Record source-type child workflow start and return one table.

        Args:
            queue_name: DBOS queue name.
            workflow_func: Child workflow function.
            workflow_run_id: Workflow run id.
            brand_input_payload: Serialized brand input.
            browser_runtime_mcp_url: Browser MCP URL.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Result root.
            source_type: Source type being started.

        Returns:
            Fake workflow handle.
        """
        _ = queue_name
        _ = workflow_func
        _ = workflow_run_id
        _ = brand_input_payload
        _ = browser_runtime_mcp_url
        _ = result_dir
        source_type_prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        enqueued_source_type_list.append(source_type)
        assert source_type_prompt_scope.product_type_request_list == []
        return FakeHandle(
            SourceTypeResult(
                source_type=source_type,
                table_extraction_list=[
                    TableExtractionArtifact(
                        chart_path=(
                            "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/"
                            "table_extract/chart/women_clothing.json"
                        ),
                        country_code_list=["TR"],
                        size_group_key="women_clothing",
                        source_title="Women clothing",
                        source_type=source_type,
                        source_url="https://brand.example/size-guide",
                    )
                ],
            ).model_dump(mode="json")
        )

    def fake_brand_selection_write_step(
        brand_input_payload: dict[str, object],
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        source_type_result_payload_list: list[dict[str, object]],
        coverage_result_payload: dict[str, object],
    ) -> dict[str, object]:
        """Return source-type execution result.

        Args:
            brand_input_payload: Serialized brand input.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Result root.
            source_type_result_payload_list: Source-type results.
            coverage_result_payload: Cumulative coverage result.

        Returns:
            Minimal fake brand result.
        """
        _ = brand_input_payload
        _ = prompt_scope_payload
        _ = result_dir
        _ = source_type_result_payload_list
        _ = coverage_result_payload
        return {"enqueued_source_type_list": list(enqueued_source_type_list)}

    from brand_size_chart.workflow import brand as brand_workflow_module

    monkeypatch.setattr(brand_workflow_module.DBOS, "enqueue_workflow", fake_enqueue_workflow)
    monkeypatch.setattr(brand_workflow_module, "SetWorkflowID", lambda _workflow_id: nullcontext())
    monkeypatch.setattr(
        workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW,
        "selection_write_step",
        fake_brand_selection_write_step,
    )
    monkeypatch.setattr(
        workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW,
        "coverage_decide_write_step",
        fake_coverage_decide_write_step,
    )

    result_payload = workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.run.__wrapped__(
        workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW,
        "run1",
        {
            "parsed_brand_key": "defacto",
            "parsed_brand_name": "Defacto",
            "raw_brand_name": "Defacto",
            "source_line_number": 1,
        },
        "http://browser/mcp",
        PromptScope(priority_country_code="TR", product_type_request_list=["women dresses"]).model_dump(mode="json"),
        str(tmp_path),
    )

    assert result_payload["enqueued_source_type_list"] == [
        "official_brand_size_guide",
        "official_seller_size_guide",
    ]


def test_brand_workflow_skips_intermediate_coverage_for_failed_source_type(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    """Do not run source-type coverage after a source type failed without verified tables."""
    coverage_source_type_list: list[str] = []

    class FakeHandle:
        """Fake DBOS workflow handle."""

        def __init__(self, result_payload: dict[str, object]) -> None:
            """Store fake workflow result.

            Args:
                result_payload: Fake result returned by `get_result`.
            """
            self.result_payload = result_payload

        def get_result(self) -> dict[str, object]:
            """Return fake workflow result.

            Returns:
                Fake result payload.
            """
            return self.result_payload

    def fake_coverage_decide_write_step(
        brand_input_payload: dict[str, object],
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        source_type: str,
        table_extraction_payload_list: list[dict[str, object]],
    ) -> dict[str, object]:
        """Record coverage stages and keep one product type uncovered until the product-page source.

        Args:
            brand_input_payload: Serialized brand input.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Result root.
            source_type: Completed source type.
            table_extraction_payload_list: Extracted table payloads.

        Returns:
            Serialized coverage decision.
        """
        _ = brand_input_payload
        _ = result_dir
        _ = table_extraction_payload_list
        PromptScope.model_validate(prompt_scope_payload)
        coverage_source_type_list.append(source_type)
        return CoverageDecisionResult(
            covered_product_type_list=[],
            uncovered_product_type_gap_list=(
                []
                if source_type == "official_brand_product_page"
                else [
                    CoverageDecisionProductTypeGap(
                        product_type="women dresses",
                        reason="Not covered by this source type.",
                    )
                ]
            ),
        ).model_dump(mode="json")

    def fake_enqueue_workflow(
        queue_name: str,
        workflow_func: object,
        workflow_run_id: str,
        brand_input_payload: dict[str, object],
        browser_runtime_mcp_url: str,
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        source_type: str,
    ) -> FakeHandle:
        """Return a failed source-type result between two successful source types.

        Args:
            queue_name: DBOS queue name.
            workflow_func: Child workflow function.
            workflow_run_id: Workflow run id.
            brand_input_payload: Serialized brand input.
            browser_runtime_mcp_url: Browser MCP URL.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Result root.
            source_type: Source type being started.

        Returns:
            Fake workflow handle.
        """
        _ = queue_name
        _ = workflow_func
        _ = workflow_run_id
        _ = brand_input_payload
        _ = browser_runtime_mcp_url
        _ = prompt_scope_payload
        _ = result_dir
        if source_type == "official_seller_size_guide":
            return FakeHandle(
                SourceTypeResult(
                    blocker_list=["no seller guide"],
                    source_type=source_type,
                ).model_dump(mode="json")
            )
        return FakeHandle(
            SourceTypeResult(
                source_type=source_type,
                table_extraction_list=[
                    TableExtractionArtifact(
                        chart_path=(
                            "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/"
                            "table_extract/chart/women_clothing.json"
                        ),
                        country_code_list=["TR"],
                        size_group_key="women_clothing",
                        source_title="Women clothing",
                        source_type=source_type,
                        source_url="https://brand.example/size-guide",
                    )
                ],
            ).model_dump(mode="json")
        )

    def fake_brand_selection_write_step(
        brand_input_payload: dict[str, object],
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        source_type_result_payload_list: list[dict[str, object]],
        coverage_result_payload: dict[str, object],
    ) -> dict[str, object]:
        """Return the coverage call list.

        Args:
            brand_input_payload: Serialized brand input.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Result root.
            source_type_result_payload_list: Source-type results.
            coverage_result_payload: Cumulative coverage result.

        Returns:
            Coverage source type list.
        """
        _ = brand_input_payload
        _ = prompt_scope_payload
        _ = result_dir
        _ = source_type_result_payload_list
        CoverageDecisionResult.model_validate(coverage_result_payload)
        return {"coverage_source_type_list": list(coverage_source_type_list)}

    from brand_size_chart.workflow import brand as brand_workflow_module

    monkeypatch.setattr(brand_workflow_module.DBOS, "enqueue_workflow", fake_enqueue_workflow)
    monkeypatch.setattr(brand_workflow_module, "SetWorkflowID", lambda _workflow_id: nullcontext())
    monkeypatch.setattr(
        workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW,
        "coverage_decide_write_step",
        fake_coverage_decide_write_step,
    )
    monkeypatch.setattr(
        workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW,
        "selection_write_step",
        fake_brand_selection_write_step,
    )

    result_payload = workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.run.__wrapped__(
        workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW,
        "run1",
        {
            "parsed_brand_key": "defacto",
            "parsed_brand_name": "Defacto",
            "raw_brand_name": "Defacto",
            "source_line_number": 1,
        },
        "http://browser/mcp",
        PromptScope(
            priority_country_code="TR",
            product_type_request_list=["women dresses"],
            source_type_allow_list=[
                "official_brand_size_guide",
                "official_seller_size_guide",
                "official_brand_product_page",
            ],
        ).model_dump(mode="json"),
        str(tmp_path),
    )

    assert result_payload["coverage_source_type_list"] == [
        "official_brand_size_guide",
        "official_brand_product_page",
    ]


def test_prompt_scope_rejects_product_type_values_in_shared_instruction() -> None:
    """Prevent product-type lists from leaking into stages through shared instruction text."""
    from brand_size_chart.validator.prompt_scope import PromptScopeValidator

    try:
        PromptScopeValidator().validate(
            PromptScope(
                priority_country_code="TR",
                product_type_request_list=["women dresses"],
                shared_instruction="Search all source types. Product types: women dresses.",
            )
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "shared_instruction must not repeat product_type_request_list values" in message


def test_prompt_scope_accepts_table_extract_and_rejects_table_extraction_stage_key() -> None:
    """Keep prompt stage keys aligned with live action-verb stage keys."""
    from brand_size_chart.validator.prompt_scope import PromptScopeValidator

    PromptScopeValidator().validate(
        PromptScope(
            priority_country_code="TR",
            stage_instruction_list=[PromptStageInstruction(stage_key="table_extract", instruction="focus")],
        )
    )
    try:
        PromptScopeValidator().validate(
            PromptScope(
                priority_country_code="TR",
                stage_instruction_list=[
                    PromptStageInstruction(stage_key="table_extraction", instruction="legacy focus")
                ],
            )
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "Unknown stage_instruction stage_key values" in message
    assert "table_extraction" in message


def test_workflow_run_prompt_apply_context_contains_source_type_catalog(tmp_path: Path) -> None:
    """Give prompt parsing enough source-type metadata to map natural-language restrictions."""
    stage = WorkflowRunPromptApplyStep(
        codex_stage_run_callable=lambda **kwargs: PromptScope(),
        result_dir=tmp_path,
        workflow_run_prompt="Use official manufacturer pages only.",
    )
    stage_input = stage._stage_input_get()  # noqa: SLF001
    source_type_catalog_by_key_map = {
        source_type_catalog.source_type: source_type_catalog
        for source_type_catalog in stage_input.source_type_catalog_list
    }
    assert "official_brand_size_guide" in source_type_catalog_by_key_map
    assert "source_priority" not in type(source_type_catalog_by_key_map["official_brand_size_guide"]).model_fields
    assert source_type_catalog_by_key_map["official_brand_size_guide"].requires_product_type is False
    assert (
        "Find official brand size-guide or size-chart surfaces"
        in source_type_catalog_by_key_map["official_brand_size_guide"].discovery_instruction
    )
    assert "official_marketplace_store" in source_type_catalog_by_key_map
    assert source_type_catalog_by_key_map["official_marketplace_store"].requires_product_type is True


def test_source_type_result_records_failed_source_without_discovery_artifact(tmp_path: Path) -> None:
    """Write failed source-type results without requiring a successful discovery artifact."""
    result_payload = workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.result_write_step.__wrapped__(
        workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW,
        {
            "parsed_brand_key": "defacto",
            "parsed_brand_name": "Defacto",
            "raw_brand_name": "Defacto",
            "source_line_number": 1,
        },
        str(tmp_path),
        "official_brand_size_guide",
        [],
        ["RuntimeError: source discovery failed"],
        [],
    )

    assert result_payload["blocker_list"] == ["RuntimeError: source discovery failed"]
    assert result_payload["source_type"] == "official_brand_size_guide"
    assert result_payload["table_extraction_list"] == []
    assert "state" not in result_payload


def test_source_type_result_records_no_table_discovery_warning(tmp_path: Path) -> None:
    """Record evidence-backed no-table source discovery in warning list."""
    brand_input_payload = {
        "parsed_brand_key": "defacto",
        "parsed_brand_name": "Defacto",
        "raw_brand_name": "Defacto",
        "source_line_number": 1,
    }
    source_type = "official_marketplace_store"
    result_payload = workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.result_write_step.__wrapped__(
        workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW,
        brand_input_payload,
        str(tmp_path),
        source_type,
        [],
        [],
        ["No concrete browser-visible size-chart table was returned."],
    )

    assert result_payload["blocker_list"] == []
    assert result_payload["table_extraction_list"] == []
    assert "state" not in result_payload
    assert result_payload["warning_list"] == ["No concrete browser-visible size-chart table was returned."]


def test_source_type_result_points_to_table_extract_chart_artifacts(tmp_path: Path) -> None:
    """Expose batch chart artifact paths as source-type table results."""
    brand_input = BrandInput(
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        raw_brand_name="Defacto",
        source_line_number=1,
    )
    source_type = "official_brand_size_guide"
    chart = BrandSizeChart(
        description="Women upper",
        row_list=[
            BrandSizeChartRow(
                measurement_list=[
                    BrandSizeChartMeasurement(name="SIZE", min_value="M", max_value="M", unit="size"),
                ],
                size_label="M",
            )
        ],
    )
    artifact_layout = ArtifactLayout(tmp_path)
    chart_path = artifact_layout.table_extract_chart_path(brand_input, source_type, "women_upper")
    chart_path.parent.mkdir(parents=True)
    chart_path.write_text(json.dumps(chart.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    table_extraction = _table_extraction_artifact_get(
        chart=chart,
        size_group_key="women_upper",
        source_title="Women upper",
        tmp_path=tmp_path,
        source_type=source_type,
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )

    result_payload = workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.result_write_step.__wrapped__(
        workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW,
        brand_input.model_dump(mode="json"),
        str(tmp_path),
        source_type,
        [table_extraction.model_dump(mode="json")],
        [],
        [],
    )

    assert result_payload == {
        "blocker_list": [],
        "source_type": "official_brand_size_guide",
        "table_extraction_list": [table_extraction.model_dump(mode="json")],
        "warning_list": [],
    }


def test_prompt_scope_rejects_unknown_source_type_and_stage_key() -> None:
    """Reject unknown prompt-derived execution keys instead of silently dropping them."""
    from brand_size_chart.validator.prompt_scope import PromptScopeValidator

    validator = PromptScopeValidator()
    try:
        validator.validate(PromptScope(priority_country_code="TR", source_type_allow_list=["unknown_source_type"]))
    except RuntimeError as exc:
        source_type_message = str(exc)
    else:
        source_type_message = ""

    try:
        validator.validate(
            PromptScope(
                priority_country_code="TR",
                stage_instruction_list=[PromptStageInstruction(stage_key="unknown_stage", instruction="x")],
            )
        )
    except RuntimeError as exc:
        stage_key_message = str(exc)
    else:
        stage_key_message = ""

    assert "unknown_source_type" in source_type_message
    assert "unknown_stage" in stage_key_message


def test_prompt_scope_stage_retries_unknown_source_type_allow_phrase(monkeypatch: object, tmp_path: Path) -> None:
    """Return all-source requests as an empty source-type allow-list after guard feedback."""
    prompt_scope_call_count = 0

    def fake_codex_stage_run(
        *,
        browser_runtime_mcp_url: str,
        model_class: type[object],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> object:
        """Return one invalid prompt scope, then a corrected prompt scope.

        Args:
            browser_runtime_mcp_url: Browser runtime URL.
            model_class: Expected result model.
            prompt_text: Prompt text with feedback.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake stage result.
        """
        nonlocal prompt_scope_call_count
        _ = browser_runtime_mcp_url
        _ = result_dir
        _ = stage_dir
        _ = stage_name
        if model_class is StageVerificationResult:
            return StageVerificationResult(
                status="success",
            )
        prompt_scope_call_count += 1
        if prompt_scope_call_count == 1:
            return PromptScope(
                priority_country_code="TR",
                product_type_request_list=["socks"],
                shared_instruction="Search all supported source types. Product types: socks.",
                source_type_allow_list=["all supported source types"],
            )
        if prompt_scope_call_count == 2:
            return PromptScope(
                priority_country_code="TR",
                product_type_request_list=["socks"],
                shared_instruction="Search all supported source types. Product types: socks.",
                source_type_allow_list=[],
            )
        assert "shared_instruction must not repeat product_type_request_list values" in prompt_text
        return PromptScope(
            priority_country_code="TR",
            product_type_request_list=["socks"],
            shared_instruction="Search all supported source types.",
            source_type_allow_list=[],
        )

    prompt_scope = WorkflowRunPromptApplyStep(
        codex_stage_run_callable=fake_codex_stage_run,
        result_dir=tmp_path,
        workflow_run_prompt="Priority country TR. Search all supported source types. Product types: socks.",
    ).run()

    assert prompt_scope.product_type_request_list == ["socks"]
    assert prompt_scope.source_type_allow_list == []
    assert prompt_scope.shared_instruction == "Search all supported source types."
    assert prompt_scope_call_count == 3


def test_table_extraction_stage_writes_chart_schema_artifact(tmp_path: Path) -> None:
    """Generate the BrandSizeChart schema beside table-extract prompt context."""
    from brand_size_chart.stage.table_extraction import TableExtractionStep

    source_discovery = SourceDiscovery(
        country_code_list=["TR"],
        size_group_key="women_upper",
        source_title="Women upper",
        source_url="https://www.defacto.com.tr/size-guide",
    )

    stage = TableExtractionStep(
        brand_input=BrandInput(
            parsed_brand_key="defacto",
            parsed_brand_name="Defacto",
            raw_brand_name="Defacto",
            source_line_number=1,
        ),
        browser_runtime_mcp_url="http://127.0.0.1:12000/mcp",
        codex_stage_run_callable=lambda **kwargs: StageVerificationResult(status="success"),
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        source_discovery_list=[source_discovery],
        source_type="official_brand_size_guide",
    )

    stage.artifact_prepare(stage.input_build())

    schema_path = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_brand_size_guide"
        / "table_extract"
        / "chart.schema.json"
    )
    schema_payload = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema_payload["title"] == "BrandSizeChart"
    assert "row_list" in schema_payload["properties"]


def test_table_extraction_rejects_missing_execplan_artifact(tmp_path: Path) -> None:
    """Treat batch execplan as required durable extraction state."""
    from brand_size_chart.validator.table_extraction import TableExtractionValidator

    stage_dir = (
        tmp_path
        / "brand_size_chart_audit"
        / "brand"
        / "defacto"
        / "source_type"
        / "official_brand_size_guide"
        / "table_extract"
    )
    chart_path = stage_dir / "chart" / "women_upper.json"
    evidence_path = stage_dir / "evidence" / "women_upper.json"
    chart_path.parent.mkdir(parents=True)
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    source_discovery = SourceDiscovery(
        country_code_list=["TR"],
        size_group_key="women_upper",
        source_title="Women upper",
        source_url="https://brand.example/size-guide",
    )
    table_extraction_result = TableExtractionResult(
        table_extraction_list=[
            TableExtractionArtifact(
                chart_path=chart_path.relative_to(tmp_path).as_posix(),
                country_code_list=source_discovery.country_code_list,
                evidence_path_list=[evidence_path.relative_to(tmp_path).as_posix()],
                size_group_key=source_discovery.size_group_key,
                source_title=source_discovery.source_title,
                source_type="official_brand_size_guide",
                source_url=source_discovery.source_url,
            )
        ],
    )

    with pytest.raises(RuntimeError, match="Stage table_extract returned missing artifact"):
        TableExtractionValidator(
            stage_input=_table_extraction_stage_input_get(
                source_discovery_list=[source_discovery],
                stage_dir=stage_dir,
                tmp_path=tmp_path,
            ),
            result_dir=tmp_path,
        ).validate(table_extraction_result)


def test_table_extraction_validator_uses_stage_input_chart_target(tmp_path: Path) -> None:
    """Use prompt-context chart targets instead of deriving chart paths from stage_dir."""
    from brand_size_chart.validator.table_extraction import TableExtractionValidator

    stage_dir = tmp_path / "stage" / "table_extract"
    chart_path = stage_dir / "generated_chart" / "women_upper.json"
    evidence_path = stage_dir / "generated_evidence" / "women_upper.json"
    chart_path.parent.mkdir(parents=True)
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    chart_path.write_text(
        BrandSizeChart(
            description="Women upper",
            row_list=[
                BrandSizeChartRow(
                    measurement_list=[
                        BrandSizeChartMeasurement(name="Beden", min_value="S", max_value="S", unit="size"),
                    ],
                    size_label="S",
                )
            ],
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    stage_input = TableExtractionInput(
        brand_name="Defacto",
        execplan_item_list=[
            TableExtractionExecplanItem(
                chart_filesystem_path=chart_path.as_posix(),
                evidence_write_target=ArtifactWriteTarget(
                    artifact_path=evidence_path.parent.relative_to(tmp_path).as_posix(),
                    filesystem_path=evidence_path.parent.as_posix(),
                ),
                source_discovery=SourceDiscovery(
                    country_code_list=["TR"],
                    size_group_key="women_upper",
                    source_title="Women upper",
                    source_url="https://brand.example/size-guide",
                ),
            )
        ],
    )

    TableExtractionValidator(
        stage_input=stage_input,
        result_dir=tmp_path,
    ).validate(
        TableExtractionResult(
            table_extraction_list=[
                TableExtractionArtifact(
                    chart_path=chart_path.relative_to(tmp_path).as_posix(),
                    country_code_list=["TR"],
                    evidence_path_list=[evidence_path.relative_to(tmp_path).as_posix()],
                    size_group_key="women_upper",
                    source_title="Women upper",
                    source_type="official_brand_size_guide",
                    source_url="https://brand.example/size-guide",
                )
            ],
        )
    )


def test_table_extraction_rejects_duplicate_chart_targets(tmp_path: Path) -> None:
    """Require table extraction chart targets to be unique."""
    from brand_size_chart.validator.table_extraction import TableExtractionValidator

    stage_dir = tmp_path / "stage" / "table_extract"
    chart_path = stage_dir / "chart" / "women_upper.json"
    evidence_path = stage_dir / "evidence" / "women_upper.json"
    chart_path.parent.mkdir(parents=True)
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    chart_path.write_text(
        BrandSizeChart(
            description="Women upper",
            row_list=[
                BrandSizeChartRow(
                    measurement_list=[
                        BrandSizeChartMeasurement(name="Beden", min_value="S", max_value="S", unit="size"),
                    ],
                    size_label="S",
                )
            ],
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    stage_input = TableExtractionInput(
        brand_name="Defacto",
        execplan_item_list=[
            TableExtractionExecplanItem(
                chart_filesystem_path=chart_path.as_posix(),
                evidence_write_target=ArtifactWriteTarget(
                    artifact_path=evidence_path.parent.relative_to(tmp_path).as_posix(),
                    filesystem_path=evidence_path.parent.as_posix(),
                ),
                source_discovery=SourceDiscovery(
                    country_code_list=["TR"],
                    size_group_key="women_upper",
                    source_title="Women upper",
                    source_url="https://brand.example/size-guide",
                ),
            ),
            TableExtractionExecplanItem(
                chart_filesystem_path=chart_path.as_posix(),
                evidence_write_target=ArtifactWriteTarget(
                    artifact_path=evidence_path.parent.relative_to(tmp_path).as_posix(),
                    filesystem_path=evidence_path.parent.as_posix(),
                ),
                source_discovery=SourceDiscovery(
                    country_code_list=["TR"],
                    size_group_key="women_lower",
                    source_title="Women lower",
                    source_url="https://brand.example/size-guide",
                ),
            ),
        ],
    )
    with pytest.raises(RuntimeError, match="duplicate chart artifact targets"):
        TableExtractionValidator(
            stage_input=stage_input,
            result_dir=tmp_path,
        ).validate(TableExtractionResult(table_extraction_list=[]))
