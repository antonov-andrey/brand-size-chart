"""Tests for DBOS entrypoint bootstrap with one complete input file."""

import argparse
import json
import os
from pathlib import Path

import pytest

from brand_size_chart.app import entrypoint, runtime_config
from brand_size_chart.model import RunResult


class _WorkflowHandle:
    """Return one successful root workflow result."""

    def get_result(self) -> RunResult:
        """Return the fixed successful result."""

        return RunResult(
            brand_list_parse_warning_list=[], brand_result_list=[], error_list=[], status="success", warning_list=[]
        )


class _FailedWorkflowHandle:
    """Return one failed root workflow result."""

    def get_result(self) -> RunResult:
        """Return the fixed failed result."""

        return RunResult(
            brand_list_parse_warning_list=[],
            brand_result_list=[],
            error_list=["root failure"],
            status="failed",
            warning_list=[],
        )


class _DBOS:
    """Record only the DBOS entrypoint arguments relevant to the public input."""

    enqueue_args: tuple[object, ...]
    event_list: list[tuple[str, object]] = []

    def __init__(self, *, config: dict[str, object]) -> None:
        """Accept DBOS configuration."""

        self.event_list.append(("configure", config))

    @classmethod
    def enqueue_workflow(cls, queue_name: str, function: object, *args: object) -> _WorkflowHandle:
        """Record root workflow arguments."""

        _ = queue_name
        _ = function
        cls.event_list.append(("enqueue", queue_name))
        cls.enqueue_args = args
        return _WorkflowHandle()

    @classmethod
    def launch(cls) -> None:
        """Accept launch."""

        cls.event_list.append(("launch", None))

    @classmethod
    def listen_queues(cls, queue_name_list: list[str]) -> None:
        """Accept queue listeners."""

        cls.event_list.append(("listen", queue_name_list))

    @classmethod
    def register_queue(cls, queue_name: str, *, worker_concurrency: int) -> None:
        """Accept queue registration."""

        cls.event_list.append(("register", (queue_name, worker_concurrency)))


class _SetWorkflowID:
    """No-op workflow-id context manager."""

    def __init__(self, workflow_id: str) -> None:
        """Accept the generated workflow id."""

    def __enter__(self) -> None:
        """Enter the no-op context."""

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        """Exit the no-op context."""


def test_entrypoint_loads_complete_typed_input(monkeypatch: object, tmp_path: Path) -> None:
    """Parse the exact root input from ``--input`` before enqueueing DBOS work."""

    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(_input_payload_get()), encoding="utf-8")
    monkeypatch.setattr(entrypoint, "DBOS", _DBOS)
    monkeypatch.setattr(entrypoint, "SetWorkflowID", _SetWorkflowID)
    monkeypatch.setattr(
        entrypoint,
        "BrandSizeChartApplication",
        lambda: type("App", (), {"root_workflow": type("R", (), {"run": object()})()})(),
    )
    monkeypatch.setattr(
        runtime_config,
        "args_parse",
        lambda: argparse.Namespace(
            browser_runtime_mcp_url="http://browser:8931/mcp",
            input=input_path,
            input_secret=None,
            output_dir=tmp_path / "out",
            secret=tmp_path / "secret",
            workflow_git_url="",
            workflow_run_id="local",
        ),
    )
    monkeypatch.setenv("DBOS_SYSTEM_DATABASE_URL", "sqlite:///tmp/dbos.sqlite")

    assert entrypoint.main() == 0
    assert _DBOS.enqueue_args[1].model_dump() == _input_payload_get()


def test_entrypoint_bootstraps_dbos_with_stable_ids_and_worker_concurrency(monkeypatch: object, tmp_path: Path) -> None:
    """Configure, listen, launch, register, and enqueue in the required order."""

    _DBOS.event_list = []
    _entrypoint_configure(monkeypatch, tmp_path)

    assert entrypoint.main() == 0
    assert [event[0] for event in _DBOS.event_list] == ["configure", "listen", "launch", "register", "enqueue"]
    assert _DBOS.event_list[3] == ("register", ("queue/local", 4))
    assert _DBOS.enqueue_args[1].model_dump() == _input_payload_get()


def test_entrypoint_returns_failed_exit_code_for_failed_root_result(monkeypatch: object, tmp_path: Path) -> None:
    """Return a failed process status when the root workflow is failed."""

    class FailedDBOS(_DBOS):
        """Return the failed root result after normal enqueueing."""

        @classmethod
        def enqueue_workflow(cls, queue_name: str, function: object, *args: object) -> _FailedWorkflowHandle:
            """Record enqueue and return a failed handle."""

            _ = function
            cls.enqueue_args = args
            cls.event_list.append(("enqueue", queue_name))
            return _FailedWorkflowHandle()

    _entrypoint_configure(monkeypatch, tmp_path, dbos_class=FailedDBOS)
    assert entrypoint.main() == 1


def test_entrypoint_accepts_explicit_sqlite_system_database(monkeypatch: object) -> None:
    """Accept SQLite only when it is explicitly configured."""

    monkeypatch.setenv("DBOS_SYSTEM_DATABASE_URL", "sqlite:///tmp/brand_size_chart.sqlite")
    assert runtime_config.system_database_url_get() == "sqlite:///tmp/brand_size_chart.sqlite"


def test_entrypoint_rejects_hidden_sqlite_system_database_fallback(monkeypatch: object) -> None:
    """Require explicit DBOS system-database configuration."""

    monkeypatch.delenv("DBOS_SYSTEM_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DBOS_SYSTEM_DATABASE_URL"):
        runtime_config.system_database_url_get()


def test_entrypoint_rejects_missing_browser_runtime_mcp_url(monkeypatch: object, tmp_path: Path) -> None:
    """Reject the launch before DBOS setup when browser runtime is absent."""

    _entrypoint_configure(monkeypatch, tmp_path, browser_runtime_mcp_url="")
    with pytest.raises(RuntimeError, match="BROWSER_RUNTIME_MCP_URL"):
        entrypoint.main()


def test_entrypoint_parser_rejects_dry_run_flag(monkeypatch: object, tmp_path: Path) -> None:
    """Keep the current CLI free of the deleted dry-run bridge."""

    monkeypatch.setattr(
        "sys.argv",
        [
            "brand-size-chart-run",
            "--workflow-run-id",
            "local",
            "--input",
            str(tmp_path / "input.json"),
            "--output-dir",
            str(tmp_path / "out"),
            "--dry-run",
        ],
    )
    with pytest.raises(SystemExit):
        runtime_config.args_parse()


def test_entrypoint_parser_uses_project_secret_by_default(monkeypatch: object, tmp_path: Path) -> None:
    """Keep `.secret` as the default runtime secret directory."""

    monkeypatch.setattr(
        "sys.argv",
        [
            "brand-size-chart-run",
            "--workflow-run-id",
            "local",
            "--input",
            str(tmp_path / "input.json"),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    assert runtime_config.args_parse().secret == Path(".secret")


def test_entrypoint_materializes_input_secret_before_workflow_start(monkeypatch: object, tmp_path: Path) -> None:
    """Copy a read-only input secret into the writable runtime-secret boundary."""

    input_secret = tmp_path / "input" / ".secret"
    (input_secret / "codex_profile").mkdir(parents=True)
    (input_secret / "codex_profile" / "auth.json").write_text("{}", encoding="utf-8")
    runtime_secret = tmp_path / "runtime" / ".secret"
    _entrypoint_configure(monkeypatch, tmp_path, input_secret=input_secret, secret=runtime_secret)

    assert entrypoint.main() == 0
    assert (runtime_secret / "codex_profile" / "auth.json").read_text(encoding="utf-8") == "{}"
    assert os.environ["CODEX_HOME"] == str(runtime_secret / "codex_profile")


def _entrypoint_configure(
    monkeypatch: object,
    tmp_path: Path,
    *,
    browser_runtime_mcp_url: str = "http://browser:8931/mcp",
    dbos_class: type[_DBOS] = _DBOS,
    input_secret: Path | None = None,
    secret: Path | None = None,
) -> None:
    """Install one complete current CLI configuration and DBOS doubles."""

    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(_input_payload_get()), encoding="utf-8")
    monkeypatch.setattr(entrypoint, "DBOS", dbos_class)
    monkeypatch.setattr(entrypoint, "SetWorkflowID", _SetWorkflowID)
    monkeypatch.setattr(
        entrypoint,
        "BrandSizeChartApplication",
        lambda: type("App", (), {"root_workflow": type("R", (), {"run": object()})()})(),
    )
    monkeypatch.setattr(
        runtime_config,
        "args_parse",
        lambda: argparse.Namespace(
            browser_runtime_mcp_url=browser_runtime_mcp_url,
            input=input_path,
            input_secret=input_secret,
            output_dir=tmp_path / "out",
            secret=secret or tmp_path / "secret",
            workflow_git_url="",
            workflow_run_id="local",
        ),
    )
    monkeypatch.setenv("DBOS_SYSTEM_DATABASE_URL", "sqlite:///tmp/dbos.sqlite")


def _input_payload_get() -> dict[str, object]:
    """Build one complete input document accepted by the entrypoint."""

    return {
        "request": {
            "brand_list_text": "Brand\\n",
            "priority_country_code": "TR",
            "product_type_request_list": [],
            "source_type_allow_list": [],
        },
        "config": {
            "instruction": "",
            "step_map": {
                step_key: (
                    {
                        "concurrency": 1,
                        "correction_attempt_limit": 1,
                        "instruction": "",
                        "model": "gpt-5.6-terra",
                        "reasoning_effort": "high",
                    }
                    if step_key == "source_discover"
                    else {
                        "correction_attempt_limit": 1,
                        "instruction": "",
                        "model": "gpt-5.6-terra",
                        "reasoning_effort": "high",
                    }
                )
                for step_key in ["source_discover", "coverage_decide", "canonical_select"]
            },
        },
    }
