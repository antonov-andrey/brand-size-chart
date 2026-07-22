"""Behavior validation for standard workflow source files."""

import json
import tomllib
from pathlib import Path

import yaml
from workflow_container_contract.testing import workflow_contract_file_validate

from brand_size_chart.model import BrandSizeChartDatasetRow
from workflow_container_runtime.artifact import JsonArtifactWriter


def test_workflow_source_contract_files_validate() -> None:
    """Validate workflow.yaml and versions.yaml through their shared contract package."""

    workflow_contract_file_validate(project_root=Path(__file__).resolve().parents[1])


def test_workflow_source_targets_exact_0_7_contract_and_migration_edge() -> None:
    """Publish the interface-v2 source with exact Data and dependency declarations."""

    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    workflow = yaml.safe_load(Path("workflow.yaml").read_text(encoding="utf-8"))
    versions = yaml.safe_load(Path("versions.yaml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == "0.7.1"
    assert "workflow-container-contract>=0.6,<0.7" in pyproject["project"]["dependencies"]
    assert "workflow-container-runtime>=0.7,<0.8" in pyproject["project"]["dependencies"]
    assert workflow["build"] == {"dockerfile_path": "docker/workflow/Dockerfile"}
    assert workflow["command"] == ["brand-size-chart-run"]
    assert workflow["test"] == {"command": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]}
    assert workflow["data"] == {"run": {"result": "result/{brand_key}", "workspace": "workspace/{brand_key}"}}
    assert workflow["dataset"] == {
        "brand_size_chart": {
            "data_path_template": "result/{brand_key}/dataset/brand_size_chart",
            "format": "json_lines",
            "manifest_key": "result",
            "schema_path": "dataset/brand_size_chart.schema.json",
            "schema_version": 1,
        }
    }
    assert workflow["secret"] == {
        "codex_profile": {"kind": "directory", "path": "/input/.secret/codex_profile"},
        "playwright_profile": {"kind": "directory", "path": "/input/.secret/playwright_profile"},
    }
    assert workflow["step"] == {
        "brand_complete": {},
        "canonical_select": {},
        "coverage_decide": {},
        "source_discover": {},
    }
    assert workflow["runtime_capability_list"] == [
        {
            "name": "browser_runtime",
            "secret_key_list": ["playwright_profile"],
        }
    ]
    assert versions == {
        "project": "brand-size-chart",
        "version": "0.7.1",
        "contracts": {"workflow": 7, "artifact_schema": 4, "prompt_set": 3},
        "input_migrations": [
            {
                "from_version": "0.4.0",
                "to_version": "0.5.0",
                "script_path": "migration/input/0.4.0_to_0.5.0.py",
            }
        ],
    }


def test_dataset_schema_is_generated_from_exact_row_model(tmp_path: Path) -> None:
    """Keep the tracked Athena row schema owned by its exact Pydantic model."""

    generated_schema_path = tmp_path / "brand_size_chart.schema.json"
    JsonArtifactWriter().schema_write(generated_schema_path, BrandSizeChartDatasetRow)

    assert json.loads(generated_schema_path.read_text(encoding="utf-8")) == json.loads(
        Path("dataset/brand_size_chart.schema.json").read_text(encoding="utf-8")
    )
