"""Behavior tests for typed DBOS workflow wrappers."""

import asyncio
from pathlib import Path

from workflow_container_runtime.step import WorkflowStepInvocation
from workflow_container_runtime.workflow import WorkflowExecutionContext, WorkflowRuntimeCapability

from brand_size_chart.model import (
    BrandInput,
    SourceDiscoveryInputSource,
    SourceDiscoveryResult,
    WorkflowStepSourceDiscoverConfig,
)
from brand_size_chart.workflow.brand import BrandSizeChartBrandWorkflow


def test_source_discovery_wrapper_passes_exact_config_and_preserves_result_order(tmp_path: Path) -> None:
    """Delegate independently runnable sources to the concurrent runtime in registry order."""

    received: dict[str, object] = {}
    workflow = BrandSizeChartBrandWorkflow.__new__(BrandSizeChartBrandWorkflow)

    class SourceDiscoveryStep:
        """Record the concurrent runtime request without DBOS execution."""

        async def source_type_result_list_get(
            self,
            invocation_list: list[WorkflowStepInvocation[SourceDiscoveryInputSource]],
            workflow_step_config: WorkflowStepSourceDiscoverConfig,
        ) -> list[SourceDiscoveryResult]:
            """Record the exact typed concurrent work request."""

            received.update(invocation_list=invocation_list, workflow_step_config=workflow_step_config)
            return _result_list_get()

    workflow._source_discovery_step = SourceDiscoveryStep()
    context = WorkflowExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        workflow_instance_dir=tmp_path / "workflow" / "brand",
    )
    invocation_list = [
        WorkflowStepInvocation(
            execution_context=context.for_step(
                runtime_capability=WorkflowRuntimeCapability(browser=None),
                step_instance_key=f"source_discover_{source_type}",
            ),
            input_source=SourceDiscoveryInputSource(
                brand_input=BrandInput(
                    parsed_brand_key="brand", parsed_brand_name="Brand", raw_brand_name="Brand", source_line_number=1
                ),
                source_type=source_type,
            ),
        )
        for source_type in ["official_brand_size_guide", "official_seller_size_guide"]
    ]
    config = WorkflowStepSourceDiscoverConfig(
        concurrency=2,
        correction_attempt_limit=1,
        instruction="",
        model="gpt-5.6-terra",
        reasoning_effort="high",
    )

    result_list = asyncio.run(
        BrandSizeChartBrandWorkflow.source_discover_write_step_list.__wrapped__(workflow, invocation_list, config)
    )

    assert received == {"invocation_list": invocation_list, "workflow_step_config": config}
    assert result_list == _result_list_get()


def _result_list_get() -> list[SourceDiscoveryResult]:
    """Build distinct discovery results in input registry order."""

    return [
        SourceDiscoveryResult(
            browsing_error_list=[], outcome="no_table", source_discovery_database_path="first.sqlite3"
        ),
        SourceDiscoveryResult(
            browsing_error_list=[], outcome="table_available", source_discovery_database_path="second.sqlite3"
        ),
    ]
