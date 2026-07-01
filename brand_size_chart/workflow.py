"""DBOS workflow for brand size-chart source collection."""

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TypeVar

from dbos import DBOS, SetWorkflowID
from pydantic import BaseModel

from brand_size_chart.codex_stage import codex_stage_run
from brand_size_chart.identifier import dbos_identifier
from brand_size_chart.io import brand_list_parse, json_artifact_write
from brand_size_chart.model import (
    APPLICABILITY_STATUS_CANONICAL_SET,
    BrandInput,
    BrandListParseWarning,
    BrandResult,
    CanonicalSelection,
    CanonicalSelectionResult,
    CoverageDecision,
    CoverageDecisionResult,
    PromptScope,
    RunResult,
    SourceDiscovery,
    SourceDiscoveryResult,
    SourceTypeSummary,
    StageVerification,
    TableExtraction,
)
from brand_size_chart.source_extractor import source_discovery_result_get, table_extraction_from_discovery_get
from brand_size_chart.source_type import (
    PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET,
    SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP,
    SOURCE_TYPE_PRIORITY_BY_KEY_MAP,
)

MAX_STAGE_ATTEMPT_COUNT = 3
SIZE_GROUP_KEY_PROMPT_NAME_SET = {
    "discovery",
    "extraction",
    "selection",
    "verification",
}
STAGE_KEY_SET = {
    "canonical_selection",
    "coverage_decision",
    "source_discovery",
    "table_extraction",
    "workflow_run_prompt_apply",
}
_ResultModelT = TypeVar("_ResultModelT", bound=BaseModel)


def _artifact_path(path: Path, result_dir: Path) -> str:
    """Return one result-dir-relative artifact path.

    Args:
        path: Artifact path.
        result_dir: Result root directory.

    Returns:
        Relative artifact path as POSIX text.
    """
    return path.relative_to(result_dir).as_posix()


def _artifact_reference_list_validate(*, evidence_path_list: list[str], result_dir: Path, stage_key: str) -> None:
    """Validate that stage evidence references point to existing run artifacts.

    Args:
        evidence_path_list: Result-dir-relative artifact references.
        result_dir: Root result directory.
        stage_key: Stable stage key for diagnostics.

    Raises:
        RuntimeError: If one evidence reference is absent or points outside the run directory.
    """
    if not evidence_path_list:
        raise RuntimeError(f"Stage {stage_key} returned no evidence_path_list.")
    for evidence_path_text in evidence_path_list:
        evidence_path = result_dir / evidence_path_text
        try:
            evidence_path.relative_to(result_dir)
        except ValueError as exc:
            raise RuntimeError(f"Stage {stage_key} returned evidence outside result_dir: {evidence_path_text}") from exc
        if not evidence_path.exists():
            raise RuntimeError(f"Stage {stage_key} returned missing evidence artifact: {evidence_path_text}")


def _artifact_path_list_validate(*, path_list: list[str], result_dir: Path, stage_key: str) -> None:
    """Validate that output artifact references point to existing run artifacts.

    Args:
        path_list: Result-dir-relative artifact references.
        result_dir: Root result directory.
        stage_key: Stable stage key for diagnostics.

    Raises:
        RuntimeError: If one artifact reference is absent or points outside the run directory.
    """
    for path_text in path_list:
        artifact_path = result_dir / path_text
        try:
            artifact_path.relative_to(result_dir)
        except ValueError as exc:
            raise RuntimeError(f"Stage {stage_key} returned artifact outside result_dir: {path_text}") from exc
        if not artifact_path.exists():
            raise RuntimeError(f"Stage {stage_key} returned missing artifact: {path_text}")


def _brand_audit_dir(result_dir: Path, brand_input: BrandInput) -> Path:
    """Return audit directory for one brand.

    Args:
        result_dir: Result root directory.
        brand_input: Parsed brand input.

    Returns:
        Brand audit directory.
    """
    return result_dir / "brand_size_chart_audit" / "brand" / brand_input.parsed_brand_key


def _brand_output_dir(result_dir: Path, brand_input: BrandInput) -> Path:
    """Return canonical output directory for one brand.

    Args:
        result_dir: Result root directory.
        brand_input: Parsed brand input.

    Returns:
        Brand output directory.
    """
    return result_dir / "brand_size_chart" / "brand" / brand_input.parsed_brand_key


def _canonical_selection_result_get(table_extraction_list: list[TableExtraction]) -> CanonicalSelectionResult:
    """Return canonical selections from verified tables.

    Args:
        table_extraction_list: Verified table extractions.

    Returns:
        Canonical selection result.
    """
    conflict_list: list[str] = []
    selected_extraction_by_size_group_key_map: dict[str, TableExtraction] = {}
    for table_extraction in table_extraction_list:
        if table_extraction.applicability_status not in APPLICABILITY_STATUS_CANONICAL_SET:
            conflict_list.append(
                f"Table {table_extraction.size_group_key} from {table_extraction.source_url} skipped because "
                f"applicability_status={table_extraction.applicability_status} is not canonical."
            )
            continue
        existing_extraction = selected_extraction_by_size_group_key_map.get(table_extraction.size_group_key)
        if existing_extraction is None:
            selected_extraction_by_size_group_key_map[table_extraction.size_group_key] = table_extraction
            continue

        existing_priority = SOURCE_TYPE_PRIORITY_BY_KEY_MAP[existing_extraction.source_type]
        current_priority = SOURCE_TYPE_PRIORITY_BY_KEY_MAP[table_extraction.source_type]
        if current_priority > existing_priority:
            conflict_list.append(
                "Higher priority table selected for "
                f"{table_extraction.size_group_key}: {table_extraction.source_type} "
                f"priority={current_priority} replaced {existing_extraction.source_type} priority={existing_priority}."
            )
            selected_extraction_by_size_group_key_map[table_extraction.size_group_key] = table_extraction
            continue
        if current_priority == existing_priority:
            conflict_list.append(
                "Duplicate verified table with same priority for "
                f"{table_extraction.size_group_key}: {existing_extraction.source_url} and {table_extraction.source_url}."
            )

    canonical_selection_list = [
        CanonicalSelection(
            conflict_list=[conflict for conflict in conflict_list if f" {size_group_key}:" in conflict],
            selected_source_priority=SOURCE_TYPE_PRIORITY_BY_KEY_MAP[table_extraction.source_type],
            selected_source_type=table_extraction.source_type,
            selected_source_url=table_extraction.source_url,
            size_group_key=size_group_key,
        )
        for size_group_key, table_extraction in sorted(selected_extraction_by_size_group_key_map.items())
    ]
    return CanonicalSelectionResult(
        canonical_selection_list=canonical_selection_list,
        conflict_list=conflict_list,
        message="Canonical tables selected." if canonical_selection_list else "No verified source tables found.",
        status="success" if canonical_selection_list else "failed",
    )


def _canonical_selection_error_list_get(
    *, canonical_selection_result: CanonicalSelectionResult, table_extraction_list: list[TableExtraction]
) -> list[str]:
    """Return canonical-selection structural errors.

    Args:
        canonical_selection_result: Candidate canonical-selection result.
        table_extraction_list: Verified table extractions available for selection.

    Returns:
        Canonical-selection error list.
    """
    selected_size_group_key_set = {
        selection.size_group_key for selection in canonical_selection_result.canonical_selection_list
    }
    eligible_size_group_key_set = {
        table_extraction.size_group_key
        for table_extraction in table_extraction_list
        if table_extraction.applicability_status in APPLICABILITY_STATUS_CANONICAL_SET
    }
    missing_size_group_key_list = sorted(eligible_size_group_key_set - selected_size_group_key_set)
    if not missing_size_group_key_list:
        return []
    return ["canonical_selection missing eligible size_group_key values: " + ", ".join(missing_size_group_key_list)]


def _canonical_selection_result_validate(
    *, canonical_selection_result: CanonicalSelectionResult, table_extraction_list: list[TableExtraction]
) -> None:
    """Validate canonical-selection structural consistency.

    Args:
        canonical_selection_result: Verified canonical-selection result.
        table_extraction_list: Verified table extractions available for selection.

    Raises:
        RuntimeError: If selection points to missing or inconsistent table data.
    """
    error_list = _canonical_selection_error_list_get(
        canonical_selection_result=canonical_selection_result,
        table_extraction_list=table_extraction_list,
    )
    if error_list:
        raise RuntimeError("; ".join(error_list))

    table_extraction_by_size_group_key_map = {
        table_extraction.size_group_key: table_extraction for table_extraction in table_extraction_list
    }
    selected_size_group_key_set: set[str] = set()
    for selection in canonical_selection_result.canonical_selection_list:
        if selection.size_group_key in selected_size_group_key_set:
            raise RuntimeError(f"canonical_selection duplicate size_group_key: {selection.size_group_key}")
        selected_size_group_key_set.add(selection.size_group_key)
        table_extraction = table_extraction_by_size_group_key_map.get(selection.size_group_key)
        if table_extraction is None:
            raise RuntimeError(f"canonical_selection missing table extraction: {selection.size_group_key}")
        expected_priority = SOURCE_TYPE_PRIORITY_BY_KEY_MAP[selection.selected_source_type]
        if selection.selected_source_priority != expected_priority:
            raise RuntimeError(
                f"canonical_selection priority mismatch for {selection.size_group_key}: "
                f"{selection.selected_source_priority} != {expected_priority}"
            )
        if selection.selected_source_type != table_extraction.source_type:
            raise RuntimeError(
                f"canonical_selection source_type mismatch for {selection.size_group_key}: "
                f"{selection.selected_source_type} != {table_extraction.source_type}"
            )


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
    available_size_group_key_list = [table_extraction.size_group_key for table_extraction in table_extraction_list]
    coverage_decision_list = [
        CoverageDecision(
            is_covered=True,
            reason="Verified source table exists.",
            size_group_key=size_group_key,
        )
        for size_group_key in available_size_group_key_list
    ]
    uncovered_product_type_list = [
        product_type
        for product_type in prompt_scope.product_type_request_list
        if not any(product_type in size_group_key for size_group_key in available_size_group_key_list)
    ]
    return CoverageDecisionResult(
        coverage_decision_list=coverage_decision_list,
        message="Coverage decision completed." if table_extraction_list else "No verified tables for coverage.",
        status="success" if table_extraction_list else "skipped",
        uncovered_product_type_list=uncovered_product_type_list,
    )


def _coverage_decision_result_validate(
    *, coverage_decision_result: CoverageDecisionResult, prompt_scope: PromptScope
) -> None:
    """Validate coverage decision against the requested product-type scope.

    Args:
        coverage_decision_result: Coverage decision result.
        prompt_scope: Current prompt scope.

    Raises:
        RuntimeError: If coverage output mentions product types outside the requested scope.
    """
    requested_product_type_set = set(prompt_scope.product_type_request_list)
    uncovered_product_type_set = set(coverage_decision_result.uncovered_product_type_list)
    if not uncovered_product_type_set.issubset(requested_product_type_set):
        unexpected_product_type_list = sorted(uncovered_product_type_set - requested_product_type_set)
        raise RuntimeError(f"coverage_decision returned unexpected product types: {unexpected_product_type_list}")


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
    verified_table_summary_text = "\n".join(
        (
            f"- {table_extraction.size_group_key}: source_type={table_extraction.source_type}; "
            f"source_title={table_extraction.source_title}; "
            f"product_type_hint_list={table_extraction.product_type_hint_list}; "
            f"applicability_description={table_extraction.applicability_description}; "
            f"chart_description={table_extraction.chart.description}"
        )
        for table_extraction in table_extraction_list
    )
    coverage_decision_result = _semantic_stage_run(
        draft_result=_coverage_decision_result_get(
            prompt_scope=prompt_scope,
            table_extraction_list=table_extraction_list,
        ),
        model_class=CoverageDecisionResult,
        prompt_context=(
            f"Brand: {brand_input.parsed_brand_name}\n"
            f"Source type just completed: {source_type}\n"
            f"Requested product types: {prompt_scope.product_type_request_list}\n"
            "Check whether verified tables cover requested product types. Use product_type_hint_list, "
            "applicability_description, source_title, size_group_key, chart description, and evidence references. "
            "A product type may be considered covered only when the table explicitly applies to it. If one table "
            "clearly covers multiple requested product types, mark all of those product types covered. Do not infer "
            "coverage from weak substring matches alone. Obviously irrelevant non-sized products may be ignored with "
            "warnings. Verified table summary is supplied below as stage input; do not report missing evidence when "
            "this list is non-empty. Refine the draft coverage decision from these verified tables instead of "
            "discarding it.\n"
            f"Verified table summary:\n{verified_table_summary_text if verified_table_summary_text else '- none'}\n"
        ),
        prompt_scope=prompt_scope,
        prompt_name="selection",
        result_dir=result_dir,
        stage_dir=stage_dir,
        stage_key="coverage_decision",
    )
    _coverage_decision_result_validate(
        coverage_decision_result=coverage_decision_result,
        prompt_scope=prompt_scope,
    )
    return coverage_decision_result


def _prompt_file_text_get(prompt_name: str) -> str:
    """Return one static prompt file.

    Args:
        prompt_name: Prompt file stem.

    Returns:
        Prompt text.
    """
    prompt_dir = Path(__file__).parent / "prompt"
    prompt_text = (prompt_dir / f"{prompt_name}.md").read_text(encoding="utf-8")
    if prompt_name not in SIZE_GROUP_KEY_PROMPT_NAME_SET:
        return prompt_text
    return f"{(prompt_dir / 'size_group_key.md').read_text(encoding='utf-8')}\n\n{prompt_text}"


def _prompt_scope_get(workflow_run_prompt: str) -> PromptScope:
    """Return a minimal draft scope for the free workflow-run prompt.

    Args:
        workflow_run_prompt: User-supplied free prompt text.

    Returns:
        Draft prompt scope.
    """
    prompt_text = workflow_run_prompt.strip()
    return PromptScope(shared_instruction=prompt_text)


def _prompt_scope_validate(prompt_scope: PromptScope) -> None:
    """Validate prompt-derived execution keys.

    Args:
        prompt_scope: Parsed prompt scope.

    Raises:
        RuntimeError: If prompt scope contains unknown source types or stage keys.
    """
    unknown_source_type_list = [
        source_type
        for source_type in prompt_scope.source_type_allow_list
        if source_type not in SOURCE_TYPE_PRIORITY_BY_KEY_MAP
    ]
    if unknown_source_type_list:
        raise RuntimeError(f"Unknown source_type_allow_list values: {unknown_source_type_list}")
    unknown_stage_key_list = [
        stage_instruction.stage_key
        for stage_instruction in prompt_scope.stage_instruction_list
        if stage_instruction.stage_key not in STAGE_KEY_SET
    ]
    if unknown_stage_key_list:
        raise RuntimeError(f"Unknown stage_instruction stage_key values: {unknown_stage_key_list}")
    leaked_product_type_list = [
        product_type
        for product_type in prompt_scope.product_type_request_list
        if product_type.casefold() in prompt_scope.shared_instruction.casefold()
    ]
    if leaked_product_type_list:
        raise RuntimeError(
            "shared_instruction must not repeat product_type_request_list values: "
            f"{sorted(leaked_product_type_list)}"
        )


def _prompt_scope_error_list_get(prompt_scope: PromptScope) -> list[str]:
    """Return prompt-scope mechanical validation errors.

    Args:
        prompt_scope: Parsed prompt scope.

    Returns:
        Validation error list.
    """
    try:
        _prompt_scope_validate(prompt_scope)
    except RuntimeError as exc:
        return [str(exc)]
    return []


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
    if source_type in PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET:
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
    prompt_scope = _prompt_scope_get(workflow_run_prompt)
    stage_dir = result_dir / "brand_size_chart_audit" / "run" / "workflow_run_prompt_apply"
    if not workflow_run_prompt.strip():
        _prompt_scope_validate(prompt_scope)
        json_artifact_write(stage_dir / "result.json", prompt_scope)
        json_artifact_write(
            stage_dir / "verification.json",
            StageVerification(
                artifact_path_list=[_artifact_path(stage_dir / "result.json", result_dir)],
                message="Empty workflow prompt requires no rewrite.",
                stage_key="workflow_run_prompt_apply",
                status="success",
            ),
        )
        return prompt_scope
    allowed_source_type_text = "\n".join(f"- {source_type}" for source_type in sorted(SOURCE_TYPE_PRIORITY_BY_KEY_MAP))
    stage_context = (
        "Allowed source_type keys are:\n"
        f"{allowed_source_type_text}\n\n"
        "If the workflow prompt asks for all supported source types, leave source_type_allow_list empty. "
        "Use source_type_allow_list only when the prompt names exact allowed source_type keys from the list above.\n\n"
        "Extract priority_country_code from the workflow prompt when the user names a priority country or market. "
        "Normalize it to one ISO 3166 alpha-2 uppercase country code. Use TR when the workflow prompt does not "
        "select another priority country.\n\n"
        f"Workflow run prompt:\n{workflow_run_prompt}\n\n"
        f"Draft prompt scope JSON:\n{prompt_scope.model_dump_json(indent=2)}\n"
    )
    prompt_scope = _semantic_stage_run(
        draft_result=prompt_scope,
        model_class=PromptScope,
        prompt_context=stage_context,
        prompt_scope=prompt_scope,
        prompt_name="apply",
        result_dir=result_dir,
        result_error_list_get=_prompt_scope_error_list_get,
        stage_dir=stage_dir,
        stage_key="workflow_run_prompt_apply",
    )
    _prompt_scope_validate(prompt_scope)
    return prompt_scope


def _semantic_stage_run(
    *,
    browser_access: bool = False,
    browser_runtime_mcp_url: str = "",
    draft_result: _ResultModelT,
    model_class: type[_ResultModelT],
    prompt_context: str,
    prompt_scope: PromptScope | None,
    prompt_name: str,
    result_error_list_get: Callable[[_ResultModelT], list[str]] | None = None,
    result_dir: Path,
    stage_dir: Path,
    stage_key: str,
) -> _ResultModelT:
    """Run one main stage plus its verification stage.

    Args:
        browser_access: Whether Codex may use browser/MCP tools and write evidence artifacts.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL for browser stages.
        draft_result: Deterministic draft result used as initial stage input.
        model_class: Pydantic result model.
        prompt_context: Stage-specific prompt context.
        prompt_scope: Parsed prompt scope relevant to this stage.
        prompt_name: Static prompt file name stem.
        result_error_list_get: Optional mechanical validator for a semantically verified result.
        result_dir: Root result directory.
        stage_dir: Stage artifact directory.
        stage_key: Stable stage key.
    Returns:
        Verified stage result.

    Raises:
        RuntimeError: If verification does not pass within the retry limit.
    """
    feedback_list: list[str] = []
    draft_result_json_text = draft_result.model_dump_json(indent=2)
    previous_result_json_text = ""
    stage_dir.mkdir(parents=True, exist_ok=True)
    for attempt_index in range(1, MAX_STAGE_ATTEMPT_COUNT + 1):
        result = codex_stage_run(
            allow_user_config=browser_access,
            browser_runtime_mcp_url=browser_runtime_mcp_url,
            model_class=model_class,
            prompt_text=_stage_prompt_text_get(
                attempt_index=attempt_index,
                draft_result_json_text=draft_result_json_text,
                feedback_list=feedback_list,
                prompt_context=prompt_context,
                prompt_name=prompt_name,
                prompt_scope=prompt_scope,
                previous_result_json_text=previous_result_json_text,
                stage_key=stage_key,
            ),
            result_dir=result_dir,
            stage_dir=stage_dir,
            stage_name=stage_key,
        )

        result_path = stage_dir / "result.json"
        json_artifact_write(result_path, result)
        artifact_path_list = [_artifact_path(result_path, result_dir)]
        previous_result_json_text = result.model_dump_json(indent=2)
        verification = _stage_verification_get(
            artifact_path_list=artifact_path_list,
            prompt_context=prompt_context,
            prompt_scope=prompt_scope,
            result=result,
            result_dir=result_dir,
            stage_dir=stage_dir,
            stage_key=stage_key,
            browser_access=browser_access,
            browser_runtime_mcp_url=browser_runtime_mcp_url,
        )
        if verification.status == "success" and result_error_list_get:
            result_error_list = result_error_list_get(result)
            if result_error_list:
                verification = _stage_guard_verification_get(
                    artifact_path_list=artifact_path_list,
                    error_list=result_error_list,
                    stage_key=stage_key,
                )
        json_artifact_write(stage_dir / "verification.json", verification)
        if verification.status == "success":
            return result
        feedback_list = verification.feedback_list or verification.error_list

    feedback_text = "; ".join(feedback_list)
    if feedback_text:
        raise RuntimeError(
            f"Stage {stage_key} did not pass verification after {MAX_STAGE_ATTEMPT_COUNT} attempts: {feedback_text}"
        )
    raise RuntimeError(f"Stage {stage_key} did not pass verification after {MAX_STAGE_ATTEMPT_COUNT} attempts.")


def _source_discovery_result_error_list_get(
    discovery_result: SourceDiscoveryResult,
    *,
    expected_source_priority: int,
    expected_source_type: str,
    prompt_scope: PromptScope,
    result_dir: Path,
    stage_dir: Path,
) -> list[str]:
    """Return source-discovery mechanical validation errors.

    Args:
        discovery_result: Source discovery result to validate.
        expected_source_priority: Registry priority for the source type being processed.
        expected_source_type: Source type being processed.
        prompt_scope: Current prompt scope.
        result_dir: Root result directory.
        stage_dir: Source-discovery stage artifact directory.

    Returns:
        Mechanical validation errors.
    """
    try:
        _source_discovery_result_validate(
            discovery_result=discovery_result,
            expected_source_priority=expected_source_priority,
            expected_source_type=expected_source_type,
            prompt_scope=prompt_scope,
            result_dir=result_dir,
            stage_dir=stage_dir,
        )
    except RuntimeError as exc:
        return [str(exc)]
    return []


def _source_discovery_country_selection_validate(
    *, discovery_result: SourceDiscoveryResult, prompt_scope: PromptScope
) -> None:
    """Validate the source-discovery market selection ladder.

    Args:
        discovery_result: Verified source discovery result.
        prompt_scope: Current prompt scope.

    Raises:
        RuntimeError: If `discovered_source_list` mixes lower-priority market scopes into a higher-priority result.
    """
    priority_country_code = prompt_scope.priority_country_code
    priority_country_source_list = [
        source_discovery
        for source_discovery in discovery_result.discovered_source_list
        if priority_country_code in source_discovery.country_code_list
    ]
    if priority_country_source_list:
        non_priority_country_size_group_key_list = [
            source_discovery.size_group_key
            for source_discovery in discovery_result.discovered_source_list
            if priority_country_code not in source_discovery.country_code_list
        ]
        if non_priority_country_size_group_key_list:
            raise RuntimeError(
                "source_discovery contains non-priority country candidates while priority country tables exist: "
                f"priority_country_code={priority_country_code}; "
                f"size_group_key_list={sorted(non_priority_country_size_group_key_list)}"
            )
        return

    global_source_list = [
        source_discovery
        for source_discovery in discovery_result.discovered_source_list
        if "GLOBAL" in source_discovery.country_code_list
    ]
    if global_source_list:
        non_global_size_group_key_list = [
            source_discovery.size_group_key
            for source_discovery in discovery_result.discovered_source_list
            if "GLOBAL" not in source_discovery.country_code_list
        ]
        if non_global_size_group_key_list:
            raise RuntimeError(
                "source_discovery contains non-global candidates while global tables exist: "
                f"priority_country_code={priority_country_code}; "
                f"size_group_key_list={sorted(non_global_size_group_key_list)}"
            )
        return

    non_europe_size_group_key_list = [
        source_discovery.size_group_key
        for source_discovery in discovery_result.discovered_source_list
        if "EU" not in source_discovery.country_code_list
    ]
    if non_europe_size_group_key_list:
        raise RuntimeError(
            "source_discovery contains candidates that are neither priority-country, global, nor verified European "
            f"consensus tables: priority_country_code={priority_country_code}; "
            f"size_group_key_list={sorted(non_europe_size_group_key_list)}"
        )


def _source_discovery_result_validate(
    *,
    discovery_result: SourceDiscoveryResult,
    expected_source_priority: int,
    expected_source_type: str,
    prompt_scope: PromptScope,
    result_dir: Path,
    stage_dir: Path,
) -> None:
    """Validate source-discovery structural consistency after semantic verification.

    Args:
        discovery_result: Verified source discovery result.
        expected_source_priority: Registry priority for the source type being processed.
        expected_source_type: Source type being processed.
        prompt_scope: Current prompt scope.
        result_dir: Root result directory.
        stage_dir: Source-discovery stage artifact directory.

    Raises:
        RuntimeError: If discovery is structurally inconsistent.
    """
    if discovery_result.source_type != expected_source_type:
        raise RuntimeError(
            f"source_discovery source_type mismatch: {discovery_result.source_type} != {expected_source_type}"
        )
    if discovery_result.status == "failed":
        if discovery_result.discovered_source_list:
            raise RuntimeError("failed source_discovery must not return discovered_source_list items")
        if not discovery_result.error_list:
            raise RuntimeError("failed source_discovery must include concrete error_list blockers")
        inventory_path = stage_dir / "evidence" / "source_surface_inventory.json"
        if not inventory_path.is_file():
            raise RuntimeError("failed source_discovery must write canonical evidence/source_surface_inventory.json")
        return
    if discovery_result.status != "success":
        raise RuntimeError(f"source_discovery status must be success or failed, got {discovery_result.status}")
    if not discovery_result.discovered_source_list:
        raise RuntimeError("source_discovery returned no discovered_source_list items")
    _source_discovery_country_selection_validate(
        discovery_result=discovery_result,
        prompt_scope=prompt_scope,
    )
    size_group_key_set: set[str] = set()
    requested_product_type_set = set(prompt_scope.product_type_request_list)
    for source_discovery in discovery_result.discovered_source_list:
        if source_discovery.size_group_key in size_group_key_set:
            raise RuntimeError(f"source_discovery duplicate size_group_key: {source_discovery.size_group_key}")
        size_group_key_set.add(source_discovery.size_group_key)
        if source_discovery.source_type != expected_source_type:
            raise RuntimeError(
                f"source_discovery item source_type mismatch for {source_discovery.size_group_key}: "
                f"{source_discovery.source_type} != {expected_source_type}"
            )
        if source_discovery.source_priority != expected_source_priority:
            raise RuntimeError(
                f"source_discovery source_priority mismatch for {source_discovery.size_group_key}: "
                f"{source_discovery.source_priority} != {expected_source_priority}"
            )
        if not source_discovery.source_url.strip():
            raise RuntimeError(f"source_discovery returned empty source_url for {source_discovery.size_group_key}")
        if not source_discovery.source_title.strip():
            raise RuntimeError(f"source_discovery returned empty source_title for {source_discovery.size_group_key}")
        if requested_product_type_set:
            hint_product_type_set = set(source_discovery.product_type_hint_list)
            if not hint_product_type_set.issubset(requested_product_type_set):
                unexpected_product_type_list = sorted(hint_product_type_set - requested_product_type_set)
                raise RuntimeError(
                    f"source_discovery returned unexpected product_type_hint_list for "
                    f"{source_discovery.size_group_key}: {unexpected_product_type_list}"
                )
        _artifact_reference_list_validate(
            evidence_path_list=source_discovery.evidence_path_list,
            result_dir=result_dir,
            stage_key="source_discovery",
        )


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
    draft_result = _source_discovery_draft_result_get(
        brand_input=brand_input,
        result_dir=result_dir,
        secret_path=secret_path,
        source_priority=source_priority,
        source_type=source_type,
        source_type_dir=source_type_dir,
    )
    evidence_dir = source_type_dir / "source_discovery" / "evidence"
    requested_product_type_text = (
        "\n".join(f"- {product_type}" for product_type in prompt_scope.product_type_request_list) or "- none"
    )
    prompt_context = (
        f"Brand: {brand_input.parsed_brand_name}\n"
        f"Source type: {source_type}\n"
        f"Source priority: {source_priority}\n"
        f"Priority country code: {prompt_scope.priority_country_code}\n"
        f"Requested product types:\n{requested_product_type_text}\n"
        f"Source type instruction: {SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP[source_type]}\n"
        f"Evidence directory: {_artifact_path(evidence_dir, result_dir)}\n"
        "Use the configured browser to search, open, and interact with source pages. "
        "All source-page and source-data loading must go through the configured browser. "
        "Do not use non-browser loading mechanisms; direct HTTP, curl, requests, wget, and Python scraping are "
        "examples of forbidden replacements, not an exhaustive list. "
        "Treat source discovery as a bounded workflow, not a best-effort search. First build one canonical "
        "browser-backed source-surface inventory artifact named source_surface_inventory.json for this source type "
        "under the evidence directory. "
        "The canonical inventory must include discovery queries, candidate URLs, opened URLs, accepted tables, "
        "rejected URLs, rejection reasons, blocking browser errors, and evidence paths. Update that canonical "
        "inventory on every retry before handoff; attempt-only inventory artifacts are allowed only as extra "
        "diagnostics and must not replace the canonical inventory verified by the workflow. "
        "In the canonical inventory, candidate_urls must contain only concrete source candidates that may directly "
        "hold size-chart data for this source type. Search pages, navigation pages, home pages, sitemap pages, FAQ "
        "index pages, help index pages, and other helper surfaces are discovery surfaces, not candidate URLs. Record "
        "helper surfaces in opened or rejected inventory entries with evidence and reasons, but do not list them as "
        "candidate URLs unless that exact opened URL itself contains a concrete size-chart table candidate. Do not "
        "put broad search-result or category product URL inventories in candidate_urls; if you collect broad product "
        "URL lists for sampling or coverage, store them separately as evidence fields such as search_result_url_list, "
        "category_product_url_list, or another clearly named non-candidate list, and record the sampling or rejection "
        "rule that selected the concrete candidate URLs. "
        "When this source type uses official brand sources, identify browser-visible official host variants before "
        "concluding that the source type has no tables. Host variants include global brand domains, country-code "
        "brand domains, and locale paths that browser evidence shows as brand-owned. Open relevant official host "
        "roots and inspect visible navigation, footer, search, help, FAQ, sitemap, and static-page links. Do not "
        "stop after one official domain variant fails when another brand-owned host variant is visible or inferable "
        "from browser-visible evidence. "
        "For each discovered official host, infer the browser-visible language and market from the opened page "
        "itself, then search for size-chart concepts in that language and market. Use the site's own search, "
        "visible navigation, footer/help pages, sitemap pages, and browser-opened public search results when they "
        "are available. Localized terms such as Turkish `beden rehberi` and `beden tablosu` are search terms, not "
        "URL templates. Record the localized queries and the opened or rejected results in the canonical inventory. "
        "Do not conclude that an official host has no size guide until localized size-chart term searches for that "
        "host are represented in the canonical inventory. "
        "Apply one market-selection ladder for discovered_source_list. First search for the priority country code "
        "from PromptScope. If priority country tables exist for this source type, discovered_source_list must "
        "contain only items whose country_code_list contains that priority country code. If no priority "
        "country table exists, return global tables only when global tables exist and mark them with "
        "country_code_list=['GLOBAL']. If neither priority country nor global tables exist, return European country "
        "tables only after verifying that the relevant official European country tables do not differ; mark such "
        "verified consensus candidates with country_code_list=['EU']. If European country tables differ, return "
        "status='failed' with exact conflicting country codes, URLs, and size_group_key values instead of picking "
        "one locale. "
        "Write each relevant browser evidence artifact under the evidence directory and reference those paths in "
        "evidence_path_list. Return every unique size-chart source candidate backed by evidence files. "
        "One SourceDiscovery item represents one concrete size chart table, not one page. "
        "If one page contains multiple size chart tables with different size_group_key values, return one "
        "discovered_source_list item per table. Inside one source type, return at most one discovered_source_list item "
        "for one size_group_key; when another page, locale, or asset exposes an equivalent table for the same "
        "size_group_key, record that duplicate or equivalent table in inventory evidence and source notes, but do not "
        "return a second candidate with the same size_group_key. "
        "The size_group_key must follow the Size Group Key Contract from the static prompt. Page-level or aggregate "
        "keys such as all, guide, page, or brand-wide bundle keys are forbidden. "
        "Requested product types are coverage targets only; they must not filter or narrow discovered_source_list, "
        "accepted_tables, or table extraction scope. When an opened source page contains concrete tables that are "
        "outside the requested product types, still return those tables and leave product_type_hint_list empty unless "
        "the evidence explicitly covers one requested product type. "
        "If requested product types are present, search for every requested product type in this source type. "
        "If one discovered table clearly applies to multiple requested product types, return one candidate and set "
        "product_type_hint_list to exactly the requested product types that are explicitly covered by the evidence. "
        "Do not include weakly inferred product types in product_type_hint_list. "
        "If at least one concrete table candidate is evidence-backed, return status='success' even when some "
        "requested product types remain uncovered; record missing requested product types in error_list with "
        "browser-backed reasons and keep accepted candidates in discovered_source_list. "
        "Respect the source type boundary exactly; do not return product-page measurement sections for "
        "official_brand_size_guide. "
        "Do not return status='skipped'. Empty discovered_source_list is forbidden in real discovery. "
        "If no concrete table can be returned after browser-backed inventory, return status='failed' "
        "with detailed blocker errors and canonical inventory evidence so this source type is recorded as failed "
        "and the workflow can continue to the next source type. Do not invent candidates.\n\n"
        f"Draft source_discovery JSON:\n{draft_result.model_dump_json(indent=2)}\n"
    )

    discovery_result = _semantic_stage_run(
        browser_access=True,
        draft_result=draft_result,
        model_class=SourceDiscoveryResult,
        prompt_context=prompt_context,
        prompt_scope=prompt_scope,
        prompt_name="discovery",
        result_error_list_get=partial(
            _source_discovery_result_error_list_get,
            expected_source_priority=source_priority,
            expected_source_type=source_type,
            prompt_scope=prompt_scope,
            result_dir=result_dir,
            stage_dir=source_type_dir / "source_discovery",
        ),
        result_dir=result_dir,
        stage_dir=source_type_dir / "source_discovery",
        stage_key="source_discovery",
        browser_runtime_mcp_url=browser_runtime_mcp_url,
    )
    return discovery_result


def _table_extraction_validate(
    *, result_dir: Path, source_discovery: SourceDiscovery, table_extraction: TableExtraction
) -> None:
    """Validate table-extraction structural consistency after semantic verification.

    Args:
        result_dir: Root result directory.
        source_discovery: Source discovery that owns the table identity.
        table_extraction: Verified table extraction result.

    Raises:
        RuntimeError: If table extraction is structurally inconsistent.
    """
    if table_extraction.source_type != source_discovery.source_type:
        raise RuntimeError(
            f"table_extraction source_type mismatch for {source_discovery.size_group_key}: "
            f"{table_extraction.source_type} != {source_discovery.source_type}"
        )
    if table_extraction.source_url != source_discovery.source_url:
        raise RuntimeError(
            f"table_extraction source_url mismatch for {source_discovery.size_group_key}: "
            f"{table_extraction.source_url} != {source_discovery.source_url}"
        )
    if table_extraction.size_group_key != source_discovery.size_group_key:
        raise RuntimeError(
            f"table_extraction size_group_key mismatch: "
            f"{table_extraction.size_group_key} != {source_discovery.size_group_key}"
        )
    _artifact_reference_list_validate(
        evidence_path_list=table_extraction.evidence_path_list,
        result_dir=result_dir,
        stage_key="table_extraction",
    )
    if not table_extraction.chart.row_list:
        raise RuntimeError(f"table_extraction returned an empty chart for {table_extraction.size_group_key}")
    for row_index, chart_row in enumerate(table_extraction.chart.row_list):
        if not chart_row.size_label.strip():
            raise RuntimeError(f"table_extraction returned empty size_label at row {row_index}")
        if not chart_row.measurement_list:
            raise RuntimeError(f"table_extraction returned empty measurement_list at row {row_index}")
        for measurement_index, measurement in enumerate(chart_row.measurement_list):
            if not measurement.name.strip():
                raise RuntimeError(
                    f"table_extraction returned empty measurement name at row {row_index}, "
                    f"measurement {measurement_index}"
                )
            if not measurement.unit.strip():
                raise RuntimeError(
                    f"table_extraction returned empty measurement unit at row {row_index}, "
                    f"measurement {measurement_index}"
                )
            if not measurement.min_value.strip():
                raise RuntimeError(
                    f"table_extraction returned empty min_value at row {row_index}, measurement {measurement_index}"
                )
            if not measurement.max_value.strip():
                raise RuntimeError(
                    f"table_extraction returned empty max_value at row {row_index}, measurement {measurement_index}"
                )


def _table_extraction_error_list_get(
    table_extraction: TableExtraction, *, result_dir: Path, source_discovery: SourceDiscovery
) -> list[str]:
    """Return table-extraction mechanical validation errors.

    Args:
        table_extraction: Table extraction result to validate.
        result_dir: Root result directory.
        source_discovery: Source discovery that owns the table identity.

    Returns:
        Mechanical validation errors.
    """
    try:
        _table_extraction_validate(
            result_dir=result_dir,
            source_discovery=source_discovery,
            table_extraction=table_extraction,
        )
    except RuntimeError as exc:
        return [str(exc)]
    return []


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
        result_dir: Result root directory.
        secret_path: Secret DataSource path.
        source_discovery: Verified source discovery.
        source_type: Source type key.
        source_type_dir: Source-type audit directory.
    Returns:
        Verified table extraction.
    """
    table_extraction = table_extraction_from_discovery_get(
        brand_input=brand_input,
        result_dir=result_dir,
        source_discovery=source_discovery,
    )
    table_stage_dir = source_type_dir / "size_chart" / table_extraction.size_group_key / "table_extraction"
    evidence_dir = table_stage_dir / "evidence"
    prompt_context = (
        f"Brand: {brand_input.parsed_brand_name}\n"
        f"Source type: {source_type}\n"
        f"Source title: {table_extraction.source_title}\n"
        f"Source URL: {table_extraction.source_url}\n"
        f"Evidence directory: {_artifact_path(evidence_dir, result_dir)}\n"
        f"Source discovery evidence paths: {source_discovery.evidence_path_list}\n"
        "All source-page and source-data loading must go through the configured browser. "
        "Use browser screenshots, DOM extracts, rendered table text, downloaded browser-visible assets, and existing "
        "discovery evidence. Do not use non-browser loading mechanisms; direct HTTP, curl, requests, wget, and Python "
        "scraping are examples of forbidden replacements, not an exhaustive list. Write browser evidence under the "
        "evidence directory and reference those paths in evidence_path_list. Extract the table exactly from "
        "browser-visible evidence and preserve all source columns that belong to the size chart when that column has "
        "a value in the source row. Do not emit measurement entries for blank source cells; describe systematic blank "
        "cells in the chart description when needed. For size-system or label-equivalence columns such as US/UK, IT, "
        "EU, TR/EU, alpha size, numeric size, or age labels, keep the column as a measurement and use unit='size' "
        "unless the source gives a more specific physical unit. Height, length, weight, body, and garment measurements "
        "must keep their physical source unit such as cm, inch, kg, or lb even when the source label is a generic word "
        "like size or taille.\n\n"
        f"Draft table_extraction JSON:\n{table_extraction.model_dump_json(indent=2)}\n"
    )
    table_result = _semantic_stage_run(
        browser_access=True,
        draft_result=table_extraction,
        model_class=TableExtraction,
        prompt_context=prompt_context,
        prompt_scope=prompt_scope,
        prompt_name="extraction",
        result_error_list_get=partial(
            _table_extraction_error_list_get,
            result_dir=result_dir,
            source_discovery=source_discovery,
        ),
        result_dir=result_dir,
        stage_dir=table_stage_dir,
        stage_key="table_extraction",
        browser_runtime_mcp_url=browser_runtime_mcp_url,
    )
    return table_result


def _source_discovery_draft_result_get(
    *,
    brand_input: BrandInput,
    result_dir: Path,
    secret_path: Path,
    source_priority: int,
    source_type: str,
    source_type_dir: Path,
) -> SourceDiscoveryResult:
    """Return draft source discovery for one source type.

    Args:
        brand_input: Parsed brand input.
        result_dir: Result root directory.
        secret_path: Secret DataSource path.
        source_priority: Source type priority.
        source_type: Source type key.
        source_type_dir: Source-type audit directory.

    Returns:
        Draft source discovery result.
    """
    _ = source_priority
    return source_discovery_result_get(
        brand_input=brand_input,
        result_dir=result_dir,
        secret_path=secret_path,
        source_type=source_type,
        source_type_dir=source_type_dir,
    )


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
    feedback_text = "\n".join(f"- {feedback}" for feedback in feedback_list)
    shared_instruction = prompt_scope.shared_instruction if prompt_scope else ""
    stage_instruction_list = [
        stage_instruction.instruction
        for stage_instruction in (prompt_scope.stage_instruction_list if prompt_scope else [])
        if stage_instruction.stage_key == stage_key
    ]
    stage_instruction_text = "\n".join(f"- {stage_instruction}" for stage_instruction in stage_instruction_list)
    return (
        f"{_prompt_file_text_get(prompt_name)}\n\n"
        f"Stage: {stage_key}\n"
        f"Attempt: {attempt_index}\n\n"
        f"Workflow run shared instruction:\n{shared_instruction if shared_instruction else '- none'}\n\n"
        f"Stage-specific instruction:\n{stage_instruction_text if stage_instruction_text else '- none'}\n\n"
        f"{prompt_context}\n\n"
        f"Draft stage result JSON:\n{draft_result_json_text}\n\n"
        f"Previous stage result JSON:\n{previous_result_json_text if previous_result_json_text else '- none'}\n\n"
        f"Verification feedback from previous attempt:\n{feedback_text if feedback_text else '- none'}\n"
    )


def _stage_guard_verification_get(
    *, artifact_path_list: list[str], error_list: list[str], stage_key: str
) -> StageVerification:
    """Return failed verification for mechanical stage-result validation.

    Args:
        artifact_path_list: Artifact paths produced by the main stage.
        error_list: Mechanical validation errors.
        stage_key: Stable stage key.

    Returns:
        Failed stage verification.
    """
    return StageVerification(
        artifact_path_list=artifact_path_list,
        error_list=error_list,
        feedback_list=error_list,
        message="Stage mechanical validation failed.",
        stage_key=stage_key,
        status="failed",
    )


def _stage_verification_get(
    *,
    artifact_path_list: list[str],
    browser_access: bool,
    browser_runtime_mcp_url: str,
    prompt_context: str,
    prompt_scope: PromptScope | None,
    result: BaseModel,
    result_dir: Path,
    stage_dir: Path,
    stage_key: str,
) -> StageVerification:
    """Return semantic verification for one stage result.

    Args:
        artifact_path_list: Artifact paths produced by the main stage.
        browser_access: Whether Codex verification may use configured browser/MCP tools.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL for browser verification.
        prompt_context: Stage prompt context.
        prompt_scope: Parsed prompt scope relevant to this stage.
        result: Main stage result.
        result_dir: Root result directory.
        stage_dir: Stage artifact directory.
        stage_key: Stable stage key.
    Returns:
        Stage verification.
    """
    draft_verification = StageVerification(
        artifact_path_list=artifact_path_list,
        message="Stage verification passed.",
        stage_key=stage_key,
        status="success",
    )
    verification_prompt = (
        f"{_prompt_file_text_get('verification')}\n\n"
        f"Stage: {stage_key}\n\n"
        "You must return a StageVerification JSON object only. Do not fail because structured output prevents progress "
        "messages. Use browser tools silently only when source evidence must be re-opened; otherwise verify from the "
        "artifact files listed below. If the stage result is schema-valid, evidence-backed, and semantically consistent "
        "with the prompt context, return the supplied draft verification success.\n\n"
        f"{prompt_context}\n\n"
        f"Stage result JSON:\n{result.model_dump_json(indent=2)}\n\n"
        f"Draft verification JSON:\n{draft_verification.model_dump_json(indent=2)}\n"
    )
    return codex_stage_run(
        allow_user_config=browser_access,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        model_class=StageVerification,
        prompt_text=verification_prompt,
        result_dir=result_dir,
        stage_dir=stage_dir,
        stage_name=f"{stage_key}_verification",
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
        result_dir=Path(result_dir),
        source_type="final_selection",
        stage_dir=_brand_audit_dir(Path(result_dir), brand_input) / "coverage_decision",
        table_extraction_list=table_extraction_list,
    )
    canonical_selection_result = _semantic_stage_run(
        draft_result=_canonical_selection_result_get(table_extraction_list),
        model_class=CanonicalSelectionResult,
        prompt_context=(
            f"Brand: {brand_input.parsed_brand_name}\n"
            "Select canonical tables by source_priority and record conflicts with all compared decision values.\n"
        ),
        prompt_scope=prompt_scope,
        prompt_name="selection",
        result_error_list_get=lambda result: _canonical_selection_error_list_get(
            canonical_selection_result=result,
            table_extraction_list=table_extraction_list,
        ),
        result_dir=Path(result_dir),
        stage_dir=_brand_audit_dir(Path(result_dir), brand_input) / "canonical_selection",
        stage_key="canonical_selection",
    )
    _canonical_selection_result_validate(
        canonical_selection_result=canonical_selection_result,
        table_extraction_list=table_extraction_list,
    )
    table_extraction_by_size_group_key_map = {
        table_extraction.size_group_key: table_extraction for table_extraction in table_extraction_list
    }
    chart_path_list: list[str] = []
    for selection in canonical_selection_result.canonical_selection_list:
        table_extraction = table_extraction_by_size_group_key_map[selection.size_group_key]
        chart_path = (
            _brand_output_dir(Path(result_dir), brand_input) / "size_chart" / f"{selection.size_group_key}.json"
        )
        json_artifact_write(chart_path, table_extraction.chart)
        chart_path_list.append(_artifact_path(chart_path, Path(result_dir)))

    brand_result_path = _brand_audit_dir(Path(result_dir), brand_input) / "brand_result" / "result.json"
    brand_error_list = [*source_type_error_list, *coverage_result.uncovered_product_type_list]
    brand_result = BrandResult(
        audit_artifact_path_list=[_artifact_path(brand_result_path, Path(result_dir))],
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
    json_artifact_write(_brand_output_dir(Path(result_dir), brand_input) / "manifest.json", brand_result)
    json_artifact_write(brand_result_path, brand_result)
    _artifact_path_list_validate(
        path_list=brand_result.size_chart_path_list,
        result_dir=Path(result_dir),
        stage_key="brand_result",
    )
    _artifact_path_list_validate(
        path_list=[
            _artifact_path(_brand_output_dir(Path(result_dir), brand_input) / "manifest.json", Path(result_dir))
        ],
        result_dir=Path(result_dir),
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
    table_extraction_list = [
        TableExtraction.model_validate(table_extraction_payload)
        for table_extraction_payload in table_extraction_payload_list
    ]
    coverage_result = _coverage_decision_semantic_result_get(
        brand_input=brand_input,
        prompt_scope=prompt_scope,
        result_dir=Path(result_dir),
        source_type=source_type,
        stage_dir=_brand_audit_dir(Path(result_dir), brand_input) / "source_type" / source_type / "coverage_decision",
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
        if source_type in PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET and prompt_scope.product_type_request_list:
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
    json_artifact_write(Path(result_dir) / "brand_size_chart_audit" / "run" / "result.json", run_result)
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
    json_artifact_write(result_dir / "brand_size_chart_audit" / "run" / "result.json", run_result)
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
    source_type_dir = _brand_audit_dir(Path(result_dir), brand_input) / "source_type" / source_type
    discovery_result = _source_discovery_result_get(
        brand_input=brand_input,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        prompt_scope=prompt_scope,
        result_dir=Path(result_dir),
        secret_path=Path(secret_ref),
        source_priority=SOURCE_TYPE_PRIORITY_BY_KEY_MAP[source_type],
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
    table_extraction_list = [
        TableExtraction.model_validate(table_extraction_payload)
        for table_extraction_payload in table_extraction_payload_list
    ]
    source_type_dir = _brand_audit_dir(Path(result_dir), brand_input) / "source_type" / source_type
    table_result_path_by_size_group_key_map = {
        table_extraction.size_group_key: _artifact_path(
            source_type_dir / "size_chart" / table_extraction.size_group_key / "table_extraction" / "result.json",
            Path(result_dir),
        )
        for table_extraction in table_extraction_list
    }
    evidence_manifest_path_list = [
        _artifact_path(artifact_path, Path(result_dir))
        for artifact_path in [
            source_type_dir / "source_discovery" / "result.json",
            source_type_dir / "source_discovery" / "verification.json",
        ]
        if artifact_path.is_file()
    ]
    summary = SourceTypeSummary(
        blocker_list=blocker_list,
        evidence_manifest_path_list=evidence_manifest_path_list,
        source_priority=SOURCE_TYPE_PRIORITY_BY_KEY_MAP[source_type],
        source_type=source_type,
        state="failed" if blocker_list else ("passed" if table_extraction_list else "skipped"),
        table_result_path_by_size_group_key_map=table_result_path_by_size_group_key_map,
        verified_size_group_key_list=list(table_result_path_by_size_group_key_map),
    )
    if sorted(summary.verified_size_group_key_list) != sorted(summary.table_result_path_by_size_group_key_map):
        raise RuntimeError(f"source_type_summary key mismatch for {source_type}")
    _artifact_path_list_validate(
        path_list=list(summary.table_result_path_by_size_group_key_map.values()),
        result_dir=Path(result_dir),
        stage_key="source_type_summary",
    )
    _artifact_path_list_validate(
        path_list=summary.evidence_manifest_path_list,
        result_dir=Path(result_dir),
        stage_key="source_type_summary",
    )
    json_artifact_write(source_type_dir / "source_type_summary" / "result.json", summary)
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
    source_type_dir = _brand_audit_dir(Path(result_dir), brand_input) / "source_type" / source_type
    table_extraction = _table_stage_run(
        brand_input=brand_input,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        prompt_scope=prompt_scope,
        result_dir=Path(result_dir),
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
    _prompt_scope_validate(prompt_scope)
    source_type_list = prompt_scope.source_type_allow_list or [
        source_type
        for source_type, _source_priority in sorted(
            SOURCE_TYPE_PRIORITY_BY_KEY_MAP.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]
    known_source_type_list = list(source_type_list)
    if prompt_scope.product_type_request_list:
        return known_source_type_list
    filtered_source_type_list = [
        source_type
        for source_type in known_source_type_list
        if source_type not in PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET
    ]
    if not filtered_source_type_list:
        raise RuntimeError("No source types remain after applying product-type scope rules.")
    return filtered_source_type_list
