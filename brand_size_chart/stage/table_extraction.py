"""Table-extraction stage owner."""

from functools import partial
from pathlib import Path

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import BrandInput, PromptScope, SourceDiscovery, TableExtraction
from brand_size_chart.source_extractor import table_extraction_from_discovery_get
from brand_size_chart.stage.base import CodexStageRun
from brand_size_chart.stage.semantic import SemanticStage
from brand_size_chart.validator import TableExtractionValidator


class TableExtractionStage:
    """Extract one verified size chart table from browser-visible evidence."""

    def __init__(
        self,
        *,
        brand_input: BrandInput,
        browser_runtime_mcp_url: str,
        codex_stage_run_callable: CodexStageRun,
        prompt_scope: PromptScope,
        result_dir: Path,
        secret_path: Path,
        source_discovery: SourceDiscovery,
        source_type: str,
        source_type_dir: Path,
    ) -> None:
        """Store table-extraction stage dependencies.

        Args:
            brand_input: Parsed brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope.
            result_dir: Root result directory.
            secret_path: Secret DataSource path.
            source_discovery: Verified source discovery.
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
        self._source_discovery = source_discovery
        self._source_type = source_type
        self._source_type_dir = source_type_dir
        self._validator = TableExtractionValidator(result_dir)

    def run(self) -> TableExtraction:
        """Run table extraction plus verification for one table.

        Returns:
            Verified table extraction.
        """

        table_extraction = self._draft_result_get()
        table_stage_dir = self._artifact_layout.table_extraction_dir(
            self._brand_input,
            self._source_type,
            table_extraction.size_group_key,
        )
        return SemanticStage(
            browser_access=True,
            browser_runtime_mcp_url=self._browser_runtime_mcp_url,
            codex_stage_run_callable=self._codex_stage_run,
            prompt_name="extraction",
            prompt_scope=self._prompt_scope,
            result_dir=self._result_dir,
            stage_dir=table_stage_dir,
            stage_key="table_extraction",
        ).run(
            draft_result=table_extraction,
            model_class=TableExtraction,
            prompt_context=self._prompt_context_get(table_extraction),
            result_error_list_get=partial(
                self._validator.error_list_get,
                source_discovery=self._source_discovery,
            ),
        )

    def _draft_result_get(self) -> TableExtraction:
        """Return deterministic draft extraction from source discovery.

        Returns:
            Draft table extraction.
        """

        _ = self._secret_path
        _ = self._source_type_dir
        return table_extraction_from_discovery_get(
            brand_input=self._brand_input,
            result_dir=self._result_dir,
            source_discovery=self._source_discovery,
        )

    def _prompt_context_get(self, table_extraction: TableExtraction) -> str:
        """Return table-extraction prompt context.

        Args:
            table_extraction: Draft table extraction.

        Returns:
            Prompt context text.
        """

        evidence_dir = self._artifact_layout.table_extraction_evidence_dir(
            self._brand_input,
            self._source_type,
            table_extraction.size_group_key,
        )
        return (
            f"Brand: {self._brand_input.parsed_brand_name}\n"
            f"Source type: {self._source_type}\n"
            f"Source title: {table_extraction.source_title}\n"
            f"Source URL: {table_extraction.source_url}\n"
            f"Target size_group_key: {table_extraction.size_group_key}\n"
            f"Target source title: {table_extraction.source_title}\n"
            f"Source discovery country_code_list: {self._source_discovery.country_code_list}\n"
            f"Browser evidence write directory: {self._artifact_layout.filesystem_path_get(evidence_dir)}\n"
            f"Evidence reference directory: {self._artifact_layout.artifact_path(evidence_dir)}\n"
            f"Source discovery evidence paths: {self._source_discovery.evidence_path_list}\n"
        )
