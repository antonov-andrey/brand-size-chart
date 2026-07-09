"""Workflow-run prompt application stage owner."""

from pathlib import Path

from workflow_container_runtime.stage import WorkflowStepBase

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import PromptScope, SourceTypeCatalogItem, WorkflowRunPromptApplyInput
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.stage.base import BrandSizeChartCodexStepBase, CodexStageRun
from brand_size_chart.validator import PromptScopeValidator


class WorkflowRunPromptApplyStep(BrandSizeChartCodexStepBase[WorkflowRunPromptApplyInput, PromptScope, PromptScope]):
    """Parse and verify the free workflow-run prompt into prompt scope."""

    stage_key = "workflow_run_prompt_apply"

    def __init__(self, *, codex_stage_run_callable: CodexStageRun, result_dir: Path, workflow_run_prompt: str) -> None:
        """Store workflow-run prompt dependencies.

        Args:
            codex_stage_run_callable: Codex stage execution boundary.
            result_dir: Root result directory.
            workflow_run_prompt: User-supplied prompt text.
        """

        self._artifact_layout = ArtifactLayout(result_dir)
        self._prompt_scope_validator = PromptScopeValidator()
        self._workflow_run_prompt = workflow_run_prompt
        super().__init__(
            codex_stage_run_callable=codex_stage_run_callable,
            result_dir=result_dir,
            stage_dir=self._artifact_layout.workflow_run_prompt_apply_dir(),
        )

    def action_output_model_get(self) -> type[PromptScope]:
        """Return the workflow-run prompt action output model.

        Returns:
            Prompt scope model.
        """

        return PromptScope

    def run(self) -> PromptScope:
        """Return parsed prompt scope and write stage artifacts.

        Returns:
            Parsed prompt scope.
        """

        prompt_scope = self._prompt_scope_seed_get()
        if not self._workflow_run_prompt.strip():
            return _WorkflowRunPromptApplyEmptyStep(
                prompt_scope_validator=self._prompt_scope_validator,
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
                stage_input=self._stage_input_get(),
            ).run()
        return super().run()

    def input_build(self) -> WorkflowRunPromptApplyInput:
        """Return workflow-run prompt application input.

        Returns:
            Stage input object.
        """

        return self._stage_input_get()

    def _prompt_scope_seed_get(self) -> PromptScope:
        """Return a minimal scope seed for the free workflow-run prompt.

        Returns:
            Prompt scope seed.
        """

        prompt_text = self._workflow_run_prompt.strip()
        return PromptScope(shared_instruction=prompt_text)

    def result_build(self, stage_input: WorkflowRunPromptApplyInput, action_output: PromptScope) -> PromptScope:
        """Return public prompt scope from the action output.

        Args:
            stage_input: Workflow-run prompt application input.
            action_output: Codex-owned prompt scope.

        Returns:
            Public prompt scope.
        """

        _ = stage_input
        return action_output

    def result_validate(self, result: PromptScope) -> None:
        """Validate public prompt scope.

        Args:
            result: Public prompt scope.
        """

        self._prompt_scope_validator.validate(result)

    def _stage_input_get(self) -> WorkflowRunPromptApplyInput:
        """Return stage input for workflow-run prompt application.

        Returns:
            Stage input object.
        """

        return WorkflowRunPromptApplyInput(
            source_type_catalog_list=[
                SourceTypeCatalogItem(
                    discovery_instruction=SOURCE_TYPE_REGISTRY.source_type_discovery_instruction_get(source_type),
                    requires_product_type=SOURCE_TYPE_REGISTRY.source_type_requires_product_type(source_type),
                    source_type=source_type,
                )
                for source_type in sorted(
                    SOURCE_TYPE_REGISTRY.source_type_priority_by_key_map,
                    key=SOURCE_TYPE_REGISTRY.source_type_priority_get,
                    reverse=True,
                )
            ],
            workflow_run_prompt=self._workflow_run_prompt,
        )


class _WorkflowRunPromptApplyEmptyStep(WorkflowStepBase[WorkflowRunPromptApplyInput, PromptScope]):
    """Deterministic prompt-apply step for an empty workflow-run prompt."""

    def __init__(
        self,
        *,
        prompt_scope_validator: PromptScopeValidator,
        result_dir: Path,
        stage_dir: Path,
        stage_input: WorkflowRunPromptApplyInput,
    ) -> None:
        """Store deterministic empty-prompt dependencies.

        Args:
            prompt_scope_validator: Prompt scope validator.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
            stage_input: Workflow-run prompt input.
        """

        super().__init__(result_dir=result_dir, stage_dir=stage_dir)
        self._prompt_scope_validator = prompt_scope_validator
        self._stage_input = stage_input

    def input_build(self) -> WorkflowRunPromptApplyInput:
        """Return deterministic empty-prompt input.

        Returns:
            Workflow-run prompt input.
        """

        return self._stage_input

    def result_build(self, stage_input: WorkflowRunPromptApplyInput) -> PromptScope:
        """Return deterministic empty-prompt scope.

        Args:
            stage_input: Workflow-run prompt input.

        Returns:
            Empty prompt scope result.
        """

        return PromptScope(shared_instruction=stage_input.workflow_run_prompt.strip())

    def result_validate(self, result: PromptScope) -> None:
        """Validate deterministic empty-prompt scope.

        Args:
            result: Empty prompt scope result.
        """

        self._prompt_scope_validator.validate(result)
