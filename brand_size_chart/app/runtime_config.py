"""Runtime configuration helpers for the DBOS application entrypoint."""

import os
import shutil
import stat
from pathlib import Path

DEFAULT_QUEUE_WORKER_CONCURRENCY = 4
INPUT_CODEX_PROFILE_PATH = Path("/input/.secret/codex_profile")
RESULT_PATH = Path("/result")
SYSTEM_DATABASE_URL_PREFIX_TUPLE = ("postgresql://", "postgres://", "sqlite://")
TEMPORARY_PATH = Path("/tmp")
WORKFLOW_DEFINITION_PATH = Path("/app/brand-size-chart/workflow.yaml")
WORKSPACE_PATH = Path("/workspace")


def directory_tree_write_enable(path: Path) -> None:
    """Make copied temporary secret files writable by the container user.

    Args:
        path: Root path of the copied tree.
    """
    path.chmod(path.stat().st_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    for child_path in path.rglob("*"):
        if child_path.is_dir():
            child_path.chmod(child_path.stat().st_mode | stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        else:
            child_path.chmod(child_path.stat().st_mode | stat.S_IRUSR | stat.S_IWUSR)


def secret_directory_materialize(input_secret_path: Path, temporary_secret_path: Path) -> None:
    """Copy one read-only secret directory into pod-local temporary storage.

    Args:
        input_secret_path: Read-only mounted input secret directory.
        temporary_secret_path: Pod-local writable temporary directory.

    Raises:
        FileNotFoundError: If input secret path is missing.
    """
    if not input_secret_path.is_dir():
        raise FileNotFoundError(f"input secret directory is missing: {input_secret_path}")
    temporary_secret_path.parent.mkdir(parents=True, exist_ok=True)
    staging_secret_path = temporary_secret_path.with_name(f".{temporary_secret_path.name}.staging")
    if staging_secret_path.exists():
        shutil.rmtree(staging_secret_path)
    shutil.copytree(input_secret_path, staging_secret_path, symlinks=True)
    directory_tree_write_enable(staging_secret_path)
    if temporary_secret_path.exists():
        shutil.rmtree(temporary_secret_path)
    os.replace(staging_secret_path, temporary_secret_path)


def system_database_url_get(runtime_path: Path) -> str:
    """Return the DBOS system database URL inside private runtime state by default.

    Args:
        runtime_path: Persistent image-visible runtime root.

    Returns:
        Configured or runtime-derived system database URL.

    Raises:
        RuntimeError: If an explicit URL uses an unsupported scheme.
    """
    database_url = (
        os.environ.get("DBOS_SYSTEM_DATABASE_URL", "").strip() or f"sqlite:///{runtime_path / 'dbos.sqlite3'}"
    )
    if not database_url.startswith(SYSTEM_DATABASE_URL_PREFIX_TUPLE):
        raise RuntimeError("DBOS_SYSTEM_DATABASE_URL must use postgresql://, postgres://, or sqlite://.")
    return database_url
