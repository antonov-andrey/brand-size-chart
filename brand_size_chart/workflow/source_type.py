"""Source-type DBOS workflow owner."""

from pathlib import Path

from dbos import DBOS
from workflow_container_runtime.artifact import JsonArtifactWriter

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    BrandInput,
    PromptScope,
    SourceDiscovery,
    SourceDiscoveryResult,
    SourceTypeResult,
    TableExtractionArtifact,
    TableExtractionResult,
)
from brand_size_chart.stage import SourceDiscoveryStep, TableExtractionStep
from brand_size_chart.workflow.codex import BrandSizeChartCodexWorkflow


@DBOS.dbos_class("BrandSizeChartSourceTypeWorkflow")
class BrandSizeChartSourceTypeWorkflow(BrandSizeChartCodexWorkflow):
    """DBOS owner for one source type and source-type side-effect steps."""

    @DBOS.workflow(name="brand_size_chart_source_type")
    def run(
        self,
        workflow_run_id: str,
        brand_input_payload: dict[str, object],
        browser_runtime_mcp_url: str,
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        source_type: str,
    ) -> dict[str, object]:
        """Process one source type with one batch table-extraction step.

        Args:
            workflow_run_id: Stable workflow run identifier.
            brand_input_payload: Serialized brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Root result directory string.
            source_type: Source type key.

        Returns:
            Serialized source-type result.
        """
        brand_input = BrandInput.model_validate(brand_input_payload)
        prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        verified_table_extraction_payload_list: list[dict[str, object]] = []
        blocker_list: list[str] = []
        source_discovery_warning_list: list[str] = []
        try:
            source_discovery_payload = self.source_discover_write_step(
                brand_input.model_dump(mode="json"),
                browser_runtime_mcp_url,
                prompt_scope.model_dump(mode="json"),
                result_dir,
                source_type,
            )
            source_discovery_result = SourceDiscoveryResult.model_validate(source_discovery_payload)
            source_discovery_warning_list = list(source_discovery_result.warning_list)
            if source_discovery_result.source_discovery_list:
                table_extraction_payload = self.table_extract_write_step(
                    brand_input.model_dump(mode="json"),
                    browser_runtime_mcp_url,
                    prompt_scope.model_dump(mode="json"),
                    result_dir,
                    source_type,
                    [
                        source_discovery.model_dump(mode="json")
                        for source_discovery in source_discovery_result.source_discovery_list
                    ],
                )
                table_extraction_result = TableExtractionResult.model_validate(table_extraction_payload)
                verified_table_extraction_payload_list.extend(
                    [
                        table_extraction.model_dump(mode="json")
                        for table_extraction in table_extraction_result.table_extraction_list
                    ]
                )
        except RuntimeError as exc:
            blocker_list.append(f"{type(exc).__name__}: {exc}")
        source_type_result_payload = self.result_write_step(
            brand_input.model_dump(mode="json"),
            result_dir,
            source_type,
            verified_table_extraction_payload_list,
            blocker_list,
            source_discovery_warning_list,
        )
        return source_type_result_payload

    @DBOS.step(name="source_discover_write_step")
    def source_discover_write_step(
        self,
        brand_input_payload: dict[str, object],
        browser_runtime_mcp_url: str,
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        source_type: str,
    ) -> dict[str, object]:
        """Write source discovery result and verification.

        Args:
            brand_input_payload: Serialized brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Root result directory string.
            source_type: Source type key.

        Returns:
            Serialized source-discovery result.
        """
        brand_input = BrandInput.model_validate(brand_input_payload)
        prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        result_dir_path = Path(result_dir)
        source_discovery_result = SourceDiscoveryStep(
            brand_input=brand_input,
            browser_runtime_mcp_url=browser_runtime_mcp_url,
            codex_stage_run_callable=self._codex_stage_runner.run,
            prompt_scope=prompt_scope,
            result_dir=result_dir_path,
            source_type=source_type,
        ).run()
        return source_discovery_result.model_dump(mode="json")

    @DBOS.step(name="table_extract_write_step")
    def table_extract_write_step(
        self,
        brand_input_payload: dict[str, object],
        browser_runtime_mcp_url: str,
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        source_type: str,
        source_discovery_payload_list: list[dict[str, object]],
    ) -> dict[str, object]:
        """Write batch table extraction and chart artifacts.

        Args:
            brand_input_payload: Serialized brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Root result directory string.
            source_type: Source type key.
            source_discovery_payload_list: Serialized source discoveries.

        Returns:
            Serialized table-extraction result.
        """

        brand_input = BrandInput.model_validate(brand_input_payload)
        prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        result_dir_path = Path(result_dir)
        table_extraction_result = TableExtractionStep(
            brand_input=brand_input,
            browser_runtime_mcp_url=browser_runtime_mcp_url,
            codex_stage_run_callable=self._codex_stage_runner.run,
            prompt_scope=prompt_scope,
            result_dir=result_dir_path,
            source_discovery_list=[
                SourceDiscovery.model_validate(source_discovery_payload)
                for source_discovery_payload in source_discovery_payload_list
            ],
            source_type=source_type,
        ).run()
        return table_extraction_result.model_dump(mode="json")

    @DBOS.step(name="source_type_result_write_step")
    def result_write_step(
        self,
        brand_input_payload: dict[str, object],
        result_dir: str,
        source_type: str,
        table_extraction_payload_list: list[dict[str, object]],
        blocker_list: list[str],
        source_discovery_warning_list: list[str],
    ) -> dict[str, object]:
        """Write source-type workflow result.

        Args:
            brand_input_payload: Serialized brand input.
            result_dir: Root result directory string.
            source_type: Source type key.
            table_extraction_payload_list: Serialized verified table extractions.
            blocker_list: Source-type blocker messages collected during discovery or extraction.
            source_discovery_warning_list: Source-discovery no-table warning list.

        Returns:
            Serialized source-type result.
        """
        brand_input = BrandInput.model_validate(brand_input_payload)
        result_dir_path = Path(result_dir)
        artifact_layout = ArtifactLayout(result_dir_path)
        table_extraction_list = [
            TableExtractionArtifact.model_validate(table_extraction_payload)
            for table_extraction_payload in table_extraction_payload_list
        ]
        source_type_result = SourceTypeResult(
            blocker_list=blocker_list,
            source_type=source_type,
            table_extraction_list=table_extraction_list,
            warning_list=[] if blocker_list or table_extraction_list else source_discovery_warning_list,
        )
        JsonArtifactWriter().write(
            artifact_layout.source_type_result_path(brand_input, source_type),
            source_type_result,
        )
        return source_type_result.model_dump(mode="json")


BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW = BrandSizeChartSourceTypeWorkflow()

__all__ = [
    "BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW",
    "BrandSizeChartSourceTypeWorkflow",
]
