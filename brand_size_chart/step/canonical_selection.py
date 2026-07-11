"""Semantic and deterministic canonical-selection steps."""

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

from brand_size_chart.model import (
    BrandSourceTypeResultInputSource,
    CanonicalSelectionActionOutput,
    BrandSourceTypeResultStepInput,
    CanonicalSelectionResult,
    canonical_selection_unresolved_size_group_gap_list_get,
)
from brand_size_chart.source.discovery_database import SourceDiscoveryDatabaseReader
from brand_size_chart.step.instruction import step_instruction_list_get
from brand_size_chart.validator import CanonicalSelectionValidator


def _canonical_selection_input_get(
    input_source: BrandSourceTypeResultInputSource,
) -> BrandSourceTypeResultStepInput:
    """Build persisted canonical candidates from complete source-type results.

    Args:
        input_source: Brand workflow input and source-type results.

    Returns:
        Persisted canonical-selection input.
    """

    prompt_scope = input_source.workflow_input.prompt_scope
    return BrandSourceTypeResultStepInput(
        source_type_result_list=input_source.source_type_result_list,
        step_instruction_list=step_instruction_list_get(
            prompt_scope=prompt_scope,
            step_key="canonical_select",
        ),
        workflow_input=input_source.workflow_input,
    )


class CanonicalSelectionDefaultStep(
    WorkflowStepDeterministicBase[
        BrandSourceTypeResultInputSource,
        BrandSourceTypeResultStepInput,
        CanonicalSelectionResult,
    ]
):
    """Publish an empty canonical selection when no candidate participates."""

    result_model: ClassVar[type[CanonicalSelectionResult]] = CanonicalSelectionResult

    def __init__(self, *, artifact_writer: JsonArtifactWriter, validator: CanonicalSelectionValidator) -> None:
        """Store standard publication and selection validation dependencies.

        Args:
            artifact_writer: Atomic standard-file writer.
            validator: Canonical-selection mechanical validator.
        """

        super().__init__(artifact_writer=artifact_writer)
        self._validator = validator

    def input_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: BrandSourceTypeResultInputSource,
    ) -> BrandSourceTypeResultStepInput:
        """Build persisted canonical-selection input.

        Args:
            execution_context: Current step context.
            input_source: Brand workflow input and source-type results.

        Returns:
            Persisted canonical-selection input.
        """

        _ = execution_context
        return _canonical_selection_input_get(input_source)

    def result_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandSourceTypeResultStepInput,
    ) -> CanonicalSelectionResult:
        """Build an empty canonical-selection result.

        Args:
            execution_context: Current step context.
            step_input: Persisted candidate input.

        Returns:
            Empty canonical-selection result.
        """

        _ = execution_context
        _ = step_input
        return CanonicalSelectionResult(
            canonical_selection_list=[],
            unresolved_size_group_gap_list=[],
        )

    def result_validate(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandSourceTypeResultStepInput,
        result: CanonicalSelectionResult,
    ) -> None:
        """Validate deterministic empty selection.

        Args:
            execution_context: Current step context.
            step_input: Persisted candidate input.
            result: Candidate canonical-selection result.
        """

        self._validator.validate(
            execution_context=execution_context,
            result=result,
            step_input=step_input,
        )


class CanonicalSelectionStep(
    WorkflowStepCodexBase[
        BrandSourceTypeResultInputSource,
        BrandSourceTypeResultStepInput,
        CanonicalSelectionActionOutput,
        CanonicalSelectionResult,
    ]
):
    """Select canonical chart artifacts from eligible candidates."""

    action_output_model: ClassVar[type[CanonicalSelectionActionOutput]] = CanonicalSelectionActionOutput
    result_model: ClassVar[type[CanonicalSelectionResult]] = CanonicalSelectionResult
    state_model: ClassVar[type[WorkflowStepCodexState]] = WorkflowStepCodexState
    step_key: ClassVar[str] = "canonical_select"

    def __init__(
        self,
        *,
        artifact_materializer: ArtifactMaterializer,
        artifact_writer: JsonArtifactWriter,
        codex_runner: CodexRunner,
        config: WorkflowStepCodexConfig,
        prompt_renderer: PromptRenderer,
        source_discovery_database_reader: SourceDiscoveryDatabaseReader,
        validator: CanonicalSelectionValidator,
    ) -> None:
        """Store reusable runtime and canonical-validation dependencies.

        Args:
            artifact_materializer: External artifact tree materializer.
            artifact_writer: Atomic standard-file writer.
            codex_runner: Low-level Codex runner.
            config: Explicit Codex step config.
            prompt_renderer: Strict project prompt renderer.
            source_discovery_database_reader: Shared accepted-table query boundary.
            validator: Canonical-selection mechanical validator.
        """

        super().__init__(
            artifact_materializer=artifact_materializer,
            artifact_writer=artifact_writer,
            codex_runner=codex_runner,
            config=config,
            prompt_renderer=prompt_renderer,
        )
        self._source_discovery_database_reader = source_discovery_database_reader
        self._validator = validator

    def input_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: BrandSourceTypeResultInputSource,
    ) -> BrandSourceTypeResultStepInput:
        """Build persisted canonical-selection input.

        Args:
            execution_context: Current step context.
            input_source: Brand workflow input and source-type results.

        Returns:
            Persisted canonical-selection input.
        """

        _ = execution_context
        return _canonical_selection_input_get(input_source)

    def have_candidate(self, input_source: BrandSourceTypeResultInputSource) -> bool:
        """Return whether semantic canonical selection has any candidate.

        Args:
            input_source: Brand workflow input and source-type results.

        Returns:
            Whether at least one candidate participates in canonical selection.
        """

        return any(
            source_type_result.source_discovery_result is not None
            and source_type_result.source_discovery_result.outcome == "table_available"
            for source_type_result in input_source.source_type_result_list
        )

    def result_from_action_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandSourceTypeResultStepInput,
        action_output: CanonicalSelectionActionOutput,
    ) -> CanonicalSelectionResult:
        """Return the exact structured canonical-selection output.

        Args:
            execution_context: Current step context.
            step_input: Persisted canonical-selection input.
            action_output: Structured Codex selection output.

        Returns:
            Public canonical-selection result.
        """

        accepted_table_list = (
            self._source_discovery_database_reader.accepted_table_list_get_for_source_type_result_list(
                result_dir=execution_context.result_dir,
                source_type_result_list=step_input.source_type_result_list,
            )
        )
        return CanonicalSelectionResult(
            canonical_selection_list=action_output.canonical_selection_list,
            unresolved_size_group_gap_list=canonical_selection_unresolved_size_group_gap_list_get(
                canonical_selection_list=action_output.canonical_selection_list,
                accepted_table_list=accepted_table_list,
            ),
        )

    def result_validate(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandSourceTypeResultStepInput,
        result: CanonicalSelectionResult,
    ) -> None:
        """Validate canonical selection mechanically.

        Args:
            execution_context: Current step context.
            step_input: Persisted candidate input.
            result: Candidate canonical-selection result.
        """

        self._validator.validate(
            execution_context=execution_context,
            result=result,
            step_input=step_input,
        )
