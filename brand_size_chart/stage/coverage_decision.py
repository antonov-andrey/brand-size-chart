"""Coverage-decision stage owner."""

from pathlib import Path

from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.stage import VerifiedCodexStageConfig, VerifiedCodexStageRunner

from brand_size_chart.model import (
    BrandInput,
    CoverageDecisionPromptContext,
    CoverageDecisionResult,
    PromptScope,
    TableExtractionArtifact,
)
from brand_size_chart.stage.base import CodexStageRun, stage_instruction_list_get
from brand_size_chart.validator import CoverageDecisionValidator

PROJECT_TEMPLATE_DIR = Path(__file__).parents[1] / "prompt" / "template"


class CoverageDecisionStage:
    """Decide requested product-type coverage from verified table extractions."""

    def __init__(
        self,
        *,
        brand_input: BrandInput,
        codex_stage_run_callable: CodexStageRun,
        prompt_scope: PromptScope,
        result_dir: Path,
        stage_dir: Path,
        table_extraction_list: list[TableExtractionArtifact],
    ) -> None:
        """Store coverage-decision stage dependencies.

        Args:
            brand_input: Parsed brand input.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            table_extraction_list: Verified table extractions.
        """

        self._brand_input = brand_input
        self._codex_stage_run = codex_stage_run_callable
        self._prompt_scope = prompt_scope
        self._result_dir = result_dir
        self._stage_dir = stage_dir
        self._table_extraction_list = table_extraction_list

    def run(self) -> CoverageDecisionResult:
        """Return semantically verified coverage for requested product types.

        Returns:
            Verified coverage decision result.
        """

        prompt_context = self._prompt_context_get()
        coverage_decision_result = VerifiedCodexStageRunner(
            codex_stage_run_callable=self._codex_stage_run,
            prompt_renderer=PromptRenderer(template_dir=PROJECT_TEMPLATE_DIR),
        ).run(
            config=VerifiedCodexStageConfig(
                prompt_context=prompt_context,
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
                stage_key="coverage_decide",
            ),
            model_class=CoverageDecisionResult,
            mechanical_validate=CoverageDecisionValidator(prompt_context=prompt_context).validate,
        )
        return coverage_decision_result

    def _prompt_context_get(self) -> CoverageDecisionPromptContext:
        """Return coverage-decision prompt context.

        Returns:
            Prompt context object.
        """

        return CoverageDecisionPromptContext(
            brand_name=self._brand_input.parsed_brand_name,
            requested_product_type_list=self._prompt_scope.product_type_request_list,
            shared_instruction=self._prompt_scope.shared_instruction,
            stage_instruction_list=stage_instruction_list_get(
                prompt_scope=self._prompt_scope,
                stage_key="coverage_decide",
            ),
            verified_table_artifact_list=self._table_extraction_list,
        )
