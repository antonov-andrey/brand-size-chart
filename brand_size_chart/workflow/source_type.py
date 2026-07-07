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
    SourceTypeSummary,
    TableExtractionArtifact,
)
from brand_size_chart.stage import SourceDiscoveryStage, TableExtractionStage
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
            Serialized source-type summary and verified table list.
        """
        brand_input = BrandInput.model_validate(brand_input_payload)
        prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        verified_table_extraction_payload_list: list[dict[str, object]] = []
        blocker_list: list[str] = []
        warning_list: list[str] = []
        try:
            discovery_result_payload = self.source_discover_write_step(
                brand_input.model_dump(mode="json"),
                browser_runtime_mcp_url,
                prompt_scope.model_dump(mode="json"),
                result_dir,
                source_type,
            )
            discovery_result = SourceDiscoveryResult.model_validate(discovery_result_payload)
            if not discovery_result.discovered_source_list:
                warning_list.extend(discovery_result.no_table_reason_list)
            else:
                table_extraction_payload_list = self.table_extract_write_step(
                    brand_input.model_dump(mode="json"),
                    browser_runtime_mcp_url,
                    prompt_scope.model_dump(mode="json"),
                    result_dir,
                    source_type,
                    [
                        source_discovery.model_dump(mode="json")
                        for source_discovery in discovery_result.discovered_source_list
                    ],
                )
                verified_table_extraction_payload_list.extend(
                    [
                        TableExtractionArtifact.model_validate(table_extraction_payload).model_dump(mode="json")
                        for table_extraction_payload in table_extraction_payload_list
                    ]
                )
        except RuntimeError as exc:
            blocker_list.append(f"{type(exc).__name__}: {exc}")
        source_type_summary_payload = self.summary_write_step(
            brand_input.model_dump(mode="json"),
            result_dir,
            source_type,
            verified_table_extraction_payload_list,
            blocker_list,
            warning_list,
        )
        return {
            "source_type_summary": source_type_summary_payload,
            "table_extraction_list": verified_table_extraction_payload_list,
        }

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
            Serialized source discovery result.
        """
        brand_input = BrandInput.model_validate(brand_input_payload)
        prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        result_dir_path = Path(result_dir)
        discovery_result = SourceDiscoveryStage(
            brand_input=brand_input,
            browser_runtime_mcp_url=browser_runtime_mcp_url,
            codex_stage_run_callable=self._codex_stage_runner.run,
            prompt_scope=prompt_scope,
            result_dir=result_dir_path,
            source_type=source_type,
        ).run()
        return discovery_result.model_dump(mode="json")

    @DBOS.step(name="table_extract_write_step")
    def table_extract_write_step(
        self,
        brand_input_payload: dict[str, object],
        browser_runtime_mcp_url: str,
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        source_type: str,
        source_discovery_payload_list: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Write batch table extraction and chart artifacts.

        Args:
            brand_input_payload: Serialized brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Root result directory string.
            source_type: Source type key.
            source_discovery_payload_list: Serialized source discoveries.

        Returns:
            Serialized verified table extraction list.
        """

        brand_input = BrandInput.model_validate(brand_input_payload)
        prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        result_dir_path = Path(result_dir)
        table_extraction_list = TableExtractionStage(
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
        return [table_extraction.model_dump(mode="json") for table_extraction in table_extraction_list]

    @DBOS.step(name="source_type_summary_write_step")
    def summary_write_step(
        self,
        brand_input_payload: dict[str, object],
        result_dir: str,
        source_type: str,
        table_extraction_payload_list: list[dict[str, object]],
        blocker_list: list[str],
        warning_list: list[str],
    ) -> dict[str, object]:
        """Write source-type summary.

        Args:
            brand_input_payload: Serialized brand input.
            result_dir: Root result directory string.
            source_type: Source type key.
            table_extraction_payload_list: Serialized verified table extractions.
            blocker_list: Source-type blocker messages collected during discovery or extraction.
            warning_list: Non-fatal source-type warnings collected during discovery.

        Returns:
            Serialized source-type summary.
        """
        brand_input = BrandInput.model_validate(brand_input_payload)
        result_dir_path = Path(result_dir)
        artifact_layout = ArtifactLayout(result_dir_path)
        table_extraction_list = [
            TableExtractionArtifact.model_validate(table_extraction_payload)
            for table_extraction_payload in table_extraction_payload_list
        ]
        summary = SourceTypeSummary(
            blocker_list=blocker_list,
            source_type=source_type,
            state="failed" if blocker_list else ("passed" if table_extraction_list else "skipped"),
            warning_list=warning_list,
        )
        JsonArtifactWriter().write(artifact_layout.source_type_summary_result_path(brand_input, source_type), summary)
        return summary.model_dump(mode="json")


BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW = BrandSizeChartSourceTypeWorkflow()

__all__ = [
    "BRAND_SIZE_CHART_SOURCE_TYPE_WORKFLOW",
    "BrandSizeChartSourceTypeWorkflow",
]
