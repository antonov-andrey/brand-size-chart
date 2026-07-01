"""Workflow-run prompt application stage owner."""

from pathlib import Path

from brand_size_chart.artifact import ArtifactLayout, JsonArtifactWriter
from brand_size_chart.model import PromptScope, StageVerification
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.stage.base import CodexStageRun
from brand_size_chart.stage.semantic import SemanticStage
from brand_size_chart.validator import PromptScopeValidator


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
        self._artifact_writer = JsonArtifactWriter()
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

        prompt_scope = self._draft_result_get()
        if not self._workflow_run_prompt.strip():
            self._empty_prompt_artifact_write(prompt_scope)
            return prompt_scope

        prompt_scope = SemanticStage(
            codex_stage_run_callable=self._codex_stage_run,
            prompt_name="apply",
            prompt_scope=prompt_scope,
            result_dir=self._result_dir,
            stage_dir=self._stage_dir,
            stage_key="workflow_run_prompt_apply",
        ).run(
            draft_result=prompt_scope,
            model_class=PromptScope,
            prompt_context=self._prompt_context_get(prompt_scope),
            result_error_list_get=self._prompt_scope_validator.error_list_get,
        )
        self._prompt_scope_validator.validate(prompt_scope)
        return prompt_scope

    def _draft_result_get(self) -> PromptScope:
        """Return a minimal draft scope for the free workflow-run prompt.

        Returns:
            Draft prompt scope.
        """

        prompt_text = self._workflow_run_prompt.strip()
        return PromptScope(shared_instruction=prompt_text)

    def _empty_prompt_artifact_write(self, prompt_scope: PromptScope) -> None:
        """Write deterministic artifacts for an empty workflow prompt.

        Args:
            prompt_scope: Draft prompt scope.
        """

        self._prompt_scope_validator.validate(prompt_scope)
        result_path = self._artifact_layout.stage_result_path(self._stage_dir)
        self._artifact_writer.write(result_path, prompt_scope)
        self._artifact_writer.write(
            self._artifact_layout.stage_verification_path(self._stage_dir),
            StageVerification(
                artifact_path_list=[self._artifact_layout.artifact_path(result_path)],
                message="Empty workflow prompt requires no rewrite.",
                stage_key="workflow_run_prompt_apply",
                status="success",
            ),
        )

    def _prompt_context_get(self, prompt_scope: PromptScope) -> str:
        """Return prompt context for workflow-run prompt application.

        Args:
            prompt_scope: Draft prompt scope.

        Returns:
            Prompt context text.
        """

        allowed_source_type_text = "\n".join(
            f"- {source_type}" for source_type in sorted(SOURCE_TYPE_REGISTRY.source_type_priority_by_key_map)
        )
        return (
            "Allowed source_type keys are:\n"
            f"{allowed_source_type_text}\n\n"
            "If the workflow prompt asks for all supported source types, leave source_type_allow_list empty. "
            "Use source_type_allow_list only when the prompt names exact allowed source_type keys from the list above.\n\n"
            "Extract priority_country_code from the workflow prompt when the user names a priority country or market. "
            "Normalize it to one ISO 3166 alpha-2 uppercase country code. Use TR when the workflow prompt does not "
            "select another priority country.\n\n"
            f"Workflow run prompt:\n{self._workflow_run_prompt}\n\n"
            f"Draft prompt scope JSON:\n{prompt_scope.model_dump_json(indent=2)}\n"
        )
