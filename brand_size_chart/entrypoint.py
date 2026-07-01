"""Command-line entrypoint for the DBOS brand size-chart workflow."""

import argparse
import os
import shutil
import stat
import sys
from pathlib import Path

import pysqlite3

sys.modules["sqlite3"] = pysqlite3

from dbos import DBOS, DBOSConfig, SetWorkflowID

from brand_size_chart.identifier import dbos_identifier, dbos_identifier_component, workflow_project_name
from brand_size_chart.workflow import brand_size_chart_workflow, run_failure_result_write

DEFAULT_BROWSER_RUNTIME_MCP_URL_ENV = "BROWSER_RUNTIME_MCP_URL"
DEFAULT_QUEUE_WORKER_CONCURRENCY = 4
SYSTEM_DATABASE_URL_PREFIX_TUPLE = ("postgresql://", "postgres://", "sqlite://")


def _directory_tree_write_enable(path: Path) -> None:
    """Make copied runtime secret files writable by the container user.

    Args:
        path: Root path of the copied tree.
    """
    path.chmod(path.stat().st_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    for child_path in path.rglob("*"):
        if child_path.is_dir():
            child_path.chmod(child_path.stat().st_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        else:
            child_path.chmod(child_path.stat().st_mode | stat.S_IRUSR | stat.S_IWUSR)


def _secret_runtime_materialize(input_secret_path: Path, runtime_secret_path: Path) -> None:
    """Copy read-only input secret into pod-local runtime secret storage.

    Args:
        input_secret_path: Read-only mounted input secret directory.
        runtime_secret_path: Pod-local writable secret directory.

    Raises:
        FileNotFoundError: If input secret path is missing.
    """
    if not input_secret_path.is_dir():
        raise FileNotFoundError(f"input secret directory is missing: {input_secret_path}")
    runtime_secret_path.parent.mkdir(parents=True, exist_ok=True)
    temp_secret_path = runtime_secret_path.with_name(f"{runtime_secret_path.name}.tmp")
    if temp_secret_path.exists():
        shutil.rmtree(temp_secret_path)
    shutil.copytree(input_secret_path, temp_secret_path, symlinks=True)
    _directory_tree_write_enable(temp_secret_path)
    if runtime_secret_path.exists():
        shutil.rmtree(runtime_secret_path)
    os.replace(temp_secret_path, runtime_secret_path)


def args_parse() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Run the brand size-chart DBOS workflow.")
    parser.add_argument("--browser-runtime-mcp-url", default=os.environ.get(DEFAULT_BROWSER_RUNTIME_MCP_URL_ENV, ""))
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--brand-list", required=True, type=Path)
    parser.add_argument("--input-secret", default=None, type=Path)
    parser.add_argument("--secret", default=Path(".secret"), type=Path)
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
    browser_runtime_mcp_url = args.browser_runtime_mcp_url.strip()
    if not browser_runtime_mcp_url:
        raise RuntimeError(f"{DEFAULT_BROWSER_RUNTIME_MCP_URL_ENV} or --browser-runtime-mcp-url must be set.")
    brand_list_text = args.brand_list.read_text(encoding="utf-8")
    secret_path = Path(args.secret)
    if args.input_secret is not None:
        _secret_runtime_materialize(Path(args.input_secret), secret_path)
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
                str(secret_path),
                str(args.output_dir),
                args.workflow_run_prompt,
                browser_runtime_mcp_url,
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
