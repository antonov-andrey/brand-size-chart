"""Behavior contracts for the workflow container image."""

from pathlib import Path


def test_workflow_image_installs_codex_cli_release_required_by_selected_model() -> None:
    """Keep the image Codex CLI compatible with the configured model."""

    dockerfile_text = (Path(__file__).resolve().parents[1] / "docker/workflow/Dockerfile").read_text(encoding="utf-8")

    assert "@openai/codex@0.144.1" in dockerfile_text
