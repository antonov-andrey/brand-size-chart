"""Coverage-decision stage owner."""

from pathlib import Path

from brand_size_chart.model import (
    BrandInput,
    CoverageDecisionInput,
    CoverageDecisionResult,
    PromptScope,
    TableExtractionArtifact,
)
from brand_size_chart.stage.base import BrandSizeChartCodexStepBase, CodexStageRun, stage_instruction_list_get
from brand_size_chart.validator import CoverageDecisionValidator


class CoverageDecisionStep(
    BrandSizeChartCodexStepBase[CoverageDecisionInput, CoverageDecisionResult, CoverageDecisionResult]
):
    """Decide requested product-type coverage from verified table extractions."""

    stage_key = "coverage_decide"

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
        """Store coverage-decision step dependencies.

        Args:
            brand_input: Parsed brand input.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            table_extraction_list: Verified table extractions.
        """

        self._brand_input = brand_input
        self._prompt_scope = prompt_scope
        self._table_extraction_list = table_extraction_list
        super().__init__(
            codex_stage_run_callable=codex_stage_run_callable,
            result_dir=result_dir,
            stage_dir=stage_dir,
        )

    def action_output_model_get(self) -> type[CoverageDecisionResult]:
        """Return the coverage-decision action output model.

        Returns:
            Coverage decision result model.
        """

        return CoverageDecisionResult

    def input_build(self) -> CoverageDecisionInput:
        """Return coverage-decision input.

        Returns:
            Stage input object.
        """

        return CoverageDecisionInput(
            brand_name=self._brand_input.parsed_brand_name,
            requested_product_type_list=self._prompt_scope.product_type_request_list,
            shared_instruction=self._prompt_scope.shared_instruction,
            stage_instruction_list=stage_instruction_list_get(
                prompt_scope=self._prompt_scope,
                stage_key=self.stage_key,
            ),
            verified_table_artifact_list=self._table_extraction_list,
        )

    def result_build(
        self, stage_input: CoverageDecisionInput, action_output: CoverageDecisionResult
    ) -> CoverageDecisionResult:
        """Return public coverage result from the action output.

        Args:
            stage_input: Coverage-decision input.
            action_output: Codex-owned coverage result.

        Returns:
            Public coverage decision result.
        """

        _ = stage_input
        return action_output

    def result_validate(self, result: CoverageDecisionResult) -> None:
        """Validate public coverage decision result.

        Args:
            result: Public coverage decision result.
        """

        CoverageDecisionValidator(stage_input=self.input_build()).validate(result)
