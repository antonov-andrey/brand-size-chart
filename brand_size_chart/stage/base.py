"""Shared contracts for semantic workflow stages."""

from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

MAX_STAGE_ATTEMPT_COUNT = 3
SIZE_GROUP_KEY_PROMPT_NAME_SET = {
    "discovery",
    "extraction",
    "selection",
    "verification",
}
CodexStageRun = Callable[..., BaseModel]
_ResultModelT = TypeVar("_ResultModelT", bound=BaseModel)
ResultErrorListGet = Callable[[_ResultModelT], list[str]]


def prompt_file_text_get(prompt_name: str) -> str:
    """Return one static prompt file.

    Args:
        prompt_name: Prompt file stem.

    Returns:
        Prompt text.
    """

    prompt_dir = Path(__file__).parents[1] / "prompt"
    prompt_text = (prompt_dir / f"{prompt_name}.md").read_text(encoding="utf-8")
    if prompt_name not in SIZE_GROUP_KEY_PROMPT_NAME_SET:
        return prompt_text
    return f"{(prompt_dir / 'size_group_key.md').read_text(encoding='utf-8')}\n\n{prompt_text}"
