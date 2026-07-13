"""Behavior tests for the exact 0.4.0 to 0.5.0 input migration."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

MIGRATION_PATH = Path("migration/input/0.4.0_to_0.5.0.py")


def _legacy_input_get(brand_list_text: str = "Defacto\nMavi\n") -> dict[str, object]:
    """Build one complete legacy input with values that migration must preserve."""

    return {
        "request": {
            "brand_list_text": brand_list_text,
            "priority_country_code": "TR",
            "product_type_request_list": ["women_dress"],
            "source_type_allow_list": ["product"],
        },
        "config": {
            "instruction": "Keep this workflow instruction.",
            "step_map": {
                "canonical_select": {
                    "correction_attempt_limit": 4,
                    "instruction": "Keep this canonical instruction.",
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "max",
                },
                "coverage_decide": {
                    "correction_attempt_limit": 5,
                    "instruction": "Keep this coverage instruction.",
                    "model": "gpt-5.6-luna",
                    "reasoning_effort": "medium",
                },
                "source_discover": {
                    "concurrency": 3,
                    "correction_attempt_limit": 6,
                    "instruction": "Keep this discovery instruction.",
                    "model": "gpt-5.6-terra",
                    "reasoning_effort": "high",
                },
            },
        },
    }


def _migration_run(input_payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    """Run the executable migration through its public stdin/stdout boundary."""

    return subprocess.run(
        [str(MIGRATION_PATH)],
        check=False,
        env={**os.environ, "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}"},
        input=json.dumps(input_payload),
        capture_output=True,
        text=True,
    )


def test_input_migration_converts_legacy_text_and_adds_exact_profile_config() -> None:
    """Migrate only the removed field and exact new browser-profile settings."""

    legacy_input = _legacy_input_get()
    completed_process = _migration_run(legacy_input)

    assert completed_process.returncode == 0, completed_process.stderr
    migrated_input = json.loads(completed_process.stdout)
    Draft202012Validator(json.loads(Path("input.schema.json").read_text(encoding="utf-8"))).validate(migrated_input)
    assert migrated_input["request"] == {
        "brand_list": ["Defacto", "Mavi"],
        "priority_country_code": "TR",
        "product_type_request_list": ["women_dress"],
        "source_type_allow_list": ["product"],
    }
    assert migrated_input["config"]["instruction"] == legacy_input["config"]["instruction"]
    assert migrated_input["config"]["step_map"] == {
        "canonical_select": {
            **legacy_input["config"]["step_map"]["canonical_select"],
            "mcp_playwright_profile": None,
            "mcp_playwright_profile_source": None,
        },
        "coverage_decide": {
            **legacy_input["config"]["step_map"]["coverage_decide"],
            "mcp_playwright_profile": None,
            "mcp_playwright_profile_source": None,
        },
        "source_discover": {
            **legacy_input["config"]["step_map"]["source_discover"],
            "mcp_playwright_profile": "source-discover",
            "mcp_playwright_profile_source": None,
        },
    }
    assert migrated_input["config"]["mcp_playwright_profile_writeback_policy"] == {
        "mcp_playwright_profile_name_prefix": "",
        "workflow_run_status_list": ["done"],
    }
    assert completed_process.stdout == json.dumps(migrated_input, separators=(",", ":"), sort_keys=True) + "\n"
    assert "brand_list_text" not in completed_process.stdout


@pytest.mark.parametrize(
    "brand_list_text",
    ["", "\n# comment\n", "Defacto\nDefacto\n", "LC Waikiki\nlc waikiki\n"],
)
def test_input_migration_rejects_invalid_final_brand_list(brand_list_text: str) -> None:
    """Reject legacy text that cannot produce the strict final brand-list contract."""

    completed_process = _migration_run(_legacy_input_get(brand_list_text))

    assert completed_process.returncode != 0
    assert completed_process.stdout == ""
