"""Behavior contracts for the workflow container image."""

from pathlib import Path


def test_workflow_image_uses_platform_base_and_only_its_source_context() -> None:
    """Consume the shared runtime release without sibling build contexts."""

    dockerfile_text = (Path(__file__).resolve().parents[1] / "docker/workflow/Dockerfile").read_text(encoding="utf-8")

    assert "apwid-workflow-platform-base:0.5.3" in dockerfile_text
    assert "COPY . ." in dockerfile_text
    assert "workflow_container_contract" not in dockerfile_text
    assert "workflow_container_runtime" not in dockerfile_text
