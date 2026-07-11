"""Final brand-output mechanical validation."""

from pathlib import Path

from workflow_container_runtime.step import StepResultValidationError, WorkflowStepExecutionContext

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import BrandOutputInput, BrandOutputResult, BrandSizeChart


class BrandOutputValidator:
    """Validate final brand chart publication against persisted targets."""

    def validate(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: BrandOutputInput,
        result: BrandOutputResult,
    ) -> None:
        """Validate exact public paths and final chart files.

        Args:
            execution_context: Current step execution context.
            step_input: Persisted final-output input used by the deterministic action.
            result: Candidate public final-output result.

        Raises:
            StepResultValidationError: If output paths or chart files violate their mechanical contract.
        """

        expected_output_artifact_path_list = [
            output_item.output_write_target.artifact_path for output_item in step_input.output_item_list
        ]
        if result.size_chart_path_list != expected_output_artifact_path_list:
            raise StepResultValidationError(
                feedback_list=[
                    "Return size_chart_path_list exactly from BrandOutputInput.output_item_list in the same order; "
                    f"expected {expected_output_artifact_path_list}, received {result.size_chart_path_list}."
                ]
            )

        layout = ArtifactLayout(execution_context.result_dir)
        for output_item in step_input.output_item_list:
            output_write_target = output_item.output_write_target
            output_path_text = output_write_target.filesystem_path
            output_path = Path(output_path_text)
            if not output_path.is_absolute():
                raise StepResultValidationError(
                    feedback_list=["Keep every output_write_target.filesystem_path absolute and inside result_dir."]
                )
            output_path = output_path.resolve()
            try:
                expected_output_artifact_path = layout.artifact_path(output_path)
            except ValueError as exc:
                raise StepResultValidationError(
                    feedback_list=[
                        "Keep every output_write_target.filesystem_path inside result_dir; outside target: "
                        f"{output_write_target.filesystem_path}."
                    ]
                ) from exc

            if output_write_target.artifact_path != expected_output_artifact_path:
                raise StepResultValidationError(
                    feedback_list=[
                        "Make each output_write_target.artifact_path the exact normalized result-relative reference "
                        "for its filesystem_path; "
                        f"expected {expected_output_artifact_path}, received {output_write_target.artifact_path}."
                    ]
                )
            source_chart_path = Path(output_item.source_chart_path)
            if (
                not output_item.source_chart_path
                or source_chart_path.is_absolute()
                or ".." in source_chart_path.parts
                or source_chart_path.as_posix() != output_item.source_chart_path
            ):
                raise StepResultValidationError(
                    feedback_list=[
                        "Keep every source_chart_path normalized and result-relative; "
                        f"received {output_item.source_chart_path}."
                    ]
                )
            source_chart = (layout.result_dir / source_chart_path).resolve()
            try:
                expected_source_chart_path = layout.artifact_path(source_chart)
            except ValueError as exc:
                raise StepResultValidationError(
                    feedback_list=[
                        f"Keep every selected source chart inside result_dir: {output_item.source_chart_path}."
                    ]
                ) from exc
            if expected_source_chart_path != output_item.source_chart_path or not source_chart.is_file():
                raise StepResultValidationError(
                    feedback_list=[
                        f"Keep every selected source chart inside result_dir: {output_item.source_chart_path}."
                    ]
                )
            try:
                source_chart_model = BrandSizeChart.model_validate_json(source_chart.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise StepResultValidationError(
                    feedback_list=[
                        f"Rewrite source chart {output_item.source_chart_path} as valid BrandSizeChart: {exc}."
                    ]
                ) from exc
            if not output_path.is_file():
                raise StepResultValidationError(
                    feedback_list=[f"Create the missing final BrandSizeChart JSON artifact at {output_path}."]
                )
            try:
                output_chart = BrandSizeChart.model_validate_json(output_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise StepResultValidationError(
                    feedback_list=[
                        f"Rewrite the final output at {output_path} as valid BrandSizeChart JSON; validation "
                        f"failed: {exc}."
                    ]
                ) from exc
            if output_chart != source_chart_model:
                raise StepResultValidationError(
                    feedback_list=[
                        f"Keep final chart content exactly equal to selected source chart {output_item.source_chart_path}."
                    ]
                )
