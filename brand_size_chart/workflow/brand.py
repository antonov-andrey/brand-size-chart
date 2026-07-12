"""Brand-level DBOS workflow owner."""

from dbos import DBOS, DBOSConfiguredInstance, pydantic_args_validator
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.step import (
    StepResultValidationError,
    WorkflowStepExecutionContext,
    WorkflowStepInvocation,
)
from workflow_container_runtime.workflow import (
    WorkflowBase,
    WorkflowExecutionContext,
    WorkflowResultValidationError,
    WorkflowRuntimeCapability,
)

from brand_size_chart.model import (
    BrandInput,
    BrandOutputInputSource,
    BrandOutputResult,
    BrandResult,
    BrandSourceTypeResultInputSource,
    CanonicalSelectionResult,
    CoverageDecisionResult,
    SourceDiscoveryInputSource,
    SourceTypeResult,
    WorkflowBrandSizeChartInput,
    WorkflowBrandSizeChartRequest,
    WorkflowStepCanonicalSelectConfig,
    WorkflowStepCoverageDecideConfig,
    WorkflowStepSourceDiscoverConfig,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.step import (
    BrandOutputStep,
    CanonicalSelectionDefaultStep,
    CanonicalSelectionStep,
    CoverageDecisionDefaultStep,
    CoverageDecisionStep,
    SourceDiscoveryStep,
)


@DBOS.dbos_class("BrandSizeChartBrandWorkflow")
class BrandSizeChartBrandWorkflow(
    WorkflowBase[WorkflowBrandSizeChartInput, BrandResult],
    DBOSConfiguredInstance,
):
    """Run independent source discovery and brand-owned decision steps."""

    def __init__(
        self,
        *,
        artifact_writer: JsonArtifactWriter,
        brand_output_step: BrandOutputStep,
        canonical_selection_default_step: CanonicalSelectionDefaultStep,
        canonical_selection_step: CanonicalSelectionStep,
        config_name: str,
        coverage_decision_default_step: CoverageDecisionDefaultStep,
        coverage_decision_step: CoverageDecisionStep,
        source_discovery_step: SourceDiscoveryStep,
    ) -> None:
        """Store reusable workflow and step dependencies.

        Args:
            artifact_writer: Atomic standard-file writer.
            brand_output_step: Deterministic final chart publication step.
            canonical_selection_default_step: Deterministic empty-selection step.
            canonical_selection_step: Semantic canonical-selection step.
            config_name: Stable DBOS configured-instance name.
            coverage_decision_default_step: Deterministic coverage step.
            coverage_decision_step: Semantic coverage step.
            source_discovery_step: Concurrent browser-backed discovery step.
        """

        WorkflowBase.__init__(self, artifact_writer=artifact_writer)
        DBOSConfiguredInstance.__init__(self, config_name=config_name)
        self._brand_output_step = brand_output_step
        self._canonical_selection_default_step = canonical_selection_default_step
        self._canonical_selection_step = canonical_selection_step
        self._coverage_decision_default_step = coverage_decision_default_step
        self._coverage_decision_step = coverage_decision_step
        self._source_discovery_step = source_discovery_step

    @DBOS.workflow(name="brand_size_chart_brand", validate_args=pydantic_args_validator)
    async def run(
        self,
        execution_context: WorkflowExecutionContext,
        workflow_input: WorkflowBrandSizeChartInput,
        brand_input: BrandInput,
    ) -> BrandResult:
        """Run one brand workflow and preserve source discovery in registry order.

        Args:
            execution_context: Current brand workflow context.
            workflow_input: Complete public workflow input.
            brand_input: One parsed brand selected by the root workflow.

        Returns:
            Complete brand result tree.
        """

        self.input_write_step(execution_context, workflow_input)
        source_type_list = self.source_type_list_get(workflow_input.request)
        invocation_list = [
            WorkflowStepInvocation(
                execution_context=execution_context.for_step(
                    runtime_capability=execution_context.runtime_capability,
                    step_instance_key=f"source_discover_{source_type}",
                ),
                input_source=SourceDiscoveryInputSource(
                    brand_input=brand_input,
                    source_type=source_type,
                ),
            )
            for source_type in source_type_list
        ]
        outcome_list = await self._source_discovery_step.run_outcome_list(
            invocation_list,
            workflow_input.config.step_map.source_discover,
        )
        source_type_result_list = [
            SourceTypeResult(
                error_list=(
                    [f"{StepResultValidationError.__name__}: {'; '.join(outcome.validation_feedback_list)}"]
                    if outcome.validation_feedback_list
                    else ["Source discovery market conflict."] if outcome.result.outcome == "market_conflict" else []
                ),
                source_discovery_result=outcome.result,
                source_type=invocation.input_source.source_type,
                status=(
                    "failed"
                    if outcome.validation_feedback_list or outcome.result.outcome == "market_conflict"
                    else "success"
                ),
                warning_list=[],
            )
            for invocation, outcome in zip(invocation_list, outcome_list, strict=True)
        ]
        decision_input_source = BrandSourceTypeResultInputSource(source_type_result_list=source_type_result_list)
        error_list: list[str] = []
        coverage_decision_result: CoverageDecisionResult | None = None
        canonical_selection_result: CanonicalSelectionResult | None = None
        brand_output_result: BrandOutputResult | None = None
        try:
            coverage_decision_result = self.coverage_decide_write_step(
                execution_context.for_step(
                    runtime_capability=WorkflowRuntimeCapability(browser=None),
                    step_instance_key="coverage_decide",
                ),
                decision_input_source,
                workflow_input.config.step_map.coverage_decide,
            )
            canonical_selection_result = self.canonical_select_write_step(
                execution_context.for_step(
                    runtime_capability=WorkflowRuntimeCapability(browser=None),
                    step_instance_key="canonical_select",
                ),
                decision_input_source,
                workflow_input.config.step_map.canonical_select,
            )
            brand_output_result = self.brand_output_write_step(
                execution_context.for_step(
                    runtime_capability=WorkflowRuntimeCapability(browser=None),
                    step_instance_key="brand_output",
                ),
                BrandOutputInputSource(
                    brand_input=brand_input,
                    canonical_selection_result=canonical_selection_result,
                    source_type_result_list=source_type_result_list,
                ),
            )
        except StepResultValidationError as exc:
            error_list.append(f"{type(exc).__name__}: {exc}")

        workflow_result = BrandResult(
            brand_input=brand_input,
            brand_output_result=brand_output_result,
            canonical_selection_result=canonical_selection_result,
            coverage_decision_result=coverage_decision_result,
            error_list=error_list,
            source_type_result_list=source_type_result_list,
            source_type_skip_list=[],
            status="failed" if error_list else "success",
            warning_list=[],
        )
        return self.result_write_step(execution_context, workflow_input, workflow_result)

    @DBOS.step(name="brand_output_write_step")
    def brand_output_write_step(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: BrandOutputInputSource,
    ) -> BrandOutputResult:
        """Publish selected chart artifacts inside one durable DBOS step.

        Args:
            execution_context: Current final-output step context.
            input_source: Verified decisions, brand identity, and source results.

        Returns:
            Final brand output result.
        """

        return self._brand_output_step.run(execution_context, input_source)

    @DBOS.step(name="canonical_select_write_step")
    def canonical_select_write_step(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: BrandSourceTypeResultInputSource,
        workflow_step_config: WorkflowStepCanonicalSelectConfig,
    ) -> CanonicalSelectionResult:
        """Run semantic or deterministic canonical selection.

        Args:
            execution_context: Current canonical-selection step context.
            input_source: Complete source-type results.
            workflow_step_config: Exact selected canonical-selection config.

        Returns:
            Verified canonical-selection result.
        """

        if self._canonical_selection_step.have_candidate(input_source):
            return self._canonical_selection_step.run(execution_context, input_source, workflow_step_config)
        return self._canonical_selection_default_step.run(execution_context, input_source)

    @DBOS.step(name="coverage_decide_write_step")
    def coverage_decide_write_step(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: BrandSourceTypeResultInputSource,
        workflow_step_config: WorkflowStepCoverageDecideConfig,
    ) -> CoverageDecisionResult:
        """Run semantic or deterministic requested-product coverage.

        Args:
            execution_context: Current coverage-decision step context.
            input_source: Complete source-type results.
            workflow_step_config: Exact selected coverage-decision config.

        Returns:
            Verified coverage decision.
        """

        workflow_request = WorkflowBrandSizeChartInput.model_validate_json(
            (execution_context.result_dir / execution_context.workflow_input_path).read_text(encoding="utf-8")
        ).request
        if workflow_request.product_type_request_list and self._have_verified_table(
            input_source.source_type_result_list
        ):
            return self._coverage_decision_step.run(execution_context, input_source, workflow_step_config)
        return self._coverage_decision_default_step.run(execution_context, input_source)

    def source_type_list_get(self, request: WorkflowBrandSizeChartRequest) -> list[str]:
        """Return source types in deterministic registry order.

        Args:
            request: Complete domain request for the current workflow run.

        Returns:
            Ordered source-type list.
        """

        return SOURCE_TYPE_REGISTRY.source_type_list_get(
            have_product_type_request=bool(request.product_type_request_list),
            source_type_allow_list=request.source_type_allow_list,
        )

    def result_validate(
        self,
        execution_context: WorkflowExecutionContext,
        workflow_input: WorkflowBrandSizeChartInput,
        workflow_result: BrandResult,
    ) -> None:
        """Require results to represent exactly the selected source plan.

        Args:
            execution_context: Current brand workflow context.
            workflow_input: Immutable public workflow input.
            workflow_result: Candidate brand workflow result.

        Raises:
            WorkflowResultValidationError: If source results differ from the selected plan.
        """

        _ = execution_context
        selected_source_type_list = self.source_type_list_get(workflow_input.request)
        attempted_source_type_list = [result.source_type for result in workflow_result.source_type_result_list]
        if attempted_source_type_list != selected_source_type_list:
            raise WorkflowResultValidationError(
                feedback_list=[
                    "Return source_type_result_list in exact selected registry order; "
                    f"expected={selected_source_type_list}, actual={attempted_source_type_list}."
                ]
            )

    def _have_verified_table(self, source_type_result_list: list[SourceTypeResult]) -> bool:
        """Return whether any source result declares available source tables.

        Args:
            source_type_result_list: Complete source-discovery result list.

        Returns:
            Whether at least one result declares available source tables.
        """

        return any(
            source_type_result.source_discovery_result is not None
            and source_type_result.source_discovery_result.outcome == "table_available"
            for source_type_result in source_type_result_list
        )


__all__ = ["BrandSizeChartBrandWorkflow"]
