"""Stage verification models."""

from __future__ import annotations

from pydantic import Field

from brand_size_chart.model.base import StageStatus, StrictBaseModel


class StageVerification(StrictBaseModel):
    """Audit verification artifact for one completed stage."""

    artifact_path_list: list[str] = Field(default_factory=list)
    error_list: list[str] = Field(default_factory=list)
    feedback_list: list[str] = Field(default_factory=list)
    message: str
    stage_key: str
    status: StageStatus
