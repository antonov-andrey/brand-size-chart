"""Run result models."""

from __future__ import annotations

from pydantic import ConfigDict, Field
from workflow_container_contract import WorkflowResult

from brand_size_chart.model.brand import BrandListParseWarning, BrandResult
from brand_size_chart.model.prompt import PromptScope


class RunResult(WorkflowResult):
    """Workflow result for one run."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True, validate_default=True)

    brand_list_parse_warning_list: list[BrandListParseWarning] = Field(default_factory=list)
    brand_result_list: list[BrandResult]
    prompt_scope: PromptScope | None
