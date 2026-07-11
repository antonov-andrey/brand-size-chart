"""Step instruction selection from one parsed prompt scope."""

from brand_size_chart.model import PromptScope

STEP_KEY_SET = frozenset(
    {
        "canonical_select",
        "coverage_decide",
        "source_discover",
        "workflow_run_prompt_apply",
    }
)


def step_instruction_list_get(*, prompt_scope: PromptScope, step_key: str) -> list[str]:
    """Return instructions owned by one step.

    Args:
        prompt_scope: Parsed workflow-run prompt scope.
        step_key: Current step key.

    Returns:
        Step-specific instruction list.
    """

    return [
        step_instruction.instruction
        for step_instruction in prompt_scope.step_instruction_list
        if step_instruction.step_key == step_key
    ]
