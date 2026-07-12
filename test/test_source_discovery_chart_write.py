"""Behavior tests for safe source-discovery chart publication."""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

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


def test_chart_command_creates_replays_and_preserves_conflicts(capsys: object, tmp_path: Path) -> None:
    """Create a valid chart, preserve equal bytes, and retain an explicit conflict."""

    input_path = _input_path_write(tmp_path / "source_discover")
    assert _command_run(input_path, CHART_PAYLOAD) == 0
    chart_path = input_path.parent / "chart" / "women_clothing__tr.json"
    assert json.loads(chart_path.read_text(encoding="utf-8")) == CHART_PAYLOAD
    assert json.loads(capsys.readouterr().out) == {"status": "created"}

    existing_bytes = chart_path.read_bytes()
    assert _command_run(input_path, CHART_PAYLOAD) == 0
    assert chart_path.read_bytes() == existing_bytes
    assert json.loads(capsys.readouterr().out) == {"status": "unchanged"}

    chart_path.write_text(json.dumps({**CHART_PAYLOAD, "description": "Prior chart."}), encoding="utf-8")
    conflict_bytes = chart_path.read_bytes()
    assert _command_run(input_path, CHART_PAYLOAD) == 0
    assert chart_path.read_bytes() == conflict_bytes
    assert json.loads(capsys.readouterr().out) == {"status": "conflict"}


def _command_run(input_path: Path, payload: object) -> int:
    """Run chart publication with one JSON object on standard input."""

    with patch("sys.stdin", StringIO(json.dumps(payload))):
        return main([str(input_path), "women_clothing", "tr"])


def _input_path_write(step_dir: Path) -> Path:
    """Write one current source-discovery input artifact."""

    step_dir.mkdir(parents=True)
    input_path = step_dir / "input.json"
    input_path.write_text(
        SourceDiscoveryInput(
            brand_input=BrandInput(
                parsed_brand_key="brand", parsed_brand_name="Brand", raw_brand_name="Brand", source_line_number=1
            ),
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
