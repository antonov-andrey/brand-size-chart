"""Run result models."""

from __future__ import annotations

from pydantic import Field

from brand_size_chart.model.base import StageStatus, StrictBaseModel
from brand_size_chart.model.brand import BrandListParseWarning, BrandResult
from brand_size_chart.model.prompt import PromptScope


class RunResult(StrictBaseModel):
    """Workflow result for one run."""

    brand_result_list: list[BrandResult]
    error_list: list[str] = Field(default_factory=list)
    message: str
    prompt_scope: PromptScope
    result_dir: str
    status: StageStatus
    warning_list: list[BrandListParseWarning]
    workflow_run_id: str
