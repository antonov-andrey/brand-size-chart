"""Behavior validation for standard workflow source files."""

import tomllib
from pathlib import Path

import yaml
from workflow_container_contract.testing import workflow_contract_file_validate


def test_workflow_source_contract_files_validate() -> None:
    """Validate workflow.yaml and versions.yaml through their shared contract package."""

    workflow_contract_file_validate(project_root=Path(__file__).resolve().parents[1])


def test_workflow_source_targets_exact_0_5_contract_and_migration_edge() -> None:
    """Publish the incompatible input under its exact source and dependency versions."""

    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    workflow = yaml.safe_load(Path("workflow.yaml").read_text(encoding="utf-8"))
    versions = yaml.safe_load(Path("versions.yaml").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == "0.5.0"
    assert "workflow-container-contract>=0.3,<0.4" in pyproject["project"]["dependencies"]
    assert "workflow-container-runtime>=0.5,<0.6" in pyproject["project"]["dependencies"]
    assert workflow["image"] == "brand-size-chart:0.5.0"
    assert versions == {
        "project": "brand-size-chart",
        "version": "0.5.0",
        "contracts": {"workflow": 4, "artifact_schema": 3, "prompt_set": 3},
        "input_migrations": [
            {
                "from_version": "0.4.0",
                "to_version": "0.5.0",
                "script_path": "migration/input/0.4.0_to_0.5.0.py",
            }
        ],
    }
