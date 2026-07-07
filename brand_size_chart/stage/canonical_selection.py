"""Canonical-selection stage owner."""

from pathlib import Path

from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.stage import (
    VerifiedCodexStageConfig,
    VerifiedCodexStageRunner,
    verified_stage_artifact_write,
)

from brand_size_chart.model import (
    CanonicalSelectionCandidate,
    CanonicalSelectionPromptContext,
    CanonicalSelectionResult,
    PromptScope,
    TableExtractionArtifact,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY, table_extraction_applicability_status_get
from brand_size_chart.stage.base import CodexStageRun, stage_instruction_list_get
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

        prompt_context = self._prompt_context_get()
        if not prompt_context.canonical_selection_candidate_list:
            canonical_selection_result = CanonicalSelectionResult(canonical_selection_list=[])
            verified_stage_artifact_write(
                config=VerifiedCodexStageConfig(
                    prompt_context=prompt_context,
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
                prompt_context=prompt_context,
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
                stage_key="canonical_select",
            ),
            model_class=CanonicalSelectionResult,
            mechanical_validate=CanonicalSelectionValidator(prompt_context=prompt_context).validate,
        )
        return canonical_selection_result

    def _prompt_context_get(self) -> CanonicalSelectionPromptContext:
        """Return canonical-selection prompt context with verified candidate tables.

        Returns:
            Prompt context object.
        """

        return CanonicalSelectionPromptContext(
            brand_name=self._brand_name,
            canonical_selection_candidate_list=[
                CanonicalSelectionCandidate(
                    applicability_status=table_extraction_applicability_status_get(
                        table_extraction,
                        priority_country_code=self._prompt_scope.priority_country_code,
                    ),
                    source_priority=SOURCE_TYPE_REGISTRY.source_type_priority_get(table_extraction.source_type),
                    table_extraction_artifact=table_extraction,
                )
                for table_extraction in self._table_extraction_list
            ],
            shared_instruction=self._prompt_scope.shared_instruction,
            stage_instruction_list=stage_instruction_list_get(
                prompt_scope=self._prompt_scope,
                stage_key="canonical_select",
            ),
        )
