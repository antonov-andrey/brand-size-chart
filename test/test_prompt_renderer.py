"""Tests for strict prompt template rendering."""

from pathlib import Path

import pytest
from jinja2 import UndefinedError
from pydantic import BaseModel

from brand_size_chart.model import PromptScope
from brand_size_chart.stage.base import VerifiedCodexStageConfig, VerifiedCodexStageRunner
from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.stage import StageVerificationResult

PROJECT_TEMPLATE_DIR = Path("brand_size_chart/prompt/template")


def test_prompt_renderer_uses_strict_undefined_variables() -> None:
    """Fail prompt rendering when a template variable is missing."""
    renderer = PromptRenderer(template_dir=PROJECT_TEMPLATE_DIR)

    with pytest.raises(UndefinedError):
        renderer.render("source_discover.md.j2", {})


def test_project_prompt_renderer_has_no_project_wrapper() -> None:
    """Use runtime prompt renderer directly with the project template directory."""

    assert not Path("brand_size_chart/prompt/renderer.py").exists()


def test_verified_stage_runner_reuses_one_prompt_renderer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Reuse one prompt renderer for action and verification prompts in one stage run."""
    renderer_instance_list: list[object] = []

    class FakePromptRenderer:
        """Fake renderer that records instance construction."""

        def __init__(self, template_dir: Path | None = None) -> None:
            """Record one renderer instance."""

            _ = template_dir
            renderer_instance_list.append(self)

        def render(self, template_name: str, context: dict[str, object]) -> str:
            """Return a minimal prompt and record template use.

            Args:
                template_name: Prompt template name.
                context: Prompt template context.

            Returns:
                Fake rendered prompt.
            """

            return f"{template_name}:{context['stage_key']}"

    def fake_codex_stage_run(
        *,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return successful fake stage outputs.

        Args:
            browser_runtime_mcp_url: Browser MCP URL.
            model_class: Expected result model.
            prompt_text: Rendered prompt text.
            result_dir: Result root.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake stage result.
        """
        _ = browser_runtime_mcp_url
        _ = prompt_text
        _ = result_dir
        _ = stage_dir
        if model_class is StageVerificationResult:
            return StageVerificationResult(status="success")
        return PromptScope()

    VerifiedCodexStageRunner(
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_renderer=FakePromptRenderer(),
    ).run(
        config=VerifiedCodexStageConfig(
            prompt_context=PromptScope(priority_country_code="TR"),
            result_dir=tmp_path,
            stage_dir=tmp_path / "stage",
            stage_key="source_discover",
        ),
        mechanical_validate=lambda result: None,
        model_class=PromptScope,
    )

    assert len(renderer_instance_list) == 1
