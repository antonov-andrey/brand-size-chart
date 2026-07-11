"""Behavior validation for standard workflow source files."""

from pathlib import Path

from workflow_container_contract.testing import workflow_contract_file_validate


def test_workflow_source_contract_files_validate() -> None:
    """Validate workflow.yaml and versions.yaml through their shared contract package."""

    workflow_contract_file_validate(project_root=Path(__file__).resolve().parents[1])
