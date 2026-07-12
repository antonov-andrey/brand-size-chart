"""Typed persisted inputs for workflow steps."""

from pathlib import Path

from brand_size_chart.model.base import IdentifierComponent, StrictBaseModel
from brand_size_chart.model.brand import BrandInput
from brand_size_chart.model.source import SourceTypeResultList


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


class SourceDiscoveryInput(StrictBaseModel):
    """Persist stable source-discovery domain data and workflow-input identity."""

    brand_input: BrandInput
    evidence_write_target: ArtifactWriteTarget
    source_type: IdentifierComponent
    workflow_input_path: Path
