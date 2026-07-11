"""Root DBOS workflow owner."""

from dbos import DBOS, DBOSConfiguredInstance, pydantic_args_validator
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.step import StepResultValidationError, WorkflowStepExecutionContext
from workflow_container_runtime.workflow import WorkflowBase, WorkflowExecutionContext, WorkflowRuntimeCapability

from brand_size_chart.io import brand_list_parse
from brand_size_chart.model import BrandResult, BrandWorkflowInput, PromptScope, RunInput, RunResult
from brand_size_chart.step import WorkflowRunPromptApplyDefaultStep, WorkflowRunPromptApplyStep
from brand_size_chart.workflow.brand import BrandSizeChartBrandWorkflow


@DBOS.dbos_class("BrandSizeChartRunWorkflow")
class BrandSizeChartRunWorkflow(
    WorkflowBase[RunInput, RunResult],
    DBOSConfiguredInstance,
):
    """Orchestrate prompt parsing and one child workflow per brand."""

    def __init__(
        self,
        *,
        artifact_writer: JsonArtifactWriter,
        brand_workflow: BrandSizeChartBrandWorkflow,
        config_name: str,
        workflow_run_prompt_apply_default_step: WorkflowRunPromptApplyDefaultStep,
        workflow_run_prompt_apply_step: WorkflowRunPromptApplyStep,
    ) -> None:
        """Store reusable root workflow dependencies.

        Args:
            artifact_writer: Atomic standard-file writer.
            brand_workflow: Child brand workflow owner.
            config_name: Stable DBOS configured-instance name.
            workflow_run_prompt_apply_default_step: Deterministic empty-prompt step.
            workflow_run_prompt_apply_step: Semantic workflow-prompt parsing step.
        """

        WorkflowBase.__init__(self, artifact_writer=artifact_writer)
        DBOSConfiguredInstance.__init__(self, config_name=config_name)
        self._brand_workflow = brand_workflow
        self._workflow_run_prompt_apply_default_step = workflow_run_prompt_apply_default_step
        self._workflow_run_prompt_apply_step = workflow_run_prompt_apply_step

    @DBOS.workflow(name="brand_size_chart_run", validate_args=pydantic_args_validator)
    def run(
        self,
        execution_context: WorkflowExecutionContext,
        workflow_input: RunInput,
    ) -> RunResult:
        """Run one complete brand-list workflow.

        Args:
            execution_context: Root workflow execution context.
            workflow_input: Stable root workflow input.

        Returns:
            Complete nested run result.
        """

        self.input_write_step(execution_context, workflow_input)
        brand_list_parse_result = brand_list_parse(workflow_input.brand_list_text)
        error_list: list[str] = []
        prompt_scope: PromptScope | None = None
        brand_result_list: list[BrandResult] = []
        if not brand_list_parse_result.brand_list:
            error_list.append("Brand list contains no valid brand names.")
        else:
            try:
                prompt_scope = self.prompt_scope_write_step(
                    execution_context.for_step(
                        runtime_capability=WorkflowRuntimeCapability(browser=None),
                        step_instance_key="workflow_run_prompt_apply",
                    ),
                    workflow_input,
                )
            except StepResultValidationError as exc:
                error_list.append(f"{type(exc).__name__}: {exc}")

        if prompt_scope is not None and not prompt_scope.priority_country_code:
            error_list.append("Workflow prompt must specify one priority country.")

        if prompt_scope is not None and not error_list:
            for brand_input in brand_list_parse_result.brand_list:
                brand_result_list.append(
                    self._brand_workflow.run(
                        execution_context.for_child_workflow(
                            runtime_capability=execution_context.runtime_capability,
                            workflow_instance_key=f"brand_{brand_input.parsed_brand_key}",
                        ),
                        BrandWorkflowInput(
                            brand_input=brand_input,
                            prompt_scope=prompt_scope,
                        ),
                    )
                )

        workflow_result = RunResult(
            brand_list_parse_warning_list=brand_list_parse_result.warning_list,
            brand_result_list=brand_result_list,
            error_list=error_list,
            prompt_scope=prompt_scope,
            status="failed" if error_list else "success",
            warning_list=[],
        )
        return self.result_write_step(execution_context, workflow_input, workflow_result)

    @DBOS.step(name="workflow_run_prompt_apply_write_step")
    def prompt_scope_write_step(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: RunInput,
    ) -> PromptScope:
        """Run semantic or deterministic workflow-prompt parsing.

        Args:
            execution_context: Current prompt-application step context.
            input_source: Root workflow input.

        Returns:
            Verified prompt scope.
        """

        if input_source.workflow_run_prompt.strip():
            return self._workflow_run_prompt_apply_step.run(execution_context, input_source)
        return self._workflow_run_prompt_apply_default_step.run(execution_context, input_source)


__all__ = ["BrandSizeChartRunWorkflow"]
