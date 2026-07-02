"""Source-discovery stage owner."""

from functools import partial
from pathlib import Path

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import BrandInput, PromptScope, SourceDiscoveryResult
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.source_extractor import source_discovery_result_get
from brand_size_chart.stage.base import CodexStageRun
from brand_size_chart.stage.semantic import SemanticStage
from brand_size_chart.validator import SourceDiscoveryValidator


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
        secret_path: Path,
        source_priority: int,
        source_type: str,
        source_type_dir: Path,
    ) -> None:
        """Store source-discovery stage dependencies.

        Args:
            brand_input: Parsed brand input.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope for source discovery.
            result_dir: Result root directory.
            secret_path: Secret DataSource path.
            source_priority: Source type priority.
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
        self._source_priority = source_priority
        self._source_type = source_type
        self._source_type_dir = source_type_dir
        self._stage_dir = self._artifact_layout.source_discovery_dir(brand_input, source_type)
        self._validator = SourceDiscoveryValidator(result_dir=result_dir, stage_dir=self._stage_dir)

    def run(self) -> SourceDiscoveryResult:
        """Run source discovery from rendered evidence.

        Returns:
            Verified source discovery result.
        """

        draft_result = self._draft_result_get()
        return SemanticStage(
            browser_access=True,
            browser_runtime_mcp_url=self._browser_runtime_mcp_url,
            codex_stage_run_callable=self._codex_stage_run,
            prompt_name="discovery",
            prompt_scope=self._prompt_scope,
            result_dir=self._result_dir,
            stage_dir=self._stage_dir,
            stage_key="source_discovery",
        ).run(
            draft_result=draft_result,
            model_class=SourceDiscoveryResult,
            prompt_context=self._prompt_context_get(draft_result),
            result_error_list_get=partial(
                self._validator.error_list_get,
                expected_source_priority=self._source_priority,
                expected_source_type=self._source_type,
                prompt_scope=self._prompt_scope,
            ),
        )

    def _draft_result_get(self) -> SourceDiscoveryResult:
        """Return draft source discovery for one source type.

        Returns:
            Draft source discovery result.
        """

        return source_discovery_result_get(
            brand_input=self._brand_input,
            result_dir=self._result_dir,
            secret_path=self._secret_path,
            source_type=self._source_type,
            source_type_dir=self._source_type_dir,
        )

    def _prompt_context_get(self, draft_result: SourceDiscoveryResult) -> str:
        """Return source-discovery prompt context.

        Args:
            draft_result: Deterministic draft source discovery.

        Returns:
            Prompt context text.
        """

        evidence_dir = self._artifact_layout.source_discovery_evidence_dir(self._brand_input, self._source_type)
        requested_product_type_text = (
            "\n".join(f"- {product_type}" for product_type in self._prompt_scope.product_type_request_list) or "- none"
        )
        return (
            f"Brand: {self._brand_input.parsed_brand_name}\n"
            f"Source type: {self._source_type}\n"
            f"Source priority: {self._source_priority}\n"
            f"Priority country code: {self._prompt_scope.priority_country_code}\n"
            f"Requested product types:\n{requested_product_type_text}\n"
            f"Source type instruction: {SOURCE_TYPE_REGISTRY.source_type_discovery_instruction_get(self._source_type)}\n"
            f"Browser evidence write directory: {self._artifact_layout.filesystem_path_get(evidence_dir)}\n"
            f"Evidence reference directory: {self._artifact_layout.artifact_path(evidence_dir)}\n"
        )
