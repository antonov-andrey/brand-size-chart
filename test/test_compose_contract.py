"""Behavior tests for the local browser-profile lifecycle in Compose."""

from pathlib import Path

import yaml


def test_compose_uses_one_run_local_profile_router_and_direct_candidate_endpoint() -> None:
    """Keep source immutable while routing profiles and candidate publication through one service."""

    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    service_by_name_map = compose["services"]
    router_service = service_by_name_map["playwright-mcp-router"]

    assert "playwright-mcp" not in service_by_name_map
    assert "playwright-profile-writeback" not in service_by_name_map
    assert router_service["command"][0] == "browser-vpn-runtime-playwright-mcp-router"
    assert "browser-profile-runtime:/runtime/mcp_playwright_profile" in router_service["volumes"]
    assert "./.secret:/input/.secret:ro" in router_service["volumes"]
    assert "./.secret:/input/.secret:ro" in service_by_name_map["workflow"]["volumes"]
    workflow_environment = service_by_name_map["workflow"]["environment"]
    assert workflow_environment["MCP_PLAYWRIGHT_PROFILE_SOURCE"] == "/input/.secret/playwright_profile"
    assert workflow_environment["MCP_PLAYWRIGHT_PROFILE_WRITEBACK_CANDIDATE_URL"] == (
        "http://playwright-mcp-router:8931/runtime/mcp-playwright-profile/writeback-candidate"
    )
    assert workflow_environment["MCP_URL"] == "http://playwright-mcp-router:8931/mcp"


def test_compose_isolates_browser_from_openvpn_tunnel_lifecycle() -> None:
    """Route browser egress through SOCKS without sharing the VPN namespace."""

    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    service_by_name_map = compose["services"]
    vpn_egress_service = service_by_name_map["vpn-egress"]
    playwright_service = service_by_name_map["playwright-mcp-router"]
    workflow_service = service_by_name_map["workflow"]

    assert "entrypoint" not in playwright_service
    assert "network_mode" not in playwright_service
    assert playwright_service["networks"] == ["browser-control"]
    assert set(vpn_egress_service["networks"]) == {"browser-control", "vpn-uplink"}
    assert set(workflow_service["networks"]) == {"browser-control", "vpn-uplink"}
    assert compose["networks"]["browser-control"]["internal"] is True
    assert compose["networks"]["vpn-uplink"]["internal"] is False
    assert "--vpn-proxy-server vpn-egress:1080" in " ".join(playwright_service["command"])
    assert workflow_service["environment"]["MCP_URL"] == "http://playwright-mcp-router:8931/mcp"
