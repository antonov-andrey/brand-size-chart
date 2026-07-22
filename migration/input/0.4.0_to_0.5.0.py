#!/usr/bin/env python3
"""Migrate one complete brand size-chart input from 0.4.0 to 0.5.0."""

import json
import sys

from brand_size_chart.model import WorkflowBrandSizeChartInput


def main() -> int:
    """Read one legacy input, validate the exact migrated model, and emit canonical JSON.

    Returns:
        Process exit code.
    """

    input_payload = json.load(sys.stdin)
    request_payload = input_payload["request"]
    brand_list_text = request_payload.pop("brand_list_text")
    request_payload["brand_list"] = [
        brand_name
        for raw_brand_name in brand_list_text.splitlines()
        if (brand_name := " ".join(raw_brand_name.split())) and not brand_name.startswith("#")
    ]

    config_payload = input_payload["config"]
    config_payload["mcp_playwright_profile_writeback_policy"] = {
        "mcp_playwright_profile_name_prefix": "",
        "workflow_run_status_list": ["done"],
    }
    for step_key in ("canonical_select", "coverage_decide", "source_discover"):
        step_config_payload = config_payload["step_map"][step_key]
        step_config_payload["mcp_playwright_network_proxy_name"] = None
        step_config_payload["mcp_playwright_profile"] = "source-discover" if step_key == "source_discover" else None
        step_config_payload["mcp_playwright_profile_source"] = None

    migrated_input = WorkflowBrandSizeChartInput.model_validate_json(json.dumps(input_payload))
    print(json.dumps(migrated_input.model_dump(mode="json"), separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
