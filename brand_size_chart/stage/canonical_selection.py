"""Canonical-selection stage owner."""

from pathlib import Path

from workflow_container_runtime.stage import WorkflowStepBase

from brand_size_chart.model import (
    CanonicalSelectionCandidate,
    CanonicalSelectionInput,
    CanonicalSelectionResult,
    PromptScope,
    TableExtractionArtifact,
)
from brand_size_chart.source import (
    SOURCE_TYPE_REGISTRY,
    is_applicability_status_canonical,
    table_extraction_applicability_status_get,
)
from brand_size_chart.stage.base import BrandSizeChartCodexStepBase, CodexStageRun, stage_instruction_list_get
from brand_size_chart.validator import CanonicalSelectionValidator


class CanonicalSelectionStep(
    BrandSizeChartCodexStepBase[CanonicalSelectionInput, CanonicalSelectionResult, CanonicalSelectionResult]
):
    """Select canonical tables from verified table extractions."""

    stage_key = "canonical_select"

    def __init__(
        self,
        *,
        brand_name: str,
        codex_stage_run_callable: CodexStageRun,
        prompt_scope: PromptScope,
        result_dir: Path,
        stage_dir: Path,
        table_extraction_list: list[TableExtractionArtifact],
    ) -> None:
        """Store canonical-selection step dependencies.

        Args:
            brand_name: Parsed brand display name.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            table_extraction_list: Verified table extractions.
        """

        self._brand_name = brand_name
        self._prompt_scope = prompt_scope
        self._table_extraction_list = table_extraction_list
        super().__init__(
            codex_stage_run_callable=codex_stage_run_callable,
            result_dir=result_dir,
            stage_dir=stage_dir,
        )

    def action_output_model_get(self) -> type[CanonicalSelectionResult]:
        """Return the canonical-selection action output model.

        Returns:
            Canonical selection result model.
        """

        return CanonicalSelectionResult

    def run(self) -> CanonicalSelectionResult:
        """Return semantically verified canonical selection.

        Returns:
            Verified canonical selection result.
        """

        stage_input = self._stage_input_get()
        if not stage_input.canonical_selection_candidate_list:
            return _CanonicalSelectionEmptyStep(
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
                stage_input=stage_input,
            ).run()
        return super().run()

    def input_build(self) -> CanonicalSelectionInput:
        """Return canonical-selection input with verified candidate tables.

        Returns:
            Stage input object.
        """

        return self._stage_input_get()

    def result_build(
        self, stage_input: CanonicalSelectionInput, action_output: CanonicalSelectionResult
    ) -> CanonicalSelectionResult:
        """Return public canonical selection result from the action output.

        Args:
            stage_input: Canonical-selection input.
            action_output: Codex-owned canonical selection result.

        Returns:
            Public canonical selection result.
        """

        _ = stage_input
        return action_output

    def result_validate(self, result: CanonicalSelectionResult) -> None:
        """Validate public canonical selection result.

        Args:
            result: Public canonical selection result.
        """

        CanonicalSelectionValidator(stage_input=self.input_build()).validate(result)

    def _stage_input_get(self) -> CanonicalSelectionInput:
        """Return canonical-selection input with verified candidate tables.

        Returns:
            Stage input object.
        """

        canonical_selection_candidate_list: list[CanonicalSelectionCandidate] = []
        for table_extraction in self._table_extraction_list:
            applicability_status = table_extraction_applicability_status_get(
                table_extraction,
                priority_country_code=self._prompt_scope.priority_country_code,
            )
            if not is_applicability_status_canonical(applicability_status):
                continue
            canonical_selection_candidate_list.append(
                CanonicalSelectionCandidate(
                    applicability_status=applicability_status,
                    source_priority=SOURCE_TYPE_REGISTRY.source_type_priority_get(table_extraction.source_type),
                    table_extraction_artifact=table_extraction,
                )
            )
        return CanonicalSelectionInput(
            brand_name=self._brand_name,
            canonical_selection_candidate_list=canonical_selection_candidate_list,
            shared_instruction=self._prompt_scope.shared_instruction,
            stage_instruction_list=stage_instruction_list_get(
                prompt_scope=self._prompt_scope,
                stage_key=self.stage_key,
            ),
        )


class _CanonicalSelectionEmptyStep(WorkflowStepBase[CanonicalSelectionInput, CanonicalSelectionResult]):
    """Deterministic canonical-selection step for an empty candidate set."""

    def __init__(self, *, result_dir: Path, stage_dir: Path, stage_input: CanonicalSelectionInput) -> None:
        """Store deterministic empty-selection input.

        Args:
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_input: Canonical-selection input with no candidates.
        """

        super().__init__(result_dir=result_dir, stage_dir=stage_dir)
        self._stage_input = stage_input

    def input_build(self) -> CanonicalSelectionInput:
        """Return deterministic empty-selection input.

        Returns:
            Canonical-selection input.
        """

        return self._stage_input

    def result_build(self, stage_input: CanonicalSelectionInput) -> CanonicalSelectionResult:
        """Return deterministic empty canonical-selection result.

        Args:
            stage_input: Canonical-selection input with no candidates.

        Returns:
            Empty canonical-selection result.
        """

        _ = stage_input
        return CanonicalSelectionResult(canonical_selection_list=[])

    def result_validate(self, result: CanonicalSelectionResult) -> None:
        """Validate deterministic empty canonical-selection result.

        Args:
            result: Empty canonical-selection result.
        """

        CanonicalSelectionValidator(stage_input=self._stage_input).validate(result)
