"""Typed persisted inputs for workflow steps."""

from pydantic import Field

from brand_size_chart.model.base import IdentifierComponent, StrictBaseModel
from brand_size_chart.model.source import SourceTypeResultList
from brand_size_chart.model.workflow_input import BrandWorkflowInput, RunInput, SourceTypeWorkflowInput


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


class SourceTypeCatalogItem(StrictBaseModel):
    """Prompt-application context for one supported source type."""

    requires_product_type: bool
    source_type: IdentifierComponent


class StepInputBase(StrictBaseModel):
    """Common step-local instruction fields for one persisted step input."""

    step_instruction_list: list[str] = Field(default_factory=list)


class BrandSourceTypeResultStepInput(StepInputBase):
    """Persisted complete source results for brand-level downstream decisions."""

    source_type_result_list: SourceTypeResultList
    workflow_input: BrandWorkflowInput


class SourceDiscoveryInput(StepInputBase):
    """Persisted input for source discovery."""

    evidence_write_target: ArtifactWriteTarget
    workflow_input: SourceTypeWorkflowInput


class WorkflowRunPromptApplyInput(StrictBaseModel):
    """Persisted input for workflow-run prompt parsing."""

    source_type_catalog_list: list[SourceTypeCatalogItem]
    workflow_input: RunInput
