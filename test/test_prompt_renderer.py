"""Tests for strict prompt template rendering."""

from pathlib import Path

import pytest
from jinja2 import UndefinedError
from pydantic import BaseModel

from brand_size_chart.model import PromptScope
from brand_size_chart.model import StageVerification
from brand_size_chart.prompt.renderer import PromptRenderer
from brand_size_chart.stage import semantic
from brand_size_chart.stage.semantic import SemanticStage


def test_prompt_renderer_uses_strict_undefined_variables() -> None:
    """Fail prompt rendering when a template variable is missing."""
    renderer = PromptRenderer()

    with pytest.raises(UndefinedError):
        renderer.render("source_discover.md.j2", {})


def test_source_discover_template_includes_stage_runtime_context() -> None:
    """Render source discovery prompts from full templates and shared partial contracts."""
    prompt_text = PromptRenderer().render(
        "source_discover.md.j2",
        {
            "attempt_index": 2,
            "draft_result_json_text": '{"draft":"result"}',
            "feedback_list": ["retry feedback"],
            "previous_result_json_text": '{"previous":"result"}',
            "prompt_context": "Brand: Defacto\nSource type: official_brand_size_guide",
            "shared_instruction": "shared instruction text",
            "stage_instruction_text": "- stage-specific instruction",
            "stage_key": "source_discover",
        },
    )

    assert "Stage: source_discover" in prompt_text
    assert "Attempt: 2" in prompt_text
    assert "shared instruction text" in prompt_text
    assert "stage-specific instruction" in prompt_text
    assert "retry feedback" in prompt_text
    assert '{"previous":"result"}' in prompt_text
    assert '{"draft":"result"}' in prompt_text
    assert "Brand: Defacto" in prompt_text
    assert "Source type: official_brand_size_guide" in prompt_text
    assert "A `size_group_key` is a stable table identifier" in prompt_text


def test_semantic_stage_reuses_one_prompt_renderer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Reuse one prompt renderer for main and verification prompts in one stage run."""
    renderer_instance_list: list[object] = []

    class FakePromptRenderer:
        """Fake renderer that records instance construction."""

        def __init__(self) -> None:
            """Record one renderer instance."""

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
        allow_user_config: bool,
        browser_runtime_mcp_url: str,
        model_class: type[BaseModel],
        prompt_text: str,
        result_dir: Path,
        stage_dir: Path,
        stage_name: str,
    ) -> BaseModel:
        """Return successful fake stage outputs.

        Args:
            allow_user_config: Whether browser config is enabled.
            browser_runtime_mcp_url: Browser MCP URL.
            model_class: Expected result model.
            prompt_text: Rendered prompt text.
            result_dir: Result root.
            stage_dir: Stage artifact directory.
            stage_name: Stage name.

        Returns:
            Fake stage result.
        """

        _ = allow_user_config
        _ = browser_runtime_mcp_url
        _ = prompt_text
        _ = result_dir
        _ = stage_dir
        if model_class is StageVerification:
            return StageVerification(message="verified", stage_key=stage_name, status="success")
        return PromptScope()

    monkeypatch.setattr(semantic, "PromptRenderer", FakePromptRenderer)

    SemanticStage(
        codex_stage_run_callable=fake_codex_stage_run,
        prompt_name="source_discover",
        prompt_scope=PromptScope(),
        result_dir=tmp_path,
        stage_dir=tmp_path / "stage",
        stage_key="source_discover",
    ).run(draft_result=PromptScope(), model_class=PromptScope, prompt_context="Brand: Defacto")

    assert len(renderer_instance_list) == 1
