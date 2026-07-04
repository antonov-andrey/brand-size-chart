"""Shared contracts for semantic workflow stages."""

from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel

MAX_STAGE_ATTEMPT_COUNT = 3
STAGE_KEY_SET = frozenset(
    {
        "canonical_select",
        "coverage_decide",
        "source_discover",
        "table_extract",
        "workflow_run_prompt_apply",
    }
)
CodexStageRun = Callable[..., BaseModel]
_ResultModelT = TypeVar("_ResultModelT", bound=BaseModel)
ResultErrorListGet = Callable[[_ResultModelT], list[str]]


def prompt_template_name_get(stage_key: str) -> str:
    """Return the main prompt template name for one stage.

    Args:
        stage_key: Existing or new stage key.

    Returns:
        Prompt template file name.
    """

    return f"{stage_key}.md.j2"


def verify_prompt_template_name_get(stage_key: str) -> str:
    """Return the verification prompt template name for one stage.

    Args:
        stage_key: Existing or new stage key.

    Returns:
        Verification prompt template file name.
    """

    return f"{stage_key}_verify.md.j2"
