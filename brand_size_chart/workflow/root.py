"""Root DBOS workflow owner."""

from pathlib import Path

from dbos import DBOS, DBOSConfiguredInstance, pydantic_args_validator
from workflow_container_contract import (
    WorkflowControlPublicationRequest,
    WorkflowControlSafepointRequest,
    WorkflowControlTerminalRequest,
)
from workflow_container_runtime import WorkflowControlClient
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.workflow import WorkflowBase, WorkflowExecutionContext

from brand_size_chart.identifier import dbos_identifier_component
from brand_size_chart.model import BrandInput, BrandResult, BrandSafepoint, RunResult, WorkflowBrandSizeChartInput
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
        control_client: WorkflowControlClient,
        workspace_path: Path,
    ) -> None:
        """Store reusable root workflow dependencies.

        Args:
            artifact_writer: Atomic standard-file writer.
            brand_workflow: Child brand workflow owner.
            config_name: Stable DBOS configured-instance name.
            control_client: Current execution-local platform control adapter.
            workspace_path: Declared writable workspace mount root.
        """

        WorkflowBase.__init__(self, artifact_writer=artifact_writer)
        DBOSConfiguredInstance.__init__(self, config_name=config_name)
        self._brand_workflow = brand_workflow
        self._control_client = control_client
        self._workspace_path = workspace_path

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
            brand_execution_context = execution_context.for_child_workflow(
                runtime_capability=execution_context.runtime_capability,
                workflow_instance_key=f"brand_{brand_input.parsed_brand_key}",
            )
            brand_result = await self._brand_workflow.run(
                brand_execution_context,
                workflow_input,
                brand_input,
            )
            brand_result_list.append(brand_result)
            self.brand_safepoint_step(
                brand_execution_context,
                brand_input,
                brand_result,
            )

        workflow_result = RunResult(
            brand_result_list=brand_result_list,
            error_list=[],
            status="success",
            warning_list=[],
        )
        workflow_result = await self.result_write_step(execution_context, workflow_input, workflow_result)
        self.terminal_request_step(workflow_result)
        return workflow_result

    @DBOS.step(name="brand_safepoint_step")
    def brand_safepoint_step(
        self,
        brand_execution_context: WorkflowExecutionContext,
        brand_input: BrandInput,
        brand_result: BrandResult,
    ) -> None:
        """Publish one completed brand result and workspace marker atomically.

        Args:
            brand_execution_context: Exact child workflow result location.
            brand_input: Stable brand identity.
            brand_result: Accepted child workflow result.
        """

        workspace_relative_path = Path("brand") / brand_input.parsed_brand_key
        self._artifact_writer.write(
            self._workspace_path / workspace_relative_path / "safepoint.json",
            BrandSafepoint(
                parsed_brand_key=brand_input.parsed_brand_key,
                parsed_brand_name=brand_input.parsed_brand_name,
                status=brand_result.status,
            ),
        )
        result_relative_path = brand_execution_context.workflow_instance_dir.relative_to(
            brand_execution_context.result_dir
        )
        self._control_client.safepoint_send(
            request=WorkflowControlSafepointRequest(
                publication_request_list=[
                    WorkflowControlPublicationRequest(
                        data_mount_key="result",
                        source_relative_path=result_relative_path.as_posix(),
                    ),
                    WorkflowControlPublicationRequest(
                        data_mount_key="workspace",
                        source_relative_path=workspace_relative_path.as_posix(),
                    ),
                ],
                step_identity=f"brand/{brand_input.parsed_brand_key}",
                transition_identity=f"brand/{brand_input.parsed_brand_key}/completed",
            )
        )

    @DBOS.step(name="terminal_request_step")
    def terminal_request_step(self, workflow_result: RunResult) -> None:
        """Persist the final result and declared mount trees as one terminal intent.

        Args:
            workflow_result: Exact accepted root workflow result.
        """

        self._control_client.terminal_send(
            request=WorkflowControlTerminalRequest(
                publication_request_list=[
                    WorkflowControlPublicationRequest(
                        data_mount_key="result",
                        source_relative_path="workflow/run",
                    ),
                    WorkflowControlPublicationRequest(
                        data_mount_key="workspace",
                        source_relative_path="brand",
                    ),
                ],
                transition_identity="run/completed",
                workflow_result=workflow_result,
            )
        )


__all__ = ["BrandSizeChartRunWorkflow"]
