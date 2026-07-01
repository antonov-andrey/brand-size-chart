"""Table-level DBOS workflow owner."""

from pathlib import Path

from dbos import DBOS, DBOSConfiguredInstance

from brand_size_chart.codex.runner import codex_stage_run
from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import BrandInput, PromptScope, SourceDiscovery
from brand_size_chart.workflow.base import table_stage_run


@DBOS.dbos_class("BrandSizeChartTableWorkflow")
class BrandSizeChartTableWorkflow(DBOSConfiguredInstance):
    """DBOS owner for one table workflow and table extraction side-effect step."""

    def __init__(self) -> None:
        """Register the stable stateless DBOS instance."""

        super().__init__("default")

    @DBOS.workflow(name="brand_size_chart_table")
    def run(
        self,
        brand_input_payload: dict[str, object],
        browser_runtime_mcp_url: str,
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        secret_ref: str,
        source_type: str,
        source_discovery_payload: dict[str, object],
    ) -> dict[str, object]:
        """Process one size-chart table.

        Args:
            brand_input_payload: Serialized brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Root result directory string.
            secret_ref: Secret DataSource path string.
            source_type: Source type key.
            source_discovery_payload: Serialized source discovery.

        Returns:
            Serialized verified table extraction.
        """
        return self.stage_write_step(
            brand_input_payload,
            browser_runtime_mcp_url,
            prompt_scope_payload,
            result_dir,
            secret_ref,
            source_type,
            source_discovery_payload,
        )

    @DBOS.step(name="table_stage_write_step")
    def stage_write_step(
        self,
        brand_input_payload: dict[str, object],
        browser_runtime_mcp_url: str,
        prompt_scope_payload: dict[str, object],
        result_dir: str,
        secret_ref: str,
        source_type: str,
        source_discovery_payload: dict[str, object],
    ) -> dict[str, object]:
        """Write table extraction and verification artifacts.

        Args:
            brand_input_payload: Serialized brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            prompt_scope_payload: Serialized prompt scope.
            result_dir: Root result directory string.
            secret_ref: Secret DataSource path string.
            source_type: Source type key.
            source_discovery_payload: Serialized source discovery.

        Returns:
            Serialized verified table extraction.
        """
        brand_input = BrandInput.model_validate(brand_input_payload)
        prompt_scope = PromptScope.model_validate(prompt_scope_payload)
        result_dir_path = Path(result_dir)
        artifact_layout = ArtifactLayout(result_dir_path)
        source_type_dir = artifact_layout.source_type_dir(brand_input, source_type)
        table_extraction = table_stage_run(
            brand_input=brand_input,
            browser_runtime_mcp_url=browser_runtime_mcp_url,
            codex_stage_run_callable=codex_stage_run,
            prompt_scope=prompt_scope,
            result_dir=result_dir_path,
            secret_path=Path(secret_ref),
            source_discovery=SourceDiscovery.model_validate(source_discovery_payload),
            source_type=source_type,
            source_type_dir=source_type_dir,
        )
        return table_extraction.model_dump(mode="json")


BRAND_SIZE_CHART_TABLE_WORKFLOW = BrandSizeChartTableWorkflow()
brand_size_chart_table = BRAND_SIZE_CHART_TABLE_WORKFLOW.run
table_stage_write_step = BRAND_SIZE_CHART_TABLE_WORKFLOW.stage_write_step

__all__ = [
    "BRAND_SIZE_CHART_TABLE_WORKFLOW",
    "BrandSizeChartTableWorkflow",
    "brand_size_chart_table",
    "table_stage_write_step",
]
