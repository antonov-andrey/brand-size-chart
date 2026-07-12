"""Source-discovery input migration contracts."""

from pathlib import Path

from brand_size_chart.model import ArtifactWriteTarget, BrandInput, SourceDiscoveryInput, SourceDiscoveryInputSource
from brand_size_chart.step.source_discovery import SourceDiscoveryStep
from workflow_container_runtime.step import WorkflowStepExecutionContext
from workflow_container_runtime.workflow import WorkflowRuntimeCapability


def test_source_discovery_builds_stable_input_without_workflow_config_copy(tmp_path: Path) -> None:
    """Build only stable source data plus the exact current workflow input path."""

    step = SourceDiscoveryStep.__new__(SourceDiscoveryStep)
    context = WorkflowStepExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        step_instance_dir=tmp_path / "workflow" / "brand" / "step" / "source_discover",
        workflow_input_path=Path("workflow/brand/input.json"),
    )
    input_source = SourceDiscoveryInputSource(
        brand_input=BrandInput(
            parsed_brand_key="brand", parsed_brand_name="Brand", raw_brand_name="Brand", source_line_number=1
        ),
        source_type="official_brand_size_guide",
    )
    step_input = SourceDiscoveryStep.input_build(step, context, input_source)

    assert isinstance(step_input, SourceDiscoveryInput)
    assert step_input.workflow_input_path == context.workflow_input_path
    assert step_input.source_type == input_source.source_type
