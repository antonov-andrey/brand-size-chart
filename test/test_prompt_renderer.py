"""Tests for strict prompt template rendering."""

import pytest
from jinja2 import UndefinedError

from brand_size_chart.prompt.renderer import PromptRenderer


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
