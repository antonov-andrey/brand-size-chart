"""Brand-level DBOS workflow owner."""

import json
from pathlib import Path

from dbos import DBOS, DBOSConfiguredInstance, SetWorkflowID

from brand_size_chart.artifact import ArtifactLayout, ArtifactReferenceValidator
from brand_size_chart.codex.runner import codex_stage_run
from brand_size_chart.identifier import dbos_identifier
from brand_size_chart.model import (
    BrandInput,
    BrandResult,
    CanonicalSelectionResult,
    CoverageDecisionResult,
    PromptScope,
    SourceTypeSummary,
    TableExtraction,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.stage import CanonicalSelectionStage
from brand_size_chart.workflow.base import (
    ARTIFACT_WRITER,
    coverage_decision_semantic_result_get,
    prompt_scope_with_product_type_request_list_get,
    source_type_list_get,
    source_type_prompt_scope_get,
)
from brand_size_chart.workflow.source_type import brand_size_chart_source_type


def _table_extraction_identity_key_get(*, size_group_key: str, source_type: str, source_url: str) -> str:
    """Return deterministic exact-match key for one extracted table identity.

    Args:
        size_group_key: Size group key.
        source_type: Source type key.
        source_url: Source URL.

    Returns:
        JSON identity key.
    """

    return json.dumps(
        {
            "size_group_key": size_group_key,
            "source_type": source_type,
            "source_url": source_url,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


@DBOS.dbos_class("BrandSizeChartBrandWorkflow")
class BrandSizeChartBrandWorkflow(DBOSConfiguredInstance):
    """DBOS owner for one brand workflow and brand-level side-effect steps."""

    def __init__(self) -> None:
        """Register the stable stateless DBOS instance."""

        super().__init__("default")

    @DBOS.workflow(name="brand_size_chart_brand")
    def run(
        self,
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
        source_type_list = source_type_list_get(prompt_scope)
        remaining_product_type_list = list(prompt_scope.product_type_request_list)
        source_type_summary_payload_list: list[dict[str, object]] = []
        table_extraction_payload_list: list[dict[str, object]] = []
        queue_name = dbos_identifier("queue", workflow_run_id)
        for source_type in source_type_list:
            if (
                SOURCE_TYPE_REGISTRY.source_type_requires_product_type(source_type)
                and prompt_scope.product_type_request_list
                and not remaining_product_type_list
            ):
                break
            source_type_prompt_scope = source_type_prompt_scope_get(
                prompt_scope=prompt_scope,
                remaining_product_type_list=remaining_product_type_list,
                source_type=source_type,
            )
            with SetWorkflowID(
                dbos_identifier("workflow", workflow_run_id, brand_input.parsed_brand_name, source_type)
            ):
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
                coverage_prompt_scope = prompt_scope_with_product_type_request_list_get(
                    product_type_request_list=remaining_product_type_list,
                    prompt_scope=prompt_scope,
                )
                coverage_check_payload = self.coverage_decision_write_step(
                    brand_input.model_dump(mode="json"),
                    coverage_prompt_scope.model_dump(mode="json"),
                    result_dir,
                    source_type,
                    table_extraction_payload_list,
                )
                coverage_check = CoverageDecisionResult.model_validate(coverage_check_payload)
                remaining_product_type_list = coverage_check.uncovered_product_type_list

        return self.selection_write_step(
            brand_input.model_dump(mode="json"),
            prompt_scope.model_dump(mode="json"),
            result_dir,
            table_extraction_payload_list,
            source_type_summary_payload_list,
        )

    @DBOS.step(name="coverage_decision_write_step")
    def coverage_decision_write_step(
        self,
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
        coverage_result = coverage_decision_semantic_result_get(
            brand_input=brand_input,
            codex_stage_run_callable=codex_stage_run,
            prompt_scope=prompt_scope,
            result_dir=result_dir_path,
            source_type=source_type,
            stage_dir=artifact_layout.coverage_decision_dir(brand_input, source_type),
            table_extraction_list=table_extraction_list,
        )
        return coverage_result.model_dump(mode="json")

    @DBOS.step(name="brand_selection_write_step")
    def selection_write_step(
        self,
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
        coverage_result = coverage_decision_semantic_result_get(
            brand_input=brand_input,
            codex_stage_run_callable=codex_stage_run,
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
        table_extraction_by_identity_key_map = {
            _table_extraction_identity_key_get(
                size_group_key=table_extraction.size_group_key,
                source_type=table_extraction.source_type,
                source_url=table_extraction.source_url,
            ): table_extraction
            for table_extraction in table_extraction_list
        }
        chart_path_list: list[str] = []
        for selection in canonical_selection_result.canonical_selection_list:
            table_extraction_identity_key = _table_extraction_identity_key_get(
                size_group_key=selection.size_group_key,
                source_type=selection.selected_source_type,
                source_url=selection.selected_source_url,
            )
            if table_extraction_identity_key not in table_extraction_by_identity_key_map:
                raise RuntimeError(
                    "canonical_selection selected missing table_extraction: "
                    f"{selection.size_group_key} {selection.selected_source_type} {selection.selected_source_url}"
                )
            table_extraction = table_extraction_by_identity_key_map[table_extraction_identity_key]
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


BRAND_SIZE_CHART_BRAND_WORKFLOW = BrandSizeChartBrandWorkflow()
brand_selection_write_step = BRAND_SIZE_CHART_BRAND_WORKFLOW.selection_write_step
brand_size_chart_brand = BRAND_SIZE_CHART_BRAND_WORKFLOW.run
coverage_decision_write_step = BRAND_SIZE_CHART_BRAND_WORKFLOW.coverage_decision_write_step

__all__ = [
    "BRAND_SIZE_CHART_BRAND_WORKFLOW",
    "BrandSizeChartBrandWorkflow",
    "brand_selection_write_step",
    "brand_size_chart_brand",
    "coverage_decision_write_step",
]
