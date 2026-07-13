"""Run result models."""

from __future__ import annotations

from pydantic import ConfigDict
from workflow_container_contract import WorkflowResult

from brand_size_chart.model.brand import BrandResult


class RunResult(WorkflowResult):
    """Workflow result for one run."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True, validate_default=True)

    brand_result_list: list[BrandResult]
