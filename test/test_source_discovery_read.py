"""Read-only source-discovery downstream handoff contracts."""

from pathlib import Path

from brand_size_chart.model import BrandSourceTypeResultStepInput


def test_downstream_handoff_keeps_only_result_list_and_workflow_input_path() -> None:
    """Keep SQLite readers independent from copied workflow input/config objects."""

    step_input = BrandSourceTypeResultStepInput(
        source_type_result_list=[],
        workflow_input_path=Path("workflow/brand/input.json"),
    )

    assert step_input.workflow_input_path.as_posix() == "workflow/brand/input.json"
    assert step_input.source_type_result_list == []
