"""Run result models."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict
from workflow_container_contract import WorkflowResult

from brand_size_chart.model.brand import BrandResult
from brand_size_chart.model.base import IdentifierComponent, StrictBaseModel


class BrandSafepoint(StrictBaseModel):
    """Durable workspace marker for one accepted brand result."""

    parsed_brand_key: IdentifierComponent
    parsed_brand_name: str
    status: Literal["success", "failed"]


class RunResult(WorkflowResult):
    """Workflow result for one run."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True, validate_default=True)

    brand_result_list: list[BrandResult]
