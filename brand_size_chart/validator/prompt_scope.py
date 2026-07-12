"""Prompt-scope mechanical validation."""

from workflow_container_runtime.step import StepResultValidationError, WorkflowStepExecutionContext

from brand_size_chart.model import (
    PromptScope,
    PromptStepInstruction,
    WorkflowRunPromptApplyInput,
)

STEP_KEY_SET = frozenset(
    {
        "canonical_select",
        "coverage_decide",
        "source_discover",
        "workflow_run_prompt_apply",
    }
)


def _step_instruction_list_validate(step_instruction_list: list[PromptStepInstruction]) -> None:
    """Reject instructions assigned to unknown workflow steps.

    Args:
        step_instruction_list: Parsed step-specific instructions.

    Raises:
        StepResultValidationError: If one instruction names an unknown step.
    """

    unknown_step_key_list = sorted(
        {
            step_instruction.step_key
            for step_instruction in step_instruction_list
            if step_instruction.step_key not in STEP_KEY_SET
        }
    )
    if unknown_step_key_list:
        raise StepResultValidationError(
            feedback_list=[
                "Replace every unsupported step_key in step_instruction_list with one of "
                f"{sorted(STEP_KEY_SET)}; unsupported values: {unknown_step_key_list}."
            ]
        )


class PromptScopeValidator:
    """Validate prompt-derived execution keys and scope isolation."""

    def validate(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: WorkflowRunPromptApplyInput,
        result: PromptScope,
    ) -> None:
        """Validate one prompt scope against its persisted parsing input.

        Args:
            execution_context: Current step execution context.
            step_input: Persisted prompt-application input used by the action.
            result: Parsed prompt scope.

        Raises:
            StepResultValidationError: If the prompt scope violates its mechanical contract.
        """

        _ = execution_context
        source_type_set = {
            source_type_catalog_item.source_type for source_type_catalog_item in step_input.source_type_catalog_list
        }
        unknown_source_type_list = sorted(
            {source_type for source_type in result.source_type_allow_list if source_type not in source_type_set}
        )
        if unknown_source_type_list:
            raise StepResultValidationError(
                feedback_list=[
                    "Remove unsupported source_type_allow_list values and use only source types declared in input.json; "
                    f"unsupported values: {unknown_source_type_list}."
                ]
            )

        _step_instruction_list_validate(result.step_instruction_list)
