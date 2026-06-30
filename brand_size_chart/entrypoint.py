"""Command-line entrypoint for the DBOS brand size-chart workflow."""

import argparse
import os
from pathlib import Path

from dbos import DBOS, DBOSConfig, SetWorkflowID

from brand_size_chart.identifier import dbos_identifier, dbos_identifier_component, workflow_project_name
from brand_size_chart.workflow import brand_size_chart_workflow, run_failure_result_write

DEFAULT_QUEUE_WORKER_CONCURRENCY = 4
SYSTEM_DATABASE_URL_PREFIX_TUPLE = ("postgresql://", "postgres://", "sqlite://")


def args_parse() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Run the brand size-chart DBOS workflow.")
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--brand-list", required=True, type=Path)
    parser.add_argument("--secret", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--workflow-run-prompt", default="")
    parser.add_argument("--workflow-git-url", default=os.environ.get("WORKFLOW_GIT_URL", ""))
    return parser.parse_args()


def system_database_url_get() -> str:
    """Return the explicit DBOS system database URL.

    Returns:
        Configured system database URL.

    Raises:
        RuntimeError: If the URL is absent or uses an unsupported scheme.
    """
    database_url = os.environ.get("DBOS_SYSTEM_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "DBOS_SYSTEM_DATABASE_URL must be set explicitly. "
            "DBOS otherwise falls back to a local SQLite system database."
        )
    if not database_url.startswith(SYSTEM_DATABASE_URL_PREFIX_TUPLE):
        raise RuntimeError("DBOS_SYSTEM_DATABASE_URL must use postgresql://, postgres://, or sqlite://.")
    return database_url


def main() -> None:
    """Configure and launch the DBOS workflow process."""
    args = args_parse()
    brand_list_text = args.brand_list.read_text(encoding="utf-8")
    codex_profile_path = Path(args.secret) / "codex_profile"
    if codex_profile_path.is_dir():
        os.environ["CODEX_HOME"] = str(codex_profile_path)

    try:
        project_name = (
            workflow_project_name(git_url=args.workflow_git_url) if args.workflow_git_url else workflow_project_name()
        )
        config: DBOSConfig = {
            "executor_id": f"{project_name}.{dbos_identifier_component(args.workflow_run_id)}",
            "name": "brand_size_chart",
            "system_database_url": system_database_url_get(),
        }
        DBOS(config=config)
        queue_name = dbos_identifier("queue", args.workflow_run_id)
        workflow_id = dbos_identifier("workflow", args.workflow_run_id)
        DBOS.listen_queues([queue_name])
        DBOS.launch()
        DBOS.register_queue(queue_name, worker_concurrency=DEFAULT_QUEUE_WORKER_CONCURRENCY)

        with SetWorkflowID(workflow_id):
            workflow_handle = DBOS.enqueue_workflow(
                queue_name,
                brand_size_chart_workflow,
                args.workflow_run_id,
                brand_list_text,
                args.secret,
                str(args.output_dir),
                args.workflow_run_prompt,
            )
        workflow_handle.get_result()
    except Exception as exc:
        run_failure_result_write(
            args.output_dir,
            error_code=type(exc).__name__,
            error_message=str(exc),
            workflow_run_id=args.workflow_run_id,
        )
        raise


if __name__ == "__main__":
    main()
