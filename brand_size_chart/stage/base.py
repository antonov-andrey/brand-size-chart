"""Shared contracts for semantic workflow stages."""

from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import TypeVar

from pydantic import BaseModel

MAX_STAGE_ATTEMPT_COUNT = 3
PROMPT_TEMPLATE_NAME_BY_STAGE_KEY_MAP = MappingProxyType(
    {
        "canonical_select": "canonical_select.md.j2",
        "canonical_selection": "canonical_select.md.j2",
        "coverage_decide": "coverage_decide.md.j2",
        "coverage_decision": "coverage_decide.md.j2",
        "source_discover": "source_discover.md.j2",
        "source_discovery": "source_discover.md.j2",
        "table_extract": "table_extract.md.j2",
        "workflow_run_prompt_apply": "workflow_run_prompt_apply.md.j2",
    }
)
PROMPT_TEMPLATE_NAME_BY_STAGE_PROMPT_MAP = MappingProxyType(
    {
        "apply": "workflow_run_prompt_apply.md.j2",
        "canonical_select": "canonical_select.md.j2",
        "coverage_decide": "coverage_decide.md.j2",
        "discovery": "source_discover.md.j2",
        "selection": "canonical_select.md.j2",
        "source_discover": "source_discover.md.j2",
        "table_extract": "table_extract.md.j2",
    }
)
VERIFY_TEMPLATE_NAME_BY_STAGE_KEY_MAP = MappingProxyType(
    {
        "canonical_select": "canonical_select_verify.md.j2",
        "canonical_selection": "canonical_select_verify.md.j2",
        "coverage_decide": "coverage_decide_verify.md.j2",
        "coverage_decision": "coverage_decide_verify.md.j2",
        "source_discover": "source_discover_verify.md.j2",
        "source_discovery": "source_discover_verify.md.j2",
        "table_extract": "table_extract_verify.md.j2",
        "workflow_run_prompt_apply": "workflow_run_prompt_apply_verify.md.j2",
    }
)
SIZE_GROUP_KEY_PROMPT_NAME_SET = {
    "discovery",
    "selection",
    "verification",
}
CodexStageRun = Callable[..., BaseModel]
_ResultModelT = TypeVar("_ResultModelT", bound=BaseModel)
ResultErrorListGet = Callable[[_ResultModelT], list[str]]


def prompt_template_name_get(*, prompt_name: str, stage_key: str) -> str:
    """Return the main prompt template name for one stage.

    Args:
        prompt_name: Existing prompt name or new template stem.
        stage_key: Existing or new stage key.

    Returns:
        Prompt template file name.
    """

    return PROMPT_TEMPLATE_NAME_BY_STAGE_KEY_MAP.get(
        stage_key,
        PROMPT_TEMPLATE_NAME_BY_STAGE_PROMPT_MAP.get(prompt_name, f"{prompt_name}.md.j2"),
    )


def verify_prompt_template_name_get(stage_key: str) -> str:
    """Return the verification prompt template name for one stage.

    Args:
        stage_key: Existing or new stage key.

    Returns:
        Verification prompt template file name.
    """

    return VERIFY_TEMPLATE_NAME_BY_STAGE_KEY_MAP.get(stage_key, f"{stage_key}_verify.md.j2")


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
