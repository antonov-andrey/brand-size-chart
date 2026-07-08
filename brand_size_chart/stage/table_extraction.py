"""Table-extraction stage owner."""

from pathlib import Path

from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.stage import VerifiedCodexStageConfig, VerifiedCodexStageRunner

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
    TableExtractionPromptContext,
)
from brand_size_chart.stage.base import CodexStageRun, stage_instruction_list_get
from brand_size_chart.validator import TableExtractionValidator

PROJECT_TEMPLATE_DIR = Path(__file__).parents[1] / "prompt" / "template"


class TableExtractionStage:
    """Extract verified size chart tables from browser-visible evidence."""

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
        """Store batch table-extraction stage dependencies.

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
        self._browser_runtime_mcp_url = browser_runtime_mcp_url
        self._codex_stage_run = codex_stage_run_callable
        self._prompt_scope = prompt_scope
        self._result_dir = result_dir
        self._source_discovery_list = source_discovery_list
        self._source_type = source_type
        self._stage_dir = self._artifact_layout.table_extract_dir(self._brand_input, self._source_type)

    def run(self) -> list[TableExtractionArtifact]:
        """Run batch table extraction plus verification.

        Returns:
            Verified artifact-backed table extractions.
        """

        self._artifact_directory_prepare()
        prompt_context = self._prompt_context_get()
        table_extraction_delta_batch_result = VerifiedCodexStageRunner(
            codex_stage_run_callable=self._codex_stage_run,
            prompt_renderer=PromptRenderer(template_dir=PROJECT_TEMPLATE_DIR),
        ).run(
            config=VerifiedCodexStageConfig(
                browser_runtime_mcp_url=self._browser_runtime_mcp_url,
                prompt_context=prompt_context,
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
                stage_key="table_extract",
            ),
            model_class=TableExtractionDeltaBatchResult,
            mechanical_validate=TableExtractionValidator(
                prompt_context=prompt_context,
                result_dir=self._result_dir,
            ).validate,
        )
        return self._table_extraction_artifact_list_get(
            prompt_context=prompt_context,
            table_extraction_delta_batch_result=table_extraction_delta_batch_result,
        )

    def _artifact_directory_prepare(self) -> None:
        """Create table-extraction directories required before Codex browser execution."""

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

    def _prompt_context_get(self) -> TableExtractionPromptContext:
        """Return batch table-extraction prompt context.

        Returns:
            Prompt context object.
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
        return TableExtractionPromptContext(
            brand_name=self._brand_input.parsed_brand_name,
            execplan_item_list=execplan_item_list,
            shared_instruction=self._prompt_scope.shared_instruction,
            stage_instruction_list=stage_instruction_list_get(
                prompt_scope=self._prompt_scope,
                stage_key="table_extract",
            ),
        )

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
        prompt_context: TableExtractionPromptContext,
        table_extraction_delta_batch_result: TableExtractionDeltaBatchResult,
    ) -> list[TableExtractionArtifact]:
        """Build cross-stage artifact handles from one Codex delta result.

        Args:
            prompt_context: Table-extraction prompt context used by the action and validator.
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
                prompt_context.execplan_item_list,
                table_extraction_delta_batch_result.table_extraction_delta_list,
                strict=True,
            )
        ]
