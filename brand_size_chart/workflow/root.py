"""Root DBOS workflow owner."""

from dbos import DBOS, DBOSConfiguredInstance, pydantic_args_validator
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.workflow import WorkflowBase, WorkflowExecutionContext

from brand_size_chart.identifier import dbos_identifier_component
from brand_size_chart.model import BrandInput, BrandResult, RunResult, WorkflowBrandSizeChartInput
from brand_size_chart.workflow.brand import BrandSizeChartBrandWorkflow


@DBOS.dbos_class("BrandSizeChartRunWorkflow")
class BrandSizeChartRunWorkflow(
    WorkflowBase[WorkflowBrandSizeChartInput, RunResult],
    DBOSConfiguredInstance,
):
    """Orchestrate one child brand workflow for every requested brand."""

    def __init__(
        self,
        *,
        artifact_writer: JsonArtifactWriter,
        brand_workflow: BrandSizeChartBrandWorkflow,
        config_name: str,
    ) -> None:
        """Store reusable root workflow dependencies.

        Args:
            artifact_writer: Atomic standard-file writer.
            brand_workflow: Child brand workflow owner.
            config_name: Stable DBOS configured-instance name.
        """

        WorkflowBase.__init__(self, artifact_writer=artifact_writer)
        DBOSConfiguredInstance.__init__(self, config_name=config_name)
        self._brand_workflow = brand_workflow

    @DBOS.workflow(name="brand_size_chart_run", validate_args=pydantic_args_validator)
    async def run(
        self,
        execution_context: WorkflowExecutionContext,
        workflow_input: WorkflowBrandSizeChartInput,
    ) -> RunResult:
        """Run one complete brand-list workflow.

        Args:
            execution_context: Root workflow execution context.
            workflow_input: Complete public workflow input.

        Returns:
            Complete nested run result.
        """

        await self.input_write_step(execution_context, workflow_input)
        brand_result_list: list[BrandResult] = []
        for parsed_brand_name in workflow_input.request.brand_list:
            brand_input = BrandInput(
                parsed_brand_key=dbos_identifier_component(parsed_brand_name),
                parsed_brand_name=parsed_brand_name,
            )
            brand_result_list.append(
                await self._brand_workflow.run(
                    execution_context.for_child_workflow(
                        runtime_capability=execution_context.runtime_capability,
                        workflow_instance_key=f"brand_{brand_input.parsed_brand_key}",
                    ),
                    workflow_input,
                    brand_input,
                )
            )

        workflow_result = RunResult(
            brand_result_list=brand_result_list,
            error_list=[],
            status="success",
            warning_list=[],
        )
        return await self.result_write_step(execution_context, workflow_input, workflow_result)


__all__ = ["BrandSizeChartRunWorkflow"]
