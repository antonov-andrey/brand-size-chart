"""Brand-level DBOS workflow owner."""

from pathlib import Path

from dbos import DBOS, SetWorkflowID
from workflow_container_runtime.artifact import JsonArtifactWriter

from brand_size_chart.artifact import ArtifactLayout, ArtifactReferenceValidator, TableExtractionChartReader
from brand_size_chart.identifier import dbos_identifier
from brand_size_chart.model import (
    BrandInput,
    BrandResult,
    CoverageDecisionProductTypeGap,
    CoverageDecisionResult,
    PromptScope,
    SourceTypeSummary,
    TableExtractionArtifact,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.stage import CanonicalSelectionStage, CoverageDecisionStage
from brand_size_chart.workflow.codex import BrandSizeChartCodexWorkflow
from brand_size_chart.workflow.source_type import BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW
from brand_size_chart.validator import PromptScopeValidator


@DBOS.dbos_class("BrandSizeChartBrandWorkflow")
class BrandSizeChartBrandWorkflow(BrandSizeChartCodexWorkflow):
    """DBOS owner for one brand workflow and brand-level side-effect steps."""

    def __init__(self) -> None:
        """Register stable DBOS workflow dependencies."""

        super().__init__()
        self._prompt_scope_validator = PromptScopeValidator()

    @DBOS.workflow(name="brand_size_chart_brand")
    def run(
        self,
        workflow_run_id: str,
        brand_input_payload: dict[str, object],
        browser_runtime_mcp_url: str,
        prompt_scope_payload: dict[str, object],
        result_dir: str,
    ) -> dict[str, object]:
        """Process one brand with source-type child workflows.

        Args:
            workflow_run_id: Stable workflow run identifier.
            brand_input_payload: Serialized brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Root result directory string.

        Returns:
            Serialized brand result.
        """
        brand_input = BrandInput.model_validate(brand_input_payload)
        prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        source_type_list = self.source_type_list_get(prompt_scope)
        remaining_product_type_list = list(prompt_scope.product_type_request_list)
        final_coverage_result_payload = CoverageDecisionResult(
            covered_product_type_list=[],
            uncovered_product_type_gap_list=[],
        ).model_dump(mode="json")
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
            source_type_prompt_scope = self.source_type_prompt_scope_get(
                prompt_scope=prompt_scope,
                remaining_product_type_list=remaining_product_type_list,
                source_type=source_type,
            )
            with SetWorkflowID(
                dbos_identifier("workflow", workflow_run_id, brand_input.parsed_brand_name, source_type)
            ):
                source_type_handle = DBOS.enqueue_workflow(
                    queue_name,
                    BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW.run,
                    workflow_run_id,
                    brand_input.model_dump(mode="json"),
                    browser_runtime_mcp_url,
                    source_type_prompt_scope.model_dump(mode="json"),
                    result_dir,
                    source_type,
                )
            source_type_result = source_type_handle.get_result()
            source_type_summary = SourceTypeSummary.model_validate(source_type_result["source_type_summary"])
            source_type_summary_payload_list.append(source_type_summary.model_dump(mode="json"))
            source_type_table_extraction_payload_list = source_type_result["table_extraction_list"]
            table_extraction_payload_list.extend(source_type_table_extraction_payload_list)
            if not prompt_scope.product_type_request_list and source_type_table_extraction_payload_list:
                break
            if (
                prompt_scope.product_type_request_list
                and table_extraction_payload_list
                and source_type_summary.state == "passed"
            ):
                coverage_check_payload = self.coverage_decide_write_step(
                    brand_input.model_dump(mode="json"),
                    prompt_scope.model_dump(mode="json"),
                    result_dir,
                    source_type,
                    table_extraction_payload_list,
                )
                coverage_check = CoverageDecisionResult.model_validate(coverage_check_payload)
                final_coverage_result_payload = coverage_check.model_dump(mode="json")
                remaining_product_type_list = [
                    product_type_gap.product_type for product_type_gap in coverage_check.uncovered_product_type_gap_list
                ]
        if prompt_scope.product_type_request_list and not table_extraction_payload_list:
            final_coverage_result_payload = self._coverage_result_without_table_get(
                product_type_request_list=remaining_product_type_list,
            ).model_dump(mode="json")

        return self.selection_write_step(
            brand_input.model_dump(mode="json"),
            prompt_scope.model_dump(mode="json"),
            result_dir,
            table_extraction_payload_list,
            source_type_summary_payload_list,
            final_coverage_result_payload,
        )

    def _coverage_result_without_table_get(self, *, product_type_request_list: list[str]) -> CoverageDecisionResult:
        """Return deterministic uncovered coverage result when no verified table exists.

        Args:
            product_type_request_list: Product types that still need coverage.

        Returns:
            Coverage result with structured gaps for every requested product type.
        """

        return CoverageDecisionResult(
            covered_product_type_list=[],
            uncovered_product_type_gap_list=[
                CoverageDecisionProductTypeGap(
                    product_type=product_type,
                    reason="No verified table artifact was found for this requested product type.",
                )
                for product_type in product_type_request_list
            ],
        )

    def prompt_scope_with_product_type_request_list_get(
        self, *, product_type_request_list: list[str], prompt_scope: PromptScope
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

    def source_type_list_get(self, prompt_scope: PromptScope) -> list[str]:
        """Return source types in execution order.

        Args:
            prompt_scope: Parsed prompt scope.

        Returns:
            Source type list.
        """

        self._prompt_scope_validator.validate(prompt_scope)
        return SOURCE_TYPE_REGISTRY.source_type_list_get(
            have_product_type_request=bool(prompt_scope.product_type_request_list),
            source_type_allow_list=prompt_scope.source_type_allow_list,
        )

    def source_type_prompt_scope_get(
        self, *, prompt_scope: PromptScope, remaining_product_type_list: list[str], source_type: str
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
            return self.prompt_scope_with_product_type_request_list_get(
                product_type_request_list=remaining_product_type_list,
                prompt_scope=prompt_scope,
            )
        return self.prompt_scope_with_product_type_request_list_get(
            product_type_request_list=[],
            prompt_scope=prompt_scope,
        )

    @DBOS.step(name="coverage_decide_write_step")
    def coverage_decide_write_step(
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
            TableExtractionArtifact.model_validate(table_extraction_payload)
            for table_extraction_payload in table_extraction_payload_list
        ]
        coverage_result = CoverageDecisionStage(
            brand_input=brand_input,
            codex_stage_run_callable=self._codex_stage_runner.run,
            prompt_scope=prompt_scope,
            result_dir=result_dir_path,
            stage_dir=artifact_layout.coverage_decide_dir(brand_input, source_type),
            table_extraction_list=table_extraction_list,
        ).run()
        return coverage_result.model_dump(mode="json")

    @DBOS.step(name="brand_selection_write_step")
    def selection_write_step(
        self,
        brand_input_payload: dict[str, object],
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        table_extraction_payload_list: list[dict[str, object]],
        source_type_summary_payload_list: list[dict[str, object]],
        coverage_result_payload: dict[str, object],
    ) -> dict[str, object]:
        """Write canonical output and brand result from verified stage payloads.

        Args:
            brand_input_payload: Serialized brand input.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Root result directory string.
            table_extraction_payload_list: Serialized verified table extractions.
            source_type_summary_payload_list: Serialized source-type summaries.
            coverage_result_payload: Serialized cumulative coverage result.

        Returns:
            Serialized brand result.
        """
        result_dir_path = Path(result_dir)
        artifact_layout = ArtifactLayout(result_dir_path)
        artifact_reference_validator = ArtifactReferenceValidator(result_dir_path)
        brand_input = BrandInput.model_validate(brand_input_payload)
        prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        table_extraction_list = [
            TableExtractionArtifact.model_validate(table_extraction_payload)
            for table_extraction_payload in table_extraction_payload_list
        ]
        chart_reader = TableExtractionChartReader(result_dir_path)
        source_type_summary_list = [
            SourceTypeSummary.model_validate(source_type_summary_payload)
            for source_type_summary_payload in source_type_summary_payload_list
        ]
        source_type_error_list = [
            f"{source_type_summary.source_type}: {blocker}"
            for source_type_summary in source_type_summary_list
            if source_type_summary.state == "failed"
            for blocker in source_type_summary.blocker_list
        ]
        coverage_result = CoverageDecisionResult.model_validate(coverage_result_payload)
        canonical_selection_result = CanonicalSelectionStage(
            brand_name=brand_input.parsed_brand_name,
            codex_stage_run_callable=self._codex_stage_runner.run,
            prompt_scope=prompt_scope,
            result_dir=result_dir_path,
            stage_dir=artifact_layout.canonical_select_dir(brand_input),
            table_extraction_list=table_extraction_list,
        ).run()
        table_extraction_by_chart_path_map = {
            table_extraction.chart_path: table_extraction for table_extraction in table_extraction_list
        }
        chart_path_list: list[str] = []
        for selection in canonical_selection_result.canonical_selection_list:
            if selection.selected_chart_path not in table_extraction_by_chart_path_map:
                raise RuntimeError(
                    f"canonical_select selected missing table_extraction: {selection.selected_chart_path}"
                )
            table_extraction = table_extraction_by_chart_path_map[selection.selected_chart_path]
            chart_path = artifact_layout.brand_size_chart_path(brand_input, table_extraction.size_group_key)
            JsonArtifactWriter().write(chart_path, chart_reader.chart_get(table_extraction))
            chart_path_list.append(artifact_layout.artifact_path(chart_path))

        brand_result_path = artifact_layout.brand_result_path(brand_input)
        brand_error_list = [
            *source_type_error_list,
            *[
                f"{product_type_gap.product_type}: {product_type_gap.reason}"
                for product_type_gap in coverage_result.uncovered_product_type_gap_list
            ],
        ]
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
        artifact_writer = JsonArtifactWriter()
        artifact_writer.write(manifest_path, brand_result)
        artifact_writer.write(brand_result_path, brand_result)
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

__all__ = [
    "BRAND_SIZE_CHART_BRAND_WORKFLOW",
    "BrandSizeChartBrandWorkflow",
]
