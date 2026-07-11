"""Workflow-run prompt parsing step."""

from typing import ClassVar

from workflow_container_runtime.artifact import ArtifactMaterializer, JsonArtifactWriter
from workflow_container_runtime.codex import CodexRunner
from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.step import (
    WorkflowStepCodexBase,
    WorkflowStepCodexConfig,
    WorkflowStepCodexState,
    WorkflowStepDeterministicBase,
    WorkflowStepExecutionContext,
)

from brand_size_chart.model import PromptScope, RunInput, SourceTypeCatalogItem, WorkflowRunPromptApplyInput
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.validator import PromptScopeValidator


class WorkflowRunPromptApplyDefaultStep(
    WorkflowStepDeterministicBase[
        RunInput,
        WorkflowRunPromptApplyInput,
        PromptScope,
    ]
):
    """Publish an empty prompt scope when the workflow prompt is empty."""

    result_model: ClassVar[type[PromptScope]] = PromptScope

    def input_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: RunInput,
    ) -> WorkflowRunPromptApplyInput:
        """Build the persisted empty-prompt input.

        Args:
            execution_context: Current step context.
            input_source: Root workflow input.

        Returns:
            Persisted prompt-application input.
        """

        _ = execution_context
        return _workflow_run_prompt_apply_input_get(input_source)

    def result_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: WorkflowRunPromptApplyInput,
    ) -> PromptScope:
        """Build the deterministic empty prompt scope.

        Args:
            execution_context: Current step context.
            step_input: Persisted empty-prompt input.

        Returns:
            Empty prompt scope.
        """

        _ = execution_context
        _ = step_input
        return PromptScope()


def _workflow_run_prompt_apply_input_get(input_source: RunInput) -> WorkflowRunPromptApplyInput:
    """Build one persisted prompt-application input.

    Args:
        input_source: Root workflow input.

    Returns:
        Persisted prompt-application input.
    """

    return WorkflowRunPromptApplyInput(
        source_type_catalog_list=[
            SourceTypeCatalogItem(
                requires_product_type=SOURCE_TYPE_REGISTRY.source_type_requires_product_type(source_type),
                source_type=source_type,
            )
            for source_type in sorted(
                SOURCE_TYPE_REGISTRY.source_type_priority_by_key_map,
                key=SOURCE_TYPE_REGISTRY.source_type_priority_get,
                reverse=True,
            )
        ],
        workflow_input=input_source,
    )


class WorkflowRunPromptApplyStep(
    WorkflowStepCodexBase[
        RunInput,
        WorkflowRunPromptApplyInput,
        PromptScope,
        PromptScope,
    ]
):
    """Parse one free workflow prompt into a verified prompt scope."""

    action_output_model: ClassVar[type[PromptScope]] = PromptScope
    result_model: ClassVar[type[PromptScope]] = PromptScope
    state_model: ClassVar[type[WorkflowStepCodexState]] = WorkflowStepCodexState
    step_key: ClassVar[str] = "workflow_run_prompt_apply"

    def __init__(
        self,
        *,
        artifact_materializer: ArtifactMaterializer,
        artifact_writer: JsonArtifactWriter,
        codex_runner: CodexRunner,
        config: WorkflowStepCodexConfig,
        prompt_renderer: PromptRenderer,
        validator: PromptScopeValidator,
    ) -> None:
        """Store reusable runtime and prompt-scope validation dependencies.

        Args:
            artifact_materializer: External artifact tree materializer.
            artifact_writer: Atomic standard-file writer.
            codex_runner: Low-level Codex runner.
            config: Explicit Codex step config.
            prompt_renderer: Strict project prompt renderer.
            validator: Prompt-scope mechanical validator.
        """

        super().__init__(
            artifact_materializer=artifact_materializer,
            artifact_writer=artifact_writer,
            codex_runner=codex_runner,
            config=config,
            prompt_renderer=prompt_renderer,
        )
        self._validator = validator

    def input_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: RunInput,
    ) -> WorkflowRunPromptApplyInput:
        """Build persisted prompt-application input from the root workflow input.

        Args:
            execution_context: Current step context.
            input_source: Root workflow input.

        Returns:
            Persisted prompt-application input.
        """

        _ = execution_context
        return _workflow_run_prompt_apply_input_get(input_source)

    def result_from_action_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: WorkflowRunPromptApplyInput,
        action_output: PromptScope,
    ) -> PromptScope:
        """Return the exact structured prompt-scope output.

        Args:
            execution_context: Current step context.
            step_input: Persisted prompt-application input.
            action_output: Structured Codex prompt scope.

        Returns:
            Public prompt scope.
        """

        _ = execution_context
        _ = step_input
        return action_output

    def result_validate(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: WorkflowRunPromptApplyInput,
        result: PromptScope,
    ) -> None:
        """Validate prompt scope against the exact source catalog and step keys.

        Args:
            execution_context: Current step context.
            step_input: Persisted prompt-application input.
            result: Candidate prompt scope.
        """

        self._validator.validate(
            execution_context=execution_context,
            result=result,
            step_input=step_input,
        )
