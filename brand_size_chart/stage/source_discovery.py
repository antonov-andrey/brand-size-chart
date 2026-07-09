"""Source-discovery stage owner."""

from pathlib import Path

from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.stage import BrowserActionResult

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
from brand_size_chart.stage.base import (
    CodexStageRun,
    VerifiedCodexStageConfig,
    VerifiedCodexStageRunner,
    stage_instruction_list_get,
)
from brand_size_chart.validator import SourceDiscoveryValidator

PROJECT_TEMPLATE_DIR = Path(__file__).parents[1] / "prompt" / "template"


class SourceDiscoveryStage:
    """Discover concrete size-chart source candidates with browser evidence."""

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
        """Store source-discovery stage dependencies.

        Args:
            brand_input: Parsed brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope for source discovery.
            result_dir: Result root directory.
            source_type: Source type key.
        """

        self._artifact_layout = ArtifactLayout(result_dir)
        self._artifact_writer = JsonArtifactWriter()
        self._brand_input = brand_input
        self._browser_runtime_mcp_url = browser_runtime_mcp_url
        self._codex_stage_run = codex_stage_run_callable
        self._prompt_scope = prompt_scope
        self._result_dir = result_dir
        self._source_type = source_type
        self._stage_dir = self._artifact_layout.source_discover_dir(brand_input, source_type)

    def run(self) -> list[SourceDiscovery]:
        """Run source discovery from rendered evidence.

        Returns:
            Verified source discovery list.
        """

        self._artifact_directory_prepare()
        stage_input = self._stage_input_get()
        VerifiedCodexStageRunner(
            codex_stage_run_callable=self._codex_stage_run,
            prompt_renderer=PromptRenderer(template_dir=PROJECT_TEMPLATE_DIR),
        ).run(
            config=VerifiedCodexStageConfig(
                browser_runtime_mcp_url=self._browser_runtime_mcp_url,
                prompt_context=stage_input,
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
                stage_key="source_discover",
            ),
            model_class=BrowserActionResult,
            mechanical_validate=SourceDiscoveryValidator(
                stage_input=stage_input,
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
            ).validate,
        )
        return self._result_get().source_discovery_list

    def _artifact_directory_prepare(self) -> None:
        """Create source-discovery directories required before Codex browser execution."""

        self._stage_dir.mkdir(parents=True, exist_ok=True)
        self._artifact_layout.source_discover_evidence_dir(self._brand_input, self._source_type).mkdir(
            parents=True,
            exist_ok=True,
        )
        self._artifact_writer.write(
            self._state_schema_path_get(),
            SourceSurfaceInventory.model_json_schema(),
        )

    def _result_get(self) -> SourceDiscoveryResult:
        """Build the public source-discovery result from validated private state.

        Returns:
            Public source-discovery result.
        """

        return SourceDiscoveryResult(
            source_discovery_list=self._source_discovery_list_get(),
            warning_list=[],
        )

    def _stage_input_get(self) -> SourceDiscoveryInput:
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
                stage_key="source_discover",
            ),
        )

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
            (self._stage_dir / "state.json").read_text(encoding="utf-8")
        )
        return [
            source_surface_table.source_discovery
            for source_surface_table in inventory.table_list
            if source_surface_table.state == "accepted"
        ]
