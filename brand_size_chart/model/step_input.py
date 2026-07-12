"""Typed persisted inputs for workflow steps."""

from pathlib import Path
from typing import Self

from workflow_container_runtime.step import WorkflowStepExecutionContext

from brand_size_chart.model.base import IdentifierComponent, StrictBaseModel
from brand_size_chart.model.brand import BrandInput
from brand_size_chart.model.source import SourceTypeResultList
from brand_size_chart.model.step_input_source import BrandSourceTypeResultInputSource


class ArtifactWriteTarget(StrictBaseModel):
    """Filesystem and public-reference paths for one step-owned artifact target."""

    artifact_path: str
    filesystem_path: str


class BrandOutputItem(StrictBaseModel):
    """One selected chart and its exact final output target."""

    output_write_target: ArtifactWriteTarget
    source_chart_path: str


class BrandOutputInput(StrictBaseModel):
    """Persisted input for final canonical chart publication."""

    output_item_list: list[BrandOutputItem]


class BrandSourceTypeResultStepInput(StrictBaseModel):
    """Persist source results and the exact complete workflow-input identity."""

    source_type_result_list: SourceTypeResultList
    workflow_input_path: Path

    @classmethod
    def from_execution_context_input_source(
        cls,
        execution_context: WorkflowStepExecutionContext,
        input_source: BrandSourceTypeResultInputSource,
    ) -> Self:
        """Build the persisted handoff from complete source results and the step context.

        Args:
            execution_context: Current workflow step context.
            input_source: Complete source-type results selected for one downstream step.

        Returns:
            Persisted source-result handoff.
        """

        return cls(
            source_type_result_list=input_source.source_type_result_list,
            workflow_input_path=execution_context.workflow_input_path,
        )


class SourceDiscoveryInput(StrictBaseModel):
    """Persist stable source-discovery domain data and workflow-input identity."""

    brand_input: BrandInput
    evidence_write_target: ArtifactWriteTarget
    source_type: IdentifierComponent
    workflow_input_path: Path
