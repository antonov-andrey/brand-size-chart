"""Workflow-tree contracts after direct concurrent source discovery migration."""

import inspect

from brand_size_chart.workflow.brand import BrandSizeChartBrandWorkflow


def test_brand_workflow_owns_source_discovery_without_source_type_proxy() -> None:
    """Keep the one-step source-type wrapper out of the concrete workflow graph."""

    assert "source_discovery_step" in inspect.signature(BrandSizeChartBrandWorkflow.__init__).parameters
    assert "source_type_workflow" not in inspect.signature(BrandSizeChartBrandWorkflow.__init__).parameters
