"""Tests for strict prompt template rendering."""

from pathlib import Path

import pytest
from jinja2 import UndefinedError

from workflow_container_runtime.prompt import PromptRenderer

PROJECT_TEMPLATE_DIR = Path("brand_size_chart/prompt/template")


def test_prompt_renderer_uses_strict_undefined_variables() -> None:
    """Fail prompt rendering when a template variable is missing."""
    renderer = PromptRenderer(template_dir=PROJECT_TEMPLATE_DIR)

    with pytest.raises(UndefinedError):
        renderer.render("source_discover.md.j2", {})


def test_project_prompt_renderer_has_no_project_wrapper() -> None:
    """Use runtime prompt renderer directly with the project template directory."""

    assert not Path("brand_size_chart/prompt/renderer.py").exists()
