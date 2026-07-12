"""Application entrypoint for the DBOS brand size-chart workflow."""

import importlib.metadata
import os
from pathlib import Path

from dbos import DBOS, DBOSConfig, SetWorkflowID
from workflow_container_runtime.step import BrowserRuntimeCapability
from workflow_container_runtime.workflow import WorkflowExecutionContext, WorkflowRuntimeCapability

from brand_size_chart.app import runtime_config
from brand_size_chart.app.application import BrandSizeChartApplication
from brand_size_chart.identifier import dbos_identifier, dbos_identifier_component, workflow_project_name
from brand_size_chart.model import RunResult, WorkflowBrandSizeChartInput


def main() -> int:
    """Configure and launch the DBOS workflow process.

    Returns:
        Process exit code.
    """
    args = runtime_config.args_parse()
    browser_runtime_mcp_url = args.browser_runtime_mcp_url.strip()
    if not browser_runtime_mcp_url:
        raise RuntimeError(
            f"{runtime_config.DEFAULT_BROWSER_RUNTIME_MCP_URL_ENV} or --browser-runtime-mcp-url must be set."
        )
    workflow_input = WorkflowBrandSizeChartInput.model_validate_json(args.input.read_text(encoding="utf-8"))
    secret_path = Path(args.secret)
    if args.input_secret is not None:
        runtime_config.secret_runtime_materialize(Path(args.input_secret), secret_path)
    codex_profile_path = secret_path / "codex_profile"
    if codex_profile_path.is_dir():
        os.environ["CODEX_HOME"] = str(codex_profile_path)

    project_name = (
        workflow_project_name(git_url=args.workflow_git_url) if args.workflow_git_url else workflow_project_name()
    )
    config: DBOSConfig = {
        "application_version": importlib.metadata.version("brand-size-chart"),
        "executor_id": f"{project_name}.{dbos_identifier_component(args.workflow_run_id)}",
        "name": "brand_size_chart",
        "system_database_url": runtime_config.system_database_url_get(),
    }
    DBOS(config=config)
    application = BrandSizeChartApplication()
    queue_name = dbos_identifier("queue", args.workflow_run_id)
    workflow_id = dbos_identifier("workflow", args.workflow_run_id)
    DBOS.listen_queues([queue_name])
    DBOS.launch()
    DBOS.register_queue(queue_name, worker_concurrency=runtime_config.DEFAULT_QUEUE_WORKER_CONCURRENCY)

    result_dir = args.output_dir.resolve()
    execution_context = WorkflowExecutionContext(
        result_dir=result_dir,
        runtime_capability=WorkflowRuntimeCapability(
            browser=BrowserRuntimeCapability(mcp_url=browser_runtime_mcp_url),
        ),
        workflow_instance_dir=result_dir / "workflow" / "run",
    )
    with SetWorkflowID(workflow_id):
        workflow_handle = DBOS.enqueue_workflow(
            queue_name,
            application.root_workflow.run,
            execution_context,
            workflow_input,
        )
    workflow_result = RunResult.model_validate(workflow_handle.get_result())
    return 1 if workflow_result.status == "failed" else 0
