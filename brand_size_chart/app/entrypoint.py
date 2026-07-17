"""Application entrypoint for the DBOS brand size-chart workflow."""

import importlib.metadata
import os
from pathlib import Path

from dbos import DBOS, DBOSConfig, SetWorkflowID
from workflow_container_runtime import WorkflowControlClient, WorkflowPlatformRuntimeConfig
from workflow_container_runtime.capability import WorkflowRuntimeCapability
from workflow_container_runtime.workflow import WorkflowExecutionContext

from brand_size_chart.app import runtime_config
from brand_size_chart.app.application import BrandSizeChartApplication
from brand_size_chart.identifier import dbos_identifier, dbos_identifier_component, workflow_project_name
from brand_size_chart.model import RunResult, WorkflowBrandSizeChartInput


def main() -> int:
    """Configure and launch the DBOS workflow process.

    Returns:
        Process exit code.
    """
    platform_runtime_config = WorkflowPlatformRuntimeConfig.from_environment(os.environ)
    platform_runtime_config.runtime_path.mkdir(parents=True, exist_ok=True)
    (platform_runtime_config.runtime_path / "home").mkdir(exist_ok=True)
    (platform_runtime_config.runtime_path / "tmp").mkdir(exist_ok=True)
    os.environ["HOME"] = str(platform_runtime_config.runtime_path / "home")
    os.environ["TMPDIR"] = str(platform_runtime_config.runtime_path / "tmp")
    control_client = WorkflowControlClient(control_url=platform_runtime_config.control_url)
    control_client.registration_send(workflow_run_id=platform_runtime_config.run_id)

    workflow_input = WorkflowBrandSizeChartInput.model_validate_json(
        platform_runtime_config.input_path.read_text(encoding="utf-8")
    )
    runtime_capability = WorkflowRuntimeCapability.from_platform_config_path(
        platform_runtime_config.capability_config_path
    )
    if runtime_capability.browser is None:
        raise RuntimeError("brand-size-chart requires the declared browser_vpn_runtime capability")
    secret_path = platform_runtime_config.runtime_path / ".secret"
    runtime_config.secret_runtime_materialize(runtime_config.INPUT_SECRET_PATH, secret_path)
    codex_profile_path = secret_path / "codex_profile"
    if codex_profile_path.is_dir():
        os.environ["CODEX_HOME"] = str(codex_profile_path)

    project_name = workflow_project_name()
    config: DBOSConfig = {
        "application_version": importlib.metadata.version("brand-size-chart"),
        "executor_id": f"{project_name}.{dbos_identifier_component(platform_runtime_config.run_id)}",
        "name": "brand_size_chart",
        "system_database_url": runtime_config.system_database_url_get(platform_runtime_config.runtime_path),
    }
    DBOS(config=config)
    application = BrandSizeChartApplication(
        control_client=control_client,
        workspace_path=runtime_config.WORKSPACE_PATH,
    )
    queue_name = dbos_identifier("queue", platform_runtime_config.run_id)
    workflow_id = dbos_identifier("workflow", platform_runtime_config.run_id)
    DBOS.listen_queues([queue_name])
    DBOS.launch()
    DBOS.register_queue(queue_name, worker_concurrency=runtime_config.DEFAULT_QUEUE_WORKER_CONCURRENCY)

    result_dir = runtime_config.RESULT_PATH.resolve()
    execution_context = WorkflowExecutionContext(
        result_dir=result_dir,
        runtime_capability=runtime_capability,
        workflow_instance_dir=result_dir / "workflow" / "run",
    )
    with SetWorkflowID(workflow_id):
        workflow_handle = DBOS.enqueue_workflow(
            queue_name,
            application.root_workflow.run,
            execution_context,
            workflow_input,
        )
    RunResult.model_validate(workflow_handle.get_result())
    return 0
