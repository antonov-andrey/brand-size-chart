"""Table-extraction stage owner."""

from pathlib import Path

from workflow_container_runtime.artifact import JsonArtifactWriter

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandInput,
    BrandSizeChart,
    PromptScope,
    SourceDiscovery,
    TableExtractionArtifact,
    TableExtractionDelta,
    TableExtractionDeltaBatchResult,
    TableExtractionExecplanItem,
    TableExtractionInput,
    TableExtractionResult,
)
from brand_size_chart.stage.base import BrandSizeChartCodexStepBase, CodexStageRun, stage_instruction_list_get
from brand_size_chart.validator import TableExtractionValidator


class TableExtractionStep(
    BrandSizeChartCodexStepBase[TableExtractionInput, TableExtractionDeltaBatchResult, TableExtractionResult]
):
    """Extract verified size chart tables from browser-visible evidence."""

    stage_key = "table_extract"

    def __init__(
        self,
        *,
        brand_input: BrandInput,
        browser_runtime_mcp_url: str,
        codex_stage_run_callable: CodexStageRun,
        prompt_scope: PromptScope,
        result_dir: Path,
        source_discovery_list: list[SourceDiscovery],
        source_type: str,
    ) -> None:
        """Store batch table-extraction step dependencies.

        Args:
            brand_input: Parsed brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope.
            result_dir: Root result directory.
            source_discovery_list: Verified source discoveries.
            source_type: Source type key.
        """

        self._artifact_layout = ArtifactLayout(result_dir)
        self._artifact_writer = JsonArtifactWriter()
        self._brand_input = brand_input
        self._table_extraction_delta_count = 0
        self._prompt_scope = prompt_scope
        self._source_discovery_list = source_discovery_list
        self._source_type = source_type
        super().__init__(
            browser_runtime_mcp_url=browser_runtime_mcp_url,
            codex_stage_run_callable=codex_stage_run_callable,
            result_dir=result_dir,
            stage_dir=self._artifact_layout.table_extract_dir(self._brand_input, self._source_type),
        )

    def action_output_model_get(self) -> type[TableExtractionDeltaBatchResult]:
        """Return the table-extraction action output model.

        Returns:
            Table-extraction delta batch result model.
        """

        return TableExtractionDeltaBatchResult

    def artifact_prepare(self, stage_input: TableExtractionInput) -> None:
        """Create table-extraction directories required before Codex browser execution."""

        _ = stage_input
        (self._stage_dir / "chart").mkdir(parents=True, exist_ok=True)
        self._artifact_writer.write(self._chart_schema_path_get(), BrandSizeChart.model_json_schema())
        for source_discovery in self._source_discovery_list:
            self._table_extract_evidence_dir_get(source_discovery).mkdir(parents=True, exist_ok=True)

    def _chart_schema_path_get(self) -> Path:
        """Return generated table-extraction chart schema path.

        Returns:
            BrandSizeChart schema artifact path.
        """

        return self._stage_dir / "chart.schema.json"

    def input_build(self) -> TableExtractionInput:
        """Return batch table-extraction input.

        Returns:
            Stage input object.
        """

        execplan_item_list = []
        for source_discovery in self._source_discovery_list:
            evidence_dir = self._table_extract_evidence_dir_get(source_discovery)
            chart_path = self._artifact_layout.table_extract_chart_path(
                self._brand_input,
                self._source_type,
                source_discovery.size_group_key,
            )
            execplan_item_list.append(
                TableExtractionExecplanItem(
                    chart_filesystem_path=self._artifact_layout.filesystem_path_get(chart_path),
                    evidence_write_target=ArtifactWriteTarget(
                        artifact_path=self._artifact_layout.artifact_path(evidence_dir),
                        filesystem_path=self._artifact_layout.filesystem_path_get(evidence_dir),
                    ),
                    source_discovery=source_discovery,
                )
            )
        return TableExtractionInput(
            brand_name=self._brand_input.parsed_brand_name,
            execplan_item_list=execplan_item_list,
            shared_instruction=self._prompt_scope.shared_instruction,
            stage_instruction_list=stage_instruction_list_get(
                prompt_scope=self._prompt_scope,
                stage_key=self.stage_key,
            ),
        )

    def result_build(
        self,
        stage_input: TableExtractionInput,
        action_output: TableExtractionDeltaBatchResult,
    ) -> TableExtractionResult:
        """Build the public table-extraction result from one Codex delta result.

        Args:
            stage_input: Table-extraction input.
            action_output: Codex-owned extraction deltas.

        Returns:
            Public table-extraction result.
        """

        self._table_extraction_delta_count = len(action_output.table_extraction_delta_list)
        return TableExtractionResult(
            table_extraction_list=self._table_extraction_artifact_list_get(
                stage_input=stage_input,
                table_extraction_delta_batch_result=action_output,
            )
        )

    def result_validate(self, result: TableExtractionResult) -> None:
        """Validate public table-extraction result.

        Args:
            result: Public table-extraction result.
        """

        execplan_count = len(self.input_build().execplan_item_list)
        if self._table_extraction_delta_count != execplan_count:
            mismatch_kind = "missing delta" if self._table_extraction_delta_count < execplan_count else "extra delta"
            raise RuntimeError(
                f"table_extract result length mismatch ({mismatch_kind}); "
                f"execplan_count={execplan_count}; "
                f"delta_count={self._table_extraction_delta_count}; "
                "expected_size_group_key_list="
                f"{[item.source_discovery.size_group_key for item in self.input_build().execplan_item_list]}"
            )
        TableExtractionValidator(stage_input=self.input_build(), result_dir=self._result_dir).validate(result)

    def _table_extract_evidence_dir_get(self, source_discovery: SourceDiscovery) -> Path:
        """Return browser evidence directory for one batch extraction item.

        Args:
            source_discovery: Verified source discovery.

        Returns:
            Browser evidence directory.
        """

        return self._artifact_layout.table_extract_evidence_dir(
            self._brand_input,
            self._source_type,
            source_discovery.size_group_key,
        )

    def _table_extraction_artifact_get(
        self,
        *,
        execplan_item: TableExtractionExecplanItem,
        table_extraction_delta: TableExtractionDelta,
    ) -> TableExtractionArtifact:
        """Build one cross-stage artifact handle from execplan identity and extraction delta.

        Args:
            execplan_item: Table-extraction execplan item that owns identity and chart target.
            table_extraction_delta: Codex-owned extraction delta.

        Returns:
            Cross-stage artifact handle.
        """

        source_discovery = execplan_item.source_discovery
        return TableExtractionArtifact(
            applicability_description=table_extraction_delta.applicability_description,
            chart_path=self._artifact_layout.artifact_path(
                self._artifact_layout.table_extract_chart_path(
                    self._brand_input,
                    self._source_type,
                    source_discovery.size_group_key,
                )
            ),
            country_code_list=source_discovery.country_code_list,
            evidence_path_list=table_extraction_delta.evidence_path_list,
            size_group_key=source_discovery.size_group_key,
            source_title=source_discovery.source_title,
            source_type=self._source_type,
            source_url=source_discovery.source_url,
        )

    def _table_extraction_artifact_list_get(
        self,
        *,
        stage_input: TableExtractionInput,
        table_extraction_delta_batch_result: TableExtractionDeltaBatchResult,
    ) -> list[TableExtractionArtifact]:
        """Build cross-stage artifact handles from one Codex delta result.

        Args:
            stage_input: Table-extraction input used by the action and validator.
            table_extraction_delta_batch_result: Codex-owned extraction deltas.

        Returns:
            Cross-stage artifact handle list.
        """

        return [
            self._table_extraction_artifact_get(
                execplan_item=execplan_item,
                table_extraction_delta=table_extraction_delta,
            )
            for execplan_item, table_extraction_delta in zip(
                stage_input.execplan_item_list,
                table_extraction_delta_batch_result.table_extraction_delta_list,
            )
        ]
