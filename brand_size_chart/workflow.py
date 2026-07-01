"""DBOS workflow for brand size-chart source collection."""

from pathlib import Path

from dbos import DBOS, SetWorkflowID

from brand_size_chart.artifact import ArtifactLayout, ArtifactReferenceValidator, JsonArtifactWriter
from brand_size_chart.codex.runner import codex_stage_run
from brand_size_chart.identifier import dbos_identifier
from brand_size_chart.io import brand_list_parse
from brand_size_chart.model import (
    BrandInput,
    BrandListParseWarning,
    BrandResult,
    CanonicalSelectionResult,
    CoverageDecisionResult,
    PromptScope,
    RunResult,
    SourceDiscovery,
    SourceDiscoveryResult,
    SourceTypeSummary,
    TableExtraction,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.stage import (
    CanonicalSelectionStage,
    CoverageDecisionStage,
    SourceDiscoveryStage,
    TableExtractionStage,
    WorkflowRunPromptApplyStage,
)
from brand_size_chart.stage.base import MAX_STAGE_ATTEMPT_COUNT, prompt_file_text_get
from brand_size_chart.stage.semantic import stage_prompt_text_get
from brand_size_chart.validator import PromptScopeValidator

ARTIFACT_WRITER = JsonArtifactWriter()
PROMPT_SCOPE_VALIDATOR = PromptScopeValidator()


def _canonical_selection_result_get(table_extraction_list: list[TableExtraction]) -> CanonicalSelectionResult:
    """Return canonical selections from verified tables.

    Args:
        table_extraction_list: Verified table extractions.

    Returns:
        Canonical selection result.
    """

    return CanonicalSelectionStage.draft_result_get(table_extraction_list)


def _coverage_decision_result_get(
    *, prompt_scope: PromptScope, table_extraction_list: list[TableExtraction]
) -> CoverageDecisionResult:
    """Return coverage decisions for requested product types.

    Args:
        prompt_scope: Parsed prompt scope.
        table_extraction_list: Verified table extractions.

    Returns:
        Coverage decision result.
    """

    return CoverageDecisionStage.draft_result_get(
        prompt_scope=prompt_scope,
        table_extraction_list=table_extraction_list,
    )


def _coverage_decision_semantic_result_get(
    *,
    brand_input: BrandInput,
    prompt_scope: PromptScope,
    result_dir: Path,
    source_type: str,
    stage_dir: Path,
    table_extraction_list: list[TableExtraction],
) -> CoverageDecisionResult:
    """Return semantically verified coverage for requested product types.

    Args:
        brand_input: Parsed brand input.
        prompt_scope: Parsed prompt scope.
        result_dir: Root result directory.
        source_type: Source type that triggered this coverage check.
        stage_dir: Stage artifact directory.
        table_extraction_list: Verified table extractions.

    Returns:
        Verified coverage decision result.
    """

    return CoverageDecisionStage(
        brand_input=brand_input,
        codex_stage_run_callable=codex_stage_run,
        prompt_scope=prompt_scope,
        result_dir=result_dir,
        source_type=source_type,
        stage_dir=stage_dir,
        table_extraction_list=table_extraction_list,
    ).run()


def _prompt_file_text_get(prompt_name: str) -> str:
    """Return one static prompt file.

    Args:
        prompt_name: Prompt file stem.

    Returns:
        Prompt text.
    """

    return prompt_file_text_get(prompt_name)


def _prompt_scope_get(workflow_run_prompt: str) -> PromptScope:
    """Return a minimal draft scope for the free workflow-run prompt.

    Args:
        workflow_run_prompt: User-supplied free prompt text.

    Returns:
        Draft prompt scope.
    """

    prompt_text = workflow_run_prompt.strip()
    return PromptScope(shared_instruction=prompt_text)


def _prompt_scope_with_product_type_request_list_get(
    *, product_type_request_list: list[str], prompt_scope: PromptScope
) -> PromptScope:
    """Return prompt scope narrowed to one product type request list.

    Args:
        product_type_request_list: Current requested product types.
        prompt_scope: Original prompt scope.

    Returns:
        Prompt scope with the product type request list replaced.
    """

    return PromptScope(
        priority_country_code=prompt_scope.priority_country_code,
        product_type_request_list=product_type_request_list,
        scope_warning_list=prompt_scope.scope_warning_list,
        shared_instruction=prompt_scope.shared_instruction,
        source_type_allow_list=prompt_scope.source_type_allow_list,
        stage_instruction_list=prompt_scope.stage_instruction_list,
    )


def _source_type_prompt_scope_get(
    *,
    prompt_scope: PromptScope,
    remaining_product_type_list: list[str],
    source_type: str,
) -> PromptScope:
    """Return prompt scope for one source type.

    Args:
        prompt_scope: Root prompt scope.
        remaining_product_type_list: Product types still uncovered by earlier source types.
        source_type: Source type being executed.

    Returns:
        Source-type-local prompt scope.
    """

    if SOURCE_TYPE_REGISTRY.source_type_requires_product_type(source_type):
        return _prompt_scope_with_product_type_request_list_get(
            product_type_request_list=remaining_product_type_list,
            prompt_scope=prompt_scope,
        )
    return _prompt_scope_with_product_type_request_list_get(
        product_type_request_list=[],
        prompt_scope=prompt_scope,
    )


def _prompt_scope_stage_get(*, result_dir: Path, workflow_run_prompt: str) -> PromptScope:
    """Run `workflow_run_prompt_apply` and write its verification artifact.

    Args:
        result_dir: Root result directory.
        workflow_run_prompt: User-supplied prompt text.

    Returns:
        Parsed prompt scope.
    """

    return WorkflowRunPromptApplyStage(
        codex_stage_run_callable=codex_stage_run,
        result_dir=result_dir,
        workflow_run_prompt=workflow_run_prompt,
    ).run()


def _source_discovery_result_get(
    *,
    brand_input: BrandInput,
    browser_runtime_mcp_url: str,
    prompt_scope: PromptScope,
    result_dir: Path,
    secret_path: Path,
    source_priority: int,
    source_type: str,
    source_type_dir: Path,
) -> SourceDiscoveryResult:
    """Run source discovery from rendered evidence.

    Args:
        brand_input: Parsed brand input.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
        prompt_scope: Parsed prompt scope for source discovery.
        result_dir: Result root directory.
        secret_path: Secret DataSource path.
        source_priority: Source type priority.
        source_type: Source type key.
        source_type_dir: Source-type audit directory.

    Returns:
        Verified source discovery result.
    """

    return SourceDiscoveryStage(
        brand_input=brand_input,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        codex_stage_run_callable=codex_stage_run,
        prompt_scope=prompt_scope,
        result_dir=result_dir,
        secret_path=secret_path,
        source_priority=source_priority,
        source_type=source_type,
        source_type_dir=source_type_dir,
    ).run()


def _table_stage_run(
    *,
    brand_input: BrandInput,
    browser_runtime_mcp_url: str,
    prompt_scope: PromptScope,
    result_dir: Path,
    secret_path: Path,
    source_discovery: SourceDiscovery,
    source_type: str,
    source_type_dir: Path,
) -> TableExtraction:
    """Run table extraction plus verification for one table.

    Args:
        brand_input: Parsed brand input.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
        prompt_scope: Parsed prompt scope.
        result_dir: Root result directory.
        secret_path: Secret DataSource path.
        source_discovery: Verified source discovery.
        source_type: Source type key.
        source_type_dir: Source-type audit directory.

    Returns:
        Verified table extraction.
    """

    return TableExtractionStage(
        brand_input=brand_input,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        codex_stage_run_callable=codex_stage_run,
        prompt_scope=prompt_scope,
        result_dir=result_dir,
        secret_path=secret_path,
        source_discovery=source_discovery,
        source_type=source_type,
        source_type_dir=source_type_dir,
    ).run()


def _stage_prompt_text_get(
    *,
    attempt_index: int,
    draft_result_json_text: str,
    feedback_list: list[str],
    prompt_context: str,
    prompt_name: str,
    prompt_scope: PromptScope | None,
    previous_result_json_text: str,
    stage_key: str,
) -> str:
    """Build one Codex stage prompt from a static prompt file.

    Args:
        attempt_index: Stage attempt index.
        draft_result_json_text: Deterministic draft result JSON.
        feedback_list: Verification feedback from previous attempts.
        prompt_context: Stage-specific context.
        prompt_name: Static prompt file name stem.
        prompt_scope: Parsed workflow-run prompt scope.
        previous_result_json_text: Previous attempt result JSON, when present.
        stage_key: Stable stage key.

    Returns:
        Complete prompt text.
    """

    return stage_prompt_text_get(
        attempt_index=attempt_index,
        draft_result_json_text=draft_result_json_text,
        feedback_list=feedback_list,
        prompt_context=prompt_context,
        prompt_name=prompt_name,
        prompt_scope=prompt_scope,
        previous_result_json_text=previous_result_json_text,
        stage_key=stage_key,
    )


@DBOS.step()
def brand_selection_write_step(
    brand_input_payload: dict[str, object],
    prompt_scope_payload: dict[str, object],
    result_dir: str,
    table_extraction_payload_list: list[dict[str, object]],
    source_type_summary_payload_list: list[dict[str, object]],
) -> dict[str, object]:
    """Write brand-level coverage, canonical output, and brand result.

    Args:
        brand_input_payload: Serialized brand input.
        prompt_scope_payload: Serialized prompt scope.
        result_dir: Root result directory string.
        table_extraction_payload_list: Serialized verified table extractions.
        source_type_summary_payload_list: Serialized source-type summaries.

    Returns:
        Serialized brand result.
    """
    result_dir_path = Path(result_dir)
    artifact_layout = ArtifactLayout(result_dir_path)
    artifact_reference_validator = ArtifactReferenceValidator(result_dir_path)
    brand_input = BrandInput.model_validate(brand_input_payload)
    prompt_scope = PromptScope.model_validate(prompt_scope_payload)
    table_extraction_list = [
        TableExtraction.model_validate(table_extraction_payload)
        for table_extraction_payload in table_extraction_payload_list
    ]
    source_type_summary_list = [
        SourceTypeSummary.model_validate(source_type_summary_payload)
        for source_type_summary_payload in source_type_summary_payload_list
    ]
    source_type_error_list = [
        f"{source_type_summary.source_type}: {blocker}"
        for source_type_summary in source_type_summary_list
        if source_type_summary.state in {"failed", "blocked"}
        for blocker in source_type_summary.blocker_list
    ]
    coverage_result = _coverage_decision_semantic_result_get(
        brand_input=brand_input,
        prompt_scope=prompt_scope,
        result_dir=result_dir_path,
        source_type="final_selection",
        stage_dir=artifact_layout.brand_coverage_decision_dir(brand_input),
        table_extraction_list=table_extraction_list,
    )
    canonical_selection_result = CanonicalSelectionStage(
        brand_name=brand_input.parsed_brand_name,
        codex_stage_run_callable=codex_stage_run,
        prompt_scope=prompt_scope,
        result_dir=result_dir_path,
        stage_dir=artifact_layout.canonical_selection_dir(brand_input),
        table_extraction_list=table_extraction_list,
    ).run()
    table_extraction_by_size_group_key_map = {
        table_extraction.size_group_key: table_extraction for table_extraction in table_extraction_list
    }
    chart_path_list: list[str] = []
    for selection in canonical_selection_result.canonical_selection_list:
        table_extraction = table_extraction_by_size_group_key_map[selection.size_group_key]
        chart_path = artifact_layout.brand_size_chart_path(brand_input, selection.size_group_key)
        ARTIFACT_WRITER.write(chart_path, table_extraction.chart)
        chart_path_list.append(artifact_layout.artifact_path(chart_path))

    brand_result_path = artifact_layout.brand_result_path(brand_input)
    brand_error_list = [*source_type_error_list, *coverage_result.uncovered_product_type_list]
    brand_result = BrandResult(
        audit_artifact_path_list=[artifact_layout.artifact_path(brand_result_path)],
        canonical_selection_list=canonical_selection_result.canonical_selection_list,
        error_list=brand_error_list,
        message=(
            "One or more source types failed."
            if source_type_error_list
            else (
                "Canonical tables selected."
                if canonical_selection_result.canonical_selection_list
                else "No verified canonical source tables found."
            )
        ),
        parsed_brand_key=brand_input.parsed_brand_key,
        parsed_brand_name=brand_input.parsed_brand_name,
        size_chart_path_list=chart_path_list,
        source_type_summary_list=source_type_summary_list,
        status=(
            "failed"
            if source_type_error_list
            else ("success" if canonical_selection_result.canonical_selection_list else "skipped")
        ),
    )
    manifest_path = artifact_layout.brand_manifest_path(brand_input)
    ARTIFACT_WRITER.write(manifest_path, brand_result)
    ARTIFACT_WRITER.write(brand_result_path, brand_result)
    artifact_reference_validator.path_list_validate(
        path_list=brand_result.size_chart_path_list,
        stage_key="brand_result",
    )
    artifact_reference_validator.path_list_validate(
        path_list=[artifact_layout.artifact_path(manifest_path)],
        stage_key="brand_result",
    )
    return brand_result.model_dump(mode="json")


@DBOS.step()
def coverage_decision_write_step(
    brand_input_payload: dict[str, object],
    prompt_scope_payload: dict[str, object],
    result_dir: str,
    source_type: str,
    table_extraction_payload_list: list[dict[str, object]],
) -> dict[str, object]:
    """Write intermediate coverage decision after one source type.

    Args:
        brand_input_payload: Serialized brand input.
        prompt_scope_payload: Serialized prompt scope.
        result_dir: Root result directory string.
        source_type: Source type key.
        table_extraction_payload_list: Serialized verified table extractions.

    Returns:
        Serialized coverage decision result.
    """
    brand_input = BrandInput.model_validate(brand_input_payload)
    prompt_scope = PromptScope.model_validate(prompt_scope_payload)
    result_dir_path = Path(result_dir)
    artifact_layout = ArtifactLayout(result_dir_path)
    table_extraction_list = [
        TableExtraction.model_validate(table_extraction_payload)
        for table_extraction_payload in table_extraction_payload_list
    ]
    coverage_result = _coverage_decision_semantic_result_get(
        brand_input=brand_input,
        prompt_scope=prompt_scope,
        result_dir=result_dir_path,
        source_type=source_type,
        stage_dir=artifact_layout.coverage_decision_dir(brand_input, source_type),
        table_extraction_list=table_extraction_list,
    )
    return coverage_result.model_dump(mode="json")


@DBOS.workflow()
def brand_size_chart_brand(
    workflow_run_id: str,
    brand_input_payload: dict[str, object],
    browser_runtime_mcp_url: str,
    prompt_scope_payload: dict[str, object],
    result_dir: str,
    secret_ref: str,
) -> dict[str, object]:
    """Process one brand with source-type child workflows.

    Args:
        workflow_run_id: Stable workflow run identifier.
        brand_input_payload: Serialized brand input.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
        prompt_scope_payload: Serialized prompt scope.
        result_dir: Root result directory string.
        secret_ref: Secret DataSource path string.

    Returns:
        Serialized brand result.
    """
    brand_input = BrandInput.model_validate(brand_input_payload)
    prompt_scope = PromptScope.model_validate(prompt_scope_payload)
    source_type_list = _source_type_list_get(prompt_scope)
    remaining_product_type_list = list(prompt_scope.product_type_request_list)
    source_type_summary_payload_list: list[dict[str, object]] = []
    table_extraction_payload_list: list[dict[str, object]] = []
    queue_name = dbos_identifier("queue", workflow_run_id)
    for source_type in source_type_list:
        if (
            SOURCE_TYPE_REGISTRY.source_type_requires_product_type(source_type)
            and prompt_scope.product_type_request_list
        ):
            if not remaining_product_type_list:
                break
        source_type_prompt_scope = _source_type_prompt_scope_get(
            prompt_scope=prompt_scope,
            remaining_product_type_list=remaining_product_type_list,
            source_type=source_type,
        )
        with SetWorkflowID(dbos_identifier("workflow", workflow_run_id, brand_input.parsed_brand_name, source_type)):
            source_type_handle = DBOS.enqueue_workflow(
                queue_name,
                brand_size_chart_source_type,
                workflow_run_id,
                brand_input.model_dump(mode="json"),
                browser_runtime_mcp_url,
                source_type_prompt_scope.model_dump(mode="json"),
                result_dir,
                secret_ref,
                source_type,
            )
        source_type_result = source_type_handle.get_result()
        source_type_summary_payload_list.append(source_type_result["source_type_summary"])
        table_extraction_payload_list.extend(source_type_result["table_extraction_list"])
        if not prompt_scope.product_type_request_list and source_type_result["table_extraction_list"]:
            break
        if prompt_scope.product_type_request_list and table_extraction_payload_list:
            coverage_prompt_scope = _prompt_scope_with_product_type_request_list_get(
                product_type_request_list=remaining_product_type_list,
                prompt_scope=prompt_scope,
            )
            coverage_check_payload = coverage_decision_write_step(
                brand_input.model_dump(mode="json"),
                coverage_prompt_scope.model_dump(mode="json"),
                result_dir,
                source_type,
                table_extraction_payload_list,
            )
            coverage_check = CoverageDecisionResult.model_validate(coverage_check_payload)
            remaining_product_type_list = coverage_check.uncovered_product_type_list

    return brand_selection_write_step(
        brand_input.model_dump(mode="json"),
        prompt_scope.model_dump(mode="json"),
        result_dir,
        table_extraction_payload_list,
        source_type_summary_payload_list,
    )


@DBOS.workflow()
def brand_size_chart_run(
    workflow_run_id: str,
    brand_list_text: str,
    secret_ref: str,
    result_dir: str,
    workflow_run_prompt: str,
    browser_runtime_mcp_url: str,
) -> dict[str, object]:
    """Run root workflow orchestration for one brand list.

    Args:
        workflow_run_id: Stable workflow run identifier.
        brand_list_text: Raw brand-list input text.
        secret_ref: Secret DataSource path string.
        result_dir: Root result directory string.
        workflow_run_prompt: User-supplied prompt text.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.

    Returns:
        Serialized `RunResult` payload.
    """
    parse_result = brand_list_parse(brand_list_text)
    prompt_scope = prompt_scope_write_step(result_dir, workflow_run_prompt)
    queue_name = dbos_identifier("queue", workflow_run_id)
    brand_result_payload_list: list[dict[str, object]] = []
    for brand_input in parse_result.brand_list:
        with SetWorkflowID(dbos_identifier("workflow", workflow_run_id, brand_input.parsed_brand_name)):
            brand_handle = DBOS.enqueue_workflow(
                queue_name,
                brand_size_chart_brand,
                workflow_run_id,
                brand_input.model_dump(mode="json"),
                browser_runtime_mcp_url,
                prompt_scope,
                result_dir,
                secret_ref,
            )
        brand_result_payload_list.append(brand_handle.get_result())
    return run_result_write_step(
        workflow_run_id,
        result_dir,
        brand_result_payload_list,
        prompt_scope,
        [warning.model_dump(mode="json") for warning in parse_result.warning_list],
    )


@DBOS.workflow()
def brand_size_chart_source_type(
    workflow_run_id: str,
    brand_input_payload: dict[str, object],
    browser_runtime_mcp_url: str,
    prompt_scope_payload: dict[str, object],
    result_dir: str,
    secret_ref: str,
    source_type: str,
) -> dict[str, object]:
    """Process one source type with table child workflows.

    Args:
        workflow_run_id: Stable workflow run identifier.
        brand_input_payload: Serialized brand input.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
        prompt_scope_payload: Serialized prompt scope.
        result_dir: Root result directory string.
        secret_ref: Secret DataSource path string.
        source_type: Source type key.

    Returns:
        Serialized source-type summary and verified table list.
    """
    brand_input = BrandInput.model_validate(brand_input_payload)
    prompt_scope = PromptScope.model_validate(prompt_scope_payload)
    verified_table_extraction_payload_list: list[dict[str, object]] = []
    blocker_list: list[str] = []
    try:
        discovery_result_payload = source_discovery_write_step(
            brand_input.model_dump(mode="json"),
            browser_runtime_mcp_url,
            prompt_scope.model_dump(mode="json"),
            result_dir,
            secret_ref,
            source_type,
        )
        discovery_result = SourceDiscoveryResult.model_validate(discovery_result_payload)
        if discovery_result.status == "failed":
            blocker_list.extend(discovery_result.error_list or [discovery_result.message])
        else:
            queue_name = dbos_identifier("queue", workflow_run_id)
            for source_discovery in discovery_result.discovered_source_list:
                with SetWorkflowID(
                    dbos_identifier(
                        "workflow",
                        workflow_run_id,
                        brand_input.parsed_brand_name,
                        source_type,
                        source_discovery.size_group_key,
                    )
                ):
                    table_handle = DBOS.enqueue_workflow(
                        queue_name,
                        brand_size_chart_table,
                        brand_input.model_dump(mode="json"),
                        browser_runtime_mcp_url,
                        prompt_scope.model_dump(mode="json"),
                        result_dir,
                        secret_ref,
                        source_type,
                        source_discovery.model_dump(mode="json"),
                    )
                verified_table_extraction_payload_list.append(table_handle.get_result())
    except RuntimeError as exc:
        blocker_list.append(f"{type(exc).__name__}: {exc}")
    source_type_summary_payload = source_type_summary_write_step(
        brand_input.model_dump(mode="json"),
        result_dir,
        source_type,
        verified_table_extraction_payload_list,
        blocker_list,
    )
    return {
        "source_type_summary": source_type_summary_payload,
        "table_extraction_list": verified_table_extraction_payload_list,
    }


@DBOS.workflow()
def brand_size_chart_table(
    brand_input_payload: dict[str, object],
    browser_runtime_mcp_url: str,
    prompt_scope_payload: dict[str, object],
    result_dir: str,
    secret_ref: str,
    source_type: str,
    source_discovery_payload: dict[str, object],
) -> dict[str, object]:
    """Process one size-chart table.

    Args:
        brand_input_payload: Serialized brand input.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
        prompt_scope_payload: Serialized prompt scope.
        result_dir: Root result directory string.
        secret_ref: Secret DataSource path string.
        source_type: Source type key.
        source_discovery_payload: Serialized source discovery.

    Returns:
        Serialized verified table extraction.
    """
    return table_stage_write_step(
        brand_input_payload,
        browser_runtime_mcp_url,
        prompt_scope_payload,
        result_dir,
        secret_ref,
        source_type,
        source_discovery_payload,
    )


brand_size_chart_workflow = brand_size_chart_run


@DBOS.step()
def prompt_scope_write_step(result_dir: str, workflow_run_prompt: str) -> dict[str, object]:
    """Write workflow prompt scope artifacts.

    Args:
        result_dir: Root result directory string.
        workflow_run_prompt: User-supplied prompt text.

    Returns:
        Serialized prompt scope.
    """
    prompt_scope = _prompt_scope_stage_get(
        result_dir=Path(result_dir),
        workflow_run_prompt=workflow_run_prompt,
    )
    return prompt_scope.model_dump(mode="json")


@DBOS.step()
def run_result_write_step(
    workflow_run_id: str,
    result_dir: str,
    brand_result_payload_list: list[dict[str, object]],
    prompt_scope_payload: dict[str, object],
    warning_payload_list: list[dict[str, object]],
) -> dict[str, object]:
    """Write root run result artifact.

    Args:
        workflow_run_id: Workflow run identifier.
        result_dir: Root result directory string.
        brand_result_payload_list: Serialized brand results.
        prompt_scope_payload: Serialized prompt scope.
        warning_payload_list: Serialized brand-list warnings.

    Returns:
        Serialized run result.
    """
    brand_result_list = [BrandResult.model_validate(payload) for payload in brand_result_payload_list]
    failed_brand_result_list = [brand_result for brand_result in brand_result_list if brand_result.status == "failed"]
    run_error_list = [
        f"{brand_result.parsed_brand_name}: {error}"
        for brand_result in failed_brand_result_list
        for error in brand_result.error_list
    ]
    run_result = RunResult(
        brand_result_list=brand_result_list,
        error_list=run_error_list,
        message="Workflow run completed with failed brands." if failed_brand_result_list else "Workflow run completed.",
        prompt_scope=PromptScope.model_validate(prompt_scope_payload),
        result_dir=result_dir,
        status="failed" if failed_brand_result_list else "success",
        warning_list=[BrandListParseWarning.model_validate(payload) for payload in warning_payload_list],
        workflow_run_id=workflow_run_id,
    )
    ARTIFACT_WRITER.write(ArtifactLayout(Path(result_dir)).run_result_path(), run_result)
    return run_result.model_dump(mode="json")


def run_failure_result_write(
    result_dir: Path,
    *,
    error_code: str,
    error_message: str,
    workflow_run_id: str,
) -> RunResult:
    """Write root failure result for entrypoint-level startup errors.

    Args:
        result_dir: Root result directory.
        error_code: Stable error class name.
        error_message: Error detail.
        workflow_run_id: Workflow run identifier.

    Returns:
        Written run result.
    """
    error_text = f"{error_code}: {error_message}"
    run_result = RunResult(
        brand_result_list=[],
        error_list=[error_text],
        message="Workflow run failed before DBOS root workflow completed.",
        prompt_scope=PromptScope(),
        result_dir=str(result_dir),
        status="failed",
        warning_list=[],
        workflow_run_id=workflow_run_id,
    )
    ARTIFACT_WRITER.write(ArtifactLayout(result_dir).run_result_path(), run_result)
    return run_result


@DBOS.step()
def source_discovery_write_step(
    brand_input_payload: dict[str, object],
    browser_runtime_mcp_url: str,
    prompt_scope_payload: dict[str, object],
    result_dir: str,
    secret_ref: str,
    source_type: str,
) -> dict[str, object]:
    """Write source discovery result and verification.

    Args:
        brand_input_payload: Serialized brand input.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
        prompt_scope_payload: Serialized prompt scope.
        result_dir: Root result directory string.
        secret_ref: Secret DataSource path string.
        source_type: Source type key.

    Returns:
        Serialized source discovery result.
    """
    brand_input = BrandInput.model_validate(brand_input_payload)
    prompt_scope = PromptScope.model_validate(prompt_scope_payload)
    result_dir_path = Path(result_dir)
    artifact_layout = ArtifactLayout(result_dir_path)
    source_type_dir = artifact_layout.source_type_dir(brand_input, source_type)
    discovery_result = _source_discovery_result_get(
        brand_input=brand_input,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        prompt_scope=prompt_scope,
        result_dir=result_dir_path,
        secret_path=Path(secret_ref),
        source_priority=SOURCE_TYPE_REGISTRY.source_type_priority_get(source_type),
        source_type=source_type,
        source_type_dir=source_type_dir,
    )
    return discovery_result.model_dump(mode="json")


@DBOS.step()
def source_type_summary_write_step(
    brand_input_payload: dict[str, object],
    result_dir: str,
    source_type: str,
    table_extraction_payload_list: list[dict[str, object]],
    blocker_list: list[str],
) -> dict[str, object]:
    """Write source-type summary.

    Args:
        brand_input_payload: Serialized brand input.
        result_dir: Root result directory string.
        source_type: Source type key.
        table_extraction_payload_list: Serialized verified table extractions.
        blocker_list: Source-type blocker messages collected during discovery or extraction.

    Returns:
        Serialized source-type summary.
    """
    brand_input = BrandInput.model_validate(brand_input_payload)
    result_dir_path = Path(result_dir)
    artifact_layout = ArtifactLayout(result_dir_path)
    artifact_reference_validator = ArtifactReferenceValidator(result_dir_path)
    table_extraction_list = [
        TableExtraction.model_validate(table_extraction_payload)
        for table_extraction_payload in table_extraction_payload_list
    ]
    table_result_path_by_size_group_key_map = {
        table_extraction.size_group_key: artifact_layout.artifact_path(
            artifact_layout.table_extraction_result_path(
                brand_input,
                source_type,
                table_extraction.size_group_key,
            )
        )
        for table_extraction in table_extraction_list
    }
    evidence_manifest_path_list = [
        artifact_layout.artifact_path(artifact_path)
        for artifact_path in [
            artifact_layout.stage_result_path(artifact_layout.source_discovery_dir(brand_input, source_type)),
            artifact_layout.stage_verification_path(artifact_layout.source_discovery_dir(brand_input, source_type)),
        ]
        if artifact_path.is_file()
    ]
    summary = SourceTypeSummary(
        blocker_list=blocker_list,
        evidence_manifest_path_list=evidence_manifest_path_list,
        source_priority=SOURCE_TYPE_REGISTRY.source_type_priority_get(source_type),
        source_type=source_type,
        state="failed" if blocker_list else ("passed" if table_extraction_list else "skipped"),
        table_result_path_by_size_group_key_map=table_result_path_by_size_group_key_map,
        verified_size_group_key_list=list(table_result_path_by_size_group_key_map),
    )
    if sorted(summary.verified_size_group_key_list) != sorted(summary.table_result_path_by_size_group_key_map):
        raise RuntimeError(f"source_type_summary key mismatch for {source_type}")
    artifact_reference_validator.path_list_validate(
        path_list=list(summary.table_result_path_by_size_group_key_map.values()),
        stage_key="source_type_summary",
    )
    artifact_reference_validator.path_list_validate(
        path_list=summary.evidence_manifest_path_list,
        stage_key="source_type_summary",
    )
    ARTIFACT_WRITER.write(artifact_layout.source_type_summary_result_path(brand_input, source_type), summary)
    return summary.model_dump(mode="json")


@DBOS.step()
def table_stage_write_step(
    brand_input_payload: dict[str, object],
    browser_runtime_mcp_url: str,
    prompt_scope_payload: dict[str, object],
    result_dir: str,
    secret_ref: str,
    source_type: str,
    source_discovery_payload: dict[str, object],
) -> dict[str, object]:
    """Write table extraction and verification artifacts.

    Args:
        brand_input_payload: Serialized brand input.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
        prompt_scope_payload: Serialized prompt scope.
        result_dir: Root result directory string.
        secret_ref: Secret DataSource path string.
        source_type: Source type key.
        source_discovery_payload: Serialized source discovery.

    Returns:
        Serialized verified table extraction.
    """
    brand_input = BrandInput.model_validate(brand_input_payload)
    prompt_scope = PromptScope.model_validate(prompt_scope_payload)
    result_dir_path = Path(result_dir)
    artifact_layout = ArtifactLayout(result_dir_path)
    source_type_dir = artifact_layout.source_type_dir(brand_input, source_type)
    table_extraction = _table_stage_run(
        brand_input=brand_input,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        prompt_scope=prompt_scope,
        result_dir=result_dir_path,
        secret_path=Path(secret_ref),
        source_discovery=SourceDiscovery.model_validate(source_discovery_payload),
        source_type=source_type,
        source_type_dir=source_type_dir,
    )
    return table_extraction.model_dump(mode="json")


def _source_type_list_get(prompt_scope: PromptScope) -> list[str]:
    """Return source types in execution order.

    Args:
        prompt_scope: Parsed prompt scope.

    Returns:
        Source type list.
    """
    PROMPT_SCOPE_VALIDATOR.validate(prompt_scope)
    return SOURCE_TYPE_REGISTRY.source_type_list_get(
        have_product_type_request=bool(prompt_scope.product_type_request_list),
        source_type_allow_list=prompt_scope.source_type_allow_list,
    )
