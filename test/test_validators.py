"""Focused behavior tests for stateless mechanical validators."""

import inspect
import json
from importlib import import_module
from pathlib import Path

import pytest
from workflow_container_runtime.step import (
    BrowsingError,
    StepResultValidationError,
    WorkflowStepExecutionContext,
)
from workflow_container_runtime.workflow import WorkflowRuntimeCapability

from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandInput,
    BrandOutputInput,
    BrandOutputItem,
    BrandOutputResult,
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    BrandWorkflowInput,
    CanonicalSelection,
    CanonicalSelectionCandidate,
    CanonicalSelectionInput,
    CanonicalSelectionResult,
    CoverageDecisionInput,
    CoverageDecisionProductTypeGap,
    CoverageDecisionResult,
    CoveredProductType,
    PromptScope,
    PromptStepInstruction,
    RunInput,
    SourceDiscovery,
    SourceDiscoveryInput,
    SourceDiscoveryResult,
    SourceSurfaceDiscoveryQuery,
    SourceSurfaceInventory,
    SourceSurfaceProductTypeSex,
    SourceSurfaceTable,
    SourceSurfaceUrl,
    SourceTypeCatalogItem,
    SourceTypeWorkflowInput,
    TableExtractionArtifact,
    TableExtractionExecplanItem,
    TableExtractionInput,
    TableExtractionResult,
    WorkflowRunPromptApplyInput,
)


def _brand_input_get() -> BrandInput:
    """Return one stable brand identity for persisted step inputs."""

    return BrandInput(
        parsed_brand_key="defacto",
        parsed_brand_name="Defacto",
        raw_brand_name="Defacto",
        source_line_number=1,
    )


def _brand_workflow_input_get(*, product_type_list: list[str] | None = None) -> BrandWorkflowInput:
    """Return one brand workflow input with requested product types.

    Args:
        product_type_list: Optional requested product-type list.

    Returns:
        Brand workflow input used by coverage and canonical-selection steps.
    """

    return BrandWorkflowInput(
        brand_input=_brand_input_get(),
        prompt_scope=PromptScope(
            priority_country_code="TR",
            product_type_request_list=product_type_list or [],
        ),
    )


def _execution_context_get(tmp_path: Path, *, step_key: str) -> WorkflowStepExecutionContext:
    """Return one filesystem-backed step execution context.

    Args:
        tmp_path: Result root supplied by pytest.
        step_key: Current step instance key.

    Returns:
        Runtime execution context with no optional capabilities.
    """

    return WorkflowStepExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        step_instance_dir=tmp_path / "workflow" / "run" / "step" / step_key,
    )


def _source_discovery_get(*, evidence_path: str, size_group_key: str = "women_upper") -> SourceDiscovery:
    """Return one accepted source discovery.

    Args:
        evidence_path: Result-relative evidence reference.
        size_group_key: Stable physical table identity.

    Returns:
        Source discovery backed by one evidence artifact.
    """

    return SourceDiscovery(
        country_code_list=["TR"],
        evidence_path_list=[evidence_path],
        size_group_key=size_group_key,
        source_title="Defacto size guide",
        source_url="https://www.defacto.com.tr/size-guide",
    )


def _source_discovery_input_get(
    execution_context: WorkflowStepExecutionContext,
) -> SourceDiscoveryInput:
    """Return the exact persisted source-discovery input.

    Args:
        execution_context: Current step execution context.

    Returns:
        Source-discovery input with one declared evidence target.
    """

    evidence_dir = execution_context.step_instance_dir / "evidence"
    return SourceDiscoveryInput(
        evidence_write_target=ArtifactWriteTarget(
            artifact_path=evidence_dir.relative_to(execution_context.result_dir).as_posix(),
            filesystem_path=(execution_context.result_dir / ".playwright-mcp" / "current" / "evidence").as_posix(),
        ),
        step_instruction_list=["Prefer visible manufacturer tables."],
        workflow_input=SourceTypeWorkflowInput(
            brand_input=_brand_input_get(),
            prompt_scope=PromptScope(
                priority_country_code="TR",
                product_type_request_list=["women dress"],
            ),
            source_type="official_brand_size_guide",
        ),
    )


def _source_inventory_get(
    *,
    source_discovery: SourceDiscovery,
    worklist_state: str = "searched",
) -> SourceSurfaceInventory:
    """Return one closed source-surface inventory.

    Args:
        source_discovery: Accepted source discovery.
        worklist_state: Product-type worklist state.

    Returns:
        Inventory with explicit query, worklist, URL, and table rows.
    """

    evidence_path = source_discovery.evidence_path_list[0]
    worklist_evidence_path_list = [evidence_path]
    worklist_reason = "The product boundary was inspected."
    return SourceSurfaceInventory(
        discovery_query_list=[
            SourceSurfaceDiscoveryQuery(
                entity_id="query:official",
                evidence_path_list=[evidence_path],
                query="Defacto size guide",
                reason="Searched the official site.",
                record_id="query:official:r1",
                revision_index=1,
                state="searched",
                supersedes_record_id=None,
            )
        ],
        product_type_sex_worklist=[
            SourceSurfaceProductTypeSex(
                entity_id="worklist:women-dress",
                evidence_path_list=worklist_evidence_path_list,
                product_type="dress",
                reason=worklist_reason,
                record_id="worklist:women-dress:r1",
                revision_index=1,
                sex="women",
                state=worklist_state,
                supersedes_record_id=None,
                worklist_key="women_dress",
            )
        ],
        table_list=[
            SourceSurfaceTable(
                entity_id="table:women-upper",
                reason="Visible official table.",
                record_id="table:women-upper:r1",
                revision_index=1,
                source_discovery=source_discovery,
                state="accepted",
                supersedes_record_id=None,
            )
        ],
        url_list=[
            SourceSurfaceUrl(
                entity_id="url:official",
                evidence_path_list=[evidence_path],
                reason="Opened the official size guide.",
                record_id="url:official:r1",
                revision_index=1,
                state="opened",
                supersedes_record_id=None,
                url=source_discovery.source_url,
                worklist_key_list=[] if worklist_state == "rejected" else ["women_dress"],
            )
        ],
    )


def _table_extraction_input_get(
    execution_context: WorkflowStepExecutionContext,
    *,
    source_discovery: SourceDiscovery,
) -> TableExtractionInput:
    """Return one exact table-extraction execplan.

    Args:
        execution_context: Current step execution context.
        source_discovery: Source identity carried into extraction.

    Returns:
        Persisted table-extraction input with declared chart and evidence targets.
    """

    evidence_dir = execution_context.step_instance_dir / "evidence" / source_discovery.size_group_key
    return TableExtractionInput(
        execplan_item_list=[
            TableExtractionExecplanItem(
                chart_filesystem_path=(
                    execution_context.step_instance_dir / "chart" / f"{source_discovery.size_group_key}.json"
                ).as_posix(),
                evidence_write_target=ArtifactWriteTarget(
                    artifact_path=evidence_dir.relative_to(execution_context.result_dir).as_posix(),
                    filesystem_path=(
                        execution_context.result_dir
                        / ".playwright-mcp"
                        / "current"
                        / "evidence"
                        / source_discovery.size_group_key
                    ).as_posix(),
                ),
                source_discovery=source_discovery,
            )
        ],
        step_instruction_list=["Extract every visible row."],
        workflow_input=SourceTypeWorkflowInput(
            brand_input=_brand_input_get(),
            prompt_scope=PromptScope(priority_country_code="TR"),
            source_type="official_brand_size_guide",
        ),
    )


def _table_extraction_artifact_get(
    execution_context: WorkflowStepExecutionContext,
    *,
    evidence_path: str,
    source_discovery: SourceDiscovery,
) -> TableExtractionArtifact:
    """Return the exact public table artifact for one execplan item.

    Args:
        execution_context: Current step execution context.
        evidence_path: Result-relative table evidence path.
        source_discovery: Immutable source identity.

    Returns:
        Public table-extraction artifact.
    """

    chart_path = execution_context.step_instance_dir / "chart" / f"{source_discovery.size_group_key}.json"
    return TableExtractionArtifact(
        applicability_description="Applies to women's upper garments.",
        chart_path=chart_path.relative_to(execution_context.result_dir).as_posix(),
        evidence_path_list=[evidence_path],
        source_discovery=source_discovery,
        source_type="official_brand_size_guide",
    )


def _valid_chart_write(path: Path) -> None:
    """Write one mechanically valid size chart.

    Args:
        path: Declared chart target.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    chart = BrandSizeChart(
        description="Women's upper garments.",
        row_list=[
            BrandSizeChartRow(
                measurement_list=[
                    BrandSizeChartMeasurement(
                        max_value="M",
                        min_value="M",
                        name="Manufacturer size",
                        unit="size",
                    ),
                    BrandSizeChartMeasurement(
                        max_value="92",
                        min_value="88",
                        name="Bust",
                        unit="cm",
                    ),
                ],
                size_label="M",
            )
        ],
    )
    path.write_text(chart.model_dump_json(), encoding="utf-8")


def _feedback_text_get(exc_info: pytest.ExceptionInfo[StepResultValidationError]) -> str:
    """Return combined actionable feedback from one validation error.

    Args:
        exc_info: Captured step-result validation exception.

    Returns:
        Combined feedback text.
    """

    assert exc_info.value.feedback_list
    assert all(feedback.strip() for feedback in exc_info.value.feedback_list)
    return " ".join(exc_info.value.feedback_list)


def _validator_class_get(name: str) -> type[object]:
    """Load one validator class inside test execution.

    Args:
        name: Public validator class name.

    Returns:
        Requested validator class.
    """

    validator_class = getattr(import_module("brand_size_chart.validator"), name)
    assert isinstance(validator_class, type)
    return validator_class


@pytest.mark.parametrize(
    ("validator_class", "parameter_name_tuple"),
    [
        ("PromptScopeValidator", ("self", "execution_context", "step_input", "result")),
        ("BrandOutputValidator", ("self", "execution_context", "step_input", "result")),
        (
            "SourceDiscoveryValidator",
            ("self", "execution_context", "step_input", "result", "inventory"),
        ),
        ("TableExtractionValidator", ("self", "execution_context", "step_input", "result")),
        ("CoverageDecisionValidator", ("self", "execution_context", "step_input", "result")),
        ("CanonicalSelectionValidator", ("self", "execution_context", "step_input", "result")),
    ],
)
def test_validator_api_is_stateless_and_explicit(
    validator_class: str,
    parameter_name_tuple: tuple[str, ...],
) -> None:
    """Expose only stateless validation over persisted input and runtime context.

    Args:
        validator_class: Concrete validator class name.
        parameter_name_tuple: Required public validation signature.
    """

    loaded_validator_class = _validator_class_get(validator_class)
    validator = loaded_validator_class()
    public_callable_name_set = {
        name for name, value in loaded_validator_class.__dict__.items() if not name.startswith("_") and callable(value)
    }

    assert "__init__" not in loaded_validator_class.__dict__
    assert vars(validator) == {}
    assert public_callable_name_set == {"validate"}
    assert tuple(inspect.signature(loaded_validator_class.validate).parameters) == parameter_name_tuple


def test_brand_output_validator_accepts_exact_paths_and_valid_charts(tmp_path: Path) -> None:
    """Accept exact public output paths backed by valid step-declared chart files."""

    execution_context = _execution_context_get(tmp_path, step_key="brand_output")
    output_path = tmp_path / "brand_size_chart" / "brand" / "defacto" / "size_chart" / "women_upper.json"
    _valid_chart_write(output_path)
    table_extraction = TableExtractionArtifact(
        chart_path="workflow/run/step/table_extract/chart/women_upper.json",
        evidence_path_list=["workflow/run/step/table_extract/evidence/women_upper/table.json"],
        source_discovery=_source_discovery_get(
            evidence_path="workflow/run/step/table_extract/evidence/women_upper/table.json"
        ),
        source_type="official_brand_size_guide",
    )
    output_artifact_path = output_path.relative_to(tmp_path).as_posix()
    step_input = BrandOutputInput(
        output_item_list=[
            BrandOutputItem(
                output_artifact_path=output_artifact_path,
                output_filesystem_path=output_path.as_posix(),
                table_extraction_artifact=table_extraction,
            )
        ],
    )

    _validator_class_get("BrandOutputValidator")().validate(
        execution_context,
        step_input,
        BrandOutputResult(size_chart_path_list=[output_artifact_path]),
    )


def test_brand_output_validator_rejects_public_path_drift(tmp_path: Path) -> None:
    """Require the public result list to equal the persisted output-item list exactly."""

    execution_context = _execution_context_get(tmp_path, step_key="brand_output")
    output_path = tmp_path / "brand_size_chart" / "brand" / "defacto" / "size_chart" / "women_upper.json"
    _valid_chart_write(output_path)
    step_input = BrandOutputInput(
        output_item_list=[
            BrandOutputItem(
                output_artifact_path=output_path.relative_to(tmp_path).as_posix(),
                output_filesystem_path=output_path.as_posix(),
                table_extraction_artifact=TableExtractionArtifact(
                    chart_path="workflow/run/step/table_extract/chart/women_upper.json",
                    evidence_path_list=["workflow/run/step/table_extract/evidence/women_upper/table.json"],
                    source_discovery=_source_discovery_get(
                        evidence_path="workflow/run/step/table_extract/evidence/women_upper/table.json"
                    ),
                    source_type="official_brand_size_guide",
                ),
            )
        ],
    )

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("BrandOutputValidator")().validate(
            execution_context,
            step_input,
            BrandOutputResult(size_chart_path_list=["brand_size_chart/brand/defacto/size_chart/wrong.json"]),
        )

    assert "Return size_chart_path_list exactly" in _feedback_text_get(exc_info)


def test_brand_output_validator_rejects_output_outside_result_dir(tmp_path: Path) -> None:
    """Reject a persisted filesystem target that escapes the runtime result root."""

    execution_context = _execution_context_get(tmp_path, step_key="brand_output")
    outside_path = tmp_path.parent / "outside-size-chart.json"
    _valid_chart_write(outside_path)
    step_input = BrandOutputInput(
        output_item_list=[
            BrandOutputItem(
                output_artifact_path="outside-size-chart.json",
                output_filesystem_path=outside_path.as_posix(),
                table_extraction_artifact=TableExtractionArtifact(
                    chart_path="workflow/run/step/table_extract/chart/women_upper.json",
                    evidence_path_list=["workflow/run/step/table_extract/evidence/women_upper/table.json"],
                    source_discovery=_source_discovery_get(
                        evidence_path="workflow/run/step/table_extract/evidence/women_upper/table.json"
                    ),
                    source_type="official_brand_size_guide",
                ),
            )
        ],
    )

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("BrandOutputValidator")().validate(
            execution_context,
            step_input,
            BrandOutputResult(size_chart_path_list=["outside-size-chart.json"]),
        )

    assert "Keep every output_filesystem_path inside result_dir" in _feedback_text_get(exc_info)


@pytest.mark.parametrize(
    ("chart_payload", "feedback_text"),
    [
        (None, "Create the missing final BrandSizeChart"),
        ('{"description":"missing rows"}', "Rewrite the final output"),
    ],
)
def test_brand_output_validator_requires_existing_valid_chart(
    tmp_path: Path,
    chart_payload: str | None,
    feedback_text: str,
) -> None:
    """Reject missing and schema-invalid final chart files.

    Args:
        tmp_path: Result root supplied by pytest.
        chart_payload: Optional invalid file payload.
        feedback_text: Expected actionable feedback fragment.
    """

    execution_context = _execution_context_get(tmp_path, step_key="brand_output")
    output_path = tmp_path / "brand_size_chart" / "brand" / "defacto" / "size_chart" / "women_upper.json"
    if chart_payload is not None:
        output_path.parent.mkdir(parents=True)
        output_path.write_text(chart_payload, encoding="utf-8")
    output_artifact_path = output_path.relative_to(tmp_path).as_posix()
    step_input = BrandOutputInput(
        output_item_list=[
            BrandOutputItem(
                output_artifact_path=output_artifact_path,
                output_filesystem_path=output_path.as_posix(),
                table_extraction_artifact=TableExtractionArtifact(
                    chart_path="workflow/run/step/table_extract/chart/women_upper.json",
                    evidence_path_list=["workflow/run/step/table_extract/evidence/women_upper/table.json"],
                    source_discovery=_source_discovery_get(
                        evidence_path="workflow/run/step/table_extract/evidence/women_upper/table.json"
                    ),
                    source_type="official_brand_size_guide",
                ),
            )
        ],
    )

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("BrandOutputValidator")().validate(
            execution_context,
            step_input,
            BrandOutputResult(size_chart_path_list=[output_artifact_path]),
        )

    assert feedback_text in _feedback_text_get(exc_info)


def test_prompt_scope_validator_uses_persisted_catalog_and_step_instruction_contract(tmp_path: Path) -> None:
    """Accept source and step keys declared by the current persisted contract."""

    execution_context = _execution_context_get(tmp_path, step_key="workflow_run_prompt_apply")
    step_input = WorkflowRunPromptApplyInput(
        source_type_catalog_list=[
            SourceTypeCatalogItem(
                requires_product_type=False,
                source_type="official_brand_size_guide",
            )
        ],
        workflow_input=RunInput(
            brand_list_text="Defacto\n",
            workflow_run_prompt="Use Turkish sources first.",
        ),
    )
    result = PromptScope(
        priority_country_code="TR",
        shared_instruction="Prefer official sources.",
        source_type_allow_list=["official_brand_size_guide"],
        step_instruction_list=[
            PromptStepInstruction(
                instruction="Preserve source titles.",
                step_key="table_extract",
            )
        ],
    )

    _validator_class_get("PromptScopeValidator")().validate(execution_context, step_input, result)


def test_prompt_scope_validator_rejects_unknown_step_key(tmp_path: Path) -> None:
    """Reject an unsupported step key through actionable feedback."""

    execution_context = _execution_context_get(tmp_path, step_key="workflow_run_prompt_apply")
    step_input = WorkflowRunPromptApplyInput(
        source_type_catalog_list=[],
        workflow_input=RunInput(brand_list_text="Defacto\n", workflow_run_prompt="Use Turkish sources first."),
    )
    result = PromptScope(
        priority_country_code="TR",
        step_instruction_list=[
            PromptStepInstruction(
                instruction="Extract every row.",
                step_key="table_extraction",
            )
        ],
    )

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("PromptScopeValidator")().validate(execution_context, step_input, result)

    assert "step_key" in _feedback_text_get(exc_info)


def test_source_discovery_validator_accepts_exact_inventory_result_and_browsing_error(tmp_path: Path) -> None:
    """Accept exact public parity while keeping browser failures in their typed result field."""

    execution_context = _execution_context_get(tmp_path, step_key="source_discover")
    step_input = _source_discovery_input_get(execution_context)
    evidence_path = f"{step_input.evidence_write_target.artifact_path}/source.json"
    evidence_file = execution_context.result_dir / evidence_path
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text('{"title":"Defacto size guide"}\n', encoding="utf-8")
    source_discovery = _source_discovery_get(evidence_path=evidence_path)
    inventory = _source_inventory_get(source_discovery=source_discovery)
    result = SourceDiscoveryResult(
        browsing_error_list=[
            BrowsingError(
                error="A secondary locale timed out.",
                url="https://www.defacto.com/size-guide",
            )
        ],
        source_discovery_list=[source_discovery],
        warning_list=[],
    )

    _validator_class_get("SourceDiscoveryValidator")().validate(
        execution_context,
        step_input,
        result,
        inventory,
    )


def test_source_discovery_validator_rejects_pending_worklist_with_opened_dedicated_url(tmp_path: Path) -> None:
    """Require each folded worklist row to record its own terminal state."""

    execution_context = _execution_context_get(tmp_path, step_key="source_discover")
    step_input = _source_discovery_input_get(execution_context)
    evidence_path = f"{step_input.evidence_write_target.artifact_path}/source.json"
    evidence_file = execution_context.result_dir / evidence_path
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("{}\n", encoding="utf-8")
    source_discovery = _source_discovery_get(evidence_path=evidence_path)
    inventory = _source_inventory_get(source_discovery=source_discovery, worklist_state="pending")

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("SourceDiscoveryValidator")().validate(
            execution_context,
            step_input,
            SourceDiscoveryResult(source_discovery_list=[source_discovery]),
            inventory,
        )

    assert "Complete every pending" in _feedback_text_get(exc_info)


def test_source_discovery_validator_rejects_one_shared_url_for_product_scoped_searched_worklist(tmp_path: Path) -> None:
    """Require one dedicated URL record for each searched product-scoped worklist row."""

    execution_context = _execution_context_get(tmp_path, step_key="source_discover")
    step_input = _source_discovery_input_get(execution_context)
    step_input = step_input.model_copy(
        update={
            "workflow_input": step_input.workflow_input.model_copy(
                update={
                    "prompt_scope": step_input.workflow_input.prompt_scope.model_copy(
                        update={"product_type_request_list": ["women dress", "men shirt"]}
                    ),
                    "source_type": "official_marketplace_store",
                }
            )
        }
    )
    evidence_path = f"{step_input.evidence_write_target.artifact_path}/source.json"
    evidence_file = execution_context.result_dir / evidence_path
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("{}\n", encoding="utf-8")
    source_discovery = _source_discovery_get(evidence_path=evidence_path)
    inventory = _source_inventory_get(source_discovery=source_discovery)
    second_worklist_item = SourceSurfaceProductTypeSex(
        entity_id="worklist:men-shirt",
        evidence_path_list=[evidence_path],
        product_type="shirt",
        reason="The product boundary was inspected.",
        record_id="worklist:men-shirt:r1",
        revision_index=1,
        sex="men",
        state="searched",
        supersedes_record_id=None,
        worklist_key="men_shirt",
    )
    inventory = inventory.model_copy(
        update={
            "product_type_sex_worklist": [*inventory.product_type_sex_worklist, second_worklist_item],
            "url_list": [inventory.url_list[0].model_copy(update={"worklist_key_list": ["women_dress", "men_shirt"]})],
        }
    )

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("SourceDiscoveryValidator")().validate(
            execution_context,
            step_input,
            SourceDiscoveryResult(source_discovery_list=[source_discovery]),
            inventory,
        )

    feedback_text = _feedback_text_get(exc_info)
    assert "dedicated product URL" in feedback_text
    assert "men_shirt" in feedback_text
    assert "women_dress" in feedback_text


def test_source_discovery_validator_rejects_rejected_url_for_searched_product_worklist(tmp_path: Path) -> None:
    """Require an opened dedicated product URL for a searched product worklist row."""

    execution_context = _execution_context_get(tmp_path, step_key="source_discover")
    step_input = _source_discovery_input_get(execution_context)
    step_input = step_input.model_copy(
        update={
            "workflow_input": step_input.workflow_input.model_copy(update={"source_type": "official_marketplace_store"})
        }
    )
    evidence_path = f"{step_input.evidence_write_target.artifact_path}/source.json"
    evidence_file = execution_context.result_dir / evidence_path
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("{}\n", encoding="utf-8")
    source_discovery = _source_discovery_get(evidence_path=evidence_path)
    inventory = _source_inventory_get(source_discovery=source_discovery)
    inventory = inventory.model_copy(
        update={
            "url_list": [inventory.url_list[0].model_copy(update={"state": "rejected"})],
        }
    )

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("SourceDiscoveryValidator")().validate(
            execution_context,
            step_input,
            SourceDiscoveryResult(source_discovery_list=[source_discovery]),
            inventory,
        )

    assert "dedicated product URL" in _feedback_text_get(exc_info)


def test_source_discovery_validator_rejects_missing_requested_product_worklist(tmp_path: Path) -> None:
    """Require every requested product type to have a source-discovery worklist row."""

    execution_context = _execution_context_get(tmp_path, step_key="source_discover")
    step_input = _source_discovery_input_get(execution_context)
    step_input = step_input.model_copy(
        update={
            "workflow_input": step_input.workflow_input.model_copy(
                update={"source_type": "official_brand_product_page"}
            )
        }
    )
    evidence_path = f"{step_input.evidence_write_target.artifact_path}/source.json"
    evidence_file = execution_context.result_dir / evidence_path
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("{}\n", encoding="utf-8")
    source_discovery = _source_discovery_get(evidence_path=evidence_path)
    inventory = _source_inventory_get(source_discovery=source_discovery)
    inventory = inventory.model_copy(
        update={
            "product_type_sex_worklist": [],
            "url_list": [inventory.url_list[0].model_copy(update={"worklist_key_list": []})],
        }
    )

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("SourceDiscoveryValidator")().validate(
            execution_context,
            step_input,
            SourceDiscoveryResult(source_discovery_list=[source_discovery]),
            inventory,
        )

    assert "requested product type" in _feedback_text_get(exc_info)


def test_source_discovery_validator_rejects_market_conflict(tmp_path: Path) -> None:
    """Treat a European market conflict as a correctable mechanical blocker."""

    execution_context = _execution_context_get(tmp_path, step_key="source_discover")
    step_input = _source_discovery_input_get(execution_context)
    evidence_path = f"{step_input.evidence_write_target.artifact_path}/source.json"
    evidence_file = execution_context.result_dir / evidence_path
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("{}\n", encoding="utf-8")
    source_discovery = _source_discovery_get(evidence_path=evidence_path)
    inventory = _source_inventory_get(source_discovery=source_discovery, worklist_state="rejected")
    inventory = inventory.model_copy(
        update={
            "table_list": [inventory.table_list[0].model_copy(update={"state": "market_conflict"})],
        }
    )

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("SourceDiscoveryValidator")().validate(
            execution_context,
            step_input,
            SourceDiscoveryResult(warning_list=["No table was selected."]),
            inventory,
        )

    assert "Resolve the market conflict" in _feedback_text_get(exc_info)


def test_source_discovery_validator_requires_exact_no_table_warning_parity(tmp_path: Path) -> None:
    """Publish exactly the evidence-backed no-table reasons from private inventory."""

    execution_context = _execution_context_get(tmp_path, step_key="source_discover")
    step_input = _source_discovery_input_get(execution_context)
    step_input = step_input.model_copy(
        update={
            "workflow_input": step_input.workflow_input.model_copy(
                update={
                    "prompt_scope": step_input.workflow_input.prompt_scope.model_copy(
                        update={"product_type_request_list": []}
                    )
                }
            )
        }
    )
    evidence_path = f"{step_input.evidence_write_target.artifact_path}/failure.json"
    evidence_file = execution_context.result_dir / evidence_path
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("{}\n", encoding="utf-8")
    inventory = SourceSurfaceInventory(
        discovery_query_list=[
            SourceSurfaceDiscoveryQuery(
                entity_id="query:official",
                evidence_path_list=[evidence_path],
                query="Defacto size guide",
                reason="The official guide was unavailable.",
                record_id="query:official:r1",
                revision_index=1,
                state="failed",
                supersedes_record_id=None,
            )
        ],
        product_type_sex_worklist=[],
        table_list=[],
        url_list=[],
    )

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("SourceDiscoveryValidator")().validate(
            execution_context,
            step_input,
            SourceDiscoveryResult(warning_list=["No result."]),
            inventory,
        )

    assert "warning_list exactly" in _feedback_text_get(exc_info)


def test_source_discovery_validator_converts_artifact_reference_failure(tmp_path: Path) -> None:
    """Translate missing inventory evidence into the runtime validation channel."""

    execution_context = _execution_context_get(tmp_path, step_key="source_discover")
    step_input = _source_discovery_input_get(execution_context)
    evidence_path = f"{step_input.evidence_write_target.artifact_path}/missing.json"
    source_discovery = _source_discovery_get(evidence_path=evidence_path)
    inventory = _source_inventory_get(source_discovery=source_discovery)

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("SourceDiscoveryValidator")().validate(
            execution_context,
            step_input,
            SourceDiscoveryResult(source_discovery_list=[source_discovery]),
            inventory,
        )

    assert "Create every referenced evidence artifact" in _feedback_text_get(exc_info)


@pytest.mark.parametrize("path_kind", ["parent_escape", "absolute"])
def test_source_discovery_validator_rejects_evidence_target_escape(tmp_path: Path, path_kind: str) -> None:
    """Reject non-relative or escaping paths at the declared source target.

    Args:
        tmp_path: Result root supplied by pytest.
        path_kind: Invalid public evidence path shape.
    """

    execution_context = _execution_context_get(tmp_path, step_key="source_discover")
    step_input = _source_discovery_input_get(execution_context)
    evidence_path = (
        f"{step_input.evidence_write_target.artifact_path}/../outside.json"
        if path_kind == "parent_escape"
        else (
            execution_context.result_dir / step_input.evidence_write_target.artifact_path / "absolute.json"
        ).as_posix()
    )
    evidence_file = (execution_context.result_dir / evidence_path).resolve()
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("{}\n", encoding="utf-8")
    source_discovery = _source_discovery_get(evidence_path=evidence_path)
    inventory = _source_inventory_get(source_discovery=source_discovery)

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("SourceDiscoveryValidator")().validate(
            execution_context,
            step_input,
            SourceDiscoveryResult(source_discovery_list=[source_discovery]),
            inventory,
        )

    assert "declared evidence_write_target.artifact_path" in _feedback_text_get(exc_info)


def test_table_extraction_validator_accepts_exact_public_result_and_artifacts(tmp_path: Path) -> None:
    """Accept one ordered extraction matching all persisted target and source fields."""

    execution_context = _execution_context_get(tmp_path, step_key="table_extract")
    source_evidence_path = "workflow/run/step/source_discover/evidence/source.json"
    source_discovery = _source_discovery_get(evidence_path=source_evidence_path)
    step_input = _table_extraction_input_get(execution_context, source_discovery=source_discovery)
    execplan_item = step_input.execplan_item_list[0]
    evidence_path = f"{execplan_item.evidence_write_target.artifact_path}/table.json"
    evidence_file = execution_context.result_dir / evidence_path
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("{}\n", encoding="utf-8")
    _valid_chart_write(Path(execplan_item.chart_filesystem_path))
    result = TableExtractionResult(
        browsing_error_list=[
            BrowsingError(
                error="A secondary table URL timed out.",
                url="https://www.defacto.com/size-guide",
            )
        ],
        table_extraction_list=[
            _table_extraction_artifact_get(
                execution_context,
                evidence_path=evidence_path,
                source_discovery=source_discovery,
            )
        ],
    )

    _validator_class_get("TableExtractionValidator")().validate(execution_context, step_input, result)


def test_table_extraction_validator_rejects_chart_without_size_measurement(tmp_path: Path) -> None:
    """Require each chart row to preserve its size label as one size measurement."""

    execution_context = _execution_context_get(tmp_path, step_key="table_extract")
    source_discovery = _source_discovery_get(evidence_path="source.json")
    step_input = _table_extraction_input_get(execution_context, source_discovery=source_discovery)
    execplan_item = step_input.execplan_item_list[0]
    evidence_path = f"{execplan_item.evidence_write_target.artifact_path}/table.json"
    evidence_file = execution_context.result_dir / evidence_path
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("{}\n", encoding="utf-8")
    chart_path = Path(execplan_item.chart_filesystem_path)
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart_path.write_text(
        json.dumps(
            {
                "description": "Women's upper garments.",
                "row_list": [
                    {
                        "measurement_list": [
                            {
                                "max_value": "92",
                                "min_value": "88",
                                "name": "Bust",
                                "unit": "cm",
                            }
                        ],
                        "size_label": "M",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("TableExtractionValidator")().validate(
            execution_context,
            step_input,
            TableExtractionResult(
                table_extraction_list=[
                    _table_extraction_artifact_get(
                        execution_context,
                        evidence_path=evidence_path,
                        source_discovery=source_discovery,
                    )
                ]
            ),
        )

    assert "Add one unit='size' measurement" in _feedback_text_get(exc_info)


@pytest.mark.parametrize("path_kind", ["parent_escape", "absolute"])
def test_table_extraction_validator_rejects_evidence_target_escape(tmp_path: Path, path_kind: str) -> None:
    """Reject non-relative or escaping paths at one execplan item's target.

    Args:
        tmp_path: Result root supplied by pytest.
        path_kind: Invalid public evidence path shape.
    """

    execution_context = _execution_context_get(tmp_path, step_key="table_extract")
    source_discovery = _source_discovery_get(evidence_path="source.json")
    step_input = _table_extraction_input_get(execution_context, source_discovery=source_discovery)
    execplan_item = step_input.execplan_item_list[0]
    evidence_path = (
        f"{execplan_item.evidence_write_target.artifact_path}/../outside.json"
        if path_kind == "parent_escape"
        else (
            execution_context.result_dir / execplan_item.evidence_write_target.artifact_path / "absolute.json"
        ).as_posix()
    )
    evidence_file = (execution_context.result_dir / evidence_path).resolve()
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text("{}\n", encoding="utf-8")
    _valid_chart_write(Path(execplan_item.chart_filesystem_path))

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("TableExtractionValidator")().validate(
            execution_context,
            step_input,
            TableExtractionResult(
                table_extraction_list=[
                    _table_extraction_artifact_get(
                        execution_context,
                        evidence_path=evidence_path,
                        source_discovery=source_discovery,
                    )
                ]
            ),
        )

    assert "declared evidence target" in _feedback_text_get(exc_info)


def test_coverage_decision_validator_preserves_complete_partition_invariant(tmp_path: Path) -> None:
    """Accept one complete covered/uncovered partition of requested product types."""

    execution_context = _execution_context_get(tmp_path, step_key="coverage_decide")
    table_extraction = TableExtractionArtifact(
        chart_path="workflow/run/step/table_extract/chart/women_upper.json",
        evidence_path_list=["workflow/run/step/table_extract/evidence/women_upper/table.json"],
        source_discovery=_source_discovery_get(
            evidence_path="workflow/run/step/table_extract/evidence/women_upper/table.json"
        ),
        source_type="official_brand_size_guide",
    )
    step_input = CoverageDecisionInput(
        verified_table_artifact_list=[table_extraction],
        workflow_input=_brand_workflow_input_get(product_type_list=["dress", "shoes"]),
    )
    result = CoverageDecisionResult(
        covered_product_type_list=[
            CoveredProductType(
                chart_path=table_extraction.chart_path,
                product_type="dress",
                reason="The verified upper-garment table covers dresses.",
            )
        ],
        uncovered_product_type_gap_list=[
            CoverageDecisionProductTypeGap(
                product_type="shoes",
                reason="No verified footwear table is available.",
            )
        ],
    )

    _validator_class_get("CoverageDecisionValidator")().validate(execution_context, step_input, result)


def test_coverage_decision_validator_rejects_omitted_product_type(tmp_path: Path) -> None:
    """Require every requested product type in exactly one result partition."""

    execution_context = _execution_context_get(tmp_path, step_key="coverage_decide")
    step_input = CoverageDecisionInput(
        verified_table_artifact_list=[],
        workflow_input=_brand_workflow_input_get(product_type_list=["dress"]),
    )

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("CoverageDecisionValidator")().validate(
            execution_context,
            step_input,
            CoverageDecisionResult(covered_product_type_list=[]),
        )

    assert "Classify every requested product type" in _feedback_text_get(exc_info)


def test_canonical_selection_validator_preserves_priority_invariant(tmp_path: Path) -> None:
    """Accept only the highest-priority candidate for one size group."""

    execution_context = _execution_context_get(tmp_path, step_key="canonical_select")
    low_priority_table = TableExtractionArtifact(
        chart_path="workflow/run/step/table_extract/chart/low.json",
        evidence_path_list=["workflow/run/step/table_extract/evidence/low.json"],
        source_discovery=SourceDiscovery(
            country_code_list=["GLOBAL"],
            evidence_path_list=["workflow/run/step/table_extract/evidence/low.json"],
            size_group_key="women_upper",
            source_title="Global guide",
            source_url="https://example.test/global",
        ),
        source_type="official_global_size_guide",
    )
    high_priority_table = low_priority_table.model_copy(
        update={
            "chart_path": "workflow/run/step/table_extract/chart/high.json",
            "source_discovery": low_priority_table.source_discovery.model_copy(
                update={
                    "country_code_list": ["TR"],
                    "source_title": "Turkish guide",
                    "source_url": "https://example.test/tr",
                }
            ),
            "source_type": "official_brand_size_guide",
        }
    )
    step_input = CanonicalSelectionInput(
        canonical_selection_candidate_list=[
            CanonicalSelectionCandidate(
                applicability_status="official_global",
                source_priority=10,
                table_extraction_artifact=low_priority_table,
            ),
            CanonicalSelectionCandidate(
                applicability_status="priority_country_official",
                source_priority=20,
                table_extraction_artifact=high_priority_table,
            ),
        ],
        workflow_input=_brand_workflow_input_get(),
    )

    _validator_class_get("CanonicalSelectionValidator")().validate(
        execution_context,
        step_input,
        CanonicalSelectionResult(
            canonical_selection_list=[CanonicalSelection(selected_chart_path=high_priority_table.chart_path)],
            unresolved_size_group_gap_list=[],
        ),
    )


def test_canonical_selection_validator_accepts_exact_python_derived_unresolved_group(tmp_path: Path) -> None:
    """Accept an omitted equal-priority group only with its exact Python-derived physical paths."""
    from brand_size_chart.model import CanonicalSelectionActionOutput

    execution_context = _execution_context_get(tmp_path, step_key="canonical_select")
    first_table = TableExtractionArtifact(
        chart_path="workflow/run/step/table_extract/chart/first.json",
        source_discovery=SourceDiscovery(
            country_code_list=["TR"],
            size_group_key="women_upper",
            source_title="First table",
            source_url="https://example.test/first",
        ),
        source_type="official_brand_size_guide",
    )
    second_table = first_table.model_copy(
        update={
            "chart_path": "workflow/run/step/table_extract/chart/second.json",
            "source_discovery": first_table.source_discovery.model_copy(
                update={
                    "source_title": "Second table",
                    "source_url": "https://example.test/second",
                }
            ),
        }
    )
    candidate_list = [
        CanonicalSelectionCandidate(
            applicability_status="priority_country_official",
            source_priority=20,
            table_extraction_artifact=first_table,
        ),
        CanonicalSelectionCandidate(
            applicability_status="priority_country_official",
            source_priority=20,
            table_extraction_artifact=second_table,
        ),
    ]
    step_input = CanonicalSelectionInput(
        canonical_selection_candidate_list=candidate_list,
        workflow_input=_brand_workflow_input_get(),
    )
    result = CanonicalSelectionResult.from_action_output(
        CanonicalSelectionActionOutput(canonical_selection_list=[]),
        candidate_list,
    )

    _validator_class_get("CanonicalSelectionValidator")().validate(execution_context, step_input, result)


def test_canonical_selection_validator_rejects_lower_priority_candidate(tmp_path: Path) -> None:
    """Return actionable feedback when a lower-priority chart is selected."""

    execution_context = _execution_context_get(tmp_path, step_key="canonical_select")
    low_priority_table = TableExtractionArtifact(
        chart_path="workflow/run/step/table_extract/chart/low.json",
        evidence_path_list=["workflow/run/step/table_extract/evidence/low.json"],
        source_discovery=SourceDiscovery(
            country_code_list=["GLOBAL"],
            evidence_path_list=["workflow/run/step/table_extract/evidence/low.json"],
            size_group_key="women_upper",
            source_title="Global guide",
            source_url="https://example.test/global",
        ),
        source_type="official_global_size_guide",
    )
    high_priority_table = low_priority_table.model_copy(
        update={
            "chart_path": "workflow/run/step/table_extract/chart/high.json",
            "source_discovery": low_priority_table.source_discovery.model_copy(
                update={
                    "country_code_list": ["TR"],
                    "source_title": "Turkish guide",
                    "source_url": "https://example.test/tr",
                }
            ),
            "source_type": "official_brand_size_guide",
        }
    )
    step_input = CanonicalSelectionInput(
        canonical_selection_candidate_list=[
            CanonicalSelectionCandidate(
                applicability_status="official_global",
                source_priority=10,
                table_extraction_artifact=low_priority_table,
            ),
            CanonicalSelectionCandidate(
                applicability_status="priority_country_official",
                source_priority=20,
                table_extraction_artifact=high_priority_table,
            ),
        ],
        workflow_input=_brand_workflow_input_get(),
    )

    with pytest.raises(StepResultValidationError) as exc_info:
        _validator_class_get("CanonicalSelectionValidator")().validate(
            execution_context,
            step_input,
            CanonicalSelectionResult(
                canonical_selection_list=[CanonicalSelection(selected_chart_path=low_priority_table.chart_path)],
                unresolved_size_group_gap_list=[],
            ),
        )

    assert "Select a highest-priority candidate" in _feedback_text_get(exc_info)
