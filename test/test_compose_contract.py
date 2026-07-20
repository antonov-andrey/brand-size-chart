"""Behavior tests for the local browser-profile lifecycle in Compose."""

from pathlib import Path

import yaml


def test_compose_uses_one_direct_run_local_profile_router_and_standard_capability_document() -> None:
    """Keep source immutable while routing direct profiles through one typed capability file."""

    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    service_by_name_map = compose["services"]
    router_service = service_by_name_map["playwright-mcp-router"]

    assert "vpn-egress" not in service_by_name_map
    assert "playwright-mcp" not in service_by_name_map
    assert "playwright-profile-writeback" not in service_by_name_map
    assert router_service["command"][0] == "browser-vpn-runtime-playwright-mcp-router"
    assert router_service["command"][router_service["command"].index("--secret-root-path") + 1] == "/input/.secret"
    assert "--vpn-proxy-server" not in router_service["command"]
    assert "--data-source-path" not in router_service["command"]
    assert "browser-profile-runtime:/runtime/mcp_playwright_profile" in router_service["volumes"]
    assert any(
        volume.get("source") == "./.secret/playwright_profile"
        and volume.get("target") == "/input/.secret/playwright_profile"
        and volume.get("read_only") is True
        and volume.get("bind", {}).get("create_host_path") is False
        for volume in router_service["volumes"]
        if isinstance(volume, dict)
    )
    assert any(
        volume.get("source") == "./.secret/codex_profile"
        and volume.get("target") == "/input/.secret/codex_profile"
        and volume.get("read_only") is True
        and volume.get("bind", {}).get("create_host_path") is False
        for volume in service_by_name_map["workflow"]["volumes"]
        if isinstance(volume, dict)
    )
    workflow_service = service_by_name_map["workflow"]
    assert "additional_contexts" not in workflow_service["build"]
    assert workflow_service["command"] == ["brand-size-chart-run"]
    assert workflow_service["read_only"] is True
    assert workflow_service["tmpfs"] == ["/tmp:mode=1777"]
    assert "./compose.capability.json:/input/capability.json:ro" in workflow_service["volumes"]
    workflow_environment = workflow_service["environment"]
    assert workflow_environment["WORKFLOW_CAPABILITY_CONFIG_PATH"] == "/input/capability.json"
    assert workflow_environment["WORKFLOW_INPUT_PATH"] == "/input/input.json"
    assert workflow_environment["WORKFLOW_RUN_CONTEXT_PATH"] == "/input/run-context.json"
    assert workflow_environment["WORKFLOW_RUNTIME_PATH"] == "/runtime"
    assert any(
        volume.get("target") == "/input/run-context.json" and volume.get("read_only") is True
        for volume in workflow_service["volumes"]
        if isinstance(volume, dict)
    )


def test_compose_direct_mode_omits_openvpn_resources_and_proxy() -> None:
    """Give the current browser and workflow direct egress without OpenVPN resources."""

    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    service_by_name_map = compose["services"]
    playwright_service = service_by_name_map["playwright-mcp-router"]
    workflow_service = service_by_name_map["workflow"]

    assert "vpn-egress" not in service_by_name_map
    assert "entrypoint" not in playwright_service
    assert "network_mode" not in playwright_service
    assert set(playwright_service["networks"]) == {"browser-control", "runtime-uplink"}
    assert set(workflow_service["networks"]) == {"browser-control", "runtime-uplink"}
    assert compose["networks"]["browser-control"]["internal"] is True
    assert compose["networks"]["runtime-uplink"]["internal"] is False
    assert "--vpn-proxy-server" not in playwright_service["command"]
    assert "vpn-egress-runtime" not in compose["volumes"]
    assert workflow_service["environment"]["WORKFLOW_CAPABILITY_CONFIG_PATH"] == "/input/capability.json"
