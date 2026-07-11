"""Brand-level DBOS workflow owner."""

from dbos import DBOS, DBOSConfiguredInstance, pydantic_args_validator
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.step import StepResultValidationError, WorkflowStepExecutionContext
from workflow_container_runtime.workflow import (
    WorkflowBase,
    WorkflowExecutionContext,
    WorkflowResultValidationError,
    WorkflowRuntimeCapability,
)

from brand_size_chart.model import (
    BrandOutputInputSource,
    BrandOutputResult,
    BrandResult,
    BrandSourceTypeResultInputSource,
    BrandWorkflowInput,
    CanonicalSelectionResult,
    CoverageDecisionResult,
    PromptScope,
    SourceTypeSkip,
    SourceTypeResult,
    SourceTypeWorkflowInput,
)
from brand_size_chart.source import SOURCE_TYPE_REGISTRY
from brand_size_chart.step import (
    BrandOutputStep,
    CanonicalSelectionDefaultStep,
    CanonicalSelectionStep,
    CoverageDecisionDefaultStep,
    CoverageDecisionStep,
)
from brand_size_chart.workflow.source_type import BrandSizeChartSourceTypeWorkflow


@DBOS.dbos_class("BrandSizeChartBrandWorkflow")
class BrandSizeChartBrandWorkflow(
    WorkflowBase[BrandWorkflowInput, BrandResult],
    DBOSConfiguredInstance,
):
    """Orchestrate source-type children and brand-owned decision steps."""

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
        source_type_workflow: BrandSizeChartSourceTypeWorkflow,
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
            source_type_workflow: Child source-type workflow owner.
        """

        WorkflowBase.__init__(self, artifact_writer=artifact_writer)
        DBOSConfiguredInstance.__init__(self, config_name=config_name)
        self._brand_output_step = brand_output_step
        self._canonical_selection_default_step = canonical_selection_default_step
        self._canonical_selection_step = canonical_selection_step
        self._coverage_decision_default_step = coverage_decision_default_step
        self._coverage_decision_step = coverage_decision_step
        self._source_type_workflow = source_type_workflow

    @DBOS.workflow(name="brand_size_chart_brand", validate_args=pydantic_args_validator)
    def run(
        self,
        execution_context: WorkflowExecutionContext,
        workflow_input: BrandWorkflowInput,
    ) -> BrandResult:
        """Run one brand workflow and preserve every child result.

        Args:
            execution_context: Current brand workflow context.
            workflow_input: Stable brand workflow input.

        Returns:
            Complete brand result tree.
        """

        self.input_write_step(execution_context, workflow_input)
        source_type_list = self.source_type_list_get(workflow_input.prompt_scope)
        source_type_result_list: list[SourceTypeResult] = []
        source_type_skip_list: list[SourceTypeSkip] = []
        remaining_product_type_list = list(workflow_input.prompt_scope.product_type_request_list)
        coverage_decision_result: CoverageDecisionResult | None = None
        canonical_selection_result: CanonicalSelectionResult | None = None
        brand_output_result: BrandOutputResult | None = None
        error_list: list[str] = []

        for source_type_index, source_type in enumerate(source_type_list):
            if (
                SOURCE_TYPE_REGISTRY.source_type_requires_product_type(source_type)
                and workflow_input.prompt_scope.product_type_request_list
                and not remaining_product_type_list
            ):
                source_type_skip_list.append(
                    SourceTypeSkip(
                        reason="requested_product_type_coverage_complete",
                        source_type=source_type,
                    )
                )
                continue
            source_type_workflow_input = SourceTypeWorkflowInput(
                brand_input=workflow_input.brand_input,
                prompt_scope=self._source_type_prompt_scope_get(
                    prompt_scope=workflow_input.prompt_scope,
                    remaining_product_type_list=remaining_product_type_list,
                    source_type=source_type,
                ),
                source_type=source_type,
            )
            source_type_result = self._source_type_workflow.run(
                execution_context.for_child_workflow(
                    runtime_capability=execution_context.runtime_capability,
                    workflow_instance_key=source_type,
                ),
                source_type_workflow_input,
            )
            source_type_result_list.append(source_type_result)

            if workflow_input.prompt_scope.product_type_request_list and self._have_verified_table(
                [source_type_result]
            ):
                try:
                    coverage_decision_result = self.coverage_decide_write_step(
                        execution_context.for_step(
                            runtime_capability=WorkflowRuntimeCapability(browser=None),
                            step_instance_key=f"coverage_decide_{source_type}",
                        ),
                        BrandSourceTypeResultInputSource(
                            source_type_result_list=source_type_result_list,
                            workflow_input=workflow_input,
                        ),
                    )
                except StepResultValidationError as exc:
                    error_list.append(f"{type(exc).__name__}: {exc}")
                    source_type_skip_list.extend(
                        SourceTypeSkip(
                            reason="coverage_decision_failed",
                            source_type=pending_source_type,
                        )
                        for pending_source_type in source_type_list[source_type_index + 1 :]
                    )
                    break
                remaining_product_type_list = [
                    product_type_gap.product_type
                    for product_type_gap in coverage_decision_result.uncovered_product_type_gap_list
                ]

        decision_input_source = BrandSourceTypeResultInputSource(
            source_type_result_list=source_type_result_list,
            workflow_input=workflow_input,
        )
        if not error_list:
            try:
                if coverage_decision_result is None:
                    coverage_decision_result = self.coverage_decide_write_step(
                        execution_context.for_step(
                            runtime_capability=WorkflowRuntimeCapability(browser=None),
                            step_instance_key="coverage_decide",
                        ),
                        decision_input_source,
                    )
                canonical_selection_result = self.canonical_select_write_step(
                    execution_context.for_step(
                        runtime_capability=WorkflowRuntimeCapability(browser=None),
                        step_instance_key="canonical_select",
                    ),
                    decision_input_source,
                )
                brand_output_result = self.brand_output_write_step(
                    execution_context.for_step(
                        runtime_capability=WorkflowRuntimeCapability(browser=None),
                        step_instance_key="brand_output",
                    ),
                    BrandOutputInputSource(
                        canonical_selection_result=canonical_selection_result,
                        source_type_result_list=source_type_result_list,
                        workflow_input=workflow_input,
                    ),
                )
            except StepResultValidationError as exc:
                error_list.append(f"{type(exc).__name__}: {exc}")

        workflow_result = BrandResult(
            brand_input=workflow_input.brand_input,
            brand_output_result=brand_output_result,
            canonical_selection_result=canonical_selection_result,
            coverage_decision_result=coverage_decision_result,
            error_list=error_list,
            source_type_result_list=source_type_result_list,
            source_type_skip_list=source_type_skip_list,
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
            input_source: Verified decisions and complete source-type results.

        Returns:
            Final brand output result.
        """

        return self._brand_output_step.run(execution_context, input_source)

    @DBOS.step(name="canonical_select_write_step")
    def canonical_select_write_step(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: BrandSourceTypeResultInputSource,
    ) -> CanonicalSelectionResult:
        """Run semantic or deterministic canonical selection.

        Args:
            execution_context: Current canonical-selection step context.
            input_source: Brand input and complete source-type results.

        Returns:
            Verified canonical-selection result.
        """

        if self._canonical_selection_step.have_candidate(input_source):
            return self._canonical_selection_step.run(execution_context, input_source)
        return self._canonical_selection_default_step.run(execution_context, input_source)

    @DBOS.step(name="coverage_decide_write_step")
    def coverage_decide_write_step(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: BrandSourceTypeResultInputSource,
    ) -> CoverageDecisionResult:
        """Run semantic or deterministic requested-product coverage.

        Args:
            execution_context: Current coverage-decision step context.
            input_source: Brand input and complete source-type results.

        Returns:
            Verified coverage decision.
        """

        if input_source.workflow_input.prompt_scope.product_type_request_list and self._have_verified_table(
            input_source.source_type_result_list
        ):
            return self._coverage_decision_step.run(execution_context, input_source)
        return self._coverage_decision_default_step.run(execution_context, input_source)

    def source_type_list_get(self, prompt_scope: PromptScope) -> list[str]:
        """Return source types in deterministic execution order.

        Args:
            prompt_scope: Verified workflow prompt scope.

        Returns:
            Ordered source-type list.
        """

        return SOURCE_TYPE_REGISTRY.source_type_list_get(
            have_product_type_request=bool(prompt_scope.product_type_request_list),
            source_type_allow_list=prompt_scope.source_type_allow_list,
        )

    def result_validate(
        self,
        execution_context: WorkflowExecutionContext,
        workflow_input: BrandWorkflowInput,
        workflow_result: BrandResult,
    ) -> None:
        """Require the result and skip channels to partition the selected source plan.

        Args:
            execution_context: Current brand workflow context.
            workflow_input: Immutable brand workflow input.
            workflow_result: Candidate brand workflow result.

        Raises:
            WorkflowResultValidationError: If one selected source is missing or one unselected source is represented.
        """

        _ = execution_context
        selected_source_type_list = self.source_type_list_get(workflow_input.prompt_scope)
        attempted_source_type_list = [result.source_type for result in workflow_result.source_type_result_list]
        skipped_source_type_list = [skip.source_type for skip in workflow_result.source_type_skip_list]
        represented_source_type_list = attempted_source_type_list + skipped_source_type_list
        selected_source_type_set = set(selected_source_type_list)
        represented_source_type_set = set(represented_source_type_list)
        missing_source_type_list = [
            source_type for source_type in selected_source_type_list if source_type not in represented_source_type_set
        ]
        extra_source_type_list = sorted(represented_source_type_set - selected_source_type_set)
        if missing_source_type_list or extra_source_type_list:
            raise WorkflowResultValidationError(
                feedback_list=[
                    "Partition the selected source plan exactly between source_type_result_list and "
                    "source_type_skip_list; "
                    f"missing={missing_source_type_list}, extra={extra_source_type_list}."
                ]
            )

    def _have_verified_table(self, source_type_result_list: list[SourceTypeResult]) -> bool:
        """Return whether any child result declares available source tables.

        Args:
            source_type_result_list: Complete source-type result list.

        Returns:
            Whether at least one complete child result declares available source tables.
        """

        return any(
            source_type_result.source_discovery_result is not None
            and source_type_result.source_discovery_result.outcome == "table_available"
            for source_type_result in source_type_result_list
        )

    def _source_type_prompt_scope_get(
        self,
        *,
        prompt_scope: PromptScope,
        remaining_product_type_list: list[str],
        source_type: str,
    ) -> PromptScope:
        """Build the exact prompt scope for one source-type child.

        Args:
            prompt_scope: Verified brand prompt scope.
            remaining_product_type_list: Product types not yet covered.
            source_type: Current source-type key.

        Returns:
            Source-type-local prompt scope.
        """

        product_type_request_list = (
            remaining_product_type_list if SOURCE_TYPE_REGISTRY.source_type_requires_product_type(source_type) else []
        )
        return PromptScope(
            priority_country_code=prompt_scope.priority_country_code,
            product_type_request_list=product_type_request_list,
            shared_instruction=prompt_scope.shared_instruction,
            source_type_allow_list=prompt_scope.source_type_allow_list,
            step_instruction_list=prompt_scope.step_instruction_list,
        )


__all__ = ["BrandSizeChartBrandWorkflow"]
