"""DBOS workflow for brand size-chart source collection."""

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
    return _semantic_stage_run(
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
            "warnings.\n"
        ),
        prompt_scope=prompt_scope,
        prompt_name="selection",
        result_dir=result_dir,
        stage_dir=stage_dir,
        stage_key="coverage_decision",
    )


def _prompt_file_text_get(prompt_name: str) -> str:
    """Return one static prompt file.

    Args:
        prompt_name: Prompt file stem.

    Returns:
        Prompt text.
    """
    return (Path(__file__).parent / "prompt" / f"{prompt_name}.md").read_text(encoding="utf-8")


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
        product_type_request_list=product_type_request_list,
        scope_warning_list=prompt_scope.scope_warning_list,
        shared_instruction=prompt_scope.shared_instruction,
        source_type_allow_list=prompt_scope.source_type_allow_list,
        stage_instruction_list=prompt_scope.stage_instruction_list,
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
    stage_context = (
        f"Workflow run prompt:\n{workflow_run_prompt}\n\n"
        f"Draft prompt scope JSON:\n{prompt_scope.model_dump_json(indent=2)}\n"
    )
    return _semantic_stage_run(
        draft_result=prompt_scope,
        model_class=PromptScope,
        prompt_context=stage_context,
        prompt_scope=prompt_scope,
        prompt_name="apply",
        result_dir=result_dir,
        stage_dir=stage_dir,
        stage_key="workflow_run_prompt_apply",
    )


def _semantic_stage_run(
    *,
    browser_access: bool = False,
    browser_runtime_data_source_path: Path | None = None,
    draft_result: _ResultModelT,
    model_class: type[_ResultModelT],
    prompt_context: str,
    prompt_scope: PromptScope | None,
    prompt_name: str,
    result_dir: Path,
    stage_dir: Path,
    stage_key: str,
) -> _ResultModelT:
    """Run one main stage plus its verification stage.

    Args:
        browser_access: Whether Codex may use browser/MCP tools and write evidence artifacts.
        browser_runtime_data_source_path: Browser/VPN runtime DataSource path for browser stages.
        draft_result: Deterministic draft result used as initial stage input.
        model_class: Pydantic result model.
        prompt_context: Stage-specific prompt context.
        prompt_scope: Parsed prompt scope relevant to this stage.
        prompt_name: Static prompt file name stem.
        result_dir: Root result directory.
        stage_dir: Stage artifact directory.
        stage_key: Stable stage key.
    Returns:
        Verified stage result.

    Raises:
        RuntimeError: If verification does not pass within the retry limit.
    """
    feedback_list: list[str] = []
    stage_dir.mkdir(parents=True, exist_ok=True)
    for attempt_index in range(1, MAX_STAGE_ATTEMPT_COUNT + 1):
        result = codex_stage_run(
            allow_user_config=browser_access,
            browser_runtime_data_source_path=browser_runtime_data_source_path,
            model_class=model_class,
            prompt_text=_stage_prompt_text_get(
                attempt_index=attempt_index,
                feedback_list=feedback_list,
                prompt_context=prompt_context,
                prompt_name=prompt_name,
                prompt_scope=prompt_scope,
                stage_key=stage_key,
            ),
            result_dir=result_dir,
            sandbox_mode="workspace-write" if browser_access else "read-only",
            stage_dir=stage_dir,
            stage_name=stage_key,
        )

        result_path = stage_dir / "result.json"
        json_artifact_write(result_path, result)
        verification = _stage_verification_get(
            artifact_path_list=[_artifact_path(result_path, result_dir)],
            prompt_context=prompt_context,
            prompt_scope=prompt_scope,
            result=result,
            result_dir=result_dir,
            stage_dir=stage_dir,
            stage_key=stage_key,
            browser_access=browser_access,
            browser_runtime_data_source_path=browser_runtime_data_source_path,
        )
        json_artifact_write(stage_dir / "verification.json", verification)
        if verification.status == "success":
            return result
        feedback_list = verification.feedback_list or verification.error_list

    raise RuntimeError(f"Stage {stage_key} did not pass verification after {MAX_STAGE_ATTEMPT_COUNT} attempts.")


def _source_discovery_result_get(
    *,
    brand_input: BrandInput,
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
        f"Requested product types:\n{requested_product_type_text}\n"
        f"Source type instruction: {SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP[source_type]}\n"
        f"Evidence directory: {_artifact_path(evidence_dir, result_dir)}\n"
        "Use the configured browser to search, open, and interact with source pages. "
        "All source-page and source-data loading must go through the configured browser. "
        "Do not use non-browser loading mechanisms; direct HTTP, curl, requests, wget, and Python scraping are "
        "examples of forbidden replacements, not an exhaustive list. "
        "Treat source discovery as a bounded workflow, not a best-effort search. First build a browser-backed "
        "source-surface inventory for this source type: discovery queries, candidate URLs, opened URLs, accepted "
        "tables, rejected URLs, rejection reasons, and blocking browser errors must be represented in evidence "
        "artifacts under the evidence directory. "
        "Write each relevant browser evidence artifact under the evidence directory and reference those paths in "
        "evidence_path_list. Return every size-chart source candidate backed by evidence files unless the workflow "
        "run shared instruction explicitly narrows the stage scope. "
        "One SourceDiscovery item represents one concrete size chart table, not one page. "
        "If one page contains multiple size chart tables, return one discovered_source_list item per table. "
        "The size_group_key must identify that concrete table, such as women_size_chart or men_shoes_size_chart; "
        "page-level or aggregate keys such as all, guide, page, or brand-wide bundle keys are forbidden. "
        "If requested product types are present, search for every requested product type in this source type. "
        "If one discovered table clearly applies to multiple requested product types, return one candidate and set "
        "product_type_hint_list to exactly the requested product types that are explicitly covered by the evidence. "
        "Do not include weakly inferred product types in product_type_hint_list. "
        "Respect the source type boundary exactly; do not return product-page measurement sections for "
        "official_brand_size_guide. "
        "Do not return status='skipped'. Empty discovered_source_list is forbidden in real discovery. "
        "If no concrete table can be returned after browser-backed inventory, return status='failed' "
        "with detailed blocker errors and evidence references; the stage must fail after retry limit instead of "
        "silently doing nothing. Do not invent candidates.\n\n"
        f"Draft source_discovery JSON:\n{draft_result.model_dump_json(indent=2)}\n"
    )

    discovery_result = _semantic_stage_run(
        browser_access=True,
        draft_result=draft_result,
        model_class=SourceDiscoveryResult,
        prompt_context=prompt_context,
        prompt_scope=prompt_scope,
        prompt_name="discovery",
        result_dir=result_dir,
        stage_dir=source_type_dir / "source_discovery",
        stage_key="source_discovery",
        browser_runtime_data_source_path=secret_path,
    )
    for source_discovery in discovery_result.discovered_source_list:
        _artifact_reference_list_validate(
            evidence_path_list=source_discovery.evidence_path_list,
            result_dir=result_dir,
            stage_key="source_discovery",
        )
    return discovery_result


def _table_stage_run(
    *,
    brand_input: BrandInput,
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
        "browser-visible evidence and preserve all source columns that belong to the size chart.\n\n"
        f"Draft table_extraction JSON:\n{table_extraction.model_dump_json(indent=2)}\n"
    )
    table_result = _semantic_stage_run(
        browser_access=True,
        draft_result=table_extraction,
        model_class=TableExtraction,
        prompt_context=prompt_context,
        prompt_scope=prompt_scope,
        prompt_name="extraction",
        result_dir=result_dir,
        stage_dir=table_stage_dir,
        stage_key="table_extraction",
        browser_runtime_data_source_path=secret_path,
    )
    _artifact_reference_list_validate(
        evidence_path_list=table_result.evidence_path_list,
        result_dir=result_dir,
        stage_key="table_extraction",
    )
    if not table_result.chart.row_list:
        raise RuntimeError(f"Stage table_extraction returned an empty chart for {table_result.size_group_key}.")
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
    feedback_list: list[str],
    prompt_context: str,
    prompt_name: str,
    prompt_scope: PromptScope | None,
    stage_key: str,
) -> str:
    """Build one Codex stage prompt from a static prompt file.

    Args:
        attempt_index: Stage attempt index.
        feedback_list: Verification feedback from previous attempts.
        prompt_context: Stage-specific context.
        prompt_name: Static prompt file name stem.
        prompt_scope: Parsed workflow-run prompt scope.
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
        f"Verification feedback from previous attempt:\n{feedback_text if feedback_text else '- none'}\n"
    )


def _stage_verification_get(
    *,
    artifact_path_list: list[str],
    browser_access: bool,
    browser_runtime_data_source_path: Path | None,
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
        browser_runtime_data_source_path: Browser/VPN runtime DataSource path for browser verification.
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
        browser_runtime_data_source_path=browser_runtime_data_source_path,
        model_class=StageVerification,
        prompt_text=verification_prompt,
        result_dir=result_dir,
        sandbox_mode="workspace-write" if browser_access else "read-only",
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
        result_dir=Path(result_dir),
        stage_dir=_brand_audit_dir(Path(result_dir), brand_input) / "canonical_selection",
        stage_key="canonical_selection",
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
    brand_result = BrandResult(
        audit_artifact_path_list=[_artifact_path(brand_result_path, Path(result_dir))],
        canonical_selection_list=canonical_selection_result.canonical_selection_list,
        error_list=coverage_result.uncovered_product_type_list,
        message=(
            "Canonical tables selected."
            if canonical_selection_result.canonical_selection_list
            else "No verified canonical source tables found."
        ),
        parsed_brand_key=brand_input.parsed_brand_key,
        parsed_brand_name=brand_input.parsed_brand_name,
        size_chart_path_list=chart_path_list,
        source_type_summary_list=source_type_summary_list,
        status="success" if canonical_selection_result.canonical_selection_list else "skipped",
    )
    json_artifact_write(_brand_output_dir(Path(result_dir), brand_input) / "manifest.json", brand_result)
    json_artifact_write(brand_result_path, brand_result)
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
    prompt_scope_payload: dict[str, object],
    result_dir: str,
    secret_ref: str,
) -> dict[str, object]:
    """Process one brand with source-type child workflows.

    Args:
        workflow_run_id: Stable workflow run identifier.
        brand_input_payload: Serialized brand input.
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
        source_type_prompt_scope = prompt_scope
        if prompt_scope.product_type_request_list:
            if not remaining_product_type_list:
                break
            source_type_prompt_scope = _prompt_scope_with_product_type_request_list_get(
                product_type_request_list=remaining_product_type_list,
                prompt_scope=prompt_scope,
            )
        with SetWorkflowID(dbos_identifier("workflow", workflow_run_id, brand_input.parsed_brand_name, source_type)):
            source_type_handle = DBOS.enqueue_workflow(
                queue_name,
                brand_size_chart_source_type,
                workflow_run_id,
                brand_input.model_dump(mode="json"),
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
            coverage_check_payload = coverage_decision_write_step(
                brand_input.model_dump(mode="json"),
                source_type_prompt_scope.model_dump(mode="json"),
                result_dir,
                source_type,
                table_extraction_payload_list,
            )
            coverage_check = CoverageDecisionResult.model_validate(coverage_check_payload)
            remaining_product_type_list = coverage_check.uncovered_product_type_list
            if not remaining_product_type_list:
                break

    return brand_selection_write_step(
        brand_input.model_dump(mode="json"),
        prompt_scope.model_dump(mode="json"),
        result_dir,
        table_extraction_payload_list,
        source_type_summary_payload_list,
    )


@DBOS.workflow()
def brand_size_chart_run(
    workflow_run_id: str, brand_list_text: str, secret_ref: str, result_dir: str, workflow_run_prompt: str
) -> dict[str, object]:
    """Run root workflow orchestration for one brand list.

    Args:
        workflow_run_id: Stable workflow run identifier.
        brand_list_text: Raw brand-list input text.
        secret_ref: Secret DataSource path string.
        result_dir: Root result directory string.
        workflow_run_prompt: User-supplied prompt text.

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
    prompt_scope_payload: dict[str, object],
    result_dir: str,
    secret_ref: str,
    source_type: str,
) -> dict[str, object]:
    """Process one source type with table child workflows.

    Args:
        workflow_run_id: Stable workflow run identifier.
        brand_input_payload: Serialized brand input.
        prompt_scope_payload: Serialized prompt scope.
        result_dir: Root result directory string.
        secret_ref: Secret DataSource path string.
        source_type: Source type key.

    Returns:
        Serialized source-type summary and verified table list.
    """
    brand_input = BrandInput.model_validate(brand_input_payload)
    prompt_scope = PromptScope.model_validate(prompt_scope_payload)
    discovery_result_payload = source_discovery_write_step(
        brand_input.model_dump(mode="json"),
        prompt_scope.model_dump(mode="json"),
        result_dir,
        secret_ref,
        source_type,
    )
    discovery_result = SourceDiscoveryResult.model_validate(discovery_result_payload)
    verified_table_extraction_payload_list: list[dict[str, object]] = []
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
                prompt_scope.model_dump(mode="json"),
                result_dir,
                secret_ref,
                source_type,
                source_discovery.model_dump(mode="json"),
            )
        verified_table_extraction_payload_list.append(table_handle.get_result())
    source_type_summary_payload = source_type_summary_write_step(
        brand_input.model_dump(mode="json"),
        result_dir,
        source_type,
        verified_table_extraction_payload_list,
    )
    return {
        "source_type_summary": source_type_summary_payload,
        "table_extraction_list": verified_table_extraction_payload_list,
    }


@DBOS.workflow()
def brand_size_chart_table(
    brand_input_payload: dict[str, object],
    prompt_scope_payload: dict[str, object],
    result_dir: str,
    secret_ref: str,
    source_type: str,
    source_discovery_payload: dict[str, object],
) -> dict[str, object]:
    """Process one size-chart table.

    Args:
        brand_input_payload: Serialized brand input.
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
    run_result = RunResult(
        brand_result_list=[BrandResult.model_validate(payload) for payload in brand_result_payload_list],
        message="Workflow run completed.",
        prompt_scope=PromptScope.model_validate(prompt_scope_payload),
        result_dir=result_dir,
        status="success",
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
    prompt_scope_payload: dict[str, object],
    result_dir: str,
    secret_ref: str,
    source_type: str,
) -> dict[str, object]:
    """Write source discovery result and verification.

    Args:
        brand_input_payload: Serialized brand input.
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
) -> dict[str, object]:
    """Write source-type summary.

    Args:
        brand_input_payload: Serialized brand input.
        result_dir: Root result directory string.
        source_type: Source type key.
        table_extraction_payload_list: Serialized verified table extractions.

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
    summary = SourceTypeSummary(
        evidence_manifest_path_list=[
            _artifact_path(source_type_dir / "source_discovery" / "result.json", Path(result_dir))
        ],
        source_priority=SOURCE_TYPE_PRIORITY_BY_KEY_MAP[source_type],
        source_type=source_type,
        state="passed" if table_extraction_list else "skipped",
        table_result_path_by_size_group_key_map=table_result_path_by_size_group_key_map,
        verified_size_group_key_list=list(table_result_path_by_size_group_key_map),
    )
    json_artifact_write(source_type_dir / "source_type_summary" / "result.json", summary)
    return summary.model_dump(mode="json")


@DBOS.step()
def table_stage_write_step(
    brand_input_payload: dict[str, object],
    prompt_scope_payload: dict[str, object],
    result_dir: str,
    secret_ref: str,
    source_type: str,
    source_discovery_payload: dict[str, object],
) -> dict[str, object]:
    """Write table extraction and verification artifacts.

    Args:
        brand_input_payload: Serialized brand input.
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
    source_type_list = prompt_scope.source_type_allow_list or [
        source_type
        for source_type, _source_priority in sorted(
            SOURCE_TYPE_PRIORITY_BY_KEY_MAP.items(),
            key=lambda item: item[1],
            reverse=True,
        )
    ]
    known_source_type_list = [
        source_type for source_type in source_type_list if source_type in SOURCE_TYPE_PRIORITY_BY_KEY_MAP
    ]
    if prompt_scope.product_type_request_list:
        return known_source_type_list
    return [
        source_type
        for source_type in known_source_type_list
        if source_type not in PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET
    ]
