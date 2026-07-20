"""Tests for standard platform bootstrap of the DBOS application entrypoint."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from workflow_container_contract import WorkflowDefinition
from workflow_container_runtime import WorkflowControlClient, WorkflowControlRequestBuilder
from workflow_container_runtime.mcp_playwright_profile import McpPlaywrightProfileRuntime

from brand_size_chart.app import entrypoint, runtime_config
from brand_size_chart.app.application import BrandSizeChartApplication
from brand_size_chart.model import RunResult

_WORKFLOW_RUN_ID = "20260719123456789"


class WorkflowHandleStub:
    """Return one fixed root workflow result."""

    def __init__(self, *, workflow_result: RunResult) -> None:
        """Store the fixed result.

        Args:
            workflow_result: Result returned by `get_result`.
        """

        self._workflow_result = workflow_result

    def get_result(self) -> RunResult:
        """Return the fixed root result.

        Returns:
            Stored workflow result.
        """

        return self._workflow_result


class DBOSStub:
    """Record DBOS bootstrap and root workflow arguments."""

    enqueue_args: tuple[object, ...]
    event_list: list[tuple[str, object]] = []
    workflow_result = RunResult(brand_result_list=[], error_list=[], status="success", warning_list=[])

    def __init__(self, *, config: dict[str, object]) -> None:
        """Record DBOS configuration.

        Args:
            config: Complete DBOS application config.
        """

        self.event_list.append(("configure", config))

    @classmethod
    def enqueue_workflow(cls, queue_name: str, function: object, *args: object) -> WorkflowHandleStub:
        """Record root workflow arguments and return the configured result.

        Args:
            queue_name: Registered queue name.
            function: Root workflow callable.
            *args: Root workflow arguments.

        Returns:
            Fixed workflow handle.
        """

        _ = function
        cls.event_list.append(("enqueue", queue_name))
        cls.enqueue_args = args
        return WorkflowHandleStub(workflow_result=cls.workflow_result)

    @classmethod
    def launch(cls) -> None:
        """Record DBOS launch."""

        cls.event_list.append(("launch", None))

    @classmethod
    def listen_queues(cls, queue_name_list: list[str]) -> None:
        """Record queue listener selection.

        Args:
            queue_name_list: Queue names listened before launch.
        """

        cls.event_list.append(("listen", queue_name_list))

    @classmethod
    def register_queue(cls, queue_name: str, *, worker_concurrency: int) -> None:
        """Record queue registration.

        Args:
            queue_name: Registered queue name.
            worker_concurrency: Configured worker concurrency.
        """

        cls.event_list.append(("register", (queue_name, worker_concurrency)))


class SetWorkflowIDStub:
    """Provide a no-op workflow-id context manager."""

    def __init__(self, workflow_id: str) -> None:
        """Accept the generated workflow id.

        Args:
            workflow_id: Stable root workflow id.
        """

        _ = workflow_id

    def __enter__(self) -> None:
        """Enter the no-op context."""

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        """Exit the no-op context."""


class WorkflowControlClientStub:
    """Record registration through the standard control boundary."""

    def registration_send(self, *, workflow_run_id: str) -> None:
        """Record registration before DBOS setup.

        Args:
            workflow_run_id: Exact platform run identity.
        """

        DBOSStub.event_list.append(("registration", workflow_run_id))


def test_entrypoint_loads_complete_typed_input_from_platform_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Parse the exact immutable input before enqueueing root DBOS work."""

    _entrypoint_configure(monkeypatch, tmp_path)

    assert entrypoint.main() == 0
    assert DBOSStub.enqueue_args[1].model_dump(mode="json") == _input_payload_get()


def test_entrypoint_registers_then_bootstraps_dbos_in_required_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Register, configure, listen, launch, register the queue, and enqueue in exact order."""

    _entrypoint_configure(monkeypatch, tmp_path)

    assert entrypoint.main() == 0
    assert [event[0] for event in DBOSStub.event_list] == [
        "registration",
        "configure",
        "listen",
        "launch",
        "register",
        "enqueue",
    ]
    assert DBOSStub.event_list[0] == ("registration", _WORKFLOW_RUN_ID)
    assert DBOSStub.event_list[4] == ("register", (f"queue/{_WORKFLOW_RUN_ID}", 4))


def test_application_injects_one_profile_runtime_into_every_codex_step(tmp_path: Path) -> None:
    """Share one run-local profile lease and candidate-staging owner across all Codex steps."""

    application = BrandSizeChartApplication(
        control_client=WorkflowControlClient(control_url="http://control/v2"),
        control_request_builder=WorkflowControlRequestBuilder(
            workflow_definition=WorkflowDefinition.from_path(Path("workflow.yaml"))
        ),
    )
    brand_workflow = application.root_workflow._brand_workflow
    profile_runtime_list = [
        brand_workflow._source_discovery_step._mcp_playwright_profile_runtime,
        brand_workflow._coverage_decision_step._mcp_playwright_profile_runtime,
        brand_workflow._canonical_selection_step._mcp_playwright_profile_runtime,
    ]

    assert all(isinstance(profile_runtime, McpPlaywrightProfileRuntime) for profile_runtime in profile_runtime_list)
    assert len({id(profile_runtime) for profile_runtime in profile_runtime_list}) == 1


def test_entrypoint_builds_exact_browser_runtime_capability(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Pass only the immutable image-visible capability config into browser-backed steps."""

    _entrypoint_configure(monkeypatch, tmp_path)

    assert entrypoint.main() == 0
    assert DBOSStub.enqueue_args[0].runtime_capability.browser.model_dump() == {
        "mcp_playwright_profile_source": "source",
        "mcp_playwright_profile_writeback_candidate_url": "http://playwright:8931/candidate",
        "mcp_url": "http://playwright:8931/mcp",
    }
    assert DBOSStub.enqueue_args[0].run_context.workflow_run_id == _WORKFLOW_RUN_ID
    assert DBOSStub.enqueue_args[0].data_path.result_path == tmp_path / "result"
    assert DBOSStub.enqueue_args[0].data_path.workspace_path == tmp_path / "workspace"
    assert DBOSStub.enqueue_args[0].result_dir == tmp_path / "runtime" / "result"


def test_entrypoint_returns_zero_after_domain_failed_final_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Use normal process exit after the root workflow has already sent final intent."""

    _entrypoint_configure(monkeypatch, tmp_path)
    DBOSStub.workflow_result = RunResult(
        brand_result_list=[],
        error_list=["root failure"],
        status="failed",
        warning_list=[],
    )

    assert entrypoint.main() == 0


def test_entrypoint_uses_runtime_local_sqlite_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep package-specific DBOS persistence inside the standard private runtime root."""

    monkeypatch.delenv("DBOS_SYSTEM_DATABASE_URL", raising=False)

    assert runtime_config.system_database_url_get(Path("/runtime")) == "sqlite:////runtime/dbos.sqlite3"


def test_entrypoint_accepts_explicit_system_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow an implementation-specific explicit DBOS database override."""

    monkeypatch.setenv("DBOS_SYSTEM_DATABASE_URL", "sqlite:////runtime/explicit.sqlite3")

    assert runtime_config.system_database_url_get(Path("/runtime")) == "sqlite:////runtime/explicit.sqlite3"


def test_entrypoint_rejects_missing_browser_runtime_after_registration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Reject domain execution when the declared browser capability payload is absent."""

    _entrypoint_configure(monkeypatch, tmp_path, capability_payload={})

    with pytest.raises(RuntimeError, match="browser_vpn_runtime"):
        entrypoint.main()
    assert DBOSStub.event_list == [("registration", _WORKFLOW_RUN_ID)]


def test_entrypoint_ignores_legacy_process_arguments(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Use only the source-owned command and standard environment without a CLI bridge."""

    _entrypoint_configure(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", ["brand-size-chart-run", "--legacy-argument"])

    assert entrypoint.main() == 0


def test_entrypoint_materializes_only_codex_secret_in_temporary_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Keep the writable Codex copy outside the accepted runtime checkpoint."""

    _entrypoint_configure(monkeypatch, tmp_path)
    input_secret_path = runtime_config.INPUT_CODEX_PROFILE_PATH
    runtime_path = Path(os.environ["WORKFLOW_RUNTIME_PATH"])
    temporary_secret_path = runtime_config.TEMPORARY_PATH / "codex_profile"

    assert entrypoint.main() == 0
    assert (temporary_secret_path / "auth.json").read_text(encoding="utf-8") == "{}"
    (temporary_secret_path / "attempt-local-state.json").write_text("{}", encoding="utf-8")

    assert entrypoint.main() == 0
    assert not (temporary_secret_path / "attempt-local-state.json").exists()
    assert input_secret_path.is_dir()
    assert not (runtime_path / ".secret").exists()
    assert os.environ["CODEX_HOME"] == str(temporary_secret_path)
    assert os.environ["HOME"] == str(runtime_config.TEMPORARY_PATH / "home")
    assert os.environ["TMPDIR"] == str(runtime_config.TEMPORARY_PATH / "process")


def _entrypoint_configure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    capability_payload: dict[str, object] | None = None,
) -> None:
    """Install one complete standard platform environment and runtime doubles.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path: Isolated test root.
        capability_payload: Optional exact capability document override.
    """

    DBOSStub.event_list = []
    DBOSStub.workflow_result = RunResult(brand_result_list=[], error_list=[], status="success", warning_list=[])
    input_path = tmp_path / "input" / "input.json"
    capability_path = tmp_path / "input" / "capability.json"
    input_secret_path = tmp_path / "input" / ".secret"
    result_path = tmp_path / "result"
    runtime_path = tmp_path / "runtime"
    run_context_path = tmp_path / "input" / "run-context.json"
    workspace_path = tmp_path / "workspace"
    (input_secret_path / "codex_profile").mkdir(parents=True)
    (input_secret_path / "codex_profile" / "auth.json").write_text("{}", encoding="utf-8")
    input_path.write_text(json.dumps(_input_payload_get()), encoding="utf-8")
    run_context_path.write_text(
        json.dumps(
            {
                "interface_major_version": 2,
                "version": 1,
                "workflow_id": "workflow-id",
                "workflow_name": "brand_size_chart_defacto",
                "workflow_run_id": _WORKFLOW_RUN_ID,
                "workflow_run_timestamp": "2026-07-19T12:34:56.789Z",
                "workflow_source_id": "source-id",
                "workflow_source_version_id": "source-version-id",
            }
        ),
        encoding="utf-8",
    )
    capability_path.write_text(
        json.dumps(
            capability_payload
            if capability_payload is not None
            else {
                "browser_vpn_runtime": {
                    "browser": {
                        "mcp_playwright_profile_source": "source",
                        "mcp_playwright_profile_writeback_candidate_url": "http://playwright:8931/candidate",
                        "mcp_url": "http://playwright:8931/mcp",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(entrypoint, "DBOS", DBOSStub)
    monkeypatch.setattr(entrypoint, "SetWorkflowID", SetWorkflowIDStub)
    monkeypatch.setattr(entrypoint, "WorkflowControlClient", lambda **kwargs: WorkflowControlClientStub())
    monkeypatch.setattr(
        entrypoint,
        "BrandSizeChartApplication",
        lambda **kwargs: type("App", (), {"root_workflow": type("Root", (), {"run": object()})()})(),
    )
    monkeypatch.setattr(runtime_config, "INPUT_CODEX_PROFILE_PATH", input_secret_path / "codex_profile")
    monkeypatch.setattr(runtime_config, "RESULT_PATH", result_path)
    monkeypatch.setattr(runtime_config, "TEMPORARY_PATH", tmp_path / "temporary")
    monkeypatch.setattr(runtime_config, "WORKFLOW_DEFINITION_PATH", Path("workflow.yaml").resolve())
    monkeypatch.setattr(runtime_config, "WORKSPACE_PATH", workspace_path)
    monkeypatch.setenv("DBOS_SYSTEM_DATABASE_URL", f"sqlite:///{runtime_path / 'dbos.sqlite3'}")
    monkeypatch.setenv("WORKFLOW_CAPABILITY_CONFIG_PATH", str(capability_path))
    monkeypatch.setenv("WORKFLOW_CONTROL_URL", "http://control/v2")
    monkeypatch.setenv("WORKFLOW_INPUT_PATH", str(input_path))
    monkeypatch.setenv("WORKFLOW_RUN_CONTEXT_PATH", str(run_context_path))
    monkeypatch.setenv("WORKFLOW_RUN_ID", _WORKFLOW_RUN_ID)
    monkeypatch.setenv("WORKFLOW_RUNTIME_PATH", str(runtime_path))


def _input_payload_get() -> dict[str, object]:
    """Build one complete input document accepted by the entrypoint.

    Returns:
        Complete public workflow input payload.
    """

    return {
        "request": {
            "brand_list": ["Brand"],
            "priority_country_code": "TR",
            "product_type_request_list": [],
            "source_type_allow_list": [],
        },
        "config": {
            "instruction": "",
            "mcp_playwright_profile_writeback_policy": {
                "mcp_playwright_profile_name_prefix": "",
                "workflow_run_status_list": ["done"],
            },
            "step_map": {
                step_key: (
                    {
                        "concurrency": 1,
                        "correction_attempt_limit": 1,
                        "instruction": "",
                        "mcp_playwright_profile": "source-discover",
                        "mcp_playwright_profile_source": None,
                        "model": "gpt-5.6-terra",
                        "reasoning_effort": "high",
                    }
                    if step_key == "source_discover"
                    else {
                        "correction_attempt_limit": 1,
                        "instruction": "",
                        "mcp_playwright_profile": None,
                        "mcp_playwright_profile_source": None,
                        "model": "gpt-5.6-terra",
                        "reasoning_effort": "high",
                    }
                )
                for step_key in ["source_discover", "coverage_decide", "canonical_select"]
            },
        },
    }
