"""Stable public inputs for brand size-chart workflows."""

from brand_size_chart.model.base import StrictBaseModel
from brand_size_chart.model.brand import BrandInput
from brand_size_chart.model.prompt import PromptScope


class RunInput(StrictBaseModel):
    """Public input for one root workflow run."""

    brand_list_text: str
    workflow_run_prompt: str


class BrandWorkflowInput(StrictBaseModel):
    """Public input for one brand workflow."""

    brand_input: BrandInput
    prompt_scope: PromptScope


class SourceTypeWorkflowInput(StrictBaseModel):
    """Public input for one source-type workflow."""

    brand_input: BrandInput
    prompt_scope: PromptScope
    source_type: str
