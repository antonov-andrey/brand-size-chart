"""Source-type DBOS workflow owner."""

from dbos import DBOS, DBOSConfiguredInstance, pydantic_args_validator
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.step import StepResultValidationError, WorkflowStepExecutionContext
from workflow_container_runtime.workflow import WorkflowBase, WorkflowExecutionContext

from brand_size_chart.model import SourceDiscoveryResult, SourceTypeResult, SourceTypeWorkflowInput
from brand_size_chart.step import SourceDiscoveryStep

_MARKET_CONFLICT_ERROR = "Source discovery market conflict."


@DBOS.dbos_class("BrandSizeChartSourceTypeWorkflow")
class BrandSizeChartSourceTypeWorkflow(
    WorkflowBase[SourceTypeWorkflowInput, SourceTypeResult],
    DBOSConfiguredInstance,
):
    """Run the one-step source-discovery lifecycle for one source type."""

    def __init__(
        self,
        *,
        artifact_writer: JsonArtifactWriter,
        config_name: str,
        source_discovery_step: SourceDiscoveryStep,
    ) -> None:
        """Store the reusable source-discovery step.

        Args:
            artifact_writer: Atomic standard-file writer.
            config_name: Stable DBOS configured-instance name.
            source_discovery_step: Browser-backed discovery/extraction step.
        """

        WorkflowBase.__init__(self, artifact_writer=artifact_writer)
        DBOSConfiguredInstance.__init__(self, config_name=config_name)
        self._source_discovery_step = source_discovery_step

    @DBOS.workflow(name="brand_size_chart_source_type", validate_args=pydantic_args_validator)
    def run(
        self,
        execution_context: WorkflowExecutionContext,
        workflow_input: SourceTypeWorkflowInput,
    ) -> SourceTypeResult:
        """Run source discovery and expose only verified terminal outcomes.

        Args:
            execution_context: Current workflow execution context.
            workflow_input: Stable source-type workflow input.

        Returns:
            Complete source-type result.
        """

        self.input_write_step(execution_context, workflow_input)
        try:
            source_discovery_result = self.source_discover_write_step(
                execution_context.for_step(
                    runtime_capability=execution_context.runtime_capability,
                    step_instance_key="source_discover",
                ),
                workflow_input,
            )
        except StepResultValidationError as exc:
            workflow_result = SourceTypeResult(
                error_list=[f"{type(exc).__name__}: {exc}"],
                source_discovery_result=None,
                source_type=workflow_input.source_type,
                status="failed",
                warning_list=[],
            )
        else:
            workflow_result = SourceTypeResult(
                error_list=[_MARKET_CONFLICT_ERROR] if source_discovery_result.outcome == "market_conflict" else [],
                source_discovery_result=source_discovery_result,
                source_type=workflow_input.source_type,
                status="failed" if source_discovery_result.outcome == "market_conflict" else "success",
                warning_list=[],
            )
        return self.result_write_step(execution_context, workflow_input, workflow_result)

    @DBOS.step(name="source_discover_write_step")
    def source_discover_write_step(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: SourceTypeWorkflowInput,
    ) -> SourceDiscoveryResult:
        """Run the complete source-discovery lifecycle inside one durable DBOS step.

        Args:
            execution_context: Current source-discovery step context.
            input_source: Stable source-type workflow input.

        Returns:
            Verified source-discovery result.
        """

        return self._source_discovery_step.run(execution_context, input_source)


__all__ = ["BrandSizeChartSourceTypeWorkflow"]
