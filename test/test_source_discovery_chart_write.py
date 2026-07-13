"""Behavior tests for safe source-discovery chart publication."""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from brand_size_chart.app.source_discovery_chart_write import main
from brand_size_chart.model import ArtifactWriteTarget, BrandInput, SourceDiscoveryInput

CHART_PAYLOAD = {
    "description": "Women's table with the manufacturer's regular fit.",
    "row_list": [
        {
            "measurement_list": [{"max_value": "M", "min_value": "M", "name": "Manufacturer size", "unit": "size"}],
            "size_label": "M",
        }
    ],
}


def test_chart_command_creates_validated_chart_at_derived_two_component_path(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Create a valid chart only below the current source-discovery step."""

    input_path = _input_path_write(tmp_path / "source_discover")
    assert _command_run(input_path, CHART_PAYLOAD) == 0
    chart_path = input_path.parent / "chart" / "women_clothing__tr.json"
    assert json.loads(chart_path.read_text(encoding="utf-8")) == CHART_PAYLOAD
    assert json.loads(capsys.readouterr().out) == {"status": "created"}


def test_chart_command_keeps_existing_equal_chart_bytes_unchanged(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Treat a valid equal chart as a replay without rewriting its bytes."""

    input_path = _input_path_write(tmp_path / "source_discover")
    chart_path = input_path.parent / "chart" / "women_clothing__tr.json"
    chart_path.parent.mkdir()
    existing_bytes = json.dumps(CHART_PAYLOAD, separators=(",", ":")).encode()
    chart_path.write_bytes(existing_bytes)

    assert _command_run(input_path, CHART_PAYLOAD) == 0

    assert chart_path.read_bytes() == existing_bytes
    assert json.loads(capsys.readouterr().out) == {"status": "unchanged"}


def test_chart_command_reports_conflict_without_overwriting_existing_bytes(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Retain a valid different chart for explicit conflict handling."""

    input_path = _input_path_write(tmp_path / "source_discover")
    chart_path = input_path.parent / "chart" / "women_clothing__tr.json"
    chart_path.parent.mkdir()
    existing_bytes = json.dumps({**CHART_PAYLOAD, "description": "Prior chart."}).encode()
    chart_path.write_bytes(existing_bytes)

    assert _command_run(input_path, CHART_PAYLOAD) == 0

    assert chart_path.read_bytes() == existing_bytes
    assert json.loads(capsys.readouterr().out) == {"status": "conflict"}


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
    """Reject invalid chart or identity input without creating a chart tree."""

    input_path = _input_path_write(tmp_path / "source_discover")
    with pytest.raises(SystemExit) as exc_info:
        _command_run(
            input_path,
            payload,
            size_group_key=size_group_key,
            market_scope_key=market_scope_key,
        )

    assert exc_info.value.code == 2
    assert not (input_path.parent / "chart").exists()
    assert capsys.readouterr().err


def test_chart_command_rejects_invalid_existing_chart_without_overwrite(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Fail closed when a prior chart is malformed instead of replacing it."""

    input_path = _input_path_write(tmp_path / "source_discover")
    chart_path = input_path.parent / "chart" / "women_clothing__tr.json"
    chart_path.parent.mkdir()
    existing_bytes = b'{"description":"invalid"}'
    chart_path.write_bytes(existing_bytes)

    with pytest.raises(SystemExit) as exc_info:
        _command_run(input_path, CHART_PAYLOAD)

    assert exc_info.value.code == 2
    assert chart_path.read_bytes() == existing_bytes
    assert capsys.readouterr().err


def test_chart_command_rejects_input_path_that_is_not_current_input(tmp_path: Path) -> None:
    """Accept only the canonical public input filename of the current step."""

    input_path = _input_path_write(tmp_path / "source_discover")
    other_path = input_path.with_name("other.json")
    other_path.write_bytes(input_path.read_bytes())

    with pytest.raises(SystemExit) as exc_info:
        _command_run(other_path, CHART_PAYLOAD)

    assert exc_info.value.code == 2
    assert not (input_path.parent / "chart").exists()


def _command_run(
    input_path: Path,
    payload: object,
    *,
    size_group_key: str = "women_clothing",
    market_scope_key: str = "tr",
) -> int:
    """Run chart publication with one JSON object on standard input."""

    with patch("sys.stdin", StringIO(json.dumps(payload))):
        return main([str(input_path), size_group_key, market_scope_key])


def _input_path_write(step_dir: Path) -> Path:
    """Write one current source-discovery input artifact."""

    step_dir.mkdir(parents=True)
    input_path = step_dir / "input.json"
    input_path.write_text(
        SourceDiscoveryInput(
            brand_input=BrandInput(parsed_brand_key="brand", parsed_brand_name="Brand"),
            evidence_write_target=ArtifactWriteTarget(
                artifact_path="workflow/run/step/source_discover/evidence",
                filesystem_path=(step_dir / "evidence").as_posix(),
            ),
            source_type="official_brand_size_guide",
            workflow_input_path=Path("workflow/run/input.json"),
        ).model_dump_json(),
        encoding="utf-8",
    )
    return input_path
