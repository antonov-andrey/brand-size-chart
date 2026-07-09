"""Source-discovery stage owner."""

from pathlib import Path

from workflow_container_runtime.stage import BrowserActionResult, stage_state_path_get

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandInput,
    PromptScope,
    SourceDiscovery,
    SourceDiscoveryInput,
    SourceDiscoveryResult,
    SourceSurfaceInventory,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.stage.base import BrandSizeChartCodexStepBase, CodexStageRun, stage_instruction_list_get
from brand_size_chart.validator import SourceDiscoveryValidator


class SourceDiscoveryStep(
    BrandSizeChartCodexStepBase[SourceDiscoveryInput, BrowserActionResult, SourceDiscoveryResult]
):
    """Discover concrete size-chart source candidates with browser evidence."""

    stage_key = "source_discover"

    def __init__(
        self,
        *,
        brand_input: BrandInput,
        browser_runtime_mcp_url: str,
        codex_stage_run_callable: CodexStageRun,
        prompt_scope: PromptScope,
        result_dir: Path,
        source_type: str,
    ) -> None:
        """Store source-discovery step dependencies.

        Args:
            brand_input: Parsed brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope for source discovery.
            result_dir: Result root directory.
            source_type: Source type key.
        """

        self._artifact_layout = ArtifactLayout(result_dir)
        self._brand_input = brand_input
        self._prompt_scope = prompt_scope
        self._source_type = source_type
        super().__init__(
            browser_runtime_mcp_url=browser_runtime_mcp_url,
            codex_stage_run_callable=codex_stage_run_callable,
            result_dir=result_dir,
            stage_dir=self._artifact_layout.source_discover_dir(brand_input, source_type),
        )

    def action_output_model_get(self) -> type[BrowserActionResult]:
        """Return the source-discovery action output model.

        Returns:
            Browser action result model.
        """

        return BrowserActionResult

    def artifact_prepare(self, stage_input: SourceDiscoveryInput) -> None:
        """Create source-discovery directories required before Codex browser execution."""

        _ = stage_input
        self._stage_dir.mkdir(parents=True, exist_ok=True)
        self._artifact_layout.source_discover_evidence_dir(self._brand_input, self._source_type).mkdir(
            parents=True,
            exist_ok=True,
        )
        self._artifact_writer.write(
            self._state_schema_path_get(),
            SourceSurfaceInventory.model_json_schema(),
        )

    def input_build(self) -> SourceDiscoveryInput:
        """Return source-discovery input.

        Returns:
            Stage input object.
        """

        evidence_dir = self._artifact_layout.source_discover_evidence_dir(self._brand_input, self._source_type)
        return SourceDiscoveryInput(
            brand_name=self._brand_input.parsed_brand_name,
            evidence_write_target=ArtifactWriteTarget(
                artifact_path=self._artifact_layout.artifact_path(evidence_dir),
                filesystem_path=self._artifact_layout.filesystem_path_get(evidence_dir),
            ),
            priority_country_code=self._prompt_scope.priority_country_code,
            requested_product_type_list=self._prompt_scope.product_type_request_list,
            shared_instruction=self._prompt_scope.shared_instruction,
            source_type=self._source_type,
            source_type_instruction=SOURCE_TYPE_REGISTRY.source_type_discovery_instruction_get(self._source_type),
            stage_instruction_list=stage_instruction_list_get(
                prompt_scope=self._prompt_scope,
                stage_key=self.stage_key,
            ),
        )

    def result_build(
        self, stage_input: SourceDiscoveryInput, action_output: BrowserActionResult
    ) -> SourceDiscoveryResult:
        """Build the public source-discovery result from validated private state.

        Args:
            stage_input: Source-discovery input.
            action_output: Browser action output.

        Returns:
            Public source-discovery result.
        """

        _ = stage_input
        _ = action_output
        source_discovery_list = self._source_discovery_list_get()
        if source_discovery_list:
            warning_list = []
        else:
            inventory = SourceSurfaceInventory.model_validate_json(
                stage_state_path_get(self._stage_dir).read_text(encoding="utf-8")
            )
            warning_list = inventory.no_table_reason_list_get()
        return SourceDiscoveryResult(
            source_discovery_list=source_discovery_list,
            warning_list=warning_list,
        )

    def result_validate(self, result: SourceDiscoveryResult) -> None:
        """Validate public source-discovery result.

        Args:
            result: Public source-discovery result.
        """

        SourceDiscoveryValidator(
            stage_input=self.input_build(),
            result_dir=self._result_dir,
            stage_dir=self._stage_dir,
        ).validate(result)

    def _state_schema_path_get(self) -> Path:
        """Return generated source-surface inventory schema path.

        Returns:
            Source-surface inventory schema artifact path.
        """

        return self._stage_dir / "state.schema.json"

    def _source_discovery_list_get(self) -> list[SourceDiscovery]:
        """Build cross-stage source discovery list from validated inventory.

        Returns:
            Python-built cross-stage source discovery list.
        """

        inventory = SourceSurfaceInventory.model_validate_json(
            stage_state_path_get(self._stage_dir).read_text(encoding="utf-8")
        )
        return [
            source_surface_table.source_discovery
            for source_surface_table in inventory.table_list
            if source_surface_table.state == "accepted"
        ]
