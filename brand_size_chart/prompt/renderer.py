"""Project prompt renderer backed by workflow-container runtime templates."""

from collections.abc import Mapping
from pathlib import Path

from workflow_container_runtime.prompt import PromptRenderer as RuntimePromptRenderer


class PromptRenderer(RuntimePromptRenderer):
    """Render project prompts with runtime-owned shared partials."""

    def __init__(self, template_dir: Path | None = None) -> None:
        """Create a strict prompt renderer.

        Args:
            template_dir: Optional template directory override.
        """

        super().__init__(template_dir=template_dir or Path(__file__).parent / "template")

    def render(self, template_name: str, context: Mapping[str, object]) -> str:
        """Render one prompt template with strict undefined-variable handling.

        Args:
            template_name: Template file name relative to the prompt template directory.
            context: Template context values.

        Returns:
            Rendered prompt text.
        """

        return super().render(template_name, context)
