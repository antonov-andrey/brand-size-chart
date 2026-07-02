"""Table-extraction stage owner."""

from functools import partial
from pathlib import Path

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    BrandInput,
    PromptScope,
    SourceDiscovery,
    TableExtractionArtifactBatchResult,
    TableExtractionBatchResult,
)
from brand_size_chart.source_extractor import table_extraction_artifact_from_discovery_get
from brand_size_chart.stage.base import CodexStageRun
from brand_size_chart.stage.semantic import SemanticStage
from brand_size_chart.validator import TableExtractionValidator


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
        secret_path: Path,
        source_discovery_list: list[SourceDiscovery],
        source_type: str,
        source_type_dir: Path,
    ) -> None:
        """Store batch table-extraction stage dependencies.

        Args:
            brand_input: Parsed brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope.
            result_dir: Root result directory.
            secret_path: Secret DataSource path.
            source_discovery_list: Verified source discoveries.
            source_type: Source type key.
            source_type_dir: Source-type audit directory.
        """

        self._artifact_layout = ArtifactLayout(result_dir)
        self._brand_input = brand_input
        self._browser_runtime_mcp_url = browser_runtime_mcp_url
        self._codex_stage_run = codex_stage_run_callable
        self._prompt_scope = prompt_scope
        self._result_dir = result_dir
        self._secret_path = secret_path
        self._source_discovery_list = source_discovery_list
        self._source_type = source_type
        self._source_type_dir = source_type_dir
        self._validator = TableExtractionValidator(result_dir)

    def run(self) -> TableExtractionBatchResult:
        """Run batch table extraction plus verification.

        Returns:
            Verified batch table extraction.
        """

        table_extraction_artifact_batch_result = SemanticStage(
            browser_access=True,
            browser_runtime_mcp_url=self._browser_runtime_mcp_url,
            codex_stage_run_callable=self._codex_stage_run,
            prompt_name="table_extract",
            prompt_scope=self._prompt_scope,
            result_dir=self._result_dir,
            stage_dir=self._artifact_layout.table_extract_dir(self._brand_input, self._source_type),
            stage_key="table_extract",
        ).run(
            draft_result=self._draft_artifact_result_get(),
            model_class=TableExtractionArtifactBatchResult,
            prompt_context=self._prompt_context_get(),
            result_error_list_get=partial(
                self._validator.artifact_error_list_get,
                source_discovery_list=self._source_discovery_list,
            ),
        )
        return self._validator.table_extraction_batch_result_get(
            table_extraction_artifact_batch_result,
            source_discovery_list=self._source_discovery_list,
        )

    def _draft_artifact_result_get(self) -> TableExtractionArtifactBatchResult:
        """Return deterministic draft extraction-artifact batch from source discoveries.

        Returns:
            Draft batch table extraction artifact result.
        """

        _ = self._secret_path
        _ = self._source_type_dir
        return TableExtractionArtifactBatchResult(
            message="Codex table extraction has not produced chart artifacts yet.",
            source_type=self._source_type,
            status="skipped",
            table_extraction_artifact_list=[
                table_extraction_artifact_from_discovery_get(
                    brand_input=self._brand_input,
                    chart_path=self._artifact_layout.table_extract_chart_path(
                        self._brand_input,
                        self._source_type,
                        source_discovery.size_group_key,
                    ),
                    result_dir=self._result_dir,
                    source_discovery=source_discovery,
                )
                for source_discovery in self._source_discovery_list
            ],
        )

    def _prompt_context_get(self) -> str:
        """Return batch table-extraction prompt context.

        Returns:
            Prompt context text.
        """

        execplan_line_list = []
        chart_dir = self._artifact_layout.table_extract_dir(self._brand_input, self._source_type) / "chart"
        for discovery_index, source_discovery in enumerate(self._source_discovery_list, start=1):
            evidence_dir = self._table_extract_evidence_dir_get(source_discovery)
            chart_path = self._artifact_layout.table_extract_chart_path(
                self._brand_input,
                self._source_type,
                source_discovery.size_group_key,
            )
            execplan_line_list.append(
                "\n".join(
                    [
                        f"{discovery_index}. size_group_key={source_discovery.size_group_key}",
                        f"   Source title: {source_discovery.source_title}",
                        f"   Source URL: {source_discovery.source_url}",
                        f"   Source discovery source_type: {source_discovery.source_type}",
                        f"   Source discovery product_type_hint_list: {source_discovery.product_type_hint_list}",
                        f"   Target size_group_key: {source_discovery.size_group_key}",
                        f"   Target source title: {source_discovery.source_title}",
                        f"   Source discovery country_code_list: {source_discovery.country_code_list}",
                        f"   Browser evidence write directory: {self._artifact_layout.filesystem_path_get(evidence_dir)}",
                        f"   Evidence reference directory: {self._artifact_layout.artifact_path(evidence_dir)}",
                        f"   Source discovery evidence paths: {source_discovery.evidence_path_list}",
                        f"   Chart artifact path: {self._artifact_layout.artifact_path(chart_path)}",
                        f"   Chart artifact filesystem path: {self._artifact_layout.filesystem_path_get(chart_path)}",
                    ]
                )
            )
        execplan_text = "\n".join(execplan_line_list)
        return (
            f"Brand: {self._brand_input.parsed_brand_name}\n"
            f"Source type: {self._source_type}\n"
            f"Stage chart artifact write directory: {self._artifact_layout.filesystem_path_get(chart_dir)}\n"
            "Batch table_extract execplan:\n"
            f"{execplan_text}\n"
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
            source_discovery.source_type,
            source_discovery.size_group_key,
        )
