"""Runtime configuration helpers for the DBOS application entrypoint."""

import os
import shutil
import stat
from pathlib import Path

DEFAULT_QUEUE_WORKER_CONCURRENCY = 4
INPUT_SECRET_PATH = Path("/input/.secret")
RESULT_PATH = Path("/result")
SYSTEM_DATABASE_URL_PREFIX_TUPLE = ("postgresql://", "postgres://", "sqlite://")
WORKSPACE_PATH = Path("/workspace")


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
    if runtime_secret_path.exists():
        return
    runtime_secret_path.parent.mkdir(parents=True, exist_ok=True)
    temp_secret_path = runtime_secret_path.with_name(f"{runtime_secret_path.name}.tmp")
    if temp_secret_path.exists():
        shutil.rmtree(temp_secret_path)
    shutil.copytree(input_secret_path, temp_secret_path, symlinks=True)
    directory_tree_write_enable(temp_secret_path)
    if runtime_secret_path.exists():
        shutil.rmtree(runtime_secret_path)
    os.replace(temp_secret_path, runtime_secret_path)


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
