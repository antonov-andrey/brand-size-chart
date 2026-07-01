"""Tests for cross-project workflow contract metadata."""

from contextlib import nullcontext
from pathlib import Path

import pytest
import yaml

from brand_size_chart import source_type as source_type_surface
from brand_size_chart import workflow
from brand_size_chart.model import BrandInput
from brand_size_chart.model import BrandSizeChart
from brand_size_chart.model import CanonicalSelectionResult
from brand_size_chart.model import CoverageDecisionResult
from brand_size_chart.model import PromptScope
from brand_size_chart.model import PromptStageInstruction
from brand_size_chart.model import SourceDiscovery
from brand_size_chart.model import SourceDiscoveryResult
from brand_size_chart.model import StageVerification
from brand_size_chart.model import TableExtraction
from brand_size_chart.source_type import (
    PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET,
    SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP,
    SOURCE_TYPE_PRIORITY_BY_KEY_MAP,
)


def _workflow_package_source_text_get() -> str:
    """Return the combined workflow package source text for source-shape contract tests.

    Returns:
        Concatenated workflow package source.
    """
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(Path("brand_size_chart/workflow").glob("*.py"))
    )


def test_model_is_package_not_monolithic_module() -> None:
    """Replace the broad model module with focused model package modules."""
    assert Path("brand_size_chart/model.py").exists() is False
    assert Path("brand_size_chart/model/__init__.py").exists()
    assert Path("brand_size_chart/model/schema_registry.py").exists()


def test_workflow_is_package_not_monolithic_module() -> None:
    """Replace the broad workflow module with workflow owner package modules."""
    assert Path("brand_size_chart/workflow.py").exists() is False
    assert Path("brand_size_chart/workflow/__init__.py").exists()
    assert Path("brand_size_chart/workflow/root.py").exists()


def test_dbos_workflow_classes_are_class_owned() -> None:
    """Ensure DBOS workflows are owned by class instance methods."""
    from brand_size_chart.workflow.brand import BrandSizeChartBrandWorkflow
    from brand_size_chart.workflow.root import BrandSizeChartRunWorkflow
    from brand_size_chart.workflow.source_type import BrandSizeChartSourceTypeWorkflow
    from brand_size_chart.workflow.table import BrandSizeChartTableWorkflow

    assert BrandSizeChartRunWorkflow.__name__ == "BrandSizeChartRunWorkflow"
    assert BrandSizeChartBrandWorkflow.__name__ == "BrandSizeChartBrandWorkflow"
    assert BrandSizeChartSourceTypeWorkflow.__name__ == "BrandSizeChartSourceTypeWorkflow"
    assert BrandSizeChartTableWorkflow.__name__ == "BrandSizeChartTableWorkflow"


def test_codex_stage_py_is_compatibility_surface_only() -> None:
    """Move Codex subprocess mechanics into the codex package."""
    codex_stage_source = Path("brand_size_chart/codex_stage.py").read_text(encoding="utf-8")

    assert "subprocess.Popen" not in codex_stage_source
    assert "class CodexStageRunner" not in codex_stage_source
    assert "from brand_size_chart.codex.runner import" in codex_stage_source


def test_source_type_py_is_compatibility_surface_only() -> None:
    """Move source type registry ownership into source package."""
    source_type_source = Path("brand_size_chart/source_type.py").read_text(encoding="utf-8")

    assert "SOURCE_TYPE_LIST" not in source_type_source
    assert "from brand_size_chart.source.source_type_registry import" in source_type_source


def test_source_type_registry_is_immutable_through_compatibility_import() -> None:
    """Prevent compatibility imports from mutating source type registry state."""
    from brand_size_chart.source import SOURCE_TYPE_REGISTRY

    source_type = "official_brand_size_guide"
    original_instruction = SOURCE_TYPE_REGISTRY.source_type_discovery_instruction_get(source_type)
    original_priority = SOURCE_TYPE_REGISTRY.source_type_priority_get(source_type)

    try:
        with pytest.raises(TypeError):
            source_type_surface.SOURCE_TYPE_PRIORITY_BY_KEY_MAP[source_type] = 1
        with pytest.raises(TypeError):
            source_type_surface.SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP[source_type] = "mutated"
        with pytest.raises(AttributeError):
            source_type_surface.PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET.add("mutated_source_type")
    finally:
        if SOURCE_TYPE_REGISTRY.source_type_priority_get(source_type) != original_priority:
            source_type_surface.SOURCE_TYPE_PRIORITY_BY_KEY_MAP[source_type] = original_priority
        if SOURCE_TYPE_REGISTRY.source_type_discovery_instruction_get(source_type) != original_instruction:
            source_type_surface.SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP[source_type] = original_instruction
        if hasattr(source_type_surface.PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET, "discard"):
            source_type_surface.PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET.discard("mutated_source_type")

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
    assert (
        layout.table_extraction_dir(brand_input, "official_brand_size_guide", "women_upper")
        .relative_to(tmp_path)
        .as_posix()
        == "brand_size_chart_audit/brand/defacto/source_type/official_brand_size_guide/size_chart/women_upper/table_extraction"
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
            stage_key="source_discovery",
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
                artifact_path_list=["brand_size_chart_audit/brand/defacto/coverage_decision/result.json"],
                message="verified",
                stage_key="coverage_decision",
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

        assert "coverage_decision returned unexpected product types" in prompt_text
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
        prompt_scope=PromptScope(product_type_request_list=["women shoes"]),
        result_dir=tmp_path,
        source_type="official_brand_size_guide",
        stage_dir=tmp_path / "coverage_decision",
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

    assert ".secret/" in gitignore_text.splitlines()


def test_local_compose_declares_vpn_profile() -> None:
    """Keep only the browser runtime in the OpenVPN network namespace."""
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    openvpn_volume_list = compose["services"]["openvpn"]["volumes"]
    playwright_mcp_volume_list = compose["services"]["playwright-mcp"]["volumes"]
    workflow_volume_list = compose["services"]["workflow"]["volumes"]
    workflow_command_text = compose["services"]["workflow"]["command"][-1]
    workflow_dockerfile_text = Path("docker/workflow/Dockerfile").read_text(encoding="utf-8")

    assert compose["services"]["playwright-mcp"]["profiles"] == ["vpn"]
    assert compose["services"]["playwright-mcp"]["entrypoint"] == []
    assert "--allowed-hosts localhost,127.0.0.1,openvpn" in compose["services"]["playwright-mcp"]["command"][-1]
    assert compose["services"]["playwright-mcp"]["network_mode"] == "service:openvpn"
    assert compose["services"]["playwright-mcp"]["depends_on"]["openvpn"]["condition"] == "service_healthy"
    assert "network_mode" not in compose["services"]["workflow"]
    assert compose["services"]["workflow"]["dns"] == ["1.1.1.1", "8.8.8.8"]
    assert compose["services"]["workflow"]["depends_on"]["playwright-mcp"]["condition"] == "service_healthy"
    assert compose["services"]["workflow"]["environment"]["BROWSER_RUNTIME_MCP_URL"] == "http://openvpn:8931/mcp"
    assert (
        compose["services"]["workflow"]["environment"]["DBOS_SYSTEM_DATABASE_URL"] == "sqlite:////runtime/dbos.sqlite"
    )
    assert "./.secret:/input/.secret:ro" in openvpn_volume_list
    assert "./.secret:/input/.secret:ro" in playwright_mcp_volume_list
    assert "${OUTPUT_DIR:-./out}:/output" in playwright_mcp_volume_list
    assert "./.secret:/input/.secret:ro" in workflow_volume_list
    assert "${BRAND_LIST:-./brand_list.txt}:/input/brand_list.txt:ro" in workflow_volume_list
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
    assert "COPY brand_size_chart ./brand_size_chart" in workflow_dockerfile_text
    assert "jq ripgrep" in workflow_dockerfile_text
    assert "pip install --root-user-action=ignore --no-cache-dir ." in workflow_dockerfile_text
    assert "healthcheck" in compose["services"]["openvpn"]
    assert "healthcheck" in compose["services"]["playwright-mcp"]


def test_workflow_imports_dbos_eagerly_without_noop_decorator_fallback() -> None:
    """Keep workflow functions real DBOS workflow and step functions."""
    workflow_source = _workflow_package_source_text_get()

    assert "except ModuleNotFoundError" not in workflow_source
    assert "DBOS = None" not in workflow_source
    assert "def _dbos_step" not in workflow_source
    assert "def _dbos_workflow" not in workflow_source


def test_source_type_registry_has_no_separate_official_brand_asset_stage() -> None:
    """Keep official PDFs, images, and assets inside the official brand size-guide source type."""
    source_type_source = Path("brand_size_chart/source_type.py").read_text(encoding="utf-8")

    assert "official_brand_asset" not in source_type_source
    assert "pdf" not in SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP["official_brand_size_guide"].lower()
    assert "image" not in SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP["official_brand_size_guide"].lower()


def test_source_type_registry_uses_authority_sources_without_seller_qa_stage() -> None:
    """Keep source types based on authority and location, not on evidence format."""
    assert SOURCE_TYPE_PRIORITY_BY_KEY_MAP == {
        "official_brand_size_guide": 600,
        "official_seller_size_guide": 550,
        "official_brand_product_page": 500,
        "official_marketplace_product_page": 300,
        "official_marketplace_store": 200,
    }
    assert "official_seller_qa" not in SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP
    assert PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET == {
        "official_brand_product_page",
        "official_marketplace_product_page",
        "official_marketplace_store",
    }


def test_source_type_selection_requires_product_types_for_product_page_source_types() -> None:
    """Run product-page source types only when product types are requested."""
    source_type_list_without_product_types = workflow._source_type_list_get(PromptScope())
    source_type_list_with_product_types = workflow._source_type_list_get(PromptScope(product_type_request_list=["bra"]))

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

    official_brand_scope = workflow._source_type_prompt_scope_get(
        prompt_scope=prompt_scope,
        remaining_product_type_list=["women dresses", "men shoes"],
        source_type="official_brand_size_guide",
    )
    official_seller_scope = workflow._source_type_prompt_scope_get(
        prompt_scope=prompt_scope,
        remaining_product_type_list=["women dresses", "men shoes"],
        source_type="official_seller_size_guide",
    )
    product_page_scope = workflow._source_type_prompt_scope_get(
        prompt_scope=prompt_scope,
        remaining_product_type_list=["men shoes"],
        source_type="official_brand_product_page",
    )

    assert official_brand_scope.product_type_request_list == []
    assert official_seller_scope.product_type_request_list == []
    assert product_page_scope.product_type_request_list == ["men shoes"]


def test_prompt_scope_owns_priority_country_code() -> None:
    """Carry the priority country through prompt scope without product-type narrowing."""
    prompt_scope = PromptScope(
        priority_country_code="TR",
        product_type_request_list=["women dresses"],
        shared_instruction="Search official pages only.",
    )

    narrowed_prompt_scope = workflow._source_type_prompt_scope_get(
        prompt_scope=prompt_scope,
        remaining_product_type_list=[],
        source_type="official_seller_size_guide",
    )

    assert PromptScope().priority_country_code == "TR"
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
    evidence_path = evidence_path / "source_discovery" / "evidence" / "source_surface_inventory.json"
    evidence_path.parent.mkdir(parents=True)
    evidence_path.write_text("{}", encoding="utf-8")
    artifact_layout = ArtifactLayout(tmp_path)
    source_discovery_result = SourceDiscoveryResult(
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
            discovery_result=source_discovery_result,
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

    assert "canonical_selection missing eligible size_group_key" in message
    assert "women_upper" in message


def test_stage_prompt_text_includes_draft_result() -> None:
    """Give semantic stages their deterministic draft result as structured input."""
    prompt_text = workflow._stage_prompt_text_get(
        attempt_index=1,
        draft_result_json_text='{"canonical_selection_list":[{"size_group_key":"women_upper"}]}',
        feedback_list=[],
        prompt_context="Brand: Defacto",
        prompt_name="selection",
        prompt_scope=PromptScope(),
        previous_result_json_text="",
        stage_key="canonical_selection",
    )

    assert "Draft stage result JSON:" in prompt_text
    assert '"size_group_key":"women_upper"' in prompt_text


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

    def fake_coverage_decision_write_step(
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
        secret_ref: str,
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
            secret_ref: Secret root.
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
        _ = secret_ref
        source_type_prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        enqueued_source_type_list.append(source_type)
        assert source_type_prompt_scope.product_type_request_list == []
        return FakeHandle(
            {
                "source_type_summary": {
                    "blocker_list": [],
                    "conflict_list": [],
                    "evidence_manifest_path_list": [],
                    "source_priority": SOURCE_TYPE_PRIORITY_BY_KEY_MAP[source_type],
                    "source_type": source_type,
                    "state": "success",
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

    monkeypatch.setattr(workflow.DBOS, "enqueue_workflow", fake_enqueue_workflow)
    monkeypatch.setattr(brand_workflow_module, "SetWorkflowID", lambda _workflow_id: nullcontext())
    monkeypatch.setattr(
        workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW,
        "selection_write_step",
        fake_brand_selection_write_step,
    )
    monkeypatch.setattr(
        workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW,
        "coverage_decision_write_step",
        fake_coverage_decision_write_step,
    )

    result_payload = workflow.brand_size_chart_brand.__wrapped__(
        workflow.BRAND_SIZE_CHART_BRAND_WORKFLOW,
        "run1",
        {
            "parsed_brand_key": "defacto",
            "parsed_brand_name": "Defacto",
            "raw_brand_name": "Defacto",
            "source_line_number": 1,
        },
        "http://browser/mcp",
        PromptScope(product_type_request_list=["women dresses"]).model_dump(mode="json"),
        str(tmp_path),
        str(tmp_path / ".secret"),
    )

    assert result_payload["enqueued_source_type_list"] == [
        "official_brand_size_guide",
        "official_seller_size_guide",
    ]


def test_prompt_scope_rejects_product_type_values_in_shared_instruction() -> None:
    """Prevent product-type lists from leaking into stages through shared instruction text."""
    from brand_size_chart.validator.prompt_scope import PromptScopeValidator

    try:
        PromptScopeValidator().validate(
            PromptScope(
                product_type_request_list=["women dresses"],
                shared_instruction="Search all source types. Product types: women dresses.",
            )
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        message = ""

    assert "shared_instruction must not repeat product_type_request_list values" in message


def test_source_type_summary_records_failed_source_without_discovery_artifact(tmp_path: Path) -> None:
    """Write failed source-type summaries without requiring a successful discovery artifact."""
    summary_payload = workflow.source_type_summary_write_step.__wrapped__(
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
    )

    assert summary_payload["blocker_list"] == ["RuntimeError: source discovery failed"]
    assert summary_payload["evidence_manifest_path_list"] == []
    assert summary_payload["source_type"] == "official_brand_size_guide"
    assert summary_payload["state"] == "failed"


def test_prompt_scope_rejects_unknown_source_type_and_stage_key() -> None:
    """Reject unknown prompt-derived execution keys instead of silently dropping them."""
    from brand_size_chart.validator.prompt_scope import PromptScopeValidator

    validator = PromptScopeValidator()
    try:
        validator.validate(PromptScope(source_type_allow_list=["unknown_source_type"]))
    except RuntimeError as exc:
        source_type_message = str(exc)
    else:
        source_type_message = ""

    try:
        validator.validate(
            PromptScope(stage_instruction_list=[PromptStageInstruction(stage_key="unknown_stage", instruction="x")])
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
                product_type_request_list=["socks"],
                shared_instruction="Search all supported source types. Product types: socks.",
                source_type_allow_list=["all supported source types"],
            )
        if prompt_scope_call_count == 2:
            return PromptScope(
                product_type_request_list=["socks"],
                shared_instruction="Search all supported source types. Product types: socks.",
                source_type_allow_list=[],
            )
        assert "shared_instruction must not repeat product_type_request_list values" in prompt_text
        return PromptScope(
            product_type_request_list=["socks"],
            shared_instruction="Search all supported source types.",
            source_type_allow_list=[],
        )

    monkeypatch.setattr(workflow, "codex_stage_run", fake_codex_stage_run)

    prompt_scope = workflow._prompt_scope_stage_get(
        result_dir=tmp_path,
        workflow_run_prompt="Search all supported source types. Product types: socks.",
    )

    assert prompt_scope.product_type_request_list == ["socks"]
    assert prompt_scope.source_type_allow_list == []
    assert prompt_scope.shared_instruction == "Search all supported source types."
    assert prompt_scope_call_count == 3


def test_source_discovery_prompt_makes_table_forms_universal() -> None:
    """Search every source type for size charts in any browser-visible form."""
    discovery_prompt = Path("brand_size_chart/prompt/discovery.md").read_text(encoding="utf-8").lower()

    assert "html table" in discovery_prompt
    assert "modal" in discovery_prompt
    assert "widget" in discovery_prompt
    assert "pdf" in discovery_prompt
    assert "image" in discovery_prompt
    assert "help" in discovery_prompt
    assert "faq" in discovery_prompt
    assert "q&a" in discovery_prompt
    assert "for `official_brand_size_guide`" not in discovery_prompt


def test_size_group_key_contract_is_prompt_and_design_owned() -> None:
    """Keep size-group naming as a semantic prompt/design contract."""
    size_group_prompt = Path("brand_size_chart/prompt/size_group_key.md").read_text(encoding="utf-8")
    design_text = Path("doc/design/brand-size-chart.md").read_text(encoding="utf-8")
    workflow_text = _workflow_package_source_text_get()

    assert "{sex}_{product_group_or_type}" in size_group_prompt
    assert "{sex}_{sex_suffix}_{product_group_or_type}" in size_group_prompt
    assert "{min}_{max}_{month|year}" in size_group_prompt
    assert "Approved non-age `sex_suffix` terms" in size_group_prompt
    assert "Do not list or invent concrete approved age intervals" in size_group_prompt
    assert "child_3_8" not in size_group_prompt
    assert "youth_8_14" not in size_group_prompt
    assert "child_3_8" not in design_text
    assert "youth_8_14" not in design_text
    assert "Never use `size_chart`" in size_group_prompt
    assert "Semantic verification must reject alternative names" in design_text
    assert "women_size_chart" not in workflow_text
    assert "men_shoes_size_chart" not in workflow_text


def test_source_discovery_checks_official_host_variants() -> None:
    """Search all browser-visible official host variants before failing source discovery."""
    discovery_prompt = Path("brand_size_chart/prompt/discovery.md").read_text(encoding="utf-8")
    source_discovery_stage_text = Path("brand_size_chart/stage/source_discovery.py").read_text(encoding="utf-8")

    assert "official host variants" in discovery_prompt
    assert "country-code brand domains" in discovery_prompt
    assert "Do not stop after one official domain variant fails" in discovery_prompt
    assert "official host variants" in source_discovery_stage_text
    assert "country-code " in source_discovery_stage_text
    assert "brand domains" in source_discovery_stage_text
    assert "stop after one official domain variant fails" in source_discovery_stage_text


def test_source_discovery_searches_localized_size_terms_without_route_templates() -> None:
    """Find official size guides through localized browser search rather than hardcoded URL guesses."""
    discovery_prompt = Path("brand_size_chart/prompt/discovery.md").read_text(encoding="utf-8")
    source_discovery_stage_text = Path("brand_size_chart/stage/source_discovery.py").read_text(encoding="utf-8")

    assert "browser-visible language and market" in discovery_prompt
    assert "localized size-chart term searches" in discovery_prompt
    assert "beden rehberi" in discovery_prompt
    assert "URL templates" in discovery_prompt
    assert "browser-visible language and market" in source_discovery_stage_text
    assert "localized size-chart term searches" in source_discovery_stage_text
    assert "beden rehberi" in source_discovery_stage_text
    assert "/statik/beden-rehberi" not in discovery_prompt
    assert "/statik/beden-rehberi" not in source_discovery_stage_text


def test_table_extraction_preserves_size_system_columns() -> None:
    """Represent size-system columns with an explicit non-empty unit."""
    extraction_prompt = Path("brand_size_chart/prompt/extraction.md").read_text(encoding="utf-8")
    table_extraction_stage_text = Path("brand_size_chart/stage/table_extraction.py").read_text(encoding="utf-8")

    assert "For size-system or label-equivalence columns" in extraction_prompt
    assert "use unit='size'" in extraction_prompt
    assert "For size-system " in table_extraction_stage_text
    assert "use unit='size'" in table_extraction_stage_text


def test_table_extraction_preserves_physical_units_and_omits_blank_cells() -> None:
    """Keep physical measurement units and avoid empty measurement values."""
    extraction_prompt = Path("brand_size_chart/prompt/extraction.md").read_text(encoding="utf-8")
    table_extraction_stage_text = Path("brand_size_chart/stage/table_extraction.py").read_text(encoding="utf-8")

    assert "Do not emit measurement entries for blank source cells" in extraction_prompt
    assert "must keep their physical source unit" in extraction_prompt
    assert "Do not emit measurement entries for blank source cells" in table_extraction_stage_text
    assert "must keep their physical source unit" in table_extraction_stage_text


def test_coverage_decision_prompt_receives_verified_table_summary() -> None:
    """Prevent coverage decision from ignoring verified tables as missing evidence."""
    coverage_decision_stage_text = Path("brand_size_chart/stage/coverage_decision.py").read_text(encoding="utf-8")

    assert "Verified table summary is supplied below as stage input" in coverage_decision_stage_text
    assert "do not report missing evidence when" in coverage_decision_stage_text
    assert "Refine the draft coverage decision from these verified tables" in coverage_decision_stage_text


def test_source_discovery_prompt_preserves_partial_candidates() -> None:
    """Keep evidence-backed candidates successful even when requested product-type coverage is incomplete."""
    discovery_prompt = Path("brand_size_chart/prompt/discovery.md").read_text(encoding="utf-8")

    assert "If at least one concrete candidate is evidence-backed, return status='success'" in discovery_prompt
    assert "missing requested product types in error_list" in discovery_prompt


def test_source_discovery_product_types_do_not_filter_tables() -> None:
    """Keep full source-surface table discovery separate from requested product-type coverage."""
    discovery_prompt = Path("brand_size_chart/prompt/discovery.md").read_text(encoding="utf-8")
    verification_prompt = Path("brand_size_chart/prompt/verification.md").read_text(encoding="utf-8")
    source_discovery_stage_text = Path("brand_size_chart/stage/source_discovery.py").read_text(encoding="utf-8")
    design_text = Path("doc/design/brand-size-chart.md").read_text(encoding="utf-8")

    expected_text = "Requested product types are coverage targets only"
    assert expected_text in discovery_prompt
    assert expected_text in verification_prompt
    assert expected_text in source_discovery_stage_text
    assert "`product_type_request_list` defines coverage targets" in design_text
    assert "must not filter `source_discovery` candidates" in design_text


def test_source_discovery_returns_unique_size_group_key_candidates() -> None:
    """Keep duplicate locale tables as evidence instead of duplicate source candidates."""
    discovery_prompt = Path("brand_size_chart/prompt/discovery.md").read_text(encoding="utf-8")
    verification_prompt = Path("brand_size_chart/prompt/verification.md").read_text(encoding="utf-8")
    source_discovery_stage_text = Path("brand_size_chart/stage/source_discovery.py").read_text(encoding="utf-8")
    design_text = Path("doc/design/brand-size-chart.md").read_text(encoding="utf-8")

    assert "return at most one `discovered_source_list` item for one `size_group_key`" in discovery_prompt
    assert "must not require a second `discovered_source_list` item" in verification_prompt
    assert "return at most one discovered_source_list" in source_discovery_stage_text
    assert "item for one size_group_key" in source_discovery_stage_text
    assert "one `size_group_key` may appear at most once in `discovered_source_list`" in design_text


def test_source_discovery_locale_policy_is_priority_global_europe_without_vague_candidate_wording() -> None:
    """Use one explicit country-selection ladder instead of vague other-locale candidate rules."""
    apply_prompt = Path("brand_size_chart/prompt/apply.md").read_text(encoding="utf-8")
    discovery_prompt = Path("brand_size_chart/prompt/discovery.md").read_text(encoding="utf-8")
    verification_prompt = Path("brand_size_chart/prompt/verification.md").read_text(encoding="utf-8")
    source_discovery_stage_text = Path("brand_size_chart/stage/source_discovery.py").read_text(encoding="utf-8")
    design_text = Path("doc/design/brand-size-chart.md").read_text(encoding="utf-8")
    combined_text = "\n".join(
        [apply_prompt, discovery_prompt, verification_prompt, source_discovery_stage_text, design_text]
    )

    assert "`priority_country_code`" in apply_prompt
    assert "Priority country code:" in source_discovery_stage_text
    assert "priority country tables exist" in discovery_prompt
    assert "global tables" in discovery_prompt
    assert "European country tables" in discovery_prompt
    assert "priority country tables exist" in verification_prompt
    assert "`priority_country_code` defines the market priority" in design_text
    for forbidden_text in ["comparison/" + "evidence/" + "blocker", "other " + "locales"]:
        assert forbidden_text not in combined_text


def test_source_discovery_prompt_requires_canonical_inventory_on_retry() -> None:
    """Require retry attempts to update the canonical source-surface inventory."""
    discovery_prompt = Path("brand_size_chart/prompt/discovery.md").read_text(encoding="utf-8")
    source_discovery_stage_text = Path("brand_size_chart/stage/source_discovery.py").read_text(encoding="utf-8")

    assert "canonical source-surface inventory artifact" in discovery_prompt
    assert "source_surface_inventory.json" in discovery_prompt
    assert "overwrite the canonical inventory artifact" in discovery_prompt
    assert "attempt-only inventory names are allowed only as extra diagnostics" in discovery_prompt
    assert "First build one canonical" in source_discovery_stage_text
    assert "source_surface_inventory.json" in source_discovery_stage_text
    assert "browser-backed source-surface inventory artifact" in source_discovery_stage_text
    assert "attempt-only inventory artifacts are allowed only as extra" in source_discovery_stage_text


def test_source_discovery_candidate_urls_exclude_helper_surfaces() -> None:
    """Keep sitemap and navigation helper surfaces out of concrete candidate URLs."""
    discovery_prompt = Path("brand_size_chart/prompt/discovery.md").read_text(encoding="utf-8")
    source_discovery_stage_text = Path("brand_size_chart/stage/source_discovery.py").read_text(encoding="utf-8")

    assert "`candidate_urls` must contain only concrete source candidates" in discovery_prompt
    assert "helper surfaces are discovery surfaces, not candidate URLs" in discovery_prompt
    assert "candidate_urls must contain only concrete source candidates" in source_discovery_stage_text
    assert "helper surfaces are discovery surfaces, not candidate URLs" in source_discovery_stage_text


def test_source_discovery_candidate_urls_exclude_broad_product_lists() -> None:
    """Keep broad search-result product inventories separate from selected source candidates."""
    discovery_prompt = Path("brand_size_chart/prompt/discovery.md").read_text(encoding="utf-8")
    source_discovery_stage_text = Path("brand_size_chart/stage/source_discovery.py").read_text(encoding="utf-8")

    assert "broad search-result or category product URL inventories" in discovery_prompt
    assert "search_result_url_list" in discovery_prompt
    assert "broad search-result or category product URL inventories" in source_discovery_stage_text
    assert "search_result_url_list" in source_discovery_stage_text


def test_source_discovery_verification_preserves_partial_candidates() -> None:
    """Prevent verification feedback from converting evidence-backed candidates into failed discovery."""
    verification_prompt = Path("brand_size_chart/prompt/verification.md").read_text(encoding="utf-8")

    assert "Do not require status='failed' only because requested product-type coverage is incomplete" in (
        verification_prompt
    )
    assert "failed only when no concrete acceptable candidate remains" in verification_prompt


def test_source_discovery_verification_uses_bounded_completeness() -> None:
    """Do not require unbounded product URL enumeration after bounded inventory is complete."""
    verification_prompt = Path("brand_size_chart/prompt/verification.md").read_text(encoding="utf-8")

    assert "verify source-type completeness inside the bounded source surface" in verification_prompt
    assert "canonical inventory evidence is missing or stale" in verification_prompt
    assert "unbounded search evidence contains additional similar product URLs" in verification_prompt


def test_verification_prompt_rejects_stale_feedback() -> None:
    """Verify only the current stage result and current artifacts."""
    verification_prompt = Path("brand_size_chart/prompt/verification.md").read_text(encoding="utf-8")

    assert "Feedback from previous attempts is not evidence" in verification_prompt
    assert "A URL already present in `opened_urls` is tested" in verification_prompt
    assert "navigation, search, home, sitemap, FAQ, or help URL" in verification_prompt
    assert "Do not fail `source_discovery` solely because one helper URL" in verification_prompt


def test_verification_prompt_rejects_stale_hidden_row_errors() -> None:
    """Do not fail table extraction for hidden rows already omitted from the current result."""
    verification_prompt = Path("brand_size_chart/prompt/verification.md").read_text(encoding="utf-8")

    assert "hidden or non-rendered rows" in verification_prompt
    assert "current `Stage result JSON` already omits them" in verification_prompt
    assert "quote the exact current extracted row" in verification_prompt
