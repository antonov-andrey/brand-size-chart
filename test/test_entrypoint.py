"""Tests for DBOS entrypoint bootstrap with one complete input file."""

import argparse
import json
from pathlib import Path

from brand_size_chart.app import entrypoint, runtime_config
from brand_size_chart.model import RunResult


class _WorkflowHandle:
    """Return one successful root workflow result."""

    def get_result(self) -> RunResult:
        """Return the fixed successful result."""

        return RunResult(
            brand_list_parse_warning_list=[], brand_result_list=[], error_list=[], status="success", warning_list=[]
        )


class _DBOS:
    """Record only the DBOS entrypoint arguments relevant to the public input."""

    enqueue_args: tuple[object, ...]

    def __init__(self, *, config: dict[str, object]) -> None:
        """Accept DBOS configuration."""

    @classmethod
    def enqueue_workflow(cls, queue_name: str, function: object, *args: object) -> _WorkflowHandle:
        """Record root workflow arguments."""

        _ = queue_name
        _ = function
        cls.enqueue_args = args
        return _WorkflowHandle()

    @classmethod
    def launch(cls) -> None:
        """Accept launch."""

    @classmethod
    def listen_queues(cls, queue_name_list: list[str]) -> None:
        """Accept queue listeners."""

    @classmethod
    def register_queue(cls, queue_name: str, *, worker_concurrency: int) -> None:
        """Accept queue registration."""


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
