"""Installed package metadata behavior tests."""

import importlib.metadata


def test_installed_package_metadata_reports_coherent_release() -> None:
    """Require the active editable brand and runtime distributions to match the release."""

    assert importlib.metadata.version("brand-size-chart") == "0.7.0"
    assert importlib.metadata.version("workflow-container-runtime") == "0.7.0"
