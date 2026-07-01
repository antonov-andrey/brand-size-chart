"""Public workflow surface for DBOS brand size-chart workflows."""

from dbos import DBOS, SetWorkflowID

from brand_size_chart.codex.runner import codex_stage_run
from brand_size_chart.model import (
    BrandInput,
    BrandListParseWarning,
    BrandResult,
    BrandSizeChart,
    CanonicalSelectionResult,
    CoverageDecisionResult,
    PromptScope,
    RunResult,
    SourceDiscovery,
    SourceDiscoveryResult,
    SourceTypeSummary,
    TableExtraction,
)
from brand_size_chart.stage.base import MAX_STAGE_ATTEMPT_COUNT, prompt_file_text_get
from brand_size_chart.workflow.base import (
    ARTIFACT_WRITER,
    PROMPT_SCOPE_VALIDATOR,
    canonical_selection_result_get as _canonical_selection_result_get,
    coverage_decision_result_get as _coverage_decision_result_get,
    coverage_decision_semantic_result_get,
    prompt_scope_get as _prompt_scope_get,
    prompt_scope_stage_get,
    prompt_scope_with_product_type_request_list_get as _prompt_scope_with_product_type_request_list_get,
    source_discovery_result_get,
    source_type_list_get as _source_type_list_get,
    source_type_prompt_scope_get as _source_type_prompt_scope_get,
    stage_prompt_text_get as _stage_prompt_text_get,
    table_stage_run,
)
from brand_size_chart.workflow.brand import (
    BRAND_SIZE_CHART_BRAND_WORKFLOW,
    BrandSizeChartBrandWorkflow,
    brand_selection_write_step,
    brand_size_chart_brand,
    coverage_decision_write_step,
)
from brand_size_chart.workflow.root import (
    BRAND_SIZE_CHART_RUN_WORKFLOW,
    BrandSizeChartRunWorkflow,
    brand_size_chart_run,
    prompt_scope_write_step,
    run_failure_result_write,
    run_result_write_step,
)
from brand_size_chart.workflow.source_type import (
    BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW,
    BrandSizeChartSourceTypeWorkflow,
    brand_size_chart_source_type,
    source_discovery_write_step,
    source_type_summary_write_step,
)
from brand_size_chart.workflow.table import (
    BRAND_SIZE_CHART_TABLE_WORKFLOW,
    BrandSizeChartTableWorkflow,
    brand_size_chart_table,
    table_stage_write_step,
)

brand_size_chart_workflow = brand_size_chart_run


def _coverage_decision_semantic_result_get(
    *,
    brand_input: BrandInput,
    prompt_scope: PromptScope,
    result_dir,
    source_type: str,
    stage_dir,
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
    return coverage_decision_semantic_result_get(
        brand_input=brand_input,
        codex_stage_run_callable=codex_stage_run,
        prompt_scope=prompt_scope,
        result_dir=result_dir,
        source_type=source_type,
        stage_dir=stage_dir,
        table_extraction_list=table_extraction_list,
    )


def _prompt_file_text_get(prompt_name: str) -> str:
    """Return one static prompt file.

    Args:
        prompt_name: Prompt file stem.

    Returns:
        Prompt text.
    """
    return prompt_file_text_get(prompt_name)


def _prompt_scope_stage_get(*, result_dir, workflow_run_prompt: str) -> PromptScope:
    """Run `workflow_run_prompt_apply` and write its verification artifact.

    Args:
        result_dir: Root result directory.
        workflow_run_prompt: User-supplied prompt text.

    Returns:
        Parsed prompt scope.
    """
    return prompt_scope_stage_get(
        codex_stage_run_callable=codex_stage_run,
        result_dir=result_dir,
        workflow_run_prompt=workflow_run_prompt,
    )


def _source_discovery_result_get(
    *,
    brand_input: BrandInput,
    browser_runtime_mcp_url: str,
    prompt_scope: PromptScope,
    result_dir,
    secret_path,
    source_priority: int,
    source_type: str,
    source_type_dir,
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
    return source_discovery_result_get(
        brand_input=brand_input,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        codex_stage_run_callable=codex_stage_run,
        prompt_scope=prompt_scope,
        result_dir=result_dir,
        secret_path=secret_path,
        source_priority=source_priority,
        source_type=source_type,
        source_type_dir=source_type_dir,
    )


def _table_stage_run(
    *,
    brand_input: BrandInput,
    browser_runtime_mcp_url: str,
    prompt_scope: PromptScope,
    result_dir,
    secret_path,
    source_discovery: SourceDiscovery,
    source_type: str,
    source_type_dir,
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
    return table_stage_run(
        brand_input=brand_input,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        codex_stage_run_callable=codex_stage_run,
        prompt_scope=prompt_scope,
        result_dir=result_dir,
        secret_path=secret_path,
        source_discovery=source_discovery,
        source_type=source_type,
        source_type_dir=source_type_dir,
    )


__all__ = [
    "ARTIFACT_WRITER",
    "BRAND_SIZE_CHART_BRAND_WORKFLOW",
    "BRAND_SIZE_CHART_RUN_WORKFLOW",
    "BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW",
    "BRAND_SIZE_CHART_TABLE_WORKFLOW",
    "BrandInput",
    "BrandListParseWarning",
    "BrandResult",
    "BrandSizeChart",
    "BrandSizeChartBrandWorkflow",
    "BrandSizeChartRunWorkflow",
    "BrandSizeChartSourceTypeWorkflow",
    "BrandSizeChartTableWorkflow",
    "CanonicalSelectionResult",
    "CoverageDecisionResult",
    "DBOS",
    "MAX_STAGE_ATTEMPT_COUNT",
    "PROMPT_SCOPE_VALIDATOR",
    "PromptScope",
    "RunResult",
    "SetWorkflowID",
    "SourceDiscovery",
    "SourceDiscoveryResult",
    "SourceTypeSummary",
    "TableExtraction",
    "_canonical_selection_result_get",
    "_coverage_decision_result_get",
    "_coverage_decision_semantic_result_get",
    "_prompt_file_text_get",
    "_prompt_scope_get",
    "_prompt_scope_stage_get",
    "_prompt_scope_with_product_type_request_list_get",
    "_source_discovery_result_get",
    "_source_type_list_get",
    "_source_type_prompt_scope_get",
    "_stage_prompt_text_get",
    "_table_stage_run",
    "brand_selection_write_step",
    "brand_size_chart_brand",
    "brand_size_chart_run",
    "brand_size_chart_source_type",
    "brand_size_chart_table",
    "brand_size_chart_workflow",
    "codex_stage_run",
    "coverage_decision_write_step",
    "prompt_scope_write_step",
    "run_failure_result_write",
    "run_result_write_step",
    "source_discovery_write_step",
    "source_type_summary_write_step",
    "table_stage_write_step",
]
