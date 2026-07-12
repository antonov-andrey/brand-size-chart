"""Semantic and deterministic canonical-selection steps."""

from typing import ClassVar

from workflow_container_runtime.artifact import ArtifactMaterializer, JsonArtifactWriter
from workflow_container_runtime.codex import CodexRunner
from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.step import (
    WorkflowStepCodexBase,
    WorkflowStepCodexRuntimePolicy,
    WorkflowStepCodexState,
    WorkflowStepDeterministicBase,
    WorkflowStepExecutionContext,
)

from brand_size_chart.model import (
    BrandSourceTypeResultInputSource,
    BrandSourceTypeResultStepInput,
    CanonicalSelectionActionOutput,
    CanonicalSelectionResult,
    WorkflowStepCanonicalSelectConfig,
    canonical_selection_unresolved_size_group_gap_list_get,
)
from brand_size_chart.source.discovery_database import SourceDiscoveryDatabaseReader
from brand_size_chart.validator import CanonicalSelectionValidator


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

        return BrandSourceTypeResultStepInput.from_execution_context_input_source(execution_context, input_source)

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
        WorkflowStepCanonicalSelectConfig,
        CanonicalSelectionActionOutput,
        CanonicalSelectionResult,
    ]
):
    """Select canonical chart artifacts from eligible candidates."""

    action_output_model: ClassVar[type[CanonicalSelectionActionOutput]] = CanonicalSelectionActionOutput
    config_model: ClassVar[type[WorkflowStepCanonicalSelectConfig]] = WorkflowStepCanonicalSelectConfig
    result_model: ClassVar[type[CanonicalSelectionResult]] = CanonicalSelectionResult
    state_model: ClassVar[type[WorkflowStepCodexState]] = WorkflowStepCodexState
    step_key: ClassVar[str] = "canonical_select"

    def __init__(
        self,
        *,
        artifact_materializer: ArtifactMaterializer,
        artifact_writer: JsonArtifactWriter,
        codex_runner: CodexRunner,
        prompt_renderer: PromptRenderer,
        runtime_policy: WorkflowStepCodexRuntimePolicy,
        source_discovery_database_reader: SourceDiscoveryDatabaseReader,
        validator: CanonicalSelectionValidator,
    ) -> None:
        """Store reusable runtime and canonical-validation dependencies.

        Args:
            artifact_materializer: External artifact tree materializer.
            artifact_writer: Atomic standard-file writer.
            codex_runner: Low-level Codex runner.
            prompt_renderer: Strict project prompt renderer.
            runtime_policy: Source-owned materialization and retry policy.
            source_discovery_database_reader: Shared accepted-table query boundary.
            validator: Canonical-selection mechanical validator.
        """

        super().__init__(
            artifact_materializer=artifact_materializer,
            artifact_writer=artifact_writer,
            codex_runner=codex_runner,
            prompt_renderer=prompt_renderer,
            runtime_policy=runtime_policy,
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

        return BrandSourceTypeResultStepInput.from_execution_context_input_source(execution_context, input_source)

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
