"""Runtime configuration helpers for the DBOS application entrypoint."""

import argparse
import os
import shutil
import stat
from pathlib import Path

DEFAULT_MCP_PLAYWRIGHT_PROFILE_SOURCE_ENV = "MCP_PLAYWRIGHT_PROFILE_SOURCE"
DEFAULT_MCP_PLAYWRIGHT_PROFILE_WRITEBACK_CANDIDATE_URL_ENV = "MCP_PLAYWRIGHT_PROFILE_WRITEBACK_CANDIDATE_URL"
DEFAULT_MCP_URL_ENV = "MCP_URL"
DEFAULT_QUEUE_WORKER_CONCURRENCY = 4
SYSTEM_DATABASE_URL_PREFIX_TUPLE = ("postgresql://", "postgres://", "sqlite://")


def args_parse() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Run the brand size-chart DBOS workflow.")
    parser.add_argument(
        "--mcp-playwright-profile-source",
        default=os.environ.get(DEFAULT_MCP_PLAYWRIGHT_PROFILE_SOURCE_ENV, ""),
    )
    parser.add_argument(
        "--mcp-playwright-profile-writeback-candidate-url",
        default=os.environ.get(DEFAULT_MCP_PLAYWRIGHT_PROFILE_WRITEBACK_CANDIDATE_URL_ENV, ""),
    )
    parser.add_argument("--mcp-url", default=os.environ.get(DEFAULT_MCP_URL_ENV, ""))
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--input-secret", default=None, type=Path)
    parser.add_argument("--secret", default=Path(".secret"), type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--workflow-git-url", default=os.environ.get("WORKFLOW_GIT_URL", ""))
    return parser.parse_args()


def directory_tree_write_enable(path: Path) -> None:
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


def secret_runtime_materialize(input_secret_path: Path, runtime_secret_path: Path) -> None:
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
    directory_tree_write_enable(temp_secret_path)
    if runtime_secret_path.exists():
        shutil.rmtree(runtime_secret_path)
    os.replace(temp_secret_path, runtime_secret_path)


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
