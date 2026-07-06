"""Shared contracts for semantic workflow stages."""

from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from workflow_container_runtime.stage import VerifiedCodexStageConfig

from brand_size_chart.model import PromptScope

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


def prompt_template_name_get(stage_key: str) -> str:
    """Return the main prompt template name for one stage.

    Args:
        stage_key: Existing or new stage key.

    Returns:
        Prompt template file name.
    """

    return f"{stage_key}.md.j2"


def stage_instruction_text_get(*, prompt_scope: PromptScope | None, stage_key: str) -> str:
    """Return bullet-form stage instructions from the prompt scope.

    Args:
        prompt_scope: Parsed workflow-run prompt scope.
        stage_key: Current stage key.

    Returns:
        Bullet-form stage instruction text.
    """

    stage_instruction_list = [
        stage_instruction.instruction
        for stage_instruction in (prompt_scope.stage_instruction_list if prompt_scope else [])
        if stage_instruction.stage_key == stage_key
    ]
    return "\n".join(f"- {stage_instruction}" for stage_instruction in stage_instruction_list)


def verify_prompt_template_name_get(stage_key: str) -> str:
    """Return the verification prompt template name for one stage.

    Args:
        stage_key: Existing or new stage key.

    Returns:
        Verification prompt template file name.
    """

    return f"{stage_key}_verify.md.j2"


def verified_stage_config_get(
    *,
    allow_user_config: bool = False,
    browser_runtime_mcp_url: str = "",
    prompt_context: str,
    prompt_scope: PromptScope | None,
    result_dir: Path,
    stage_dir: Path,
    stage_key: str,
) -> VerifiedCodexStageConfig:
    """Return a runtime verified stage config for one domain stage.

    Args:
        allow_user_config: Whether Codex may use user config and browser MCP tools.
        browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
        prompt_context: Stage-specific prompt context.
        prompt_scope: Parsed workflow-run prompt scope.
        result_dir: Root result directory.
        stage_dir: Stage artifact directory.
        stage_key: Stable stage key.

    Returns:
        Runtime verified stage config.
    """

    return VerifiedCodexStageConfig(
        action_template_name=prompt_template_name_get(stage_key),
        allow_user_config=allow_user_config,
        browser_runtime_mcp_url=browser_runtime_mcp_url,
        prompt_context=prompt_context,
        result_dir=result_dir,
        shared_instruction=prompt_scope.shared_instruction if prompt_scope else "",
        stage_dir=stage_dir,
        stage_instruction_text=stage_instruction_text_get(prompt_scope=prompt_scope, stage_key=stage_key),
        stage_key=stage_key,
        verification_template_name=verify_prompt_template_name_get(stage_key),
    )
