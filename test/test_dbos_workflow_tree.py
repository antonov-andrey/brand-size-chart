"""Workflow-tree contract tests for one-step source discovery."""

import inspect

from brand_size_chart.workflow.source_type import BrandSizeChartSourceTypeWorkflow


def test_source_type_workflow_has_only_source_discovery_step_dependency() -> None:
    """Keep downstream decisions outside the child source workflow."""

    assert set(inspect.signature(BrandSizeChartSourceTypeWorkflow.__init__).parameters) == {
        "self",
        "artifact_writer",
        "config_name",
        "source_discovery_step",
    }
