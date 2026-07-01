"""Tests for DBOS entrypoint bootstrap."""

import argparse
import os
from pathlib import Path

import pytest

from brand_size_chart.app import entrypoint
from brand_size_chart.app import runtime_config


class _FakeWorkflowHandle:
    """Minimal DBOS workflow handle test double."""

    def __init__(self, event_list: list[tuple[str, object]]) -> None:
        """Store the shared event log.

        Args:
            event_list: Mutable list that records DBOS calls.
        """
        self._event_list = event_list

    def get_result(self) -> dict[str, str]:
        """Record result wait and return a dummy workflow result.

        Returns:
            Dummy workflow result.
        """
        self._event_list.append(("get_result", None))
        return {"state": "completed"}


class _FakeSetWorkflowID:
    """Context manager that records the requested DBOS workflow id."""

    event_list: list[tuple[str, object]] = []

    def __init__(self, workflow_id: str) -> None:
        """Store the workflow id.

        Args:
            workflow_id: DBOS workflow id.
        """
        self._workflow_id = workflow_id

    def __enter__(self) -> None:
        """Record context entry."""
        self.event_list.append(("workflow_id_enter", self._workflow_id))

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        """Record context exit.

        Args:
            exc_type: Exception type, when one is active.
            exc_value: Exception value, when one is active.
            traceback: Exception traceback, when one is active.
        """
        self.event_list.append(("workflow_id_exit", self._workflow_id))


class _FakeDBOS:
    """DBOS test double that records bootstrap call order and arguments."""

    event_list: list[tuple[str, object]] = []

    def __init__(self, *, config: dict[str, object]) -> None:
        """Record DBOS singleton configuration.

        Args:
            config: DBOS configuration payload.
        """
        self.event_list.append(("configure", config))

    @classmethod
    def enqueue_workflow(cls, queue_name: str, function: object, *args: object) -> _FakeWorkflowHandle:
        """Record workflow enqueue call.

        Args:
            queue_name: Queue name.
            function: Workflow function.
            *args: Workflow arguments.

        Returns:
            Fake workflow handle.
        """
        cls.event_list.append(("enqueue_workflow", (queue_name, args)))
        return _FakeWorkflowHandle(cls.event_list)

    @classmethod
    def launch(cls) -> None:
        """Record DBOS launch."""
        cls.event_list.append(("launch", None))

    @classmethod
    def listen_queues(cls, queue_name_list: list[str]) -> None:
        """Record queue listen configuration.

        Args:
            queue_name_list: Queue names listened by this process.
        """
        cls.event_list.append(("listen_queues", queue_name_list))

    @classmethod
    def register_queue(cls, queue_name: str, *, worker_concurrency: int) -> None:
        """Record queue registration.

        Args:
            queue_name: Queue name.
            worker_concurrency: Per-worker concurrency limit.
        """
        cls.event_list.append(("register_queue", (queue_name, worker_concurrency)))


def test_entrypoint_bootstraps_dbos_with_stable_ids_and_worker_concurrency(monkeypatch: object, tmp_path: Path) -> None:
    """Configure DBOS with stable identifiers and register the one workflow-run queue."""
    brand_list_path = tmp_path / "brand_list.txt"
    brand_list_path.write_text("Mavi\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    secret_dir = tmp_path / "secret"
    event_list: list[tuple[str, object]] = []
    _FakeDBOS.event_list = event_list
    _FakeSetWorkflowID.event_list = event_list

    monkeypatch.setattr(entrypoint, "DBOS", _FakeDBOS)
    monkeypatch.setattr(entrypoint, "SetWorkflowID", _FakeSetWorkflowID)
    monkeypatch.setattr(
        runtime_config,
        "args_parse",
        lambda: argparse.Namespace(
            brand_list=brand_list_path,
            browser_runtime_mcp_url="http://browser-runtime:8931/mcp",
            input_secret=None,
            output_dir=output_dir,
            secret=str(secret_dir),
            workflow_git_url="git@github.com:antonov-andrey/brand-size-chart.git",
            workflow_run_id="Run 01",
            workflow_run_prompt="official_brand_size_guide only",
        ),
    )
    monkeypatch.setenv("DBOS_SYSTEM_DATABASE_URL", "postgresql://dbos:secret@localhost:5432/brand_size_chart")

    entrypoint.main()

    assert event_list == [
        (
            "configure",
            {
                "executor_id": "antonov-andrey__brand-size-chart.run_01",
                "name": "brand_size_chart",
                "system_database_url": "postgresql://dbos:secret@localhost:5432/brand_size_chart",
            },
        ),
        ("listen_queues", ["queue/run_01"]),
        ("launch", None),
        ("register_queue", ("queue/run_01", 4)),
        ("workflow_id_enter", "workflow/run_01"),
        (
            "enqueue_workflow",
            (
                "queue/run_01",
                (
                    "Run 01",
                    "Mavi\n",
                    str(secret_dir),
                    str(output_dir),
                    "official_brand_size_guide only",
                    "http://browser-runtime:8931/mcp",
                ),
            ),
        ),
        ("workflow_id_exit", "workflow/run_01"),
        ("get_result", None),
    ]


def test_entrypoint_accepts_explicit_sqlite_system_database(monkeypatch: object) -> None:
    """Accept SQLite only when it is configured explicitly."""
    monkeypatch.setenv("DBOS_SYSTEM_DATABASE_URL", "sqlite:///tmp/brand_size_chart.sqlite")

    assert runtime_config.system_database_url_get() == "sqlite:///tmp/brand_size_chart.sqlite"


def test_entrypoint_rejects_hidden_sqlite_system_database_fallback(monkeypatch: object, tmp_path: Path) -> None:
    """Reject hidden DBOS SQLite fallback by requiring an explicit system database URL."""
    brand_list_path = tmp_path / "brand_list.txt"
    brand_list_path.write_text("Mavi\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    secret_dir = tmp_path / "secret"
    monkeypatch.delenv("DBOS_SYSTEM_DATABASE_URL", raising=False)
    monkeypatch.setattr(
        runtime_config,
        "args_parse",
        lambda: argparse.Namespace(
            brand_list=brand_list_path,
            browser_runtime_mcp_url="http://browser-runtime:8931/mcp",
            input_secret=None,
            output_dir=output_dir,
            secret=str(secret_dir),
            workflow_git_url="git@github.com:antonov-andrey/brand-size-chart.git",
            workflow_run_id="Run 01",
            workflow_run_prompt="",
        ),
    )

    with pytest.raises(RuntimeError, match="DBOS_SYSTEM_DATABASE_URL"):
        entrypoint.main()


def test_entrypoint_rejects_missing_browser_runtime_mcp_url(monkeypatch: object, tmp_path: Path) -> None:
    """Require an externally managed browser runtime MCP URL."""
    brand_list_path = tmp_path / "brand_list.txt"
    brand_list_path.write_text("Mavi\n", encoding="utf-8")
    monkeypatch.setattr(
        runtime_config,
        "args_parse",
        lambda: argparse.Namespace(
            brand_list=brand_list_path,
            browser_runtime_mcp_url="",
            input_secret=None,
            output_dir=tmp_path / "out",
            secret=str(tmp_path / "secret"),
            workflow_git_url="git@github.com:antonov-andrey/brand-size-chart.git",
            workflow_run_id="Run 01",
            workflow_run_prompt="",
        ),
    )

    with pytest.raises(RuntimeError, match="BROWSER_RUNTIME_MCP_URL"):
        entrypoint.main()


def test_entrypoint_parser_has_no_dry_run_flag(monkeypatch: object) -> None:
    """Expose exactly one production runtime path without a dry-run switch."""
    assert "--dry-run" not in Path("brand_size_chart/app/runtime_config.py").read_text(encoding="utf-8")


def test_entrypoint_parser_uses_project_secret_by_default(monkeypatch: object, tmp_path: Path) -> None:
    """Use the project-local `.secret` directory as the default runtime DataSource."""
    brand_list_path = tmp_path / "brand_list.txt"
    brand_list_path.write_text("Defacto\n", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "brand-size-chart-run",
            "--workflow-run-id",
            "local",
            "--brand-list",
            str(brand_list_path),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    args = runtime_config.args_parse()

    assert args.secret == Path(".secret")


def test_entrypoint_materializes_input_secret_before_workflow_start(
    monkeypatch: object,
    tmp_path: Path,
) -> None:
    """Copy read-only input secret into pod-local runtime secret before DBOS starts."""
    brand_list_path = tmp_path / "brand_list.txt"
    brand_list_path.write_text("Mavi\n", encoding="utf-8")
    input_secret_path = tmp_path / "input" / ".secret"
    input_codex_profile_path = input_secret_path / "codex_profile"
    input_codex_profile_path.mkdir(parents=True)
    (input_codex_profile_path / "auth.json").write_text('{"tokens": {"access_token": "token"}}\n', encoding="utf-8")
    runtime_secret_path = tmp_path / "runtime" / ".secret"
    event_list: list[tuple[str, object]] = []
    _FakeDBOS.event_list = event_list
    _FakeSetWorkflowID.event_list = event_list

    monkeypatch.setattr(entrypoint, "DBOS", _FakeDBOS)
    monkeypatch.setattr(entrypoint, "SetWorkflowID", _FakeSetWorkflowID)
    monkeypatch.setattr(
        runtime_config,
        "args_parse",
        lambda: argparse.Namespace(
            brand_list=brand_list_path,
            browser_runtime_mcp_url="http://browser-runtime:8931/mcp",
            input_secret=input_secret_path,
            output_dir=tmp_path / "out",
            secret=runtime_secret_path,
            workflow_git_url="git@github.com:antonov-andrey/brand-size-chart.git",
            workflow_run_id="Run 01",
            workflow_run_prompt="",
        ),
    )
    monkeypatch.setenv("DBOS_SYSTEM_DATABASE_URL", "sqlite:////runtime/dbos.sqlite")

    entrypoint.main()

    assert (runtime_secret_path / "codex_profile" / "auth.json").read_text(encoding="utf-8") == (
        input_codex_profile_path / "auth.json"
    ).read_text(encoding="utf-8")
    assert os.environ["CODEX_HOME"] == str(runtime_secret_path / "codex_profile")
    assert event_list[5] == (
        "enqueue_workflow",
        (
            "queue/run_01",
            (
                "Run 01",
                "Mavi\n",
                str(runtime_secret_path),
                str(tmp_path / "out"),
                "",
                "http://browser-runtime:8931/mcp",
            ),
        ),
    )
