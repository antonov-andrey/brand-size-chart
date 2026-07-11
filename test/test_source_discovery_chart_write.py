"""Tests for safe source-discovery chart publication."""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from brand_size_chart.app.source_discovery_chart_write import main
from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandInput,
    PromptScope,
    SourceDiscoveryInput,
    SourceTypeWorkflowInput,
)

CHART_PAYLOAD = {
    "description": "Women's table with the manufacturer's regular fit.",
    "row_list": [
        {
            "measurement_list": [
                {"max_value": "M", "min_value": "M", "name": "Manufacturer size", "unit": "size"},
                {"max_value": "92", "min_value": "88", "name": "Bust", "unit": "cm"},
            ],
            "size_label": "M",
        }
    ],
}


def _command_run(input_path: Path, size_group_key: str, market_scope_key: str, payload: object) -> int:
    """Run the chart command with one JSON object supplied through standard input.

    Args:
        input_path: Current source-discovery input path.
        size_group_key: Source-derived physical table identity.
        market_scope_key: Validated market identity.
        payload: Candidate chart JSON value.

    Returns:
        Process exit code.
    """

    with patch("sys.stdin", StringIO(json.dumps(payload))):
        return main([str(input_path), size_group_key, market_scope_key])


def _input_path_write(step_dir: Path) -> Path:
    """Write one valid current source-discovery input artifact.

    Args:
        step_dir: Current source-discovery step directory.

    Returns:
        Written public input path.
    """

    step_dir.mkdir(parents=True, exist_ok=True)
    step_input = SourceDiscoveryInput(
        evidence_write_target=ArtifactWriteTarget(
            artifact_path="workflow/run/step/source_discover/evidence",
            filesystem_path=(step_dir / "evidence").as_posix(),
        ),
        workflow_input=SourceTypeWorkflowInput(
            brand_input=BrandInput(
                parsed_brand_key="brand",
                parsed_brand_name="Brand",
                raw_brand_name="Brand",
                source_line_number=1,
            ),
            prompt_scope=PromptScope(priority_country_code="TR"),
            source_type="official_brand_size_guide",
        ),
    )
    input_path = step_dir / "input.json"
    input_path.write_text(step_input.model_dump_json(), encoding="utf-8")
    return input_path


def test_chart_command_creates_validated_chart_at_derived_two_component_path(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Create a chart only under the current source-discovery step directory."""

    input_path = _input_path_write(tmp_path / "source_discover")

    assert _command_run(input_path, "women_clothing", "tr", CHART_PAYLOAD) == 0

    chart_path = input_path.parent / "chart" / "women_clothing__tr.json"
    assert json.loads(chart_path.read_text(encoding="utf-8")) == CHART_PAYLOAD
    assert json.loads(capsys.readouterr().out) == {
        "chart_filesystem_path": chart_path.resolve().as_posix(),
        "status": "created",
    }


def test_chart_command_keeps_existing_equal_chart_bytes_unchanged(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Treat an existing equivalent validated chart as a durable replay."""

    input_path = _input_path_write(tmp_path / "source_discover")
    chart_path = input_path.parent / "chart" / "women_clothing__tr.json"
    chart_path.parent.mkdir()
    existing_bytes = json.dumps(CHART_PAYLOAD, separators=(",", ":")).encode()
    chart_path.write_bytes(existing_bytes)

    assert _command_run(input_path, "women_clothing", "tr", CHART_PAYLOAD) == 0

    assert chart_path.read_bytes() == existing_bytes
    assert json.loads(capsys.readouterr().out)["status"] == "unchanged"


def test_chart_command_reports_conflict_without_overwriting_existing_bytes(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Preserve a different validated chart for later explicit conflict handling."""

    input_path = _input_path_write(tmp_path / "source_discover")
    chart_path = input_path.parent / "chart" / "women_clothing__tr.json"
    chart_path.parent.mkdir()
    existing_bytes = json.dumps({**CHART_PAYLOAD, "description": "Prior chart."}).encode()
    chart_path.write_bytes(existing_bytes)

    assert _command_run(input_path, "women_clothing", "tr", CHART_PAYLOAD) == 0

    assert chart_path.read_bytes() == existing_bytes
    assert json.loads(capsys.readouterr().out)["status"] == "conflict"


@pytest.mark.parametrize(
    ("payload", "size_group_key", "market_scope_key"),
    [
        ({"description": "missing rows"}, "women_clothing", "tr"),
        (CHART_PAYLOAD, "women__clothing", "tr"),
        (CHART_PAYLOAD, "women_clothing", "fr_de"),
    ],
)
def test_chart_command_rejects_invalid_input_without_creating_chart(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    payload: object,
    size_group_key: str,
    market_scope_key: str,
) -> None:
    """Reject malformed chart or identity input without changing the chart tree."""

    input_path = _input_path_write(tmp_path / "source_discover")
    with pytest.raises(SystemExit) as exc_info:
        _command_run(input_path, size_group_key, market_scope_key, payload)

    assert exc_info.value.code == 2
    assert not (input_path.parent / "chart").exists()
    assert capsys.readouterr().err


def test_chart_command_rejects_invalid_existing_chart_without_overwrite(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Fail closed when a prior chart is malformed rather than replacing its bytes."""

    input_path = _input_path_write(tmp_path / "source_discover")
    chart_path = input_path.parent / "chart" / "women_clothing__tr.json"
    chart_path.parent.mkdir()
    existing_bytes = b'{"description":"invalid"}'
    chart_path.write_bytes(existing_bytes)

    with pytest.raises(SystemExit) as exc_info:
        _command_run(input_path, "women_clothing", "tr", CHART_PAYLOAD)

    assert exc_info.value.code == 2
    assert chart_path.read_bytes() == existing_bytes
    assert capsys.readouterr().err


def test_chart_command_rejects_input_path_that_is_not_current_input(tmp_path: Path) -> None:
    """Accept only the canonical public input filename for its owning step."""

    input_path = _input_path_write(tmp_path / "source_discover")
    other_path = input_path.with_name("other.json")
    other_path.write_bytes(input_path.read_bytes())

    with pytest.raises(SystemExit) as exc_info:
        _command_run(other_path, "women_clothing", "tr", CHART_PAYLOAD)

    assert exc_info.value.code == 2
    assert not (input_path.parent / "chart").exists()
