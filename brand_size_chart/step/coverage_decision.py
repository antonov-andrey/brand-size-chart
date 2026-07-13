"""Semantic and deterministic product-type coverage steps."""

from typing import ClassVar

from workflow_container_runtime.artifact import ArtifactMaterializer, JsonArtifactWriter
from workflow_container_runtime.codex import CodexRunner
from workflow_container_runtime.mcp_playwright_profile import McpPlaywrightProfileRuntime
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
    CoverageDecisionProductTypeGap,
    CoverageDecisionResult,
    WorkflowBrandSizeChartInput,
    WorkflowStepCoverageDecideConfig,
)
from brand_size_chart.validator import CoverageDecisionValidator


class CoverageDecisionDefaultStep(
    WorkflowStepDeterministicBase[
        BrandSourceTypeResultInputSource,
        BrandSourceTypeResultStepInput,
        CoverageDecisionResult,
    ]
):
    """Build deterministic coverage when semantic table comparison is unnecessary."""

    result_model: ClassVar[type[CoverageDecisionResult]] = CoverageDecisionResult

    def __init__(self, *, artifact_writer: JsonArtifactWriter, validator: CoverageDecisionValidator) -> None:
        """Store standard publication and coverage validation dependencies.

        Args:
            artifact_writer: Atomic standard-file writer.
            validator: Coverage mechanical validator.
        """

        super().__init__(artifact_writer=artifact_writer)
        self._validator = validator

    def input_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: BrandSourceTypeResultInputSource,
    ) -> BrandSourceTypeResultStepInput:
        """Build persisted coverage input.

        Args:
            execution_context: Current step context.
            input_source: Brand workflow input and source-type results.

        Returns:
            Persisted coverage input.
        """

        return BrandSourceTypeResultStepInput.from_execution_context_input_source(execution_context, input_source)

    def result_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandSourceTypeResultStepInput,
    ) -> CoverageDecisionResult:
        """Build explicit gaps for every requested type without verified tables.

        Args:
            execution_context: Current step context.
            step_input: Persisted coverage input.

        Returns:
            Deterministic coverage result.
        """

        _ = execution_context
        return CoverageDecisionResult(
            covered_product_type_list=[],
            uncovered_product_type_gap_list=[
                CoverageDecisionProductTypeGap(
                    product_type=product_type,
                    reason="No accepted source table is available for this requested product type.",
                )
                for product_type in WorkflowBrandSizeChartInput.model_validate_json(
                    (execution_context.result_dir / step_input.workflow_input_path).read_text(encoding="utf-8")
                ).request.product_type_request_list
            ],
        )

    def result_validate(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandSourceTypeResultStepInput,
        result: CoverageDecisionResult,
    ) -> None:
        """Validate deterministic coverage partitioning.

        Args:
            execution_context: Current step context.
            step_input: Persisted coverage input.
            result: Candidate coverage result.
        """

        self._validator.validate(
            execution_context=execution_context,
            result=result,
            step_input=step_input,
        )


class CoverageDecisionStep(
    WorkflowStepCodexBase[
        BrandSourceTypeResultInputSource,
        BrandSourceTypeResultStepInput,
        WorkflowStepCoverageDecideConfig,
        CoverageDecisionResult,
        CoverageDecisionResult,
    ]
):
    """Decide product-type coverage from verified chart artifacts."""

    action_output_model: ClassVar[type[CoverageDecisionResult]] = CoverageDecisionResult
    config_model: ClassVar[type[WorkflowStepCoverageDecideConfig]] = WorkflowStepCoverageDecideConfig
    result_model: ClassVar[type[CoverageDecisionResult]] = CoverageDecisionResult
    state_model: ClassVar[type[WorkflowStepCodexState]] = WorkflowStepCodexState
    step_key: ClassVar[str] = "coverage_decide"

    def __init__(
        self,
        *,
        artifact_materializer: ArtifactMaterializer,
        artifact_writer: JsonArtifactWriter,
        codex_runner: CodexRunner,
        mcp_playwright_profile_runtime: McpPlaywrightProfileRuntime,
        prompt_renderer: PromptRenderer,
        runtime_policy: WorkflowStepCodexRuntimePolicy,
        validator: CoverageDecisionValidator,
    ) -> None:
        """Store reusable runtime and coverage-validation dependencies.

        Args:
            artifact_materializer: External artifact tree materializer.
            artifact_writer: Atomic standard-file writer.
            codex_runner: Low-level Codex runner.
            mcp_playwright_profile_runtime: Run-local browser profile lifecycle owner.
            prompt_renderer: Strict project prompt renderer.
            runtime_policy: Source-owned materialization and retry policy.
            validator: Coverage mechanical validator.
        """

        super().__init__(
            artifact_materializer=artifact_materializer,
            artifact_writer=artifact_writer,
            codex_runner=codex_runner,
            mcp_playwright_profile_runtime=mcp_playwright_profile_runtime,
            prompt_renderer=prompt_renderer,
            runtime_policy=runtime_policy,
        )
        self._validator = validator

    def input_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: BrandSourceTypeResultInputSource,
    ) -> BrandSourceTypeResultStepInput:
        """Build persisted coverage input.

        Args:
            execution_context: Current step context.
            input_source: Brand workflow input and source-type results.

        Returns:
            Persisted coverage input.
        """

        return BrandSourceTypeResultStepInput.from_execution_context_input_source(execution_context, input_source)

    def result_from_action_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandSourceTypeResultStepInput,
        action_output: CoverageDecisionResult,
    ) -> CoverageDecisionResult:
        """Return the exact structured coverage action output.

        Args:
            execution_context: Current step context.
            step_input: Persisted coverage input.
            action_output: Structured Codex coverage output.

        Returns:
            Public coverage result.
        """

        _ = execution_context
        _ = step_input
        return action_output

    def result_validate(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandSourceTypeResultStepInput,
        result: CoverageDecisionResult,
    ) -> None:
        """Validate semantic coverage output mechanically.

        Args:
            execution_context: Current step context.
            step_input: Persisted coverage input.
            result: Candidate coverage result.
        """

        self._validator.validate(
            execution_context=execution_context,
            result=result,
            step_input=step_input,
        )
