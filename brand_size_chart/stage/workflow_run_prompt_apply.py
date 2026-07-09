"""Workflow-run prompt application stage owner."""

from pathlib import Path

from workflow_container_runtime.prompt import PromptRenderer

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import PromptScope, SourceTypeCatalogItem, WorkflowRunPromptApplyInput
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.stage.base import (
    CodexStageRun,
    VerifiedCodexStageConfig,
    VerifiedCodexStageRunner,
    verified_stage_artifact_write,
)
from brand_size_chart.validator import PromptScopeValidator

PROJECT_TEMPLATE_DIR = Path(__file__).parents[1] / "prompt" / "template"


class WorkflowRunPromptApplyStage:
    """Parse and verify the free workflow-run prompt into prompt scope."""

    def __init__(self, *, codex_stage_run_callable: CodexStageRun, result_dir: Path, workflow_run_prompt: str) -> None:
        """Store workflow-run prompt dependencies.

        Args:
            codex_stage_run_callable: Codex stage execution boundary.
            result_dir: Root result directory.
            workflow_run_prompt: User-supplied prompt text.
        """

        self._artifact_layout = ArtifactLayout(result_dir)
        self._codex_stage_run = codex_stage_run_callable
        self._prompt_scope_validator = PromptScopeValidator()
        self._result_dir = result_dir
        self._stage_dir = self._artifact_layout.workflow_run_prompt_apply_dir()
        self._workflow_run_prompt = workflow_run_prompt

    def run(self) -> PromptScope:
        """Return parsed prompt scope and write stage artifacts.

        Returns:
            Parsed prompt scope.
        """

        prompt_scope = self._prompt_scope_seed_get()
        if not self._workflow_run_prompt.strip():
            self._empty_prompt_artifact_write(prompt_scope)
            return prompt_scope

        prompt_scope = VerifiedCodexStageRunner(
            codex_stage_run_callable=self._codex_stage_run,
            prompt_renderer=PromptRenderer(template_dir=PROJECT_TEMPLATE_DIR),
        ).run(
            config=VerifiedCodexStageConfig(
                prompt_context=self._stage_input_get(),
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
                stage_key="workflow_run_prompt_apply",
            ),
            model_class=PromptScope,
            mechanical_validate=self._prompt_scope_validator.validate,
        )
        return prompt_scope

    def _prompt_scope_seed_get(self) -> PromptScope:
        """Return a minimal scope seed for the free workflow-run prompt.

        Returns:
            Prompt scope seed.
        """

        prompt_text = self._workflow_run_prompt.strip()
        return PromptScope(shared_instruction=prompt_text)

    def _empty_prompt_artifact_write(self, prompt_scope: PromptScope) -> None:
        """Write deterministic artifacts for an empty workflow prompt.

        Args:
            prompt_scope: Prompt scope seed.
        """

        self._prompt_scope_validator.validate(prompt_scope)
        verified_stage_artifact_write(
            config=VerifiedCodexStageConfig(
                prompt_context=self._stage_input_get(),
                result_dir=self._result_dir,
                stage_dir=self._stage_dir,
                stage_key="workflow_run_prompt_apply",
            ),
            result=prompt_scope,
        )

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
