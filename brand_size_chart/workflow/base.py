"""Shared deterministic helpers for DBOS workflow owners."""

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from brand_size_chart.artifact import ArtifactLayout, ArtifactReferenceValidator, JsonArtifactWriter
from brand_size_chart.model import (
    BrandInput,
    CanonicalSelectionResult,
    CoverageDecisionResult,
    PromptScope,
    SourceDiscovery,
    SourceDiscoveryResult,
    TableExtraction,
    TableExtractionBatchResult,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.stage import (
    CanonicalSelectionStage,
    CoverageDecisionStage,
    SourceDiscoveryStage,
    TableExtractionStage,
    WorkflowRunPromptApplyStage,
)
from brand_size_chart.stage.semantic import stage_prompt_text_get as semantic_stage_prompt_text_get
from brand_size_chart.validator import PromptScopeValidator

ARTIFACT_WRITER = JsonArtifactWriter()
PROMPT_SCOPE_VALIDATOR = PromptScopeValidator()
CodexStageRun = Callable[..., BaseModel]


def canonical_selection_result_get(table_extraction_list: list[TableExtraction]) -> CanonicalSelectionResult:
    """Return canonical selections from verified tables.

    Args:
        table_extraction_list: Verified table extractions.

    Returns:
        Canonical selection result.
    """
    return CanonicalSelectionStage.draft_result_get(table_extraction_list)


def coverage_decision_result_get(
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


def coverage_decision_semantic_result_get(
    *,
    brand_input: BrandInput,
    codex_stage_run_callable: CodexStageRun,
    prompt_scope: PromptScope,
    result_dir: Path,
    source_type: str,
    stage_dir: Path,
    table_extraction_list: list[TableExtraction],
) -> CoverageDecisionResult:
    """Return semantically verified coverage for requested product types.

    Args:
        brand_input: Parsed brand input.
        codex_stage_run_callable: Codex stage runner.
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
        codex_stage_run_callable=codex_stage_run_callable,
        prompt_scope=prompt_scope,
        result_dir=result_dir,
        source_type=source_type,
        stage_dir=stage_dir,
        table_extraction_list=table_extraction_list,
    ).run()


def prompt_scope_get(workflow_run_prompt: str) -> PromptScope:
    """Return a minimal draft scope for the free workflow-run prompt.

    Args:
        workflow_run_prompt: User-supplied free prompt text.

    Returns:
        Draft prompt scope.
    """
    prompt_text = workflow_run_prompt.strip()
    return PromptScope(shared_instruction=prompt_text)


def prompt_scope_stage_get(
    *, codex_stage_run_callable: CodexStageRun, result_dir: Path, workflow_run_prompt: str
) -> PromptScope:
    """Run `workflow_run_prompt_apply` and write its verification artifact.

    Args:
        codex_stage_run_callable: Codex stage runner.
        result_dir: Root result directory.
        workflow_run_prompt: User-supplied prompt text.

    Returns:
        Parsed prompt scope.
    """
    return WorkflowRunPromptApplyStage(
        codex_stage_run_callable=codex_stage_run_callable,
        result_dir=result_dir,
        workflow_run_prompt=workflow_run_prompt,
    ).run()


def prompt_scope_with_product_type_request_list_get(
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


def source_discovery_result_get(
    *,
    brand_input: BrandInput,
    browser_runtime_mcp_url: str,
    codex_stage_run_callable: CodexStageRun,
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
        codex_stage_run_callable: Codex stage runner.
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
        codex_stage_run_callable=codex_stage_run_callable,
        prompt_scope=prompt_scope,
        result_dir=result_dir,
        secret_path=secret_path,
        source_priority=source_priority,
        source_type=source_type,
        source_type_dir=source_type_dir,
    ).run()


def source_type_list_get(prompt_scope: PromptScope) -> list[str]:
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


def source_type_prompt_scope_get(
    *, prompt_scope: PromptScope, remaining_product_type_list: list[str], source_type: str
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
        return prompt_scope_with_product_type_request_list_get(
            product_type_request_list=remaining_product_type_list,
            prompt_scope=prompt_scope,
        )
    return prompt_scope_with_product_type_request_list_get(
        product_type_request_list=[],
        prompt_scope=prompt_scope,
    )


def stage_prompt_text_get(
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
    return semantic_stage_prompt_text_get(
        attempt_index=attempt_index,
        draft_result_json_text=draft_result_json_text,
        feedback_list=feedback_list,
        prompt_context=prompt_context,
        prompt_name=prompt_name,
        prompt_scope=prompt_scope,
        previous_result_json_text=previous_result_json_text,
        stage_key=stage_key,
    )


def table_extract_result_get(
    *,
    brand_input: BrandInput,
    browser_runtime_mcp_url: str,
    codex_stage_run_callable: CodexStageRun,
    prompt_scope: PromptScope,
    result_dir: Path,
    secret_path: Path,
    source_discovery_list: list[SourceDiscovery],
    source_type: str,
    source_type_dir: Path,
) -> TableExtractionBatchResult:
    """Run batch table extraction plus verification for one source type.

    Args:
        brand_input: Parsed brand input.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
        codex_stage_run_callable: Codex stage runner.
        prompt_scope: Parsed prompt scope.
        result_dir: Root result directory.
        secret_path: Secret DataSource path.
        source_discovery_list: Verified source discoveries.
        source_type: Source type key.
        source_type_dir: Source-type audit directory.

    Returns:
        Verified batch table extraction.
    """
    return TableExtractionStage(
        brand_input=brand_input,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        codex_stage_run_callable=codex_stage_run_callable,
        prompt_scope=prompt_scope,
        result_dir=result_dir,
        secret_path=secret_path,
        source_discovery_list=source_discovery_list,
        source_type=source_type,
        source_type_dir=source_type_dir,
    ).run()


__all__ = [
    "ARTIFACT_WRITER",
    "CodexStageRun",
    "PROMPT_SCOPE_VALIDATOR",
    "canonical_selection_result_get",
    "coverage_decision_result_get",
    "coverage_decision_semantic_result_get",
    "prompt_scope_get",
    "prompt_scope_stage_get",
    "prompt_scope_with_product_type_request_list_get",
    "source_discovery_result_get",
    "source_type_list_get",
    "source_type_prompt_scope_get",
    "stage_prompt_text_get",
    "table_extract_result_get",
]
