"""Application entrypoint for the DBOS brand size-chart workflow."""

import os
import sys
from pathlib import Path

import pysqlite3

sys.modules["sqlite3"] = pysqlite3

from dbos import DBOS, DBOSConfig, SetWorkflowID

from brand_size_chart.app import runtime_config
from brand_size_chart.identifier import dbos_identifier, dbos_identifier_component, workflow_project_name
from brand_size_chart.workflow import BRAND_SIZE_CHART_RUN_WORKFLOW, run_failure_result_write


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
    brand_list_text = args.brand_list.read_text(encoding="utf-8")
    secret_path = Path(args.secret)
    if args.input_secret is not None:
        runtime_config.secret_runtime_materialize(Path(args.input_secret), secret_path)
    codex_profile_path = secret_path / "codex_profile"
    if codex_profile_path.is_dir():
        os.environ["CODEX_HOME"] = str(codex_profile_path)

    try:
        project_name = (
            workflow_project_name(git_url=args.workflow_git_url) if args.workflow_git_url else workflow_project_name()
        )
        config: DBOSConfig = {
            "executor_id": f"{project_name}.{dbos_identifier_component(args.workflow_run_id)}",
            "name": "brand_size_chart",
            "system_database_url": runtime_config.system_database_url_get(),
        }
        DBOS(config=config)
        queue_name = dbos_identifier("queue", args.workflow_run_id)
        workflow_id = dbos_identifier("workflow", args.workflow_run_id)
        DBOS.listen_queues([queue_name])
        DBOS.launch()
        DBOS.register_queue(queue_name, worker_concurrency=runtime_config.DEFAULT_QUEUE_WORKER_CONCURRENCY)

        with SetWorkflowID(workflow_id):
            workflow_handle = DBOS.enqueue_workflow(
                queue_name,
                BRAND_SIZE_CHART_RUN_WORKFLOW.run,
                args.workflow_run_id,
                brand_list_text,
                str(args.output_dir),
                args.workflow_run_prompt,
                browser_runtime_mcp_url,
            )
        workflow_result_payload = workflow_handle.get_result()
        if isinstance(workflow_result_payload, dict) and workflow_result_payload.get("status") == "failed":
            return 1
        return 0
    except Exception as exc:
        run_failure_result_write(
            args.output_dir,
            error_code=type(exc).__name__,
            error_message=str(exc),
            workflow_run_id=args.workflow_run_id,
        )
        raise
