"""Strict Jinja2 renderer for static prompt templates."""

from collections.abc import Mapping
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined


class PromptRenderer:
    """Render prompt templates from the project prompt template directory."""

    def __init__(self, template_dir: Path | None = None) -> None:
        """Create a strict prompt renderer.

        Args:
            template_dir: Optional template directory override.
        """

        self._environment = Environment(
            autoescape=False,
            loader=FileSystemLoader(template_dir or Path(__file__).parent / "template"),
            undefined=StrictUndefined,
        )

    def render(self, template_name: str, context: Mapping[str, object]) -> str:
        """Render one prompt template with strict undefined-variable handling.

        Args:
            template_name: Template file name relative to the prompt template directory.
            context: Template context values.

        Returns:
            Rendered prompt text.
        """

        return self._environment.get_template(template_name).render(**context)
