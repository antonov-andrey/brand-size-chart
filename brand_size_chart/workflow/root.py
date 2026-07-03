"""Root DBOS workflow owner."""

from pathlib import Path

from dbos import DBOS, DBOSConfiguredInstance, SetWorkflowID

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.identifier import dbos_identifier
from brand_size_chart.io import brand_list_parse
from brand_size_chart.model import BrandListParseWarning, BrandResult, PromptScope, RunResult
from brand_size_chart.workflow.base import ARTIFACT_WRITER, prompt_scope_stage_get
from brand_size_chart.workflow.brand import brand_size_chart_brand
from workflow_container_runtime.codex import codex_stage_run


@DBOS.dbos_class("BrandSizeChartRunWorkflow")
class BrandSizeChartRunWorkflow(DBOSConfiguredInstance):
    """DBOS owner for the root run workflow and run-level side-effect steps."""

    def __init__(self) -> None:
        """Register the stable stateless DBOS instance."""

        super().__init__("default")

    @DBOS.workflow(name="brand_size_chart_run")
    def run(
        self,
        workflow_run_id: str,
        brand_list_text: str,
        secret_ref: str,
        result_dir: str,
        workflow_run_prompt: str,
        browser_runtime_mcp_url: str,
    ) -> dict[str, object]:
        """Run root workflow orchestration for one brand list.

        Args:
            workflow_run_id: Stable workflow run identifier.
            brand_list_text: Raw brand-list input text.
            secret_ref: Secret DataSource path string.
            result_dir: Root result directory string.
            workflow_run_prompt: User-supplied prompt text.
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.

        Returns:
            Serialized `RunResult` payload.
        """
        parse_result = brand_list_parse(brand_list_text)
        prompt_scope = self.prompt_scope_write_step(result_dir, workflow_run_prompt)
        queue_name = dbos_identifier("queue", workflow_run_id)
        brand_result_payload_list: list[dict[str, object]] = []
        for brand_input in parse_result.brand_list:
            with SetWorkflowID(dbos_identifier("workflow", workflow_run_id, brand_input.parsed_brand_name)):
                brand_handle = DBOS.enqueue_workflow(
                    queue_name,
                    brand_size_chart_brand,
                    workflow_run_id,
                    brand_input.model_dump(mode="json"),
                    browser_runtime_mcp_url,
                    prompt_scope,
                    result_dir,
                    secret_ref,
                )
            brand_result_payload_list.append(brand_handle.get_result())
        return self.result_write_step(
            workflow_run_id,
            result_dir,
            brand_result_payload_list,
            prompt_scope,
            [warning.model_dump(mode="json") for warning in parse_result.warning_list],
        )

    @DBOS.step(name="prompt_scope_write_step")
    def prompt_scope_write_step(self, result_dir: str, workflow_run_prompt: str) -> dict[str, object]:
        """Write workflow prompt scope artifacts.

        Args:
            result_dir: Root result directory string.
            workflow_run_prompt: User-supplied prompt text.

        Returns:
            Serialized prompt scope.
        """
        prompt_scope = prompt_scope_stage_get(
            codex_stage_run_callable=codex_stage_run,
            result_dir=Path(result_dir),
            workflow_run_prompt=workflow_run_prompt,
        )
        return prompt_scope.model_dump(mode="json")

    @DBOS.step(name="run_result_write_step")
    def result_write_step(
        self,
        workflow_run_id: str,
        result_dir: str,
        brand_result_payload_list: list[dict[str, object]],
        prompt_scope_payload: dict[str, object],
        warning_payload_list: list[dict[str, object]],
    ) -> dict[str, object]:
        """Write root run result artifact.

        Args:
            workflow_run_id: Workflow run identifier.
            result_dir: Root result directory string.
            brand_result_payload_list: Serialized brand results.
            prompt_scope_payload: Serialized prompt scope.
            warning_payload_list: Serialized brand-list warnings.

        Returns:
            Serialized run result.
        """
        brand_result_list = [BrandResult.model_validate(payload) for payload in brand_result_payload_list]
        failed_brand_result_list = [
            brand_result for brand_result in brand_result_list if brand_result.status == "failed"
        ]
        run_error_list = [
            f"{brand_result.parsed_brand_name}: {error}"
            for brand_result in failed_brand_result_list
            for error in brand_result.error_list
        ]
        run_result = RunResult(
            brand_result_list=brand_result_list,
            error_list=run_error_list,
            message=(
                "Workflow run completed with failed brands." if failed_brand_result_list else "Workflow run completed."
            ),
            prompt_scope=PromptScope.model_validate(prompt_scope_payload),
            result_dir=result_dir,
            status="failed" if failed_brand_result_list else "success",
            warning_list=[BrandListParseWarning.model_validate(payload) for payload in warning_payload_list],
            workflow_run_id=workflow_run_id,
        )
        ARTIFACT_WRITER.write(ArtifactLayout(Path(result_dir)).run_result_path(), run_result)
        return run_result.model_dump(mode="json")


def run_failure_result_write(
    result_dir: Path,
    *,
    error_code: str,
    error_message: str,
    workflow_run_id: str,
) -> RunResult:
    """Write root failure result for entrypoint-level startup errors.

    Args:
        result_dir: Root result directory.
        error_code: Stable error class name.
        error_message: Error detail.
        workflow_run_id: Workflow run identifier.

    Returns:
        Written run result.
    """
    error_text = f"{error_code}: {error_message}"
    run_result = RunResult(
        brand_result_list=[],
        error_list=[error_text],
        message="Workflow run failed before DBOS root workflow completed.",
        prompt_scope=PromptScope(),
        result_dir=str(result_dir),
        status="failed",
        warning_list=[],
        workflow_run_id=workflow_run_id,
    )
    ARTIFACT_WRITER.write(ArtifactLayout(result_dir).run_result_path(), run_result)
    return run_result


BRAND_SIZE_CHART_RUN_WORKFLOW = BrandSizeChartRunWorkflow()
brand_size_chart_run = BRAND_SIZE_CHART_RUN_WORKFLOW.run
prompt_scope_write_step = BRAND_SIZE_CHART_RUN_WORKFLOW.prompt_scope_write_step
run_result_write_step = BRAND_SIZE_CHART_RUN_WORKFLOW.result_write_step

__all__ = [
    "BRAND_SIZE_CHART_RUN_WORKFLOW",
    "BrandSizeChartRunWorkflow",
    "brand_size_chart_run",
    "prompt_scope_write_step",
    "run_failure_result_write",
    "run_result_write_step",
]
