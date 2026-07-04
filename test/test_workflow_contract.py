"""Tests for cross-project workflow contract metadata."""

import ast
from contextlib import nullcontext
import json
from pathlib import Path
import re

import pytest
import yaml

from brand_size_chart import workflow
from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import BrandInput
from brand_size_chart.model import BrandSizeChart
from brand_size_chart.model import BrandSizeChartMeasurement
from brand_size_chart.model import BrandSizeChartRow
from brand_size_chart.model import CanonicalSelection
from brand_size_chart.model import CanonicalSelectionResult
from brand_size_chart.model import CoverageDecisionResult
from brand_size_chart.model import PromptScope
from brand_size_chart.model import PromptStageInstruction
from brand_size_chart.model import SourceDiscovery
from brand_size_chart.model import SourceDiscoveryResult
from brand_size_chart.model import SourceTypeSummary
from brand_size_chart.model import StageVerification
from brand_size_chart.model import TableExtraction
from brand_size_chart.model import TableExtractionBatchResult
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.stage import semantic
from brand_size_chart.stage.semantic import SemanticStage
from brand_size_chart.stage.workflow_run_prompt_apply import WorkflowRunPromptApplyStage
from workflow_container_runtime.prompt import PromptRenderer as RuntimePromptRenderer

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


def _prompt_template_text_get(template_name: str) -> str:
    """Return one rendered prompt template text.

    Args:
        template_name: Prompt template file name.

    Returns:
        Rendered prompt template text.
    """

    return RuntimePromptRenderer(template_dir=PROJECT_TEMPLATE_DIR).render(
        template_name,
        {
            "artifact_path_list": ["brand_size_chart_audit/brand/defacto/source_type/source/result.json"],
            "attempt_index": 2,
            "draft_result_json_text": '{"status":"success"}',
            "draft_verification_json_text": '{"status":"success"}',
            "feedback_list": ["feedback"],
            "previous_result_json_text": '{"status":"failed"}',
            "prompt_context": (
                "Brand: Defacto\n"
                "Source type: official_brand_size_guide\n"
                "Priority country code: TR\n"
                "Browser evidence write directory: /tmp/evidence\n"
                "Evidence reference directory: .playwright-mcp/current/evidence\n"
                "Verified table summary:\n- women_upper"
            ),
            "shared_instruction": "shared instruction",
            "stage_instruction_text": "- stage instruction",
            "stage_key": template_name.removesuffix(".md.j2"),
            "stage_result_json_text": '{"status":"success"}',
        },
    )


def _runtime_prompt_template_text_get(template_name: str) -> str:
    """Return one rendered runtime prompt template text.

    Args:
        template_name: Runtime prompt template file name.

    Returns:
        Rendered runtime prompt template text.
    """

    return RuntimePromptRenderer().render(
        template_name,
        {
            "workflow_container_name": "workflow-container",
        },
    )


def _prompt_template_tree_text_get() -> str:
    """Return all prompt template source text.

    Returns:
        Concatenated prompt template tree source.
    """
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(Path("brand_size_chart/prompt/template").rglob("*.md.j2"))
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
        layout.brand_coverage_decide_dir(brand_input).as_posix()
        == "/tmp/result/brand_size_chart_audit/brand/defacto/coverage_decide"
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


def test_prompt_text_lives_only_in_template_tree() -> None:
    """Keep static prompt prose in one template tree without root Markdown copies."""

    prompt_root_markdown_path_list = sorted(Path("brand_size_chart/prompt").glob("*.md"))

    assert prompt_root_markdown_path_list == []
    assert Path("brand_size_chart/prompt/template/workflow_run_prompt_apply.md.j2").is_file()
    assert Path("brand_size_chart/prompt/template/source_discover.md.j2").is_file()
    assert Path("brand_size_chart/prompt/template/table_extract.md.j2").is_file()
    assert Path("brand_size_chart/prompt/template/partial/size_group_key_contract.md.j2").is_file()


def test_domain_prompts_do_not_duplicate_runtime_source_access_contract() -> None:
    """Keep generic browser and web-search rules in workflow-container-runtime."""

    source_discover_text = Path("brand_size_chart/prompt/template/source_discover.md.j2").read_text(encoding="utf-8")

    assert "Use Codex internal web search" not in source_discover_text
    assert "Do not open public search-engine result pages" not in source_discover_text
    assert "through the configured browser" not in source_discover_text


def test_generic_runtime_prompt_partials_are_not_local_project_files() -> None:
    """Load generic prompt partials from workflow-container runtime."""

    assert not Path("brand_size_chart/prompt/template/partial/runtime_source_access.md.j2").exists()
    assert not Path("brand_size_chart/prompt/template/partial/artifact_reference_contract.md.j2").exists()
    assert not Path("brand_size_chart/prompt/template/partial/stage_verification_contract.md.j2").exists()
    assert "Use the configured browser" in RuntimePromptRenderer(template_dir=PROJECT_TEMPLATE_DIR).render(
        "runtime/partial/runtime_source_access.md.j2",
        {},
    )


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
            workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.summary_write_step,
            "source_type_summary_write_step",
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
        layout.table_extract_result_path(brand_input, "official_brand_size_guide").relative_to(tmp_path).as_posix()
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
            stage_key="source_discover",
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
            stage_key="brand_result",
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
            stage_key="source_discover",
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "leading or trailing whitespace" in message


def test_artifact_materializer_preserves_external_reference_inside_allowed_root(tmp_path: Path) -> None:
    """Materialize allowed absolute references as result-dir-relative POSIX artifact paths."""
    from brand_size_chart.artifact import ArtifactMaterializer

    result_dir = tmp_path / "result"
    external_root = result_dir / ".tool-output"
    external_file = external_root / "source.json"
    external_file.parent.mkdir(parents=True)
    external_file.write_text("{}\n", encoding="utf-8")
    materializer = ArtifactMaterializer(result_dir=result_dir, allowed_root_list=[external_root])

    assert materializer.reference_list_materialize([str(external_file)]) == [".tool-output/source.json"]


def test_artifact_materializer_resolves_relative_paths_from_result_dir(tmp_path: Path) -> None:
    """Materialize result-dir-relative references without depending on process CWD."""
    from brand_size_chart.artifact import ArtifactMaterializer

    result_dir = tmp_path / "result"
    external_file = result_dir / ".tool-output" / "source.json"
    external_file.parent.mkdir(parents=True)
    external_file.write_text("{}\n", encoding="utf-8")
    materializer = ArtifactMaterializer(result_dir=result_dir, allowed_root_list=[Path(".tool-output")])

    assert materializer.reference_list_materialize([".tool-output/source.json"]) == [".tool-output/source.json"]


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


def test_table_extraction_validator_rejects_source_title_mismatch(tmp_path: Path) -> None:
    """Require extracted table identity to preserve the discovered source title."""
    from brand_size_chart.validator.table_extraction import TableExtractionValidator

    evidence_path = (
        tmp_path / ".playwright-mcp/current/brand_size_chart_audit/brand/defacto/source_type/"
        "official_brand_size_guide/table_extract/evidence/women_upper/table.json"
    )
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}\n", encoding="utf-8")
    source_discovery = SourceDiscovery(
        confidence=1.0,
        country_code_list=["TR"],
        evidence_path_list=[evidence_path.relative_to(tmp_path).as_posix()],
        product_type_hint_list=["upper"],
        size_group_key="women_upper",
        source_priority=600,
        source_title="Kadın Üst Beden Tablosu",
        source_type="official_brand_size_guide",
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )
    table_extraction = TableExtraction(
        applicability_status="priority_country_official",
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
        source_type="official_brand_size_guide",
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )

    try:
        TableExtractionValidator(tmp_path).validate(
            source_discovery_list=[source_discovery],
            table_extraction_batch_result=TableExtractionBatchResult(
                message="browser extraction completed",
                source_type="official_brand_size_guide",
                status="success",
                table_extraction_list=[table_extraction],
            ),
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "table_extraction source_title mismatch" in message
    assert "Kadın Üst Beden Tablosu" in message


def test_table_extraction_validator_rejects_mixed_source_type_batch(tmp_path: Path) -> None:
    """Require one batch extraction to belong to exactly one source type."""
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
        confidence=1.0,
        country_code_list=["TR"],
        evidence_path_list=[],
        size_group_key="women_upper",
        source_priority=600,
        source_title="Women upper",
        source_type="official_brand_size_guide",
        source_url="https://www.defacto.com.tr/size-guide",
    )
    second_discovery = SourceDiscovery(
        confidence=1.0,
        country_code_list=["TR"],
        evidence_path_list=[],
        size_group_key="women_lower",
        source_priority=500,
        source_title="Women lower",
        source_type="official_brand_product_page",
        source_url="https://www.defacto.com.tr/product",
    )
    first_extraction = TableExtraction(
        applicability_status="priority_country_official",
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
        source_type="official_brand_size_guide",
        source_url="https://www.defacto.com.tr/size-guide",
    )
    second_extraction = TableExtraction(
        applicability_status="priority_country_official",
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
        source_url="https://www.defacto.com.tr/product",
    )

    try:
        TableExtractionValidator(tmp_path).validate(
            source_discovery_list=[first_discovery, second_discovery],
            table_extraction_batch_result=TableExtractionBatchResult(
                message="browser extraction completed",
                source_type="official_brand_size_guide",
                status="success",
                table_extraction_list=[first_extraction, second_extraction],
            ),
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "source_type set mismatch" in message
    assert "official_brand_product_page" in message


def test_semantic_stages_live_under_stage_package() -> None:
    """Keep semantic stage lifecycle outside DBOS workflow orchestration."""
    from brand_size_chart.stage.canonical_selection import CanonicalSelectionStage
    from brand_size_chart.stage.coverage_decision import CoverageDecisionStage
    from brand_size_chart.stage.source_discovery import SourceDiscoveryStage
    from brand_size_chart.stage.table_extraction import TableExtractionStage
    from brand_size_chart.stage.workflow_run_prompt_apply import WorkflowRunPromptApplyStage

    assert WorkflowRunPromptApplyStage.__name__ == "WorkflowRunPromptApplyStage"
    assert SourceDiscoveryStage.__name__ == "SourceDiscoveryStage"
    assert TableExtractionStage.__name__ == "TableExtractionStage"
    assert CoverageDecisionStage.__name__ == "CoverageDecisionStage"
    assert CanonicalSelectionStage.__name__ == "CanonicalSelectionStage"


def test_stage_prompt_instruction_fragments_live_under_templates() -> None:
    """Keep long human prompt instructions out of Python stage files."""
    stage_source_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(Path("brand_size_chart/stage").glob("*.py"))
    )
    prompt_text = "\n".join(
        [
            _prompt_template_text_get("source_discover.md.j2"),
            _prompt_template_text_get("table_extract.md.j2"),
        ]
    )
    instruction_fragment_list = [
        "Do not use non-browser loading mechanisms",
        "Extract only the table whose",
    ]

    for instruction_fragment in instruction_fragment_list:
        assert instruction_fragment not in stage_source_text
        assert instruction_fragment in prompt_text


def test_coverage_decision_validation_retries_inside_semantic_stage(tmp_path: Path) -> None:
    """Feed coverage-decision mechanical errors back into the semantic retry loop."""
    from pydantic import BaseModel

    from brand_size_chart.model import CoverageDecision
    from brand_size_chart.stage.coverage_decision import CoverageDecisionStage

    call_list: list[dict[str, object]] = []

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return one mechanically invalid coverage result, then a corrected result.

        Args:
            allow_user_config: Whether Codex browser config is enabled.
            browser_runtime_mcp_url: Browser runtime URL.
            model_class: Expected result model.
            prompt_text: Prompt text with feedback.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake coverage or verification result.
        """

        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = result_dir
        _ = stage_dir
        _ = stage_name
        call_list.append({"model_class": model_class, "prompt_text": prompt_text})
        if model_class is StageVerification:
            return StageVerification(
                artifact_path_list=["brand_size_chart_audit/brand/defacto/coverage_decide/result.json"],
                message="verified",
                stage_key="coverage_decide",
                status="success",
            )
        coverage_call_count = len([call for call in call_list if call["model_class"] is CoverageDecisionResult])
        if coverage_call_count == 1:
            return CoverageDecisionResult(
                coverage_decision_list=[
                    CoverageDecision(is_covered=True, reason="Verified source table exists.", size_group_key="women")
                ],
                message="coverage checked",
                status="success",
                uncovered_product_type_list=["unexpected_product"],
            )

        assert "coverage_decide returned unexpected product types" in prompt_text
        return CoverageDecisionResult(
            coverage_decision_list=[
                CoverageDecision(is_covered=True, reason="Verified source table exists.", size_group_key="women")
            ],
            message="coverage checked",
            status="success",
            uncovered_product_type_list=["women shoes"],
        )

    result = CoverageDecisionStage(
        brand_input=BrandInput(
            parsed_brand_key="defacto",
            parsed_brand_name="Defacto",
            raw_brand_name="Defacto",
            source_line_number=1,
        ),
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR", product_type_request_list=["women shoes"]),
        result_dir=tmp_path,
        source_type="official_brand_size_guide",
        stage_dir=tmp_path / "coverage_decide",
        table_extraction_list=[
            TableExtraction(
                applicability_status="priority_country_official",
                chart=BrandSizeChart(description="Women shoes", row_list=[]),
                size_group_key="women",
                source_title="Women shoes",
                source_type="official_brand_size_guide",
                source_url="https://www.defacto.com.tr/size",
            )
        ],
    ).run()

    coverage_call_list = [call for call in call_list if call["model_class"] is CoverageDecisionResult]
    assert len(coverage_call_list) == 2
    assert result.uncovered_product_type_list == ["women shoes"]


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
    evidence_path = evidence_path / "source_discover" / "evidence" / "source_surface_inventory.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text('{"browsing_error_list": []}', encoding="utf-8")
    artifact_layout = ArtifactLayout(tmp_path)
    source_discover_result = SourceDiscoveryResult(
        discovered_source_list=[
            SourceDiscovery(
                confidence=0.9,
                country_code_list=["TR"],
                evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
                size_group_key="women_upper",
                source_priority=600,
                source_title="Defacto TR size guide",
                source_type="official_brand_size_guide",
                source_url="https://www.defacto.com.tr/statik/beden-rehberi",
            ),
            SourceDiscovery(
                confidence=0.9,
                country_code_list=["MA"],
                evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
                size_group_key="women_bras",
                source_priority=600,
                source_title="Defacto Morocco size guide",
                source_type="official_brand_size_guide",
                source_url="https://www.defacto.com/en-ma/static/size-charts",
            ),
        ],
        message="Found tables.",
        source_type="official_brand_size_guide",
        status="success",
    )

    try:
        SourceDiscoveryValidator(result_dir=tmp_path, stage_dir=evidence_path.parents[1]).validate(
            discovery_result=source_discover_result,
            expected_source_priority=600,
            expected_source_type="official_brand_size_guide",
            prompt_scope=PromptScope(priority_country_code="TR"),
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "non-priority country" in message
    assert "priority_country_code=TR" in message


def test_source_discovery_rejects_missing_inventory_evidence_path(tmp_path: Path) -> None:
    """Require source-surface inventory evidence path references to point to real artifacts."""
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
        / "evidence"
        / "source_surface_inventory.json"
    )
    evidence_path = inventory_path.parent / "opened_page.yml"
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(
        json.dumps(
            {
                "browsing_error_list": [
                    {
                        "error": "blocked page",
                        "url": "https://example.test/blocked",
                    }
                ],
                "rejected_urls": [
                    {
                        "evidence_path_list": [
                            " brand_size_chart_audit/brand/defacto/source_type/"
                            "official_marketplace_product_page/source_discover/evidence/google_blocked.yml"
                        ],
                        "reason": "blocked page",
                        "url": "https://example.test/blocked",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    evidence_path.write_text("{}\n", encoding="utf-8")
    artifact_layout = ArtifactLayout(tmp_path)
    source_discover_result = SourceDiscoveryResult(
        discovered_source_list=[
            SourceDiscovery(
                confidence=0.9,
                country_code_list=["GLOBAL"],
                evidence_path_list=[artifact_layout.artifact_path(evidence_path)],
                size_group_key="women_hats",
                source_priority=300,
                source_title="Marketplace product size chart",
                source_type="official_marketplace_product_page",
                source_url="https://example.test/product",
            ),
        ],
        message="Found tables.",
        browsing_error_list=[
            {
                "error": "blocked page",
                "url": "https://example.test/blocked",
            }
        ],
        source_type="official_marketplace_product_page",
        status="success",
    )

    try:
        SourceDiscoveryValidator(result_dir=tmp_path, stage_dir=inventory_path.parents[1]).validate(
            discovery_result=source_discover_result,
            expected_source_priority=300,
            expected_source_type="official_marketplace_product_page",
            prompt_scope=PromptScope(priority_country_code="TR"),
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "leading or trailing whitespace" in message


def test_source_discovery_rejects_missing_result_browsing_error(tmp_path: Path) -> None:
    """Expose URL-level browsing failures in source discovery result JSON."""
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
        / "evidence"
        / "source_surface_inventory.json"
    )
    inventory_path.parent.mkdir(parents=True)
    inventory_path.write_text(
        json.dumps(
            {
                "browsing_error_list": [
                    {
                        "error": "Google displayed reCAPTCHA.",
                        "url": "https://www.google.com/search?q=Defacto",
                    }
                ],
                "rejected_urls": [
                    {
                        "evidence_path_list": [inventory_path.relative_to(tmp_path).as_posix()],
                        "reason": "Google displayed reCAPTCHA.",
                        "url": "https://www.google.com/search?q=Defacto",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    artifact_layout = ArtifactLayout(tmp_path)
    source_discover_result = SourceDiscoveryResult(
        discovered_source_list=[
            SourceDiscovery(
                confidence=0.9,
                country_code_list=["TR"],
                evidence_path_list=[artifact_layout.artifact_path(inventory_path)],
                size_group_key="women_upper",
                source_priority=600,
                source_title="Defacto TR size guide",
                source_type="official_brand_size_guide",
                source_url="https://www.defacto.com.tr/statik/beden-rehberi",
            ),
        ],
        message="Found tables.",
        source_type="official_brand_size_guide",
        status="success",
    )

    try:
        SourceDiscoveryValidator(result_dir=tmp_path, stage_dir=inventory_path.parents[1]).validate(
            discovery_result=source_discover_result,
            expected_source_priority=600,
            expected_source_type="official_brand_size_guide",
            prompt_scope=PromptScope(priority_country_code="TR"),
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "browsing_error_list mismatch" in message
    assert "https://www.google.com/search?q=Defacto" in message


def test_table_extraction_rejects_non_priority_applicability_for_priority_country_source(tmp_path: Path) -> None:
    """Keep table applicability aligned with the verified source market."""
    from brand_size_chart.validator.table_extraction import TableExtractionValidator

    evidence_path = tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "evidence.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}", encoding="utf-8")
    source_discovery = SourceDiscovery(
        confidence=0.95,
        country_code_list=["TR"],
        size_group_key="boys_3_8_year_clothing",
        source_priority=600,
        source_title="DeFacto Beden Rehberi",
        source_type="official_brand_size_guide",
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )
    table_extraction = TableExtraction(
        applicability_status="official_global",
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
        source_type="official_brand_size_guide",
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )

    try:
        TableExtractionValidator(tmp_path).validate(
            source_discovery_list=[source_discovery],
            table_extraction_batch_result=TableExtractionBatchResult(
                message="browser extraction completed",
                source_type="official_brand_size_guide",
                status="success",
                table_extraction_list=[table_extraction],
            ),
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "applicability_status" in message
    assert "priority_country_official" in message


def test_table_extraction_rejects_missing_size_label_measurement(tmp_path: Path) -> None:
    """Preserve the source row size label as a unit=size measurement."""
    from brand_size_chart.validator.table_extraction import TableExtractionValidator

    evidence_path = tmp_path / "brand_size_chart_audit" / "brand" / "defacto" / "evidence.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}", encoding="utf-8")
    source_discovery = SourceDiscovery(
        confidence=0.95,
        country_code_list=["TR"],
        size_group_key="boys_3_8_year_clothing",
        source_priority=600,
        source_title="DeFacto Beden Rehberi",
        source_type="official_brand_size_guide",
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )
    table_extraction = TableExtraction(
        applicability_status="priority_country_official",
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
        source_type="official_brand_size_guide",
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )

    try:
        TableExtractionValidator(tmp_path).validate(
            source_discovery_list=[source_discovery],
            table_extraction_batch_result=TableExtractionBatchResult(
                message="browser extraction completed",
                source_type="official_brand_size_guide",
                status="success",
                table_extraction_list=[table_extraction],
            ),
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "unit=size" in message
    assert "size_label" in message


def test_canonical_selection_rejects_missing_verified_tables() -> None:
    """Do not let semantic canonical selection drop verified canonical tables."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator

    table_extraction = TableExtraction(
        applicability_status="priority_country_official",
        chart=BrandSizeChart(description="Women upper", row_list=[]),
        size_group_key="women_upper",
        source_title="Women upper",
        source_type="official_brand_size_guide",
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )
    canonical_selection_result = CanonicalSelectionResult(
        canonical_selection_list=[],
        error_list=["No evidence files were supplied."],
        message="No referenced evidence files were supplied to read.",
        status="failed",
    )

    try:
        CanonicalSelectionValidator().validate(
            canonical_selection_result=canonical_selection_result,
            table_extraction_list=[table_extraction],
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "canonical_select missing eligible size_group_key" in message
    assert "women_upper" in message


def test_canonical_selection_rejects_non_extracted_selection() -> None:
    """Do not allow canonical selection to invent a source absent from verified extractions."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator

    table_extraction = TableExtraction(
        applicability_status="priority_country_official",
        chart=BrandSizeChart(description="Women clothing", row_list=[]),
        size_group_key="women_clothing",
        source_title="Women clothing",
        source_type="official_marketplace_store",
        source_url="https://marketplace.example/defacto",
    )
    canonical_selection_result = CanonicalSelectionResult(
        canonical_selection_list=[
            CanonicalSelection(
                selected_source_priority=500,
                selected_source_type="official_brand_product_page",
                selected_source_url="https://brand.example/product",
                size_group_key="women_clothing",
            )
        ],
        message="Canonical tables selected.",
        status="success",
    )

    try:
        CanonicalSelectionValidator().validate(
            canonical_selection_result=canonical_selection_result,
            table_extraction_list=[table_extraction],
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "canonical_select missing table extraction" in message
    assert "official_brand_product_page" in message


def test_canonical_selection_rejects_lower_priority_duplicate_source() -> None:
    """Prefer the highest-priority verified source for a duplicate size group."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator

    lower_priority_table = TableExtraction(
        applicability_status="priority_country_official",
        chart=BrandSizeChart(description="Marketplace women shoes", row_list=[]),
        size_group_key="women_shoes",
        source_title="Marketplace women shoes",
        source_type="official_marketplace_store",
        source_url="https://marketplace.example/defacto",
    )
    higher_priority_table = TableExtraction(
        applicability_status="priority_country_official",
        chart=BrandSizeChart(description="Brand women shoes", row_list=[]),
        size_group_key="women_shoes",
        source_title="Brand women shoes",
        source_type="official_brand_product_page",
        source_url="https://brand.example/shoes",
    )
    canonical_selection_result = CanonicalSelectionResult(
        canonical_selection_list=[
            CanonicalSelection(
                selected_source_priority=200,
                selected_source_type="official_marketplace_store",
                selected_source_url="https://marketplace.example/defacto",
                size_group_key="women_shoes",
            )
        ],
        message="Canonical tables selected.",
        status="success",
    )

    try:
        CanonicalSelectionValidator().validate(
            canonical_selection_result=canonical_selection_result,
            table_extraction_list=[lower_priority_table, higher_priority_table],
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "canonical_select selected lower priority" in message
    assert "women_shoes" in message


def test_canonical_selection_validator_accepts_selected_duplicate_source_type() -> None:
    """Validate the selected table, not the last table with the same size_group_key."""
    from brand_size_chart.validator.canonical_selection import CanonicalSelectionValidator

    lower_priority_table = TableExtraction(
        applicability_status="priority_country_official",
        chart=BrandSizeChart(description="Seller boys clothing", row_list=[]),
        size_group_key="boys_3_8_year_clothing",
        source_title="Seller boys clothing",
        source_type="official_seller_size_guide",
        source_url="https://seller.example/size-guide",
    )
    higher_priority_table = TableExtraction(
        applicability_status="priority_country_official",
        chart=BrandSizeChart(description="Brand boys clothing", row_list=[]),
        size_group_key="boys_3_8_year_clothing",
        source_title="Brand boys clothing",
        source_type="official_brand_size_guide",
        source_url="https://brand.example/beden-rehberi",
    )
    canonical_selection_result = CanonicalSelectionResult(
        canonical_selection_list=[
            CanonicalSelection(
                selected_source_priority=600,
                selected_source_type="official_brand_size_guide",
                selected_source_url="https://brand.example/beden-rehberi",
                size_group_key="boys_3_8_year_clothing",
            )
        ],
        message="Canonical tables selected.",
        status="success",
    )

    CanonicalSelectionValidator().validate(
        canonical_selection_result=canonical_selection_result,
        table_extraction_list=[higher_priority_table, lower_priority_table],
    )


def test_brand_selection_writes_selected_duplicate_table(monkeypatch: object, tmp_path: Path) -> None:
    """Write the canonical table selected by full source identity when size_group_key duplicates exist."""
    from pydantic import BaseModel

    from brand_size_chart.workflow import brand as brand_workflow

    brand_input = BrandInput(
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        raw_brand_name="Defacto",
        source_line_number=1,
    )
    selected_table = TableExtraction(
        applicability_status="priority_country_official",
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
        source_type="official_brand_size_guide",
        source_url="https://brand.example/beden-rehberi",
    )
    duplicate_table = TableExtraction(
        applicability_status="priority_country_official",
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
        source_type="official_seller_size_guide",
        source_url="https://seller.example/size-guide",
    )

    class FakeCoverageDecisionStage:
        """Return final coverage without using Codex."""

        def __init__(self, **kwargs: object) -> None:
            """Accept workflow construction kwargs.

            Args:
                kwargs: Ignored workflow inputs.
            """

            _ = kwargs

        def run(self) -> CoverageDecisionResult:
            """Return a successful coverage result.

            Returns:
                Coverage decision result.
            """

            return CoverageDecisionResult(
                coverage_decision_list=[],
                message="coverage checked",
                status="success",
            )

    class FakeCanonicalSelectionStage:
        """Return a canonical selection for the higher-priority duplicate table."""

        def __init__(self, **kwargs: object) -> None:
            """Accept workflow construction kwargs.

            Args:
                kwargs: Ignored workflow inputs.
            """

            _ = kwargs

        def run(self) -> CanonicalSelectionResult:
            """Return selected canonical table identity.

            Returns:
                Canonical selection result.
            """

            return CanonicalSelectionResult(
                canonical_selection_list=[
                    CanonicalSelection(
                        selected_source_priority=600,
                        selected_source_type="official_brand_size_guide",
                        selected_source_url="https://brand.example/beden-rehberi",
                        size_group_key="boys_3_8_year_clothing",
                    )
                ],
                message="Canonical tables selected.",
                status="success",
            )

    monkeypatch.setattr(brand_workflow, "CoverageDecisionStage", FakeCoverageDecisionStage)
    monkeypatch.setattr(brand_workflow, "CanonicalSelectionStage", FakeCanonicalSelectionStage)

    result = brand_workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW.selection_write_step.__wrapped__(
        brand_workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW,
        brand_input.model_dump(mode="json"),
        PromptScope().model_dump(mode="json"),
        str(tmp_path),
        [selected_table.model_dump(mode="json"), duplicate_table.model_dump(mode="json")],
        [
            SourceTypeSummary(
                source_priority=600,
                source_type="official_brand_size_guide",
                state="passed",
            ).model_dump(mode="json")
        ],
    )

    chart_path = tmp_path / "brand_size_chart/brand/defacto/size_chart/boys_3_8_year_clothing.json"
    chart_payload = json.loads(chart_path.read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert chart_payload["description"] == "Selected brand table"
    assert chart_payload["row_list"][0]["size_label"] == "S"


def test_semantic_stage_has_no_prompt_function_proxy() -> None:
    """Keep stage prompt generation owned by `SemanticStage`."""

    assert not hasattr(semantic, "stage_prompt_text_get")


def test_semantic_stage_prompt_text_includes_draft_result(tmp_path: Path) -> None:
    """Give semantic stages their deterministic draft result as structured input."""
    captured_prompt_list: list[str] = []

    def fake_codex_stage_run(
        *,
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[PromptScope] | type[StageVerification],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> PromptScope | StageVerification:
        """Capture prompt text and return schema-valid fake stage outputs.

        Args:
            allow_user_config: Whether browser config is enabled.
            browser_runtime_mcp_url: Browser MCP URL.
            model_class: Expected output model.
            prompt_text: Rendered prompt text.
            result_dir: Result root.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake stage result.
        """

        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = result_dir
        _ = stage_dir
        captured_prompt_list.append(prompt_text)
        if model_class is StageVerification:
            return StageVerification(message="verified", stage_key=stage_name, status="success")
        return PromptScope(priority_country_code="TR")

    SemanticStage(
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_scope=PromptScope(priority_country_code="TR"),
        result_dir=tmp_path,
        stage_dir=tmp_path / "stage",
        stage_key="workflow_run_prompt_apply",
    ).run(
        draft_result=PromptScope(priority_country_code="TR"),
        model_class=PromptScope,
        prompt_context="Brand: Defacto",
    )

    assert "Draft stage result JSON:" in captured_prompt_list[0]
    assert '"priority_country_code": "TR"' in captured_prompt_list[0]


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
            "coverage_decision_list": [
                {
                    "is_covered": True,
                    "missing_size_list": [],
                    "reason": "covered",
                    "size_group_key": "women_clothing",
                }
            ],
            "message": "covered",
            "status": "success",
            "uncovered_product_type_list": [],
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
            {
                "source_type_summary": {
                    "blocker_list": [],
                    "conflict_list": [],
                    "evidence_manifest_path_list": [],
                    "source_priority": SOURCE_TYPE_REGISTRY.source_type_priority_get(source_type),
                    "source_type": source_type,
                    "state": "passed",
                    "table_result_path_by_size_group_key_map": {},
                    "verified_size_group_key_list": ["women_clothing"],
                    "warning_list": [],
                },
                "table_extraction_list": [{"size_group_key": "women_clothing", "source_type": source_type}],
            }
        )

    def fake_brand_selection_write_step(
        brand_input_payload: dict[str, object],
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        table_extraction_payload_list: list[dict[str, object]],
        source_type_summary_payload_list: list[dict[str, object]],
    ) -> dict[str, object]:
        """Return source-type execution summary.

        Args:
            brand_input_payload: Serialized brand input.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Result root.
            table_extraction_payload_list: Extracted table payloads.
            source_type_summary_payload_list: Source-type summaries.

        Returns:
            Minimal fake brand result.
        """
        _ = brand_input_payload
        _ = prompt_scope_payload
        _ = result_dir
        _ = table_extraction_payload_list
        _ = source_type_summary_payload_list
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
            coverage_decision_list=[],
            message="coverage",
            status="success",
            uncovered_product_type_list=[] if source_type == "official_brand_product_page" else ["women dresses"],
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
                {
                    "source_type_summary": SourceTypeSummary(
                        blocker_list=["no seller guide"],
                        source_priority=SOURCE_TYPE_REGISTRY.source_type_priority_get(source_type),
                        source_type=source_type,
                        state="failed",
                    ).model_dump(mode="json"),
                    "table_extraction_list": [],
                }
            )
        return FakeHandle(
            {
                "source_type_summary": SourceTypeSummary(
                    source_priority=SOURCE_TYPE_REGISTRY.source_type_priority_get(source_type),
                    source_type=source_type,
                    state="passed",
                    verified_size_group_key_list=["women_clothing"],
                ).model_dump(mode="json"),
                "table_extraction_list": [{"size_group_key": "women_clothing", "source_type": source_type}],
            }
        )

    def fake_brand_selection_write_step(
        brand_input_payload: dict[str, object],
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        table_extraction_payload_list: list[dict[str, object]],
        source_type_summary_payload_list: list[dict[str, object]],
    ) -> dict[str, object]:
        """Return the coverage call list.

        Args:
            brand_input_payload: Serialized brand input.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Result root.
            table_extraction_payload_list: Extracted table payloads.
            source_type_summary_payload_list: Source-type summaries.

        Returns:
            Coverage source type list.
        """
        _ = brand_input_payload
        _ = prompt_scope_payload
        _ = result_dir
        _ = table_extraction_payload_list
        _ = source_type_summary_payload_list
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


def test_source_type_summary_records_failed_source_without_discovery_artifact(tmp_path: Path) -> None:
    """Write failed source-type summaries without requiring a successful discovery artifact."""
    summary_payload = workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.summary_write_step.__wrapped__(
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

    assert summary_payload["blocker_list"] == ["RuntimeError: source discovery failed"]
    assert summary_payload["evidence_manifest_path_list"] == []
    assert summary_payload["source_type"] == "official_brand_size_guide"
    assert summary_payload["state"] == "failed"


def test_source_type_summary_records_no_table_discovery_as_skipped_warning(tmp_path: Path) -> None:
    """Record evidence-backed no-table source discovery as skipped instead of failed."""
    summary_payload = workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.summary_write_step.__wrapped__(
        workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW,
        {
            "parsed_brand_key": "defacto",
            "parsed_brand_name": "Defacto",
            "raw_brand_name": "Defacto",
            "source_line_number": 1,
        },
        str(tmp_path),
        "official_marketplace_store",
        [],
        [],
        ["No concrete browser-visible size-chart table was returned."],
    )

    assert summary_payload["blocker_list"] == []
    assert summary_payload["state"] == "skipped"
    assert summary_payload["warning_list"] == ["No concrete browser-visible size-chart table was returned."]


def test_source_type_summary_points_to_table_extract_chart_artifacts(tmp_path: Path) -> None:
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
    table_extraction = TableExtraction(
        applicability_status="priority_country_official",
        chart=chart,
        size_group_key="women_upper",
        source_title="Women upper",
        source_type=source_type,
        source_url="https://www.defacto.com.tr/statik/beden-rehberi",
    )

    summary_payload = workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.summary_write_step.__wrapped__(
        workflow.BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW,
        brand_input.model_dump(mode="json"),
        str(tmp_path),
        source_type,
        [table_extraction.model_dump(mode="json")],
        [],
        [],
    )

    assert summary_payload["table_result_path_by_size_group_key_map"] == {
        "women_upper": (
            "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/"
            "table_extract/chart/women_upper.json"
        )
    }
    assert summary_payload["verified_size_group_key_list"] == ["women_upper"]


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
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[object],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> object:
        """Return one invalid prompt scope, then a corrected prompt scope.

        Args:
            allow_user_config: Whether Codex browser config is enabled.
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
        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = result_dir
        _ = stage_dir
        _ = stage_name
        if model_class is StageVerification:
            return StageVerification(
                artifact_path_list=["brand_size_chart_audit/run/workflow_run_prompt_apply/result.json"],
                message="verified",
                stage_key="workflow_run_prompt_apply",
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

    prompt_scope = WorkflowRunPromptApplyStage(
        codex_stage_run_callable=fake_codex_stage_run,
        result_dir=tmp_path,
        workflow_run_prompt="Priority country TR. Search all supported source types. Product types: socks.",
    ).run()

    assert prompt_scope.product_type_request_list == ["socks"]
    assert prompt_scope.source_type_allow_list == []
    assert prompt_scope.shared_instruction == "Search all supported source types."
    assert prompt_scope_call_count == 3


def test_source_discovery_prompt_makes_table_forms_universal() -> None:
    """Search every source type for size charts in any browser-visible form."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2").lower()

    assert "html table" in source_discover_template
    assert "modal" in source_discover_template
    assert "widget" in source_discover_template
    assert "pdf" in source_discover_template
    assert "image" in source_discover_template
    assert "help" in source_discover_template
    assert "faq" in source_discover_template
    assert "q&a" in source_discover_template
    assert "for `official_brand_size_guide`" not in source_discover_template


def test_source_discovery_prompt_uses_split_evidence_paths() -> None:
    """Keep source discovery prompt explicit about filesystem writes and returned references."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")

    assert "under the browser evidence write directory" in source_discover_template
    assert "result-dir-relative paths under the evidence reference directory" in source_discover_template
    assert "under the evidence directory" not in source_discover_template


def test_size_group_key_contract_is_prompt_and_design_owned() -> None:
    """Keep size-group naming as a semantic prompt/design contract."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")
    design_text = Path("doc/design/brand-size-chart.md").read_text(encoding="utf-8")
    workflow_text = _workflow_package_source_text_get()

    assert "{sex}_{product_group_or_type}" in source_discover_template
    assert "{sex}_{sex_suffix}_{product_group_or_type}" in source_discover_template
    assert "{min}_{max}_{month|year}" in source_discover_template
    assert "Approved non-age `sex_suffix` terms" in source_discover_template
    assert "Do not list or invent concrete approved age intervals" in source_discover_template
    assert "child_3_8" not in source_discover_template
    assert "youth_8_14" not in source_discover_template
    assert "child_3_8" not in design_text
    assert "youth_8_14" not in design_text
    assert "Never use `size_chart`" in source_discover_template
    assert "Use `lower` for lower-body clothing tables" in source_discover_template
    assert "`pants_skirts`" not in source_discover_template
    assert "`pants_skirts`" not in design_text
    assert "Semantic verification must reject alternative names" in design_text
    assert "women_size_chart" not in workflow_text
    assert "men_shoes_size_chart" not in workflow_text


def test_source_discovery_checks_official_host_variants() -> None:
    """Search all browser-visible official host variants before failing source discovery."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")

    assert "official host variants" in source_discover_template
    assert "country-code " in source_discover_template
    assert "brand domains" in source_discover_template
    assert "stop after one official domain variant fails" in source_discover_template


def test_source_discovery_searches_localized_size_terms_without_route_templates() -> None:
    """Find official size guides through localized browser search rather than hardcoded URL guesses."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")

    assert "browser-visible language and market" in source_discover_template
    assert "localized size-chart term searches" in source_discover_template
    assert "derive localized size-chart search-term families" in source_discover_template
    assert "URL templates" in source_discover_template
    assert "beden rehberi" not in source_discover_template
    assert "beden tablosu" not in source_discover_template
    assert "/statik/beden-rehberi" not in source_discover_template


def test_table_extraction_preserves_size_system_columns() -> None:
    """Represent size-system columns with an explicit non-empty unit."""
    table_extract_template = _prompt_template_text_get("table_extract.md.j2")

    assert "For size-system " in table_extract_template
    assert "use unit='size'" in table_extract_template
    assert "Treat this row.size_label measurement as an atomic label" in table_extract_template
    assert "do not parse or split row labels" in table_extract_template


def test_table_extraction_keeps_metadata_out_of_chart_artifact() -> None:
    """Keep chart artifact schema separate from extraction metadata."""
    table_extract_template = _prompt_template_text_get("table_extract.md.j2")

    assert "A BrandSizeChart artifact must contain only description and row_list" in table_extract_template
    assert "metadata belong only in the structured TableExtractionArtifactBatchResult" in table_extract_template


def test_browser_stage_prompts_forbid_local_artifact_browser_access() -> None:
    """Keep local artifact reads and non-evidence writes outside the browser context."""
    browser_stage_text = "\n".join(
        [
            _runtime_prompt_template_text_get("system/codex_browser_stage.md.j2"),
            _prompt_template_text_get("source_discover.md.j2"),
            _prompt_template_text_get("source_discover_verify.md.j2"),
            _prompt_template_text_get("table_extract.md.j2"),
            _prompt_template_text_get("table_extract_verify.md.j2"),
        ]
    )

    assert "Do not open local result artifacts through browser tools" in browser_stage_text
    assert "file://, localhost, or 127.0.0.1" in browser_stage_text
    assert "Read local artifact files through normal filesystem access" in browser_stage_text
    assert "Browser tools may write only evidence artifacts" in browser_stage_text
    assert "Do not use browser page context to write chart artifacts" in browser_stage_text
    assert "Do not use jq with guessed JSON paths" in browser_stage_text
    assert "Do not use browser_run_code_unsafe" in browser_stage_text
    assert "Use browser_evaluate with pure browser JavaScript" in browser_stage_text
    assert "must not use Node.js APIs" in browser_stage_text
    assert "return serializable data" in browser_stage_text


def test_browser_stage_prompts_require_robust_browser_interactions() -> None:
    """Keep browser stages from repeating recoverable selector and overlay failures."""
    browser_stage_text = "\n".join(
        [
            _runtime_prompt_template_text_get("system/codex_browser_stage.md.j2"),
            _prompt_template_text_get("source_discover.md.j2"),
            _prompt_template_text_get("table_extract.md.j2"),
        ]
    )

    assert "overlays that intercept pointer events" in browser_stage_text
    assert "use the browser snapshot to choose a scoped unique target" in browser_stage_text
    assert "Retry transient browser navigation failures such as ERR_NETWORK_CHANGED" in browser_stage_text


def test_verification_prompts_forbid_brittle_local_json_scripts() -> None:
    """Keep semantic verifier helper scripts from failing on unrelated JSON artifact shapes."""
    verification_text = "\n".join(
        [
            _runtime_prompt_template_text_get("system/codex_browser_stage.md.j2"),
            _runtime_prompt_template_text_get("system/codex_stage.md.j2"),
            _prompt_template_text_get("source_discover_verify.md.j2"),
            _prompt_template_text_get("table_extract_verify.md.j2"),
        ]
    )

    assert "validate each parsed JSON value shape before field access" in verification_text
    assert "skip unrelated JSON artifact shapes" in verification_text
    assert "Do not use brittle glob scripts over heterogeneous JSON artifacts" in verification_text


def test_table_extraction_preserves_physical_units_and_omits_blank_cells() -> None:
    """Keep physical measurement units and avoid empty measurement values."""
    table_extract_template = _prompt_template_text_get("table_extract.md.j2")

    assert "Do not emit measurement entries for blank source cells" in table_extract_template
    assert "must keep their physical source unit" in table_extract_template


def test_coverage_decision_prompt_receives_verified_table_summary() -> None:
    """Prevent coverage decision from ignoring verified tables as missing evidence."""
    coverage_decide_template = _prompt_template_text_get("coverage_decide.md.j2")

    assert "Verified table summary is supplied below as stage input" in coverage_decide_template
    assert "do not report missing evidence when" in coverage_decide_template
    assert "Refine the draft coverage decision from these verified tables" in coverage_decide_template


def test_source_discovery_prompt_preserves_partial_candidates() -> None:
    """Keep evidence-backed candidates successful even when requested product-type coverage is incomplete."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")

    assert "If at least one concrete table candidate is evidence-backed, return status='success'" in (
        source_discover_template
    )
    assert "missing requested product types in error_list" in source_discover_template


def test_source_discovery_product_types_do_not_filter_tables() -> None:
    """Keep full source-surface table discovery separate from requested product-type coverage."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")
    source_discover_verify_template = _prompt_template_text_get("source_discover_verify.md.j2")
    design_text = Path("doc/design/brand-size-chart.md").read_text(encoding="utf-8")

    expected_text = "Requested product types are coverage targets only"
    assert expected_text in source_discover_template
    assert expected_text in source_discover_verify_template
    assert "`product_type_request_list` defines coverage targets" in design_text
    assert "must not filter `source_discover` candidates" in design_text


def test_source_discovery_requires_current_table_specific_inventory() -> None:
    """Require table-specific current evidence instead of vague prior-evidence notes."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")
    source_discover_verify_template = _prompt_template_text_get("source_discover_verify.md.j2")

    assert "every visible table group and subtable" in source_discover_template
    assert "prior evidence" in source_discover_template
    assert "current evidence_path_list entry" in source_discover_verify_template
    assert "A note such as prior evidence" in source_discover_verify_template


def test_source_discovery_returns_unique_size_group_key_candidates() -> None:
    """Keep duplicate locale tables as evidence instead of duplicate source candidates."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")
    source_discover_verify_template = _prompt_template_text_get("source_discover_verify.md.j2")
    design_text = Path("doc/design/brand-size-chart.md").read_text(encoding="utf-8")

    assert "return at most one discovered_source_list item for one size_group_key" in source_discover_template
    assert "must not require a second discovered_source_list item" in source_discover_verify_template
    assert "return at most one discovered_source_list" in source_discover_template
    assert "item for one size_group_key" in source_discover_template
    assert "one `size_group_key` may appear at most once in `discovered_source_list`" in design_text


def test_source_discovery_locale_policy_is_priority_global_europe_without_vague_candidate_wording() -> None:
    """Use one explicit country-selection ladder instead of vague other-locale candidate rules."""
    apply_prompt = _prompt_template_text_get("workflow_run_prompt_apply.md.j2")
    source_discover_stage_text = Path("brand_size_chart/stage/source_discovery.py").read_text(encoding="utf-8")
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")
    source_discover_verify_template = _prompt_template_text_get("source_discover_verify.md.j2")
    design_text = Path("doc/design/brand-size-chart.md").read_text(encoding="utf-8")
    combined_text = "\n".join([apply_prompt, source_discover_template, source_discover_verify_template, design_text])

    assert "`priority_country_code`" in apply_prompt
    assert "Priority country code:" in source_discover_stage_text
    assert "priority country tables exist" in source_discover_template
    assert "global tables" in source_discover_template
    assert "European country tables" in source_discover_template
    assert "priority country tables exist" in source_discover_verify_template
    assert "`priority_country_code` defines the market priority" in design_text
    for forbidden_text in ["comparison/" + "evidence/" + "blocker", "other " + "locales"]:
        assert forbidden_text not in combined_text


def test_priority_country_is_not_hardcoded_in_prompts_or_design() -> None:
    """Keep concrete priority market selection only in the workflow-run prompt."""
    prompt_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(Path("brand_size_chart/prompt").rglob("*.md*"))
    )
    design_text = Path("doc/design/brand-size-chart.md").read_text(encoding="utf-8")
    checked_text = "\n".join([prompt_text, design_text])

    assert not re.search(r"\bTR\b", checked_text)
    for forbidden_text in ["Turkey", "Turkiye", "Türkiye", "Турция", "Turkish", "beden rehberi", "beden tablosu"]:
        assert forbidden_text not in checked_text


def test_source_discovery_prompt_requires_canonical_inventory_on_retry() -> None:
    """Require retry attempts to update the canonical source-surface inventory."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")

    assert "First build one canonical" in source_discover_template
    assert "source_surface_inventory.json" in source_discover_template
    assert "browser-backed source-surface inventory artifact" in source_discover_template
    assert "attempt-only inventory artifacts are allowed only as extra" in source_discover_template
    assert "must be copied from an actually saved artifact path" in source_discover_template
    assert "must not contain leading or trailing whitespace" in source_discover_template


def test_source_discovery_prompt_requires_market_localized_term_families() -> None:
    """Require all local size-guide/search-term families before an absence result."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")
    source_discover_verify_template = _prompt_template_text_get("source_discover_verify.md.j2")

    expected_text = "derive localized size-chart search-term families"
    assert expected_text in source_discover_template
    assert expected_text in source_discover_verify_template


def test_source_discovery_candidate_urls_exclude_helper_surfaces() -> None:
    """Keep sitemap and navigation helper surfaces out of concrete candidate URLs."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")

    assert "candidate_urls must contain only concrete source candidates" in source_discover_template
    assert "helper surfaces are discovery surfaces, not candidate URLs" in source_discover_template


def test_source_discovery_candidate_urls_exclude_broad_product_lists() -> None:
    """Keep broad search-result product inventories separate from selected source candidates."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")

    assert "broad search-result or category product URL inventories" in source_discover_template
    assert "search_result_url_list" in source_discover_template


def test_source_discovery_prompt_closes_selected_source_boundary_urls() -> None:
    """Require selected seller/store/product URL closure without exhaustive URL crawling."""
    source_discover_template = _prompt_template_text_get("source_discover.md.j2")
    source_discover_verify_template = _prompt_template_text_get("source_discover_verify.md.j2")

    assert "Do not exhaustively open every similar product URL" in source_discover_template
    assert "Every concrete URL selected as a possible source boundary" in source_discover_template
    assert "selected as a possible seller, store, product, or size-guide boundary" in source_discover_verify_template
    assert "Broad unselected search_result_url_list" in source_discover_verify_template


def test_source_discovery_verification_preserves_partial_candidates() -> None:
    """Prevent verification feedback from converting evidence-backed candidates into failed discovery."""
    source_discover_verify_template = _prompt_template_text_get("source_discover_verify.md.j2")

    assert "Do not require status='failed' only because requested product-type coverage is incomplete" in (
        source_discover_verify_template
    )
    assert "failed only when no concrete acceptable candidate remains" in source_discover_verify_template


def test_source_discovery_verification_uses_bounded_completeness() -> None:
    """Do not require unbounded product URL enumeration after bounded inventory is complete."""
    source_discover_verify_template = _prompt_template_text_get("source_discover_verify.md.j2")

    assert "verify source-type completeness inside the bounded source surface" in source_discover_verify_template
    assert "canonical inventory evidence is missing or stale" in source_discover_verify_template
    assert "unbounded search evidence contains additional similar product URLs" in source_discover_verify_template


def test_verification_prompt_rejects_stale_feedback() -> None:
    """Verify only the current stage result and current artifacts."""
    source_discover_verify_template = _prompt_template_text_get("source_discover_verify.md.j2")

    assert "Feedback from previous attempts is not evidence" in source_discover_verify_template
    assert "A URL already present in `opened_urls` is tested" in source_discover_verify_template
    assert "navigation, search, home, sitemap, FAQ, or help URL" in source_discover_verify_template
    assert "Do not fail `source_discover` solely because one helper URL" in source_discover_verify_template


def test_verification_prompt_rejects_stale_hidden_row_errors() -> None:
    """Do not fail table extraction for hidden rows already omitted from the current chart artifact."""
    table_extract_verify_template = _prompt_template_text_get("table_extract_verify.md.j2")

    assert "hidden or non-rendered rows" in table_extract_verify_template
    assert "current chart artifact already omits them" in table_extract_verify_template
    assert "quote the exact current extracted row" in table_extract_verify_template
