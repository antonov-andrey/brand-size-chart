"""Canonical-selection stage owner."""

from pathlib import Path

from workflow_container_runtime.prompt import PromptRenderer

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
from brand_size_chart.stage.base import (
    CodexStageRun,
    VerifiedCodexStageConfig,
    VerifiedCodexStageRunner,
    stage_instruction_list_get,
    verified_stage_artifact_write,
)
from brand_size_chart.validator import CanonicalSelectionValidator

PROJECT_TEMPLATE_DIR = Path(__file__).parents[1] / "prompt" / "template"


class CanonicalSelectionStage:
    """Select canonical tables from verified table extractions."""

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
        """Store canonical-selection stage dependencies.

        Args:
            brand_name: Parsed brand display name.
            codex_stage_run_callable: Codex stage execution boundary.
            prompt_scope: Parsed prompt scope.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            table_extraction_list: Verified table extractions.
        """

        self._brand_name = brand_name
        self._codex_stage_run = codex_stage_run_callable
        self._prompt_scope = prompt_scope
        self._result_dir = result_dir
        self._stage_dir = stage_dir
        self._table_extraction_list = table_extraction_list

    def run(self) -> CanonicalSelectionResult:
        """Return semantically verified canonical selection.

        Returns:
            Verified canonical selection result.
        """

        stage_input = self._stage_input_get()
        if not stage_input.canonical_selection_candidate_list:
            canonical_selection_result = CanonicalSelectionResult(canonical_selection_list=[])
            verified_stage_artifact_write(
                config=VerifiedCodexStageConfig(
                    prompt_context=stage_input,
                    result_dir=self._result_dir,
                    stage_dir=self._stage_dir,
                    stage_key="canonical_select",
                ),
                result=canonical_selection_result,
            )
            return canonical_selection_result
        canonical_selection_result = VerifiedCodexStageRunner(
            codex_stage_run_callable=self._codex_stage_run,
            prompt_renderer=PromptRenderer(template_dir=PROJECT_TEMPLATE_DIR),
        ).run(
            config=VerifiedCodexStageConfig(
                prompt_context=stage_input,
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
                stage_key="canonical_select",
            ),
            model_class=CanonicalSelectionResult,
            mechanical_validate=CanonicalSelectionValidator(stage_input=stage_input).validate,
        )
        return canonical_selection_result

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
                stage_key="canonical_select",
            ),
        )
