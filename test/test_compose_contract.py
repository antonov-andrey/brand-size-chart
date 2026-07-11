"""Behavior tests for the local browser-profile lifecycle in Compose."""

from pathlib import Path

import yaml


def test_compose_keeps_profile_runtime_durable_and_writeback_explicit() -> None:
    """Keep mutable profile state in one volume and expose one writeback-only service."""

    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    service_by_name_map = compose["services"]
    playwright_service = service_by_name_map["playwright-mcp"]
    writeback_service = service_by_name_map["playwright-profile-writeback"]

    assert "browser-profile-runtime:/runtime-profile" in playwright_service["volumes"]
    assert "/runtime-profile/playwright_profile" in " ".join(playwright_service["command"])
    assert writeback_service["profiles"] == ["writeback"]
    assert writeback_service["command"][0] == "browser-vpn-runtime-playwright-profile-snapshot"
    assert "browser-profile-runtime:/runtime-profile:ro" in writeback_service["volumes"]
    assert "./.secret:/writeback" in writeback_service["volumes"]
    assert "./.secret:/input/.secret:ro" in playwright_service["volumes"]
    assert "./.secret:/input/.secret:ro" in service_by_name_map["workflow"]["volumes"]

    for service_name, service in service_by_name_map.items():
        writable_secret_mount_list = [
            volume
            for volume in service.get("volumes", [])
            if isinstance(volume, str) and volume.startswith("./.secret:") and not volume.endswith(":ro")
        ]
        assert writable_secret_mount_list == (
            ["./.secret:/writeback"] if service_name == "playwright-profile-writeback" else []
        )


def test_compose_isolates_browser_from_openvpn_tunnel_lifecycle() -> None:
    """Route browser egress through SOCKS without sharing the VPN namespace."""

    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))
    service_by_name_map = compose["services"]
    vpn_egress_service = service_by_name_map["vpn-egress"]
    playwright_service = service_by_name_map["playwright-mcp"]
    workflow_service = service_by_name_map["workflow"]

    assert "entrypoint" not in playwright_service
    assert "network_mode" not in playwright_service
    assert playwright_service["networks"] == ["browser-control"]
    assert set(vpn_egress_service["networks"]) == {"browser-control", "vpn-uplink"}
    assert set(workflow_service["networks"]) == {"browser-control", "vpn-uplink"}
    assert compose["networks"]["browser-control"]["internal"] is True
    assert compose["networks"]["vpn-uplink"]["internal"] is False
    assert "--vpn-proxy-server vpn-egress:1080" in " ".join(playwright_service["command"])
    assert workflow_service["environment"]["BROWSER_RUNTIME_MCP_URL"] == "http://playwright-mcp:8931/mcp"
