"""Shared contracts for semantic workflow steps."""

from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel
from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.stage import CodexStageRun, WorkflowStepCodexBase

from brand_size_chart.model import PromptScope

ActionOutputT = TypeVar("ActionOutputT", bound=BaseModel)
InputT = TypeVar("InputT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)

PROJECT_TEMPLATE_DIR = Path(__file__).parents[1] / "prompt" / "template"
STAGE_KEY_SET = frozenset(
    {
        "canonical_select",
        "coverage_decide",
        "source_discover",
        "table_extract",
        "workflow_run_prompt_apply",
    }
)


class BrandSizeChartCodexStepBase(
    WorkflowStepCodexBase[InputT, ActionOutputT, ResultT], Generic[InputT, ActionOutputT, ResultT]
):
    """Codex-backed base for brand-size-chart workflow steps."""

    def __init__(
        self,
        *,
        browser_runtime_mcp_url: str = "",
        codex_stage_run_callable: CodexStageRun,
        result_dir: Path,
        stage_dir: Path,
    ) -> None:
        """Store shared Codex-backed step dependencies.

        Args:
            browser_runtime_mcp_url: Run-level browser/VPN runtime MCP URL.
            codex_stage_run_callable: Codex stage execution boundary.
            result_dir: Root result directory.
            stage_dir: Stage artifact directory.
        """

        super().__init__(
            browser_runtime_mcp_url=browser_runtime_mcp_url,
            codex_stage_run_callable=codex_stage_run_callable,
            prompt_renderer=PromptRenderer(template_dir=PROJECT_TEMPLATE_DIR),
            result_dir=result_dir,
            stage_dir=stage_dir,
        )


def stage_instruction_list_get(*, prompt_scope: PromptScope, stage_key: str) -> list[str]:
    """Return stage instructions from the prompt scope.

    Args:
        prompt_scope: Parsed workflow-run prompt scope.
        stage_key: Current stage key.

    Returns:
        Stage-specific instruction list.
    """

    return [
        stage_instruction.instruction
        for stage_instruction in prompt_scope.stage_instruction_list
        if stage_instruction.stage_key == stage_key
    ]
