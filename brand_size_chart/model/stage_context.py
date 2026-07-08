"""Typed prompt-context models for Codex-backed stages."""

from pydantic import Field

from brand_size_chart.model.base import ApplicabilityStatus, IdentifierComponent, StrictBaseModel
from brand_size_chart.model.source import SourceDiscovery, TableExtractionArtifact


class StagePromptContextBase(StrictBaseModel):
    """Common user-instruction fields for one stage prompt context."""

    shared_instruction: str = ""
    stage_instruction_list: list[str] = Field(default_factory=list)


class ArtifactWriteTarget(StrictBaseModel):
    """Filesystem and artifact-reference paths for one stage-owned artifact target."""

    artifact_path: str
    filesystem_path: str


class CanonicalSelectionCandidate(StrictBaseModel):
    """Canonical-selection candidate with deterministic decision values."""

    applicability_status: ApplicabilityStatus
    source_priority: int = Field(ge=1)
    table_extraction_artifact: TableExtractionArtifact


class CanonicalSelectionPromptContext(StagePromptContextBase):
    """Prompt context for canonical selection."""

    brand_name: str
    canonical_selection_candidate_list: list[CanonicalSelectionCandidate]


class CoverageDecisionPromptContext(StagePromptContextBase):
    """Prompt context for requested product-type coverage decisions."""

    brand_name: str
    requested_product_type_list: list[str] = Field(default_factory=list)
    verified_table_artifact_list: list[TableExtractionArtifact]


class SourceDiscoveryPromptContext(StagePromptContextBase):
    """Prompt context for source discovery."""

    brand_name: str
    evidence_write_target: ArtifactWriteTarget
    priority_country_code: str
    requested_product_type_list: list[str] = Field(default_factory=list)
    source_type: str
    source_type_instruction: str


class SourceTypeCatalogItem(StrictBaseModel):
    """Prompt-application context for one supported source type."""

    discovery_instruction: str
    requires_product_type: bool
    source_type: IdentifierComponent


class TableExtractionExecplanItem(StrictBaseModel):
    """Prompt context for one table-extraction batch item."""

    chart_filesystem_path: str
    evidence_write_target: ArtifactWriteTarget
    source_discovery: SourceDiscovery


class TableExtractionPromptContext(StagePromptContextBase):
    """Prompt context for batch table extraction."""

    brand_name: str
    execplan_item_list: list[TableExtractionExecplanItem]


class WorkflowRunPromptApplyPromptContext(StrictBaseModel):
    """Prompt context for workflow-run prompt parsing."""

    source_type_catalog_list: list[SourceTypeCatalogItem]
    workflow_run_prompt: str
